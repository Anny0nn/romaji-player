# More accurate Japanese singing readings and word timing

Status: Draft

## Goal

Make Experimental understand the words being sung and highlight them accurately across
the fourteen existing test songs, working toward complete coverage before expanding to
new recordings. A wrong reading with a confident yellow marker is a failure. A missing
marker remains preferable to an invented timing.

This PR begins with this plan only. Implementation and model experiments start after
explicit approval, on this same branch and PR. The targets below are proposed experiment
and release criteria, not results or a promise of perfect recognition on arbitrary songs.

## Starting evidence

The [merged evaluation](../study-reading-evaluation.md) records TIFA at 3,121/4,160 words
(75.0%) and Experimental at 3,434/4,160 (82.5%). Experimental left 726 words untimed.
These fourteen recordings have all influenced development; none is a genuine holdout.
The suite has no comprehensive listening-verified word-boundary reference yet.

| Recording            | Experimental | Missing words |
| -------------------- | -----------: | ------------: |
| SAKURA               |      265/265 |             0 |
| うれしくて           |      363/423 |            60 |
| departure!           |      209/221 |            12 |
| spiral               |      238/245 |             7 |
| Koino Uta            |      223/307 |            84 |
| Tabi no Tochuu       |      153/153 |             0 |
| NEVER SAY GOODBYE    |      367/430 |            63 |
| Just Awake           |      183/306 |           123 |
| the WORLD            |      135/153 |            18 |
| 色彩                 |      269/291 |            22 |
| 君のせい             |      259/270 |            11 |
| 今世大革命           |      188/246 |            58 |
| Bling-Bang-Bang-Born |      335/473 |           138 |
| 天天天国地獄国       |      247/377 |           130 |

The four largest gaps account for 475/726 missing words (65.4%). Start diagnostics
there, while retaining the two fully covered songs as regression sentinels. The source
track links and exact recordings are identified in the existing evaluation.

Experimental already combines Demucs and Kim vocal separation, TIFA, MMS acoustic
views, RomajiASR verification and full-song Whisper large-v3. Previous experiment tools
also ran Qwen3-ASR and LLM reading proposals. Adding another vote from the same model,
or repeating those runs unchanged, is not a new approach.

Current code supplies concrete hypotheses, not established causes of the 726 gaps:

- `src/study/alignment.rs` crops from 500 ms before a supplied line cue through
  300 ms after the next cue, capped at 30 seconds. Incorrect line boundaries can exclude
  the right audio before any word model sees it.
- `tifa/tifa_helper.py` can omit unsupported pronunciations and rejects intervals shorter
  than 80 ms. Fast words might need a different acoustic treatment; simply lowering that
  limit could admit incorrect paths.
- The existing Qwen experiment forces Japanese and caps generation at 256 tokens.
  Language routing, context and truncation deserve separate measurement on mixed lyrics.
- Two separated inputs to MMS remain two views of one model. They do not provide two
  independent recognizers or calibrated correctness probabilities.

## Approach

Keep the original TIFA action stable. Develop challengers offline from explicit private
recordings, then promote only measured improvements into Experimental. Reuse cached
audio and evidence; do not re-record songs or change the authorized capture helper.

### 1. Explain the failures before selecting models

Extend the existing experiment tools with a versioned, private diagnostic ledger, keyed
by recording hash, source snapshot, occurrence, original UTF-8 span, conversion signature
and recipe/model hashes. Record source cue, exact crop sample bounds, pronunciation
support, token/path completeness, rejection reason, raw interval and each verifier's
evidence. Store both the first failing gate and all observable failure flags so one early
rejection does not hide a second problem.

Separate unsupported phones, wrong reading/text, wrong line/verse location, truncated
context, short interval, weak acoustics, overlapping voices and unresolved cases. Initial
labels are hypotheses until evidence or listening confirms them. Include already accepted
words in the audit: missing words are not the only possible errors.

Freeze the existing input documents and model versions. Compare each challenger against
the same baseline, then run ablations before combining winners. Do not repeatedly feed
the previous experiment's corrected output into the next baseline.

### 2. Test structural and pronunciation fixes first

These experiments reuse available models and target failures that model size cannot fix.

