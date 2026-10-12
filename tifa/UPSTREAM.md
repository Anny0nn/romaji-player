# TIFA runtime provenance

Imported runtime files from [openvpi/TIFA](https://github.com/openvpi/TIFA/tree/32a0a13aebce580844ad1dc281ea11ef1be94f14),
v1.0.0, commit `32a0a13aebce580844ad1dc281ea11ef1be94f14`, under MIT.
`vendor/original-sha256.json` lists the exact unmodified imported Python files and hashes.
Training, Lightning runners, CLI, datasets, plotting, source README, instruction files,
agent metadata, and Chinese dictionaries/converters are excluded.

The three G2P package initializers are local runtime-only replacements. The original ones
discover converters by filesystem enumeration and import unrelated converters; explicit imports
make freezing predictable. Model network, mel features, G2P conversion and Viterbi decoding
remain upstream code. `patches/token-probability.patch` exposes the existing token probabilities
in `AlignResult`; it changes returned metadata only. `vendor/local-sha256.json` pins that patch. Our loader replaces the training-oriented `inference/api.py`: it uses the
same configuration classes, backend, vocabulary and strict state dictionary, with explicit
`weights_only=True` after checking the pinned archive and every extracted asset.

Model: [TIFA-1.0-ST release](https://github.com/openvpi/TIFA/releases/tag/v1.0.0).
Archive: 150,789,526 bytes, SHA-256
`6da6832cd2cb981aae1ccc2d9330f8f7c085ce7977d1eb13bff63531d038a88b`.
`model-files.json` pins weights, config, vocabulary, Japanese/English dictionaries and English
G2P assets. Only these members are extracted. The downloaded model is CC BY-NC-SA 4.0;
the release explicitly excludes output data from that restriction.
The English [LstmG2p model](https://github.com/wolfgitpr/LstmG2p/releases/tag/v1.0.0) is Apache-2.0,
and the [CMU pronunciation dictionary](https://github.com/cmusphinx/cmudict/blob/master/LICENSE)
retains its notice. Notices accompany the app. This personal learning app uses the released model
without modification; a commercial distribution would need a separate license decision.

`requirements.lock` pins a dedicated inference/build environment. Torch is needed for TIFA's
Apple Silicon Metal backend; SciPy resamples the existing 16 kHz capture to the model's 48 kHz,
and ONNX Runtime is needed for unknown English pronunciations. Recipients need none of these
installed. PyInstaller bundles them. The model downloads once when automatic timing is first used.

Protocol 3 preserves original UTF-8 source spans and reading identity, and adds displayed romaji
for particle pronunciation. A negative interval means unavailable timing. Silence, incomplete
phoneme paths, sub-80 ms words, negative mean similarity, invalid bounds, and individual word
mismatches (mean phoneme-token agreement below 0.99) are withheld. Agreement is not calibrated confidence: mismatched
lyrics can still pass, so coverage must be checked by listening. No missing interval is interpolated.
