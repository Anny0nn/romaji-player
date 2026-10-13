# Singing accuracy: implementation experiments

This report records work after approval of the [accuracy plan](plans/singing-accuracy.md)
on 2026-10-13. Tests use the existing fourteen private recordings on an Apple M2 Pro with
16 GiB memory. The integrated Experimental update retains **3,435/4,160 words**, versus
3,434 previously. It adds one narrowly guarded pronunciation fallback; the broader
challengers below remain offline. Original TIFA remains at 3,121/4,160.

## Integrated result

`vowel-extension-v1` handles same-vowel small-kana spellings such as `あぁ` only when
the normal TIFA pronunciation converter rejects them. It preserves original text,
readings and byte anchors. Independent MMS support, phrase coherence and the existing
bounded repair policy remain required. Only nominated unsupported spans may gain timing;
the fallback cannot authorize unrelated missing words. Valid digraphs are preserved.

Both packaged helpers ran through the native app's pipeline on all fourteen cached
recordings, with isolated result directories. Comparisons use source occurrence and byte
span, verify identical recording/source/delay identities, and keep the 4,160-word denominator.

| Recording            | Previous Experimental | Updated Experimental | Gains / losses | Existing words adjusted | TIFA / Experimental seconds |
| -------------------- | --------------------: | -------------------: | -------------: | ----------------------: | --------------------------: |
| SAKURA               |               265/265 |              265/265 |          0 / 0 |                       0 |                 9.6 / 220.5 |
| うれしくて           |               363/423 |              363/423 |          0 / 0 |                       0 |                 9.3 / 266.0 |
| departure!           |               209/221 |              209/221 |          0 / 0 |                       0 |                 6.6 / 175.4 |
| spiral               |               238/245 |              238/245 |          0 / 0 |                       0 |                 6.4 / 161.0 |
| Koino Uta            |               223/307 |              223/307 |          0 / 0 |                       0 |                 6.0 / 150.4 |
| Tabi no Tochuu       |               153/153 |              153/153 |          0 / 0 |                       0 |                 5.4 / 181.0 |
| NEVER SAY GOODBYE    |               367/430 |              367/430 |          0 / 0 |                       0 |                 7.1 / 200.8 |
| Just Awake           |               183/306 |              183/306 |          0 / 0 |                       0 |                 6.7 / 161.6 |
| the WORLD            |               135/153 |              135/153 |          0 / 0 |                       0 |                 5.8 / 154.9 |
| 色彩                 |               269/291 |              270/291 |          1 / 0 |                       1 |                 6.2 / 148.9 |
| 君のせい             |               259/270 |              259/270 |          0 / 0 |                       0 |                 6.3 / 180.5 |
| 今世大革命           |               188/246 |              188/246 |          0 / 0 |                       0 |                 7.0 / 155.4 |
| Bling-Bang-Bang-Born |               335/473 |              335/473 |          0 / 0 |                       0 |                 7.4 / 163.1 |
| 天天天国地獄国       |               247/377 |              247/377 |          0 / 0 |                       0 |                 7.3 / 197.1 |
| **Total**            |       **3,434/4,160** |      **3,435/4,160** |      **1 / 0** |                   **1** |      **6.6 / 169.3 median** |

All original TIFA intervals are identical to the previous run. All fifteen automatic
reading occurrences are unchanged, including the six verified Tabi readings. The sole
changed existing interval is adjacent to the recovered 色彩 word inside its bounded
repair region; no other song moves. This qualifies as a narrow conversion fix, not a
passing general-recovery recipe or a listening-verified accuracy improvement.

All **28 saved action results** were reopened and reconverted with the standalone
romanizer. Native checks verified word highlight intervals and valid spans in romaji
and hiragana, retained earlier bundles, selected a previous version and restored that
selection after another save/reopen. Offline tests additionally cover protected edits,
stale/cancelled jobs, regrouping, nonzero delay and persisted display modes.

For the affected vocal crop, the first execution of TIFA retry plus MMS verification
took **6.93 seconds**; three subsequent runs took **1.86, 2.35 and 1.91 seconds**,
each recovering the same one word. Models reload sequentially each run; weights are
already on disk. This stage excludes separation, transcription, source conversion,
integrity checking and process startup. Its lifetime peak RSS reached 1.15 GB.
Pre-release MPS driver samples reached 2.24 GB; they are allocation samples, not true
peaks or total unified-memory use. MLX did not infer in this focused stage.

