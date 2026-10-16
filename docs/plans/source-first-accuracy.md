# Source-aware singing accuracy and word boundaries

Status: Approved (2026-10-14; maintainer requested implementation in the successor PR)

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

Preserve internal apostrophes in an original English contraction's acoustic
spelling. The current punctuation filter turns `Don't` into the different G2P
input `Dont`; audit original-versus-target dictionary paths and replay affected
cues without changing their source spans, displays or saved clocks. Cover
contractions and surrounding quotation punctuation with regressions.

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

The next English comparison separates lexical verification from word boundaries.
Use source-blind Whisper on original mix and vocals to confirm unique multiword runs
with probability at least 0.70, preserving its audio-occurrence check. TIFA and
HubertFA must separately observe both boundaries within 150 ms; keep TIFA's 0.90
agreement, positive similarity and 80 ms duration rules. Do not treat HubertFA's
conditional score as recognition confidence. On the opened development reference,
the boundary pair retains 31/37 word envelopes with 31 correct; lexical verification
and wrong-target tests remain prerequisites. Compare original cue recognition against
up-to-30-second unions of complete Rust crops, with unchanged timing-job bounds.

Keep recognition statistics typed: Whisper word confidence and an acoustic CTC
phone probability are different measurements. The exploratory HubertFA CTC path
requires every phone to reach 0.45 unmasked probability, 0.90 greedy agreement,
and an adjacent supported word in each actual audio view. Its CTC and alignment
heads share an encoder. The first development test accepts three correct groups
and rejects 111 wrong-phone controls, but the commercial trial adds zero groups.
It is not an integration candidate or a calibrated universal probability rule.

