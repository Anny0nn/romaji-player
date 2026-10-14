# Source-aware accuracy work

Status: research in progress on PR #5; no timing recipe promoted.

PR #4 merged at `21a8286`, retaining all 61 initial measurements. The fixed ten-song
set is **2,210/2,927 groups (75.5%)**, with 717 gaps. Its seven-low/three-high selection
and original denominators stay frozen in the [catalog](study-song-catalog.md).
The [approved plan](plans/source-first-accuracy.md) targets substantive gains across
multiple difficult songs, rather than completing after a small or null trial.

## Exact source ownership

The romanizer previously split unknown dotted kana into displayed words without
mapping their individual source spans. `ゲ・ン・カ・イ` became `ge/n/ka/i` with four
unmapped words. The converter now proves each ordered kana-to-romaji correspondence
and maps the four original pieces individually. Output spelling and group count stay
the same. Mixed half-width kana uses the existing normalization boundary proof;
an inexact reconstruction still keeps the fallback.

Nine additional regression cases cover exact ownership, rejected partial mappings
and source-anchored reading edits after reconversion. All 74 romanizer tests pass.
This establishes mapping correctness, not additional measured commercial word timing.

## Singing-trained English boundary challenger

[HubertFA-combined](https://huggingface.co/Silasimo/HubertFA-combined/tree/f20e23ab12596d914b2adfcbeb8882180dd92fac)
provides a singing-trained alignment head and a 39-phone ARPAbet inventory plus
silence. Its [Apache-2.0 inference source](https://github.com/wolfgitpr/HubertFA/tree/b3f086966946255a05b0ccb69c865c8e3e806e0a)
is available, unlike the missing SingAlign toolkit. The encoder is pinned
[Chinese HuBERT](https://huggingface.co/TencentGameMate/chinese-hubert-base/tree/fce0375452b1dd6c080ac3248d423d4d037bc831).
The head weights are CC-BY-NC-SA-4.0; the encoder is MIT. Research weights and corpus
files remain outside Git and the app. The source license is retained in
`scripts/third-party/HubertFA-LICENSE`.

The new adapter verifies every asset's size/SHA-256, uses restricted `weights_only`
loading, checks checkpoint configuration and vocabulary, and strictly loads every
inference parameter. Only seven named, shape-checked training-statistic buffers are
omitted. It does not create missing layers. It imports the pinned inference modules
and removes only plotting dependencies from the decoder. The released head does not
include the nonlexical checkpoint required by upstream's full CLI; this adapter makes
no breath-detection claim.

The adapter retains the 44.1 kHz /10 ms output clock and nearest 20 ms HuBERT feature
grid, including ties-to-even rounding. It uses existing SciPy polyphase resampling
instead of adding torchaudio, and follows upstream's raw, unnormalized waveform input.
There is no added left padding. These preprocessing choices are recorded in receipts.

The development comparison uses the already opened NUS ADIZ song 01: 12 phrases,
146 human phones and 37 human `sp` word groups. It is a supplied-phone boundary test,
with no gold spelling. JLEE song 05 remains reserved; this runner offers no heldout
operation and does not open or hash its annotation file.

| ADIZ development measurement         | Aligned | Within onset ≤150 ms and offset ≤200 ms |
| ------------------------------------ | ------: | --------------------------------------: |
| Complete supplied-phone paths        | 146/146 |                         129/146 (88.4%) |
| Complete human word groups           |   37/37 |                           32/37 (86.5%) |
| Word groups with unmasked mean ≥0.45 |    0/37 |                      No accepted groups |

Both CPU and MPS produce the same correct counts. This is better boundary evidence
than the earlier speech IPA pilot's 67/109 complete phone paths and 10/17 accepted
word groups, with different acceptance sets. It remains below an integration-quality
result: five word groups have excessive error, and the 37-group descriptive Wilson
interval is 72.0–94.1%. No model's output supplies a gold reference.

The model's decoder confidence is conditioned on the supplied phone sequence. Its
unmasked frame probabilities also do not behave like the existing Japanese recognizer's
probabilities. Neither is accepted as independent lyric verification. Audio-only CTC
IDs are saved as observations, without claiming that they establish spelling. A next
English trial needs a separately tested lexical verification path and wrong-target
controls, rather than lowering a threshold to raise commercial coverage.

| M2 Pro /16 GiB, four Torch CPU threads |  Load | Inference after load | Lifetime peak process RSS | End MPS driver sample |
| -------------------------------------- | ----: | -------------------: | ------------------------: | --------------------: |
| MPS                                    | 4.3 s |                1.7 s |                   0.81 GB |               1.56 GB |
| CPU                                    | 2.7 s |                1.9 s |                   1.51 GB |                     — |

These are serial, cached-asset development runs. RSS and driver allocation overlap
and are not added or called total unified-memory use. Loading includes asset verification.
The initial unrestricted-thread run took 4.6 seconds after load. The head and encoder
downloads total approximately 432 MB, apart from small source/config files.

Reproduce with an existing experimental environment and privately acquired reference
manifest (the same `development`, `heldout`, `songs` format as the earlier NUS runner):

```sh
.venv-experimental/bin/python scripts/benchmark-hubertfa.py fetch \
  --model-directory /private/tmp/romaji-hubertfa-research
.venv-experimental/bin/python scripts/benchmark-hubertfa.py run \
  --model-directory /private/tmp/romaji-hubertfa-research \
  --manifest /private/tmp/romaji-nus-private/reference-manifest.json \
  --output /private/tmp/romaji-hubertfa-development-mps --device mps
```

Completed phrase checkpoints bind the recipe and observation checksum; altered data
or identities are refused. Resume uses only authenticated completed observations.
Seven offline contract tests cover clocks, inventories, ownership, protected storage,
changed assets/checkpoints and abstentions. Normal repository checks never load models.

## Fresh local Japanese-romaji windows

`scripts/probe-local-romaji.py` tests a deliberately selected Japanese-romaji hypothesis
on the frozen 嘘 recording. Its source remains the original pre-romanized LRCLIB snapshot;
no alternate Japanese record was verified. Macron expansion, syllabic `N`, apostrophes
and gemination preserve the original word identities and displayed spelling. Thirteen
phone fixtures pass. English lookalikes such as `to` still need acoustic language
selection; successful parsing does not establish Japanese.

The tool verifies the frozen selection, Rust job/source-result hashes, original PCM,
delay, sample clock, model files and posterior frame lengths. It records the current
vocals and posterior hashes privately and reuses them without recording or recognition.
Fresh local TIFA alignment uses actual waveform slices and both observed endpoints.
Each candidate window is evaluated separately; overlapping proposals are not merged
into a recipe that no model observed.

Across 23 eligible crops, 29 local trials produced **zero additions beyond the earlier
one-word full-window proposal** and zero moves. Twenty-two missing-word searches had
no fresh paired anchor. The final run took 4.8 seconds with 1.06 GB lifetime peak RSS.
App data and commercial coverage remain unchanged. This rejects this first window
recipe as a substantive improvement; it does not justify relaxing the accuracy rules.

The accompanying region solver permits at most four groups. Both models must support
every replacement and contradict an old automatic interval before moving it. Fresh,
unchanged outer anchors contain the region. It protects supplied/user intervals,
preserves complete original group ownership and refuses actual overlap rather than
trimming timestamps. Eight offline tests cover these cases. It remains a research
tool pending labelled, wrong-window and commercial evaluation.

## Remaining work

The first experiments do not satisfy the plan's multi-song integration target. Continue
with independently verified English runs, local sung-reading alternatives and stronger
anchor evidence. Keep the ten-song set fixed, test new admission rules against the
existing references and negative controls, and report gains, losses and moved boundaries
separately. Do not rebuild the capture helper or ask the user to annotate songs.