The complete native jobs had cached-weight median times of **6.6 seconds TIFA** and
**169.3 seconds Experimental**. Two-second process-tree sampling covered 25 action jobs
(it began during the second song), with a largest sampled summed RSS of **2.99 GB**.
RSS can double-count shared pages and excludes accelerator allocations. System swap
used rose from 8,786 to 9,883 MiB, while `memory_pressure -Q` free percentage changed
from 20% to 62%. This shared-machine observation includes background applications and
research pauses; the swap delta is not attributed solely to one app job. All jobs
completed without an out-of-memory failure. No first-download latency was remeasured.
The fix adds no weights or runtime dependency; existing first-use downloads remain
about 151 MB TIFA plus 5.3 GB Experimental.

Standalone `RomajiPlayer.app` and its distribution zip were rebuilt from this recipe.
`check-helper-package.py` and `check-app-package.py` passed: ARM64 architecture,
deep/strict signing, relocation into a path containing spaces, Rust-to-bundled converter
calls, helper protocols and the Experimental-to-romanizer boundary with a minimal PATH.
The bundle contains inference runtimes and notices, not private recordings, reference
labels or the research-only English checkpoint. Repository validation uses the mandatory
full `bash scripts/check.sh` pre-push gate; model runs remain separate explicit acceptance
commands.

## Reproduced diagnostic

`scripts/diagnose-song-suite.py` joins explicit hashed case, historical TIFA diagnostic and
saved Experimental result inputs. It verifies source UTF-8 spans, exact lyric occurrences,
word grouping and declared coverage. Its private ledger records crop/audio/source identity,
conversion signatures and saved recipe/model identity. It rejects stale or mismatched inputs.

The Rust export test calls the same `crop_targets` function as the app. All fourteen
recording hashes, **671 crop windows** and source target-span lists matched the cached
cases exactly. A regression distinguishes recording origin from a nonzero saved delay.
Legacy diagnostic reasons remain labelled historical, even after validating their windows.

| Measure                                                          |      Result |
| ---------------------------------------------------------------- | ----------: |
| Original words                                                   |       4,160 |
| Saved Experimental timings                                       |       3,434 |
| Missing timings                                                  |         726 |
| Missing spans containing ASCII Latin letters                     |         404 |
| Missing spans containing Latin letters and only ASCII characters |         397 |
| Crops reaching 30 seconds                                        |       1/671 |
| Historical TIFA token-agreement rejections among missing spans   |         683 |
| Historical duration / unsupported / incomplete                   | 25 / 12 / 6 |

Latin script is not a language label, and historical rejections do not establish why the
current Experimental recipe abstains. This supports investigating pronunciation and mixed
language before changing the crop cap. Full lyric/audio evidence stays outside the checkout.

## Pronunciation selection pilot

TIFA normally takes the first valid whole-word pronunciation path. The challenger uses
its pinned backend's acoustic scorer to select complete alternatives, preserving phone
ownership. It changes no numerical vendor source, timing thresholds or source mappings.

Across all fourteen mix recordings, it retained **3,118/4,160**, compared with TIFA's
3,121. It gained 36 spans, lost 39 and moved 42 shared intervals by more than 150 ms at
either endpoint. The run took **56.1 seconds**, including one model load for the suite;
the process lifetime peak RSS was **1.25 GB**. This is not a per-song app latency or
unified GPU-memory measurement.

| Recording                 | Baseline TIFA | Scored alternatives | Gains | Losses | Shared spans moved >150 ms |
| ------------------------- | ------------: | ------------------: | ----: | -----: | -------------------------: |
| Bling-Bang-Bang-Born      |           303 |                 312 |    24 |     15 |                         16 |
| Just Awake                |           178 |                 172 |     2 |      8 |                         17 |
| NEVER SAY GOODBYE         |           341 |                 337 |     8 |     12 |                          7 |
| departure!                |           204 |                 204 |     1 |      1 |                          2 |
| 今世大革命                |           154 |                 152 |     1 |      3 |                          0 |
| Remaining nine recordings |     unchanged |           unchanged |     0 |      0 |                          0 |

