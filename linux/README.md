# Linux desktop companion

PomoCLI's Python daemon keeps the timer and saves session history. The small Rust
`pomo-tray` process connects directly to its Unix socket; it does not start a new
Python CLI process every second. A separate GTK4 helper, `pomo-dialog`, runs only
while a dialog is open. The optional Plasma 6 widget displays the ticking timer
in the panel using a bundled QtDBus bridge and the companion's cached status.

## Desktop support

| Desktop | Tray and dialogs | Always-visible timer text | Desktop integration |
| --- | --- | --- | --- |
| KDE Plasma 6, Wayland | Yes | Optional native panel widget | Idle through `ext_idle_notifier_v1`, screen lock, suspend, portal shortcuts, notifications |
| KDE Plasma 6, X11 | Yes | Optional native panel widget | Lock, suspend, notifications; idle and shortcut availability depend on desktop services |
| Other StatusNotifierItem/AppIndicator desktops | Where a tray host is available | Tray tooltip and menu | Capabilities detected at runtime |
| GNOME | Requires an AppIndicator extension for a visible tray icon | Dedicated GNOME timer extension deferred | Portal and compositor capabilities vary |

The system tray standard lets the desktop control icon layout. It does not
guarantee persistent timer text; install the KDE widget when that matters. The
portable companion does not depend on KDE or Qt. Run `pomo-tray --doctor` to see
the services and executables available in the current desktop session.

## Build and install

Install the Python CLI first, from the repository root:

```sh
python3 scripts/stamp_version.py
uv tool install . --reinstall
pomo init
```

When upgrading an existing installation, restart its running backend with
`pomo daemon restart` so it loads the new desktop protocol metadata.

The native build requires Rust/Cargo, a C linker, `pkg-config`, and GTK4
development files when dialogs are enabled. On Ubuntu/Debian:

```sh
sudo apt install build-essential pkg-config libgtk-4-dev
```

Use a current stable Rust toolchain. Builds use one job by default to limit
memory pressure. From this directory:

```sh
cd linux
make native
make install                      # ~/.local by default
pomo-tray                         # or open PomoCLI Desktop in the launcher
```

The installed launcher uses the companion's absolute path. Quick Start finds
`pomo` in `~/.local/bin`, then the desktop session's `PATH`; `POMOCLI_BIN` can
select an explicit executable. If you changed your login environment, log out
and back in. A
different prefix can be selected with `PREFIX=/path`; system installation can
use `sudo make install PREFIX=/usr/local` after building. Staging is supported
with `DESTDIR=/path` and does not change the active desktop.

For a tray-only build that omits the GTK4 dependency:

```sh
make native-minimal
make install DIALOGS=0
```

Controls that need a dialog report that the helper is unavailable in this build.
The running tray process never links GTK, even when dialogs are installed.
Dialogs default to GTK's Cairo renderer. On GTK 4.16 and later they also avoid
unnecessary GL/Vulkan driver probing, which substantially reduced open-window
memory in the headless measurements. Earlier GTK4 releases still work with
Cairo but ignore that optimization. Explicit `GSK_RENDERER` and `GDK_DISABLE`
environment settings take precedence; memory use depends on the GTK version
and graphics environment.

### Optional KDE panel widget

The widget needs the native companion installed above and running as well as
the Python daemon. If it says **Companion not running**, open **PomoCLI Desktop**
from your application launcher. Starting only `pomo daemon start` does not start
the companion.

The widget requires Plasma 6, a C++ compiler, CMake, and Qt6 development files.
It does not link KDE private libraries. Install the compiler even when building
only the widget:

```sh
sudo apt install build-essential cmake qt6-base-dev qt6-declarative-dev
make install-widget
```

If CMake reports `No CMAKE_CXX_COMPILER could be found`, install
`build-essential` and rerun `make install-widget`. You can also select an
existing compiler explicitly, for example `CXX=/path/to/clang++ make install-widget`.

Use the panel's **Add Widgets…** menu and add **PomoCLI Timer**. A newly installed
widget may require a new Plasma session before it appears. The compiled bridge
is installed alongside the widget, so no global QML import-path setting is
needed. Compile it on the target distribution against that system's Qt6.

