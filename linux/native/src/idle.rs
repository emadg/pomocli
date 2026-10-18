//! Wayland idle notifications without reading keys, pointers, or global input.
use crate::desktop::DesktopEvent;
use anyhow::{bail, Context, Result};
use tokio::sync::mpsc;
use wayland_client::{
    protocol::{wl_registry, wl_seat},
    Connection, Dispatch, QueueHandle,
};
use wayland_protocols::ext::idle_notify::v1::client::{
    ext_idle_notification_v1, ext_idle_notifier_v1,
};

struct State {
    notifier: Option<ext_idle_notifier_v1::ExtIdleNotifierV1>,
    seat: Option<wl_seat::WlSeat>,
    events: Option<mpsc::Sender<DesktopEvent>>,
}
impl Dispatch<wl_registry::WlRegistry, ()> for State {
    fn event(
        state: &mut Self,
        registry: &wl_registry::WlRegistry,
        event: wl_registry::Event,
        _: &(),
        _: &Connection,
        qh: &QueueHandle<Self>,
    ) {
        if let wl_registry::Event::Global {
            name,
            interface,
            version,
        } = event
        {
            if interface == "ext_idle_notifier_v1" && state.notifier.is_none() {
                state.notifier = Some(registry.bind(name, version.min(1), qh, ()));
            } else if interface == "wl_seat" && state.seat.is_none() {
                state.seat = Some(registry.bind(name, version.min(1), qh, ()));
            }
        }
    }
}
impl Dispatch<wl_seat::WlSeat, ()> for State {
    fn event(
        _: &mut Self,
        _: &wl_seat::WlSeat,
        _: wl_seat::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
    }
}
impl Dispatch<ext_idle_notifier_v1::ExtIdleNotifierV1, ()> for State {
    fn event(
        _: &mut Self,
        _: &ext_idle_notifier_v1::ExtIdleNotifierV1,
        _: ext_idle_notifier_v1::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
    }
}
impl Dispatch<ext_idle_notification_v1::ExtIdleNotificationV1, ()> for State {
    fn event(
        state: &mut Self,
        _: &ext_idle_notification_v1::ExtIdleNotificationV1,
        event: ext_idle_notification_v1::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        let active = match event {
            ext_idle_notification_v1::Event::Idled => true,
            ext_idle_notification_v1::Event::Resumed => false,
            _ => return,
        };
        if let Some(tx) = &state.events {
            let _ = tx.blocking_send(DesktopEvent::Presence {
                source: "idle",
                active,
                acknowledged: None,
            });
        }
    }
}
pub fn run(timeout_seconds: u32, events: Option<mpsc::Sender<DesktopEvent>>) -> Result<()> {
    let connection = Connection::connect_to_env().context("Wayland is unavailable")?;
    let mut queue = connection.new_event_queue();
    let qh = queue.handle();
    let _registry = connection.display().get_registry(&qh, ());
    let mut state = State {
        notifier: None,
        seat: None,
        events,
    };
    queue.roundtrip(&mut state)?;
    let notifier = state
        .notifier
        .as_ref()
        .context("ext_idle_notifier_v1 is unavailable")?;
    let seat = state.seat.as_ref().context("Wayland seat is unavailable")?;
    if state.events.is_none() {
        return Ok(());
    }
    if timeout_seconds == 0 {
        bail!("Idle monitoring disabled by idle_timeout = 0");
    }
    let _notification =
        notifier.get_idle_notification(timeout_seconds.saturating_mul(1000), seat, &qh, ());
    loop {
        queue.blocking_dispatch(&mut state)?;
    }
}
pub fn spawn(timeout: u32, events: mpsc::Sender<DesktopEvent>) {
    if timeout == 0 {
        return;
    }
    let _ = std::thread::Builder::new()
        .name("pomo-wayland-idle".into())
        .stack_size(256 * 1024)
        .spawn(move || {
            if let Err(error) = run(timeout, Some(events)) {
                eprintln!("Idle monitoring: {error:#}");
            }
        });
}
