# Sung-reading evaluation: first recipe

Experimental saves supported sung-reading corrections, then freshly aligns the resulting
lyrics. TIFA keeps its original timing-only path. Unmatched or contradictory evidence
retains the selected reading. This report records the 2026-10-12 merge validation on an
Apple M2 Pro with 16 GiB unified memory.

This remains the original recipe's merge record. The subsequent
[accuracy implementation report](study-accuracy-evaluation.md) records `vowel-extension-v1`
at 3,435/4,160 retained words, its one-word gain, unchanged reading repairs and rejected
broader challengers.

## Fourteen-song comparison

Both packaged actions ran on the same fourteen private documents and recordings.
TIFA retained **3,121/4,160 words (75.0%)**; Experimental retained
**3,434/4,160 (82.5%)**, an increase of 313 words and 7.5 percentage points. All fourteen
recordings improved coverage in this run. Two reached full coverage: SAKURA and Tabi no
Tochuu. These are calibration songs reused during development, not a held-out accuracy
benchmark. Coverage counts display words with accepted intervals; it does not measure
whether a listener hears the correct word at that interval.

| Recording                                                                     | TIFA words | Experimental words | Reading repairs | TIFA seconds | Experimental seconds |
| ----------------------------------------------------------------------------- | ---------: | -----------------: | --------------: | -----------: | -------------------: |
| [SAKURA](https://open.spotify.com/track/1lTfD2M6UpJRWi3YLb8qb5)               |    263/265 |            265/265 |               0 |         12.2 |                238.6 |
| [うれしくて](https://open.spotify.com/track/25C3HZIvRGGtkasbrZe7D1)           |    340/423 |            363/423 |               0 |         11.0 |                293.3 |
| [departure!](https://open.spotify.com/track/4cH6RfZ1qIuz6sumRoDEGK)           |    204/221 |            209/221 |               3 |          7.4 |                186.0 |
| [spiral](https://open.spotify.com/track/6xAIVrhyFQaHwPVWfUvWvE)               |    228/245 |            238/245 |               2 |          8.1 |                182.2 |
| [Koino Uta](https://open.spotify.com/track/15St0qWPnH4xKflV39vk28)            |    198/307 |            223/307 |               1 |          8.0 |                165.9 |
| [Tabi no Tochuu](https://open.spotify.com/track/6KeWalxT7jDYdNfwiBtBzt)       |    150/153 |            153/153 |               6 |          7.0 |                187.0 |
| [NEVER SAY GOODBYE](https://open.spotify.com/track/1NVQvAvYhYUluRrRQpdCjg)    |    341/430 |            367/430 |               0 |          7.2 |                190.1 |
| [Just Awake](https://open.spotify.com/track/1Gqpa08T7eBAvPQj9O9L2Q)           |    178/306 |            183/306 |               0 |          6.6 |                159.3 |
| [the WORLD](https://open.spotify.com/track/1g0SlTCGN9j3OicWHfSKEn)            |    116/153 |            135/153 |               0 |          5.6 |                150.8 |
| [色彩](https://open.spotify.com/track/1uveEvgKX4irLcp1BUTIFD)                 |    237/291 |            269/291 |               0 |          5.7 |                141.8 |
| [君のせい](https://open.spotify.com/track/7jEwBMtA7gM43NxiuvfF3h)             |    220/270 |            259/270 |               3 |          5.9 |                174.6 |
| [今世大革命](https://open.spotify.com/track/5cDdNqff2mAutAWAM2Zs2c)           |    154/246 |            188/246 |               0 |          6.5 |                149.9 |
| [Bling-Bang-Bang-Born](https://open.spotify.com/track/0kdqcbwei4MDWFEX5f33yG) |    303/473 |            335/473 |               0 |          7.0 |                161.2 |
| [天天天国地獄国](https://open.spotify.com/track/2dkIbR4mudsHg45av3YwxQ)       |    189/377 |            247/377 |               0 |          6.7 |                187.9 |

Experimental saved fifteen new reading occurrences and no lyric-text substitutions.
Six Tabi occurrences match the user's verified readings: 闇夜 → やみよ,
行こう → ゆこう (four occurrences), and ハッカ色 → はっかいろ.
The other nine are model-supported candidates that still need listening confirmation.
Existing corrections and earlier versions were retained. This sample therefore does not
validate the kana-text substitution path on naturally occurring errors; that path has
bounded mapping and rejection regressions in the offline suite.

Difficult recordings remain difficult. Just Awake reaches only 59.8%, 天天天国地獄国
65.5%, Bling-Bang-Bang-Born 70.8%, and Koino Uta 72.6%. The remaining words are withheld;
line highlighting still works. Nothing in this table establishes general reading precision
or word-onset timing error for arbitrary Japanese songs.

### Measurement and persistence

The reported time covers the native inference call, including helper startup, repair and
alignment. Recording capture, initial source conversion and weight downloads are excluded.
Each helper starts afresh with weights already present on disk. There was one successful
measured run per recording/action, so the table gives no variance estimate. Median time
was **7.0 seconds for TIFA** (range 5.6–12.2) and **178.4 seconds for Experimental**
(range 141.8–293.3). Models run sequentially.

The maximum resident-set counter from `/usr/bin/time -l` was 1.93 GB for the TIFA test
commands and 3.18 GB for Experimental. It covers the test command and its children and
may include compilation; it is not total unified GPU memory. A separate full-song Whisper
trial peaked at about 4.06 GB of MLX allocations. These separate maxima must not be added
or presented as a measured whole-job memory peak.

All 28 pipeline runs saved and reopened their generated result and complete document,
retaining the prior bundles. A separate reopening test reconverted every display word,
checked source-to-romaji and source-to-hiragana spans, counted actual highlightable words,
and restored an earlier version without allowing the latest result to overwrite that
selection. These are model, mapping and persistence checks, not a fresh listening pass.
The final package audit passed all 28 reopening checks using the converter embedded in
the app. It verified fourteen paired input identities and all 6,555 generated intervals
against source byte spans and recording bounds.

TIFA's generated recording fingerprint covers mono PCM. Experimental's covers mono
followed by stereo PCM, so the two result fingerprints intentionally differ. Comparisons
use the same original document and mono recording, with the corresponding stereo recording
for Experimental. Counts have identical denominators in this run; future corrections may
change grouping, so comparisons must retain each denominator.

The larger suite exposed a converter mismatch on leading unpronounced wave dashes in a
blind transcription. Assembly validation now matches Cutlet's whitespace trimming while
preserving exact source/display spans. Optional transcription input rejections are
withheld; source conversion and protocol/identity failures remain fatal. Successful earlier
runs were retained, the failed Experimental recording was rerun after the fix, and the
reading-selection thresholds were unchanged. Dedicated regressions and a relocated
standalone fixture cover the failure. Replaying the frozen Tabi evidence with the updated
converter still yields the same six repairs.

## Reading policy and independent controls

Dictionary calibration replay covered fourteen songs, 671 ordinary lyric crops and
thirteen wrong-verse controls. Contextual and exact-envelope N-best paths supplied
1,323 ambiguous source groups. The stricter frozen gate retained all six user-verified
Tabi reading occurrences and admitted no dictionary correction on the wrong-verse
controls. This calibration replay is separate from the complete song pipeline above.

Independent singing-phoneme evidence strongly supports 闇夜 and ハッカ色. It is
approximately tied on 行こう, so the recipe treats that as uncertainty rather than
confirmation; both MMS views must still pass their full acoustic gates. Short Whisper
crops sometimes hallucinated unrelated closing phrases. Full-song blind transcription
worked better and is used on the Kim vocals and original mix. Its text is a candidate
source, never sufficient permission to rewrite lyrics. Examples such as 想い → そうい
and 誰 → たれ were rejected by independent evidence or the absolute probability gate.

A separate lexical check used four JSUT recordings, with three yielding ten eligible
phrases. Blind full-context transcription had to match the parallel HTS score phone
sequence before inclusion. The frozen policy changed **0/39 baseline-correct word
occurrences** and repaired **20/39 intentionally substituted dictionary readings**, with
**zero incorrect replacements** and nineteen abstentions on the injected-error cases.
These are artificial controls, not 39 naturally occurring dictionary mistakes. Repeated
words and phrases are correlated; no general precision estimate follows from this sample.
Score-derived timestamps were never used as acoustic timing ground truth, and melismatic
repeated vowels were collapsed only for lexical reference matching.

Primary corpus documentation: [JSUT-Song author page](https://sites.google.com/site/shinnosuketakamichi/publication/jsut-song).
It describes recordings as parallel performances of songs from HTS and limits
redistribution. Audio, scores and private model evidence remain outside the public repo.

## Reproducing without publishing song data

`bash scripts/check.sh` runs offline protocol, span, repeat, acoustic-rejection, legacy-data,
stale-result and persistence regressions. The current gate passes 1,100 Rust library tests
(with four explicit acceptance tests ignored), all binary/integration suites, 47 romanizer
tests, 34 TIFA/refinement tests and 69 script tests. Package checks exercise relocation,
restricted PATH, inference runtime imports, signing/resources and Experimental launching
its bundled romanizer.

A fresh configured ARM64 app and ZIP passed both standalone helper and relocated app
checks. All 83 existing user study JSON files and the immutable authorized capture helper
were unchanged by validation and packaging. No new Spotify authorization or recording
was needed for this batch.

The [contributing instructions](../CONTRIBUTING.md#testing-models-on-recordings) give the
explicit-input commands for the full pipeline and reopening tests. They do not authenticate,
capture audio or download models. Use private temporary result directories; never point
them at the listener's saved study data.

`scripts/experiment-sung-readings.py` replays the same `reading_repair.propose` policy
from explicit local JSON/NPZ evidence. Its manifest documents frozen conversion requests,
crops, two MMS posterior views, independent phoneme evidence and blind transcriptions.
It writes proposals to a private output and never writes app data. Audio, full lyrics,
model weights, generated bundles and personal tools are excluded from public source and
outgoing history. Model weights download once with pinned hashes; runtime and model
notices remain with the bundle.

## Limits

This first recipe supports bounded reading corrections and independently corroborated
kana-only text substitutions. It withholds arbitrary kanji rewriting, unsupported or
incomplete spans, changes displacing existing corrections, and conflicting repeat readings.
Restoring an earlier uncorrected version allows previously corrected spans to be evaluated
again. More yellow words do not prove better lyrics or audible alignment.

Fresh listening for the newly generated intervals and unverified readings remains pending,
as does fresh login/playback acceptance in the public-port binary. Earlier live acceptance
belongs to the private predecessor. The public binary release, notarization and other
platforms are separate work.