The idle panel shows just the larger original icon. A diagonal red slash marks
a missing connection to the companion or Python daemon. Running and paused
sessions use a smaller icon beside a countdown or stopwatch with stable width
between ticks. Narrow vertical panels fall back to the icon when the timer
would not fit.

On the desktop, a tiny widget shows only the icon. More space reveals **Pomo**
and then **Ready to focus! 🍅👀** while idle. During a session, the timer grows
with the widget and task/project names appear when they fit. Icon and text sizes
are capped so a large widget stays readable. Click either placement for Quick
Start, distraction, Pause/Resume, Stop and Save, stopwatch completion, and Quit
Companion. Errors appear with the controls. Closing the companion leaves the
Python timer running.

To avoid showing both tray and panel controls, set `show_tray = false` under
`[linux]` in `~/.config/pomocli/config.toml`, or start `pomo-tray --no-tray`.
The widget connects to the companion over D-Bus and never polls the CLI itself.

The panel and launcher use `assets/pomocli-status-icon.svg`, traced from the
same PNG template as the macOS menu bar. The widget selects dark or light SVG
paths for contrast with its foreground palette, including with Qt's software
renderer. Both variants come from the same vector at build time. To regenerate
the vector after changing the PNG, run `python3 scripts/trace_status_icon.py`
with Pillow and Potrace installed; these are only needed for regeneration.

### Login autostart and removal

Installation does not enable login autostart or edit your panel. Opt in explicitly:

```sh
make autostart-enable
make autostart-disable
```

These commands manage only
`$XDG_CONFIG_HOME/autostart/org.pomocli.Desktop.desktop` (default `~/.config`).
Use the same `PREFIX` as installation. Remove the widget from your panel before
uninstalling its files:

```sh
pomo-tray --quit
make autostart-disable
make uninstall
```

The CLI, daemon, configuration, and saved history are not removed.

## Debian packages

Build on the target Ubuntu/Debian distribution. Packages contain the desktop
pieces only; install the Python CLI separately. The widget has its own package,
so the portable companion does not pull in KDE dependencies.

```sh
sudo apt install dpkg-dev
make deb                         # pomocli-desktop
make deb-widget                  # optional pomocli-plasma-widget
```

Artifacts are written to `build/packages/`. `dpkg-shlibdeps` calculates required
library versions from the built binaries. `POMOCLI_VERSION` overrides the
project version, and `POMOCLI_PACKAGE_DIR` changes the output directory. Package
building uses a temporary staging tree; it never installs files or starts the
companion. There are no login-autostart or service-start maintainer scripts.

## Configuration and interfaces

Existing session duration, distraction notes, idle timeout, and sound settings
apply to Linux. Linux-specific preferences live in `[linux]` so existing macOS
hotkeys remain unchanged. `pomo config` edits the current platform's shortcuts
and offers the Linux tray, launch, and desktop-integration preferences. Restart
the companion after changing its settings. The companion supports `--quick-start`, `--quit`,
`--doctor`, and `--no-tray`; see `pomo-tray --help` for current options. Desktop
shortcut requests require approval in the desktop's own portal UI, and denied
or conflicting requests do not prevent timer use.

For example, add the Linux table to `~/.config/pomocli/config.toml`:

```toml
session_duration = 25
idle_timeout = 300
sound_enabled = true
distraction_note_prompt = false

[linux]
show_tray = true
autolaunch = true
desktop_integration = true
hotkey_distraction = "CTRL+ALT+d"
hotkey_quick_start = "CTRL+ALT+p"
```

Keep shared settings before `[linux]`; TOML keys after that heading belong to
the Linux table. `autolaunch` controls companion launch from `pomo start`.
`desktop_integration` controls automatic desktop-event monitoring and portal
shortcuts. Set `show_tray = false` when using the KDE widget alone. Login
autostart remains a separate opt-in setting.

The optional widget uses this session-bus contract:

- Service `org.pomocli.Desktop`, object `/org/pomocli/Desktop`, interface
  `org.pomocli.Desktop1`.
- String property `Snapshot` and signal `SnapshotChanged(string)` contain JSON
  with `connected`, `state`, `timer_mode`, `time_left`, `elapsed_seconds`, and
  optional session/task/project fields and two-second distraction `feedback`.
