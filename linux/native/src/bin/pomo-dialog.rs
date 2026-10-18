//! Short-lived GTK UI. The tray never links or loads GTK.
use gtk4::{self as gtk, glib, prelude::*};
use pomocli_desktop::config;
use serde_json::{json, Value};
use std::{
    cell::Cell,
    io::Read,
    os::fd::AsRawFd,
    rc::Rc,
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex,
    },
    time::{Duration, Instant},
};

#[derive(Clone, Default)]
struct Workers {
    cancelled: Arc<AtomicBool>,
    threads: Arc<Mutex<Vec<std::thread::JoinHandle<()>>>>,
}
impl Workers {
    fn launch(&self, work: impl FnOnce(Arc<AtomicBool>) + Send + 'static) {
        let cancelled = self.cancelled.clone();
        self.threads
            .lock()
            .unwrap()
            .push(std::thread::spawn(move || work(cancelled)));
    }
    fn stop(&self) {
        self.cancelled.store(true, Ordering::Relaxed);
        for worker in self.threads.lock().unwrap().drain(..) {
            let _ = worker.join();
        }
    }
}

fn finish(app: &gtk::Application, result: Value) {
    println!("{result}");
    app.quit();
}
fn label(text: &str) -> gtk::Label {
    let widget = gtk::Label::new(Some(text));
    widget.set_xalign(0.0);
    widget
}
fn cli(arguments: &[String], cancelled: &AtomicBool) -> Result<Vec<u8>, String> {
    let mut command = std::process::Command::new(config::cli());
    command
        .args(arguments)
        .stdin(std::process::Stdio::null())
        .env("NO_COLOR", "1")
        .env("TERM", "dumb");
    // No shell is involved, including for task/project names beginning with '-'.
    let mut child = command
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|error| format!("Cannot run pomo: {error}"))?;
    let mut stdout = child.stdout.take().unwrap();
    let mut stderr = child.stderr.take().unwrap();
    for fd in [stdout.as_raw_fd(), stderr.as_raw_fd()] {
        let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
        if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
            pomocli_desktop::process::terminate_cli(child.id());
            let _ = child.wait();
            return Err("Cannot read PomoCLI output safely.".into());
        }
    }
    fn drain(pipe: &mut impl Read, output: &mut Vec<u8>) -> Result<(), String> {
        let mut buffer = [0; 4096];
        loop {
            match pipe.read(&mut buffer) {
                Ok(0) => return Ok(()),
                Ok(count) => {
                    output.extend_from_slice(&buffer[..count]);
                    if output.len() > 64 * 1024 {
                        return Err("PomoCLI output exceeded 64 KiB.".into());
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => return Ok(()),
                Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(error) => return Err(error.to_string()),
            }
        }
    }
    let deadline = Instant::now()
        + Duration::from_secs(
            if arguments.first().is_some_and(|arg| arg == "last-session") {
                10
            } else {
                30
            },
        );
    let mut out = Vec::new();
    let mut err = Vec::new();
    let status = loop {
        if cancelled.load(Ordering::Relaxed) || Instant::now() >= deadline {
            pomocli_desktop::process::terminate_cli(child.id());
            let _ = child.wait();
            return Err(if cancelled.load(Ordering::Relaxed) {
                "Cancelled.".into()
            } else {
                "PomoCLI did not respond in time. Try again.".into()
            });
        }
        if let Err(error) = drain(&mut stdout, &mut out).and_then(|_| drain(&mut stderr, &mut err))
        {
            pomocli_desktop::process::terminate_cli(child.id());
            let _ = child.wait();
            return Err(error);
        }
        match child.try_wait() {
            Ok(Some(status)) => {
                let _ = drain(&mut stdout, &mut out);
                let _ = drain(&mut stderr, &mut err);
                break status;
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(25)),
            Err(error) => {
                pomocli_desktop::process::terminate_cli(child.id());
                let _ = child.wait();
                return Err(error.to_string());
            }
        }
    };
    if status.success() {
        Ok(out)
    } else {
        let text = format!(
            "{}{}",
            String::from_utf8_lossy(&out),
            String::from_utf8_lossy(&err)
        );
        Err(if text.trim().is_empty() {
            "PomoCLI could not start the session.".into()
        } else {
            text.trim().chars().take(2000).collect()
        })
    }
}
fn quick_start(
    app: &gtk::Application,
    content: &gtk::Box,
    window: &gtk::ApplicationWindow,
    workers: &Workers,
) {
    let cfg = config::load();
    let task = gtk::Entry::builder()
        .placeholder_text("What will you work on?")
        .activates_default(true)
        .build();
    let project = gtk::Entry::builder()
        .placeholder_text("Optional project")
        .activates_default(true)
        .build();
    let elapsed = gtk::CheckButton::with_label("Stopwatch (count up)");
    let duration = gtk::SpinButton::with_range(1.0, 1440.0, 1.0);
    duration.set_value(cfg.session_duration.clamp(1, 1440) as f64);
    let error = label("");
    error.set_wrap(true);
    error.add_css_class("error");
    let start = gtk::Button::with_label("Start session");
    start.add_css_class("suggested-action");
    content.append(&label("Task"));
    content.append(&task);
    content.append(&label("Project"));
    content.append(&project);
    content.append(&elapsed);
    content.append(&label("Duration (minutes)"));
    content.append(&duration);
    content.append(&error);
    content.append(&start);
    window.set_default_widget(Some(&start));
    let duration_toggle = duration.clone();
    elapsed.connect_toggled(move |button| duration_toggle.set_sensitive(!button.is_active()));
    // Last-session lookup never blocks the GTK main loop; don't replace text the
    // owner has entered while the lookup was in progress.
    let (prefill_tx, prefill_rx) = mpsc::channel();
    workers.launch(move |cancelled| {
        let result = cli(&["last-session".into(), "--json".into()], &cancelled)
            .ok()
            .and_then(|data| serde_json::from_slice::<Value>(&data).ok());
        let _ = prefill_tx.send(result);
    });
    let prefill_task = task.clone();
    let prefill_project = project.clone();
    glib::timeout_add_local(Duration::from_millis(50), move || {
        match prefill_rx.try_recv() {
            Ok(Some(data)) => {
                if prefill_task.text().is_empty() {
                    if let Some(value) = data["task"].as_str() {
                        prefill_task.set_text(value);
                    }
                }
                if prefill_project.text().is_empty() {
                    if let Some(value) = data["project"].as_str() {
                        prefill_project.set_text(value);
                    }
                }
                glib::ControlFlow::Break
            }
            Ok(None) | Err(mpsc::TryRecvError::Disconnected) => glib::ControlFlow::Break,
            Err(mpsc::TryRecvError::Empty) => glib::ControlFlow::Continue,
        }
    });
    let app = app.clone();
    let window = window.clone();
    task.grab_focus();
    let workers = workers.clone();
    start.connect_clicked(move |button| {
        let task_name = task.text().trim().to_string();
        if task_name.is_empty() {
            error.set_text("Enter a task to start a session.");
            task.grab_focus();
            return;
        }
        let mut args = vec!["start".to_string()];
        let project_name = project.text().trim().to_string();
        if !project_name.is_empty() {
            args.extend(["--project".into(), project_name]);
        }
        if elapsed.is_active() {
            args.push("--elapsed".into());
        } else {
            args.extend(["--duration".into(), duration.value_as_int().to_string()]);
        }
        args.extend(["--".into(), task_name]);
        button.set_sensitive(false);
        button.set_label("Starting…");
        error.set_text("");
        // Keep the helper alive until the child exits so a submitted start cannot
        // leave an unobserved CLI child behind when its window is closed.
        window.set_deletable(false);
        let (result_tx, result_rx) = mpsc::channel();
        workers.launch(move |cancelled| {
            let _ = result_tx.send(cli(&args, &cancelled));
        });
        let button = button.clone();
        let app = app.clone();
        let error = error.clone();
        let window = window.clone();
        glib::timeout_add_local(Duration::from_millis(50), move || {
            match result_rx.try_recv() {
                Ok(Ok(_)) => {
                    finish(&app, json!({"action":"started"}));
                    glib::ControlFlow::Break
                }
                Ok(Err(message)) => {
                    error.set_text(&message);
                    button.set_sensitive(true);
                    button.set_label("Start session");
                    window.set_deletable(true);
                    glib::ControlFlow::Break
                }
                Err(mpsc::TryRecvError::Disconnected) => {
                    error.set_text("Session start failed.");
                    button.set_sensitive(true);
                    window.set_deletable(true);
                    glib::ControlFlow::Break
                }
                Err(mpsc::TryRecvError::Empty) => glib::ControlFlow::Continue,
            }
        });
    });
}

fn configure_renderer() {
    // These small forms do not need a GPU renderer. In software-rendered
    // sessions, probing graphics drivers can cost much more than the UI itself.
    // Respect an explicit renderer or feature override from the owner.
    if std::env::var_os("GSK_RENDERER").is_none() {
        std::env::set_var("GSK_RENDERER", "cairo");
    }
    if std::env::var("GSK_RENDERER").as_deref() == Ok("cairo")
        && std::env::var_os("GDK_DISABLE").is_none()
    {
        std::env::set_var("GDK_DISABLE", "gl,vulkan");
    }
}

fn main() {
    let mode = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "quick-start".into());
    if !matches!(mode.as_str(), "quick-start" | "distract" | "return") {
        eprintln!("Usage: pomo-dialog [quick-start|distract|return]");
        std::process::exit(2);
    }
    configure_renderer();
    let app = gtk::Application::builder()
        .application_id("org.pomocli.Dialog")
        .flags(gtk::gio::ApplicationFlags::NON_UNIQUE)
        .build();
    let workers = Workers::default();
    let ui_workers = workers.clone();
    app.connect_activate(move |app| {
        let window = gtk::ApplicationWindow::builder()
            .application(app)
            .title(match mode.as_str() {
                "distract" => "Log distraction",
                "return" => "Session paused",
                _ => "Start a focus session",
            })
            .default_width(380)
            .resizable(false)
            .build();
        let content = gtk::Box::new(gtk::Orientation::Vertical, 10);
        for property in ["margin-top", "margin-bottom", "margin-start", "margin-end"] {
            content.set_property(property, 20_i32);
        }
        window.set_child(Some(&content));
        let escaped = Rc::new(Cell::new(false));
        match mode.as_str() {
            "quick-start" => quick_start(app, &content, &window, &ui_workers),
            "distract" => {
                content.append(&label("Add a note (optional)"));
                let entry = gtk::Entry::builder()
                    .placeholder_text("What distracted you?")
                    .activates_default(true)
                    .build();
                content.append(&entry);
                let button = gtk::Button::with_label("Log distraction");
                button.add_css_class("suggested-action");
                content.append(&button);
                window.set_default_widget(Some(&button));
                entry.grab_focus();
                let app = app.clone();
                button.connect_clicked(move |_| {
                    finish(
                        &app,
                        json!({"action":"distract","description":entry.text().to_string()}),
                    )
                });
            }
            _ => {
                let task = std::env::args().nth(2).unwrap_or_default();
                let message = label(&format!(
                    "Your session{} was paused while you were away. Continue?",
                    if task.is_empty() {
                        String::new()
                    } else {
                        format!(" “{task}”")
                    }
                ));
                message.set_wrap(true);
                content.append(&message);
                let row = gtk::Box::new(gtk::Orientation::Horizontal, 10);
                for (text, action) in [("Stop session", "stop"), ("Resume", "resume")] {
                    let button = gtk::Button::with_label(text);
                    if action == "resume" {
                        button.add_css_class("suggested-action");
                        window.set_default_widget(Some(&button));
                    }
                    let app = app.clone();
                    button.connect_clicked(move |_| finish(&app, json!({"action":action})));
                    row.append(&button);
                }
                content.append(&row);
            }
        }
        let cancel = gtk::Button::with_label("Cancel");
        let app_cancel = app.clone();
        let cancel_window = window.clone();
        content.append(&cancel);
        cancel.connect_clicked(move |_| {
            if cancel_window.is_deletable() {
                finish(&app_cancel, json!({"action":"cancel"}));
            }
        });
        let keys = gtk::EventControllerKey::new();
        let app_escape = app.clone();
        let escape_window = window.clone();
        keys.connect_key_pressed(move |_, key, _, _| {
            if key == gtk::gdk::Key::Escape {
                if escape_window.is_deletable() && !escaped.replace(true) {
                    finish(&app_escape, json!({"action":"cancel"}));
                }
                glib::Propagation::Stop
            } else {
                glib::Propagation::Proceed
            }
        });
        window.add_controller(keys);
        window.present();
    });
    // GTK must not attempt to interpret the helper's positional arguments.
    app.run_with_args(&["pomo-dialog"]);
    workers.stop();
}

