#!/usr/bin/env python3
"""Explicit opt-in autostart; installation never modifies login settings."""

import argparse
import os
from pathlib import Path


def desktop_argument(value: str) -> str:
    """Quote one Exec argument according to the desktop-entry specification."""
    # Percent introduces a field code even inside quotes. Backslashes are
    # unescaped once by the entry parser and again by the Exec parser.
    escaped = value.replace("\\", "\\\\\\\\").replace("%", "%%")
    for character in ('"', "`", "$"):
        escaped = escaped.replace(character, "\\\\" + character)
    return '"' + escaped + '"'


def desktop_entry(executable: Path) -> str:
    """Render the launcher for an explicit install prefix, including staging."""
    template = Path(__file__).with_name("org.pomocli.Desktop.desktop").read_text()
    lines = []
    for line in template.splitlines():
        if line.startswith("TryExec="):
            continue
        lines.append(f"Exec={desktop_argument(str(executable))}" if line.startswith("Exec=") else line)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enable", "disable"))
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    target = config / "autostart" / "org.pomocli.Desktop.desktop"
    if args.action == "disable":
        target.unlink(missing_ok=True)
        print(f"Login autostart disabled: {target}")
        return
    if args.executable is None:
        parser.error("enable requires --executable /path/to/pomo-tray")
    executable = args.executable.expanduser().resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        parser.error(f"executable not installed: {executable}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(desktop_entry(executable))
    print(f"Login autostart enabled: {target}")


if __name__ == "__main__":
    main()
