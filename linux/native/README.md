# Native companion implementation

The resident `pomo-tray` binary uses the daemon socket and D-Bus. GTK is used
only by the optional, short-lived `pomo-dialog` binary. Build with a current
stable Rust toolchain; see [Linux installation](../README.md) for dependencies
and packaging.

For the component diagram and an explanation of which processes stay running,
see [Components and processes](../README.md#components-and-processes).

Desktop integrations follow service owners rather than retrying on a timer.
Lock, logind, and shortcut monitors subscribe to `NameOwnerChanged` before
discovery, cancel the previous owner's monitor, and attach once to each new
owner. Denied shortcut permission does not cause recurring approval dialogs.

Unsandboxed portal connections must register `org.pomocli.Desktop` through
`org.freedesktop.host.portal.Registry.Register` **before** creating a shortcut
session. The ID matches the installed `org.pomocli.Desktop.desktop` launcher.
Registration repeats for a replacement portal owner. Portals without Registry
retain compatibility; other registration failures stop that owner's shortcut
attempt. Read-only `--doctor` never registers an identity or shortcuts.
See the [official Registry documentation](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.host.portal.Registry.html).

Shortcut activation tokens are passed only to the helper opened by that event.
Other helper launches remove inherited tokens, since Wayland activation tokens
are single use. See the [GlobalShortcuts Activated signal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html#org-freedesktop-portal-globalshortcuts-activated).
