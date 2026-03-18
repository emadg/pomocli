"""Allow running the daemon with: python -m pomocli.daemon"""
from .server import DaemonServer

if __name__ == "__main__":
    server = DaemonServer()
    server.start()
