# Source-aware singing accuracy and word boundaries

Status: Draft

## Goal

Make Experimental correctly read and highlight substantially more of the words being
sung, including difficult Japanese, pre-romanized Japanese and English passages. Keep
one automatic action, the five views, local processing on M2 Pro /16 GiB and saved
results that survive reopening. The user will not time words or label recordings.

This is the maintainer-requested successor to [PR #4](https://github.com/Anny0nn/romaji-player/pull/4),
merged at `21a8286`. Its 61 authenticated baseline recordings remain intact:
**15,265/17,561 retained groups (86.9%)**. The active ten-song set has **2,210/2,927
(75.5%)**, leaving **717** gaps. See the [catalog](../study-song-catalog.md) for counts,
URLs, the fixed seven-low/three-high selection and private-source provenance.

Aim for at least 95% retained coverage on each selected song. The first integration
milestone targets at least **100 independently supported original groups across three
or more low-set songs**, with the accuracy and preservation checks below. A tiny gain
or a null trial does not complete this PR: keep working and keep it draft. These
targets do not authorize invented timing or guarantee that every provider word is sung.

## Approach

### Start from the measured restrictions

The ten-song selection stays fixed: Just Awake, Wild Side, Kyouran Hey Kids!!, TEENAGE
CITY RIOT, LOST IN PARADISE, 嘘 and 天天天国地獄国; plus たぶん, CROW and 残酷な天使のテーゼ.
No selected crop reaches the 30-second limit. Of the 717 gaps, 583 contain Latin
letters, 85 contain kanji, 48 contain only kana and one is neither. Script alone does
not establish language, a wrong reading, or whether a word is present in the recording.

嘘 illustrates two separate defects. Its LRCLIB source is already Japanese romaji:
158 ASCII targets take the English route and nine macron-bearing targets are unsupported.
A private Japanese-phone probe recovered no words; including marked vowels recovered
one. Fresh TIFA retained 43/51 missing candidates, but only nine agreed with the singing
recognizer's endpoints within 150 ms; seven also passed its probability check, and one
survived context/interval conflicts. Fixing target spelling alone is insufficient.

Several earlier approaches are already rejected: a speech IPA verifier produced only
10/17 correct accepted English word groups on the small NUS development sample;
blind phone reading repair introduced additional wrong repairs; weak-repeat DTW added
zero words. Repeating those recipes without a specific changed factor is not new work.

### First deliverable: source ownership and reproducible evidence

Move reusable private probe logic into reviewed repository tools. Consume authenticated
Rust crop manifests, source/result hashes, pinned model revisions and the frozen selection.
Cache vocals, audio-only transcripts and acoustic posteriors outside Git, checkpoint
each song, and refuse changed identities or silent overwrites. Separate collection from
candidate evaluation so later trials reuse recognition instead of rerunning whole songs.

Export per-word restrictions at each stage: source mapping, pronunciation support,
TIFA path/completeness/agreement/duration, independent probability, both endpoint errors,
phrase context, and collision with an already retained interval. Keep unknown acoustic
causes unknown. Store lyric-bearing ledgers privately; publish aggregate restrictions,
per-song gains/losses/moves and processing/memory observations.

Resolve demonstrated exact-source mapping defects, including dotted-kana tokens split
inside a dictionary node. A proposed subnode mapping must reconstruct every source
piece and display token exactly through normalization, with unique UTF-8 boundaries;
otherwise retain the existing line fallback. Keep existing displayed groups and original
denominators. Do not merge syllables or remove troublesome groups to improve percentages.

### Canonical readings and source language

Represent original spelling, selected kana, acoustic pronunciation and provenance
separately. Keep Rust as persistence/identity authority and Cutlet as the bundled display
converter. A change of display script never changes acoustic inputs.

1. Test bounded Japanese-romaji hypotheses, including macrons, syllabic `n`, gemination,
   apostrophes and mixed-script text. Preserve original source spans and displayed text.
   Ambiguous spellings remain alternatives; English words that also parse as romaji
   need acoustic discrimination. Round-trip spelling and provider language are hints.
2. Compare authentic Japanese-source candidates where the selected provider offers only
   romanized text. Require matching title, complete artist credits, recording duration
   and album/version where available; then check correspondence with the actual audio.
   LRCLIB record 9914800 is the confirmed romanized 嘘 source, not a new Japanese candidate.
   Unavailable search or ambiguous recording identity remains an explicit failure.
3. Generate sung-reading candidates from source-provided readings, bounded dictionary
   alternatives and closed audio-only phone/kana recognition. Check local source-owned
   envelopes so an unsupported English word elsewhere cannot block a Japanese reading.
   Do not send the same kanji through a second dictionary and call that new evidence.

Accepted corrections stay attached to original lyric spans, apply to identical repeated
text, and obtain fresh occurrence-specific alignment. Preserve user edits and verified
readings; never reconstruct ambiguous kanji from sound. A genuinely different source
snapshot stays a separate saved version. Report its new denominator separately; compare
old groups only when phonetic/source correspondence is unique and documented.

### Local acoustic verification and region realignment

Compare full-line alignment with bounded local regions on the same waveform. Use only
anchors supported by fresh acoustic evidence; retain their exact frame/crop provenance.
Local regions must remain inside Rust-exported recording bounds and include enough
context to check both sides. Candidates at a cut edge, ambiguous repeats and missing
word ownership remain withheld. Cropping is a search restriction, not a word timestamp.

Keep current probability, token-agreement, duration and endpoint rules for the first
comparison: independent probability at least 0.45, TIFA agreement at least 0.90 when
using raw rejected paths, positive similarity, duration at least 80 ms, and both observed
endpoints within 150 ms. Evaluate any later policy change against references before
adoption; do not lower thresholds because the commercial coverage count is disappointing.

The existing immutable-interval fallback can block a correct new candidate beside a
wrong earlier interval. Test a separate, bounded region solver using the existing
`repair_regions` work as a starting point. It may replace an **automatic** neighbor only
when fresh independent observations agree with the replacement and contradict the old
boundary, and the complete region passes order, overlap, context and unchanged outer
anchor checks. A region starts with at most four groups. User/supplied timing stays
protected. Preserve the earlier version rather than silently rewriting it.

Report added words and moved words separately. Unsupported old intervals are not erased
to clear space. Correct existing reference timings must not gain new errors; source
reading changes and justified repairs are identified explicitly rather than hidden in
an assertion that nothing moved.

### English singing needs an appropriate acoustic path

Reuse existing TIFA and cached singing evidence first. English and romanized Japanese
must be routed separately, with an unknown/mixed option. Test verified English runs
using a singing-trained challenger and an independent family of evidence rather than
requiring the Japanese-only phoneme checker to understand all English words.

The pinned [Echora](https://huggingface.co/hcX02/echora-mms-300m-multilingual-lyrics-forced-aligner)
checkpoint is a bounded research candidate already available locally. Its actual
30-token vocabulary is Latin-only, so native kanji/kana are unsupported despite the
model card's language claims. Its earlier six additions and zero direct RomajiASR-gated
additions must remain visible. A new trial changes phrase routing and verification,
not just the model name. Do not bundle its research-only weights.

The first new challenger is [HubertFA-combined](https://huggingface.co/Silasimo/HubertFA-combined/tree/f20e23ab12596d914b2adfcbeb8882180dd92fac),
with [Apache-licensed inference source](https://github.com/wolfgitpr/HubertFA/tree/b3f086966946255a05b0ccb69c865c8e3e806e0a)
and a pinned Chinese HuBERT encoder. It publishes a 39-phone ARPAbet inventory plus
silence, configuration and a singing-trained boundary head. The upstream CLI also
requires an unpublished nonlexical head: test the forced-alignment head alone, without
pretending to detect breaths. Verify restricted checkpoint loading, complete state
keys/shapes and the 44.1 kHz /10 ms output clock before running NUS development audio.
Its conditional path confidence does not verify spelling. Keep weights research-only;
measure CPU and MPS rather than assuming upstream supports Metal.

[SingAlign](https://huggingface.co/pymaster/SingAlign) is a possible singing-trained
English phoneme path only if its encoder/head/vocabulary/frame-clock contract can be
recovered and pinned. Its linked source currently returns 404. Search official renamed
or archived sources and inspect safe documented metadata before rejecting it; never
initialize missing layers or guess the inference graph. If unusable, record that exact
restriction and pursue the reproducible path. New downloads require pinned hashes and
recorded terms; no training on the private commercial test recordings is planned.

Japanese timing uses the existing PJS references. English timing needs the existing
NUS singing phone/word-marker references: PJS is not English evidence. NUS word groups
have no orthographic gold text; evaluate supplied-phone boundary accuracy honestly, and
score spelling only after an independently sourced transcript matches the human phone
groups uniquely. Do not use ASR output as gold. The previous speech verifier remains
rejected, not a baseline to rescue by opening held-out data.

## Steps

1. **Cache and trace.** Build the reviewed evidence/probe tools, authenticate existing
   inputs, and collect only missing caches for the frozen ten. Publish the restriction
   breakdown before choosing longer model trials. Fix exact mapping defects with fixtures.
2. **Readings and routing.** Implement bounded source/romaji/kana hypotheses and local
   reading verification. Run written-versus-spoken and language-routing comparisons
   separately, preserving the input groups and reporting all selected songs.
3. **Boundaries.** Compare full-line, local-region and verified-neighbor-repair paths.
   Exercise timing checks on known labels and wrong-window controls before integration.
4. **English challenger.** Establish a reproducible singing-specific model contract,
   explicit phone/token mapping and positive English singing evaluation. Run the same
   frozen commercial cases and reject incomplete or poorly validated paths.
5. **Integrate a substantive recipe.** Extend Experimental only after a candidate passes
   the gates and delivers multi-song gains. Version engine/model/provenance identities;
   retain the original TIFA action, saved edits and earlier results. Keep this same PR
   open if the first candidates fail; update the plan as evidence changes the approach.
6. **Validate and explain.** Native replay/reopening on the ten selected songs, protected
   reading and representation fixtures, app/ZIP packaging and relocation, full repository
   checks, README/design/evaluation updates. Further catalog testing uses documented
   bounded sets after the recipe freezes; never replay all 61 for each hypothesis.

## Tests and checks

- Source/representation: dotted and half-width kana; combining dakuten; macrons and
  ASCII English lookalikes; punctuation; repeated lines; non-bijective normalization;
  unknown readings; exact source ownership; protected edits and reconversion reattachment.
- Every cache/result binds recording, original/source snapshot, selected group identities,
  Rust crop samples, delay, source/edit revision, model and code hashes. Interrupted runs
  resume only authenticated completed work. No capture helper rebuild or Keychain access.
- Compare frozen original groups: gains, losses, moves, reading/text changes and new
  denominators where necessary. Never equate retained coverage with verified correctness.
- PJS: keep the previously opened 390-word/62-recording development comparison, including
  masked gaps. Preserve the 389 previously joint-correct words (onset error ≤150 ms and
  offset error ≤200 ms), retain their coverage, and report the remaining error separately.
  Labels are opened only after a trial's observations close; this is no fresh holdout claim.
- English: keep used NUS ADIZ development evidence separate from the frozen JLEE song 05
  reserve. Freeze model, mapping, preprocessing, thresholds and eligibility before opening
  JLEE labels. Report word-group timing, sample size and uncertainty by song; one clean
  a cappella song cannot certify commercial mixed-language pop accuracy.
- Exact new stages must admit zero timings on the 143 existing wrong-verse, silence,
  instrumental and English mismatch controls, plus region-specific wrong-word/repeat
  controls. Correct-reading controls and the six verified Tabi/fifteen saved occurrences
  remain unchanged. Extra false repairs fail promotion even if coverage increases.
- No required listening/annotation assignment to the user. Optional listening feedback
  supplements existing labelled evaluation; limitations remain explicit.
- Measure cached and full-pipeline time, process RSS and sampled MPS/MLX allocation on
  M2 Pro /16 GiB separately. Run models serially, checkpoint, and preserve safe cancellation.
- `bash scripts/check.sh` remains the mandatory offline gate; new tool checks join it
  without model inference/network. Packaged/helper and `check-app-package.py` smoke tests
  verify signatures, source/protocol compatibility and relocation before a merge request.

## Out of scope

Manual timing, fabricated/interpolated timestamps, mobile ports, new lyric views,
another timing button, a hosted service, publishing private skills/history/credentials,
recordings/lyrics/model weights, and training on the private song suite. Corpus acquisition
that needs contacting/licensing a third party is not a prerequisite for the first source
and boundary deliverables. This PR does not promise 100% or call unverified words correct.
