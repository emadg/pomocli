use anyhow::{bail, Context, Result};
use ksni::{menu::StandardItem, TrayMethods};
use pomocli_desktop::{
    config::{self},
    desktop::{self, DesktopEvent},
    model::{AutomaticPause, CompletionTracker, Snapshot},
    process::ManagedChild,
    wire, BUS, INTERFACE, PATH,
};
use serde_json::{json, Value};
use std::{
    collections::HashSet,
    sync::{Arc, RwLock},
    time::{Duration, Instant},
};
use tokio::sync::{mpsc, oneshot};
use zbus::{Connection, Proxy};

type Shared = Arc<RwLock<Snapshot>>;
#[derive(Debug)]
struct Action {
    name: String,
    snapshot: Snapshot,
    reply: Option<oneshot::Sender<String>>,
    activation_token: Option<String>,
}
struct Desktop {
    shared: Shared,
    tx: mpsc::Sender<Action>,
}
#[zbus::interface(name = "org.pomocli.Desktop1")]
impl Desktop {
    #[zbus(property)]
    fn snapshot(&self) -> String {
        serde_json::to_string(&*self.shared.read().unwrap()).unwrap()
    }
    async fn action(&self, action: &str) -> String {
        let (reply, wait) = oneshot::channel();
        let snapshot = self.shared.read().unwrap().clone();
        if self
            .tx
            .try_send(Action {
                name: action.into(),
                snapshot,
                reply: Some(reply),
                activation_token: None,
            })
            .is_err()
        {
            return json!({"status":"error","message":"Desktop action queue is full"}).to_string();
        }
        wait.await.unwrap_or_else(|_| {
            json!({"status":"error","message":"Desktop companion is stopping"}).to_string()
        })
    }
    fn quit(&self) {
        let _ = self.tx.try_send(Action {
            name: "quit".into(),
            snapshot: self.shared.read().unwrap().clone(),
            reply: None,
            activation_token: None,
        });
    }
    #[zbus(signal, name = "SnapshotChanged")]
    async fn emit_snapshot_changed(
        emitter: &zbus::object_server::SignalEmitter<'_>,
        snapshot: &str,
    ) -> zbus::Result<()>;
}
#[derive(Debug)]
struct Tray {
    snapshot: Snapshot,
    tx: mpsc::Sender<Action>,
}
impl ksni::Tray for Tray {
    fn id(&self) -> String {
        "pomocli".into()
    }
    fn title(&self) -> String {
        self.snapshot.title()
    }
    fn icon_name(&self) -> String {
        if self.snapshot.feedback {
            "emblem-ok-symbolic"
        } else if !self.snapshot.connected {
            "network-offline-symbolic"
        } else if self.snapshot.state == "paused" {
            "media-playback-pause-symbolic"
        } else {
            "appointment-soon"
        }
        .into()
    }
    fn tool_tip(&self) -> ksni::ToolTip {
        ksni::ToolTip {
            title: self.snapshot.title(),
            description: self.snapshot.project_name.clone().unwrap_or_default(),
            icon_name: self.icon_name(),
            ..Default::default()
        }
    }
    fn activate(&mut self, _: i32, _: i32) {
        let _ = self.tx.try_send(Action {
            name: "quick-start".into(),
            snapshot: self.snapshot.clone(),
            reply: None,
            activation_token: None,
        });
    }
    fn menu(&self) -> Vec<ksni::MenuItem<Self>> {
        let mut items = vec![StandardItem {
            label: self.snapshot.title().replace('_', "__"),
            enabled: false,
            ..Default::default()
        }
        .into()];
        for (label, action, enabled) in [
            ("Quick Start…", "quick-start", !self.snapshot.active()),
            (
                "Log Distraction",
                "distract",
                self.snapshot.connected && self.snapshot.state == "running",
            ),
            (
                if self.snapshot.state == "paused" {
                    "Resume"
                } else {
                    "Pause"
                },
                if self.snapshot.state == "paused" {
                    "resume"
                } else {
                    "pause"
                },
                self.snapshot.active(),
            ),
            ("Stop", "stop", self.snapshot.active()),
        ] {
            items.push(self.item(label, action, enabled));
        }
        if self.snapshot.active() && self.snapshot.timer_mode == "elapsed" {
            items.push(self.item("Complete Session", "complete", true));
        }
        items.push(ksni::MenuItem::Separator);
        items.push(self.item("Quit Desktop Companion", "quit", true));
        items
    }
}
impl Tray {
    fn item(&self, label: &str, action: &str, enabled: bool) -> ksni::MenuItem<Self> {
        let snapshot = self.snapshot.clone();
        let name = action.to_string();
        StandardItem {
            label: label.into(),
            enabled,
            activate: Box::new(move |this: &mut Self| {
                let _ = this.tx.try_send(Action {
                    name: name.clone(),
                    snapshot: snapshot.clone(),
                    reply: None,
                    activation_token: None,
                });
            }),
            ..Default::default()
        }
        .into()
    }
}
#[derive(Clone)]
enum DialogKind {
    QuickStart,
    Distract(Snapshot),
    Return(AutomaticPause),
}
struct DialogResult {
    kind: DialogKind,
    result: Result<Value>,
}
fn spawn_dialog(
    kind: DialogKind,
    snapshot: &Snapshot,
    tx: mpsc::Sender<DialogResult>,
    activation_token: Option<&str>,
) -> ManagedChild {
    let mode = match kind {
        DialogKind::QuickStart => "quick-start",
        DialogKind::Distract(_) => "distract",
        DialogKind::Return(_) => "return",
    };
    let mut command = tokio::process::Command::new(config::dialog());
    command.arg(mode).arg(&snapshot.task_name);
    // Activation tokens are single use. A fresh portal token belongs only to
    // this helper; never inherit an old token from the resident companion.
    command.env_remove("XDG_ACTIVATION_TOKEN");
    if let Some(token) = activation_token {
        command.env("XDG_ACTIVATION_TOKEN", token);
    }
    ManagedChild::spawn(command, move |output| {
        let result = output.and_then(|output| {
            if !output.status.success() {
                bail!(
                    "Dialog helper exited unsuccessfully: {}",
                    String::from_utf8_lossy(&output.stderr).trim()
                );
            }
            if output.stdout.is_empty() {
                return Ok(json!({"action":"cancel"}));
            }
            serde_json::from_slice(&output.stdout).context("Invalid dialog response")
        });
        let _ = tx.try_send(DialogResult { kind, result });
    })
}

