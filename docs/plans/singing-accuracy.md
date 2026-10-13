# More accurate Japanese singing readings and word timing

Status: Draft

## Goal and scope

Improve Experimental toward complete coverage of **sung words** across the fourteen
existing songs, then test unfamiliar songs. Correct abstention on words absent from the
recording is a success. Preserve the original TIFA action and durable per-song versions.

Keep this work in one broad PR, as requested. Use the milestones below to make progress
reviewable without splitting the implementation into other PRs. This remains plan-only
until explicit approval; no new model inference or application changes have started.

**First deliverable:** a reproducible failure report for the fourteen songs, followed by a
language/pronunciation challenger evaluated against the shipped Experimental recipe.
Report gains, regressions and readiness for the Experimental button.

## Decisions and responsibilities

- The implementing agent owns diagnostics, experiment tooling, model-term checks,
  automated evaluation, integration and documentation. Neither app user is assigned
  listening labels or manual timing work.
- Shipping an opt-in Experimental improvement uses the automated gates below. Claiming
  listening-verified accuracy is a separate decision requiring actual reference labels.
  The previous unassigned 500-word audit and absolute 98% commercial-song gate are removed.
- No product choice is outstanding besides approval of this plan. Pyshiro is optional:
  the implementing agent records checkpoint-specific permitted use before downloading,
  and integration/distribution terms before bundling. Unclear terms mean skip that model,
  not stall the rest of the PR or presume permission.

## Starting evidence

The [merged evaluation](../study-reading-evaluation.md) records TIFA at 3,121/4,160 words
(75.0%) and Experimental at 3,434/4,160 (82.5%). Experimental left 726 words untimed.
These fourteen recordings have all influenced development; none is a genuine holdout.
The suite has no comprehensive listening-verified word-boundary reference yet.

The existing evaluation links every track and gives the complete per-song table. The
largest gaps are Bling-Bang-Bang-Born (138), 天天天国地獄国 (130), Just Awake (123)
and Koino Uta (84): 475/726 gaps (65.4%). Keep SAKURA and Tabi no Tochuu, currently
fully covered, as regression sentinels.

## Cheap diagnostic already completed

A read-only join of cached TIFA mix diagnostics with the merged Experimental output
matched all 671 lyric occurrences and 4,160 original word spans: 3,434 had saved fragments,
726 did not. Raw lyric lines matched, and cached diagnostic audio/source/crop identities
matched their case manifest. No model ran and no user data changed.

| Historical TIFA mix reason for those 726 spans | Count |
| ---------------------------------------------- | ----: |
| `token_agreement`                              |   683 |
| `duration`                                     |    25 |
| `unsupported`                                  |    12 |
| `incomplete`                                   |     6 |
| `bounds` / `similarity`                        |     0 |

404/726 missing spans (55.6%) contain ASCII Latin letters; 397 contain only ASCII
characters. This describes source script, not the language actually sung. Latin-bearing
spans account for 101/123 gaps in Just Awake and 95/138 in Bling-Bang-Bang-Born.
Only seven Latin-bearing gaps have `unsupported`; 386 have `token_agreement`.
One of 671 cached crops reaches 30 seconds: a the WORLD occurrence with three missing
words. This supports prioritizing language/pronunciation diagnostics over the duration cap.

These are **historical TIFA mix reasons joined to current missing spans**, not fresh
Experimental rejection explanations or proof of the underlying acoustic cause. The
private inputs are `cases-all14-mix.json`, `tifa-mix-all14.json` and the fourteen merged
Experimental result bundles. Reproduce this join in milestone 1, recording input hashes
and unmatched counts; do not silently substitute cached diagnostics from another recipe.

## Experiments, in priority order

### 1. Diagnose and test language/pronunciation handling

Reuse the existing counter in `scripts/experiment-phonetic-alignment.py` before building
new infrastructure. Extend it only where current evidence cannot distinguish failures.
The minimal diagnostic ledger lives outside the checkout in an explicit private output
root, such as `/private/tmp/romaji-accuracy-private` (directory 0700, files 0600). It and
full lyrics, audio, labels and model evidence must never be published, even as PR logs.
Only aggregate results, synthetic fixtures and general experiment code enter git.

Key rows by recording hash, snapshot, occurrence, original UTF-8 span, conversion and
recipe/model signatures. Include raw and accepted intervals, first rejection reason and
other observable failure flags. Take exact crop sample bounds/origin from the **Rust job
manifest**, extending its exported diagnostics if needed; Python must not re-derive them.
Legacy cached crops retain their provenance and are not represented as fresh Rust output.