| Experiment               | Concrete change to test                                                                                                                                                                                                                      | Evidence needed to retain it                                                                                                                                                              |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Adaptive phrase context  | Retry failed regions with neighboring lyric lines and overlapping acoustic windows; use trusted surrounding anchors and vocal activity to propose bounds. Align the joint phrase before assigning words back to occurrences.                 | Fewer wrong-line/edge failures, correct reference onsets, no duplicate assignment to adjacent lines. Silence detection proposes cuts; it does not prove word boundaries.                  |
| Pronunciation lattice    | Preserve original spans while offering bounded kana/phone alternatives for contractions, long vowels, small kana, particles, sung kanji readings and Japanese/English spans. Score complete phrase paths with a null/wrong-text alternative. | Correct sung reading wins independent acoustic checks; unsupported symbols and invented readings are withheld. Orthography normalization must not erase audible distinctions.             |
| Language/context routing | Compare the existing blind Qwen3/Whisper paths with automatic or explicit per-phrase language choices and sufficient output budget. Keep transcription blind to downloaded lyrics.                                                           | Lower reference kana/phone or English word error on the affected spans; no new hallucinations on instrumental/wrong-verse controls. A new configuration is not an independent model vote. |

For longer windows, constrain search by neighboring trusted occurrences and retain original
sample coordinates. Do not let a repeated chorus elsewhere in the recording provide a
plausible but wrong match. Start with bounded neighboring windows; whole-song relocation
requires a separately evaluated monotonic occurrence assignment. Correcting an alignment
crop need not rewrite the downloaded lyric snapshot.

Reading proposals retain Japanese source text when only pronunciation differs. Actual
lyric substitutions create a new snapshot with an explicit old-to-new span map. Insertion,
deletion or word regrouping must be represented in that map and evaluated against the
audible reference; deleting difficult words cannot improve the score. Unmapped protected
edits block automatic replacement of the affected region. Keep earlier complete versions.

### 3. Benchmark a singing-specific duration model

