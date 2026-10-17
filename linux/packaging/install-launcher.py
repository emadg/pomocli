#!/usr/bin/env python3
"""Render a launcher with its runtime prefix, excluding any staging directory."""

import argparse
from pathlib import Path

from autostart import desktop_entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.expanduser()
    if not executable.is_absolute():
        parser.error("the install prefix must be an absolute path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(desktop_entry(executable))
    args.output.chmod(0o644)


if __name__ == "__main__":
    main()
