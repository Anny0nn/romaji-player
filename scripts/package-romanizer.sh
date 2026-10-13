#!/usr/bin/env bash
# Build a standalone ARM64 converter; no user Python environment is needed.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
project_root="$(pwd)"
[[ "$(uname -m)" == arm64 ]] || { printf 'Build the helper on an Apple Silicon Mac.\n' >&2; exit 1; }
.venv/bin/python -m PyInstaller --noconfirm --clean --onedir --name RomajiRomanizer \
  --hidden-import shlex --target-arch arm64 --distpath dist --workpath build/romanizer \
  --specpath build --collect-all cutlet --collect-all fugashi --collect-all unidic_lite \
  --copy-metadata cutlet --copy-metadata fugashi --copy-metadata unidic-lite \
  --copy-metadata mojimoji --copy-metadata jaconv \
  --add-data "$project_root/romanizer/romanizer.py:." romanizer/romanizer.py
codesign --force --deep --sign - dist/RomajiRomanizer
codesign --verify --deep --strict dist/RomajiRomanizer
printf 'Standalone helper: dist/RomajiRomanizer/RomajiRomanizer\n'
