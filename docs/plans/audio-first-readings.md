# Recover sung readings before choosing romaji

Status: Approved (2026-10-13)

## Goal

Make Experimental recover the pronunciation the singer uses, including readings such as
`闇夜 → やみよ → yamiyo` and `行こう → ゆこう → yukou`, even when the dictionary chooses
another valid reading. Then align those corrected readings and save them for the song.

The first deliverable is a reproducible **blind pronunciation-recognition benchmark and
source-reconciliation pilot**. It must establish whether the new approach discovers better
readings before changing the app. This plan and any resulting implementation share this PR;
the completed [benchmark work](../study-accuracy-evaluation.md) is already merged separately.
No manual timing or reference labelling is assigned to the maintainer or other app users.

## Approach

### Change the starting point

Today the app converts written lyrics through Cutlet, aligns those readings, and proposes
bounded corrections using dictionary alternatives or Whisper text. Whisper can recognize
the kanji correctly while hiding the pronunciation: converting `行こう` back through a
dictionary can discard the distinction between `ikou` and `yukou`.

The proposed path is:

```text
vocals → independently decoded phones/kana → reconcile with source spans
       → preserve the selected kana → derive romaji → fresh word alignment
```

The recognizer gets audio only. Source lyrics, dictionaries, song titles and reference labels
are unavailable until its hypotheses have been saved. Written lyrics then help recover word
boundaries and spelling; they cannot force the recognizer to emit the expected pronunciation.
Keep homophonic source spellings when acoustics cannot distinguish them. A longer sung vowel
does not by itself authorize adding kana or changing a word.

### Two concrete recognizers

| Recognizer                                        | Why test it                                                                                                | Local contract and limitation                                                                                                                                                       |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Existing RomajiASR HuBERT                         | Singing-specific model already bundled; currently used to score supplied candidates, not freely transcribe | Reuse pinned `SINGING_FILES` and MPS loader. Free greedy and prefix-beam N-best decoding; mixed mora/phone tokens need expansion. Same weights, a new decoding/reconciliation path. |
| `sakasegawa/japanese-wav2vec2-large-hiragana-ctc` | A separate acoustic model outputs hiragana directly, plus an auxiliary phone head                          | Apache-2.0, 315.6M parameters, about 632 MB checkpoint. Speech-trained: published speech error rates and the author's M2 runtime claim do not establish singing quality.            |

