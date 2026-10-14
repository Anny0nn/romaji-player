# Bundled romanizer

This is a persistent newline-delimited JSON helper, built on Cutlet/fugashi
with unidic-lite. Rust owns lyric/timing storage and playback; this helper
owns whole-line normalization, source mapping, conversion and atomic reading
corrections. It supplies contextual hiragana, katakana and romaji with separate display
spans on the same original word groups. A selected-reading record also supplies model
targets and eligible inflected dictionary pronunciations, without overriding saved
sung readings. Hiragana preserves particle spelling;
unverified reverse readings show an explicit placeholder. Protocol version 2
uses only UTF-8 byte ranges. The plan describes
identity fields and units; `src/study/conversion.rs` validates returned ranges.

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r romanizer/requirements.lock
.venv/bin/python -m pytest romanizer -q
bash scripts/package-romanizer.sh
python3 scripts/check-helper-package.py
```

The package is ARM64, approximately 269 MB uncompressed, including its runtime
and dictionary. Preserve framework symlinks when copying or archiving. No
HTTP service or Python install is needed by recipients. Package checks are
separate from normal hooks; pytest and real Rust/Python protocol tests are in
the normal full gate. Requests are bounded, stale responses are rejected,
and invalid/ambiguous source mappings remain visible for correction.

Verified track/context readings are bundled defaults, not guesses. SAKURA's
故郷(まち) comes from [Uta-net's licensed annotation](https://www.uta-net.com/song/37330/).
departure!'s 地球(ほし) follows [its licensed annotation](https://www.uta-net.com/song/123698/),
fixing the dictionary reading _chikyuu_ in the reported line around 48–50 seconds.
It changes the displayed reading while preserving source spans; saved user corrections
take precedence. Other songs and contexts retain dictionary readings.
