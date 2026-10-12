# Automatic sung readings and lyric repair

Status: Implemented (2026-10-12)

Merge validation compares both packaged actions on all fourteen existing private song
recordings, using the same input documents and mono recordings; Experimental also uses
each recording's stereo view. The numerical report
separates coverage and processing time from listening accuracy. The offline gate also
checks stale-completion messaging and scans publishable source without traversing ignored
model environments or personal links; new untracked source is still checked. Setup,
usage, local-data backup and reproduction instructions are maintained in the README and
CONTRIBUTING alongside the implementation.

The larger recorded suite exposed a conversion mismatch on leading unpronounced wave
dashes in a blind transcription. Assembly validation now agrees with Cutlet's whitespace
trimming while retaining exact source/display spans. Unsupported optional transcription
or canonical-reading inputs are withheld; mandatory source conversion, stale replies and
protocol failures still fail the job. These are bounded robustness fixes, with dedicated
regressions; acoustic thresholds and the first reading-selection recipe are unchanged.

## Goal

Make **Experimental** correct dictionary readings using the captured singing, then time
the corrected lyrics. It may also repair genuinely wrong lyric text when the evidence is
strong. Save the corrected version per song, restore it after reopening, and preserve
earlier versions. The user should not need to correct words or tap timings manually.

The original **TIFA** action remains available. It aligns the selected version without
running the new correction pass. Keep the interface compact and use Saved lyric versions
under Options to inspect or restore previous results.

## Findings

The current converter chooses one MeCab/UniDic path. Tabi no Tochuu exposes three
different reading problems: 闇夜 → やみよ, 行こう → ゆこう, and ハッカ色 → はっかいろ.
The first two currently default to あんや and いこう; the third has a track-specific fix.
These sung alternatives already appear among the current dictionary's 32 best paths.
Changing every occurrence of those spellings globally would break other songs.

A local retrospective trial ranked dictionary alternatives with the existing singing
MMS evidence. All six affected Tabi occurrences selected the user-verified reading on
both Demucs and Kim vocal views: 12/12 rankings. This reused cached evidence, performed
no new inference, and changed no app data. Repeats and the two views are correlated;
this is feasibility evidence, not a held-out accuracy benchmark or an acceptance rule.

Poetic readings can be absent from the dictionary altogether. The tested dictionary
paths for 地球 do not include ほし. Independent audio transcription must therefore be
able to supply candidates, rather than merely select dictionary entries. A text model
can propose alternatives, but must not approve its own proposals.

## Approach

### Candidate generation and acoustic selection

1. Freeze the exact recording, current snapshot, edit revision, offset and converted
   source groups at job start. Reuse current capture and separated vocals; run models
   sequentially on the M2 Pro/16 GB target. Audio and full lyrics stay local.
2. Generate bounded kana candidates from contextual MeCab N-best paths, initially 32
   paths per line. Retain their original UTF-8 spans, lemma, inflection and grouping.
   Measure candidate recall before expanding dictionaries or adding a dependency.
   Preserve the current reading as a candidate. No universal `行く`/`行こう` substitution.
3. Independently transcribe the full Kim vocal track and original mix with Whisper
   large-v3, without titles, lyrics or song hints; short isolated clips hallucinated
   unrelated phrases in the trial. Use the separate RomajiASR singing phoneme model
   to reject confident pronunciation contradictions. MMS scores remain the primary
   ranking evidence; a near tie in the independent model is uncertainty, not a vote. Source/transcript matching must tolerate token splits through
   exact source envelopes and agreeing neighboring phonemes, not require equal word
   counts as the previous experiment did. Ambiguous mappings are withheld automatically.
4. Rank candidates against the same acoustic frames. Measure absolute compatibility,
   improvement over the baseline and separation from competing candidates; calibrate
   these gates on development controls before freezing them for held-out evaluation.
   Account for candidate length, unsupported phonemes, crop padding, repeated vowels
   and silence. More timed words is never evidence that a reading is correct. Two vocal
   stems scored by one model are correlated views, not independent model votes.
