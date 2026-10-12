# Sung-reading evaluation: first recipe

The Experimental action can now save supported sung-reading corrections before freshly
aligning them. TIFA keeps its original timing-only path. The recipe is deliberately
conservative: unmatched or contradictory evidence retains the selected lyrics.

## What was tested

Dictionary calibration replay covered fourteen local songs, 671 ordinary lyric crops,
and thirteen wrong-verse controls. Contextual and exact-envelope N-best paths supplied
1,323 ambiguous source groups. All fourteen songs were used for calibration; none is
reported as held-out. The stricter final gate retained all six user-verified Tabi reading
occurrences and admitted no correction on the dictionary wrong-verse controls.

The verified readings are 闇夜 → やみよ, 行こう → ゆこう, and ハッカ色 → はっかいろ.
Independent singing-phoneme evidence strongly supports the first and third. It is
approximately tied on 行こう, so the recipe treats that as uncertainty rather than
confirmation; both MMS views still have to pass their full acoustic gates.

Short Whisper crops sometimes hallucinated unrelated closing phrases. Full-song blind
transcription worked better and is now used on the Kim vocals and original mix. Its
text is a candidate source, never a license to rewrite lyrics by itself. Examples such
as 想い → そうい and 誰 → たれ were rejected by the independent recognizer or stricter
absolute probability gate.

A separate lexical check used four JSUT recordings, with three yielding ten eligible
phrases. Blind full-context transcription had to match the parallel HTS score phone
sequence before inclusion. The frozen policy changed none of 39 baseline-correct word
occurrences and repaired 20 of 39 intentionally substituted dictionary readings, with no incorrect
replacement admitted on those injected-error cases. The remaining nineteen abstained. These
are artificial error controls, not 39 naturally occurring dictionary mistakes. Repeated
words and phrases are correlated; no general precision estimate follows from this sample.
Score-derived timestamps were never used as performance timing ground truth, and
melismatic repeated vowels were collapsed only for lexical reference matching.

## Packaged acceptance

Tests use previously captured recordings and private temporary documents; they do not
replace the listener's saved song files or require another Spotify login.

| Recording      |                      Automatic reading repairs | Retained word timing | Processing time |
| -------------- | ---------------------------------------------: | -------------------: | --------------: |
| Tabi no Tochuu |                         6 verified occurrences |              153/153 |        192.54 s |
| departure!     | 3 candidates: 行け → ゆけ, 明日 → あした twice |              209/221 |        184.39 s |

Both runs used the standalone packaged Experimental and romanizer executables. They
validated fresh source-span timing, kept every earlier version, saved the generated
result and complete document, and reopened both. This is model and persistence acceptance.
The newly identified departure! readings and both recordings' new intervals still need
a fresh listening check; departure!'s remaining twelve untimed words are withheld.

Hardware was an Apple M2 Pro with 16 GiB unified memory. The Tabi test reported a maximum
resident set of 3.50 GB; that counter is not a measurement of all unified GPU allocations.
The separate full-song Whisper trial peaked at approximately 4.06 GB of MLX allocations.
Models run sequentially and release their caches between phases; these separate maxima
must not be added or presented as a measured whole-job memory peak.

## Reproducing without publishing song data

`bash scripts/check.sh` runs the recorded-free protocol, span, repeat, acoustic-rejection,
legacy-data and persistence regressions. Package checks exercise relocation, restricted
PATH, Metal inference imports, and Experimental launching its bundled romanizer.

`scripts/experiment-sung-readings.py` replays the same `reading_repair.propose` policy
from explicit local JSON/NPZ inputs. Its manifest documents the frozen conversion
requests, crops, two MMS posterior views, independent phoneme evidence and blind
transcriptions. It writes proposals to a private output and never writes app data.
The ignored Rust recorded-song acceptance test additionally checks the complete pipeline,
version preservation and reopening. Neither mode downloads song audio during tests.

Audio, full lyrics, private evidence, model weights and personal tools are excluded from
public source and git history. The app downloads hash-pinned weights once; the runtime
and model notices are retained with the bundle.

## Limits and references

This first recipe supports bounded reading corrections and independently corroborated
kana-only text substitutions. It withholds arbitrary kanji rewriting, unsupported or
incomplete spans, edits that would displace existing corrections, and conflicting repeat
readings. More yellow words do not prove better lyrics or audible alignment. Difficult
songs and independent fresh listening remain useful acceptance cases.

Primary corpus documentation: [JSUT-Song author page](https://sites.google.com/site/shinnosuketakamichi/publication/jsut-song).
It describes the recordings as parallel performances of songs from HTS, rather than
recordings with measured lyric durations, and limits redistribution. The recordings
and score files used here remain private.