async fn read_status() -> Result<Snapshot> {
    let response = wire::request(&config::socket(), "status", json!({})).await?;
    Snapshot::from_data(response.data)
}
async fn publish(
    connection: &Connection,
    shared: &Shared,
    snapshot: &Snapshot,
    tray: &Option<ksni::Handle<Tray>>,
) {
    let changed = *shared.read().unwrap() != *snapshot;
    if !changed {
        return;
    }
    *shared.write().unwrap() = snapshot.clone();
    if let Some(handle) = tray {
        handle.update(|tray| tray.snapshot = snapshot.clone()).await;
    }
    if let Ok(interface) = connection
        .object_server()
        .interface::<_, Desktop>(PATH)
        .await
    {
        let _ = interface
            .get()
            .await
            .snapshot_changed(interface.signal_emitter())
            .await;
        let _ = Desktop::emit_snapshot_changed(
            interface.signal_emitter(),
            &serde_json::to_string(snapshot).unwrap(),
        )
        .await;
    }
}
async fn error_notification(connection: &Connection, message: &str) {
    eprintln!("PomoCLI: {message}");
    let _ = desktop::notify(connection, "PomoCLI", message, false).await;
}
async fn perform(name: &str, captured: &Snapshot, args: Option<Value>) -> Result<()> {
    if !captured.active() {
        bail!("There is no active session");
    }
    if name == "distract" && captured.state != "running" {
        bail!("Distractions can only be logged while running");
    }
    if name == "complete" && captured.timer_mode != "elapsed" {
        bail!("Only stopwatch sessions can be completed manually");
    }
    let mut arguments = args.unwrap_or_else(|| captured.guards());
    if name == "pause" {
        arguments["source"] = json!("manual");
    }
    wire::request(&config::socket(), name, arguments).await?;
    Ok(())
}
async fn forward(connection: &Connection, quick: bool, quit: bool) -> Result<bool> {
    let proxy = Proxy::new(connection, BUS, PATH, INTERFACE).await?;
    match proxy.get_property::<String>("Snapshot").await {
        Ok(_) => {
            if quit {
                proxy.call::<_, _, ()>("Quit", &()).await?;
            } else if quick {
                let response: String = proxy.call("Action", &("quick-start",)).await?;
                println!("{response}");
            } else {
                let _: String = proxy.call("Action", &("refresh",)).await?;
            }
            Ok(true)
        }
        Err(_) => Ok(false),
    }
}
#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<()> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    if arguments.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!("pomo-tray [--quick-start] [--quit] [--doctor] [--no-tray]\nLightweight PomoCLI desktop companion. Quit leaves the timer daemon running.");
        return Ok(());
    }
    for argument in &arguments {
        if !matches!(
            argument.as_str(),
            "--quick-start" | "--quit" | "--doctor" | "--no-tray"
        ) {
            bail!("Unknown option: {argument}");
        }
    }
    let config = config::load();
    let connection = zbus::connection::Builder::session()?
        .method_timeout(Duration::from_secs(3))
        .build()
        .await
        .context("A desktop D-Bus session is required")?;
    if arguments.iter().any(|arg| arg == "--doctor") {
        println!(
            "{}",
            serde_json::to_string_pretty(&desktop::doctor(&connection).await)?
        );
        return Ok(());
    }
    let quick = arguments.iter().any(|arg| arg == "--quick-start");
    let quit = arguments.iter().any(|arg| arg == "--quit");
    if forward(&connection, quick, quit).await? {
        return Ok(());
    }
    if quit {
        return Ok(());
    }
    let shared: Shared = Arc::new(RwLock::new(Snapshot::default()));
    let (action_tx, mut actions) = mpsc::channel(32);
    connection
        .object_server()
        .at(
            PATH,
            Desktop {
                shared: shared.clone(),
                tx: action_tx.clone(),
            },
        )
        .await?;
    if let Err(error) = connection.request_name(BUS).await {
        // Another launcher can acquire the name between discovery and request.
        if forward(&connection, quick, quit).await? {
            return Ok(());
        }
        return Err(error.into());
    }
    let tray = if config.linux.show_tray && !arguments.iter().any(|arg| arg == "--no-tray") {
        match (Tray {
            snapshot: Snapshot::default(),
            tx: action_tx.clone(),
        })
        .spawn()
        .await
        {
            Ok(handle) => Some(handle),
            Err(error) => {
                eprintln!("System tray unavailable: {error}; KDE panel and D-Bus controls remain available");
                None
            }
        }
    } else {
        None
    };
    let (desktop_tx, mut desktop_events) = mpsc::channel(32);
    if config.linux.desktop_integration {
        desktop::spawn_monitors(&connection, &config, desktop_tx);
    }
    let (dialog_tx, mut dialogs) = mpsc::channel(4);
    let mut dialog_busy = false;
    let mut dialog_job: Option<ManagedChild> = None;
    let mut snapshot = Snapshot::default();
    let mut tracker = CompletionTracker::default();
    let mut automatic: Option<AutomaticPause> = None;
    let mut return_prompt_pending = false;
    let mut away = HashSet::new();
    let mut feedback_until: Option<Instant> = None;
    let mut backoff = 1_u64;
    let mut next_poll = tokio::time::Instant::now();
    if quick {
        let _ = action_tx.try_send(Action {
            name: "quick-start".into(),
            snapshot: snapshot.clone(),
            reply: None,
            activation_token: None,
        });
    }
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    loop {
        tokio::select! {
            _ = tokio::signal::ctrl_c() => break,
            _ = terminate.recv() => break,
            _ = tokio::time::sleep_until(next_poll) => {
                match read_status().await {
                    Ok(mut fresh) => {
                        fresh.feedback = feedback_until.is_some_and(|until| Instant::now() < until);
                        if tracker.observe(&fresh) {
                            let task = fresh.completion_description(&snapshot);
                            let _ = desktop::notify(&connection, "Session complete", &task, config.sound_enabled).await;
                        }
                        if automatic.as_ref().is_some_and(|pause| !pause.matches(&fresh)) { automatic = None; }
                        snapshot = fresh; backoff = 1;
                    }
                    Err(error) => { if snapshot.connected { eprintln!("Daemon disconnected: {error:#}"); } snapshot.connected = false; snapshot.feedback = false; backoff = (backoff * 2).min(30); }
                }
                publish(&connection, &shared, &snapshot, &tray).await;
                next_poll = tokio::time::Instant::now() + Duration::from_secs(if snapshot.connected { 1 } else { backoff });
            }
            Some(action) = actions.recv() => {
                if action.name == "quit" { if let Some(reply) = action.reply { let _ = reply.send(json!({"status":"ok"}).to_string()); } break; }
                let result: Result<()> = match action.name.as_str() {
                    // A CLI autolaunch can find the companion in a long daemon
                    // reconnect backoff. Wake the shared poll immediately.
                    "refresh" => Ok(()),
                    "quick-start" if snapshot.active() => Err(anyhow::anyhow!("A session is already active; stop or complete it first")),
                    "quick-start" if dialog_busy => Err(anyhow::anyhow!("A dialog is already open")),
                    "quick-start" => { dialog_job = Some(spawn_dialog(DialogKind::QuickStart, &snapshot, dialog_tx.clone(), action.activation_token.as_deref())); dialog_busy = true; Ok(()) }
                    "distract" if feedback_until.is_some_and(|until| Instant::now() < until) => Err(anyhow::anyhow!("Distraction already logged; please wait")),
                    "distract" if config.distraction_note_prompt && action.snapshot.active() && action.snapshot.state == "running" => {
                        if dialog_busy { Err(anyhow::anyhow!("A dialog is already open")) }
                        else { dialog_job = Some(spawn_dialog(DialogKind::Distract(action.snapshot.clone()), &snapshot, dialog_tx.clone(), action.activation_token.as_deref())); dialog_busy = true; Ok(()) }
                    }
                    "pause" | "resume" | "stop" | "complete" | "distract" => {
                        let result = perform(&action.name, &action.snapshot, None).await;
                        if result.is_ok() && action.name == "distract" { feedback_until = Some(Instant::now() + Duration::from_secs(2)); }
                        if result.is_ok() && matches!(action.name.as_str(), "resume" | "stop" | "complete") { automatic = None; }
                        result
                    }
                    _ => Err(anyhow::anyhow!("Unknown desktop action")),
                };
                let response = match &result { Ok(()) => json!({"status":"ok"}), Err(error) => json!({"status":"error","message":error.to_string()}) };
                if let Some(reply) = action.reply { let _ = reply.send(response.to_string()); }
                if let Err(error) = result { error_notification(&connection, &error.to_string()).await; }
                next_poll = tokio::time::Instant::now();
            }
            Some(event) = desktop_events.recv() => {
                match event {
                    DesktopEvent::Shortcut { action: name, activation_token } => { let _ = action_tx.try_send(Action { name, snapshot:snapshot.clone(), reply:None, activation_token }); }
                    DesktopEvent::Presence { source, active, acknowledged } => {
                        let changed = if active { away.insert(source) } else { away.remove(source) };
                        if changed && active {
                            if let Ok(fresh) = read_status().await {
                                let provenance = if source == "idle" { "idle" } else { "screen_lock" };
                                if let Some(pause) = AutomaticPause::from_running(&fresh, provenance) {
                                    let mut args = fresh.guards(); args["source"] = json!(provenance);
                                    if wire::request(&config::socket(), "pause", args).await.is_ok() { automatic = Some(pause); return_prompt_pending = true; }
                                }
                            }
                        }
                        if let Some(done) = acknowledged { let _ = done.send(()); }
                        if changed && !active && automatic.is_some() { return_prompt_pending = true; }
                        next_poll = tokio::time::Instant::now();
                    }
                }
            }
            Some(dialog) = dialogs.recv() => {
                dialog_busy = false;
                if let Some(job) = dialog_job.take() { job.stop().await; }
                match dialog.result {
                    Err(error) => error_notification(&connection, &error.to_string()).await,
                    Ok(value) => {
                        let action = value["action"].as_str().unwrap_or("cancel");
                        match dialog.kind {
                            DialogKind::QuickStart => {},
                            DialogKind::Distract(captured) if action == "distract" => {
                                let mut args = captured.guards(); args["description"] = value.get("description").cloned().unwrap_or(Value::Null);
                                match perform("distract", &captured, Some(args)).await {
                                    Ok(()) => feedback_until = Some(Instant::now() + Duration::from_secs(2)),
                                    Err(error) => error_notification(&connection, &error.to_string()).await,
                                }
                            }
                            DialogKind::Return(pause) if matches!(action, "resume" | "stop") => {
                                match read_status().await {
                                    Ok(fresh) if pause.matches(&fresh) && away.is_empty() => {
                                        if let Err(error) = wire::request(&config::socket(), action, pause.guards()).await { error_notification(&connection, &error.to_string()).await; }
                                        automatic = None;
                                    }
                                    _ => { automatic = None; error_notification(&connection, "This paused session has changed; no action was taken.").await; }
                                }
                            }
                            _ => {},
                        }
                    }
                }
                next_poll = tokio::time::Instant::now();
            }
        }
        // A distraction/quick-start dialog may already be open when the owner
        // returns. Defer the return question until that helper has exited.
        if return_prompt_pending && away.is_empty() && !dialog_busy {
            return_prompt_pending = false;
            if let Some(pause) = &automatic {
                if let Ok(fresh) = read_status().await {
                    if pause.matches(&fresh) {
                        dialog_job = Some(spawn_dialog(
                            DialogKind::Return(pause.clone()),
                            &fresh,
                            dialog_tx.clone(),
                            None,
                        ));
                        dialog_busy = true;
                    } else {
                        automatic = None;
                    }
                }
            }
        }
    }
    if let Some(job) = dialog_job.take() {
        job.stop().await;
    }
    if let Some(handle) = tray {
        handle.shutdown().await;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use ksni::Tray as _;
    fn tray(snapshot: Snapshot) -> Tray {
        let (tx, _) = mpsc::channel(4);
        Tray { snapshot, tx }
    }
    fn labels(tray: &Tray) -> Vec<(String, bool)> {
        tray.menu()
            .into_iter()
            .filter_map(|item| match item {
                ksni::MenuItem::Standard(item) => Some((item.label, item.enabled)),
                _ => None,
            })
            .collect()
    }
    #[test]
    fn disconnected_menu_preserves_quick_start_and_disables_timer_controls() {
        let menu = labels(&tray(Snapshot::default()));
        assert!(menu.contains(&("Quick Start…".into(), true)));
        assert!(menu.contains(&("Log Distraction".into(), false)));
        assert!(menu.contains(&("Stop".into(), false)));
    }
    #[test]
    fn complete_is_only_visible_for_active_stopwatch() {
        let mut snapshot = Snapshot {
            connected: true,
            state: "running".into(),
            session_id: Some(1),
            ..Snapshot::default()
        };
        assert!(!labels(&tray(snapshot.clone()))
            .iter()
            .any(|(label, _)| label == "Complete Session"));
        snapshot.timer_mode = "elapsed".into();
        assert!(labels(&tray(snapshot.clone())).contains(&("Complete Session".into(), true)));
        snapshot.state = "paused".into();
        let menu = labels(&tray(snapshot));
        assert!(menu.contains(&("Resume".into(), true)));
        assert!(menu.contains(&("Log Distraction".into(), false)));
    }
}
