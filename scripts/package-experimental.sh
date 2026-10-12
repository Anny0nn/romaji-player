#!/usr/bin/env bash
# Bundle inference code only; pinned experimental weights download on first use.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
project_root="$(pwd)"
[[ "$(uname -m)" == arm64 ]] || { printf 'Build on Apple Silicon.\n' >&2; exit 1; }
.venv-experimental/bin/python -m PyInstaller --noconfirm --clean --onedir --name RomajiExperimental \
  --target-arch arm64 --distpath dist --workpath build/experimental --specpath build \
  --paths tifa --paths tifa/vendor --paths refinement \
  --hidden-import modules.backbones.jebf --hidden-import onnxruntime \
  --collect-all librosa --collect-all numba --collect-all llvmlite --collect-all mlx \
  --collect-all demucs_mlx --collect-all mlx_spectro \
  --hidden-import mlx_audio.dsp \
  --hidden-import transformers.models.wav2vec2.modeling_wav2vec2 \
  --copy-metadata torch --copy-metadata numpy --copy-metadata scipy --copy-metadata librosa \
  --copy-metadata numba --copy-metadata llvmlite --copy-metadata onnxruntime \
  --copy-metadata pydantic --copy-metadata omegaconf --copy-metadata einops --copy-metadata filelock \
  --copy-metadata transformers --copy-metadata tokenizers --copy-metadata safetensors \
  --copy-metadata huggingface-hub --copy-metadata mlx --copy-metadata mlx-audio \
  --add-data "$project_root/tifa/vendor:vendor" \
  --add-data "$project_root/tifa/model-files.json:." \
  --add-data "$project_root/refinement/refinement-model-files.json:." \
  --add-data "$project_root/.venv-experimental/lib/python3.14/site-packages/mlx_audio/sts/models/mel_roformer:mel_roformer" \
  refinement/refinement_helper.py
codesign --force --deep --sign - dist/RomajiExperimental
codesign --verify --deep --strict dist/RomajiExperimental
dist/RomajiExperimental/RomajiExperimental --self-test
