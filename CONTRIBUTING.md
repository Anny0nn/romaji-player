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

After changing Python inference or conversion code, rebuild the corresponding packaged
helper before testing the app. `scripts/dev.sh` reuses existing helper executables, and
`scripts/package.sh` rebuilds all helpers and the configured release app. A passing
source test alone does not verify the standalone Python-to-Python helper boundary.

## Testing models on recordings

Ordinary tests use synthetic/recorded protocol fixtures and run without model downloads.
Ignored Rust acceptance tests require explicit local inputs and are excluded from the
offline gate. Keep song audio, full lyrics and generated evidence
outside this checkout, in a directory accessible only to your account.

For the complete song pipeline, supply a saved study `document.json`, mono float32
little-endian PCM at 16 kHz, and interleaved stereo float32 PCM at 44.1 kHz. Experimental
also needs the already downloaded `models/refinement-v1` assets. For example, after
setting these environment variables to your own private files:

```sh
# Required for both methods:
# ROMAJI_TEST_DOCUMENT, ROMAJI_TEST_PCM, ROMAJI_TEST_MODEL, ROMAJI_TEST_RESULT_DIR
# Experimental additionally requires ROMAJI_TEST_STEREO and ROMAJI_TEST_ASSETS.
export ROMAJI_HELPER_PATH="$PWD/dist/RomajiRomanizer/RomajiRomanizer"
export ROMAJI_TIFA_PATH="$PWD/dist/RomajiTIFA/RomajiTIFA"
export ROMAJI_EXPERIMENTAL_PATH="$PWD/dist/RomajiExperimental/RomajiExperimental"
export ROMAJI_TEST_METHOD=experimental # use tifa for the original action
cargo test --locked --no-default-features --lib \
  study::alignment::tests::recorded_song_pipeline_preserves_source_versions_and_reports_coverage \
  -- --exact --ignored --nocapture
```

`ROMAJI_TEST_MODEL` points to the downloaded TIFA ZIP, not its extracted directory.
Use a fresh result directory per song and method; do not point it at the app's real
state. The test validates protected edits, source spans, earlier versions, saving and
reopening, and prints a structured `Acceptance metrics:` JSON line without lyric text.
It does not authenticate, capture audio or download models. Compare both methods on the
same document and mono PCM input hash; Experimental also uses that recording's stereo
PCM. Its generated audio fingerprint covers both inputs, whereas TIFA's covers mono.
Report each denominator: corrections can change word
grouping, so counts alone may not describe identical display words.

After that run, verify the saved document can still drive word highlighting and restore
an earlier version. This test uses the same `ROMAJI_HELPER_PATH`, `ROMAJI_TEST_DOCUMENT`
and `ROMAJI_TEST_RESULT_DIR`, without loading inference models:

```sh
cargo test --locked --no-default-features --lib \
  study::alignment::tests::reopening_recorded_results_restores_word_highlights_and_earlier_versions \
  -- --exact --ignored --nocapture
```

For cached acoustic/transcription evidence, `scripts/experiment-sung-readings.py` runs
the same proposal policy as the app without changing saved song data. See its manifest
description and the [evaluation report](docs/study-reading-evaluation.md). Capture new
Spotify test inputs only as an explicit live action. The local capture wrapper requires
an immutable helper already authorized by its owner; rebuilding an ad-hoc signed helper
can prompt for Keychain access again.

Treat retained timing coverage, correctness of readings and audible timing accuracy as
separate measurements. Include silence/wrong-verse controls, correct baseline readings,
repeated lines, saved edits and stale results. Freeze policy thresholds before evaluating
disjoint data; label reused calibration songs and injected-error cases honestly. Run
large models sequentially on the M2 Pro/16 GB target and record elapsed time and the
memory counter used. An operating-system RSS counter is not total unified GPU memory.

## Local data and licenses

Do not commit account settings, credentials, recordings, downloaded lyrics, caches,
model weights, generated app bundles or personal development configuration. The export
guard checks tracked files and each outgoing commit; removing a file later does not
remove it from history.

Keep dependency attribution and model notices intact. Contributions to the application
source use its MIT license; model weights retain their separate licenses. There is no
hosted service or telemetry in this project.
