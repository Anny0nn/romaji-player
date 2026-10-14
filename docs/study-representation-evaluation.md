# Japanese script and reading representations

This change adds Katakana and original Japanese to the persisted study modes, sharing
the existing source groups and timings with romaji and hiragana. The version-2 converter
exports an explicit selected-reading record and an optional dictionary pronunciation.
The reading contract fixes representation ownership; it does not establish that every
dictionary reading matches the singing.

## Frozen source comparison

The merged PR #3 baseline contains **3,507/4,160 retained groups** in fourteen songs
and 671 recorded lyric windows. All earlier output text, original byte envelopes,
word grouping, hiragana/romaji spans and applied corrections are identical after
reconversion under the new protocol: **0/671 changed legacy outputs**. Source-owned
timings reattach without using positions in romaji. All **4,160 model targets** also
pass the new Python boundary validation without changing a valid target.

Of the 653 remaining groups, **376 contain Latin letters**, **276 are kana-only**,
and one is neither. All have an exact conversion group; none differ from the frozen
selected kana, and three are in a crop at the 30-second limit. Agreement with an earlier
dictionary reading is not evidence that the singer uses it. These structural categories
do not identify which words are actually sung or prove that the remaining Japanese
readings are correct; acoustic and lyric-mismatch causes remain unclassified here.

## Paired pronunciation trials

Two runs use the same frozen audio, crop bounds, source/edit revisions, original
denominator and independent audio-only RomajiASR posteriors. Both obtain fresh TIFA
intervals and apply the shipped singing-recovery gates. The written-reading control
adds **0 words**. Eligible inflected dictionary pronunciation changes 55 missing targets
and adds **2 words**, both in 今世大革命, taking that song from **197 to 199/246**.
The aggregate becomes **3,509/4,160** in the focused trial; every previously retained
interval stays identical. The other thirteen songs keep their previous counts.

The written trial took **12.2 seconds** and the spoken trial **12.1 seconds** on M2 Pro
/16 GiB, after model loading and with cached singing posteriors. These are focused-stage
times, excluding full-song separation, transcription, posterior inference and startup.
The optional dictionary pronunciation affects acoustic hypotheses only. It leaves the
written lyrics, romaji and saved sung corrections unchanged, and introduces no weights.

A separate canonical-kana trial explicitly retains `ー` and adds **0 words** in
**12.9 seconds**. Its targets are identical to the control: Unicode classifies the
long-vowel mark as a letter, so the existing alphanumeric filter already retains it.
Twelve source groups contain that mark, including two missing groups. This rejected
normalization hypothesis does not justify a production target change.

The new Katakana mode itself supplies no new acoustic evidence. The MMS checker still
receives compatible Latin labels, TIFA uses kana/phonetic targets, and the independent
singing model uses phones. Display selection never changes their inputs. The converter
compatibility control also leaves existing MMS label spelling unchanged. Protected
alternate readings are retained and freshly consumed by the normal repair workflow;
the rejected blind reading pilot is not adopted.

## Regression gates

With pronunciation targets enabled, the exact runtime fallback admits **0/105 words**
on fifteen Japanese wrong-verse, silence and instrumental controls, and **0/38 words**
on seven English-heavy wrong-verse controls. The frozen human PJS benchmark remains
**390/390 retained**, with **389/390** meeting onset error ≤150 ms and offset error
≤200 ms. No retained interval changes. Hiding the known timing envelopes before
inference recovers **138/390**, all **138/138** within those limits, matching the prior
recipe. These development and artificial-gap checks do not establish the accuracy of
the two new commercial-song intervals or an unseen-song success rate.

## Native and package acceptance

Both standalone timing runtimes completed native replay on all fourteen cached
recordings. Original TIFA remains **3,121/4,160 (75.0%)**, with every interval identical
to PR #3. Experimental reaches **3,509/4,160 (84.4%)**, adding two words while losing
or moving **zero** previously retained intervals. The original source snapshots and
denominator remain unchanged. All fifteen automatic reading occurrences and the six
verified Tabi corrections retain their exact source anchors and canonical readings;
no new reading or lyric-text repair is introduced by this fallback.

