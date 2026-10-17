use crate::config::Config;
use anyhow::{bail, Context, Result};
use futures_util::StreamExt;
use std::{
    collections::HashMap,
    future::{pending, Future},
    time::Duration,
};
use tokio::sync::{mpsc, oneshot};
use zbus::{
    zvariant::{OwnedObjectPath, OwnedValue, Value},
    Connection, Proxy,
};

#[derive(Debug)]
pub enum DesktopEvent {
    Presence {
        source: &'static str,
        active: bool,
        acknowledged: Option<oneshot::Sender<()>>,
    },
    Shortcut {
        action: String,
        activation_token: Option<String>,
    },
}
pub async fn notify(connection: &Connection, title: &str, body: &str, sound: bool) -> Result<()> {
    let proxy = Proxy::new(
        connection,
        "org.freedesktop.Notifications",
        "/org/freedesktop/Notifications",
        "org.freedesktop.Notifications",
    )
    .await?;
    let mut hints: HashMap<&str, Value<'_>> = HashMap::new();
    hints.insert("desktop-entry", Value::from("org.pomocli.Desktop"));
    if sound {
        hints.insert("sound-name", Value::from("complete"));
    } else {
        hints.insert("suppress-sound", Value::from(true));
    }
    let _: u32 = proxy
        .call(
            "Notify",
            &(
                "PomoCLI",
                0_u32,
                "appointment-soon",
                title,
                body,
                Vec::<String>::new(),
                hints,
                6000_i32,
            ),
        )
        .await?;
    Ok(())
}
/// Subscribe before querying the owner so a service appearing or restarting
/// cannot fall into a discovery/subscription gap. Each unique owner gets one
/// monitor attempt; an error (including denied shortcut permission) waits for a
/// new owner instead of retrying a dialog on a timer.
async fn supervise<F, M>(
    connection: &Connection,
    destination: &str,
    label: &str,
    mut start: F,
) -> Result<()>
where
    F: FnMut(String) -> M,
    M: Future<Output = Result<()>>,
{
    let bus = Proxy::new(
        connection,
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
    )
    .await?;
    let mut changes = bus.receive_signal("NameOwnerChanged").await?;
    async fn current_owner(bus: &Proxy<'_>, destination: &str) -> Option<String> {
        bus.call::<_, _, String>("GetNameOwner", &(destination,))
            .await
            .ok()
    }
    let mut owner = current_owner(&bus, destination).await;
    if owner.is_none() && destination == "org.freedesktop.portal.Desktop" {
        // Installed portals can be D-Bus activated rather than already running.
        // This is a single startup attempt; denied permission never starts a
        // retry timer, and the owner subscription above covers late appearance.
        match tokio::time::timeout(
            Duration::from_secs(3),
            bus.call::<_, _, u32>("StartServiceByName", &(destination, 0_u32)),
        )
        .await
        {
            Ok(Ok(_)) => {}
            Ok(Err(error)) => eprintln!("{label}: portal activation unavailable: {error}"),
            Err(_) => eprintln!("{label}: portal activation timed out"),
        }
        owner = current_owner(&bus, destination).await;
    }
    let mut monitor = owner.clone().map(|owner| Box::pin(start(owner)));
    loop {
        tokio::select! {
            result = async {
                match monitor.as_mut() {
                    Some(monitor) => monitor.await,
                    None => pending().await,
                }
            }, if monitor.is_some() => {
                if let Err(error) = result { eprintln!("{label}: {error:#}"); }
                monitor = None;
            }
            message = changes.next() => {
                let Some(message) = message else { bail!("D-Bus service-owner stream closed"); };
                let (name, _old, _new): (String, String, String) = message.body().deserialize()?;
                if name != destination { continue; }
                // Query the current owner rather than replaying stale queued
                // transitions from before the initial GetNameOwner reply.
                let fresh = current_owner(&bus, destination).await;
                if fresh != owner {
                    drop(monitor.take()); // releases old signal streams/inhibitors
                    owner = fresh;
                    monitor = owner.clone().map(|owner| Box::pin(start(owner)));
                }
            }
        }
    }
}
pub fn spawn_monitors(connection: &Connection, config: &Config, tx: mpsc::Sender<DesktopEvent>) {
    crate::idle::spawn(config.idle_timeout, tx.clone());
    let session = connection.clone();
    let lock_tx = tx.clone();
    tokio::spawn(async move {
        let monitor_connection = session.clone();
        let result = supervise(
            &session,
            "org.freedesktop.ScreenSaver",
            "Lock monitoring",
            move |owner| {
                let connection = monitor_connection.clone();
                let tx = lock_tx.clone();
                async move { locks(&connection, &owner, tx).await }
            },
        )
        .await;
        if let Err(error) = result {
            eprintln!("Lock service monitoring: {error:#}");
        }
    });
    let sleep_tx = tx.clone();
    tokio::spawn(async move {
        let result = async {
            let system = Connection::system().await?;
            let monitor_connection = system.clone();
            supervise(
                &system,
                "org.freedesktop.login1",
                "Suspend monitoring",
                move |owner| {
                    let connection = monitor_connection.clone();
                    let tx = sleep_tx.clone();
                    async move { sleep(&connection, &owner, tx).await }
                },
            )
            .await
        }
        .await;
        if let Err(error) = result {
            eprintln!("Suspend service monitoring: {error:#}");
        }
    });
    let session = connection.clone();
    let config = config.clone();
    tokio::spawn(async move {
        let monitor_connection = session.clone();
        let result = supervise(
            &session,
            "org.freedesktop.portal.Desktop",
            "Global shortcuts",
            move |owner| {
                let connection = monitor_connection.clone();
                let config = config.clone();
                let tx = tx.clone();
                async move { shortcuts(&connection, &owner, &config, tx).await }
            },
        )
        .await;
        if let Err(error) = result {
            eprintln!("Shortcut service monitoring: {error:#}");
        }
    });
}