**Decision:** reject replacing the first-path strategy. Candidate scoring may later
nominate a bounded alternative, but these results do not justify accepting its choice.
TIFA's token-agreement diagnostic is self-consistency, not a calibrated correctness score.

The CLI exposes `--score-pronunciations`; the helper defaults to the original behavior.
An offline regression checks that an alternative adding a phone is selected as a whole
word, rather than mixing individual phones from incompatible readings.

## Whisper language pilot

The shipped transcription helper now permits explicit Japanese, English or detection
**for experiments**, with Japanese remaining its default. It stays blind to source lyrics,
uses transcription rather than translation, and releases the model between recordings.

Full-song detection ran on the mix and Kim vocals for Tabi no Tochuu, Just Awake,
Bling-Bang-Bang-Born and 天天天国地獄国: **all eight inputs detected Japanese**. Total
decode time was **258.9 seconds** with weights cached. These initial detection runs do not
measure reading precision or recovery. They show that detection alone will not route
those mixed-language songs to an English pass.

`scripts/experiment-song-language.py` verifies pinned assets and recording hashes, records
decoder/model-manifest identity and explicit language settings, and writes private segment
results without changing app documents. The initial eight pilot outputs predate the added
decoder/model provenance fields; they remain exploratory. Bounded English retries need
an independently evaluated English acoustic path before any app promotion.

## Human phone-boundary calibration

