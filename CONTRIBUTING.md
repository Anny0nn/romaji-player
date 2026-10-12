# Contributing to RomajiPlayer

RomajiPlayer is a Japanese sing-along fork of
[Spotifast](https://github.com/crmne/spotifast), currently targeting Apple Silicon Macs.
Keep changes focused on the native app and preserve the upstream playback foundation.

Use a feature or fix branch and open a pull request targeting this fork's `main`.
Describe the resulting behavior, relevant tests and any user-visible interface changes.
Discuss substantial new features before implementing them. Do not push directly to
`main` or rewrite published history.

## Setup and checks

Follow the [README](README.md) to install the pinned helper environments and bootstrap
alignment source. Keep your Spotify configuration in the ignored `.env` file.

```sh
git config core.hooksPath .githooks
bash scripts/check.sh --quick
bash scripts/check.sh
```

The gate checks maintained study documentation, shell syntax, Rust formatting/Clippy,
Python formatting/lints, export paths and history, C++ alignment protocol, Python helper
and evidence boundaries, and Rust tests. Upstream's website and historic release notes
retain their own documentation formatting.

Tests must remain offline. Use synthetic fixtures for readings, UTF-8 source spans,
lyric snapshots, repeated lines and timing selection. Never read a real Keychain grant
or call Spotify, lyric providers or model downloads from ordinary tests.

Packaging changes also need `python3 scripts/check-helper-package.py` and
`python3 scripts/check-app-package.py`. Report the actual platforms and models tested;
timing coverage is distinct from audible correctness.

## Local data and licenses

Do not commit account settings, credentials, recordings, downloaded lyrics, caches,
model weights, generated app bundles or personal development configuration. The export
guard checks tracked files and each outgoing commit; removing a file later does not
remove it from history.

Keep dependency attribution and model notices intact. Contributions to the application
source use its MIT license; model weights retain their separate licenses. There is no
hosted service or telemetry in this project.
