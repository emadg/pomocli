from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("pomocli")
except PackageNotFoundError:
    __version__ = "0.1.0"

# Build timestamp — fixed at install time for installed packages,
# reflects current time when running from source (dev mode).
__build__ = f"{__version__}.dev{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