async fn locks(connection: &Connection, owner: &str, tx: mpsc::Sender<DesktopEvent>) -> Result<()> {
    let proxy = Proxy::new(
        connection,
        owner,
        "/ScreenSaver",
        "org.freedesktop.ScreenSaver",
    )
    .await?;
    let mut signals = proxy.receive_signal("ActiveChanged").await?;
    let active: bool = proxy.call("GetActive", &()).await?;
    tx.send(DesktopEvent::Presence {
        source: "lock",
        active,
        acknowledged: None,
    })
    .await?;
    while let Some(message) = signals.next().await {
        let (active,): (bool,) = message.body().deserialize()?;
        tx.send(DesktopEvent::Presence {
            source: "lock",
            active,
            acknowledged: None,
        })
        .await?;
    }
    Ok(())
}
async fn inhibitor(proxy: &Proxy<'_>) -> Option<zbus::zvariant::OwnedFd> {
    match proxy
        .call(
            "Inhibit",
            &(
                "sleep",
                "PomoCLI",
                "Pause the focus session before sleeping",
                "delay",
            ),
        )
        .await
    {
        Ok(fd) => Some(fd),
        Err(error) => {
            eprintln!("Suspend delay inhibitor unavailable: {error}");
            None
        }
    }
}
async fn pause_before_sleep(
    tx: &mpsc::Sender<DesktopEvent>,
    delay: &mut Option<zbus::zvariant::OwnedFd>,
    deadline: Duration,
) {
    let (done, wait) = oneshot::channel();
    // Queueing and acknowledgement share one deadline. In particular, attaching
    // to logind during an ongoing suspend must release the initial inhibitor.
    let _ = tokio::time::timeout(deadline, async {
        tx.send(DesktopEvent::Presence {
            source: "suspend",
            active: true,
            acknowledged: Some(done),
        })
        .await?;
        let _ = wait.await;
        Ok::<(), anyhow::Error>(())
    })
    .await;
    drop(delay.take());
}
async fn sleep(connection: &Connection, owner: &str, tx: mpsc::Sender<DesktopEvent>) -> Result<()> {
    let proxy = Proxy::new(
        connection,
        owner,
        "/org/freedesktop/login1",
        "org.freedesktop.login1.Manager",
    )
    .await?;
    let mut signals = proxy.receive_signal("PrepareForSleep").await?;
    let mut delay = inhibitor(&proxy).await;
    // A logind replacement may never emit the old owner's pending resume.
    // Read its current state so an old suspend condition does not stay latched.
    let active = proxy
        .get_property::<bool>("PreparingForSleep")
        .await
        .unwrap_or(false);
    if active {
        pause_before_sleep(&tx, &mut delay, Duration::from_secs(3)).await;
    } else {
        tx.send(DesktopEvent::Presence {
            source: "suspend",
            active: false,
            acknowledged: None,
        })
        .await?;
    }
    while let Some(message) = signals.next().await {
        let (active,): (bool,) = message.body().deserialize()?;
        if active {
            pause_before_sleep(&tx, &mut delay, Duration::from_secs(3)).await;
        } else {
            delay = inhibitor(&proxy).await;
            tx.send(DesktopEvent::Presence {
                source: "suspend",
                active,
                acknowledged: None,
            })
            .await?;
        }
    }
    Ok(())
}
fn request_path(connection: &Connection, token: &str) -> String {
    let sender = connection
        .unique_name()
        .unwrap()
        .as_str()
        .trim_start_matches(':')
        .replace('.', "_");
    format!("/org/freedesktop/portal/desktop/request/{sender}/{token}")
}
async fn portal_response(
    stream: &mut zbus::proxy::SignalStream<'_>,
) -> Result<HashMap<String, OwnedValue>> {
    let message = tokio::time::timeout(Duration::from_secs(120), stream.next())
        .await?
        .context("Portal request closed")?;
    let (code, results): (u32, HashMap<String, OwnedValue>) = message.body().deserialize()?;
    if code != 0 {
        bail!("Shortcut permission was declined or cancelled (response {code})");
    }
    Ok(results)
}
/// Unsandboxed peers register their desktop ID before any portal API call.
/// Old portal versions without Registry retain their previous behavior; denial
/// or invalid registration ends this owner's attempt without showing a dialog.
async fn register_portal_identity(connection: &Connection, owner: &str) -> Result<()> {
    let registry = Proxy::new(
        connection,
        owner,
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.host.portal.Registry",
    )
    .await?;
    match registry
        .call::<_, _, ()>(
            "Register",
            &("org.pomocli.Desktop", HashMap::<&str, Value<'_>>::new()),
        )
        .await
    {
        Ok(()) => Ok(()),
        Err(zbus::Error::MethodError(name, _, _))
            if matches!(
                name.as_str(),
                "org.freedesktop.DBus.Error.UnknownInterface"
                    | "org.freedesktop.DBus.Error.UnknownMethod"
            ) =>
        {
            Ok(())
        }
        Err(error) => Err(error).context("Cannot register PomoCLI's portal identity"),
    }
}
async fn shortcuts(
    connection: &Connection,
    owner: &str,
    config: &Config,
    tx: mpsc::Sender<DesktopEvent>,
) -> Result<()> {
    register_portal_identity(connection, owner).await?;
    let proxy = Proxy::new(
        connection,
        owner,
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.GlobalShortcuts",
    )
    .await?;
    // Subscribe to the predictable request path before the method call, avoiding
    // the race where a portal returns its Response before the reply is handled.
    let token = format!("pomo_create_{}", std::process::id());
    let request = Proxy::new(
        connection,
        owner,
        request_path(connection, &token),
        "org.freedesktop.portal.Request",
    )
    .await?;
    let mut responses = request.receive_signal("Response").await?;
    let mut options = HashMap::new();
    options.insert("handle_token", Value::from(token.as_str()));
    let session_token = format!("pomo_session_{}", std::process::id());
    options.insert("session_handle_token", Value::from(session_token.as_str()));
    let _: OwnedObjectPath = proxy.call("CreateSession", &(options,)).await?;
    let mut result = portal_response(&mut responses).await?;
    let session_string = String::try_from(
        result
            .remove("session_handle")
            .context("Portal omitted session handle")?,
    )?;
    let session = OwnedObjectPath::try_from(session_string)?;
    let mut activated = proxy.receive_signal("Activated").await?;
    let token = format!("pomo_bind_{}", std::process::id());
    let request = Proxy::new(
        connection,
        owner,
        request_path(connection, &token),
        "org.freedesktop.portal.Request",
    )
    .await?;
    let mut responses = request.receive_signal("Response").await?;
    let mut bindings = Vec::new();
    for (id, description, shortcut) in [
        (
            "distract",
            "Log a distraction",
            config.linux.hotkey_distraction.as_str(),
        ),
        (
            "quick-start",
            "Start a focus session",
            config.linux.hotkey_quick_start.as_str(),
        ),
    ] {
        let mut properties = HashMap::new();
        properties.insert("description", Value::from(description));
        properties.insert("preferred_trigger", Value::from(shortcut));
        bindings.push((id, properties));
    }
    let mut options = HashMap::new();
    options.insert("handle_token", Value::from(token.as_str()));
    let _: OwnedObjectPath = proxy
        .call("BindShortcuts", &(&session, bindings, "", options))
        .await?;
    portal_response(&mut responses).await?;
    while let Some(message) = activated.next().await {
        let (handle, id, _time, mut options): (
            OwnedObjectPath,
            String,
            u64,
            HashMap<String, OwnedValue>,
        ) = message.body().deserialize()?;
        if handle == session {
            let activation_token = options
                .remove("activation_token")
                .and_then(|value| String::try_from(value).ok())
                .filter(|token| !token.is_empty());
            tx.send(DesktopEvent::Shortcut {
                action: id,
                activation_token,
            })
            .await?;
        }
    }
    Ok(())
}
pub async fn doctor(connection: &Connection) -> serde_json::Value {
    let notifications = Proxy::new(
        connection,
        "org.freedesktop.Notifications",
        "/org/freedesktop/Notifications",
        "org.freedesktop.Notifications",
    )
    .await;
    let notifications = if let Ok(proxy) = notifications {
        proxy
            .call::<_, _, Vec<String>>("GetCapabilities", &())
            .await
            .is_ok()
    } else {
        false
    };
    let portal = Proxy::new(
        connection,
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.GlobalShortcuts",
    )
    .await;
    let shortcuts = if let Ok(proxy) = portal {
        proxy.get_property::<u32>("version").await.is_ok()
    } else {
        false
    };
    let lock = Proxy::new(
        connection,
        "org.freedesktop.ScreenSaver",
        "/ScreenSaver",
        "org.freedesktop.ScreenSaver",
    )
    .await;
    let lock = if let Ok(proxy) = lock {
        proxy.call::<_, _, bool>("GetActive", &()).await.is_ok()
    } else {
        false
    };
    let idle = tokio::task::spawn_blocking(|| crate::idle::run(300, None)).await;
    let idle = matches!(idle, Ok(Ok(())));
    serde_json::json!({"notifications":notifications,"global_shortcuts_portal":shortcuts,"lock_events":lock,"wayland_idle":idle,"socket":crate::config::socket(),"dialog_helper":crate::config::dialog(),"desktop":std::env::var("XDG_CURRENT_DESKTOP").unwrap_or_default()})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn suspend_deadline_releases_inhibitor_with_full_queue_or_missing_ack() {
        for full in [true, false] {
            let (tx, mut rx) = mpsc::channel(1);
            if full {
                tx.send(DesktopEvent::Presence {
                    source: "lock",
                    active: false,
                    acknowledged: None,
                })
                .await
                .unwrap();
            }
            let (_peer, inhibitor) = std::os::unix::net::UnixStream::pair().unwrap();
            let inhibitor: std::os::fd::OwnedFd = inhibitor.into();
            let mut delay = Some(zbus::zvariant::OwnedFd::from(inhibitor));
            tokio::time::timeout(
                Duration::from_millis(500),
                pause_before_sleep(&tx, &mut delay, Duration::from_millis(30)),
            )
            .await
            .expect("sleep preparation must have a bounded deadline");
            assert!(
                delay.is_none(),
                "release the inhibitor even when desktop processing stalls"
            );
            let event = rx.try_recv().unwrap();
            match event {
                DesktopEvent::Presence {
                    source,
                    active,
                    acknowledged,
                } if full => {
                    assert_eq!(source, "lock");
                    assert!(!active);
                    assert!(acknowledged.is_none());
                }
                DesktopEvent::Presence {
                    source,
                    active,
                    acknowledged,
                } => {
                    assert_eq!(source, "suspend");
                    assert!(active);
                    assert!(acknowledged.is_some());
                }
                _ => panic!("unexpected desktop event"),
            }
        }
    }
}
