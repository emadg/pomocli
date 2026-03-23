from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("pomocli")
except PackageNotFoundError:
    __version__ = "0.1.0"

try:
    from ._build_info import __build__
except ImportError:
    __build__ = f"{__version__}-dev"
