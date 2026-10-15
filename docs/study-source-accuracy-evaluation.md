# Source-aware accuracy work

Status: research in progress on PR #5; no timing recipe promoted.

PR #4 merged at `21a8286`, retaining all 61 initial measurements. The fixed ten-song
set is **2,210/2,927 groups (75.5%)**, with 717 gaps. Its seven-low/three-high selection
and original denominators stay frozen in the [catalog](study-song-catalog.md).
The [approved plan](plans/source-first-accuracy.md) targets substantive gains across
multiple difficult songs, rather than completing after a small or null trial.

## Exact source ownership

The romanizer previously split unknown dotted kana into displayed words without
mapping their individual source spans. `ゲ・ン・カ・イ` became `ge/n/ka/i` with four
unmapped words. The converter now proves each ordered kana-to-romaji correspondence
and maps the four original pieces individually. Output spelling and group count stay
the same. Mixed half-width kana uses the existing normalization boundary proof;
an inexact reconstruction still keeps the fallback.

Nine additional regression cases cover exact ownership, rejected partial mappings
and source-anchored reading edits after reconversion. All 74 romanizer tests pass.
This establishes mapping correctness, not additional measured commercial word timing.

## Singing-trained English boundary challenger

[HubertFA-combined](https://huggingface.co/Silasimo/HubertFA-combined/tree/f20e23ab12596d914b2adfcbeb8882180dd92fac)
provides a singing-trained alignment head and a 39-phone ARPAbet inventory plus
silence. Its [Apache-2.0 inference source](https://github.com/wolfgitpr/HubertFA/tree/b3f086966946255a05b0ccb69c865c8e3e806e0a)
is available, unlike the missing SingAlign toolkit. The encoder is pinned
[Chinese HuBERT](https://huggingface.co/TencentGameMate/chinese-hubert-base/tree/fce0375452b1dd6c080ac3248d423d4d037bc831).
The head weights are CC-BY-NC-SA-4.0; the encoder is MIT. Research weights and corpus
files remain outside Git and the app. The source license is retained in
`scripts/third-party/HubertFA-LICENSE`.

The new adapter verifies every asset's size/SHA-256, uses restricted `weights_only`
loading, checks checkpoint configuration and vocabulary, and strictly loads every
inference parameter. Only seven named, shape-checked training-statistic buffers are
omitted. It does not create missing layers. It imports the pinned inference modules
and removes only plotting dependencies from the decoder. The released head does not
include the nonlexical checkpoint required by upstream's full CLI; this adapter makes
no breath-detection claim.

The adapter retains the 44.1 kHz /10 ms output clock and nearest 20 ms HuBERT feature
grid, including ties-to-even rounding. It uses existing SciPy polyphase resampling
instead of adding torchaudio, and follows upstream's raw, unnormalized waveform input.
There is no added left padding. These preprocessing choices are recorded in receipts.

The development comparison uses the already opened NUS ADIZ song 01: 12 phrases,
146 human phones and 37 human `sp` word groups. It is a supplied-phone boundary test,
with no gold spelling. JLEE song 05 remains reserved; this runner offers no heldout
operation and does not open or hash its annotation file.

| ADIZ development measurement         | Aligned | Within onset ≤150 ms and offset ≤200 ms |
| ------------------------------------ | ------: | --------------------------------------: |
| Complete supplied-phone paths        | 146/146 |                         129/146 (88.4%) |
| Complete human word groups           |   37/37 |                           32/37 (86.5%) |
| Word groups with unmasked mean ≥0.45 |    0/37 |                      No accepted groups |

Both CPU and MPS produce the same correct counts. This is better boundary evidence
than the earlier speech IPA pilot's 67/109 complete phone paths and 10/17 accepted
word groups, with different acceptance sets. It remains below an integration-quality
result: five word groups have excessive error, and the 37-group descriptive Wilson
interval is 72.0–94.1%. No model's output supplies a gold reference.

The model's decoder confidence is conditioned on the supplied phone sequence. Its
unmasked frame probabilities also do not behave like the existing Japanese recognizer's
probabilities. Neither is accepted as independent lyric verification. Audio-only CTC
IDs are saved as observations, without claiming that they establish spelling. A next
English trial needs a separately tested lexical verification path and wrong-target
controls, rather than lowering a threshold to raise commercial coverage.

| M2 Pro /16 GiB, four Torch CPU threads |  Load | Inference after load | Lifetime peak process RSS | End MPS driver sample |
| -------------------------------------- | ----: | -------------------: | ------------------------: | --------------------: |
| MPS                                    | 4.3 s |                1.7 s |                   0.81 GB |               1.56 GB |
| CPU                                    | 2.7 s |                1.9 s |                   1.51 GB |                     — |

These are serial, cached-asset development runs. RSS and driver allocation overlap
and are not added or called total unified-memory use. Loading includes asset verification.
The initial unrestricted-thread run took 4.6 seconds after load. The head and encoder
downloads total approximately 432 MB, apart from small source/config files.

Reproduce with an existing experimental environment and privately acquired reference
manifest (the same `development`, `heldout`, `songs` format as the earlier NUS runner):

```sh
.venv-experimental/bin/python scripts/benchmark-hubertfa.py fetch \
  --model-directory /private/tmp/romaji-hubertfa-research
.venv-experimental/bin/python scripts/benchmark-hubertfa.py run \
  --model-directory /private/tmp/romaji-hubertfa-research \
  --manifest /private/tmp/romaji-nus-private/reference-manifest.json \
  --output /private/tmp/romaji-hubertfa-development-mps --device mps
```

Completed phrase checkpoints bind the recipe and observation checksum; altered data
or identities are refused. Resume uses only authenticated completed observations.
Seven offline contract tests cover clocks, inventories, ownership, protected storage,
changed assets/checkpoints and abstentions. Normal repository checks never load models.

## Fresh local Japanese-romaji windows

`scripts/probe-local-romaji.py` tests a deliberately selected Japanese-romaji hypothesis
on the frozen 嘘 recording. Its source remains the original pre-romanized LRCLIB snapshot;
no alternate Japanese record was verified. Macron expansion, syllabic `N`, apostrophes
and gemination preserve the original word identities and displayed spelling. Thirteen
phone fixtures pass. English lookalikes such as `to` still need acoustic language
selection; successful parsing does not establish Japanese.

The tool verifies the frozen selection, Rust job/source-result hashes, original PCM,
delay, sample clock, model files and posterior frame lengths. It records the current
vocals and posterior hashes privately and reuses them without recording or recognition.
Fresh local TIFA alignment uses actual waveform slices and both observed endpoints.
Each candidate window is evaluated separately; overlapping proposals are not merged
into a recipe that no model observed.

Across 23 eligible crops, 29 local trials produced **zero additions beyond the earlier
one-word full-window proposal** and zero moves. Twenty-two missing-word searches had
no fresh paired anchor. The final run took 4.8 seconds with 1.06 GB lifetime peak RSS.
App data and commercial coverage remain unchanged. This rejects this first window
recipe as a substantive improvement; it does not justify relaxing the accuracy rules.

The accompanying region solver permits at most four groups. Both models must support
every replacement and contradict an old automatic interval before moving it. Fresh,
unchanged outer anchors contain the region. It protects supplied/user intervals,
preserves complete original group ownership and refuses actual overlap rather than
trimming timestamps. Eight offline tests cover these cases. It remains a research
tool pending labelled, wrong-window and commercial evaluation.

## Recognition and boundary agreement

The new collector authenticates the frozen Rust jobs, source snapshots, recordings,
model manifests and stems. It reuses three stems and collects the other four low-set
stems without re-recording. Audio contexts union complete Rust crops, stay at most
30 seconds, and are chosen before recognition. They never supply word clocks.

Source-blind Whisper large-v3 recognizes 172 mix/vocal context views with `language=en`,
no lyric prompt and no previous-text conditioning. Source-bearing reconciliation lives
separately outside Git. Each candidate needs a unique exact multiword match and at
least 0.70 confidence in both views. Its observed midpoint checks occurrence inside
the original cue; Whisper endpoints are never copied, clipped or rescaled.

Fresh TIFA and HubertFA must observe both boundaries within 150 ms. TIFA still needs
positive similarity, 0.90 agreement and 80 ms duration; its actual interval is retained.
The known-phone ADIZ development comparison retains **31/37 envelopes, all 31 correct**
within the labelled limits. TIFA alone retains 35/37, all 35 correct. This tests boundaries
for supplied correct phones, not spelling. The pair's descriptive Wilson interval is
89.0–100%, so it does not certify 98% correctness across songs.

| Frozen song                        | Gaps recognized in both views | Dictionary proposals | CMU fallback proposals |
| ---------------------------------- | ----------------------------: | -------------------: | ---------------------: |
| Just Awake                         |                             0 |                    0 |                      0 |
| Wild Side                          |                            16 |                    0 |                      3 |
| Kyouran Hey Kids!!                 |                             0 |                    0 |                      0 |
| TEENAGE CITY RIOT                  |                            10 |                    1 |                      1 |
| LOST IN PARADISE                   |                            19 |                    7 |                      7 |
| 嘘                                 |                             2 |                    0 |                      0 |
| 天天天国地獄国                     |                             0 |                    0 |                      0 |
| たぶん / CROW / 残酷な天使のテーゼ |                             0 |                    0 |                      0 |
| Total                              |                            47 |                    8 |                     11 |

Latin script does not establish English: the two recognized 嘘 groups obtain no new
timing. This first boundary runner withholds mixed cues. Extended dictionary phones
`ax`, `dx` and `_r` initially block whole cues; the CMU fallback predicts a complete
alternative with the existing LSTM converter. It does not substitute unknown phones,
remove groups or change lyrics. Every alternative still needs both observed boundaries
and both lexical views.

The dictionary trial takes 7.9 seconds after loading, with 0.75 GB lifetime RSS; the
CMU fallback takes 8.6 seconds, with 1.13 GB. Eleven proposals would give 2,221/2,927
(75.9%), with zero losses/moves. **Saved app coverage remains 2,210/2,927.** Full accuracy
and negative checks are still pending; these counts are not listening-verified completeness.

The reproducible sequence is `cache-capped-singing.py`, `transcribe-timing-crops.py`,
`probe-context-english.py`, then `probe-english-boundaries.py --pronunciation cmu-fallback`.
Their `--help` lists private manifests/cache paths. Completed observations bind source,
audio, recipe and record hashes; changed identities or silent overwrites are refused.

## Singing CTC pronunciation veto

The HubertFA adapter exposes its unmasked audio-only CTC probabilities through an
optional observer. No supplied-phone mask influences that head. It shares an encoder
with the alignment head, so those heads are correlated evidence. Its statistics stay
separate from Whisper's word-confidence statistic.

The exploratory gate requires every phone's probability at least 0.45, greedy agreement
at least 0.90, an adjacent qualifying word and paired TIFA/HubertFA endpoints. On opened
ADIZ development material, **3/37 words qualify, all three with correct boundaries**.
The CTC veto rejects 111 fixed wrong-phone substitutions. Those are pronunciation
controls, separate from the 143 wrong-window/verse integration controls. There is no
orthographic gold and JLEE remains unopened. The three-word descriptive Wilson interval
is 43.9–100%; this does not establish a generally calibrated acceptance rule.

Across 189 whole-English commercial cues, the boundary pair finds 137 missing candidates
but the complete dual-view CTC gate adds **zero**. Existing intervals remain unchanged.
The run takes 63.3 seconds with 1.89 GB lifetime RSS. This rejects the first CTC recipe;
it does not justify bypassing pronunciation verification. `benchmark-english-ctc.py`
records the development/control comparison, while `--lexical-mode singing-ctc` selects
the private commercial probe. Neither writes app data.

## MOSS-Music singing transcription pilot

[MOSS-Music](https://github.com/OpenMOSS/MOSS-Music) is a different singing-specific
recognizer. The research bootstrap pins the community
[4-bit checkpoint](https://huggingface.co/mlx-community/MOSS-Music-8B-Thinking-4bit/tree/b14123a419b6254b92d9e55b8a5b6f7285e05c70)
and [MLX runtime](https://github.com/Blaizzy/mlx-audio/tree/70f4add32911bab6f869b824864ad9f1e24dcb97).
Weights are Apache-2.0; runtime source is MIT. `scripts/moss-model-files.json` records
every model artifact, the runtime archive and three Apple Silicon Python 3.14 dependency
wheels. They are installed privately, without changing the app's locked dependencies.
Offline inference verifies files/source, requires `strict=True` and rejects remote
tokenizer code. Generated text is an unverified proposal; timestamps are not word clocks.

The pilot picks a difficult context each from Just Awake and Wild Side using baseline
missing-group counts, then transcribes mix and vocals without lyric input. All four
22.0–29.5-second clips exhaust 1,024 tokens with repetitive output. Loading takes
12.1 seconds; clips take 36.0–53.1 seconds. Largest MLX peak is 6.73 GB; process RSS is
1.19 GB. Those accounting measures overlap and are not added or called total unified
memory. The 6.02 GB checkpoint download/verification takes 329 seconds.

A second diagnostic uses the official timestamp-transcription task in a full chat
prompt with an empty thinking suffix. Both identical Just Awake contexts exhaust
256 tokens again. It takes 25.4 seconds including loading, with 6.61 GB MLX peak.
No generated text or timestamp is accepted as a correction.

[Upstream reports similar repetition](https://github.com/OpenMOSS/MOSS-Music/issues/1)
and says its Hugging Face path was fixed; no confirmed corresponding MLX fix was found.
The [separate MLX port](https://github.com/OpenMOSS/MOSS-Music/pull/3) calls 4-bit/6-bit
execution unverified. This does not prove quantization caused the result or justify
a 10.2 GB 8-bit download. Reject the tested path until a concrete inference change
merits another bounded pilot. Local loading success does not establish singing accuracy.

```sh
.venv-experimental/bin/python scripts/fetch-singing-research.py \
  --output /private/tmp/romaji-moss-research
.venv-experimental/bin/python scripts/transcribe-singing-crops.py \
  /private/tmp/romaji-private/audio-only-pilot.json \
  --asset-directory /private/tmp/romaji-moss-research \
  --output /private/tmp/romaji-moss-pilot
```

## Other recognition frontends

A source-blind [Parakeet TDT v2](https://huggingface.co/mlx-community/parakeet-tdt-0.6b-v2/tree/b8e276dc1b4645dc90ddb6d7b22fa82e9773f685)
pilot reuses the same four contexts and strict pinned MLX runtime. Its CC BY 4.0
checkpoint is 2.47 GB; there is no prompt or exposed token confidence. The first
BF16 run and a separate float32 frontend run produce little matching text for
Just Awake, and empty output on both Wild Side views. Float32 loading takes 5.1
seconds; inference takes 0.25–0.80 seconds per context, with 3.61 GB MLX peak.
This rejects that recipe; fast inference is not singing accuracy. Predicted TDT
durations remain unused. `fetch-singing-research.py --engine parakeet` and
`transcribe-parakeet-crops.py` reproduce the private pilot.

`prepare-asr-transforms.py` tests pitch-preserving 0.75× tempo and four-semitone
pitch reduction on the two original Just Awake contexts, using an installed FFmpeg
only for research. Source-blind Whisper's longest exact text blocks increase to
five/six tokens on these views. That is a text-matching diagnostic, not an admitted
word or correction. Every transformed result is marked text-only: verification
must return to original samples, and transformed timestamps cannot enter app data.

## Source-conditioned acoustic evidence

A new experiment uses the already pinned Whisper large-v3 weights and original
Japanese/English spelling rather than comparing only dictionary-selected romaji.
The decoder receives exact source text. Full-vocabulary token log probabilities,
including EOS alternatives, remain separate from conditional attention confidence.
Exact UTF-8/BPE ownership withholds a token or attention word that spans multiple
original groups; complete pieces may merge, and no timing is split or interpolated.

`observe-source-evidence.py` compares the same candidate on original audio, silence
and another verse. Optional ablation zeros a model-observed word interval, then
compares its word-score drop with disjoint masks of identical length elsewhere.
Human reference clocks are never used to choose masks. These are conditional
observations, not independent recognition or an accepted app recipe. Acoustic
contrast and boundary correctness must be measured together, including negative
controls; a plausible forced sentence is insufficient.

The first smoke test distinguishes one Kyouran Japanese line from silence and a
wrong verse: mean token log probability is −0.72 on original audio, versus −4.14
and −3.82. The difficult Just Awake line gives −9.02, −9.24 and −9.33 respectively,
so it has little contrast. Neither example changes saved coverage.

For English development, [JamendoLyrics](https://github.com/f90/jamendolyrics)
provides manual word starts/ends tied to normalized word text, which NUS lacks.
The [pinned dataset](https://huggingface.co/datasets/jamendolyrics/jamendolyrics/tree/4e7acfcbd1440e68eda7ee8933ef221e5f970501)
contains two chosen tracks marked CC BY: [Cortez — Feel (Stripped)](https://www.jamendo.com/track/1481500/feel-stripped)
and [Rxbyn — Bad Side](https://www.jamendo.com/track/1556580/bad-side).
The metadata does not specify a CC version; none is invented. Artifact hashes,
source URLs and attribution are pinned in `scripts/jamendo-reference-files.json`;
MP3s, lyric text, annotations and per-word results stay private. The first eight
eligible lines per song give **96 reference words across 16 lines**, all development.
This is neither original orthographic transcription nor a representative fast-rock
holdout. The existing NUS JLEE reserve remains unopened.

On those 96 words, forced Whisper attention supplies 96 intervals but only **17**
meet the onset/offset tolerances. Localized contrast retains 21, of which six meet
the timing tolerances. The attention clock is unsuitable for this recipe. Fresh
TIFA/HubertFA instead supplies 56 paired intervals, **53** joint-correct. Using
those observed intervals for the masks retains **34**, with **33** joint-correct
(97.1%; descriptive Wilson 85.1–99.5%). This remains below the accuracy gate and
does not establish general English singing correctness.

The existing 143 negative words contain 17 groups in four whole-Latin cues that
pass the prototype's script filter; 126 are excluded. Six eligible groups have paired
clock candidates, and all 17 are rejected even without the extra wrong-verse
contrast requirement. This weaker negative check cannot certify mixed-language or
Japanese-romaji routing.

A preselected two-cue-per-song cap pilot runs 24 mix/vocal views across twelve cues
and seven low songs. Ten missing groups pass both localized acoustic checks, but
context/interval preservation leaves one timing proposal on 嘘, whose source is
Japanese romaji. There are **zero admissible English additions**, zero lost or moved
intervals, and no app writes. English script is insufficient language evidence;
the 嘘 proposal is kept separate. The pilot takes 205 seconds including loading,
with 3.95 GB MLX peak and 1.45 GB lifetime process RSS, reported separately.
`prepare-cap-source-evidence.py`
and `evaluate-source-cap.py` bind the original Rust crops/results and protect existing
fragment identities even when their crop-relative start is negative.

`prepare-paired-reference.py` supplies the fresh two-model boundary fixture;
`evaluate-source-evidence.py` evaluates closed observations against human clocks.
The all-word denominators remain unchanged. Neither repeated-source timestamps nor
ASR-derived clocks are used to fill gaps.

```sh
.venv-experimental/bin/python scripts/prepare-jamendo-reference.py \
  --assets /private/tmp/romaji-jamendo-assets --download \
  --output /private/tmp/romaji-jamendo-development
.venv-experimental/bin/python scripts/observe-source-evidence.py \
  /private/tmp/romaji-jamendo-development/manifest.json \
  --models "$ROMAJI_REFINEMENT_MODEL_DIR" --ablations \
  --output /private/tmp/romaji-source-evidence
```

## Free Qwen decoding and boundary checks

The previous Qwen experiment forced Japanese even on English clips. The new
`transcribe-qwen-singing.py` comparison pins the official
[Qwen3-ASR-1.7B-hf](https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf/tree/bcd2b5b7f32b480ab5790554cfa8347f246a14f3)
checkpoint, uses its native BF16 precision, and supplies no lyric prompt. Automatic
language selection and explicit English are separate trials. Decoded tokens and
their actual full-vocabulary probabilities are saved; a budget-exhausted view is
withheld before scoring. ASR supplies no word timestamps.

On the 96 Jamendo development words, automatic language selection gives **12 word
errors (12.5% WER)** and 88 exact source matches in unique multiword blocks. All 88
reach the exploratory 0.70 geometric-mean token-probability threshold. This is a
free-decoder statistic, distinct from Whisper word confidence and CTC probability.
BPE pieces spanning words cannot receive invented individual word scores, and
partial UTF-8 pieces must reconstruct exactly. The run takes 20.1 seconds including
5.1 seconds loading; MPS allocated/driver readings are 4.09/4.61 GB and process RSS
is 0.66 GB, reported separately.

Recognition does not settle boundary correctness. Qwen-confirmed TIFA/HubertFA
clocks retain 52 reference words, **49 joint-correct**. A diagnostic requiring
HubertFA's first/last-phone greedy agreement and choosing its actual CTC envelope
retains nine, all nine correct. Nine development words cannot certify a new recipe.
Qwen alone also matches three words in the four eligible negative cues: common-word
recognition is insufficient wrong-verse protection.

The existing native Qwen forced aligner independently gives 92 valid reference
intervals, only **62 joint-correct**. Its TIFA-paired subset gives 50/52 correct when
keeping TIFA's clock. This is forced alignment, separate from free Qwen ASR; sharing
a product name does not establish equivalent accuracy or independent lexical truth.

On the preselected commercial pilot's twelve cues /24 mix-vocal views, free Qwen
finds 31 exact multiword matches across both views, including retained anchors.
Seven missing groups match in both views; the unchanged context/collision overlay
leaves **five proposals: two on TEENAGE CITY RIOT and three on LOST IN PARADISE**.
No saved interval is lost or moved. One view exhausts its token budget and another
detects a different language; both are withheld. These are proposals before the
complete accuracy/negative gates, not five shipped or verified words.

`collect-qwen-lexical.py` reproduces lexical collection from completed observations
without another inference run. It checks model/tokenizer assets, closed-record hashes,
crop identity and exact source ownership. The existing app remains at 2,210/2,927.

## Singing letters and original-script timing

A fresh [Echora checkpoint](https://huggingface.co/hcX02/echora-mms-300m-multilingual-lyrics-forced-aligner/tree/701595f1be1125cce835d4e32fd432358ea8ed9f)
comparison strictly loads both released heads: 30 base vocabulary entries plus the
two special entries used by its 32-output architecture. Its custom terms permit
this private research but restrict redistribution and commercial use; weights do
not ship. `recognize-singing-letters.py` caches unmasked audio-only CTC distributions.
The two heads share an encoder and are not independent votes.

On the 16 original Jamendo clips, the lead stream emits letters without word
delimiters; normalized character error is 159/349 (45.6%). Absence of spaces alone
is not proof of failed recognition. The secondary stream is blank on these clips.
Complete literal-word forced paths give 68/96 correct boundaries on the mix and
77/96 on Kim-isolated vocals. A 0.45 confidence requirement plus TIFA agreement
retains 41 words with 36 correct on the mix and 44 with 39 correct on vocals,
so neither is promoted.
`prepare-reference-vocals.py` creates the position-preserving vocal comparison from
the pinned recordings without using reference boundaries in separation.

An original-script pilot selects three Japanese-gap cues from each eligible low
song before inference: 18 cues, 150 original groups, 72 native-model views comparing
original spelling /selected reading and mix /vocals. 嘘 has no native-script source
and is excluded from this comparison. In 11.5 seconds the aligner returns 489 valid
intervals across all four views. Within-model mix/vocal agreement plus the immutable
overlay leaves five source-script proposals versus four selected-reading proposals.
This is a representation diagnostic, not independent verification or evidence that
kanji input solves the remaining coverage problem. `source_script_probe.py` keeps
original UTF-8 spans and spelling, including punctuation, without merging groups.

## Partial-source and joint-window trials (2026-10-15)

A different decoder now allows an entire unmatched source word to remain unplaced
and consumes unrelated audio without assigning it to lyrics. It retains ordinary
CTC repeat/blank rules inside words, complete phone ownership and original frame
clocks. A mora cannot be divided between source words. The deletion margin compares
actual path scores with the word disabled; it is not a calibrated probability.
This is an experimental extension inspired by
[CTC segmentation](https://github.com/lumaku/ctc-segmentation), rather than a claim
that the upstream implementation solves lyric mismatches.

`benchmark-partial-singing.py` reuses the closed PJS development posteriors and
closes observations before reading human clocks. Across the original 390 groups
and 62 recordings, 388 receive an envelope but only **226 are joint-correct**.
The predeclared probability /duration /margin /adjacency gate retains 164, only
99 correct. Keeping an existing TIFA clock and requiring both endpoints to agree
within 150 ms gives 75, of which 74 are correct. The 12.8-second cached trial
rejects this decoder as a standalone clock; no saved timings change.

On the same 18 commercial Japanese-gap cues, the fresh TIFA comparison adds one
proposal with the forced verifier and two with the partial verifier, with zero
lost/moved intervals. That is **one incremental proposal**, not a substantive
recipe. `probe-partial-source.py` records both methods on identical samples;
none of these observations is promoted.

A separate joint-window experiment selects one previously authenticated context
per low song by baseline gap count before inference. It covers **479 original
source groups, including 218 gaps**, across seven 22.0–29.9-second windows. The
same word groups retain their occurrence and UTF-8 identities when neighboring
cues are joined. Returned clocks reattach by exact owners and sample offsets;
unplaced words stay unplaced. Repeated text is not matched by string search.

Native Qwen forced alignment takes 20.2 seconds for 14 mix/vocal views and returns
658 valid intervals across both views. TIFA takes 6.8 seconds including loading
and retains 550 across both views. Source-blind Qwen recognition reuses the two
identical earlier Just Awake observations and runs only the twelve new views;
two exhaust their token budget and are withheld. The independent native/TIFA
boundary pair plus dual-view lexical/context checks adds **zero** words and
loses/moves zero. Larger context alone does not solve the frozen subset.
`joint_source_windows.py` and its regression fixtures protect repeated-line
ownership, crop bounds, Unicode and negative crop-relative saved starts.

## Source-blind phone witnesses (2026-10-15)

`free_phone_words.py` matches words only after an unconstrained audio-only CTC
decode. Complete observed mora tokens own the word envelope and their actual
probabilities; a token crossing a source word boundary cannot be divided.
The default requires an exact unique word plus two context phones on each side.
This is phonetic correspondence, not proof of kanji spelling. Unsupported source
words remain unmatched without preventing later words from being considered.

`benchmark-free-phones.py` closes observations before opening the same 390 PJS
development references. At the 0.45 probability and 80 ms duration requirements,
180 words qualify, but their free-decoder clocks are joint-correct for only 112.
Requiring both endpoints to agree with TIFA within 150 ms leaves 84 words;
83 TIFA clocks are joint-correct (98.8%; descriptive Wilson 93.6–99.8%). This
does not certify the free decoder as a timing model or a representative pop recipe.
The cached benchmark takes 2.2 seconds.

A complete opportunity check reuses 41 earlier posteriors and collects only 255
missing audio-only caches. It covers all 296 affected cues in the seven low songs,
with **714 original gaps**; the high three songs' three gaps are outside this
comparison. Existing selected/direct/loan pronunciation hypotheses and the explicit
Japanese-romaji hypothesis for 嘘 produce **40 distinct phonetic witnesses**:
3 Just Awake, 1 Wild Side, 7 Kyouran, 3 TEENAGE CITY RIOT, 2 LOST IN PARADISE,
21 嘘 and 3 天天天国地獄国. These are an upper bound before boundary, context and
saved-interval checks, not 40 retained or correct additions. Cached matching takes
7.0 seconds; inference and postprocessing are separate measurements.

Removing the neighboring-phone requirement tests whether a misrecognized neighbor
was the main restriction. All trials retain complete word/token ownership, exact
unique correspondence, the same probabilities and original denominators:

| Matching rule                        | Missing-group witnesses | PJS paired clocks | Joint-correct pairs |
| ------------------------------------ | ----------------------- | ----------------- | ------------------- |
| Two context phones on each side      | 40                      | 84                | 83                  |
| One context phone on each side       | 42                      | 87                | 86                  |
| Unique whole word, at least 4 phones | 42                      | 79                | 78                  |
| Unique whole word, at least 6 phones | 23                      | 36                | 35                  |
| Unique whole word, at least 8 phones | 11                      | 12                | 12                  |

None provides a substantial recipe. The Japanese negative comparison matches zero
of 105 words. The separate English comparison matches zero of 38, but 32 have no
complete representation in this Japanese phone vocabulary; count those as excluded,
not successful English verification. A genuinely source-blind HubertFA head cache
also finds zero complete unique word witnesses on the 96 Jamendo development words.
Do not sweep the commercial English set with that unchanged phone-decoder recipe.

The dedicated Japanese-singing SOFA checkpoint has a separate private CPU contract
pilot. Its complete inference state loads strictly; saved mel settings and the
58-phone inventory, rather than an English phone-set assumption, define the adapter.
The training loss uses per-utterance phone masks: neither its selected-path score
nor unmasked full-vocabulary score is calibrated independent word confidence.
Use it only as a boundary challenger. PJS appears in its training list, so the PJS
contract smoke is not an independent accuracy result. Weight redistribution terms
remain unspecified and the weights are not bundled.

On three preselected 嘘 cues, 28 groups include 14 original gaps. SOFA/TIFA supplies
seven valid paired missing candidates; six also have independent free-phone
witnesses. The immutable-interval overlay leaves **five proposals**, zero lost or
moved intervals. This private prototype needs reproducible adapter and independent
accuracy checks before integration; these are not shipped gains.

```sh
.venv-experimental/bin/python scripts/benchmark-free-phones.py "$PJS_MANIFEST" \
  --recognition "$PJS_RECOGNITION" --cases "$PJS_CASES" \
  --baseline "$PJS_BASELINE" --pjs "$PJS_CORPUS" --output "$PRIVATE_OUTPUT"
```

## Remaining work

The first experiments do not satisfy the plan's multi-song integration target. Continue
with independently verified English runs, local sung-reading alternatives and stronger
anchor evidence. Keep the ten-song set fixed, test new admission rules against the
existing references and negative controls, and report gains, losses and moved boundaries
separately. Do not rebuild the capture helper or ask the user to annotate songs.