[RomajiASR inference](https://github.com/Xiantaidu/RomajiASR/blob/79f92eedc7e8f87ca3bc4dcf5d3178cb68c550af/src/infer.py)
supports greedy/beam, N-best and optional phoneme language models. Start with **no language
model or lyric-conditioned bias**, using the existing
[v1.0.0 checkpoint](https://github.com/Xiantaidu/RomajiASR/releases/tag/v1.0.0).
The second model's [card](https://huggingface.co/sakasegawa/japanese-wav2vec2-large-hiragana-ctc)
reports long-vowel and small-kana weaknesses. Its two heads share an encoder and count as
one model, not independent confirming votes.

Pin the kana checkpoint to Hugging Face revision
`d30d246cd24a225821d03d183de7bb2e769e18df`, with checkpoint SHA-256
`1c8d97f2c01560da21df4095cea800f0b6f12dd1269c8e2233e6db659b502e14`, and its
[inference/model source](https://github.com/nyosegawa/hiragana-asr/tree/f78b27ce0b897d2a5db217275c6730fc53b1fcaa)
to `f78b27ce0b897d2a5db217275c6730fc53b1fcaa`. Record and verify the configuration,
feature-extractor, vocabulary and implementation hashes too. Instantiate the 24-layer
dual-head graph from pinned configuration, load the complete checkpoint strictly on CPU,
then move to MPS. Avoid implicitly downloading a second base-model weight set. Measure FP16
against FP32 on calibration inputs before choosing precision.

Do not change tokenizer just because it is different. [Haqumei](https://github.com/o24s/haqumei)
may later supply dictionary reading candidates, but it cannot hear authorial readings and
its source mapping needs its own adapter. Note/mora-aware decoding is a later ablation with
[published Japanese singing precedent](https://www.isca-archive.org/interspeech_2019/suzuki19b_interspeech.pdf),
not a ready checkpoint. Neither is part of this first implementation.

### Recognition and mapping contract

Python owns acoustic decoding, token-to-phone expansion, phone-to-kana candidates and
phonetic reconciliation. The existing romanizer owns original/normalized UTF-8 mapping and
kana-to-romaji display conversion. Rust owns final validation, protected edits, snapshot
selection and atomic persistence; Python cannot write app documents.

Save a private, versioned recognition record containing audio/stem hashes, exact Rust-exported
sample bounds, sample rate, model/config/vocabulary hashes, decoder settings and version;
raw token IDs, normalized phones/kana, ranked hypotheses and acoustic scores; and original
frame indices with the model's convolution stride/receptive-field convention. A separate
reconciliation record adds track/snapshot/revision/conversion identity, occurrence ID,
original byte span and expected text, proposed kana/romaji, mapping status and verifier evidence.
Unknown tokens remain explicit. All audio, lyric-bearing hypotheses, references and per-word
ledgers stay outside git under `/private/tmp/romaji-audio-first-private` with restrictive
permissions; only tools, synthetic fixtures and aggregate results are published.

For RomajiASR, retain raw token identity through ordinary CTC blank/repeat rules before
expanding mora tokens. Combine phonetic-equivalent N-best hypotheses without counting them
as different supporting readings. Pruned beam scores are approximate; recompute complete
candidate CTC likelihoods over the same frames for selection. Keep sequence length, frame
count, raw score and the calibrated decision score; freeze length handling and margins on
calibration data rather than comparing uncalibrated scores from different models.

Map phones to kana with an explicit tested inventory, including nasals, geminates, small kana,
particles and long vowels. Preserve source kana spellings when multiple spellings share the
observed phones. An ambiguous phone-to-kana conversion must remain a set of alternatives,
not a guessed unique transcription. English/unsupported phone runs remain unassigned.

Reconcile within the exported occurrence window using monotone phone edit alignment and
exact, unique neighboring matches. Require at least two matching phones on each available
side; line-edge proposals require the entire remaining envelope to match uniquely. A patch
must cover one to four complete original displayed words, preserving their byte ownership.
Insertions/deletions, multiple valid attachments, cross-line matches and partial-word changes
are diagnostic results initially. No substring search across choruses or borrowed timestamps.

A verified changed reading becomes an existing source-anchored `ReadingRepair`: original
Japanese remains intact, while explicit kana drives both hiragana and romaji. Spaces in a
grouped correction highlight together, following current behavior. For this first pilot,
unanchored lyric rewrites remain offline; a kanji word can still receive a previously unknown
kana reading if its envelope is unique. There is no kana → kanji → canonical-reading round trip.

## Steps

1. **Build the blind decoder and reproducible comparison first.** Add an offline runner for
   RomajiASR greedy and beam decoding (initial width 32, N-best 8, no LM, no insertion/length
   bonus), then the separate kana recognizer with greedy and the same bounded beam search.
   Compare against the shipped Whisper Japanese transcription → Cutlet → phones path on
   identical audio windows. Capture recognition output before the evaluator opens labels or
   source lyrics. Reuse cached Kim vocals for all fourteen songs and original PJS vocals;
   original mixes are a separately reported ablation. No new Spotify recording is needed.
   Keep whole PJS clips; commercial windows come from Rust and retain their 30-second cap.
   Report incompatible model loads, unsupported spans and memory failures as results.
2. **Measure pronunciation before building a new app path.** Reuse the
   [PJS human monophone labels](https://github.com/UtaUtaUtau/pjs-manual-labels), with their
   CC BY-SA attribution, to score genuinely decoded sequences. The prior forced-boundary
   benchmark supplied the correct phones; this runner must not. Use the existing 80-song
   development partition for decoder/threshold calibration. Freeze the chosen recipe and
   run the remaining twenty as a replay check; their labels were previously opened, so they
   are not fresh holdout evidence. All fourteen commercial songs are development inputs.

   Report phone error rate `(substitutions + deletions + insertions) / reference phones`,
   exact phrase phone matches, unsupported-reference totals, and coverage/precision for
   accepted reading changes separately. Preserve `cl` as an ambiguous reference convention;
   reject undocumented `I/U/O` mappings rather than lowercasing them. Show complete supported
   inventory totals and omitted counts. Phone equivalence is pronunciation evidence, not
   proof of exact kana spelling, kanji text, word boundaries or semantic transcription.

   Freeze a cross-model phone inventory before scoring. Normalization rules must come from
   the published vocabularies, not substitutions discovered in reference results. Where a
   model cannot represent a reference phone, report that cohort separately and compare all
   models on the identical supported cohort. Count unmatched model output as insertions.

   Run all six user-verified Tabi occurrences with previous automatic overrides disabled
   in the isolated input. References are evaluation-only: test whether blind output discovers
   `yamiyo`, four `yukou` occurrences and `hakkairo`, rather than handing those readings to
   the decoder. Record discoveries, misses and wrong readings for each occurrence; three
   distinct words in one song are a regression set, not a generalization claim.

3. **Reconcile the strongest blind output and test corrections.** Keep the original source
   denominator and compare proposals against current source/dictionary readings. In the
   labelled corpus, create a seeded, frozen challenge of alternative valid readings and
   kana substitutions at known phone envelopes, plus unchanged controls. Alter the candidate
   source only, never the audio or evaluation reference. Report these injected-error repairs
   separately from naturally wrong commercial lyrics. The recognizer must produce the same
   saved output regardless of which candidate-source variant the reconciler receives.

   Import the PJS source sentences with pinned provenance. Admit corpus word envelopes only
   when source-to-phone alignment matches the manual phone sequence uniquely; report omitted
   or ambiguous mappings. Inject faults into a copied canonical reading/candidate input,
   not saved user overrides, which are protected. Give the current repair baseline and the
   challenger identical corrupted inputs and audio. Freeze the eligible challenge/control
   list and seed before tuning; correct reference readings remain evaluator-only.

   Require MMS evidence on mix and Kim views using the current gain/margin/probability and
   phrase-coherence gates, followed by freshly computed TIFA timing. When RomajiASR proposes,
   it is no longer an independent confirming model: do not count its forced re-score twice.
   For kana-model proposals, RomajiASR may supply the existing contradiction veto. Preserve
   all existing bounds, protected-span and repeat checks; model agreement cannot replace
   reference-based evaluation. Never use decoder spike times as sung word onsets or offsets.
   PJS uses original vocals and a Kim-derived view, explicitly labelled correlated. Missing
   views are a failed verification, not an excuse to count the same waveform twice.

4. **Publish the result and make an explicit adoption decision.** Add an aggregate report
   with baselines, per-song counts, reading errors, abstentions, gains/losses, runtime and
   memory. Finish the runner and mapping fixtures even if both models fail. Choose one recipe
   on development results; freeze it before the twenty-song replay. The following are
   engineering targets for adopting the new path, not population-accuracy guarantees:

   - At least **20% relative reduction in phone errors** versus Whisper → Cutlet on the
     supported development references, with no higher error rate on the twenty-song replay.
     If the baseline has zero errors, require zero errors and a separately demonstrated
     correction benefit rather than dividing by zero.
   - At least **ten more correctly restored injected-error spans** than the current repair
     path across at least five PJS songs; no incorrect accepted changes on at least fifty
     unchanged control spans across ten songs. Include every eligible challenge/control,
     not a favorable selection after inference. No regression on the six verified Tabi
     occurrences. These counts are openly a controlled test, not ten new real-song fixes.
   - For timing, retain onset ≤150 ms and offset ≤200 ms on labelled corrected phone envelopes;
     report joint correctness as a point estimate with counts and phrase-bootstrap intervals.
     Require no decrease against the baseline on the same accepted/reference units, and
     report changed membership separately. Missing units stay missing.
   - Complete all fourteen cached-song replays on M2 Pro / 16 GiB without an out-of-memory
     failure. Measure cached/full-job latency, process-tree RSS, sampled MPS/MLX allocations
     and system swap separately; disclose sampling limits and background load.

   If a gate fails, keep the challenger offline and document the precise failure plus the
   next hypothesis. This PR can then deliver useful recognition benchmarks without another
   tiny timing change being presented as a breakthrough. Commercial proposals without human
   references remain acoustically supported experiments, not measured correct repairs.

5. **Integrate a passing recipe into Experimental on this same PR.** Preserve original TIFA
   and the two existing buttons. Version the new reading recipe and model manifest; extend
   the Python–Rust evidence protocol explicitly rather than reusing old verification fields
   with different meanings. Rust checks identities, UTF-8 envelopes and all verifier results,
   reconverts explicit kana, then saves the derived reading bundle and fresh timings atomically.
   An invalid, stale, cancelled or unverifiable job leaves the previous bundle selected.

   Corrections remain shared by identical source lines under the existing repeat policy;
   conflicting evidence or a protected edit in any affected repeat vetoes the shared change.
   Timings are always computed for each occurrence independently. Earlier bundles and user
   edits survive reopening, cache clearing and model/romanizer upgrades. Do not transplant
   intervals when regrouping changes displayed words. Report original-source coverage and
   corrected-display coverage separately, preserving the 4,160-word suite comparison.

   If the kana model wins, add only its pinned inference adapter/assets to the Experimental
   runtime, with notices and first-use download size; release models between stages. Update
   README/design docs, rebuild the standalone app and verify relocation/offline cached use.

## Tests and checks

- Decoder fixtures: CTC blank/repeated labels, mora versus split-phone equivalence, N-best
  deduplication, impossible/unknown symbols, finite scores, model/vocabulary mismatch,
  deterministic pruning, and reference/source text isolation. Score phone insertions and
  deletions instead of dropping them. Calibration/replay receipts reject changed inputs.
- Conversion/attachment fixtures: `闇夜`, `行こう`, `ハッカ色`, particles, long vowels,
  geminates, Unicode normalization/UTF-8 boundaries, split original tokens, grouped readings
  with spaces, ambiguous repeats, lyric mismatch and unanchored insertions. Keep the existing
  Cutlet mapping contract; no new dictionary dependency in this pilot.
- Integration, if adopted: nonzero delay, rejected verifier evidence, per-occurrence timing,
  identical-repeat conflicts, protected edits, cancelled/stale jobs, save/reopen and earlier
  version restoration, all three lyric modes, original TIFA bitwise interval comparison,
  silence/instrumental/wrong-verse controls and packaged helper/app smoke checks.
- Add any new fast and full offline checks to `scripts/check.sh`; no model downloads,
  inference or live Spotify calls in the routine gate. Run `bash scripts/check.sh` at the
  final head. Publish aggregate results with exact implementation/model/recipe hashes.

## Out of scope

No manual timing editor, user labelling assignment, cloud inference, model training, new
default TIFA behavior, automatic kanji rewriting or inferred timestamps. English-only spans
need a separate language-capable path: the earlier ledger found Latin letters in 404/726
missing spans, so this Japanese-reading pilot cannot credibly promise full suite coverage.
That historic denominator precedes the one-word merged fix. A separate English recognizer,
Haqumei import, note-constrained decoding and MOSS port are follow-ups driven by this pilot's
failure analysis, rather than additional unbounded experiments in the first deliverable.