#[cfg(test)]
mod gui_tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn capture(window: &gtk::ApplicationWindow, path: &std::path::Path) {
        let paintable = gtk::WidgetPaintable::new(Some(window));
        let snapshot = gtk::Snapshot::new();
        paintable.snapshot(&snapshot, window.width() as f64, window.height() as f64);
        let node = snapshot
            .to_node()
            .expect("The dialog should render a scene");
        let texture = window
            .renderer()
            .expect("A renderer is available")
            .render_texture(&node, None);
        texture.save_to_png(path).expect("Save the dialog preview");
    }

    #[test]
    #[ignore = "requires an isolated graphical display, such as Xvfb"]
    fn quick_start_renders_prefill_validation_and_cli_error() {
        configure_renderer();
        let directory =
            std::env::temp_dir().join(format!("pomo-dialog-preview-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let cli_path = directory.join("pomo-test-cli");
        std::fs::write(&cli_path, "#!/bin/sh\nif [ \"$1\" = last-session ]; then\n  printf '%s\\n' '{\"task\":\"Review Linux desktop support\",\"project\":\"PomoCLI\"}'\n  exit 0\nfi\nprintf '%s\\n' 'Start rejected in isolated preview' >&2\nexit 1\n").unwrap();
        std::fs::set_permissions(&cli_path, std::fs::Permissions::from_mode(0o700)).unwrap();
        std::env::set_var("POMOCLI_BIN", &cli_path);
        std::env::set_var("POMOCLI_CONFIG_DIR", &directory);
        let output = std::env::var_os("POMOCLI_GUI_OUTPUT_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| directory.clone());
        std::fs::create_dir_all(&output).unwrap();
        let app = gtk::Application::builder()
            .application_id("org.pomocli.DialogPreview")
            .flags(gtk::gio::ApplicationFlags::NON_UNIQUE)
            .build();
        let workers = Workers::default();
        let ui_workers = workers.clone();
        app.connect_activate(move |app| {
            let window = gtk::ApplicationWindow::builder()
                .application(app)
                .title("PomoCLI Quick Start")
                .default_width(380)
                .resizable(false)
                .build();
            let content = gtk::Box::new(gtk::Orientation::Vertical, 10);
            for property in ["margin-top", "margin-bottom", "margin-start", "margin-end"] {
                content.set_property(property, 20_i32);
            }
            window.set_child(Some(&content));
            quick_start(app, &content, &window, &ui_workers);
            window.present();
            let app = app.clone();
            let output = output.clone();
            glib::timeout_add_local_once(Duration::from_millis(700), move || {
                let mut task = None;
                let mut start = None;
                let mut error_label = None;
                let mut child = content.first_child();
                while let Some(widget) = child {
                    if task.is_none() {
                        task = widget.clone().downcast::<gtk::Entry>().ok();
                    }
                    if let Ok(button) = widget.clone().downcast::<gtk::Button>() {
                        start = Some(button);
                    }
                    if let Ok(label) = widget.clone().downcast::<gtk::Label>() {
                        if label.has_css_class("error") {
                            error_label = Some(label);
                        }
                    }
                    child = widget.next_sibling();
                }
                let task = task.expect("Task entry");
                let start = start.expect("Start button");
                let error = error_label.expect("Inline error label");
                assert_eq!(task.text(), "Review Linux desktop support");
                capture(&window, &output.join("quick-start.png"));
                task.set_text("");
                start.emit_clicked();
                assert!(error.text().contains("Enter a task"));
                task.set_text("Review Linux desktop support");
                start.emit_clicked();
                assert!(!start.is_sensitive());
                glib::timeout_add_local_once(Duration::from_millis(700), move || {
                    assert!(start.is_sensitive());
                    assert!(window.is_deletable());
                    assert!(error.text().contains("Start rejected in isolated preview"));
                    capture(&window, &output.join("quick-start-error.png"));
                    app.quit();
                });
            });
        });
        app.run_with_args(&["pomo-dialog-preview"]);
        workers.stop();
        std::env::remove_var("POMOCLI_BIN");
        std::env::remove_var("POMOCLI_CONFIG_DIR");
        std::fs::remove_dir_all(directory).unwrap();
    }
}
