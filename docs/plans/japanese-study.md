# Japanese sing-along study player

Status: Implemented (2026-10-12)

## Goal

Extend Spotifast with a Japanese sing-along view for Apple Silicon Macs. The app plays
Spotify music internally and displays large, synchronized romaji, hiragana, or both.
Share the source freely so others can build and run the same experience locally.

## Approach

Keep Spotifast's native Rust/egui interface and librespot playback. Build on the current
upstream source and retain its root layout and MIT attribution. Develop on feature
branches, with pull requests targeting this fork's `main`.

Cutlet, fugashi and unidic-lite run in a bundled Python helper that returns readings and
UTF-8 spans anchored to the original Japanese lyrics. Rust owns playback position,
lyric snapshots, corrections and durable per-song timings. Identical repeated lyric
lines share reading corrections; timing remains specific to each occurrence.

Offer two automatic timing actions: TIFA and an experimental pipeline that isolates
vocals and checks candidate repairs with independent phonetic alignment. Preserve older
results. Missing timing remains missing; do not distribute words evenly across a line
or claim coverage proves audible accuracy. There is no manual word-timing workflow.

Bundle helper runtimes and download pinned, hash-verified model assets separately.
Each user configures their own Spotify application and account; no account credentials,
recordings, downloaded lyrics or model weights belong in the source repository.

## Steps

1. Port the study modules, original-text identity model and reading/timing persistence
   onto upstream. Keep upstream behavior and tests, including recent window changes.
2. Integrate the compact study controls, separate timing buttons, song-link playback and
   three lyric display modes. Preserve app identity and saved data during updates.
3. Adapt helper packaging, development commands and offline checks to the root layout.
   Keep local `.env`, generated distributions and personal development tools ignored.
4. Document personal Spotify setup, model licenses, build commands and upstream credit.
   Verify exported source and outgoing commits before opening a public draft PR.

## Tests and checks

Run `bash scripts/check.sh`: formatting, lints, export guard, C++ protocol, Python helper
and boundary tests, and the Rust suite. Tests use synthetic/recorded fixtures and never
connect to Spotify, real lyric providers, Keychain or model downloads.

Check a standalone Apple Silicon package with `scripts/check-app-package.py`. Reopening
must retain lyric mode and saved timings. Preserve stable bundle/data identifiers.
Live listening is needed to evaluate singing alignment; report it separately from
retained timing coverage.

## Validation

The migrated source passes the full local gate, including the upstream Rust suite,
study persistence and source-span tests, and helper protocol/evidence tests. A fresh
configured Apple Silicon app and ZIP have been built from this port and pass standalone
helper, restricted-environment and relocation checks. The
[sung-reading plan](sung-reading-repair.md) adds automatic reading repair to Experimental;
its [evaluation report](../study-reading-evaluation.md) records model acceptance and
persistence on private song copies. Public binary release and fresh live login/playback
and listening acceptance for the ported binary remain separate work.

## Out of scope

Hosted services, sales, YouTube playback, mobile ports, publishing recordings or lyrics,
commercial model licensing, and automatic merging or public binary release.
