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

## Recognition and boundary agreement

The new collector authenticates the frozen Rust jobs, source snapshots, recordings,
model manifests and stems. It reuses three stems and collects the other four low-set
stems without re-recording. Audio contexts union complete Rust crops, stay at most
30 seconds, and are chosen before recognition. They never supply word clocks.

Source-blind Whisper large-v3 recognizes 172 mix/vocal context views with `language=en`,
no lyric prompt and no previous-text conditioning. Source-bearing reconciliation lives
separately outside Git. Each candidate needs a unique exact multiword match and at
least 0.70 confidence in both views. Its observed midpoint checks occurrence inside
the original cue; Whisper endpoints are never copied, clipped or rescaled.

Fresh TIFA and HubertFA must observe both boundaries within 150 ms. TIFA still needs
positive similarity, 0.90 agreement and 80 ms duration; its actual interval is retained.
The known-phone ADIZ development comparison retains **31/37 envelopes, all 31 correct**
within the labelled limits. TIFA alone retains 35/37, all 35 correct. This tests boundaries
for supplied correct phones, not spelling. The pair's descriptive Wilson interval is
89.0–100%, so it does not certify 98% correctness across songs.

| Frozen song                        | Gaps recognized in both views | Dictionary proposals | CMU fallback proposals |
| ---------------------------------- | ----------------------------: | -------------------: | ---------------------: |
| Just Awake                         |                             0 |                    0 |                      0 |
| Wild Side                          |                            16 |                    0 |                      3 |
| Kyouran Hey Kids!!                 |                             0 |                    0 |                      0 |
| TEENAGE CITY RIOT                  |                            10 |                    1 |                      1 |
| LOST IN PARADISE                   |                            19 |                    7 |                      7 |
| 嘘                                 |                             2 |                    0 |                      0 |
| 天天天国地獄国                     |                             0 |                    0 |                      0 |
| たぶん / CROW / 残酷な天使のテーゼ |                             0 |                    0 |                      0 |
| Total                              |                            47 |                    8 |                     11 |

Latin script does not establish English: the two recognized 嘘 groups obtain no new
timing. This first boundary runner withholds mixed cues. Extended dictionary phones
`ax`, `dx` and `_r` initially block whole cues; the CMU fallback predicts a complete
alternative with the existing LSTM converter. It does not substitute unknown phones,
remove groups or change lyrics. Every alternative still needs both observed boundaries
and both lexical views.

The dictionary trial takes 7.9 seconds after loading, with 0.75 GB lifetime RSS; the
CMU fallback takes 8.6 seconds, with 1.13 GB. Eleven proposals would give 2,221/2,927
(75.9%), with zero losses/moves. **Saved app coverage remains 2,210/2,927.** Full accuracy
and negative checks are still pending; these counts are not listening-verified completeness.

The reproducible sequence is `cache-capped-singing.py`, `transcribe-timing-crops.py`,
`probe-context-english.py`, then `probe-english-boundaries.py --pronunciation cmu-fallback`.
Their `--help` lists private manifests/cache paths. Completed observations bind source,
audio, recipe and record hashes; changed identities or silent overwrites are refused.

## Singing CTC pronunciation veto

The HubertFA adapter exposes its unmasked audio-only CTC probabilities through an
optional observer. No supplied-phone mask influences that head. It shares an encoder
with the alignment head, so those heads are correlated evidence. Its statistics stay
separate from Whisper's word-confidence statistic.

The exploratory gate requires every phone's probability at least 0.45, greedy agreement
at least 0.90, an adjacent qualifying word and paired TIFA/HubertFA endpoints. On opened
ADIZ development material, **3/37 words qualify, all three with correct boundaries**.
The CTC veto rejects 111 fixed wrong-phone substitutions. Those are pronunciation
controls, separate from the 143 wrong-window/verse integration controls. There is no
orthographic gold and JLEE remains unopened. The three-word descriptive Wilson interval
is 43.9–100%; this does not establish a generally calibrated acceptance rule.

Across 189 whole-English commercial cues, the boundary pair finds 137 missing candidates
but the complete dual-view CTC gate adds **zero**. Existing intervals remain unchanged.
The run takes 63.3 seconds with 1.89 GB lifetime RSS. This rejects the first CTC recipe;
it does not justify bypassing pronunciation verification. `benchmark-english-ctc.py`
records the development/control comparison, while `--lexical-mode singing-ctc` selects
the private commercial probe. Neither writes app data.

## MOSS-Music singing transcription pilot

[MOSS-Music](https://github.com/OpenMOSS/MOSS-Music) is a different singing-specific
recognizer. The research bootstrap pins the community
[4-bit checkpoint](https://huggingface.co/mlx-community/MOSS-Music-8B-Thinking-4bit/tree/b14123a419b6254b92d9e55b8a5b6f7285e05c70)
and [MLX runtime](https://github.com/Blaizzy/mlx-audio/tree/70f4add32911bab6f869b824864ad9f1e24dcb97).
Weights are Apache-2.0; runtime source is MIT. `scripts/moss-model-files.json` records
every model artifact, the runtime archive and three Apple Silicon Python 3.14 dependency
wheels. They are installed privately, without changing the app's locked dependencies.
Offline inference verifies files/source, requires `strict=True` and rejects remote
tokenizer code. Generated text is an unverified proposal; timestamps are not word clocks.

The pilot picks a difficult context each from Just Awake and Wild Side using baseline
missing-group counts, then transcribes mix and vocals without lyric input. All four
22.0–29.5-second clips exhaust 1,024 tokens with repetitive output. Loading takes
12.1 seconds; clips take 36.0–53.1 seconds. Largest MLX peak is 6.73 GB; process RSS is
1.19 GB. Those accounting measures overlap and are not added or called total unified
memory. The 6.02 GB checkpoint download/verification takes 329 seconds.

A second diagnostic uses the official timestamp-transcription task in a full chat
prompt with an empty thinking suffix. Both identical Just Awake contexts exhaust
256 tokens again. It takes 25.4 seconds including loading, with 6.61 GB MLX peak.
No generated text or timestamp is accepted as a correction.

[Upstream reports similar repetition](https://github.com/OpenMOSS/MOSS-Music/issues/1)
and says its Hugging Face path was fixed; no confirmed corresponding MLX fix was found.
The [separate MLX port](https://github.com/OpenMOSS/MOSS-Music/pull/3) calls 4-bit/6-bit
execution unverified. This does not prove quantization caused the result or justify
a 10.2 GB 8-bit download. Reject the tested path until a concrete inference change
merits another bounded pilot. Local loading success does not establish singing accuracy.

```sh
.venv-experimental/bin/python scripts/fetch-singing-research.py \
  --output /private/tmp/romaji-moss-research
.venv-experimental/bin/python scripts/transcribe-singing-crops.py \
  /private/tmp/romaji-private/audio-only-pilot.json \
  --asset-directory /private/tmp/romaji-moss-research \
  --output /private/tmp/romaji-moss-pilot
```

## Remaining work

The first experiments do not satisfy the plan's multi-song integration target. Continue
with independently verified English runs, local sung-reading alternatives and stronger
anchor evidence. Keep the ten-song set fixed, test new admission rules against the
existing references and negative controls, and report gains, losses and moved boundaries
separately. Do not rebuild the capture helper or ask the user to annotate songs.
