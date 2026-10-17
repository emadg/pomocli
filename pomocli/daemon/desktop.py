"""Launch the optional Linux frontend without adding desktop dependencies."""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import load_config


def launch_linux_companion() -> None:
    if not load_config().get("linux", {}).get("autolaunch", True):
        return
    binary = shutil.which("pomo-tray")
    if binary is None:
        return
    env = dict(os.environ)
    entrypoint = Path(sys.argv[0]).resolve()
    if "POMOCLI_BIN" not in env and entrypoint.name == "pomo" and entrypoint.is_file():
        env["POMOCLI_BIN"] = str(entrypoint)
    try:
        subprocess.Popen(
            [binary],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            # Pass the exact CLI entrypoint even when a graphical login PATH
            # does not contain the uv tool environment.
            env=env,
        )
    except OSError as exc:
        logging.warning("Could not launch Linux desktop companion: %s", exc)
