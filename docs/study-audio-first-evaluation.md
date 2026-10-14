# Audio-first sung-reading pilot

Measured on 2026-10-13, on an Apple M2 Pro with 16 GiB unified memory. This implements
the offline deliverable of the [audio-first plan](plans/audio-first-readings.md).

**Decision: keep this path offline.** Blind RomajiASR pronunciation recognition beats
Whisper → Cutlet on the labelled clips. A fixed current-core-first fallback restores
19 additional injected reading errors, with accurate fresh TIFA intervals in this corpus.
It also adds two wrong repairs. Natural-song discovery and complete app validation have
not established a passing replacement or extension to Experimental. The app buttons,
saved versions and released timing recipe therefore keep their existing behavior.

## What was tested

The new path starts with audio, not a dictionary-selected lyric reading:

```text
cached vocals → blind phones/kana → original-source word envelope
              → bounded kana candidates → independent MMS admission → fresh TIFA
```

- RomajiASR uses the existing pinned singing HuBERT checkpoint, MPS FP32, greedy or
  prefix beam width 32 / N-best 8 / token prune 16. No lyrics, language model, insertion
  penalty or length bonus enters decoding. Mixed mora and phone tokens retain normal
  CTC repeat rules; equivalent decoded phone sequences are deduplicated.
- A separate speech-trained hiragana CTC model was tested in FP32. Its kana and auxiliary
  phone heads share an encoder. FP16 failed with nonfinite outputs on all seven smoke
  clips, so it was excluded from the larger runs. It is an optional research checkpoint,
  not an app download.
- Whisper large-v3 gets the identical audio, Japanese language, temperature zero, no
  prompt and no previous-text conditioning. Raw transcripts are saved before conversion.
  The bundled Cutlet converter uses a synthetic track identity, disabling song defaults.
- Source attachment happens after recognition closes. It requires complete original
  UTF-8 word ownership, unique two-phone anchors on both sides and coherent monotone
  matching. Interior phone edits may combine into a whole reading; line edges, inserted
  lyric words and ambiguous attachment remain withheld. Homophonic spellings remain
  candidates, with a unique closest source spelling required before admission.

The source mapper also tests a dictionary pronunciation shadow from the existing
Fugashi/UniDic `feature.pron`, using the converter's original node spans. `pronBase` is
excluded because it can discard inflection. Written kana and display words stay intact:
`行こう` remains `いこう`, while its dictionary acoustic representation can be `いこー`.
This is lexical: `光景` becomes `こーけー`, but `思う` and `子牛` retain their `う`.
There is no global `ou → oo` rule, kanji round trip or timing from decoder spikes.

## Blind pronunciation recognition