Distinguish unsupported phones, wrong reading/text, **not sung / lyric mismatch**, wrong
line/verse, truncated context, short duration, weak acoustics, overlapping voices and
unknown causes. A failed alignment alone cannot establish that a word was not sung.
Audit accepted words too. Freeze original inputs; each trial starts from the same source,
not the previous trial's corrected output.

The shipped Whisper path in `refinement/reading_repair.py` forces `language="ja"` and
uses no lyric prompt. Test changed language handling there first: compare full-context
Japanese-forced decoding with language detection and bounded English/mixed-phrase
retries. Keep transcription blind to downloaded lyrics; source script can nominate a
retry but cannot decide sung language. Avoid the already observed short-crop hallucinations.
Qwen3-ASR is an optional offline comparator, not the shipped transcription path; its
existing experiment also forces Japanese and caps generation at 256 tokens.

In parallel, test bounded pronunciation alternatives for small kana, long vowels,
contractions, particles, sung kanji readings and English spans. Preserve source mappings
through phone conversion; score whole phrases, including null/wrong-text alternatives.
Measure whether Latin-heavy failures originate in conversion, alignment or the Japanese
verifier's unsupported language. A Japanese-only verifier cannot approve English changes;
keep those proposals offline until an independently evaluated English acoustic path exists.
Two MMS stems or two Whisper configurations are views, not independent model votes.

### 2. Recover context and test singing-specific durations

For failures near line boundaries, retry joint neighboring phrases using trusted anchors
and vocal activity. Existing Rust crops use 500 ms before the cue, 300 ms after the next
cue and a 30-second cap. Preserve absolute sample coordinates; align the joint phrase
before assigning words to occurrences, rejecting duplicated or wrong-verse assignments.
Whole-song relocation requires its own monotonic occurrence assignment evaluation.

