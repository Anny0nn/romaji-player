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

Native replay was paused at the maintainer's request. Five completed action results
passed reopening and original-script span checks: both actions for 今世大革命 and
Koino Uta, plus SAKURA's original TIFA action. 今世大革命 reaches 199/246 Experimental
with two additions; Koino Uta remains 252/307. Those completed jobs preserve all previous
intervals and canonical sung readings. A fresh acoustic score changed by one quantization
unit in one vocal view; it did not change the saved reading or timing.

The standalone app and ZIP were built, but relocation acceptance currently fails in the
`--check-romaji` smoke entrypoint: it still sends the retired converter protocol version.
That entrypoint must be updated and package checks repeated. The remaining 23 native
actions, final per-song counts and processing measurements are pending. The PR stays
draft until these checks finish; no complete-suite native result is claimed here.

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
