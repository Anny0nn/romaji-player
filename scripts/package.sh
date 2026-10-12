#!/usr/bin/env bash
# Produce a configured, self-contained app and a zip preserving framework links.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
[[ "$(uname -m)" == arm64 ]] || { printf 'Build on an Apple Silicon Mac.\n' >&2; exit 1; }
# Validate configuration before building anything. No .env is copied into the app.
python3 scripts/spotify-build-env.py python3 -c 'pass'
bash scripts/package-romanizer.sh
python3 scripts/package-aligner.py
bash scripts/package-tifa.sh
bash scripts/package-experimental.sh
python3 scripts/spotify-build-env.py cargo build --manifest-path Cargo.toml --locked --release --no-default-features
bash packaging/macos/bundle.sh target/release/spotifast dist/RomajiPlayer.app 0.12.0
cp -R dist/RomajiRomanizer dist/RomajiPlayer.app/Contents/Resources/
cp -R dist/RomajiAligner dist/RomajiPlayer.app/Contents/Resources/
cp -R dist/RomajiTIFA dist/RomajiPlayer.app/Contents/Resources/
cp -R dist/RomajiExperimental dist/RomajiPlayer.app/Contents/Resources/
mkdir -p dist/RomajiPlayer.app/Contents/Resources/Notices
cp LICENSE dist/RomajiPlayer.app/Contents/Resources/Notices/Spotifast-MIT.txt
cp .cache/aligner-source/qwen3-asr.cpp/LICENSE dist/RomajiPlayer.app/Contents/Resources/Notices/QwenCPP-MIT.txt
cp .cache/aligner-source/qwen3-asr.cpp/ggml/LICENSE dist/RomajiPlayer.app/Contents/Resources/Notices/GGML-MIT.txt
cp aligner/MODEL-LICENSE.txt dist/RomajiPlayer.app/Contents/Resources/Notices/QwenModel-Apache-2.0.txt
cp tifa/vendor/LICENSE dist/RomajiPlayer.app/Contents/Resources/Notices/TIFA-MIT.txt
cp tifa/notices/* dist/RomajiPlayer.app/Contents/Resources/Notices/
cp assets/fonts/*LICENSE.txt dist/RomajiPlayer.app/Contents/Resources/Notices/
python3 scripts/package-notices.py
.venv-tifa/bin/python scripts/package-python-notices.py
.venv-experimental/bin/python scripts/package-python-notices.py ExperimentalPython
cp refinement/MODEL-NOTICES.txt dist/RomajiPlayer.app/Contents/Resources/Notices/ExperimentalModels.txt
# PyInstaller includes library/dictionary license metadata. Preserve Python's notice too.
.venv/bin/python - <<'PY'
import sysconfig
from pathlib import Path
source = Path(sysconfig.get_path('stdlib'))/'LICENSE.txt'
if not source.is_file():
    raise SystemExit('Python license notice unavailable')
target = Path('dist/RomajiPlayer.app/Contents/Resources/Notices/Python-LICENSE.txt')
target.write_bytes(source.read_bytes())
PY
if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --timestamp --options runtime --sign "$CODESIGN_IDENTITY" dist/RomajiPlayer.app
else
  codesign --force --deep --sign - dist/RomajiPlayer.app
fi
codesign --verify --deep --strict dist/RomajiPlayer.app
/usr/bin/ditto -c -k --sequesterRsrc --keepParent dist/RomajiPlayer.app dist/RomajiPlayer.zip
printf 'Built dist/RomajiPlayer.app and dist/RomajiPlayer.zip\n'