- `Action(string)` accepts `quick-start`, `distract`, `pause`, `resume`, `stop`,
  or `complete`, and returns JSON `{ "status": "ok" }` or
  `{ "status": "error", "message": "…" }`. Dialog actions return when launched.
- `Quit()` exits the companion, leaving the timer daemon running.

The bridge uses asynchronous calls with bounded timeouts, subscribes to status
changes, and reconnects when the companion's D-Bus owner changes. It does not
write the SQLite database.

For isolated tests or custom installations, these environment overrides are
available:

| Variable | Purpose |
| --- | --- |
| `POMOCLI_CONFIG_DIR` | Configuration directory, including the default socket location |
| `POMOCLI_SOCKET` | Explicit companion socket path |
| `POMOCLI_DB_PATH` | Python backend database path |
| `POMOCLI_BIN` | Exact Python CLI executable used by Quick Start |
| `POMOCLI_DIALOG_BIN` | Exact dialog helper executable |

## Verification and memory goals

Development checks on Linux amd64 passed: 159 Python tests (one Swift compiler
check skipped), 11 Rust tests in both minimal and dialog-enabled builds, the
explicit GTK GUI regression test, and the QtDBus bridge/plugin integration
tests. Private-bus checks cover real countdown and stopwatch completion,
desktop-service restarts, suspend inhibitor release, fresh shortcut activation
tokens, stale action protection, and helper process cleanup. The GTK forms and
horizontal/vertical widget layouts were rendered and inspected.

Actual login-session idle, lock, suspend, and shortcut interactions still need
desktop acceptance testing. The read-only capability check confirmed Wayland
idle, lock, shortcut, and notification support on KDE. The macOS application was not built in this Linux environment;
the optional standalone Swift config-parser regression test needs `swiftc`.

Run these checks from the repository root:

```sh
make -C linux test-widget        # isolated bridge and responsive UI tests; Qt6 Test required
cargo test --manifest-path linux/native/Cargo.toml --locked -j 1 --features dialogs
desktop-file-validate linux/packaging/org.pomocli.Desktop.desktop
```

The widget UI tests render offscreen at desktop and panel sizes, including
disconnected, paused, long-timer, light/dark, and narrow vertical cases. Set
`POMO_WIDGET_PREVIEW_DIR` to an absolute directory when running `test-widget`
to save PNG previews. They exercise the presentation components and compile
the Plasma entry point; placement in a live Plasma shell still needs a manual
check after installation.

The integration smoke runner starts its own private D-Bus session with fake
desktop services, a real daemon and companion, temporary data, and a fake
dialog helper. It does not register shortcuts or open windows on your desktop.
It requires distro `python3-dbus`, `python3-gi`, `dbus-daemon`, and `gdbus`
(`libglib2.0-bin` on Ubuntu/Debian), plus a project Python environment:

```sh
uv sync
/usr/bin/python3 linux/tests/smoke.py \
  --python .venv/bin/python --companion linux/native/target/release/pomo-tray \
  --output linux/build/smoke.json
/usr/bin/python3 linux/tests/smoke.py --integrations \
  --python .venv/bin/python --companion linux/native/target/release/pomo-tray \
  --output linux/build/smoke-integrations.json
/usr/bin/python3 linux/tests/smoke.py --activation \
  --python .venv/bin/python --companion linux/native/target/release/pomo-tray \
  --output linux/build/smoke-activation.json
```

Add `--natural-completion` to wait for a real one-minute countdown and check
its saved duration and single completion notification.

The second invocation simulates portal shortcuts, screen lock, suspend,
and desktop-service restarts, including an initially active suspend and delay
inhibitor release. The third tests an installed but initially dormant portal's
D-Bus activation. Wayland idle events require a real compositor. The runner
manages `fake_desktop.py`; do not run
that test service on your login session bus. Reports and process logs are saved
beside the selected output path.

An optional GTK regression test renders the actual Quick Start dialog using a
fake CLI and checks prefilling, validation, and submission errors. It is ignored
by default because it requires a graphical display. For an isolated headless
run, install `xvfb` and `xauth`, then run from the repository root:

