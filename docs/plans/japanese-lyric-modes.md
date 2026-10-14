# Japanese lyric modes and consistent sung readings

Status: Draft

## Goal

Offer five saved study modes: **Romaji**, **Hiragana + romaji**, **Hiragana**,
**Katakana**, and **Japanese** (the original mixed kanji and kana). All modes use the
same source-owned words and saved timings. Investigate whether inconsistent or wrongly
chosen readings account for the remaining timing gaps, and improve that layer where
the cached singing provides evidence.

This PR starts from merged [PR #3](https://github.com/Anny0nn/romaji-player/pull/3),
merge commit `b8e6ca6`. Its baseline is **3,507/4,160 retained words** across fourteen
songs, including 72 additions over the previous Experimental recipe. Preserve those
gains, the fifteen automatic reading occurrences, the six verified Tabi corrections,
saved song versions, and the separate TIFA and Experimental actions. Retained coverage
is not a claim of listening-verified accuracy; see the
[completed evaluation](../study-completeness-evaluation.md).

The first deliverable is the five working modes and a single explicit reading contract.
The second is a paired evaluation of reading representations, followed by integration
of any safe improvement in the same PR. A script switch alone is not expected to raise
coverage, and 100% is an objective to investigate rather than a promised result.

## Approach

### What needs changing

Current timings already attach to the original Japanese source spans. TIFA usually
receives hiragana from Cutlet, whereas the independent MMS checker consumes labels
derived from displayed romaji. Cutlet also determines word grouping through its rendered
romaji. A wrong dictionary reading can therefore affect both paths even when their
timestamps and source anchors are correct.

Known examples separate this from translation: `闇夜` can be read `an'ya` by the
dictionary while the singer uses `yamiyo`; `行こう` can be `ikou` or sung `yukou`.
These require selecting the sung reading. Converting the same wrong reading to katakana
does not resolve it. Other gaps can still come from English, missing or incorrect source
lyrics, crop boundaries, and acoustic rejection.

Respect each model's actual inputs. The pinned
[MMS karaoke checkpoint](https://huggingface.co/NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn/tree/2ab2b5f46539ee284703c281f286b01d2410ee12)
has a Latin vocabulary; its [model card](https://huggingface.co/NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn)
describes Japanese romaji training but does not establish all spelling conventions.
Raw kanji and kana must not be fed into that tokenizer. TIFA's vendored Japanese
converter already normalizes katakana to hiragana. The existing independent singing
recognizer uses phonemes. Keep those interfaces explicit and test normalization instead
of assuming that one script is universally a better model input.

### One reading, several views

Extend the existing conversion output with an explicit reading record per current
source-owned word group; do not introduce another tokenizer. Python owns text
normalization, dictionary analysis, correction application, grouping and all output
span maps. Rust validates the result and owns persistence and job identity.

Each record contains the original `raw_span` and `expected_text`, constituent normalized
node spans, the selected written hiragana, optional spoken-pronunciation kana and its
provenance, and spans into the rendered romaji, hiragana and katakana strings. All ranges
are UTF-8 byte offsets into their named string. Preserve existing group boundaries and
IDs by source snapshot, line occurrence and raw envelope; neither the selected display
mode nor an alignment model may redefine them.

Generate display romaji and katakana from the same selected reading, retaining Cutlet's
contextual particle and joining conventions. Japanese displays the selected snapshot's
exact source text, punctuation and spacing, without reconstructing kanji from a reading.
ASCII words, digits and punctuation stay intact in kana modes; do not invent Japanese
readings for English or unknown kanji. Missing readings remain visibly unavailable,
with the existing conservative mapping behavior.

Written kana and acoustic pronunciation remain separate. For example, `東京` displays
`とうきょう` / `トウキョウ`, while a pronunciation record may contain `とーきょー`.
Particles such as `は` retain their written form and contextual spoken sound. Reuse the
node/source mapping tested by `scripts/export-pronunciation-shadow.py`; use the inflected
pronunciation, never the lemma. Dictionary pronunciation is eligible only when those
nodes still express the selected reading. A saved or acoustically verified correction
must not be overwritten by re-reading its original kanji.

Use an explicit helper protocol revision for these fields, update both callers, and
include the representation policy in conversion signatures and Experimental cache
identity. Validate string boundaries, exact source slices, ordered display spans,
correction ownership and response identity in Rust. No old field silently changes
meaning. The TIFA action keeps its current target fields and behavior; optional spoken
targets are evaluated inside Experimental first.

### Display and storage behavior

Add `Katakana` and `Japanese` to `LyricMode`, preserving the existing serialized
`Romaji`, `Both` and `Hiragana` values and the default for older settings. Keep the
compact mode selector; Hiragana + romaji continues to put hiragana above romaji.
The selected mode persists across relaunches. Switching modes never starts inference,
changes a lyric version, or writes timings.

Each rendered word uses its existing timing and the span for the selected script.
Japanese uses its original raw envelope, including inflection; punctuation between
groups remains unhighlighted. A reading correction containing spaces is still one
highlighted group in every view. If raw envelopes overlap or ownership is ambiguous,
show the original line with line highlighting rather than inventing word subdivisions.
Stored timings remain available in other modes. Avoid showing the auxiliary Original
Japanese line twice when Japanese is the main mode.

A reading-only repair changes derived readings but leaves the kanji source intact.
An actual lyric-text repair creates a new source snapshot using the existing version
workflow. Corrections still apply to identical repeated text within the song, and each
line occurrence retains independent timing.

Adding conversion fields changes the helper signature. Reconvert pinned snapshots and
reattach saved data by exact source identity, not romaji positions. An unchanged reading
and group must retain its exact timing. Ambiguous groups stay on the earlier usable
conversion/version and are flagged through the existing pending-review workflow, not
silently discarded. Do not require manual timing. A new verified reading is freshly
aligned before its reading/timing bundle becomes active; keep the previous bundle
restorable. Cancelling, stale responses and partial migrations cannot replace it.

### Paired reading experiments

Reuse the fourteen cached recordings and all 671 Rust-exported crop windows. Freeze
source snapshots, protected edits, audio bounds, model revisions and PR #3 outputs.
No new recording or model download is required for this first comparison. Private
per-word observations, lyric-bearing ledgers and audio remain outside Git; publish only
aggregate counts, policy versions and reproduction instructions.

First classify the **653 remaining source groups** using existing rejection diagnostics
and a reading comparison: mismatched selected reading; display/model normalization;
source/group mapping; unsupported English; acoustic/bounds rejection; or not sung /
source-text mismatch. Preserve an unknown category rather than calling every gap a
romanization error. Report classification evidence and overlap instead of adding
overlapping categories into a false total.

Then compare these fixed inputs on identical audio, changing one factor at a time:

1. Current selected kana and displayed-romaji targets: the frozen baseline.
2. Consistently generated targets from the same selected reading, including contextual
   particle handling and explicit model spelling normalization.
3. Dictionary spoken-pronunciation shadows for eligible unedited source groups, with
   written display unchanged; test long vowels, gemination and contractions separately.
4. Existing independently supported alternate sung readings, reconverted through the
   same source groups and freshly aligned. This checks reading selection rather than
   merely changing script. Do not turn the previous blind reading pilot's mistakes into
   automatic corrections.

Keep TIFA, MMS and the singing recognizer's adapters separate. Establish MMS spelling
choices through these paired results; generic
[MMS/uroman preprocessing](https://github.com/facebookresearch/fairseq/blob/main/examples/mms/data_prep/README.md)
does not prove the conventions of this karaoke fine-tune. Agreement between two
dictionary renderings is not independent acoustic support. Retain the existing repair
and timing gates, and do not relax them just to maximize retained counts.

Record per-song additions, losses, moved intervals, reading changes, rejection reasons,
elapsed time and memory observations on M2 Pro /16 GiB. Keep the frozen **4,160 original
source-group denominator** for comparisons. If a legitimate source correction changes
grouping, publish the new denominator separately and match unchanged source envelopes;
do not claim improvement by merging or dropping difficult words.

Promotion has a concrete decision rule: a candidate must add at least one independently
supported missing source group, lose or move zero previously retained unchanged groups,
preserve all protected/verified readings, admit zero timings on the existing negative
controls, and introduce no new error on the frozen PJS timing envelopes and known
reading fixtures. Each accepted reading change must also pass the existing sung-reading
repair gate and fresh alignment. These development checks are regression evidence,
not a new held-out accuracy claim. If no candidate passes, ship the five modes and
consistent representation contract with the measured null result; keep Experimental's
current recipe. The maintainer does not have to label hundreds of words for this PR
to produce its first deliverable.

## Steps

1. **Freeze and diagnose.** After approval, save the merged baseline receipt and run
   the reading/rejection comparison before modifying target generation. Identify which
   changes can address measured gaps; add synthetic regressions for demonstrated
   conversion or mapping defects. Report the cheap diagnostic before longer trials.
2. **Make conversion explicit.** Extend `romanizer/romanizer.py` and
   `src/study/conversion.rs`, derive katakana spans, centralize selected-reading target
   construction in `src/study/alignment.rs` and `refinement/reading_repair.py`, and
   version the boundary. Preserve current target values in a compatibility comparison
   before trying any optional pronunciation policy. Add saved-data migration tests.
3. **Add the five views.** Update `src/study/mod.rs`, `src/settings.rs`,
   `src/ui/study.rs` and layout tests in `src/app.rs`. Share group timing, seek/selection
   and follow behavior across modes. Verify original-script word highlighting without
   adding persistent controls above the lyrics.
4. **Evaluate reading policies.** Run the paired trials and existing accuracy/negative
   controls. Integrate only a passing policy into Experimental, with its own engine
   identity and saved provenance. Do not add another timing button. Record unsuccessful
   trials and the reason they were withheld as well as improvements.
5. **Verify and explain.** Replay native TIFA and Experimental on all fourteen cached
   songs, reopen their saved versions after reconversion, rebuild the standalone app,
   and run package relocation checks. Update README and `docs/study.md` to explain the
   five modes, selected readings and model inputs. Put aggregate results in
   `docs/study-representation-evaluation.md`, run the full repository gate at the final
   head, and set this plan to Implemented when its deliverables are complete.

## Tests and checks

- Existing known readings: Tabi's `闇夜`, `行こう` and `ハッカ色`, departure!'s `地球`,
  SAKURA's `故郷`, all fifteen automatic occurrences, and explicit user corrections.
  Alternative candidates must not override protected edits or bypass fresh timing.
- Source-to-display mapping: NFC/NFKC and half-width kana; combining dakuten; `ゔ` /
  `ヴ`; small kana, gemination, long vowels and particles; split dictionary nodes;
  spaces inside corrected readings; mixed kanji/kana/ASCII; punctuation; unknown kanji;
  non-bijective normalization; and overlapping or unmappable raw envelopes.
- Model targets: all modes produce the same group IDs and alignment request for a
  fixed reading policy; kana and romaji adapters agree on the selected reading;
  supported Latin labels stay inside the pinned MMS vocabulary; dictionary shadows
  cannot erase a saved sung reading. TIFA compatibility targets remain unchanged.
- Persistence: old three-mode settings reopen; all five selections survive relaunch;
  timings survive signature changes when their source/group/reading is unchanged;
  repeated lines retain independent intervals; protected edits, earlier-version restore,
  nonzero delay, cancellation and stale results remain safe. Mode switching changes no
  saved song data and performs no inference.
- Rendering: both rows highlight the same word; katakana and original Japanese word
  highlights, wrapping, character hit testing, seeking and follow use valid byte spans.
  Original-script ambiguity falls back to line highlighting without corrupting timings.
- Baseline replay: **3,507/4,160 Experimental** and **3,121/4,160 original TIFA** are
  retained before any promoted policy. Report exact source-group additions, losses and
  moved intervals afterward. Use the existing PJS envelopes, known reading fixtures and
  143-word negative controls; make no fresh holdout claim from already opened inputs.
- `bash scripts/check.sh`, bundled helper protocol/signature checks, and
  `python3 scripts/check-app-package.py`. Routine checks use synthetic/recorded fixtures
  without network, real Spotify or model inference; real model comparisons are explicit
  private experiments and native cached-audio acceptance runs.

## Out of scope

New transcription models, another romanizer dependency, manual word timing, syllable
highlighting, translation into English, additional paired display combinations,
mobile ports, re-recording the test suite, and publishing audio, full lyrics, model
weights or personal development files. Do not replace Cutlet or the shipped recovery
stages without measured evidence and an update to this plan.
