#!/usr/bin/env bash
# Self-contained Apple Silicon inference; weights download on first timing use.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
project_root="$(pwd)"
[[ "$(uname -m)" == arm64 ]] || { printf 'Build TIFA on Apple Silicon.\n' >&2; exit 1; }
.venv-tifa/bin/python -m PyInstaller --noconfirm --clean --onedir --name RomajiTIFA \
  --target-arch arm64 --distpath dist --workpath build/tifa --specpath build \
  --paths tifa/vendor --hidden-import modules.backbones.jebf --hidden-import onnxruntime \
  --collect-all librosa --collect-all numba --collect-all llvmlite \
  --copy-metadata torch --copy-metadata numpy --copy-metadata scipy --copy-metadata librosa \
  --copy-metadata numba --copy-metadata llvmlite --copy-metadata onnxruntime \
  --copy-metadata pydantic --copy-metadata omegaconf --copy-metadata einops --copy-metadata filelock \
  --add-data "$project_root/tifa/vendor:vendor" \
  --add-data "$project_root/tifa/model-files.json:." tifa/tifa_helper.py
codesign --force --deep --sign - dist/RomajiTIFA
codesign --verify --deep --strict dist/RomajiTIFA
dist/RomajiTIFA/RomajiTIFA --self-test