| Recording            |   Original TIFA | PR #3 Experimental | New Experimental | Added |
| -------------------- | --------------: | -----------------: | ---------------: | ----: |
| SAKURA               |         263/265 |            265/265 |          265/265 |     0 |
| うれしくて           |         340/423 |            363/423 |          363/423 |     0 |
| departure!           |         204/221 |            209/221 |          209/221 |     0 |
| spiral               |         228/245 |            238/245 |          238/245 |     0 |
| Koino Uta            |         198/307 |            252/307 |          252/307 |     0 |
| Tabi no Tochuu       |         150/153 |            153/153 |          153/153 |     0 |
| NEVER SAY GOODBYE    |         341/430 |            369/430 |          369/430 |     0 |
| Just Awake           |         178/306 |            183/306 |          183/306 |     0 |
| the WORLD            |         116/153 |            135/153 |          135/153 |     0 |
| 色彩                 |         237/291 |            271/291 |          271/291 |     0 |
| 君のせい             |         220/270 |            259/270 |          259/270 |     0 |
| 今世大革命           |         154/246 |            197/246 |          199/246 |     2 |
| Bling-Bang-Bang-Born |         303/473 |            348/473 |          348/473 |     0 |
| 天天天国地獄国       |         189/377 |            265/377 |          265/377 |     0 |
| **Total**            | **3,121/4,160** |    **3,507/4,160** |  **3,509/4,160** | **2** |

All **28 saved action results** passed native reopening, reconversion, original-script
and katakana span checks, and earlier-version restoration. Offline fixtures additionally
cover migration from the old three-mode settings, persistence of all five modes,
highlight layout, protected edits, nonzero delay, cancelled/stale jobs and ambiguous
source ownership. Tests use isolated data directories and do not alter the user's saved
song data. The replay resumed from authenticated completed receipts after a pause;
fresh acoustic scores showed small quantization differences on two saved corrections,
without changing any canonical reading or interval.

On M2 Pro /16 GiB, cached-weight native processing took a median **167.8 seconds
Experimental** (range 143.9–263.7) and **6.5 seconds TIFA** (range 5.2–12.2).
Largest recorded command/child maximum RSS was **3.16 GB Experimental** and
**1.49 GB TIFA**. These observations are not a simultaneous process-tree or full
unified-memory peak; accelerator allocations and first-download latency were not
remeasured. All jobs completed without an out-of-memory failure. The latency difference
from PR #3's shared-machine run is not attributed solely to this change.

The standalone app and ZIP have been rebuilt and passed relocation acceptance: ARM64,
signing, public build configuration, notices, clean-environment converter/runtime checks,
and a path with spaces. The `--check-romaji` smoke entrypoint now uses the current
converter protocol and has a real-helper regression test including katakana and raw spans.
The full mandatory repository gate passes, including formatting, lints, helper boundary
tests, source/display mapping, persistence, layout and public-export checks. The
implementation is `3a2ea42`, staged runtime packaging is `15c6834`, and the app smoke
protocol fix is `78f7f17`. The two new commercial-song intervals still require a
listening check; retained coverage is not a correctness score.

## Reproduction

`scripts/check-reading-representations.py` compares the new converter with an explicit
private frozen conversion file. `scripts/experiment-reading-representations.py` accepts
a private suite manifest, validated conversion records, authenticated audio-only
recognition, its audio manifest and the pinned TIFA archive; run both `--policy written`
and `--policy spoken`. The existing singing-gap benchmark and negative-control runners
accept `--pronunciations` for source-matched dictionary shadows. Reports retain input
hashes and write lyric-bearing details outside the checkout. Routine repository checks
use synthetic protocol, mapping, persistence and layout fixtures without real models,
Spotify or network access. Audio, full lyrics, predictions, references and model files
are not published.