5. Admit automatic reading repairs only when the source mapping, neighboring words and
   acoustic gates agree. For actual text repairs, require consistent independent
   transcription evidence and phonetic verification. The first recipe admits bounded
   kana-only substitutions, including splits/merges of up to four complete source words;
   arbitrary insertions, deletions and kanji text rewriting remain withheld. Prefer a reading-only repair when existing kanji can represent the
   sung expression; audio cannot decide between homophonic written forms. A model's
   familiarity with a song or a larger coverage count cannot authorize rewriting it.
6. Reconvert accepted readings/text and align that corrected version with TIFA and the
   existing experimental timing policy. Old intervals on changed pronunciation/text
   groups cannot satisfy the new alignment. Unchanged groups keep their original source
   identity; changed grouping gets freshly validated timing. Withheld repairs retain
   the baseline and require no user work.

### Protocol and durable data

Python owns candidate generation, model evidence and kana-to-display conversion. Rust
owns source identity validation, final repair selection, version creation and persistence.
The evidence helper returns a bounded JSON proposal package containing the job/source
identity, recording hash, model/recipe fingerprints, and proposed patches. Separated
stems are temporary evidence derived from that recording and pinned model recipe; they
are not persisted as an additional source of truth.
Each patch includes its original occurrence, UTF-8 source envelope and expected text,
candidate kana or replacement Japanese text, and calibrated absolute, comparative,
neighbor-coherence and independent-pronunciation measurements. Rust rejects changed text, invalid boundaries, overlaps, missing
evidence, stale revisions and model/recipe mismatches before admitting any patch.

One Experimental invocation performs proposal, provisional reconversion and fresh
alignment internally. Rust sends bounded conversion requests and protected spans beside
the crop manifest; Python calls the bundled romanizer through its JSON protocol. The
first JSON reply is the frozen repair package, followed by freshly aligned line results.
Rust validates the package, reconverts it independently and requires exact target/span
agreement before persisting the complete generated version. No provisional Python
patch writes app data. The frozen helper processes reset their PyInstaller environment
when launching one another; package relocation checks cover this boundary.

Extend reading records with optional canonical hiragana and automatic provenance; old
romaji-only records still load. For new automatic readings, the converter derives romaji
from that kana and returns both scripts on the same source group. Avoid reverse-inferencing
kana from a generated romaji string. Preserve particles, long vowels, doubled consonants
and existing UTF-8 normalization mappings. User-saved corrections have precedence.

Reading edits continue to apply to identical repeated lines. Check supported repeats for
conflicting sung readings before sharing an automatic correction; conflicting evidence
withholds that automatic correction. Timing remains specific to each occurrence.

Text repairs create a derived immutable snapshot with a parent snapshot ID and repair
provenance. Keep the original provider payload and original version. Maintain unaffected
occurrences/cues, recompute snapshot identity, and reattach existing edits only through
exact unambiguous text/span correspondences. Do not automatically change a span with an
explicit saved correction or require the user to resolve reattachment to finish the job.
Changed text receives newly aligned fragments; stale intervals cannot follow new words.

Persist a complete generated version containing its snapshot, reading patches, timings,
base edit revision, offset and model/audio identities before applying it. Add optional
fields so legacy timing-only results remain readable. Apply to a cloned document and
atomically save it as one consistent version; recover a completed job only if its original
source/revision still matches and the version was not already saved. Cancellation, failure,
song switching and a concurrent reading edit leave the previous usable version intact.
Reopening must restore the corrected display and timing without inference or downloads.

### Study interface

Keep the two existing actions. Experimental adds progress for checking sung readings and
reports a short completion status such as `3 readings corrected · 153/153 words timed`.
Put details, provenance and version restore under Options. Uncertain candidates remain
unused; there is no mandatory approval dialog, manual correction or manual timing step.

## Frozen first recipe

