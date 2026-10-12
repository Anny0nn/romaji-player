# RomajiPlayer

A free, open-source Japanese sing-along player for Apple Silicon Macs, built on
[Spotifast](https://github.com/crmne/spotifast). Play Spotify music inside the app and
follow the lyrics as romaji, hiragana, or hiragana above romaji.

- Large lyrics with the current line and timed word highlighted.
- Separate **TIFA** and **Experimental** buttons for local automatic word alignment.
- Saved timings and lyric versions per song, preserved across restarts.
- Reading corrections anchored to the original Japanese text.
- Compact **Options** controls for import, delay and saved versions.

Alignment is experimental: high timing coverage does not guarantee correct singing
alignment. Missing intervals stay unmarked. There is no manual word-timing requirement.

## Build on macOS

The current study build targets Apple Silicon and macOS 15 or later. Use Rust 1.98.1,
Python 3.14, Node.js/npm, CMake and Xcode Command Line Tools. A machine with 16 GB of
unified memory can run the optional experimental models.

Copy `.env.example` to `.env`. Set `SPOTIFY_CLIENT_ID` to your own Spotify developer
application and register `http://127.0.0.1:8989/login` as its redirect URI. Spotify Premium
is required for in-app playback. Development Mode users must be allowlisted in your
application; configuration belongs to each user, rather than one shared registration.

```sh
cp .env.example .env
# Edit .env before building.
python3.14 -m venv .venv
.venv/bin/python -m pip install -r romanizer/requirements.lock
python3.14 -m venv .venv-tifa
.venv-tifa/bin/python -m pip install -r tifa/requirements.lock
python3.14 -m venv .venv-experimental
.venv-experimental/bin/python -m pip install --no-deps -r refinement/requirements.lock
python3 scripts/fetch-aligner-source.py
bash scripts/package-romanizer.sh
bash scripts/package-tifa.sh
bash scripts/package-experimental.sh
bash scripts/dev.sh
```

For a standalone app and ZIP, run `bash scripts/package.sh`. Output is under `dist/`;
recipients need no Python installation. Downloaded model weights are separate from the
bundle. Run `python3 scripts/check-app-package.py` to verify the packaged distribution.

## Models and local data

TIFA downloads about 151 MB on first use. Experimental alignment additionally downloads
vocal-separation and phonetic-alignment assets. Downloads are pinned and hash-verified.
Processing runs locally; previous timing versions remain selectable.

Model licenses differ from the MIT application source. TIFA and MMS weights have
noncommercial terms. See [TIFA provenance](tifa/UPSTREAM.md) and the
[experimental model notices](refinement/MODEL-NOTICES.txt); review the original Demucs
weight terms before using that optional model. Weights, recordings, downloaded lyrics,
credentials and personal development configuration are excluded from git.

This is an unofficial Spotify integration. Spotify's
[developer restrictions](https://developer.spotify.com/compliance-tips) include lyric
synchronization; source availability does not establish Spotify approval.

## Development

Use feature branches and pull requests targeting this fork. Enable the local hooks with
`git config core.hooksPath .githooks`; run `bash scripts/check.sh` before pushing.
The offline suite does not sign in, download models or contact music/lyrics services.
See [the implementation plan](docs/plans/japanese-study.md) and
[contributing instructions](CONTRIBUTING.md).

## Credits and license

Spotifast is by Carmine Paolino and contributors. RomajiPlayer retains its native
Rust/egui interface, librespot playback and MIT attribution. Application code is
[MIT licensed](LICENSE); bundled dependencies and separately downloaded models retain
their own notices and terms. Upstream's website sources remain in `docs/` for provenance;
they describe Spotifast, while the study build is documented here.