```sh
ui_dir=$(mktemp -d)
mkdir -p "$ui_dir/config" "$ui_dir/data" "$ui_dir/cache" "$ui_dir/runtime" "$ui_dir/render"
chmod 700 "$ui_dir/runtime"
env XDG_CONFIG_HOME="$ui_dir/config" XDG_DATA_HOME="$ui_dir/data" \
  XDG_CACHE_HOME="$ui_dir/cache" XDG_RUNTIME_DIR="$ui_dir/runtime" \
  GDK_BACKEND=x11 GSK_RENDERER=cairo GTK_A11Y=none \
  POMOCLI_GUI_OUTPUT_DIR="$ui_dir/render" \
  dbus-run-session -- xvfb-run -a -s "-screen 0 1280x900x24 -nolisten tcp" \
  cargo test --manifest-path linux/native/Cargo.toml --locked -j 1 \
    --features dialogs --bin pomo-dialog gui_tests:: \
    -- --ignored --test-threads=1
printf 'Dialog captures: %s\n' "$ui_dir/render"
```

Manual checks should use an isolated `POMOCLI_DB_PATH` and companion/socket
configuration, never the personal database. Check countdown/stopwatch ticks,
pause/resume, distraction feedback, conditional completion, action errors,
daemon/companion reconnection, dialog cancellation, desktop service restarts,
and horizontal/vertical panels. Idle, lock, suspend, shortcuts, notifications,
and visual rendering need a real desktop session; headless bridge tests do not
establish those behaviors.

The existing Python-only short benchmark measured approximately 23 MiB RSS,
0.20–0.25% of one CPU core with one status request per second, and 2–3 ms status
responses. These values exclude the desktop companion, panel widget, and
dialogs. They are a short baseline, not a long-running memory-leak test.

Measurements on an 8 GB Linux amd64 machine, using Python 3.10.21 on
2026-10-16, stayed within the resident-process budgets:

| Component | Budget | Measured result |
| --- | --- | --- |
| Resident companion, dialogs closed | At most 10 MiB PSS | Final binary: 2.7 MiB mean PSS, 2.8 MiB maximum; 5.1 MiB mean RSS |
| Python daemon plus companion | At most 35 MiB PSS | Final binary: 20.2 MiB mean PSS; one-hour polling run: 22.4 MiB including swapped pages |
| Incremental widget memory in Plasma | At most 5 MiB additional PSS | Unmeasured; isolated Plasma shell failed before loading a widget |
| Daemon plus companion ticking | Below 0.5% of one logical CPU core on average | 0.43% final binary; 0.35% one-hour polling run |

The one-hour run exercised the polling path on a candidate build, with desktop
integrations disabled. Final changes to cold portal activation, initial suspend
handling, and shortcut activation-token handoff were checked by the private-bus
tests and a separate 120-second run of the final binary with fake desktop
integrations enabled. Neither run showed sustained memory, thread, or descriptor
growth. The final companion settled at one thread and 13 descriptors; a real
Wayland idle connection adds a dedicated small-stack thread.

Host memory pressure paged out cold memory during the hour-long run. Its
22.4 MiB figure conservatively adds `Swap` to PSS rather than treating the falling
resident size as a smaller allocation. The final two-minute run had no swap.
PSS apportions shared pages, so values also depend on other running processes.
These are observations in the stated environment, not cross-desktop guarantees.

The separate release GTK4 helper measured 24.9 MiB PSS / 40.4 MiB RSS with
Quick Start open on GTK 4.22.4 and isolated Xvfb. That measurement used a fake,
completed CLI prefill; it excludes the transient Python CLI process during a
real lookup or submission. The helper exits when its dialog closes. Release
tray and helper binaries together occupy approximately 3.3 MiB on disk,
excluding the existing Python installation and shared system libraries.

The resource runner seeds temporary demo data and tracks the daemon and tray
separately through `/proc`, including PSS/RSS, CPU, threads, descriptors, and swap:

```sh
python3 scripts/profile_linux.py --python .venv/bin/python \
  --companion linux/native/target/release/pomo-tray --seconds 3600 \
  --output linux/build/resource-soak.json
```

Use `--desktop-integrations` for a separate run with fake portal, lock, and
logind services. Wayland idle, dialogs, and Plasma are outside that runner's
measurements. Compare RSS and private memory alongside PSS. The runner also
reports PSS plus proportional swapped pages (`SwapPss`, falling back to `Swap`)
so paging does not hide the allocated footprint.
