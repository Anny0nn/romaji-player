#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
export ROMAJI_HELPER_PATH="$(pwd)/dist/RomajiRomanizer/RomajiRomanizer"
[[ -x "$ROMAJI_HELPER_PATH" ]] || bash scripts/package-romanizer.sh
export ROMAJI_ALIGNER_PATH="$(pwd)/dist/RomajiAligner/RomajiAligner"
python3 scripts/package-aligner.py
export ROMAJI_TIFA_PATH="$(pwd)/dist/RomajiTIFA/RomajiTIFA"
[[ -x "$ROMAJI_TIFA_PATH" ]] || bash scripts/package-tifa.sh
export ROMAJI_EXPERIMENTAL_PATH="$(pwd)/dist/RomajiExperimental/RomajiExperimental"
[[ -x "$ROMAJI_EXPERIMENTAL_PATH" ]] || bash scripts/package-experimental.sh
python3 scripts/spotify-build-env.py cargo run --manifest-path Cargo.toml --locked --no-default-features -- "$@"
