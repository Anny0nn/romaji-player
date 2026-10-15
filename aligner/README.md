# Native lyric alignment helper

Build with `python3 scripts/package-aligner.py`, after the explicit one-time
`python3 scripts/fetch-aligner-source.py` bootstrap. CMake and Apple's command-line
tools are build dependencies. The recipient's Mac needs neither.

Dependencies are exported into ignored `.cache/aligner-source/`, with upstream
agent instructions excluded. The fetch script records and verifies its raw-timing
adapter against the exact pinned source; it removes interpolation, timestamp
repair and clamping. No model is downloaded by builds or checks.

- qwen3-asr.cpp: `6dcc586e5073fd6e85ee5728e75f0903d6c70c6c`, MIT.
- GGML: `9be313313c8ecb9488911bd64550190e3ed80f38`, MIT, embedded Metal shaders.
- Qwen3-ForcedAligner-0.6B Q8: OpenVoiceOS revision
  `efe4002aa7d567851883c05f9950c869debe8847`, Apache-2.0; model size and SHA-256
  live in `scripts/observe-native-word-bounds.py`; the default TIFA archive is a
  separate model pinned in `src/study/alignment.rs`. The quantized checkpoint was tested
  directly. A similarly named, incompatible GGUF from another converter was rejected.

Protocol v2 takes model path, mono 16 kHz little-endian float32 PCM path, and
binary crop-manifest path. All fields are little-endian uint32. After version/count,
each crop contains occurrence/start-sample/end-sample/word-count. Each word contains
original-start-byte/original-end-byte/input-text-byte-count followed by UTF-8 text.
Rust supplies contextual hiragana readings, falling back to the written source when
unavailable. Input punctuation is omitted without changing source anchors. Explicit
word groups use the library's whitespace segmentation path, avoiding its Japanese
character splitter. This argument selects segmentation rather than acoustic language.
Bounds are checked before inference. Each stdout line contains an occurrence and
raw-span/text/start-ms/end-ms units relative to that crop. Audio and lyrics never
appear in argv or error messages.

Rust validates the complete audio ledger, reply size, word identities and
timestamp bounds; it owns grouping, offsets and durable storage. Bad word predictions
are omitted individually. It retains a longest ordered subset of model intervals,
then bounds overlapping selection by the next observed onset, without interpolation
or snapping. One bad word no longer discards every word in its line.
The helper has no confidence score;
listening tests on Japanese singing are still required.

`synthetic-tone.ogg` is a generated 440 Hz, 300 ms stereo Vorbis regression fixture
for decoder priming and packet timestamp continuity. It contains no song audio.
The model smoke uses synthetic Japanese speech outside the offline hook suite.