The [PJS corpus](https://sites.google.com/site/shinnosuketakamichi/research-topics/pjs_corpus)
and [human monophone relabels](https://github.com/UtaUtaUtau/pjs-manual-labels) state
CC BY-SA 4.0. Their audio and labels are stored privately. Twenty whole-song IDs were
reserved before inspecting label contents; eighty form the development partition.

`scripts/benchmark-singing-phones.py` hashes the archives, extracted recordings/labels,
split, recipes and implementation. It imports integer HTK 100 ns times as recording
milliseconds and compares **raw phone boundaries**, with silence excluded. Supplied
reference phones bypass G2P, recognition and app word-retention policy: this is a decoder
boundary calibration, not a reading or word-accuracy evaluation.

On eighty development recordings there were **5,448 non-silence reference phones**.
Thirteen recordings contain uppercase `I/U/O`, whose PJS convention is undocumented;
the runner abstained on those complete sequences rather than dropping or relabelling the
unknown phones. That leaves **4,506 aligned phones and 942 abstentions**.

| Metric on aligned phones            |               Result |
| ----------------------------------- | -------------------: |
| Onset ≤150 ms and offset ≤200 ms    | 4,500/4,506 (99.87%) |
| Onset median / p90 / p95 error      | 3.9 / 12.3 / 18.3 ms |
| Offset median / p90 / p95 error     | 3.8 / 11.7 / 16.5 ms |
| Joint phrase-bootstrap 95% interval |         99.73–99.98% |

Three TIFA skip penalties (0, 0.5 and 1) produced identical boundaries. The complete
three-recipe run took **26.6 seconds** after loading, with **0.85 GB** process lifetime
peak RSS. **Decision:** changing that penalty has no demonstrated value on this reference
pilot.

After freezing archive, recipe and implementation hashes, the twenty reserved recordings
were evaluated together: **1,434 reference phones, 1,291 aligned and 143 abstentions**.
All **1,291/1,291** aligned phones met onset ≤150 ms and offset ≤200 ms, with identical
results for the three penalties. Onset median/p90/p95 errors were 4.0/13.6/18.8 ms;
offset errors were 3.9/12.4/16.2 ms. The descriptive Wilson interval is 99.70–100%; the
phrase bootstrap is degenerate at 100% because every aligned unit passes. Neither
interval establishes perfect population accuracy. The three-recipe run took 7.4 seconds
after loading, with lifetime peak RSS 0.92 GB. This pool is now opened and must not be
reused as unseen tuning evidence.

PJS is one male singer in controlled conditions. `cl` also labels glottal stops in the
human relabel; this score preserves the supplied label instead of claiming a geminate
recognition test. References have no published per-boundary uncertainty; the importer
records it as unknown. [TIFA's release](https://github.com/openvpi/TIFA/releases/tag/v1.0.0)
discloses private training data without enough detail to rule out PJS. The partition is
held out from this project's tuning, **not certified unseen by the pretrained model**.
These results therefore cannot establish word or reading accuracy on commercial songs.

The heldout command requires a previously frozen receipt matching recipes, archives,
split and implementation. The runner emits no partial per-song heldout reports; evidence
is released only when the entire run finishes. Offline tests cover stale receipts,
partition overlap, HTK units, abstentions and invalid/mismatched prediction identities.

## Neighboring-phrase context pilot

`scripts/build-context-cases.py` constructs neighboring windows from the exported Rust
sample bounds. It preserves original occurrence/UTF-8 ownership, checks mix/stem hashes,
and excludes contexts containing existing reading repairs when replaying older canonical
targets. All trial inputs remain private. `scripts/evaluate-context-trial.py` replays
TIFA and independent MMS evidence through `refinement/context_policy.py`.

The complete pilot used 311 joint windows. TIFA took 28.0 seconds and MMS 53.3 seconds,
with process lifetime peak RSS 0.96 GB and 0.58 GB respectively. Evidence must agree at
both endpoints within 150 ms, meet MMS probability 0.45 and the existing phrase/region
guards, and retain the original source occurrence's crop bounds. Conflicting context
proposals are rejected atomically; compatible overlapping proposals are not spliced.
No word is relocated to another occurrence or given an interpolated timestamp.

| Recording                  | Additional model-supported words | Existing intervals adjusted | Lost words |
| -------------------------- | -------------------------------: | --------------------------: | ---------: |
| Koino Uta                  |                                7 |                           2 |          0 |
| the WORLD                  |                                1 |                           0 |          0 |
| 色彩                       |                                6 |                           5 |          0 |
| うれしくて                 |                                1 |                           0 |          0 |
| 天天天国地獄国             |                                8 |                           9 |          0 |
| 今世大革命                 |                                7 |                           1 |          0 |
| 君のせい                   |                                1 |                           1 |          0 |
| Remaining seven recordings |                                0 |                           0 |          0 |
| **Total**                  |                           **31** |                      **18** |      **0** |

That would increase retention from 3,434 to 3,465/4,160 if enabled. An earlier policy
allowed one extra word beyond its original crop; enforcing the native app's bounds
withheld it. These are cached commercial-song proposals, not verified improvements.

`scripts/benchmark-singing-context.py` then tested the actual TIFA/MMS/context functions
on the eighty PJS development recordings, grouping complete CV/N sequences into at
most two-mora reference units. This is an explicit **nonlexical phone grouping**, not
a word or reading-recognition benchmark. Unknown `I/U/O`, ambiguous `cl` and incomplete
phone sequences reject the entire phrase. Short phrases are excluded from this two-line
test, with counts reported separately. The 3,059 original vowel/N units therefore do
not share a denominator with the 916 eligible grouped units in 123 voiced phrases.

| Condition                            | Baseline aligned groups | Joint windows retried | Newly affected groups | Joint onset ≤150 ms / offset ≤200 ms on aligned groups |
| ------------------------------------ | ----------------------: | --------------------: | --------------------: | -----------------------------------------------------: |
| Clean reference singing              |                 881/916 |                    34 |                     0 |                                                 93.19% |
| Fixed band-limited noise at 0 dB SNR |                 855/916 |                    49 |                     0 |                                                 79.53% |

Both runs had zero losses or regressions, because no proposals passed the contextual
policy. They took 48.4 and 52.2 seconds, with lifetime peak RSS 2.59 and 2.61 GB.
The synthetic noise preserves human reference endpoints; it does not create labelled
commercial mixtures. Sixty-six unsupported and 32 short/long phrases are reported rather
than silently erased. Correct input kana are supplied to both recipes; this cannot
measure reading selection. The grouped app-style path and raw phone decoder calibration
above are different measurements.

**Decision:** keep context recovery offline. It meets the commercial recovery-count
threshold but supplies zero affected human-reference units, failing the required sample
size of fifty units over ten distinct phrases. Do not mask correct baseline words or
lower thresholds to manufacture a qualifying result. The reserved PJS pool was subsequently
opened for the frozen raw-phone run above; no context candidate was promoted with it.
Fixtures cover repeated source spans, exact sample origins,
original crop bounds, conflicting proposals, weak/wrong-verse evidence and score abstentions.

## Reproduction

Models and private inputs are never downloaded by hooks or unit tests. The diagnostic
manifest contains `cases`, `diagnostics`, `results: [{track, path}]`, `crop_provenance`
and optional `rust_manifests` paths. Outputs require a fresh directory outside git.

```sh
python3 scripts/diagnose-song-suite.py /path/to/private/manifest.json \
  --output /path/to/private/fresh-diagnostic
```

Export app windows explicitly using a private document, its recording, a bundled
romanizer and a fresh output directory:

```sh
ROMAJI_TEST_DOCUMENT=/path/to/private/document.json \
ROMAJI_TEST_PCM=/path/to/private/audio.pcm \
ROMAJI_TEST_MANIFEST_DIR=/path/to/private/fresh-crops \
ROMAJI_HELPER_PATH=/path/to/RomajiRomanizer \
cargo test --locked --no-default-features recorded_song_exports_rust_crop_manifest \
  -- --ignored --exact study::alignment::tests::recorded_song_exports_rust_crop_manifest
```

The PJS private root contains `audio.zip`, `labels.zip`, extracted `audio/<id>_song.wav`,
`labels/<id>.lab`, and `split.json` with disjoint `development` and `heldout` ID lists.
Recipes are a JSON map from names to TIFA skip penalties. Run `--partition development`
first; use `freeze` with a new output directory before a heldout `run --receipt ...`.
Both commands need `--archive`, `--recipes` and `--output`.

The small-vowel mix pilot recovered three words and lost none, but moved five shared
intervals by >150 ms; broad replacement is unsuitable. The vocal trials took 60.5 seconds
(Kim) and 54.4 seconds (Demucs), with process lifetime peak RSS about 0.91 GB each.
A targeted replay joined all 671 source/audio/crop identities in each view to the saved
Experimental result. Both independently checked views recovered the same one word in
色彩 and adjusted one neighboring interval through the existing bounded repair policy.
The other two gaps remained withheld. The native integration above confirms the same
one-word gain and bounded neighboring adjustment. The context, repeat and English
challengers remain offline.

The pre-existing pyshiro adapter is not a new result. Checkpoint terms/provenance remain
unresolved for its v2 model and the Intunist models, so this work adds neither runtime
nor weights. No passing general-recovery recipe is claimed.

The [SingAlign English model card](https://huggingface.co/pymaster/SingAlign) describes a
singing-specific HuBERT alignment head with separate encoder weights and CC-BY-NC-SA
terms. Its linked toolkit source is unavailable, and bundled TIFA's SSL inference class
is a stub with a different feature/model contract. It is deferred rather than treated
as a compatible checkpoint. [NUS-48E](https://smcnus.comp.nus.edu.sg/) supplies the
private human English-singing phone/word references used in the verifier pilot below.
Its linked corpus README explicitly restricts use to research. Two small audio/annotation
pairs have now been acquired privately; none enters git or the app. The human annotations
contain CMU phones and zero-duration `sp` word markers, rather than gold orthographic
transcripts. An English grapheme verifier must not manufacture its gold words from ASR.

## Independent English verifier pilot

The pinned [XLSR eSpeak phoneme checkpoint](https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft)
is an Apache-2.0 speech model trained with Common Voice phone targets, rather than a
singing recognizer. Revision `3e836924cfd3b858a0bbdbc1f7ef412105d00446` has a
1.26 GB FP32 weight file. `scripts/english-ctc-model-files.json` records exact sizes and
SHA-256 hashes; `scripts/benchmark-english-phones.py` verifies them before offline loading.
It bypasses the eSpeak tokenizer and maps human CMU phones to the checkpoint's IPA
inventory using an explicit [en-US crosswalk](https://github.com/cmusphinx/cmudict-tools/blob/master/accents/en-US.csv).
Unmapped `ER` rejects a whole phrase; stressless `AH` uses canonical `ʌ` rather than
guessing its schwa realization. These are known mapping limits.

The research-only NUS pilot uses ADIZ song 01 for development; JLEE song 05 remains
reserved with hashes frozen, without parsing its labels or running inference. Neither
audio nor annotations are distributed. Both have human singing annotations; automatic
annotations for the spoken renditions are not used.

| ADIZ development measurement                       | Reference units | Accepted | Within onset ≤150 ms and offset ≤200 ms |
| -------------------------------------------------- | --------------: | -------: | --------------------------------------: |
| Complete forced phone paths                        |             146 |      109 |                          67/109 (61.5%) |
| Phones with mean probability ≥0.45                 |             146 |       57 |                           52/57 (91.2%) |
| Human `sp` word groups with mean probability ≥0.45 |              37 |       17 |                           10/17 (58.8%) |

Two of twelve phrases were unsupported. The word groups have human boundaries but no
gold spelling, so this measures supplied-phone timing rather than lyric recognition.
Decoding took 1.5 seconds after loading, with lifetime process peak RSS 0.66 GB;
the separate MPS driver-allocation sample at the end was 2.24 GB. These counters
are not added or treated as total unified-memory use.
**Decision:** reject app integration. The pilot fails the timing gate and is too small
to certify a new mixed-language recovery path. No heldout result was opened to rescue
it. Both the checkpoint and its English reference data stay outside the app.

## Weak-repeat localization pilot

`scripts/experiment-repeat-windows.py` found **21 weak repeated occurrences with 39
missing Japanese words across eight songs**. Each matches a fully timed occurrence's
original text and word readings in the same recording. English spans and previously
corrected reading lines are excluded. Nomination uses exact existing lyric occurrences,
so this bounded pilot does not need whole-song chroma retrieval.

Fresh MMS vocal posteriors, with the actual blank channel removed, provide cosine DTW
features with band radius 0.25. Duration ratios outside 0.5–2 are rejected. Target-audio
RomajiASR independently checks complete mixed mora/phone paths and word endpoints;
tokens cannot cross source-word boundaries, and interior phone times are never divided.
Accepted proposals must be within 150 ms at both endpoints, then survive a fresh TIFA
alignment in a ±300 ms window, original crop bounds and unchanged supported neighboring
anchors. Conflicting new intervals are rejected together without trimming them.

The pilot added **zero words**: five proposals failed DTW bounds/distortion, 27 failed
independent target support/coherence, and seven failed fresh realignment. It took
27.4 seconds after input verification, with lifetime peak RSS 0.95 GB. Input, model,
runner and mapping hashes are recorded privately. **Decision:** keep the experiment
offline; it supplies neither recovery gains nor relevant affected reference cases.
Whole-song relocation is not justified by this result.

## Next bounded hypothesis

The dominant unresolved class is mixed-language pronunciation: 404 missing spans contain
Latin letters, while whole-song language detection still chooses Japanese. The attempted
speech IPA verifier is inadequate for sung word boundaries. The next useful experiment
is a singing-specific multilingual phone recognizer, rather than another vote between
the same transcription models. First obtain a usable alignment checkpoint and its exact
encoder contract, or adapt a small phoneme CTC head on eligible labelled singing data.
Resolve checkpoint/data terms and singer/song separation before training; do not train on
the private commercial test recordings. Freeze English/Japanese phone mappings, reserve
new human-labelled songs, and compare accepted word groups against the same boundary,
abstention and negative-control gates before integrating it. Runtime feasibility on
16 GiB is a separate measurement, not inferred from checkpoint size.

The reserved JLEE English reference remains available for a future frozen test. PJS's
twenty-song pool has already been opened; reserve different data for new tuning claims.
Additional commercial recordings are not currently available, so the ten-new-song
robustness milestone is deferred and no unfamiliar-song accuracy claim is made.

## Negative controls

`scripts/check-phonetic-controls.py` explicitly runs the small-vowel fallback and the
offline context policy against synthetic silence, a fixed five-tone instrumental signal,
and an unrelated PJS singing excerpt. Each control has two synthetic Japanese target
lines including a same-vowel small-kana spelling. **All three admit zero new words**
through either recovery operator. The spelling fallback proposes no reading changes.
These are focused recovery tests, not a measurement of false positives across arbitrary
music or the entire pre-existing transcription pipeline.
