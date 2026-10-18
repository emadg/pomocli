"""Bounded JSON socket reads shared by the daemon and Python client.

The legacy protocol sends one JSON object per connection without a delimiter.
Decode only once a complete object arrives: a Unix stream may split even short
messages, and enriched status responses can exceed the old 4096-byte buffer.
"""

import json
import socket

MAX_MESSAGE_BYTES = 64 * 1024


def receive_json(conn: socket.socket):
    data = bytearray()
    while len(data) < MAX_MESSAGE_BYTES:
        chunk = conn.recv(min(4096, MAX_MESSAGE_BYTES - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        try:
            return json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    if len(data) >= MAX_MESSAGE_BYTES:
        raise ValueError("JSON message exceeds 64 KiB")
    raise ValueError("Incomplete or invalid JSON message")
