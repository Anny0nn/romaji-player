"""Pass only the two public Spotify build settings from .env to an argv command."""

import os
import re
import sys
from pathlib import Path


def main():
    environment = os.environ.copy()
    configuration = Path(".env")
    if configuration.is_file():
        for line in configuration.read_text().splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() in {
                "SPOTIFY_CLIENT_ID",
                "SPOTIFY_REDIRECT_URI",
            }:
                environment.setdefault(name.strip(), value.strip().strip("\"'"))
    client = environment.get("SPOTIFY_CLIENT_ID", "")
    callback = environment.get("SPOTIFY_REDIRECT_URI", "")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", client):
        raise SystemExit("Set SPOTIFY_CLIENT_ID to your public Spotify app identifier.")
    if callback != "http://127.0.0.1:8989/login":
        raise SystemExit(
            "Set SPOTIFY_REDIRECT_URI to http://127.0.0.1:8989/login and register it with Spotify."
        )
    if len(sys.argv) < 2:
        raise SystemExit("Pass a build or run command as arguments.")
    os.execvpe(sys.argv[1], sys.argv[1:], environment)


if __name__ == "__main__":
    main()