Two MMS vocal views must select the same candidate, each with full-line CTC improvement
and runner-up separation of at least eight log units, selected-word mean posterior
at least 0.45, and support for at least half the other words at probability 0.30.
The separate singing recognizer compares complete phrase likelihoods through its mixed
mora/phone CTC lattice. A candidate or competing alternative that it contradicts by
more than two log units is withheld. Shortening below 75% of the original phone count
requires independently mapped transcription support; expansion is capped at four times.
Exact, nonoverlapping UTF-8 envelopes, protected edits and conflicting repeats are
checked before any save. No threshold is derived from coverage.

Calibration used all fourteen local songs; none is called held-out. The six verified
Tabi occurrences pass this rule. Thirteen wrong-verse controls admitted no reading
repair in the dictionary replay. A disjoint lexical check uses private JSUT recordings
with full-context blind transcription and matching HTS score phone sequences. Score
timestamps are not alignment ground truth. Its artificial reading errors are reported
separately from ordinary dictionary readings; this small test cannot establish general
Japanese song accuracy. Results and final packaged acceptance belong in
`docs/study-reading-evaluation.md`. Audio, full lyrics and private evidence stay local.

## Steps

1. Build a replayable source-anchored candidate/ranking experiment, with synthetic
   public fixtures and explicit local acceptance inputs. Audit the full departure!
   recording, including its middle verses; the remaining reported word is unidentified.
   Test all available songs, not only the Tabi examples, with defaults/user edits disabled
   as evidence inputs so they cannot teach the recognizer the expected answer.
2. Compare dictionary alternatives, independent transcription matching and acoustic
   selection. Include baseline-correct words and silence/wrong-verse controls. Freeze
   candidate generation and admission gates before evaluating disjoint songs/phrases.
   Report exact sung-reading accuracy, repair precision, regressions, abstentions,
   candidate recall, runtime and peak memory separately from timing coverage.
3. Implement canonical-kana repair records, evidence validation and derived source
   versions. Add compatibility, source-span, repeat-conflict and recovery regressions.
4. Integrate only a policy that passes the evaluation into Experimental; if the first
   policy fails, continue experiments and revise this plan before enabling writes.
   Package any newly required runtime/assets with pinned hashes and notices.
5. Build and test the standalone app, then listen to corrected Tabi, departure! and
   held-out passages. Verify all three display modes, saved-version restore and restart.

## Tests and checks

- Synthetic contexts for the three Tabi alternatives, ordinary contexts that retain
  their original readings, inflected `ゆこう` versus `ゆく`, and out-of-dictionary candidates.
- Compound/token split and normalization boundaries, spaces inside an atomic correction,
  kana/romaji agreement, and stable source anchors after a corrected pronunciation.
- Withhold silence, unrelated verse/recording, unsupported phonemes, incomplete/colliding
  spans, ambiguous transcription matches, conflicting repeats and homophonic text guesses.
- Preserve explicit saved edits and prior versions; reject stale jobs and stale cached
  evidence. Test nonzero offsets, failure/cancellation and crash recovery without a
  partially corrected display or timing from the previous pronunciation.
- Confirm backward compatibility with saved documents and timing-only results, plus
  persistence after reopening and selecting an older result. No inference in unit tests.
- Enable the first policy only if every verified Tabi case is repaired, no repair is
  admitted on the adversarial controls, and the disjoint evaluated set improves exact
  sung-reading accuracy with zero observed regressions on labeled baseline-correct
  controls. Report sample sizes and uncertainty; this does not establish universal accuracy.
- Run `bash scripts/check.sh`, helper/package isolation checks and live listening checks.

## Out of scope

Replacing Spotify playback or the working timing models; translation into another
language; global song-independent guess rules; manual timing; model fine-tuning in the
first iteration; claiming correctness from coverage; publishing audio, full song lyrics,
personal chat contents or private development tools.

## Primary references

- [Fugashi and MeCab token/N-best interfaces](https://github.com/polm/fugashi)
- [Full UniDic data and reading/pronunciation fields](https://github.com/polm/unidic-py)
- [Whisper transcription and limitations](https://github.com/openai/whisper)
- [Japanese singing MMS checkpoint](https://huggingface.co/NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn)
- [RomajiASR singing phoneme inference](https://github.com/Xiantaidu/RomajiASR): an
  independent pronunciation check; TIFA still supplies word timing.