Benchmark [pyshiro](https://github.com/wavtechyukky/pyshiro) and the
[Japanese SHIRO models](https://github.com/intunist/SHIRO-Models-Japanese) as an optional
independent duration-model challenger. Its singing HSMM is relevant to held vowels and
short consonants. The model description emphasizes female/tenor training material and
warns about low male voices and long segments; measure CPU/RAM on short phrases first.
GPL-3.0 code and unresolved model terms are subject to the responsibility rule above.

Implement an explicit versioned kana-to-checkpoint-phone mapping before comparison.
Fixtures cover long vowels, geminates, moraic nasal, devoicing, palatalization, particles,
silence and word boundaries; unmapped phones and English are rejected, never dropped.
Phone-to-word aggregation must preserve original spans. Check the mapping against the
checkpoint inventory and labelled examples, not merely round-trip self-consistency.
Never distribute times evenly across phones or lower TIFA's 80 ms threshold merely to
inflate retention. Any short-word recovery must pass the same acoustic/reference checks.

### 3. Recover weak repeats and refine boundaries

Use [librosa recurrence](https://librosa.org/doc/main/api/generated/librosa.segment.recurrence_matrix.html)
to nominate repeated sections and [constrained DTW](https://librosa.org/doc/0.11.0/generated/librosa.sequence.dtw.html)
on MMS vocal features to propose target boundaries. Chroma locates sections; it is too
coarse to place words. Librosa is ISC-licensed and adds no model weights for this trial.

The contribution is a better **search window**, not copied timing: a weak occurrence may
have enough phonetic evidence once localized, despite failing full-line alignment.
Warp only from matching source lyrics; retain target occurrence identity and reject high
distortion. Re-align target audio within the proposed region without a timing prior.

The verifying path is RomajiASR CTC on the **target audio**, excluded from DTW proposal
features. Require a complete mapped path, mean phone probability at least 0.45, onset and
offset within 150 ms of the proposal, non-overlap with unchanged neighbors, and the
existing reading-repair gates for any changed pronunciation. Calibrate these proposed
thresholds on development references, then freeze them before final evaluation. Unsupported
languages abstain. Model agreement remains a proxy, not listening truth. This avoids the
circular requirement that a target already have an accepted timestamp before DTW helps.

Test local consonant/onset or pitch-change features only for diagnosed boundary errors.
A note change may occur inside a held word, so it cannot independently accept a word.
Contradictory repeat readings remain withheld; each repeat needs its own acoustic evidence.

### 4. Additional models only for remaining failure classes

Demucs, Kim Vocal 2, MMS, RomajiASR, Whisper large-v3 and Qwen3-ASR have already been
tried. Another conversion of Kim Vocal 2 or unchanged ensemble is not a new experiment.
Benchmark a genuinely distinct separator only if downstream failures implicate separation.
Keep the best-performing components by ablation, not model count.

Singing-recognizer adaptation is a later option if these tracks plateau. Use appropriately
licensed training material disjoint from evaluation singers/songs, never the personal
commercial recordings or their evaluation labels. A local LLM may propose bounded
alternatives but cannot vote on acoustic correctness. Record a concrete training/runtime
proposal before expanding into adaptation.

## Evaluation and precise promotion rules

The fourteen songs are development data. Full-song replays may expose all their results;
we no longer describe selected phrases from repeatedly inspected songs as blind acceptance
material. Automated reference evaluation uses existing human-labelled data, beginning with
[PJS human phone relabels](https://github.com/UtaUtaUtau/pjs-manual-labels) and the
[PJS corpus](https://sites.google.com/site/shinnosuketakamichi/research-topics/pjs_corpus).
The implementing agent owns acquisition, versioned reference import and the evaluation
runner. Corpus and relabel state CC BY-SA 4.0. Their single male singer and roughly
27 minutes of controlled singing limit transfer to commercial mixes. Reserve twenty
whole PJS songs before tuning; use the remainder for calibration. The runner withholds
reserved per-unit results from tuning reports/ledgers until recipe hashes are frozen,
then scores both baseline and candidate together. A tested report filter enforces this;
after inspecting failures, do not reuse that pool as an unseen acceptance set.

Store private reference JSONL with recording hash, occurrence/reference-unit ID, audible
phone/kana sequence, language, onset/offset in recording milliseconds, reference provenance,
annotation version and uncertainty. Compare phone boundaries directly where the corpus
has only phone labels; word metrics require an explicit frozen phone-to-word grouping.
Score/JSUT synthesis times and model-generated labels are not acoustic truth.

For a proposed recipe, all of the following are required before enabling it in Experimental:

1. Full offline regression, identity, mapping, persistence and package checks pass. Fixed
   silence, instrumental and wrong-verse controls admit zero new words or reading changes.
2. On frozen labelled-reference cases relevant to the changed path, compare candidate
   and shipped baseline on identical inputs. Use at least 50 affected units over ten
   distinct phrases; tiny samples remain exploratory. At least 98% of accepted units have
   the correct reference reading and onset within 150 ms, and at least 95% have offsets
   within 200 ms. These are **point estimates**, not confidence-bound gates. Previously
   correct baseline units must remain correct, and supported reading repairs must add no
   wrong replacements. Report phrase-clustered uncertainty separately, plus abstentions;
   use phone or word terminology according to the actual reference granularity.
3. On the fourteen-song suite, require at least twenty additional acoustically supported
   words across at least three songs for a general recovery path, with no lost accepted
   spans or moved baseline intervals outside deliberately repaired regions. A narrow
   reading/conversion bug may qualify through a verified failing fixture instead; report
   it as that specific fix, not evidence of general recovery. Preserve verified Tabi
   readings and protected edits. Publish per-song gains/losses and changed regions.
4. Keep baseline results as selectable versions. Unverified commercial-song outcomes are
   labelled model-supported Experimental results. The reference gates evaluate **newly
   affected paths**, not an assertion that today's entire shipped baseline achieves 98%.
   If relevant reference data are unavailable (for example English singing), that path
   stays offline; other passing improvements can still ship in the same PR.

Coverage keeps the original 4,160-word denominator for unchanged spans, alongside
corrected display totals and reference-unit totals. Track insertions, deletions, absent
sung words and uncertain cases separately so removing lyrics cannot improve the score.
Report onset/offset median, p90/p95 and fractions within 50/100/150/250 ms where references
exist. Do not call a commercial song fully verified without checking the whole performance.

Additional blind listening is optional and currently unassigned, not a merge prerequisite.
Any future adjudicator must understand sung Japanese and identify phone boundaries; use
an audio/waveform annotation tool, export the same private schema, hide system identity
and record uncertain judgments. Do not assign this work to the maintainer or his girlfriend,
make up a staffing/time commitment, or present automated agreement as its substitute.

After freezing the recipe, expand to at least ten new recordings from five artists with
varied voices, speed, held notes and mixed language. Freeze configuration/model hashes
before the first run; results and per-word logs are revealed only after the complete frozen
run finishes. Once inspected or used for tuning, mark the set as development and reserve
new songs for the next holdout. Without acoustic labels, this remains an unseen-song
robustness/coverage check, not a measured accuracy benchmark.

Reuse all fourteen cached recordings. New songs use `scripts/capture-song-suite.py` and
the existing authorized immutable helper; never rebuild it to capture. A macOS permission
prompt requires the user's response if it actually appears, not a planned repeated approval.
Unavailable new recordings do not block testing or shipping improvements to the current set;
broader claims remain pending the new-song evaluation.

## Integration and milestones in this PR

1. **Failure report and first challenger:** reproduce the cached histogram, export missing
   Rust diagnostics, freeze reference inputs, test shipped Whisper language handling and
   pronunciation support. Publish aggregates and a keep/reject decision per experiment.
2. **Context, duration and repeat challengers:** proceed according to measured failure
   classes. Give each a bounded pilot and retain it only when it adds distinct value.
   Failed or unavailable models get recorded outcomes, not endless dependency work.
3. **First integrated Experimental recipe:** combine passing changes, rerun ablations and
   the complete fourteen-song/persistence suite, then package a testable app. Record exact
   components, model revisions, mapping versions, gates, sizes and results in this plan
   and `docs/study-reading-evaluation.md`. Milestones are progress checkpoints, not new
   approval requests within the authorized scope. If none passes, report that result and
   the next concrete hypothesis rather than inventing an accuracy improvement.
4. **Broader validation and documentation:** evaluate available new recordings with the
   frozen recipe; update `docs/study.md` and README behavior/limits. Finish the PR when
   selected improvements and checks are complete; deferred research remains documented.

Python proposes acoustic candidates; the bundled romanizer maps source spans; Rust
validates identity, coordinates, protected edits and atomic version saves. Protocols state
sample rate, recording origin and half-open byte spans; subtract saved delay exactly once.
Pronunciation-only changes preserve source text. Text changes require a new snapshot and
explicit old-to-new span mapping, including insertions/deletions/regrouping. Unmapped
protected edits block the affected replacement. Reconvert and freshly align accepted changes.

Retain both timing buttons, compact Options, all lyric modes and per-song preferences.
Cancellation/failure must preserve saved results; cache cleanup must not remove durable
versions. Upgrading models must not silently rewrite accepted songs. Run models sequentially
on M2 Pro/16 GiB; measure first load and three cached runs, stage/whole-job time, process-tree
RSS, MLX/MPS memory, system pressure, swap and disk/download sizes. Separate those counters
instead of adding unrelated maxima. Prefer accuracy while keeping cancellation responsive.

## Tests and checks

Add offline fixtures for phone mapping, English/mixed input, short/held words, wrong cues,
repeats, absent lyrics, transcription truncation, crop identity and nonzero delay. Test
source-span reattachment, protected edits, stale jobs, regrouping and all lyric modes.
Include negative controls, reference scoring, ledger privacy and frozen-run report release.
Never evenly distribute timings. Reopen all fourteen outputs in isolated private storage.

New deterministic tests join `scripts/check.sh`; downloads/inference remain explicit
acceptance commands. Run the full gate and standalone helper/app relocation checks before
marking implementation ready. Publish aggregates only; no live user study-data writes.

## Further research references

- [Joint pitch/phoneme alignment](https://arxiv.org/abs/2202.01646),
  [chroma/phonetic alignment](https://arxiv.org/abs/2401.09200) and
  [repeated sung-vowel patterns](https://arxiv.org/abs/1701.06078) inform boundary/repeat
  experiments; their results are not Japanese pop benchmarks for our models.
- [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) documents the already tried family;
  changed language/context handling is the relevant experiment.
- [GTSinger](https://github.com/AaronZ345/GTSinger) is a possible later labelled singing
  source; review dataset-specific terms separately from code licensing before use.
- [MOSS-Music](https://github.com/OpenMOSS/MOSS-Music) is deferred pending a viable Mac
  runtime/quantization: its 9.1B model exceeds 16 GiB for BF16 weights alone, and published
  singing results do not establish Japanese accuracy.
- [Kotoba bilingual Whisper](https://huggingface.co/kotoba-tech/kotoba-whisper-bilingual-v1.0)
  has speech evidence and shared Whisper ancestry, not an independent singing vote.

## Out of scope

Manual user timing, acceptance by coverage alone, unrestricted LLM rewrites, cloud inference,
platform/playback changes, publishing private song data, and guaranteeing every song is perfect.
