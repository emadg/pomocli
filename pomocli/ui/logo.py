import sys

from .logo_ansi_generated import LOGO_ANSI_LINES


def print_logo() -> None:
    """Print the Pomodoro CLI logo (pre-rendered luminance-ramp ASCII + bright-white ANSI; see `scripts/generate_cli_logo.py`)."""
    for line in LOGO_ANSI_LINES:
        sys.stdout.write(line + "\n")
    sys.stdout.flush()
