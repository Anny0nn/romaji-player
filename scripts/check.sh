#!/usr/bin/env bash
# The project's only gate: there is no CI. The pre-commit hook runs `--quick`, the pre-push hook
# runs everything. Add each new kind of check here in the PR that introduces the code it covers.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

quick=false
case "${1:-}" in
  '') ;;
  --quick) quick=true ;;
  *) printf 'Usage: bash scripts/check.sh [--quick]\n' >&2; exit 2 ;;
esac

step() { printf '\n== %s\n' "$1"; }

step 'Shell syntax'
while IFS= read -r -d '' file; do
  bash -n "$file"
done < <(git ls-files -z -- '*.sh' '.githooks/*')

step 'Markdown formatting'
# Keep Prettier pinned through npx; Markdown checks do not require a Node project.
# Symbolic links (AGENTS.md) are skipped: Prettier checks the file they point to.
git ls-files -z -- 'README.md' 'CONTRIBUTING.md' 'docs/plans/*.md' 'docs/study*.md' 'romanizer/*.md' 'aligner/*.md' 'tifa/*.md' |
  while IFS= read -r -d '' file; do [[ -L "$file" ]] || printf '%s\0' "$file"; done |
  xargs -0 npx --yes prettier@3.9.6 --check --log-level warn

step 'Whitespace'
git diff --check HEAD

step 'Public export paths'
python3 scripts/check-export.py

step 'Rust formatting'
cargo fmt --manifest-path Cargo.toml --all -- --check

step 'Rust Clippy'
cargo clippy --manifest-path Cargo.toml --locked --no-default-features --all-targets -- -D warnings

step 'Python format/lint'
.venv/bin/ruff format --check romanizer tifa/tifa_helper.py tifa/tests refinement scripts/*.py scripts/tests
.venv/bin/ruff check romanizer tifa/tifa_helper.py tifa/tests refinement scripts/*.py scripts/tests

step 'Native aligner compilation'
cmake -S aligner -B aligner/build -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build aligner/build --target RomajiAligner -j 4 >/dev/null

if [[ "$quick" == true ]]; then
  printf '\nQuick checks passed.\n'
  exit 0
fi

step 'Aligner protocol tests'
aligner/build/RomajiAligner --self-test

step 'Romanizer tests'
.venv/bin/python -m pytest romanizer -q

step 'Reading experiment boundary tests'
.venv/bin/python -m unittest discover -s scripts/tests -q

step 'TIFA protocol and word retention tests'
.venv-tifa/bin/python -m pytest tifa/tests refinement/tests -q

step 'Native tests'
cargo test --manifest-path Cargo.toml --locked --no-default-features

printf '\nAll checks passed.\n'