The [PJS singing corpus](https://sites.google.com/site/shinnosuketakamichi/research-topics/pjs_corpus)
and [human monophone labels](https://github.com/UtaUtaUtau/pjs-manual-labels) provide the
reference. The manual labels are CC BY-SA 4.0. Original full mono vocals are used,
resampled from 48 to 16 kHz. Recognition never receives these labels.

The common supported cohort is 67/80 development clips (4,506 phones) and 18/20 replay
clips (1,291 phones). Thirteen development clips / 942 phones and two replay clips /
143 phones are omitted because their labels contain undocumented `I`, `U` or `O`
conventions unavailable in the shared inventory. `cl` is retained. Unknown predictions
are errors; missing predictions would count as deletions. These exclusions apply equally
to the compared models, and are not coverage on all Japanese pronunciations.

| Decoder                            | Development errors / phones | Phone error rate | Replay errors / phones | Phone error rate |
| ---------------------------------- | --------------------------: | ---------------: | ---------------------: | ---------------: |
| RomajiASR greedy                   |                   276/4,506 |            6.13% |               76/1,291 |            5.89% |
| RomajiASR beam                     |                   271/4,506 |            6.01% |               76/1,291 |            5.89% |
| Whisper → written Cutlet kana      |                   609/4,506 |           13.52% |              135/1,291 |           10.46% |
| Whisper → dictionary pronunciation |                   564/4,506 |           12.52% |              109/1,291 |            8.44% |
| Hiragana CTC greedy                |                 1,001/4,506 |           22.21% |             Not tested |                — |
| Hiragana CTC beam                  |                 1,035/4,506 |           22.97% |             Not tested |                — |
| Auxiliary phone head greedy        |                 1,236/4,506 |           27.43% |             Not tested |                — |
| Auxiliary phone head beam          |                 1,010/4,506 |           22.41% |             Not tested |                — |

Beam RomajiASR has **52.0% fewer development errors and 30.3% fewer replay errors** than
the dictionary-pronunciation Whisper baseline. The earlier 55.5% / 43.7% reductions used
written kana and overstate that comparison. The authenticated Whisper reruns reproduced
all original decoded phone outputs exactly; the ablation changes dictionary conversion,
not the recognized transcript. Beam versus greedy adds little here: four exact full
development clips for each, and zero versus one exact replay clip.

The twenty replay labels had been opened in previous work. Decoding was fixed before
replay scoring, but replay inference had already started before its receipt was written.
Pronunciation and reconciliation refinements followed that replay. This is a development
comparison and stability check, not a new unseen holdout. Training disjointness from
either corpus/model is unverified. Phone error rate is not exact word, kana or lyric accuracy.

## Source repair and fresh timing

Official source sentences come from the pinned
[Voice Actress sentence file](https://github.com/voice-statistics/voice-statistics.github.com/blob/22923912010c358a4a044702e78b343f3ba8123f/assets/doc/balance_sentences.txt),
under CC BY-SA attribution. PJS per-song `.txt` files contain musical metadata, not lyrics.
The parser rejects that metadata. The frozen challenge contains 390 uniquely mapped
interior word envelopes across 62 development songs. Their source phones must match
the human reference and neighboring context exactly. This favors clean, supported words;
it does not cover every corpus word or the six natural Tabi errors.

For each envelope, a deterministic first-vowel cycle creates a faulty copied candidate
reading. The recording and references never change. The same 390 envelopes also run
unchanged as controls; neither the recognizer nor fallback priority sees the truth label.
These are kana faults, not 390 naturally wrong provider lyrics or saved user edits.

Admission uses the existing MMS gain/margin/probability/coherence rules on original
PJS vocals and a genuine Kim-derived view. These are correlated views of one recording.
RomajiASR's own full-sequence score is a proposer-confidence check, not a second model
vote. Eight hypotheses and a four-log-unit own-score margin are development settings.

| Method                                  | Admitted repairs | Phone-correct | Wrong | Changed unchanged controls |
| --------------------------------------- | ---------------: | ------------: | ----: | -------------------------: |
| Current single-word repair core         |              137 |           136 |     1 |                      0/390 |
| Whisper + same source reconciler        |              138 |           137 |     1 |                      0/390 |
| Blind beam + pronunciation shadow alone |              139 |           137 |     2 |                      0/390 |
| Current core, then blind on abstentions |              158 |           155 |     3 |                      0/390 |

The fallback retains every current-core admission, then adds 21: **19 phone-correct
repairs across 13 songs and two wrong repairs**. There is no truth-based winner selection.
For comparison, written-source N-best mapping alone admitted 139 correct / two wrong;
the pronunciation shadow traded two of those controlled recoveries for better natural
Tabi attachment. Top-one blind proposals without own-score filtering changed two correct
controls; that unsafe configuration was rejected.

This comparator replays the existing single-word dictionary/transcript selection and
verification core. Its singing evidence is from original PJS vocals; the complete app
uses its separate production audio workflow. It does not test full-song lyric substitution,
native persistence, repeat conflicts or all production proposal stages.

Fresh TIFA runs used admitted readings and original audio; no reference phones or borrowed
timestamps entered alignment. All 137 core and 158 fallback admissions retained timings.
The human first/last phone boundaries define each evaluated word envelope.

| Measurement                                   | Current core | Core then blind |
| --------------------------------------------- | -----------: | --------------: |
| Correct reading + onset ≤150 ms + end ≤200 ms |      136/137 |         155/158 |
| Joint fraction of all admissions              |       99.27% |          98.10% |
| Phrase-bootstrap descriptive 95% interval     | 97.62–100.0% |    95.76–100.0% |
| Median onset error, correct timed readings    |      3.74 ms |         3.81 ms |
| Median offset error, correct timed readings   |      4.87 ms |         4.86 ms |

All 137 common admissions have identical freshly computed intervals; the 19 additional
correct repairs also meet both timing tolerances. Their candidate inputs coincide where
the fallback retains the core, so identical common timing is expected, not independent
confirmation. Fifty-four distinct full-line target sequences were aligned, with identical
targets cached within the job. The very small boundary errors on these selected clean
vocals do not establish similar performance on commercial mixes. The bootstrap clusters
by recording, counts withheld timings as failures, and is descriptive rather than a
population guarantee. Original eligible-source denominator remains 390.

## Natural songs

All 671 cached Kim lyric windows on fourteen recordings completed blind RomajiASR
recognition without an out-of-memory failure. Original Rust crop bounds and recording
hashes were checked; no new capture or Keychain prompt was needed. The canonical source
denominator remains 4,160 words. Counts below are candidate envelopes across up to eight
beam hypotheses, deduplicated within a crop. Multiple alternatives can name the same
word; these counts are neither coverage gains nor correct accepted repairs.

| Recording            | Source words | Candidate envelopes |
| -------------------- | -----------: | ------------------: |
| SAKURA               |          265 |                  65 |
| うれしくて           |          423 |                  44 |
| departure!           |          221 |                  18 |
| spiral               |          245 |                  81 |
| Koino Uta            |          307 |                  63 |
| Tabi no Tochuu       |          153 |                  42 |
| NEVER SAY GOODBYE    |          430 |                  50 |
| Just Awake           |          306 |                   9 |
| the WORLD            |          153 |                  48 |
| 色彩                 |          291 |                  82 |
| 君のせい             |          270 |                 114 |
| 今世大革命           |          246 |                  56 |
| Bling-Bang-Bang-Born |          473 |                  45 |
| 天天天国地獄国       |          377 |                  38 |

With earlier automatic defaults disabled, written-source top-one mapping attached one
verified Tabi candidate (`yamiyo`). Dictionary pronunciation plus N-best attaches three:
`yamiyo` and two of the four `yukou` occurrences. Two `yukou` occurrences remain unanchored,
and line-edge `hakkairo` is withheld. Independent admission and combined current-core
fallback were not evaluated on these commercial candidates. Existing Experimental already
recovers all six verified occurrences, so three candidates are not an app improvement.

## Runtime and memory limits

Models ran sequentially with cached weights. Times include startup, inference, decoding
and writes for the named recognition jobs, excluding stem preparation and downloads.

| Job                                  | Seconds | Peak process RSS | GPU allocation measurement |
| ------------------------------------ | ------: | ---------------: | -------------------------: |
| RomajiASR, 80 development clips      |    48.4 |         0.53 GiB |           2.07 GiB sampled |
| Hiragana CTC, 80 development clips   |    93.6 |         2.17 GiB |           2.09 GiB sampled |
| Whisper, 80 development clips        |   148.6 |         0.88 GiB |              3.68 GiB peak |
| RomajiASR, 20 replay clips           |    15.8 |         0.59 GiB |           2.06 GiB sampled |
| Whisper, 20 replay clips             |    39.4 |         1.15 GiB |              3.69 GiB peak |
| RomajiASR, 671 commercial windows    |   120.2 |         0.93 GiB |           2.08 GiB sampled |
| Kim + paired MMS, 62 PJS recordings  |   495.4 |         0.98 GiB |               Not measured |
| Fresh TIFA, 54 distinct target lines |    11.8 |         0.88 GiB |               Not measured |

RSS is the runner's lifetime counter, not aggregate process-tree RSS. PyTorch values
sample MPS driver allocations after inference, missing transient peaks; Whisper uses
MLX's peak allocation counter. These counters overlap unified memory and must not be
added. Swap and background load were not sampled. Successful cached inference is weaker
than a fully profiled combined native job, so the complete memory gate is unestablished.

## Reproduction and provenance

Use the existing `.venv`, `.venv-tifa` and `.venv-experimental` environments. Inputs,
audio, texts, posteriors, per-word proposals and ledgers stay outside git with private
permissions. Only synthetic tests, tools and this aggregate report are public.

1. Prepare an audio-only manifest: `version: 1`, with cases containing only `id`, `path`,
   `sha256`, `encoding` (`pcm` or mono WAV), `first_sample`, `last_sample`. Bounds are
   relative to 16 kHz resampled audio. Reuse Rust-exported commercial bounds.
2. Run `recognize-singing-phones.py` with `--engine romaji`, cached `--models` and a fresh
   private `--output`. Kana additionally needs its pinned `--kana-source` checkout/assets.
3. Run `transcribe-singing-baseline.py` on the same manifest, with `--models`, the packaged
   `--romanizer`, and a fresh output. Record hashes authenticate raw transcripts too.
4. After recognition closes, export an id→text dictionary shadow using `.venv/bin/python
scripts/export-pronunciation-shadow.py`, `--signature` from that exact converter and
   a fresh private `--output`. Source and transcript text maps must be separate.
5. Use `rephoneticize-transcript-baseline.py` for the transcript pronunciation ablation;
   then `evaluate-singing-recognition.py --pjs ... --runs ... --output ...` for PJS phones.
6. Freeze cases with `benchmark-reading-reconciliation.py`; reuse them with `--reuse-cases`,
   `--hypotheses 8` and optional `--shadow`. Supply pinned `--sentences` and authenticated
   Romaji/Whisper runs. `capture-reading-verifier.py` computes original/Kim MMS evidence;
   `evaluate-reading-verifier.py --proposer-margin 4` performs admission and fixed fallback.
7. `time-reading-admissions.py` freshly aligns admitted PJS readings with the pinned
   TIFA archive. `audit-song-reading-proposals.py --hypotheses 8 --shadow ...` audits
   commercial source candidates separately. Each command's `--help` lists input paths.

Corpus archives are SHA-256 `683c00253ee35a62d50de0375bb9d8e003a74338d4ce3495ac3f7ad096abc1ca`
(audio) and `ae8d28e45e5be8642873196f3899485174078a832ded8e95d1b67832ab444c3f` (labels).
Official sentences use revision `22923912010c358a4a044702e78b343f3ba8123f` and SHA-256
`1ed75aba2a0d3548f548ee4a8afd00cfd4cff37de5620424112f745d9e4e31a6`.
Model/source pins are in [audio-first-model-files.json](../scripts/audio-first-model-files.json),
existing `SINGING_FILES`, and the runtime manifests. The converter signature was
`e8e6df0921be4ce777759acefd6d9142767ef524a1849d200813db99f3b5a526`.

Selected private artifact SHA-256 receipts:

| Artifact                         | SHA-256                                                            |
| -------------------------------- | ------------------------------------------------------------------ |
| RomajiASR development recipe     | `481cb9234f438b3f1b0ed68e994a5056e0035211f631c83d068129edd0faf736` |
| Kana development recipe          | `cdde7f04fe844920acf4adabde42f435bbfebf0cbf418c623a52ed6a28cee41e` |
| Whisper authenticated recipe     | `56d2ff0621c478ba93be2f08d60e500c31bf5843dfc0140c705143fb3b6ab25b` |
| Frozen 390-case challenge        | `a897ab21f71c64f329f3f18d2b7fd89ad5a65f76c199071e779b62e763bd4cb1` |
| Development pronunciation scores | `c6a853bc93cef3a30383e88f6cdf1b81f8371a134d72917f719679f324bc7feb` |
| Replay pronunciation scores      | `1489c3dda466c01efdb2a42d0ac7bc2798c8f447e15ebddddfc8df9de42d9ed0` |
| Final fallback admission summary | `00297ee9c4ce01e1037919e5093dc7049d0ffee0c97f1d52927d0f6f7e1d43a2` |
| Fresh TIFA timing summary        | `4e0a1883d6ea962b62614d7e4b8d5d7d6baaccc75b1325936ac31b1c3ca7af7f` |

Each run stores its exact implementation/asset/decoder identities; early inference
receipts precede later mapper fixes and final source formatting. They are not claimed
to be runs of the final PR commit. Final tools replay the authenticated raw predictions;
the authenticated Whisper rerun and fresh admission/timing records identify their own
versions. The NumPy offline MMS path acceleration is regression-tested against the
unchanged production dynamic program, including ties and repeated labels.

## Next hypothesis

Recognition is stronger than safe attachment and verification. Continue with independently
tested long-vowel/held-note attachment and whole-envelope line-edge mapping, then replay
the fixed fallback on natural songs through the complete production evidence and persistence
path. A vowel held longer cannot authorize changing its spelling, and absent consonants
cannot be invented to recover `hakkairo`. Better benchmark counts alone should not enable
the new app path. English singing and broad kanji/text rewriting remain separate work.