Privately evaluate [pyshiro](https://github.com/wavtechyukky/pyshiro) with the
[Japanese SHIRO models](https://github.com/intunist/SHIRO-Models-Japanese) as a challenger
to current CTC alignment. It uses a duration-explicit HSMM and Japanese singing models,
offering a different hypothesis for sustained vowels, short consonants and word boundaries.
Aggregate measured phone boundaries into the existing displayed words; never apportion
word times equally across phones or morae.

The model author describes 17.8 hours of training audio, mainly female voices with some
tenor material, and warns about low male voices and long segments. Test both male and
female recordings, short words, held vowels and dense passages. Use short, overlapping
phrases and measure CPU runtime/RAM first. Apple Silicon performance is unverified.

Pyshiro's GPL-3.0 code and the model repository's unclear weight redistribution terms
make this an isolated research candidate, not a selected bundled dependency. Resolve
permitted research use before obtaining weights, and code/model distribution terms before
any product integration; if that cannot be done,
retain the experiment findings and use the other paths. A forced aligner's successful path
is not evidence that the supplied words were actually sung.

### 4. Use repetitions and musical boundaries as supporting evidence

Where identical lyrics recur, use vocal phonetic features and constrained dynamic time
warping to propose boundaries in the weaker occurrence. The repeat itself must have
matching acoustic content and independently supported target words. A clearer chorus
can suggest a pronunciation, but timing remains specific to each performance. Do not
copy timestamps, average a changed verse, or let a strong repeat override contradictory
singing in another occurrence.

Reuse librosa's [recurrence matrix](https://librosa.org/doc/main/api/generated/librosa.segment.recurrence_matrix.html)
and [constrained DTW](https://librosa.org/doc/0.11.0/generated/librosa.sequence.dtw.html)
implementations for the prototype. Chroma can nominate repeated sections, but the word
warp uses vocal phonetic features; reject low-support or highly distorted paths. This
adds no new model weights. The library is ISC-licensed; measure bounded-window CPU cost.

For remaining boundary errors, test local consonant/onset and pitch-change features around
existing phonetic candidates. A note onset is not necessarily a word onset, and a sustained
word may cover multiple notes. Such features can refine an acoustically supported boundary;
they cannot manufacture a missing word. Both experiments remain hypotheses for Japanese
commercial recordings, supported by research precedents rather than a ready-made solution.

### 5. Add heavier models only for diagnosed residual errors

If remaining failures are separation artifacts, benchmark one demonstrably different vocal
checkpoint against the existing Kim Vocal 2 and Demucs outputs. Identify the exact base
weights first: another conversion of the same Kim model is not a new challenger. Compare
final reading and timing accuracy, not just a separation leaderboard score.

If failures instead reflect unseen singing pronunciations, explore a singing recognizer
adaptation using licensed, acoustically labelled Japanese singing data. Keep training
singers/songs disjoint from evaluation, and never train on the fourteen personal commercial
recordings or their test labels. This is a later proposal if the earlier experiments plateau,
not a dependency for this implementation. A local LLM may suggest bounded alternatives;
its semantic preference cannot accept a reading or contribute an acoustic verification vote.

## Accuracy and experiment gates

Keep the fourteen-song development benchmark and add an independently labelled listening
audit. This is developer evaluation, not a manual timing workflow for app users. Labels must
come from the audible performance, not dictionary output, agreement between our models,
or a musical score's nominal timing. If qualified listening adjudication is unavailable,
report only coverage and model agreement, and leave accuracy-dependent promotion pending.

Define word onset as the first audible phone belonging to the displayed word and offset
as the last audible phone, including held vowels but excluding following silence. Annotate
ambiguous/overlapping cases as uncertain and report their count rather than silently
discarding them. Keep audible sung readings alongside boundaries; preserve unvoiced
consonants, long-vowel distinctions and English spans in the reference.

1. Build a development audit of at least 200 words across all fourteen songs, including
   retained and rejected words, all fifteen automatic reading changes, the user-reported
   departure! region and the verified Tabi readings. This diagnoses and calibrates gates.
2. Before tuning, reserve separate phrases with at least 300 words across all fourteen
   songs for a blind acceptance audit. Group repeated phrases together so one chorus
   cannot appear in both pools. Stratify retained/missing words, vocal type, fast passages,
   sustained notes and mixed languages. Keep system identity hidden during adjudication.
   These held-out phrases still do not make the fourteen songs unseen recordings.
3. Report retained coverage, correct sung-reading rate, onset/offset absolute error
   (median, p90 and p95), and joint correctness: correct sung word with onset within
   150 ms. Report fractions within 50/100/150/250 ms as well. The proposed promotion
   target is at least 98% joint correctness among accepted, adjudicated words and at
   least 95% offsets within 200 ms, with counts and uncertainty intervals. Separate
   newly recovered words from the already accepted set; report each song and stratum.
   Record sampling probabilities and report stratified estimates rather than treating an
   oversampled difficult-word audit as the song population. Group uncertainty estimates
   by phrase/song; repeated words are not independent observations.
4. A challenger must improve correct recoveries on its targeted failure class without
   observed regressions on previously correct audit words or verified readings. Require
   zero accepted new words/readings on the fixed silence, instrumental and wrong-verse
   controls. If it fails, keep it offline and explain the tradeoff; do not relax the gate
   solely to reach a coverage target. A small audit cannot establish 98% population accuracy.
5. Preserve the original 4,160-word coverage denominator for comparable unchanged spans.
   Also report corrected displayed-word totals and a fixed listening-reference denominator,
   including insertions/deletions and uncertain references. Full coverage is only a
   diagnostic milestone; call a song fully verified only after its entire performance is
   checked, including already yellow words and untranscribed singing.

Use [PJS](https://sites.google.com/site/shinnosuketakamichi/research-topics/pjs_corpus)
and its [human-relabelled phone timings](https://github.com/UtaUtaUtau/pjs-manual-labels)
for an additional Japanese phone-boundary sanity check, subject to their terms. These
controlled recordings do not substitute for the commercial-song listening audit. Existing
JSUT score times remain unsuitable as acoustic boundary ground truth.

PJS contains one male singer and about 27 minutes of singing. Use the human relabel
rather than assuming the original labels are exact. Corpus and relabel both state
CC BY-SA 4.0; keep attribution and evaluation inputs separate from the app package.

After freezing a winning recipe, evaluate at least ten genuinely new songs from at least
five artists, including unfamiliar voices, rapid singing, long notes and code switching.
Reserve whole recordings and all their repeats; do not tune on their outcomes. A failed
holdout can become development data only with that change recorded and a fresh future
holdout. Expansion follows improvement of the current list and does not block the initial
diagnostic work. General claims about almost any Japanese song wait for that evidence.

## Product and resource boundaries

Only validated winners enter Experimental; retain the two existing timing buttons and
compact Options. Use staged progress and cancellation. Cache reusable intermediate
evidence by audio/model/recipe identity, with cleanup separate from durable user results.
Never clear accepted saved timings when an optional model fails or a job is cancelled.

Python owns acoustic candidate generation and inference. The bundled romanizer owns
conversion and its source-span mappings. Rust validates identities, coordinates, protected
edits and complete result bundles before atomically saving. Any new crop/phone protocol
must declare sample rate, recording origin, half-open source spans and coordinate units;
subtract the saved delay exactly once when saving playback-derived times. Reconvert and
freshly align accepted reading/text changes rather than attaching old display offsets.

Preserve existing user corrections, prior automatic versions, per-song preferences and
repeat-reading safeguards. Restore/reopen must reproduce the selected version in all
three lyric modes. Model upgrades do not silently rewrite existing accepted songs.

Run models sequentially on the M2 Pro/16 GiB machine. For each shortlisted configuration,
measure first-load and three cached runs, per-stage and whole-job time, process-tree RSS,
MLX/MPS allocations, system memory pressure and swap change. Do not add unrelated peak
counters and call the sum a memory measurement. Investigate memory-pressure failures
before packaging; reduce window/batch sizes first. Record extra download/disk sizes.
Prefer accuracy over an arbitrary speed cutoff, while keeping cancellation usable.

## Steps

1. After approval, add diagnostic/replay schemas, fixtures and the frozen benchmark
   manifest; establish the audit protocol and baseline. Keep private inputs outside git.
2. Test adaptive context, pronunciation support and language routing individually. Publish
   aggregate failure counts, accuracy evidence, runtime and negative results in
   `docs/study-reading-evaluation.md`.
3. Run the isolated duration-model challenger and bounded repeat/boundary experiments
   where diagnostics justify them. Compare both individual and combined effects; stop
   adding models that provide no independently verified improvement.
4. Select the smallest passing recipe, or document that none passed. Before integration,
   record its exact model revisions, terms, gates and protocol changes in this plan; a
   material change in scope requires renewed approval. Package only validated components.
5. Integrate the selected Experimental recipe, test persistence and the standalone app,
   and update `docs/study.md`, README usage/limitations and measured evaluation results.
   Keep unproven experiments outside the shipping path. Record remaining gaps explicitly.
6. Freeze the recipe and evaluate the new-song holdout before claiming broader accuracy.

## Tests and checks

- Offline regressions for unsupported kana, contractions, mixed languages, short words,
  long vowels, wrong cues, adjacent/repeated verses and truncated transcription.
- Synthetic and recorded-feature tests for sample-rate/origin conversion, nonzero delay,
  overlap, out-of-bounds intervals, null paths and disallowed zero/evenly distributed times.
- Span mapping and reattachment tests for regrouping, insertions/deletions, repeats,
  protected edits, stale jobs, recipe changes and reconversion in all lyric modes.
- Negative acoustic controls and blinded audits above, with exact input/model identities;
  generated references or hypotheses must never be counted as listening truth.
- Full fourteen-song replay and reopening checks; no writes to the user's live study data.
- New deterministic tests join `scripts/check.sh`; network, model downloads and long
  inference stay explicit acceptance commands. Run the full gate and standalone helper/
  app relocation checks before marking implementation ready.

## Research references and limits

Research consulted 2026-10-13. Sources below motivate experiments; they do not establish
results for our suite or Apple Silicon compatibility.

- [Pyshiro](https://github.com/wavtechyukky/pyshiro) and
  [SHIRO Japanese models](https://github.com/intunist/SHIRO-Models-Japanese): singing
  duration-model challenger; voice coverage, licensing and local performance need checks.
- [Joint pitch/phoneme lyrics alignment](https://arxiv.org/abs/2202.01646): evidence for
  musical/phonetic boundary features, not a released Japanese model for our hardware.
- [Chroma and singing phonetic features](https://arxiv.org/abs/2401.09200): a classical
  singing alignment precedent; do not transfer its reported accuracy to Japanese pop.
- [Recurring patterns and canonical time warping](https://arxiv.org/abs/1701.06078):
  repeat-based alignment research on other languages; our bounded repeat experiment is
  an adaptation hypothesis.
- [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR): source for the already tried model
  family. Compare changed context/language handling, not another identical ensemble.
- [GTSinger](https://github.com/AaronZ345/GTSinger): possible later multilingual singing
  evaluation/adaptation data. Verify annotation provenance and dataset-specific terms
  separately from code terms; controlled singing is not a substitute for mixed recordings.
- [MOSS-Music](https://github.com/OpenMOSS/MOSS-Music) and its
  [model card](https://huggingface.co/OpenMOSS-Team/MOSS-Music-8B-Thinking): a distinct
  music-trained transcription candidate, deferred. Its 9.1B parameters exceed 16 GiB
  for unquantized BF16 weights alone; official runtime is CUDA-oriented and published
  singing results do not establish Japanese accuracy. A validated Mac quantization would
  be a separate feasibility experiment, not a dependency of this plan.
- [Kotoba bilingual Whisper](https://huggingface.co/kotoba-tech/kotoba-whisper-bilingual-v1.0):
  Japanese/English speech evidence and shared Whisper ancestry; defer unless language
  diagnostics justify a comparison. It cannot count as an independent singing verifier.

## Out of scope

Manual word timing, automatic acceptance based on coverage alone, arbitrary LLM rewrites,
cloud inference, new platforms, replacing Spotify playback, a public training-data release,
training on personal commercial recordings, and a guarantee of 100% on every song.
This draft adds no models, application changes or new downloads.