Test the released [MOSS-Music singing recognizer](https://github.com/OpenMOSS/MOSS-Music)
through an isolated, pinned MLX runtime. The 4-bit checkpoint is about 6 GB; require
strict complete weight loading and a local tokenizer without custom remote code.
Use audio-only transcription, keep text as an unverified proposal, and never use
generative timestamps as word clocks. Measure M2 memory and processing time.
The first four-clip pilot and two-clip prompt diagnostic both repeat and exhaust
their token limits. Reject that path unless a reproducible inference change fixes
it; larger precision is not itself a fix. A bounded speech-ASR challenger may still
test fast English recognition, without assuming singing accuracy from speech scores.

The next comparisons change the acoustic path: a second vocal separator before
source-blind recognition, English GMM-HMM clocks with and without per-speaker
feature adaptation, and complete Parakeet CTC paths from cached audio-only emissions.
Keep these separate from text/reading corrections. A third fixed waveform requires
two scored, unique-context word witnesses; it supplies no word clocks. Same-model
waveforms remain correlated. Test lead/backing-vocal separation separately from
ordinary all-vocal extraction. The MOSS port's validated 8-bit configuration may
receive one controlled comparison against the unvalidated 4-bit result, within a
measured memory limit; it must demonstrate a change rather than presume one.

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

The next reading trial compares explicit kana minimal pairs on otherwise identical
cues, rather than re-reading an ASR-produced kanji string. Use real/silence/other-verse
contrasts for both the owned word and complete cue so a candidate cannot absorb its
neighbor unnoticed. These remain research nominations: test localized acoustic
dependence and independent reading evidence before any correction. Keep model
features cached without changing scores. English work also tests a genuinely new
source-blind CTC recognizer; CTC spikes supply lexical location, never word offsets.
The latest SOFA/MFA and pitch-transform limitations are recorded in the evaluation;
none authorizes relaxing the integration gates or changing saved results.

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

## Progress (2026-10-14)

- Exact dotted-kana mapping is implemented with nine additional source/edit fixtures.
- Pinned HubertFA inference and development benchmark tools run on CPU and MPS.
  The supplied-phone test gives 32/37 correct word envelopes; no verifier-qualified
  words or app recipe are promoted.
- The reviewed romaji parser and bounded region probe ran 29 fresh local trials on
  嘘, producing zero additions beyond the earlier one-word full-window proposal.
- English recognition on 172 context views finds 47 missing groups with evidence
  in both views. Paired TIFA/HubertFA retains eight proposals; a complete CMU G2P
  fallback raises that to eleven across three songs, with zero losses or moves.
  These are research proposals, not shipped coverage.
- The phone-recognition gate adds zero groups across 189 commercial cues. MOSS
  fits the M2 memory target but repeats. Keep those failures visible and pursue
  a changed recognition/verification approach instead of relaxing the gates.
- A source-blind Parakeet pilot also fails on the difficult mix/vocal contexts.
  Tempo and pitch transformations are restricted to text proposals: their clocks
  cannot supply saved timing. Do not sweep the cap until a bounded pilot retains
  actual original groups.
- Test a different verification surface with the already pinned Whisper model:
  score the exact original Japanese/English source against the original waveform,
  silence and a different verse. Mask each model-observed word interval and compare
  the score change with equal-size masks elsewhere. This tests local acoustic support
  without requiring greedy transcription to spell our selected romaji. Forced text,
  attention clocks and conditional confidence alone never verify a word. Calibrate
  the combined decision on labelled development audio and existing negatives before
  considering integration; preserve the existing boundary and saved-edit gates.
- Add two pinned CC BY JamendoLyrics development songs with human word clocks and
  exact normalized word text. They address NUS's missing orthographic transcript;
  they are a small English development sample, not a new Japanese/pop holdout.
  Store all lyrics/audio/results outside Git, retain attribution, and do not mix
  corpus accuracy with commercial retained coverage. JLEE remains reserved.
- The localized source-contrast pilot does not improve English retention. Forced
  Whisper clocks fail the labelled comparison; TIFA/HubertFA masks retain 34
  development words, 33 joint-correct. Continue with independently decoded singing
  text and explicit language routing; do not promote this conditional-only recipe.
- The substantial multi-song target remains unmet. Continue the lexical verification,
  sung-reading and anchor work on this same draft PR. Results and reproduction are
  recorded in [the evaluation](../study-source-accuracy-evaluation.md).
- Free Qwen decoding with explicit language policy improves the English development
  transcription, but the paired timing pilot still has errors and only five commercial
  proposals. Fresh singing-letter and original-kanji /selected-kana comparisons also
  fail to establish a substantive recipe. Test joint neighboring-cue alignment next:
  preserve original groups and use unions of authenticated Rust crop bounds, with
  occurrence-specific clocks. Compare it with isolated cues before expanding the run;
  shared-model agreement alone never authorizes a new saved word.

## Next bounded comparison (2026-10-15)

The deletion-aware and neighboring-cue pilots do not meet the gain target. Keep
them as measured research tools; neither changes the app. Test the dedicated
Japanese-singing [SOFA akm_ja release](https://github.com/ariikamusic/SOFA_Models/releases/tag/akm_ja_v001)
as a different acoustic surface. Pin the released checkpoint and matching
inference source, validate the complete state, phone inventory, mel preprocessing
and output clock, and measure a small CPU pilot before expanding. Its selected-path
confidence is conditional and must not be called independent lexical probability.
Keep raw observations, require complete original word ownership and compare with
fresh independent boundaries. This does not waive existing promotion gates.

The model owner lists PJS in training. PJS may check this adapter's contract but
cannot establish independent accuracy for this checkpoint. Keep unknown weight
redistribution terms explicit and weights private; an integration decision needs
appropriate independent evidence. Do not ask the maintainer for labels or accounts
as a prerequisite to continuing the other experiments.

Separate source-blind phone presence from a forced path's clocks. The first complete
low-set opportunity comparison finds only 40/714 missing groups with exact unique
phone witnesses; neighboring-phone ablations reach 42 and do not solve the restriction.
The SOFA/TIFA/free-phone prototype leaves five proposals on three 嘘 cues, without
changing existing timings. Neither trial meets the integration milestone. Expand
the better English free-decoding pilot to the already frozen 172 mix/vocal context
clips, with unchanged probability and independent boundary checks. Match the complete
source window before assigning occurrences, so repeated phrases cannot be credited
to the wrong cue. Reuse the existing authenticated paired boundaries and withhold
incomplete recognition; this comparison does not change the app or open a holdout.
The completed comparison leaves sixteen proposals across three songs, with no lost
or moved intervals; it still misses the substantive target. Thirteen of the 172
views are withheld for exhaustion or non-reconstructible repetition-cleaned text.
Record that full-window English detection fails on Japanese passages even though
the PJS/order diagnostics work. Test a bounded explicit Japanese-language hypothesis
against original-source words next; a language prefill is not a lyric prompt, a
detected-language result or independent evidence that a particular word was sung.
That six-view pilot finds only one scored literal match among 18 missing groups.
A private long-vowel projection also fails to increase the complete opportunity
count. Preserve these nulls and continue with a different acoustic recognizer or
source-correspondence hypothesis; do not expand these unchanged recipes merely to
accumulate more proposals.

The next different acoustic candidate is Japanese-specific
[ReazonSpeech NeMo v2](https://huggingface.co/reazon-research/reazonspeech-nemo-v2),
using a pinned private speech.cpp Metal runtime and Q8 checkpoint. Its twenty-clip
greedy/beam comparison finds only seven phonetic opportunities among 81 gaps with
either decoder, and its public JSON has no word probabilities. Keep the artifact
pins and benchmark in the evaluation; do not integrate its transcript or emission
times as verified lyric/timing corrections. The substantial integration target
remains open.

Test local pronunciation contrast on closed singing CTC posteriors next. Compare
each complete original group's phones against the union of representable one-phone
substitutions and the blank path on identical frames. This is a likelihood ratio,
not a calibrated word probability. Keep the existing observed-frame duration,
independent boundary, context and preservation checks. The fixed first comparison
rejects all 390 wrong-reading variants but pairs only 79 original development words
with TIFA, of which 78 are correct; its eighteen-cue commercial replay leaves one
proposal. It does not satisfy promotion. Investigate the observed boundary failures
and a duration-aware singing model rather than expanding that unchanged recipe.

A numerical MOSS frontend check on one earlier crop matches the official-equivalent
Whisper features closely. It supplies no corrected runtime that warrants repeating
the recognizer sweep. Keep this one-crop diagnostic separate from model accuracy.

The closed CTC audit measures a median 170 ms early ending against human sung
boundaries; padding is not the main cause. Test a separate duration model rather
than extending emission peaks. A private pinned PySHIRO v2 full-phrase comparison
checks 264 development groups with 263 correct TIFA clocks, but its commercial
overlay adds zero. At-most-four-group Japanese regions remove mixed-language
blocking but reduce development boundary accuracy and leave only one commercial
proposal. The adapter's silent unknown-mora dropping is fixed with a regression.
These are measured rejected recipes, not a promoted change: keep model weights
private, disclose unknown PJS training overlap, and preserve the substantive target.

The next duration trial replaces pause-only surroundings with a source-independent
mixture over distinct acoustic state outputs. Sum complete positive-duration state
paths with an exact finite-window prior normalizer; retain actual frame boundaries
and report their posterior spread. This is an acoustic background diagnostic, not
a full phone-loop recognizer. Compare the same windows with the pause ablation,
the opened PJS labels and all mismatch controls. The first trial checks 171 PJS
groups with 171 correct TIFA clocks, but still leaves only one commercial proposal.
Keep original intervals immutable; their collisions are not permission to retime
user/provider/unknown-origin data. A source-tag/result audit can distinguish an
earlier automatic interval, but each proposed replacement still needs fresh evidence
and unchanged outer anchors.

Test a separate duration-model pronunciation contrast next: compare each complete
word with all canonical same-length one-phone substitutions, using the same observed
window and each candidate's own prior-fit normalizer. A strict unweighted sum of
these conditional likelihoods is not a union probability or calibrated confidence.
Report competitor counts, unknown phones and bounded-window abstentions. This tests
an alternative to the CTC emission-confidence gate; it is not a threshold reduction
or an app policy change. Freeze the recipe before scoring known references and
wrong-reading/wrong-audio controls. Wider commercial replay requires positive results.
The first fixed pilot scores twelve eligible PJS groups and none beats even its
best competing phone path; all commercial additions are zero. Keep the exact scorer
and null result, but reject this GMM pronunciation gate and do not expand it unchanged.

A real alias-routing defect is fixed: explicit validated phones must be considered
even when ordinary text routing rejects a macron-bearing lyric. Preserve its source
text/span and reject unknown phones. The RomajiASR contract audit finds no missing
waveform normalization and no token-expansion discrepancy; those unchanged paths
do not warrant another recognizer sweep. A correctly mapped English HFA CTC contrast
retains only one of 96 development words and is rejected before further inference.

## Latest experiment adjustment

Correct the private English replay's fully supported-source skip before judging
its evidence. Export its source-owned lexical matcher and regressions, then test
original UTF-8 source groups directly rather than encoding supplied lyrics with
an English-only tokenizer. Both changes improve measurement but add no gaps
beyond the same eighteen unpromoted proposals; do not count extra witnesses as
coverage gains.

Dictionary replacement and the independent acoustic pilots still miss the
substantive target. Test context-aware kana candidate generation as a distinct
reading-selection approach: freeze source-only prompts and model identity before
inference, keep labels and current readings outside that process, and reject
changed IDs or incomplete responses. Reattach candidate readings to original
spans, preserve surrounding words, and evaluate them against real audio and
controls before considering any saved edit. Published furigana may nominate
alternatives but cannot certify how the singer pronounces them. This remains
research in this PR and changes neither the app recipe nor its saved timings.

Keep a separate whole-cue minimal-pair unit where a recognizer's BPE token spans
more than one source word. Score the complete unchanged-neighbor cue against the
same controls, without dividing a token score between words. Preserve the original
word-and-cue gate and report both units. Three cross-family sequence nominations
justify fresh current-versus-candidate clock probes; they do not authorize edits.
Also test current-reading winners as possible timing evidence and a small English
CMU-confusable-word pilot. These tests ask whether discriminative source checking
can recover useful evidence when free transcription fails. Freeze competitors and
controls before inference, score wrong-current queries symmetrically, and require
physical/reference checks before any integration.

The full English cue may include another language or incorrect neighboring lyrics.
Test a separate immediate-source-neighbor window on all twelve reference words,
twelve hard gaps and twelve independent negatives, rather than selecting only
favorable failures. Keep the same competitors, controls and decision margins.
Changing text context is a new verification unit, not permission to discard a
failed full-cue decision from the record.

Challenge canonical English pronunciation as well. A bounded Japanese-English
phone lattice can represent documented consonant substitutions while preserving
the original source word. Start with unambiguous, contextual rules from
[Ando et al.](https://www.isca-archive.org/interspeech_2021/ando21_interspeech.pdf),
with a fixed variant cap and deterministic gap selection across low-set songs.
The speech evidence is a hypothesis for singing. Do not invent epenthetic vowels
where the source does not define a usable rule. Alternative forced paths nominate
boundaries, not verified lyric spelling; compare them against canonical paths,
independent lexical evidence, physical clocks and wrong-audio controls.

Keep natural source script and phonetic input separate in the verifier too. Compare
unchanged original-script neighbors with all-kana contexts, reusing only byte-identical
closed inputs. A separate mixture-versus-vocals comparison holds the complete
candidate sets and source context fixed; agreement on a distorted consonant must
not become a displayed reading correction. Likewise, local boundary comparisons
must keep the old waveform role before attributing a difference to context alone.

Measure the oracle availability of correct existing intervals as a diagnostic,
separate from a label-free interval selector. A whole-interval consensus may choose
only measured original-word observations; report introduced errors, lost correct
words and source-order overlaps, not just added words. It remains a research recipe
until correctness and ordered-region checks pass together.

A corrected reading can restore a paired target while the old automatic neighbors
still overlap it. Test a separate bounded automatic-region solver using only
observed endpoints belonging to the same original word and waveform. An old
endpoint may be retained when both fresh models endorse it; another endpoint of
that word may come from a fresh observation. Such an interval has explicit
composite provenance and must not be described as one model's complete output.
Never manufacture, average, trim, snap or transfer an endpoint from another word.
Protect user, provider and unknown-origin data, retain the earlier strict solver's
results, and validate this new recipe independently before any app migration.

Keep the existing complete-pronunciation CTC contrast and its 0.45 emission check
as lexical evidence, separately from physical duration. Test native source-word
forced alignment as the second physical clock beside TIFA; the CTC spike's
endpoints do not become the word's boundaries. This changes the observer family,
not the pronunciation margin or timestamp tolerances. Start with all 390 opened
PJS words and the existing wrong-reading/audio controls, then a source-selected
48-gap cohort across the frozen low songs, including current readings. Report
every structural abstention and retain the old CTC-clock and HSMM comparisons.

Test native character timestamp slots as a separate granularity factor. The
official Python Japanese path uses Nagisa morphemes; the pinned C++ Japanese
path instead splits CJK characters. Neither establishes that character slots
will improve singing. Keep the same frozen words and waveforms, tile each source
word exactly with auxiliary character/run pieces, and aggregate only its first
observed start and last observed end. Equal internal character timestamps are
recorded, not interpolated; missing, nonmonotone or ambiguous pieces abstain.
Original word denominators and display groups remain unchanged. Evaluate this
condition on the same references and controls before considering it for songs.

Test Fun-ASR-Nano as a different source-blind lexical observer. Its model card
lists Japanese and music-background lyric recognition, but does not establish
Japanese singing accuracy. Use the official pinned native checkpoint, a separate
local research environment and saved audio. Freeze language routing, frontend,
decoding and complete-source-owner matching before each comparison. Keep generic
automatic-language and upstream-amplitude conditions separate; do not choose a
different winner for each clip. Compare only authenticated identical waveforms
with earlier free transcription, retaining missing comparisons explicitly.
Transcription matches nominate reading or timing checks; they never supply word
duration. First audit the physical/ordered-overlay ceiling before expanding a
cohort whose clocks remain fixed. Test English gaps separately from romanized
Japanese, since treating every Latin source as English repeats the existing bug.

Complete a missing-observation census for all 717 frozen gaps before extrapolating
from selected probes. Keep every original group in each gap-containing Rust cue,
reuse exact closed observations and collect only missing ordinary-current TIFA
and native clocks. The seven difficult songs use their authenticated Kim stems;
the three high-set gaps without authenticated stems remain a separate original-
mixture stratum. A missing cached observation is unknown, not model failure.
Keep the separately frozen English cohort and its dual-view free-transcription
matches separate from this physical census. Calibrate any proposed replacement
lexical observer on the same opened references and mismatch controls before
considering app admission; do not substitute its decoder confidence for CTC
emission probability.

The complete census also permits a separate filter experiment: TIFA's 0.99
token-agreement threshold is a mean conditional token probability, not proof
that a path is structurally complete. Keep the original action and current
retained-path policy unchanged. Test complete raw observations with finite
positive similarity and the same strict duration/interior/paired-clock rules,
using independently qualified lexical evidence in place of that one confidence
filter. First close proposals on the opened PJS/English references and existing
mismatch controls, then join their labels and report wrong readings, errors and
lost correct intervals. Missing complete-path proof abstains. This is a new
research recipe, not permission to treat every rejected raw path as a word.

Test a different boundary factor rather than repeating the failed preset-head
Whisper run. Port the pinned stable-ts runtime head selection with six heads per
token and two selection/DTW passes. Keep the same forced text and acoustic
features; the selector sees no reference timestamps. This is source-conditioned
alignment, not source-blind recognition. Start with the already opened sixteen
English cues and unchanged controls. Retain attention/head selections and both
paths, and compare endpoint error and independently qualified intervals. Exclude
refinement, silence suppression, duration clamps and timing shifts. Do not sweep
head counts or iterations against these labels; a null result does not justify
choosing the best head retrospectively.

Test direct source-blind kana decoding as a separate acoustic representation:
ordinary Japanese transcripts can hide a sung pronunciation behind kanji. A
UTF-8 token-state constraint may emit kana without supplying the target lyrics;
retain split-byte tokens, permit end-of-text only after complete UTF-8, and save
the chosen tokens' original full-vocabulary scores separately from the masked
distribution. Constrained output is a hypothesis, not calibrated lexical
confidence. Start with the three opened reading examples before expanding.

Exact repeated source lines offer another bounded experiment. The frozen cap
contains at most 44 missing groups with a compatible already-timed occurrence.
Test whether independent acoustic sequences can locate boundaries on the target's
observed frames, using wrong-verse controls and protected-neighbor checks. Never
copy a source timestamp or linearly stretch it onto the target; a source-only
repeat count is not recovered coverage. Record this ceiling before collecting
the small additional acoustic observations the existing caches lack.

Test the initial Music Flamingo checkpoint as a music-trained alternative to
speech ASR. Use a pinned Q4_K_M text model, its matched F16 audio projector and
an isolated current llama.cpp build with explicit Music Flamingo audio support.
Keep these research assets outside the app and Git. Freeze one generic lyric
transcription prompt, decoding settings and the same eight audio-only pilot
windows; preserve sample identity through WAV encoding. Strictly validate model,
projector, runtime and frontend provenance before interpreting output. Japanese
lyric quality and M2 memory/latency are measurements to make, not established
capabilities. No integration or larger replay follows an unvalidated pilot.

Test a singing-conditioned boundary model rather than another speech recognizer:
the released Schulze-Forster lyrics-aligner jointly learns phone alignment and
lyric-conditioned vocal separation. Freeze its pinned checkpoint, canonical CMU
dictionary and all 39 phones before the same sixteen Jamendo development cues.
The model receives supplied phones, so this is source-conditioned alignment.
Start with the original mixtures; isolated vocals are a separate condition.
Use deterministic evaluation mode, no VAD threshold, an explicit Torch STFT
compatibility change and no additional padding. Retain complete attention/DTW
paths. Measure first-phone onsets as the primary endpoint and its observed
separator-state word ends as a separate full-interval comparison; neither is
ground truth merely because the model produces it. Reject skipped or incomplete
owners, preserve all original denominators, and close proposals before joining
reference clocks. Disclose training-domain overlap checks. Expand to the frozen
song gaps only if reference/control results justify it.

## Out of scope

Manual timing, fabricated/interpolated timestamps, mobile ports, new lyric views,
another timing button, a hosted service, publishing private skills/history/credentials,
recordings/lyrics/model weights, and training on the private song suite. Corpus acquisition
that needs contacting/licensing a third party is not a prerequisite for the first source
and boundary deliverables. This PR does not promise 100% or call unverified words correct.
