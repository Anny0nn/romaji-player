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

The expanded comparison completes all **172 frozen mix/vocal context clips** in
714.6 seconds, including 4.2 seconds loading. Process peak RSS is 1.22 GB and MPS
allocated/driver readings are 4.09/4.62 GB, reported separately. Eleven views exhaust
their budget. On two further views, the official parser shortens repetitive output:
its returned transcript no longer reconstructs the scored decoder bytes. Withhold
those complete views; never transfer the longer output's scores to the shortened
text. The collector records this reason without aborting other authenticated clips;
a regression fixture protects both the abstention and invalid-probability errors.

`evaluate-qwen-contexts.py` matches each complete source window before assigning
words to individual occurrences. A phrase repeated in neighboring cues cannot be
credited to whichever identical line is inspected first. Both views still require
actual whole-token probability at least 0.70, and fresh TIFA/HubertFA clocks must
pass the unchanged duration/agreement/endpoint checks. Existing fragments remain
protected even when their crop-relative start is negative.

The replay has cached boundary observations for **189 cues /453 original gaps**;
57 other source cues have no cached pair and are outside this timing comparison.
Within the paired subset, 83 missing groups have dual-view lexical matches, 32
also have paired clocks, and preservation/context checks leave **16 proposals**:
two Kyouran, six TEENAGE CITY RIOT and eight LOST IN PARADISE. Zero old intervals
are lost or moved. These are alternative proposals against the original baseline,
not sixteen incremental gains beyond earlier trials or verified shipped words.

All 172 views report English, including the romanized Japanese source contexts.
A separate three-clip PJS diagnostic correctly reports Japanese; explicit Japanese
prefill gives the same three transcripts. Repeating the same 嘘 clip before and
after English/PJS audio gives identical tokens, also identical to the full run.
This rejects a cross-request state explanation for that clip, not the observed
commercial language-routing failure. Source language remains a hypothesis needing
validation. Explicit Japanese prefill on six mix/vocal views from three previously
selected native-source cues finds just one of 18 missing groups with a unique
literal source match and complete scored tokens in both views. This is a lexical
opportunity check, not a new retained timing. The 57 mixed cues without cached
English boundaries contain 178 original gaps; their existing context outputs give
only one further dual-view lexical match. Neither result justifies a bulk repeat
of unchanged alignment models. A third boundary-model intersection on Jamendo also falls short:
Qwen-confirmed TIFA/HubertFA/native-Qwen agreement retains 41 words with 40
joint-correct. Neither expansion establishes a recipe for promotion.

```sh
.venv-experimental/bin/python scripts/transcribe-qwen-singing.py "$AUDIO_CONTEXTS" \
  --model-directory "$QWEN_ASSETS" --language auto --output "$PRIVATE_RECOGNITION"
.venv-experimental/bin/python scripts/evaluate-qwen-contexts.py \
  --suite "$FROZEN_SUITE" --contexts "$CONTEXT_CACHE" --paired "$BOUNDARY_CACHE" \
  --lexical "$ORIGINAL_LEXICAL_CACHE" --observations "$PRIVATE_RECOGNITION" \
  --model-directory "$QWEN_ASSETS" --output "$PRIVATE_REPLAY"
```

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

A separate private projection tests long-vowel correspondence (`ou`/`oo`, `ei`/`ee`
and repeated vowels), preserving complete observed token envelopes and original
word boundaries. It produces 35 missing-group witnesses rather than 40; adding
a `wo`/`o` equivalence gives 36. Both have 78/79 correct TIFA-paired PJS clocks.
The negative results remain zero, with the same 32 English exclusions. This is
not a successful normalization fix; in particular, the production kana converter
already maps the particle を to `o`. Neither private projection changes the app.

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

## Japanese-specific speech recognizer pilot (2026-10-15)

[ReazonSpeech NeMo v2](https://huggingface.co/reazon-research/reazonspeech-nemo-v2)
tests a different acoustic model: a Japanese FastConformer/RNN-T recognizer rather
than another Whisper/Qwen setting. Its published evidence is for speech, not singing.
The private pilot uses the Apache-2.0
[Q8 conversion](https://huggingface.co/sakasegawa/reazonspeech-nemo-v2-GGUF/tree/ed04d9ee2cd156414982a7c0f6123c6fd1093904)
through MIT [speech.cpp v0.8.4](https://github.com/nyosegawa/speech.cpp/tree/d23c49f3233375e3ad4944c880807790b7f490be).
`scripts/reazon-singing-files.json` pins the complete 660,910,656-byte artifact,
SHA-256, immutable source/model revisions and ggml submodule. No weights, cloned
source or new app runtime are committed.

Twenty clips are fixed before inference: the eighteen earlier native-source Kim
cues and two earlier high-gap 嘘 cues. They contain **169 original groups /81 gaps**
and 93.23 seconds of audio. Exact authenticated samples are wrapped as 16 kHz mono
float WAVs; their hashes and original Rust crop owners remain recorded. The CLI
receives only local model/audio paths, explicit Metal/four-thread settings and JSON
output. No model alias, source text, prompt, detection model or microphone is used.

Greedy decoding completes in 22.7 seconds, including 20.8 seconds first loading;
its twenty recognitions take 1.83 seconds. Beam decoding on the same clips completes
in 2.58 seconds, including a 0.21-second load with the shader cache warm; inference
takes 2.34 seconds. The load difference is not a decoder speed claim. Peak process
RSS is 876 MB greedy /847 MB beam; the separate macOS footprint readings are
770/769 MB. These are measured M2 Pro results, not the converter's published M5
speech benchmark extrapolated to singing.

The CLI's JSON exposes transcript text and stop reason but no actual token
probabilities. Decoder-emission timestamps are not used as word clocks. Literal
unique source matches offer six missing-group opportunities with greedy and eight
with beam. Converting closed transcripts with the pinned reading helper, without
song defaults, and requiring complete unique phonetic context gives **seven**
opportunities with either decoder: one on TEENAGE CITY RIOT and six on 嘘. These
sets overlap; they are not retained or verified additions. Two greedy clips are
empty, versus one beam clip. A decoded kanji's dictionary reading is not independent
evidence for choosing a sung reading. No new timings, reading edits or app data are
saved. This bounded pilot does not justify a full-song sweep or promotion.

For reproduction, build the pinned external runtime privately with CMake and the
existing Apple toolchain, verify the model bytes against the manifest, then run:

```sh
"$PRIVATE_SPEECH" asr "$VERIFIED_REAZON_GGUF" --device gpu --threads 4 \
  --decoding greedy --format json "$PRIVATE_CLIP_WAV" > "$PRIVATE_RESULT" 2> "$PRIVATE_LOG"
# Repeat on the identical files with --decoding beam and fresh output paths.
```

## Local pronunciation contrast (2026-10-15)

`contrastive_phones.py` evaluates complete source-owned pronunciations against a
different local competitor: the exact CTC union of every representable same-length
one-phone substitution, including mixed mora/phone tokenizations and ordinary
repeat/blank rules. Substitutions use the model's actual standalone-phone inventory;
consonants appearing only inside mora labels are not invented as standalone labels.
This is an unweighted union, so beating it is stricter than beating each alternative
separately. The margin and blank contrast are likelihood ratios, not probabilities
or proof of kanji spelling. Exhaustive short label-path tests check the forward sums.

The fixed trial uses original TIFA clocks with 120 ms padding, positive union/blank
margins and at least 0.45 mean probability on actual nonblank emission frames. Its
best complete CTC path supplies observed frame endpoints, with the existing 80 ms
minimum and 150 ms TIFA agreement. Paths touching the search edge are withheld;
a narrow emission is never extended to match a word's expected duration. Candidate
scores close before the already opened development reference clocks are read.

On **390 original PJS groups /62 recordings**, 331 pass the lexical check and
79 pass the boundary pair. **78/79 TIFA clocks are joint-correct** (98.7%; descriptive
Wilson 93.2–99.8%). All 390 same-length one-phone wrong-reading variants are rejected.
The cached comparison takes 7.7 seconds. Fresh TIFA observations on the existing
143 mismatch-control words admit zero paired timings: 105 Japanese-phone targets
are representable, while 32/38 English targets are structurally unsupported and
must not be counted as evidence of an English verifier. One Japanese mismatch
passes the lexical check alone, confirming that it cannot replace boundary/context
verification. Seventy-five control groups have a qualifying TIFA search interval
for local scoring; the others already abstain. These legacy posteriors have frozen
actual hashes but lack
the complete newer recognition receipt; that provenance limitation remains explicit.

The identical policy reuses the eighteen earlier native-source commercial cues:
150 original groups /71 baseline gaps. It yields four paired missing candidates
and **one** context/interval-preserving proposal, on Wild Side; zero old intervals
are lost or moved. This is an alternative research proposal against the original
baseline, not an incremental shipped gain. No app timings or readings change.

```sh
.venv-experimental/bin/python scripts/benchmark-contrastive-phones.py "$PJS_AUDIO" \
  --recognition "$CLOSED_PHONE_CACHE" --cases "$FROZEN_ORIGINAL_GROUPS" \
  --baseline "$ORIGINAL_TIFA_OBSERVATIONS" --pjs "$PRIVATE_PJS" \
  --output "$FRESH_PRIVATE_OUTPUT"
```

A separate runtime audit compares the pinned MLX MOSS frontend with the checkpoint's
official-equivalent Whisper extraction on one unchanged 22.01-second crop. Both
return 128×2,201 features. Before BF16, maximum/mean absolute errors are
`4.97e-5` /`2.09e-7`, with correlation above `0.99999999999`; after BF16 the mean
error is `1.41e-7`. This checks feature conversion on that crop, not singing accuracy,
and identifies no material frontend mismatch justifying another unchanged MOSS run.
The diagnostic loads no model weights and uses no transcription output.

## Duration-aware boundary comparison (2026-10-15)

The closed local observations expose a clock-semantics problem. Against the opened
human PJS labels, the CTC word's first emission is a median 38 ms late, while its
last emission is **170 ms early**; its emitted envelope is a median 0.4× the sung
word duration on lexical passes. Only one lexical-pass path touches a padded cut
edge. The earlier free decoder has essentially the same early-ending pattern.
These token-emission peaks are not full phonetic duration boundaries. This diagnoses
the restriction; it does not authorize shifting, extending or interpolating clocks.

The next measured challenger uses the cached
[PySHIRO v2 source/checkpoint](https://github.com/wavtechyukky/pyshiro/tree/49851cd4701d300eaf310b274f7c3b3e594d3824),
with exact sizes/hashes and preprocessing in `scripts/pyshiro-singing-files.json`.
Its HMM bootstrap and duration-aware HSMM refinement emit 5 ms phone boundaries.
Original word envelopes come from their actual first/last phone intervals. Model
likelihood is not lexical confidence; the fixed CTC contrast remains the separate
presence check, and both HSMM/TIFA endpoints must still agree within 150 ms.

The existing adapter had a mapping defect: kana-range input could be reported as
supported even when upstream warned and skipped an unknown mora. The adapter now
proves complete table coverage, rejects unsupported small kana/voiced kana and
leading/invalid length marks, and preserves complete groups. A regression covers
those failures, digraphs, nasal/geminate phones and long vowels. Nothing is dropped
to improve the denominator.

One closed run evaluates the same 62 development recordings and eighteen commercial
cues: 80 inputs in **74.5 seconds**, with peak process RSS **324 MB**. On the original
390 development groups, raw HSMM clocks place 380, of which 329 are joint-correct.
The accepted clock remains TIFA; the comparison below changes the checking role only.
Five deterministic recording-disjoint reporting folds fit no parameters; all use
already opened development data, not a fresh holdout.

| Boundary check plus unchanged CTC lexical gate | Retained original groups | Joint-correct TIFA clocks |
| ---------------------------------------------- | -----------------------: | ------------------------: |
| CTC emission envelope                          |                       79 |                        78 |
| Full-phrase HSMM phone boundaries              |                      264 |                       263 |
| HSMM regions of at most four original groups   |                      183 |                       182 |

The region variant prevents an unsupported English word from withholding every
Japanese word in a mixed phrase. It uses 300 ms padding around observed TIFA search
regions; boundaries are measured afresh, and cut edges remain withheld. The closed
338-region run takes **20.0 seconds**, with peak RSS **262 MB**, including 260 PJS,
41 commercial and 37 mismatch-control regions. Its raw clocks are only 226/390
correct, so smaller context is not a general boundary improvement. No fitted duration
offset or padded timestamp is saved.

On the eighteen commercial cues /71 gaps, the full-phrase combination has two
paired missing candidates and zero final additions. The region combination has five
and leaves only **one** final Wild Side proposal. Both lose/move zero old intervals.
The regional check admits zero of 143 mismatch-control groups, with the same 32
unsupported English groups disclosed above. Neither variant meets the substantive
integration target. The checkpoint's v2 training recordings and separate weight terms
are not disclosed: PJS cannot certify unseen accuracy, and weights remain private.
This trial does not reverse the earlier deferral of shipping PySHIRO.

For a bounded private reproduction, first verify an external checkout and model
against the pin file, then use the existing source-owned case schema:

```sh
PYTHONPATH="$PINNED_PRIVATE_PYSHIRO" .venv-experimental/bin/python \
  scripts/experiment-phonetic-alignment.py hsmm "$AUTHENTICATED_CASES" \
  "$FRESH_PRIVATE_OBSERVATIONS" --model "$PINNED_PRIVATE_PYSHIRO"
```

## Complete duration paths against an acoustic background (2026-10-15)

`scripts/duration_spotting.py` tests a different boundary model on the same cached
recordings. Every target state consumes observed frames; a semi-Markov forward sum
and Viterbi path use normalized discrete duration PMFs. An exact prior-only pass
conditions the complete chain on fitting inside the finite search window, so a
shorter pronunciation/window does not win merely by discarding more prior mass.
Forward/backward boundary marginals expose ambiguous placements without averaging
their clocks. Exhaustive small examples verify sums, measured paths, normalization
and repeated-occurrence uncertainty.

The private pinned PySHIRO adapter compares two backgrounds in identical TIFA
±300 ms windows: an equal mixture over all 123 distinct GMM state outputs and an
equal mixture over the three pause outputs. It verifies normalized component
weights and unit stream weights. This iid acoustic mixture is source-independent;
it is not a phonotactic phone-loop model, recognition probability or spelling proof.
Complete phones remain mandatory. Both observed endpoints must agree with TIFA
within 150 ms, duration must reach 80 ms, and neither endpoint may touch a cut edge.
The new checks require positive conditional acoustic contrast and start/end 90%
posterior widths no larger than 300 ms. The CTC lexical gate remains unchanged in
this first comparison. Accepted clocks would remain TIFA's actual observations.

| Background, same 390 PJS groups | Raw duration-model clocks correct | TIFA/physical boundary pairs | Pairs after acoustic and CTC checks | Correct retained TIFA clocks |
| ------------------------------- | --------------------------------: | ---------------------------: | ----------------------------------: | ---------------------------: |
| All distinct acoustic outputs   |                               296 |                          283 |                                 171 |                          171 |
| Pause outputs                   |                                68 |                           61 |                                  56 |                           56 |

Both models place all 390 groups. The all-output result has 199 pairs after acoustic
contrast/concentration and 171 after the separate CTC gate. Its five deterministic
recording-disjoint reporting folds retain 50, 16, 46, 31 and 28 correct groups, with
no fitting. This is already opened development data; unknown PJS overlap in the
checkpoint training still prevents an unseen-accuracy claim. The 62-recording run
takes **60.8 seconds**, with peak process RSS **354 MB**. Its closed-observation
SHA-256 is `84c1d256f4d6d578a9fa1f9c50678c7e579c1658846e43335fc16b4ab0b55fc8`.

The commercial comparison has 41 cues /296 original groups /122 gaps: the eighteen
native-source cues and 23 affected 嘘 cues. A fresh explicit-Japanese-phone TIFA
trial on 嘘 retains 135/146 candidates in 3.2 seconds after loading. That trial
exposes a real routing bug: ordinary text routing rejected macron-bearing words
before their explicit phones could be applied. The helper now validates those
phones first, retaining the exact original text and source span; a regression checks
both a valid long vowel and an unknown-phone rejection. Candidate TIFA paths are
not automatically accepted timings.

After both acoustic checks and the existing CTC lexical gate, the all-output model
has fifteen qualified missing candidates: two Just Awake, one Kyouran Hey Kids!!
and twelve 嘘. Adjacent support and immutable-interval checks leave **one 嘘 proposal**;
the pause ablation leaves zero. Neither loses or moves any old interval. Both admit
zero of the 143 mismatch-control groups, with the same unsupported-English limit.
This 63-input commercial/control run takes **70.3 seconds**, peak RSS **521 MB**;
observation SHA-256 is
`74cd7e2aab6e3bff121401eb7785b2b239726e099c6a3b315b74ac707bab6123`.
嘘/control recognition caches have frozen actual hashes but predate complete modern
recognition receipts. No app data, engine identity, bundle or shipped coverage changes.

A separate source/result audit confirms one conflicting Kyouran neighbor was created
by the earlier automatic engine, rather than supplied or hand edited. Its new physical
checks agree, but its CTC evidence and fresh outer anchors fail the region policy.
That provenance finding alone does not authorize moving it. It also explains why
simply allowing more candidates would not establish a safe regional repair.

The next closed pilot tests a different pronunciation-checking surface with those
same duration densities. `contrast_pronunciation` shares exact target prefixes and
suffixes when summing all complete one-phone replacements. Each sequence has its
own finite-window prior normalizer; the gate compares the target with an unweighted
sum of these conditional likelihoods. This deliberately strict sum grows with the
number of competitors, and is neither a calibrated Bayes factor nor the probability
of a disjoint union. Equal-density/unequal-duration and exhaustive-placement fixtures
check that the normalizers and reverse suffix pass behave correctly.

The inventory uses 41 canonical acoustic/duration paths, excluding explicit aliases
and deduplicating identical paths; pause and nonlexical paths remain disclosed
competitors. Windows over 320 frames (1.6 seconds) abstain without truncating source
phones or duration priors. Scoring occurs only after the unchanged physical boundary
checks pass. This first pilot freezes twelve eligible PJS groups by sorted identity,
then all eligible words in the same 41 commercial and 22 mismatch cases. It does not
open additional reference songs or change thresholds after inspecting their outcome.

It scores **12 PJS, 57 commercial and seven mismatch words** in **70.5 seconds**,
peak process RSS **229 MB**. None of the twelve PJS targets beats even its single
best phone replacement: the median best-alternative margin is −85.1 nats. Thus the
failure is not explained by summing many competitors. Their fixed wrong-phone
variants also have zero passes; two commercial words pass, both already timed.
The combined physical/pronunciation/overlay policy adds **zero** commercial words,
moves/loses zero old intervals and admits zero of the 143 mismatch groups. Most
control words abstain before this lexical stage; eight pass physical checks, seven
also fit its bounded window. The rest of the 390-word PJS comparison is not expanded
after this failed positive pilot. Observation SHA-256 is
`e45f84212f68e32027f2159ba3602a294258a0c2d7ae2682adeee75cd32f5967`.
This model remains a rejected pronunciation checker; good forced boundaries alone
do not make its densities a reliable word recognizer.

## English contrast and recognizer-contract checks (2026-10-15)

The CTC scorer now accepts an explicit token-expansion contract. HFA's 39 ARPAbet
labels are atomic phones: `aa` and `ng` must not pass through the Japanese mora
parser. A numerical regression checks exact target/competitor sums and requires a
complete explicit map. Its released CTC head is distinct from its dense alignment
head, but shares the encoder; those heads are not independent acoustic votes.
The Japanese default-path replay remains byte-identical to the earlier closed
390-group observations (SHA-256
`1c8458d666cb1ec34e2ad1869b0f95171c02de749f20478de8c7437b1ad025a1`).

On sixteen cached English clips /96 independently transcribed development words,
the original TIFA/HFA boundary pair retains 56. Correctly mapped local CTC contrast
retains only **one**, with one correct TIFA clock and zero of 96 fixed wrong-phone
variants passing. Ninety-five words beat the blank path, but only one beats the
one-phone substitution union; only five reach the 0.45 mean emission probability
rule. Median emission probability is 0.190. This **1.4-second cached trial is
rejected** before collecting further English inference. Its observation SHA-256 is
`67e8b1b402374119a21511878993266e5bd367cc74a4b4ef38ce1eac6eb3d2a0`.
English orthographic references, supplied-phone timing and phonetic likelihood
evidence remain separate; no spelling accuracy is inferred from conditional scores.

An additional [official RomajiASR inference-source audit](https://github.com/Xiantaidu/RomajiASR/blob/main/src/infer.py)
finds the existing mono /16 kHz /raw-float /one-unpadded-crop path already matches
the author's inference. The pinned group-normalized HuBERT archive has no processor
config; its 157 token-expansion entries all match the app's parser exactly. There
is no supported normalization or expansion fix to justify rerunning recognition.
The four unmapped vocabulary entries are structural specials, not sung phones.

## Changed vocal evidence and English clocks (2026-10-15)

A pinned BS-RoFormer ViperX checkpoint supplies a genuinely different vocal
estimate. Four preselected English-heavy source contexts are followed by the next
two contexts per song, ranked before inference by paired gaps without dual-view
recognition. All twelve use original stereo recordings, complete Rust context
bounds, strict model loading and position-preserving overlap-add. Qwen receives
only the resulting audio. Recognition matches the entire original source context
before assigning words to occurrences; the original TIFA/HFA clock is unchanged.

`evaluate-vocal-contexts.py` authenticates these closed runs and compares two versus
three fixed waveforms, requiring two qualifying witnesses for each word. It checks
original recording/source identities, separator completeness, derived sample count,
recognition receipts and reproduction of the original two-view result. Regression
fixtures cover changed occurrences/recordings, translated context bounds, forced or
weak confidence, invalid clocks and protected negative crop-relative intervals.
It also authenticates the exact original mix/vocal window bytes, rejects a third
waveform identical to either original, and checks mono/16 kHz separator metadata
before projecting it into the audio-only recognition manifest.
These are correlated waveform views, not independent recognizer votes.

| Frozen original comparison  | Timing proposals | Additional proposals | Old intervals lost/moved |
| --------------------------- | ---------------: | -------------------: | -----------------------: |
| Original mix + Kim          |               16 |                    — |                     0 /0 |
| Add ViperX, twelve contexts |               20 |                    4 |                     0 /0 |

The four extra proposals are one Wild Side word and three TEENAGE CITY RIOT words.
The expanded eight-context batch adds none beyond the first four-context pilot.
The replay retains the full **2,927-group** denominator; it checks 189 paired cues
containing 453 gaps, of which 41 cues receive the new selected-context waveform.
Other groups remain unchanged. These proposals are not independently labelled
commercial accuracy, are not cumulative with other alternative recipes, and do not
change the saved **2,210/2,927** app result. The exact new stage has not passed the
full mismatch-control/promotion gate.

Separation takes **237.8 seconds** across both serial batches, excluding 1.1 seconds
of model loading; peak MLX allocation is **3.10 GB**, maximum process RSS **1.54 GB**.
The two Qwen runs total **56.0 seconds** including loading, with about **4.62 GB**
driver allocation at closure; that last value is not a measured peak. The checkpoint
SHA-256 is `5b84f37e8d444c8cb30c79d77f613a41c05868ff9c9ac6c7049c00aefae115aa`.
It and the pinned MLX separator runtime remain private research inputs.

To replay already closed private batches without running models:

```sh
.venv-experimental/bin/python scripts/evaluate-vocal-contexts.py \
  --suite "$FROZEN_SUITE" --contexts "$CONTEXT_CACHE" \
  --baseline "$ORIGINAL_QWEN_REPLAY" --model-directory "$QWEN_ASSETS" \
  --separation "$CLOSED_SEPARATOR_BATCH" --recognition "$CLOSED_QWEN_BATCH" \
  --output "$FRESH_PRIVATE_REPLAY"
```

Repeat the paired `--separation`/`--recognition` arguments for disjoint context
batches; duplicate extra estimates for the same context are refused. The replay
record SHA-256 for the twelve-context comparison is recorded in its private identity.

A second, two-stage separation trial feeds the four original ViperX vocal contexts
through [Becruily's lead/backing-vocal model](https://huggingface.co/becruily/mel-band-roformer-karaoke/tree/0c149975cfaa261c7d87baf54330a9da85bcf888).
The pinned legacy training graph loads every learned tensor strictly. Its cached
44.1 kHz stereo intermediate is planar; reconstructing the earlier mono vocal
outputs from that intermediate is byte-identical before the new stage runs. Native
11-second chunks and eight-way overlap preserve the original context clock. The
extra stage takes **119.9 seconds** after loading, with **3.88 GB** peak MLX allocation
and **2.76 GB** process RSS; Qwen takes **20.6 seconds** including loading. Used as an
alternative third waveform, it produces the **same twenty proposals and same four
incremental groups** as the first ViperX pilot, with zero losses or moved intervals.
Lead-vocal isolation therefore adds no further gain in this comparison and is not
expanded unchanged.

The independently labelled English comparison still uses the same sixteen Jamendo
clips and 96 original groups. A new [MFA English GMM-HMM model](https://huggingface.co/MontrealCorpusTools/english_us_arpa/tree/ca321816421fef0dcb6666ae480a2abe922144fb)
uses 16 kHz MFCCs and a 10 ms frame step. Its CC BY 4.0 weights are distinct from
TIFA and HFA. The native arm64 runtime is MFA 3.4.3 /Kalpy 0.10.5 /Kaldi 5.5.1172
on Python 3.12. All sixteen source-only alignments close before reference scoring;
every output maps uniquely to its original word group.

| Fixed Qwen lexical check and TIFA/other-clock agreement | Admitted TIFA clocks | Human-correct clocks |
| ------------------------------------------------------- | -------------------: | -------------------: |
| Previous HFA                                            |                   52 |                   49 |
| Speaker-independent MFA                                 |                   45 |                   44 |
| MFA with per-speaker fMLLR                              |                   52 |                   50 |

The adapted run groups clips by the two actual singers, uses the model's default
feature adaptation and takes **25.0 seconds**. It introduces seven correct and one
incorrect admissions compared with the old set; it also withholds old candidates,
so this is a net gain of only one correct clock at unchanged coverage. Keeping the
TIFA interval outperforms replacing it with the MFA interval. Adaptation improves
standalone MFA clocks but does not establish the required new recipe. Peak RSS was
unavailable in this private runtime; no total-memory estimate is substituted.

Other changed verification pilots also remain unpromoted. A source-conditioned TIFA
phone-masking test accepts 16/96 targets and zero of 96 fixed phone faults, but only
14 accepted clocks meet the human endpoint tolerance. Masking the entire word accepts
six, all correct; that is too small to establish general accuracy. Same-family
mix/vocal TIFA agreement retains more correct pairs but also accepts 47/96 wrong-song
targets before lexical verification, demonstrating that stability alone is insufficient.
The new native-kana WavLM path adds zero groups on the eighteen Japanese-gap cues;
union with the previous verifier also adds zero. No reference reserve is opened.

An official eight-bit MOSS comparison uses the exact earlier 22.01-second audio and
prompt, with a fixed 128-token budget. Strict model loading takes 9.2 seconds; the
test is stopped at about five minutes without a completed first transcript. Load-time
MLX allocation is **10.23 GB**, but inference peak memory was not sampled. This is a
latency ceiling, not evidence of inaccurate recognition, an out-of-memory failure or
paging. No words or timings are inferred from that incomplete test.

## Kana minimal pairs instead of a second kanji dictionary

The next reading experiment supplies explicit kana alternatives to the already
pinned Whisper large-v3 model. Every hypothesis replaces exactly one original
Japanese group in an otherwise unchanged kana cue. Real audio, silence and a
different verse use identical decoder tokens. Full-vocabulary token likelihoods
retain exact UTF-8/BPE ownership; a token crossing the target boundary withholds
the comparison. This is conditioned evidence, not free transcription or a
calibrated probability that a reading is correct.

The three previously verified examples form an opened calibration set: departure!'s
地球 → ほし, and Tabi's 闇夜 → やみよ and 行こう → ゆこう. Fourteen candidate
readings include dictionary readings and fixed incorrect alternatives. All three
sung readings win both real-minus-silence and real-minus-other-verse comparisons.
The 42 observations take **24.5 seconds** after loading. Reusing identical encoder
features gives bit-identical scores in **7.9 seconds**, with **3.95 GB** peak MLX
allocation. These examples were already corrected; they add no new saved coverage.

An eighteen-cue trial covers **72 original kanji groups** and **427 hypotheses**,
including the current reading. The first run takes **126.4 seconds** after loading,
with **4.04 GB** peak MLX allocation and **1.49 GB** process RSS. Six cues initially
lack a distinct same-length wrong-verse control. A frozen supplement supplies 28
unique controls from other authenticated recordings, excluding the target word,
line and canonical kana. Only the missing **166** conditions are run, taking
**31.0 seconds**; the original real/silence observations remain unchanged.

Target-token scoring exposes a new failure: an alternative can absorb the next
word while receiving a high score for its own tokens. For example, a proposed
あまの for the original 天 is followed by a separately owned の. Whole-cue
scoring prefers あま in that case, although its margin remains too small. The new
`kana_reading_contrast.py` therefore requires the same winner for both the owned
word and the complete cue, against both audio controls. Its exploratory ln(10)
margin remains uncalibrated and produces nominations only.

| Complete 72-group replay outcome         | Groups |
| ---------------------------------------- | -----: |
| Current reading passes the contrast rule |     29 |
| Alternative nominated for further checks |      3 |
| Contrast too weak                        |     15 |
| Word/cue or audio-control winners differ |     14 |
| At least one competitor has unowned BPE  |      8 |
| No distinct alternative                  |      3 |

The three alternative nominations are not three verified fixes. A separate Qwen
conditional check does not strongly corroborate the first unknown reading; another
nomination may reflect a voiced/unvoiced consonant error. No edits or timings are
saved. Local acoustic masking and independent pronunciation checks remain necessary.

`evaluate-reading-contrasts.py` authenticates closed observation files, the original
Rust source/snapshot/crop and every competitor's unchanged surrounding text and
waveform. A supplement can add only an absent condition, using the same model and
source scorer. Per-word reports stay outside Git. The replay performs no inference
and never reads reference labels or writes app data:

```sh
.venv/bin/python scripts/evaluate-reading-contrasts.py \
  "$PRIVATE_READING_MANIFEST" "$CLOSED_READING_OBSERVATIONS" \
  --supplement-manifest "$PRIVATE_MISSING_CONTROL_MANIFEST" \
  --supplement-observations "$CLOSED_MISSING_CONTROLS" \
  --output "$FRESH_PRIVATE_READING_REPLAY"
```

Omit both supplement arguments for a fully controlled original run. The replay
reproduces all three calibration nominations and the 72-group table above.

## Further independent acoustic comparisons

A new English CTC family, [Parakeet CTC 1.1B](https://huggingface.co/mlx-community/parakeet-ctc-1.1b),
closes **214 source-blind views**: 172 context views and 42 negative-control views.
Its frame spikes locate lexical evidence only; they never supply a word's offset.
The fixed-context replay reproduces the earlier sixteen Qwen proposals before
adding two groups, both on Wild Side, with zero lost or moved intervals. Requiring
cross-family Qwen/CTC agreement adds zero. The negative replay admits zero of 143
targets, but 105 Japanese targets are structurally unsupported; the 38 English or
mixed targets must remain a separate denominator. This is not an app promotion.

An English MFA comparison closes 230 mix/vocal cue views across six songs in
**30.5 seconds**. Eleven missing exports are explicit abstentions. Joining fresh
TIFA and adapted MFA intervals yields fourteen physical pairs; lexical and original
interval checks leave three proposals, two already in the earlier sixteen. The
single additional source group does not establish the required multi-song gain.

The official [Japanese MFA model](https://huggingface.co/MontrealCorpusTools/japanese_mfa/tree/da71f868eaf4f4ebbf4b1941031df192d9e498de)
adds a different speech-trained duration family. On the opened PJS development
set, 238/390 reference groups have an exact supported phone mapping; 214 supply
valid intervals. Fresh TIFA/MFA agreement retains **148/390**, all 148 within the
human endpoint tolerances. This checks a limited supported subset; TIFA already
has 389/390 correct and is not improved. On 41 native-source and 嘘 cues, the model
adds no original gap under the existing checks.

That comparison also identifies six disagreements with saved automatic clocks.
An independent provenance audit finds no user edits or provider word timings in
those six records. A private solver tests replacement regions of at most four
groups, with fresh paired boundaries, exact source ownership, complete order and
unchanged supported outer anchors. Only one region passes; five remain withheld.
On the opened references it moves no correct PJS or Jamendo interval and adds no
error. The one unlabelled-song proposal is a possible timing repair, not measured
correctness or a completeness gain.

The approved English [SOFA combined checkpoint](https://huggingface.co/Silasimo/SOFA-combined/tree/4a86e84a2c0275a00c06152b9a6fa9bcf1ae52fc)
is a distinct mel/UNet singing model. Its complete state, 39-phone inventory,
44.1 kHz frontend and 128-sample output grid are verified. Unmasked phone/edge/CTC
outputs close before any supplied phone sequence or reference clocks are read.
Weights remain private; their CC BY-NC-SA terms are not a new app dependency.

| SOFA input; same 96 Jamendo reference words | Clocks within 150 ms onset /200 ms offset |
| ------------------------------------------- | ----------------------------------------: |
| Original short mixed clips                  |                                     41/96 |
| Mixed audio with real context               |                                     45/96 |
| Isolated vocals with the same context       |                                     44/96 |

The context runs preserve the exact focal frame phase and use at least six seconds
of real audio on each side. They take **7.3 seconds** and **3.9 seconds** respectively
after loading. Isolated vocals improve some boundary-error medians but fail to
improve the acceptance rule: the Qwen/TIFA/SOFA gate has 30 correct clocks among
39 admitted, versus the historical Qwen/TIFA/HFA 49/52. Neither longer context nor
vocal isolation makes this checkpoint suitable for integration.

A separate four-cue speech-projection pilot changes pitch without changing the
model. Rubber Band R3 preserves formants while lowering register by seven semitones.
Source-blind Japanese Whisper runs on the originals and transformed vocals. Across
three kana-only cues, pronunciation-normalized text edit distance changes from
73/94 to 74/94; the fourth mixed cue is empty in both conditions. A net extra short
word is offset by losses elsewhere, with no recovered multiword content block.
Cutlet-derived text phones are diagnostic references, not acoustic gold. All
transformed timestamps are unusable. A separate F0-contour compression preserves
median register and halves log-F0 variation. It increases short-word matches from
two to five, all particles, but worsens normalized edit distance from 73/94 to
93/94 and recovers no multiword content block. The four new Whisper runs take
**5.3 seconds**. Neither pitch transformation warrants expansion.

## Corrected English source ownership

An audit finds a private replay bug: matching ran only when an English source
window contained an unsupported word. Entirely supported English windows were
skipped. `ctc_lexical.py` now matches every window, retains unsupported words as
barriers and requires a unique complete multiword correspondence. Regression
tests cover wholly supported English, incomplete observed tokens and repeated
phrases. The corrected matcher reproduces all 214 cached views against the
unconditionally enabled earlier implementation.

A separate representation experiment stops encoding supplied Japanese/English
lyrics with the English recognizer's tokenizer. `ctc_source_words.py` uses the
original UTF-8 lyric spans and spelling to identify supported English words;
Japanese groups remain barriers in their original positions. Recognized audio
still requires complete observed-token ownership and the same confidence checks.
Unowned source letters, partial source words and repeated occurrences cannot be
silently removed or reassigned.

| Closed replay stage                                          | Corrected tokenizer-based source | Original-span source |
| ------------------------------------------------------------ | -------------------------------: | -------------------: |
| Confidence-qualified word/view matches                       |                              518 |                  578 |
| Matches localized inside a paired TIFA interval              |                              287 |                  304 |
| Primary-context CTC recipe eligible groups                   |                               62 |                   68 |
| Total proposed missing groups, including the earlier sixteen |                               18 |                   18 |

The six newly eligible source groups already have saved timings and dual-Qwen
support. Two unlocalized raw matches are correctly withheld when restored source
words expose a repeated phrase. No saved interval is lost or moved. The eighteen
proposals remain a projection, **not** an increase in app coverage. Source
representation fixes the research measurement but does not by itself fill a gap.

The corrected negative replay has four qualified word/view hits across two
literal common source groups. None has valid paired physical clocks: the actual
wrong-audio audit still admits **0/143**, with 105 structurally unsupported
Japanese targets and 38 English/mixed targets reported separately. A claim of
zero raw lexical matches would be wrong; zero final admissions is the measured
result. No new inference or recordings are needed for these replays.

## Contextual readings and independent checks

Localizing kana evidence does not yet validate new reading edits. Masking the
target and its surroundings independently reproduces the three known Whisper
reading preferences. An independent Qwen run reproduces only two complete known
pairs; the remaining example crosses a token boundary, and an unknown proposed
reading disagrees with Whisper. Scores normalized by token count can reverse a
preference, so the scoring scale is not changed after observing the result. No
reading or timing is saved from these comparisons.

Published furigana provides a different candidate source, not acoustic truth.
Across eighteen existing Japanese cues, **75 of 83** targets map exactly to the
published source, and Cutlet agrees literally on **71/75**. Four differences
include a personal-name interpretation, compound voicing and alternate kanji
readings. Swapping dictionaries is insufficient: Sudachi matches 70/75; OpenJTalk
maps 70 targets and matches 64 of those. Both miss the already verified special
sung-reading fixtures. Written-kana and phonetic differences remain separate.

The next frozen pilot asks a local text model for kana alternatives from the
original Japanese context and source-group IDs only. Current readings, published
annotations, artist metadata and acoustic transcripts are absent from the
prompts. Candidates must retain exact original word ownership and pass subsequent
audio checks; generating a plausible alternative is not a verified correction.
The pinned Qwen3-4B model and all lyric-bearing inputs and outputs remain private.

That pilot is now closed. A first response fails the strict schema. A second,
separately frozen prompt uses an unrelated example and retains every invalid
response as an abstention: **16/19** prompts and **66/84** target readings are
structurally valid. On the 57 valid published-furigana targets, primary readings
match literally on **44/57**, versus Cutlet's **54/57** on that same subset
(44/75 and 71/75 respectively when reporting the full proxy pool). The model
recovers 2/6 verified Tabi fixture readings and 1/3 separate known sung examples.
It takes **48.7 seconds** after a **1.1-second** load, with **3.04 GB** peak MLX
allocation and **1.81 GB** process RSS. Its two novel untimed-word proposals fail
the subsequent acoustic competition. Generic text generation is rejected as a
replacement for the current readings.

A broader strict comparison retains all **404 low-set cues /2,183 groups /714
gaps**. Six cached published pages match 250 complete cues and provide 573 readable
groups, including 89 untimed groups. Eight untimed groups have different supported
phone paths; sixty agree and 21 have unsupported paths. This is a detected
opportunity under exact matching, not a ceiling on errors in unmatched lyrics.
Two published alternatives are absent from the bundled candidate lists. Adding
them to every existing competitor still yields weak acoustic contrasts. Five
other source owners already have the alternatives available; testing their 36
competitors takes **16.9 seconds** for 108 Whisper conditions.

Three of those five alternatives agree across independent Whisper and Qwen
**whole-cue** contrasts. Qwen BPE tokens cross source-word boundaries for two
of them, so the original word-and-cue rule correctly withholds its word statistic.
A separate sequence experiment compares complete unchanged-neighbor cues against
both controls, without allocating a shared token's probability to a word.
`cue_reading_contrast.py` reproduces the private five-competition decisions and
exact margins. The replay exposes this explicit research unit:

```sh
.venv/bin/python scripts/evaluate-reading-contrasts.py \
  "$PRIVATE_READING_MANIFEST" "$CLOSED_READING_OBSERVATIONS" \
  --unit cue --output "$FRESH_PRIVATE_CUE_REPLAY"
```

The default remains `--unit word-and-cue`; source, crop, neighbor, control and model
authentication are identical. A sequence nomination is not word confidence or a
saved correction. One other Qwen winner differs by a voiced consonant from the
published reading and the other model's preference. Without a listening label,
that is a disagreement, not a measured false prediction. Localized evidence and
fresh physical word clocks remain necessary.

Current-reading winners matter too: of 29 current winners in the original 72-group
trial, seven are original timing gaps. A fully extended competitor set withholds
one. Twelve of all 29 have fresh TIFA/native-Qwen forced-clock agreement, but ten already have
saved timings. The two remaining groups are isolated under the earlier overlay's
adjacency rule and add zero through that unchanged rule. These are opportunities
for testing a different contextual verifier, not impossible words or counted gains.
The legacy private join calls the second observer `fresh_hfa`; its authenticated
runner is the native Qwen forced aligner, not the English HubertFA model.

Two further acoustic alternatives fail their small pilots. Granite Speech CTC
makes 45 reference-word edit errors across the same 96 English development words,
versus Qwen's twelve, and supplies no dual-view witness for the selected hard
gaps. Japanese MFA with explicit kana alternatives selects **0/3** known sung
readings correctly. Neither is expanded unchanged. Only nine of 717 gap groups
have otherwise valid TIFA intervals below 80 ms, and none has corroborating
independent clocks; reducing the duration floor is not a supported solution.

## Direct audio-to-kana and acoustic repeats

The pinned third-party [Kotoba v2.0 MLX conversion](https://huggingface.co/kaiinui/kotoba-whisper-v2.0-mlx/tree/b2c725b0a8d131447cdb0bc41762df970b0a2482)
has a 32-layer encoder and two-layer decoder. Complete key/shape loading verifies
its 1.51 GB checkpoint; conversion is not bitwise audited against the official
source. Ordinary source-blind Japanese transcription on eighteen existing vocal
crops and three known examples takes **11.2 seconds**, with **2.38 GB** peak MLX
allocation and **1.10 GB** process RSS. Most output uses kanji, so converting it
back through Cutlet does not independently establish the sung reading.

A new UTF-8 state constraint emits kana without supplying target lyrics. It retains
valid partial-byte BPE tokens, rejects kanji/Latin text, allows the long-vowel mark
and permits end-of-text only after complete UTF-8. Chosen-token scores are captured
from the original full vocabulary before masking, separately from the constrained
distribution. No masked score becomes a word-confidence statistic.

On the same eighteen cues, the constrained model has **12/98** exact unique
three-word contexts, versus **1/98** for ordinary output's dictionary proxy.
However, overall normalized text error worsens and zero of eighteen full cues is
exact. Twelve centers represent twenty complete source owners; seventeen already
have baseline timings. Only one untimed owner is incremental over the ordinary
proxy, and it is a neighboring particle rather than a recovered target reading.
The known-reading comparison has **2/3** exact target-centered contexts and zero
of six matched wrong-verse/silence controls; these are tiny development counts.
Full Whisper large-v3 does not solve the constraint: one known cue is unrelated
and another adds a vowel, so its unchanged recipe is not expanded.

A separate repeat experiment starts from **44** source-compatible untimed groups.
Nine source-blind clips cover three target/source/control sets and seven gaps.
Two independently trained acoustic surfaces, HuBERT latents and singing CTC,
provide complete observed-frame paths before source clocks are opened. The frozen
two-family DTW rule leaves **one of seven** proposals; six fail control, crop-edge
or protected-neighbor checks. Its proposed endpoints are actual target frame-cell
edges, with the second family as verifier. An earlier averaged endpoint is retired;
no averaged or copied timestamp reaches an app result. Without a target reference,
this remains an unverified proposal and adds no saved coverage.

One reference-opportunity audit reads the two complete Jamendo annotation files
(795 rows) beyond the intended 96-row development pool. The exposure is recorded
privately and the broad audit excluded; those additional rows cannot be called an
unopened reserve. Subsequent diagnostics use only the original 96 selected rows.
An onset-only diagnostic admits 73 using lexical evidence and model agreement
before reference scoring; 67/73 TIFA onsets are within 150 ms, below the earlier
49/52 full-check accuracy. It supplies no support for changing the product gate or
claiming unknown word endings as timed words.

## Conditional English evidence and automatic-neighbor repair

A source-conditioned English pilot compares each word with four fixed CMU
one-phone competitors, retaining complete-cue and owned-word decisions separately.
All twelve words come from two already opened cues by one singer; this is a small
development test. Whisper nominates the source for seven words under both units,
Qwen for ten, and both families for six. Neither selects a competing spelling.
Changing which candidate is marked current leaves the acoustic decisions unchanged.

The endpoint join is performed after both observation sets close. Four words have
cross-family lexical support and paired physical clocks; all four TIFA envelopes
meet the opened reference's 150 ms endpoint tolerance. Qwen alone admits one
incorrect envelope that the Whisper cue check rejects. These counts are too small
to establish accuracy, and the exact incremental overlap with the earlier benchmark
is unresolved. They justify a separate twelve-gap test across three difficult songs
and independent wrong-audio controls, rather than a new app policy.

That follow-up is closed: the twelve paired gaps all fail the old four-way
free-transcription witnesses. Whisper nominates one source word under word-and-cue,
Qwen three, and their intersection is empty. No full-policy proposal survives the
unchanged timing overlay. On twelve independent wrong-audio queries, both full
word-and-cue rules and their intersection nominate zero. Qwen's isolated word
unit makes two false source nominations and its isolated cue unit one false rival
nomination; all count as errors rather than being hidden by the current-candidate
flag. The full policy adds zero words and is not promoted from this small pilot.

Fresh Japanese clock probes compare current and nominated readings on three cues.
Changing one reading increases TIFA retention from seven to nine of nine groups,
but its target endpoints disagree with Whisper. Another changes eight to nine of
ten and has target agreement within 90 ms at the start and 80 ms at the end.
The strict overlay still adds zero because saved automatic neighbors overlap it.

A separate frozen endpoint-selection recipe tests that overlap explicitly. It
uses only same-word, same-role timestamps actually observed on the same waveform.
Existing automatic endpoints may survive if both fresh models endorse them within
150 ms. User, provider and unknown-origin clocks remain protected. An interval
assembled from different observations retains endpoint-level composite provenance;
it is never described as one model's whole interval.

The primary profile keeps the recovered target's complete TIFA interval. On the
ten-word cue it moves four endpoints across three automatic neighbors and retains
all ten original groups, versus nine before repair. No endpoint is averaged,
trimmed or copied from another word. The other five current/candidate probes lack
paired targets and remain infeasible. Twenty-five private regressions include
structured boundary negatives and ownership/protection checks. This establishes
feasibility, not acoustic accuracy or an increase in saved app coverage. Reference
validation and localized reading evidence remain prerequisites for integration.

A subsequent cached calibration freezes proposals for all 96 opened reference
words before scoring them. HFA supplies a measured baseline proxy, with TIFA and
Whisper as the fresh pair; this is not the app's actual saved baseline. The primary
profile is feasible for three targets, fixes zero wrong preexisting word intervals
and makes one previously correct interval wrong. That case includes a fresh
Whisper onset at the crop edge. The solver's permissive zero-bound rule therefore
also violates the plan's existing cut-edge restriction. The unchanged conditional
Whisper check retains only one safe, already-correct target. A separate dropped-word
diagnostic recovers three gaps with two correct intervals and one incorrect.
Neither model agreement nor endpoint feasibility is sufficient for promotion.

A separate second version restores strict crop-interior observations, an existing
plan requirement, without changing thresholds or hiding the first version. Both
proposals and comparisons remain recorded as development data. The primary profile
then has two feasible replacements, both correct, with no old errors fixed and no
regressions across three changed preexisting word observations. Its dropped-word
diagnostic proposes two correct intervals and one safe collateral neighbor move.
The corrected-reading ten-word cue keeps exactly the same successful repair. This
removes the observed edge bug but still does not establish broad accuracy gains.

An independent SOFA Japanese duration probe uses three audio posteriors to decode
the six unchanged/current-versus-candidate sequences. It does not corroborate the
two difficult corrected-reading targets: one collapses below the duration floor,
and the other disagrees with the TIFA/Whisper envelope. These conditional forced
paths supply no new lexical evidence or saved words.

## Testing context, pronunciation and interval selection

The English follow-up keeps all twelve reference targets, twelve hard gaps and
twelve independent negatives. A three-source-group text window over the old full
audio loses reference recall. Matching that text with measured local audio improves
lexical nominations, but the primary cross-family rule still supplies no additional
correct reference timing or hard-set overlay insertion. It also makes one false
lexical nomination on the independent negatives; paired clocks withhold it. Two
negative targets lack complete neighboring observations and remain explicit
structural abstentions in the twelve-target denominator.

Fresh local alignment retains all 92 source-group observations from 34 eligible
windows, including rejected paths. It provides 26 valid pairs. On the twelve
reference targets, paired clocks alone worsen from seven correct of eight to six
of eight. The hard-set physical comparison changes vocal-isolated audio to the
original mixture as well as context, so it does not isolate a crop effect. Keep
that result and test the old waveform role separately before drawing that conclusion.

A pronunciation pilot tests ten gaps across four songs with complete captured
canonical English paths and documented Japanese-English substitutions. Twenty
candidate paths are measured by each aligner; the canonical paths reproduce the
cached observations exactly. Six alternatives improve the changed phone's HFA
conditional score, but zero recover a paired target. Neighbor pairs gain one and
lose four. Improved path scores alone cannot authorize a pronunciation or timing.

A separate cached 96-word audit asks whether correct clocks exist outside the
original AND gate. With source-blind Qwen qualification, the original 52 pairs have
49 correct intervals under the historical onset-150/end-200 ms metric, or 46 under
strict 150/150 ms. The frozen observed-whole-interval consensus selects 69, with
63 and 58 correct respectively. It gains correct words but also introduces errors
and overlapping intervals, so it is withheld. The oracle finds a correct existing
clock for 78 qualified words under the strict metric; that is an upper bound using
labels, not an admission rule. Future selection work must improve correctness and
source-order geometry together.

Original Japanese script is also kept separate from phonetic alignment input.
Replacing only the candidate span with kana while leaving every neighbor byte in
its original script preserves nine complete competitions and 54 candidates. One
competition is already text-identical and reuses its closed observations. This
changes some scores but does not solve reading selection: a voiced-consonant
variant conflicting with the published reading remains a joint winner. Two raw
Japanese Whisper boundary probes also fail to corroborate the missing targets.
Neither a new representation nor recognizer agreement is sufficient evidence on
its own; the next comparison keeps the candidate text fixed and changes the audio
view to check separation artifacts.

Holding that candidate text fixed across the mixture and isolated vocals leaves
two joint reading nominations. Fresh native forced-alignment clocks corroborate
one target, but disagree with its following neighbor; they supply no complete
region repair. A separate comparison restoring the English local windows' old
waveform role recovers more paired neighbors than the confounded mixture trial,
but still adds zero primary-policy hard targets. These remain separate factors.

Published Japanese loanword readings also underperform the canonical English
paths: target retention falls from 15 to 10 of 21 gaps. A separately frozen small
vowel hypothesis raises that to 11, with no verified additions. Scoring alternate
dictionary paths changes six choices but leaves canonical retention at 15/21.
Published pronunciation and a higher conditional score cannot replace acoustic
verification.

The same audit exposes a concrete frontend bug: the existing vowel fallback
handles `あぁ` but misses mora endings such as `さぁ` and `ねぇ`. The corrected
fallback preserves valid digraphs, script, original words and UTF-8 ownership.
Twenty new regressions cover those rules. Four fresh calls retain both previously
unsupported targets; one agrees with native clocks within 150 ms at both ends,
and the other's ending disagrees by 590 ms. The four-call test takes 3.0 seconds
including loading, with 0.74 GB peak process RSS. This fixes Experimental's
phonetic-input fallback and versions its engine identity; it does not establish
two independently verified additions or change the original TIFA action.

An exact replay of the existing Experimental repair policy admits neither
target. Fresh MMS observations fail probability, endpoint and line-context
requirements. The kana change therefore fixes unsupported model input but adds
zero saved timings under the current policy. Native forced-clock agreement is
not substituted for that policy. The two source-free MMS calls take 2.6 seconds
including loading; process RSS peaks at 0.51 GB, with a 2.24 GB after-crop MPS
driver sample rather than a measured allocation peak.

## An authentic Japanese alternative for 嘘

An authenticated [Japanese source with furigana](https://utaten.com/lyric/jb10904545/)
provides an alternative to the frozen romanized source. Complete artist and song
credits are checked against the released recording. The saved PCM's 205.973-second
duration matches its LRCLIB source; the catalog's Seconds column measures processing
time, not track length. Original HTML bytes, annotations and correspondence live
outside Git.

Exact complete-cue phone correspondence identifies fifteen unique source spans.
The candidate replaces those fifteen cues, preserves the other twelve acoustic
cues verbatim and retains all 32 original source occurrences and line timestamps.
Repeated or unmatched passages stay unchanged. No word clock is transferred.
Rust import, snapshot validation, published-reading overrides and all five display
representations pass offline checks. The alternative remains a separate private
version, with the original still active.

| Same full-song waveform and fresh model runs | Original romaji | Composite Japanese candidate |
| -------------------------------------------- | --------------: | ---------------------------: |
| Source groups                                |             167 |                          168 |
| TIFA retained                                |              99 |                          128 |
| Retained with strict interior /80 ms bounds  |              87 |                          111 |
| Retained and native-clock paired ≤150 ms     |              24 |                           23 |

The unchanged twelve cues give exactly identical observations in both model
families. The replaced cohort accounts for the retention increase: 55/88 becomes
84/89. Its second-clock pairs fall from 11 to 10, so the result does not establish
improved timing accuracy. The earlier saved Experimental result of 116/167 uses
another recipe and remains a separate baseline. Fifty-four TIFA calls take 7.9
seconds with 0.94 GB peak RSS; 54 native forced-aligner calls take 7.9 seconds.
Twenty-two private source/import/join regressions pass. Neither the alternative
source feature nor a new accuracy recipe is integrated from this trial alone.

## Separate pronunciation evidence from physical word duration

The next comparison keeps the existing CTC pronunciation test unchanged: positive
complete-sequence margins against the one-phone substitution union and blank,
with at least 0.45 mean probability on actual emission frames. It replaces the
CTC-spike duration comparison with two physical observations: TIFA and the native
Qwen source-word aligner. Both must satisfy the fixed duration/interior rules and
agree within 150 ms at each endpoint. Accepted timestamps remain TIFA's actual
interval; no spike is extended and no endpoint is averaged.

The native run retains every original conditioning group across 62 PJS recordings
and 22 existing mismatch cues. One nine-group mismatch cue is unsupported because
its original word contains whitespace; all nine stay in the control denominator.
Two derived PCM buffers preserve each original clip byte-for-byte, and the helper
aligns their exact slices independently. There is no cross-recording clock
transfer. The 83 eligible native cues take 30.5 seconds. Additional context scores
use cached posteriors, with no new recognition or recordings.

Proposals close before joining the same 390 already opened PJS reference words.
The lexical scores and thresholds are unchanged; only the physical observer is
different. Correct counts below satisfy both strict 150/150 ms and the historical
150/200 ms reference tolerances, except the explicitly marked old comparator.

| Opened PJS development rule                      | Qualified /390 | Correct intervals |
| ------------------------------------------------ | -------------: | ----------------: |
| Old lexical + CTC-spike physical gate            |             79 |    78, historical |
| TIFA/native physical pair without lexical filter |            303 |               303 |
| Unchanged lexical filter + TIFA/native pair      |            257 |               257 |
| Also require coherent full source context        |            208 |               208 |
| Also pass the existing ordered drop-one overlay  |            170 |               170 |

The 257-word rule shares 64 old admissions, adds 193 correct previously withheld
words and withholds fifteen old admissions: fourteen correct and the old error.
It does not extend the original 79-word set monotonically. Recording-disjoint
descriptive folds qualify 46, 66, 28, 75 and 42 words, all correct; no fold is used
to fit thresholds. These are development results with unknown native-model
training overlap, rather than fresh holdout or app coverage.
The [reference labels](https://github.com/UtaUtaUtau/pjs-manual-labels) are human
relabels/corrections. The [PJS recordings](https://arxiv.org/html/2006.02959) use
one male singer following guide melodies on phoneme-balanced sentences in a
controlled room. That narrow setting does not establish transfer to natural pop.

The word-level gate still accepts one wrong-verse control of 143: a common
phonetic word has coincident physical clocks. Its cue has only one of six
qualified groups, so the separately frozen context requirement (at least two and
at least half of all original groups) rejects it. Context and ordered overlay
therefore admit zero of 143 controls; the primary false positive remains recorded.
All 390 fixed one-phone wrong readings remain rejected. The 32 English phone
abstentions and nine native-unsupported groups are structural exclusions, not
successful English verification. Song trials must retain the context requirement.

`source_physical_policy.py` exports the exact model-free research decision and
immutable overlay. Fifteen regressions cover source identity, sustained vowels,
finite statistics, both physical endpoints, crop edges, original denominators,
context and protected clocks. Its decisions reproduce all 390 reference words,
143 negatives and full source contexts. It does not change the app pipeline.

A source-selected trial then tests 48 original gaps across all seven difficult
songs, including current readings rather than only proposed dictionary changes.
All 255 original groups in their forty cues remain represented. Twenty-seven
targets have eligible TIFA windows, thirteen pass the unchanged lexical check,
five have TIFA/native physical pairs and four satisfy both. One passes full
context, and zero survive the existing ordered overlay. The surviving target
also overlaps an old automatic neighbor by 30 ms; no unsupported neighbor move
is made to hide that conflict. The reference improvement therefore supplies no
additional song timings in this closed trial.

## Character timestamp slots

The separate character-slot comparison preserves all original words and exact
waveforms. It aligns auxiliary CJK characters or Latin runs, then reconstructs
an original word only when its pieces tile the source span exactly and have
complete, bounded, monotone observations. Its first observed start and last
observed end belong to that same word. No missing point is interpolated. The
official Python Japanese path uses Nagisa morphemes; this is an experimental
granularity factor, not a claim to reproduce the training frontend.

The 123 requests take 36.7 seconds. On the same 390 opened PJS references,
character slots reduce physical pairs from 303 to 289, lexical-and-physical
qualifications from 257 to 254, context qualifications from 208 to 163, and
ordered drop-one insertions from 170 to 138. Every admitted TIFA interval is
correct under both reference tolerances. The earlier single word-level
wrong-verse admission is withheld, leaving zero of 143; both versions already
withheld all controls after context. Requiring strictly positive duration for
every internal slot reduces qualifications further. Zero-duration points and
nonmonotone paths are retained in the private diagnostics.

On the 48 missing song words, both character profiles reproduce the earlier
five physical pairs, four joint qualifications, one context qualification and
zero insertions. Some already-timed neighbors change qualification, but no
missing target improves. This factor is not adopted.

## A different free-transcription architecture

[Fun-ASR-Nano](https://huggingface.co/FunAudioLLM/Fun-ASR-Nano-2512) lists Japanese
support and music-background lyric recognition. The published lyric result is
not a Japanese-specific accuracy guarantee. The local pilot uses the official
native checkpoint at `d93b302ee7fd505e1b3576120fc142fc6f7820e1`, strict loading,
CPU float32, greedy decoding and at most 256 new tokens. Its 1.66 GB weights and
matching Torch/Torchaudio research environment remain outside the app and Git.
No lyric prompt, keywords or source-conditioned transcription are supplied.

Eight saved windows are identical to the earlier Qwen2-Audio pilot: six
isolated-vocal Japanese-song cues and two already opened English reference
clips. Complete matching source words must belong to a unique exact phonetic
block containing at least two adjacent original words. Unsupported owners stay
in the denominator. These are source-candidate witnesses, not Japanese accuracy
labels or timing admissions.

| Same six song cues                                         | Contextual owners /51 | Missing-word witnesses /26 |
| ---------------------------------------------------------- | --------------------: | -------------------------: |
| Qwen2-Audio, earlier generic instruction                   |                     6 |                          1 |
| Fun-ASR, fixed Japanese language                           |                    10 |                          3 |
| Fun-ASR, automatic language                                |                     8 |                          2 |
| Fun-ASR, automatic language with upstream amplitude factor |                     8 |                          2 |

All outputs finish with EOS. The three Fun-ASR runs take approximately 14–17
seconds after loading and peak at approximately 3.9–4.0 GB process RSS. They
share two missing-word witnesses; the fixed-language condition supplies one
more. Exact-wave earlier free Qwen3 results exist for only three of the six
Japanese clips and already attest one of those words. The other comparisons
remain missing, so the two gains against Qwen2 are not established gains against
the complete existing ensemble.

The two English clips contain only eight human-reference words. Fun-ASR makes
one insertion, Qwen2 makes seven errors, and existing same-wave free Qwen3 makes
none. This tiny comparison does not establish a better general recognizer.

The upstream-amplitude factor reproduces the original Kaldi/LFR calculation in
a feature-only check. Much of its uniform log-power shift cancels in the first
encoder LayerNorm; quiet clipped bins still differ. Seven of eight transcripts
are identical to the automatic-language baseline and the contextual witness
sets are unchanged. This does not establish that the native frontend is broken.
The factors remain separate and no per-clip best result is selected.

The three opened reading examples supply a separate bounded check on both the
mixture and isolated vocals. Ordinary Japanese transcription nominates the
verified departure! reading `hoshi` on the isolated vocals only, withholds both
Tabi alternatives, and nominates no wrong fixed candidate. Raw kanji output
does not establish its pronunciation. A generic hiragana-only prompt fails to
remove kanji from all six real clips and loses the sole correct nomination.
The added five-second zero-audio control emits `/sil`, a marker-like string;
the frozen alphanumeric-hallucination diagnostic flags it, without treating it
as a fluent invented lyric. Neither condition supplies timestamps or app edits.

A source-only English follow-up selects 48 original gaps in 35 cues across six
low-set songs, with eight targets per song and at most two per cue. All 192
original context groups remain. The 70 mixture/vocal requests take 118.5 seconds
after loading with 4.09 GB peak process RSS. Two reach the token limit and
abstain. Complete unique context matches with whole-BPE ownership and actual
free-decoder probability qualify ten missing owners on each view and eight in
both; the twelve-owner union remains diagnostic. There are no new human labels
or false-positive estimates in this real-song cohort.

The physical follow-up obtains all missing observations for those 35 cues.
On isolated vocals, 28 selected gaps have retained interior TIFA intervals,
38 have valid native intervals and fourteen have paired clocks. Requiring
independent lexical matches on both audio views and coherent original context
leaves one ordered-overlay hypothesis. Its whole observed TIFA interval is
800–1,210 ms and native is 800–1,200 ms relative to its crop; no existing clock
moves. The original-mixture TIFA paths are rejected by the unchanged filters.
This is one research hypothesis, with no new reference label or Fun-ASR mismatch
calibration, and is not an app admission.

A separate generic kana-only logits constraint bypasses kanji-to-dictionary
reinterpretation without supplying source lyrics. Its reversible byte-token
filter preserves partial UTF-8 and permits EOS only after a complete character;
raw full-vocabulary scores stay separate from the constrained distribution.
On the same three known readings in both audio views, it nominates `hoshi` and
`yukou` correctly on both views, withholds `yamiyo`, and nominates no wrong fixed
candidate: four of six role-specific nominations versus one with ordinary
transcription. The isolated-vocal `yamiyo` transcript lacks enough of its source
context for the frozen 65% envelope rule. The zero-audio control emits a short
Japanese word, so unrestricted automatic repair is not established.

The bounded expansion preserves the eighteen earlier Japanese cues, all 150
original owners and both audio views. Thirty-six requests take 91.1 seconds
after 3.4 seconds loading with 4.20 GB peak RSS. Two hit the token cap and
abstain. The mixture yields no changed-reading nominations; isolated vocals
yield two, one already timed and one missing. The same-wave constrained Kotoba
baseline already nominates the former; the latter is new. Both agree with a
provider annotation, which is candidate agreement rather than a correctness
label. Neither replicates on the mixture. No reading or timing is saved.

## Complete physical census of the frozen gaps

The earlier cache audit had both physical families for only 131 of the 714
low-set gaps. Completing the census preserves 299 gap-containing Rust cues and
all 1,700 original context groups. It reuses exact closed observations, adds
275 TIFA cue calls and 280 native calls including the English follow-up, and
retains every unsupported or rejected owner. The 714 low-set gaps use their
authenticated Kim stems. The three high-set gaps lack authenticated stems in
this cache and remain a separate original-mixture stratum; none pairs.

| Mutually exclusive restriction, low-set gaps | Original gaps /714 |
| -------------------------------------------- | -----------------: |
| No retained, strictly interior TIFA interval |                416 |
| TIFA valid, native interval invalid          |                 70 |
| Both valid, endpoints disagree beyond 150 ms |                135 |
| Both physical clocks qualify                 |                 93 |

Even granting perfect lexical evidence, the unchanged research context gate
leaves 33 targets and its strict immutable ordered overlay leaves ten, including
one unresolved romanized-source owner. At most nine have usable ownership under
that recipe. This is a ceiling for that fixed research rule, not an impossibility
result for the app: existing storage can preserve overlapping observations, and
a separately validated automatic-region repair could choose different clocks.

English spelling accounts for 490 low-set gaps. Ordinary TIFA retains 238,
including 22 at a crop edge; of the 252 internal rejections, 233 are token
agreement, fourteen incomplete paths, three duration and two similarity.
Among 130 Japanese-source gaps, 47 of 59 internal rejections are token agreement.
The statistic is a mean conditional input-token probability, not literal token
equality. This identifies a research restriction; existing Experimental already
has a separately verified recovery stage with a 0.90 threshold. Removing the
ordinary action's 0.99 filter alone is not a new validated recovery policy.

The missing English observations take 6.5 seconds for 67 TIFA calls and 5.7
seconds for 67 native calls. The remaining census takes 14.7 seconds for 208
TIFA calls and 17.8 seconds for 213 native calls. TIFA peak process RSS is
1.04 and 1.11 GB respectively. No new separation, recording or ASR is performed
for this physical census, and no source or saved result changes.

## Contraction spelling reaches the pronunciation dictionary

The audit finds a real source-to-model defect: the punctuation filter strips
internal English apostrophes. Eight CMU-supported missing words then reach
different dictionary paths: four `Don't`, three `I'm` and one `what's`. Forty-three
context owners are affected. Two additional nonstandard contractions lack a
supported source dictionary entry and remain diagnostic. There are no curly
apostrophe or hyphen input occurrences in this cohort; those hypothetical
normalization defects do not explain its gaps.

The fix preserves internal ASCII apostrophes between English letters in the
acoustic spelling and updates Rust's matching validation rule. Nine Python
regressions and cross-language target/validation checks retain original source
spans, displayed text and all five modes. The converter signature changes with
the transformation; no saved clocks are rewritten.

Forty-two exact affected cues compare old and corrected acoustic inputs with
unchanged first-pronunciation selection. Source-owned native observations are
identical and reused. The fresh TIFA run takes 6.0 seconds with 0.86 GB peak RSS.
It changes 25 context intervals, seventeen on neighbors whose spelling did not
change, but the eight supported gaps retain one physical pair before and after.
Both ordered overlays add zero. The bug fix corrects dictionary input without
establishing a timing-coverage improvement, and none of the provisional clocks
are saved into the app.

## Complete paths and alternative physical observers

A separate recipe replaces the ordinary TIFA token-confidence filter with
independent lexical qualification while retaining complete observed paths,
finite positive similarity, strict crop interior, at least 80 ms duration and
150 ms agreement at both native endpoints. Fresh diagnostics for the same 62
PJS recordings reproduce all 949 earlier retained intervals exactly. The
390-word development comparison still qualifies the same 303 physical pairs
and 257 CTC-qualified pairs: it supplies no newly rescued low-agreement target
whose accuracy can be measured there. Wrong-verse physical pairs rise from six
to seven of 143, with zero after full context.

On the 96 opened English words, raw-complete physical pairs add three correct
observations to the 49 retained pairs. Two additions also satisfy source-blind
Qwen and both CTC-view word matches. Five existing strict timing errors remain;
the new complete set is not universally accurate. In the frozen song census,
raw-complete physical pairs rise from 93 to 133 and generous context-qualified
targets from 33 to 59. Strict ordered geometry leaves eighteen hypothetical
targets before lexical evidence and unresolved-source exclusions. Dual-view
Fun-ASR evidence in the English48 cohort still yields only the same earlier
hypothesis. These are research-policy comparisons, not increased app coverage.

A further cached comparison replaces the primary clock itself. Source-blind
Qwen matches and native endpoint agreement check whole MFA-SI observations;
the same full-source context gate applies. Proposals close before reusing the
same 96 development labels. A first context implementation is preserved as an
invalid comparator; the corrected rule counts all original groups, including
the target and unsupported owners.

| Primary whole interval + native corroboration | Qualified /96 | Strict correct | Historical correct |
| --------------------------------------------- | ------------: | -------------: | -----------------: |
| MFA, speaker adaptation disabled              |            33 |             31 |                 31 |
| MFA, separate speaker-adapted arm             |            43 |             38 |                 40 |
| HFA control                                   |            31 |             26 |                 27 |

No priority or timestamp winner is chosen from these labels. The MFA-SI arm
also has a 29-word adjacent-candidate subset with 28 correct intervals; that
subset is not a full protected-baseline overlay. These error rates do not
justify integration.

An onset-only diagnostic keeps the same structural and lexical checks but
corroborates starts alone. It accepts 46 starts, 43 within 150 ms of the human
onset; the two-endpoint comparator has 32 correct starts of 33. An advancing
marker simulation on 32 consecutive qualified edges matches the source word
for 85.6% of the measured 11.2 seconds, shows the wrong word for 9.4% and is
unmarked for 5.0%. This selected development subset is not full-song coverage.
No new word ends, saved events or app behavior are introduced.

## Runtime Whisper head selection

The [stable-ts implementation](https://github.com/jianfch/stable-ts/blob/e312072cc024ae9fceb25b057d7d18524873a02b/stable_whisper/timing.py)
selects attention heads per token from the audio-conditioned forced transcript,
then repeats selection around its first DTW path. It reads no reference clocks.
This trial fixes six heads and two passes before inference. The old MLX path
normalizes full queries before trimming and floors the frame crop; stable-ts
normalizes trimmed queries and rounds it. A fixed-head stable-ts control keeps
those changes separate from dynamic head selection.

One forward per each of the same sixteen English cues preserves all 640 raw
attention heads. Proposals and exact source ownership close before joining the
same 96 opened references. All 96 old word clocks reproduce exactly; the CPU
replay and exact MLX control have identical frame jumps on every cue.

| Complete original words /96          | Strict 150/150 ms correct | Historical 150/200 ms correct |
| ------------------------------------ | ------------------------: | ----------------------------: |
| Original MLX fixed ten heads         |                        14 |                            17 |
| Stable fixed ten heads               |                        15 |                            18 |
| Stable dynamic six heads, two passes |                        20 |                            23 |

Dynamic selection gains seven correct words and loses one versus the old rule.
It still produces 76 incorrect strict intervals. Restricting to the 88 words
matched by the fixed source-blind Qwen gate leaves only 17 strict correct clocks.
One correct clock is new relative to the union of earlier clock families, but
identifying it uses reference labels; it is not a selectable admission rule.
This result does not justify expanding or integrating the method.

The capture takes 17.0 seconds after loading, plus 2.4 seconds loading. Peak
process RSS is 1.65 GB and MLX reports 4.58 GB peak allocation; these are distinct
measures of shared unified memory, not additive memory totals. No timing shift,
duration clamp, silence suppression or reference-informed head search is applied.

## Music-trained lyric transcription

The initial [Music Flamingo model](https://research.nvidia.com/labs/adlr/MF/)
offers a different training domain from speech recognition. This bounded trial
uses the third-party Q4_K_M text model and matching F16 audio projector from
[`mradermacher/music-flamingo-hf-GGUF`](https://huggingface.co/mradermacher/music-flamingo-hf-GGUF/tree/39c453b1d6714c4de87293050661e97a6011af84),
6,005,627,616 bytes in total. Their exact files are hashed before inference. The
quantizer does not document the originating base-checkpoint commit; this is a
pinned derivative trial, not a claim of official checkpoint parity.

An isolated [llama.cpp runtime](https://github.com/ggml-org/llama.cpp/tree/620d2225cc436ab0b001e3200e590e3b286ef9ab)
supports the explicit Music Flamingo projector. A private observer records sampled
tokens, real end-of-generation versus the token cap, and the decoder's actual
float samples. All eight pilot inputs reproduce the earlier waveforms byte for
byte. The runtime's different mel floor has no surviving effect after Whisper
clamping on these eight windows; complete feature-tensor parity is not established.

Both conditions use the same eight clips, automatic language, greedy decoding,
256 tokens, 4,096 context and four CPU threads with Metal. The first prompt is the
official structured-lyric-sheet example. A separately frozen prompt-only trial
asks for the sung lyrics in their original language, without headings, timestamps
or commentary. Whole assistant outputs are scored; headers and repetitions are
not removed after seeing results.

| Same fixed pilot                          | Structured prompt | Plain prompt |
| ----------------------------------------- | ----------------: | -----------: |
| Completed outputs /8                      |                 3 |            7 |
| Japanese contextual owner witnesses /51   |                 8 |           13 |
| Japanese missing-owner witnesses /26      |                 2 |            3 |
| English insertions, eight reference words |               186 |            2 |
| Wall seconds, including eight model loads |              95.9 |         50.5 |
| Peak process RSS, GB                      |              6.28 |         6.38 |

The plain prompt retains the structured condition's witnesses and adds one gap
already recognized by Fun-ASR. Across both conditions, just one gap witness is
new versus all available exact-wave baselines. Its raw TIFA interval ends at the
crop boundary, is rejected by the ordinary filter, and has no native corroborator.
Neither condition supplies a selectable timing addition or a reading correction.
Japanese transcription accuracy remains unmeasured; these are source-match
opportunities, not an accuracy percentage. Do not expand this recipe merely for
its improved completion rate.

## Closing one source-reading hypothesis

The source-blind kana experiment nominates あま for a source-owned 天 group.
Existing singing-CTC evidence prefers that reading over all six frozen dictionary
competitors, both locally and across the full cue. A fresh Qwen six-way whole-cue
comparison also nominates it, with real-versus-control margins of 7.353 and 7.962
nats. The original word-token comparison remains withheld because a competitor
crosses a BPE boundary; it is not relabeled as a successful word-level result.

Fresh candidate-specific clocks confirm that changing the reading changes its
alignment: TIFA gives 2340–2690 ms and native Qwen 2320–2720 ms, agreeing within
20/30 ms. The chosen TIFA interval fits before the protected following word
without moving it. The old original-kanji native clock is not reused as the
candidate's observation. Fresh Whisper attention disagrees with the physical
pair and is reported separately.

This is stronger reading and boundary evidence, but the unchanged research rule
still qualifies only three of the cue's eight original groups, below its four-
group context requirement. Reading nomination: one; target physical pair: one;
selectable additions under that policy: zero. No saved reading or clock changes.
The rule's abstention is not evidence that the candidate is wrong, and this
development example does not establish a replacement admission rule.

## Singing-conditioned boundaries and longer source context

A separate [lyrics-aligner](https://github.com/schufo/lyrics-aligner/tree/72be8a14b9126c201e0b8920513764c44ccd3f9e)
jointly learns lyric-conditioned vocal separation and phone alignment. Its pinned
40.4 MB checkpoint loads strictly with restricted tensor loading. The pilot uses
the official CMU phone inventory, deterministic evaluation mode, no extra STFT
padding and one explicit Torch compatibility change. Upstream's CLI omits evaluation
mode, so these results do not claim stock-CLI parity. Word ends are observed
separator-state onsets from its DTW path, not reference labels.

On the same sixteen opened English development cues, all 96 original word owners
remain in the denominator. Original mixes give 57 correct onsets and 46 correct
complete intervals at 150 ms per endpoint; isolated vocals give 65 and 54. Each
condition still admits two incorrect unprotected additions through its tested
pairing rule. No correct interval is new relative to the earlier clock-family
union. This does not justify expanding that model. Mix processing takes 1.17
seconds after loading, with 0.33 GB peak process RSS on the M2 Pro.

A separate structural comparison joins these sixteen consecutive source cues
into two complete original-audio passages, 29.0 and 25.0 seconds. All intervening
source lines, original word groups and UTF-8 ownership survive. Clocks map back
through exact sample origins, without clamping or padding. TIFA's short-cue
baseline is rerun with the same helper and runtime as the longer condition;
only 70/96 endpoint pairs reproduce the historical cache exactly, so that cache
cannot isolate the context factor.

| Same 96 original words                      | Short cues: retained / strict correct | Long passages: retained / strict correct |
| ------------------------------------------- | ------------------------------------: | ---------------------------------------: |
| Singing-conditioned DTW model, original mix |                               96 / 46 |                                  96 / 35 |
| Fresh TIFA                                  |                               91 / 65 |                                  86 / 71 |
| Native Qwen alignment                       |                               92 / 56 |                                  94 / 69 |
| TIFA/native pair plus fixed lexical screen  |                               46 / 41 |                                  53 / 51 |

Strict correctness requires both endpoints within 150 ms. The lexical screen is
the unchanged, earlier short-cue source-blind Qwen observation; it is not a new
long-passage transcription. TIFA gains thirteen correct intervals and loses seven;
native alignment gains seventeen and loses four. Simply replacing every saved
clock would therefore introduce regressions.

An initial selection incorrectly enlarged the confidence unit from the original
lyric cue to the entire passage. It leaves three correct immutable additions.
A separately labeled **post-hoc** comparison keeps the complete original cue as
the confidence unit, while both aligners hear the longer passage. The same
minimum-two/half-cue context rule then selects eight additions, all eight correct,
versus two correct and one incorrect short-cue additions. It gains six correct
owners, loses no correct owner, and preserves all 52 existing clocks exactly.
This is promising development evidence, not prospective validation or an app
coverage gain. Freeze that distinction before the difficult-song pilot.

The prospective pilot covers 48 previously missing English-spelling groups from
six low-set songs, with 192 focal source groups in 35 original cues. Complete
multi-line contexts bring 605 original groups into 13 windows; auxiliary groups
remain separate from the 48-gap denominator. TIFA target text and romaji remain
unchanged. The native aligner receives the original source surfaces.

Fresh short-cue versus longer-passage runs retain 29 versus 34 of the 48 targets;
paired clocks increase from 14 to 15, gaining seven owners and losing six. Six
targets in each condition also have the fixed, earlier Fun-ASR lexical witness.
Neither condition yields an immutable insertion. Even perfect lexical evidence
cannot overcome the longer condition's 33 missing physical pairs, six failed
original-cue contexts, one missing adjacent qualifier and eight interval collisions.
These are overlapping-model agreement opportunities, not singing accuracy labels.

A separately frozen bounded-region trial allows automatic neighbors to move only
with paired fresh observations contradicting the old clocks, at most four groups,
verified unchanged outer anchors and complete nonoverlapping observed intervals.
All 48 targets still fail: 33 lack a physical pair, six lack context, two have an
unsupported region member, five lack a verified outer anchor, and two have an
observed interval overlap. All saved origins are explicitly automatic; user-edit
protection is not the cause of this null result. Do not spend more recognition
calls on the same clocks in the hope that lexical evidence alone will fix them.

The 13 TIFA passages take 4.37 seconds after loading, plus 0.99 seconds loading,
with 0.91 GB peak process RSS. Twelve new native contexts take 12.42 seconds;
one byte-identical five-word context reuses its authenticated observation. Fresh
35-cue TIFA takes 3.20 seconds after loading, plus 0.86 seconds loading, with
1.20 GB peak process RSS. These timings exclude cached vocal isolation.

## Supervised Japanese phone occupancy

A separate trial fits a small linear phone head over the frozen singing-HuBERT
encoder, using [GTSinger](https://huggingface.co/datasets/AaronZ345/GTSinger/tree/d78cd68d00135b1995da03f25fccb3a221efd8c1)
Japanese recordings with corrected phone intervals. The 2,000 singing clips total
3,343,442,192 bytes; speech clips are excluded. This tests supervised sustained
phone occupancy rather than another CTC clock or free-transcription prompt.

The bounded 16-clip pilot verifies every WAV's pinned hash, PCM24 decoding,
48-to-16 kHz resampling and all 8,737 native feature frames. Frozen final-layer
features take 1.43 seconds after loading, plus 0.51 seconds loading, with 0.67 GB
peak process RSS. This initial check measures frontend correctness and speed.

The dataset's Japanese text owners are mostly single characters. They must be
aggregated through exact converter-owned spans before measuring displayed words.
Marker/unknown phones and ambiguous or discontinuous ownership stay explicit.
Two singer-disjoint head folds keep all title variants grouped; the encoder's
unpublished training list means these are not certified encoder-unseen tests.
All data and trained products stay outside Git; no private song enters training.

The complete run extracts 1,159,240 native frames in 234.2 seconds after loading,
with 2.49 GB peak process RSS. Two fixed linear-head folds, including test-posterior
collection, take 33.6 seconds and 3.17 GB peak process RSS. A pre-fit review finds
one shared title differing only in capitalization; its normalized title is excluded
from both fitting pools. Validation selects epochs 13 and 29 within each training
singer. No test timing chooses a checkpoint.

All 2,000 test posteriors and three source-condition proposal sets close before
joining references. Of 17,110 displayed words, 17,061 have continuous usable
references assembled from phone intervals and 49 remain unscored; seven non-display placeholders stay in
the separate source ledger. TIFA receives the app's written readings on identical
resampled waveforms. Its 1,996 calls and 2,000 statuses finish without errors in
297.3 seconds after loading, with 2.40 GB peak process RSS.

Strict correctness below requires both endpoints within 150 ms of their reference.

| Qualified clocks, known references   | Strict correct | Wrong | Correct fraction of scored clocks |
| ------------------------------------ | -------------: | ----: | --------------------------------: |
| Retained TIFA                        |         13,876 | 2,147 |                             86.6% |
| Dense head, supplied phone oracle    |         12,337 | 2,379 |                             83.8% |
| Dense head, written readings         |          5,107 | 1,039 |                             83.1% |
| Dense head, dictionary pronunciation |          4,959 | 1,466 |                             77.2% |
| TIFA/written-head endpoint agreement |          4,872 |   348 |                             93.3% |

The supplied-phone condition isolates boundary estimation by providing annotated
lexical phone identities. The app must select a pronunciation separately. It fixes 441
TIFA errors but damages 798 correct TIFA clocks among shared observations. On
previously TIFA-withheld words, the written head offers 89 correct intervals and
139 incorrect ones. Neither direct replacement nor model agreement is safe enough
for automatic repair. No app timing is changed.

Source mapping also limits this trial: the provisional kana mapper requests
palatalized labial classes never observed in the corpus, affecting hundreds of
words. Those abstentions do not establish wrong kanji readings. Official
[MFA Japanese dictionaries](https://mfa-models.readthedocs.io/en/latest/dictionary/Japanese/Japanese%20MFA%20dictionary%20v2_0_1a.html)
retain palatalized labial distinctions; an unconditional alias would conflate
different source sounds. Keep unknown representations unsupported while testing
a separate, training-only kana-to-corpus-phone mapping. The corpus's exact MFA
version is undocumented, and its [repository](https://github.com/AaronZ345/GTSinger)
still lists Japanese annotation refinement as unfinished. These are additional
limitations of the benchmark, not grounds to discard its unfavorable results.

A separate decoder fits literal-phone duration distributions using only each
fold's training singer and training titles. It permits explicitly recorded
zero-frame phones, while an entirely unobserved word abstains. On the same
supplied-phone oracle, it produces 11,977 correct and 2,283 wrong qualified
intervals, fewer correct intervals than the original decoder. Its 2,103 qualified
words containing a skipped phone are only 60.7% correct; complete-phone words
are 88.0% correct. Compared with the original oracle, it gains 117 correct
intervals and loses 477, including newly withheld words. The duration recipe is
not adopted. These follow-ups reuse opened development references and are not
new held-out validation.

The fixed midpoint-layer trial also loses correct intervals: its supplied-phone
oracle has 12,023 correct and 2,511 wrong qualified words; written readings have
5,015 and 1,051, respectively. Feature grids and resampled audio are identical to
the final-layer trial. The result does not support changing encoder layers.
Feature collection takes 301.8 seconds, and both head folds with test-posterior
collection take 33.6 seconds with 2.96 GB peak process RSS.

A nine-frame temporal filter followed by the original linear classifier also fails
to improve timing. Its supplied-phone oracle has 12,033 correct and 2,523 wrong
qualified intervals; written readings give 4,991 /1,104. The temporal head gains
165 correct written-reading intervals and loses 281 relative to the original
linear head. It takes 167.9 seconds for both folds and test-posterior collection,
with 3.10 GB peak process RSS. Its median clock change is zero; improved mean
signed errors conceal worse absolute errors. No constant offset is fitted.

A training-only mapping audit finds that this corpus labels simple kana `mi` and
`bi` with its unpalatalized labial classes. Applying that convention to those
selected-reading morae, while leaving yōon and unsupported gemination unchanged,
restores 716 source-word class mappings. Written-reading qualified results increase
from 5,107 correct /1,039 wrong to 8,217 /1,706; every baseline-observed clock is
preserved. This repairs a representation restriction, without choosing a different
kanji reading. Among 1,038 words without retained TIFA clocks, the revised head
offers 136 correct and 212 wrong intervals. Agreement with a rejected raw TIFA
interval retains 97 words: 75 are correct in both models, 20 wrong in both and
two correct in only one model. The mapping helps, but neither its raw coverage nor
agreement with TIFA justifies automatic admission.

An external development comparison fits the original linear head on all 2,000
public clips for a fixed 21 epochs, chosen before PJS inference from the earlier
validation epochs. No PJS or private song is a training input. The PJS trial keeps
390 focal words and 949 full-context owners across 62 recordings. All waveforms
match the earlier native benchmark bit for bit. Unsupported neighboring phones
withhold 228 focal words; missing trained classes restrict the remainder further.
The head returns 123 qualified focal intervals: 108 correct and 15 wrong. TIFA
already has 389 correct of 390. Endpoint agreement keeps 109 TIFA intervals,
including the existing error. This does not justify adding the head to the app.
The all-public fit takes 33.7 seconds and 3.65 GB peak process RSS; PJS feature
collection takes 5.71 seconds after loading and head inference takes 0.39 seconds.

A separate support cutoff is fitted only on each head's training-singer validation
titles, using actual-frame source-versus-rival phone margins and fixed one-vowel
counterfactuals. Thresholds close before the full held-singer proposals. It retains
89 raw TIFA intervals, 80 correct and nine wrong, from 8,390 physical pairs. None
of the TIFA-withheld words passes the cutoff; no complete context or ordered gap
addition survives. The cutoff's apparent validation precision does not transfer
reliably across singers. It is not adopted or retuned against these test outcomes.

The bounded final-two-block adaptation also selects both original epoch-zero
models: all five adapted epochs have worse training-singer validation loss. The
trial keeps its FP32 replay condition separate from the earlier stored-FP16 head.
Caching block-ten features takes 269.3 seconds, with exact unmodified-tail and
old-final-output reproduction on all 2,000 recordings. Fitting and collecting both
posterior conditions takes 355.9 seconds, 3.28 GB peak process RSS and sampled MPS
maxima of 1.83 GB current allocation /6.60 GB driver allocation. These samples do
not guarantee the true GPU peak. No adapted checkpoint is promoted.

Per-record mean centering on the original final-layer features is also mixed.
Keeping the original training-fold scale, written-reading qualified intervals gain
253 correct and lose 250, while spoken readings gain 349 and lose 293. New false
TIFA agreement admissions increase. Training and posterior collection take 43.8
seconds with 2.40 GB peak process RSS. The feature-shift diagnostic motivates the
test but does not justify promoting this normalization.

The source-owned geminate lattice gives a larger representation gain on the
original head: 9,778 correct /2,009 wrong qualified intervals, versus fixed
Scope-B's 8,217 /1,706. It adds 1,561 correct intervals and loses no previously
correct fixed-path interval, while adding 303 wrong intervals. Fully representable
source contexts rise from 1,448 to 1,767; the older aggregate's 1,451 count disagrees
with its own rows, so comparisons use the authenticated per-record data. On the
1,038 reference-eligible words without retained TIFA, the lattice supplies 155
correct /229 wrong clocks versus 136 /212 for the fixed path. This is useful
representation work, with no demonstrated app gain yet.

## Existing fine-timed lyric sources

An audit of the ten frozen recordings finds no overlooked provider word clock in
their saved source payloads. Nine Spotify responses are `LINE_SYNCED`; their
`syllables` arrays are empty and their `words` fields contain whole lines. The
LRCLIB source also has only line timestamps. Existing automatic fragments came
from TIFA rather than a missed provider schema.

The next comparison uses actual fine-timed alternative sources. Public Spotify
embed metadata supplies titles, artists and recording durations independently of
our model processing times. [Karaoke Mugen](https://github.com/karamoe/karaokebase)
has a full Japanese Just Awake candidate
at 219 seconds, close to Spotify's 218.573 seconds. A source-only proposal, frozen
before inspecting saved timing membership, maps 181 of the 306 original words
through complete ASS karaoke chunks. It offers clocks for 75 of the 123 saved
gaps. Those are candidate counts, not verified additions. Independent parser review
finds that a combined override block's leading `\k90` rest was missed, making every
proposed clock 900 ms early. Those clocks are invalid and remain unadopted; a
corrected parser must precede endpoint comparison. A separate all-optimal-path
whole-song text mapping finds 292 candidate word owners, resolving many line
segmentation and repeat ambiguities. Its timing fields inherit the same parser
bug and are also withheld pending regeneration.

The same rule maps 48/377 words for 天天天国地獄国, including four old gaps;
its normalized lyric stream differs substantially. The other full-length catalog
candidates map only words that already have saved clocks. The parser correction
must be applied to these files too. A QQ pilot for 嘘 finds
the same title, artist and album with a whole-second duration consistent with the
public catalog, and returns original and romanization QRC tracks with 36 timed
lines and 364 chunks each, using the pinned
[LDDC client and parser](https://github.com/chenmozhijin/LDDC/tree/84631e8cd011fcc3f71ca0ae017e2c9758958ffc).
The first availability probe discarded its payload. A subsequent one-shot lookup
preserves the encrypted response, decoded tracks and anonymous session privately.
Matching chunk counts alone do not establish original/romanization ownership or
correct clocks on the Spotify recording; those checks remain separate.
Musixmatch's anonymous macro endpoint returns HTTP/API success for Just Awake but
identifies an unrelated Drake recording; that response is rejected. No candidate
from this source comparison has changed app state or saved coverage.

The corrected whole-song karaoke mapping offers clocks for 119 of Just Awake's
123 saved gaps. Existing authenticated acoustic caches cover every nominee.
Only one gap agrees with both timing models within 150 ms at both ends; its
original context and neighboring saved clock prevent admission. NetEase returns
word-timed YRC for LOST IN PARADISE: 437 of 476 original owners map through whole
chunks, including 132 of 146 saved gaps. Its cached checks find two three-way gap
agreements, also withheld by their original context. Neither case justifies more
inference under the unchanged admission rule.

QQ's supplied Uso clocks are also inconsistent with the local observations.
On the separate 170-owner Japanese source, dictionary TIFA retains 155 words and
roundtrip-guarded provider readings retain 156. Only 11 and 12 respectively agree
with the supplied intervals within 150 ms at both ends. Native alignment supplies
122 positive bounded observations, only two agreeing with QRC. Each reading arm
has 19 strict TIFA/native pairs; one also agrees with QRC. Those are consistency
measurements, not reference accuracy. Possible title/credit lines and a clipped
long cue remain separately reported. Supplied coverage alone is not promoted.

## Source-qualified Japanese pronunciation input

The source comparison exposes a separate input issue: TIFA routes ASCII lyric
text through its English pronunciation converter. The frozen romaji-only Uso
source has 158 English-routed words and nine unresolved words, despite being
Japanese lyrics. An exact whole-song phoneme reconciliation with the Japanese
candidate qualifies 137 original words; allowing complete kana-mora edges
qualifies another 14 without requiring a complete alternative-source word.
That second rule supplies reading text only, never a cut or copied word clock.

The fixed comparison retains all 167 original owners, original displayed romaji,
UTF-8 spans and 27 original Rust audio windows. Unqualified words keep their
original model input. No QQ word clock or QQ line window enters either repaired
condition.

| Same 167 original owners                 | TIFA retained, mixture | TIFA retained, production vocals | Paired clocks, mixture / vocals |
| ---------------------------------------- | ---------------------: | -------------------------------: | ------------------------------: |
| Original romaji input                    |                     96 |                               99 |                          21 /24 |
| 137 source-qualified kana inputs         |                    137 |                              132 |                          36 /30 |
| 151 inputs with complete kana-mora edges |                    144 |                              140 |                          35 /31 |

Paired clocks require the unchanged native aligner and both physical endpoints
within 150 ms, with the existing duration and crop-interior rules. They are
consistency counts, not acoustic lexical verification or reference accuracy.
On the vocal stem only one complete original cue meets the minimum-two/half-cue
physical context rule in each arm. Changing the native model's input to Japanese
glyphs or kana does not improve the mixture comparison, so the vocal comparison
keeps its original input and reuses its authenticated cache.

The paired original/whole-owner mixture run takes 5.55 seconds after loading;
the kana-mora run takes 3.34 seconds, with 950 MB peak process RSS. The three-arm
production-vocal comparison takes 6.39 seconds after 0.91 seconds loading, with
1.02 GB peak process RSS. These are fresh retention counts, not verified saved
recoveries. The existing 116/167 Experimental result also includes additional
processing. Compare original saved gaps, preserved clocks and independently
supported additions separately before integrating this language repair.

Joining the original 116 saved intervals leaves 51 original gaps. Each vocal
condition has three gap-level physical pairs, two with sufficient cue context.
The immutable interval check permits one original-input candidate versus two in
each kana condition, preserving every saved interval exactly. Lexical evidence
has not qualified those proposals. This isolates a real pronunciation-routing
restriction, but the current physical checks do not establish a substantial
saved-coverage gain.

A broader language-routing ablation tests 150 reversible ASCII-to-kana candidate
inputs across five Japanese-labeled Spotify sources, including 58 saved gaps.
It retains all 589 original owners in 98 affected cues. The unchanged English
routing retains 415 words; the kana condition retains only 227, in 8.91 seconds
after loading. A song-level Japanese label and dictionary roundtrip do not certify
that its Latin words are Japanese. This broader rule is withheld; it does not
expand the separately qualified Uso source mapping.

## Supervised TIFA adaptation

The next controlled trial adapts the conditional TIFA aligner itself. A strict
mapping to its existing vocabulary admits 1,043 complete Japanese GTSinger clips;
957 unsupported clips remain accounted for. The first fold trains on 215 eligible
clips from one singer and selects on 40 eligible clips from 57 fixed validation
clips. All 1,359 opposite-singer recordings remain outside fine-tuning and model
selection. Shared normalized song titles are excluded from fitting.

The adapter uses the pinned upstream frame-alignment, span-contrastive,
token-identity and frame-identity losses, including its sequence-edit and
masked-token input policy. It preserves gap class zero, sub-grid phone spans and
actual 48→16→48 kHz frontend geometry. Four input-contract tests and synthetic
loss/gradient fixtures pass before fitting. A 16-clip no-update profile takes
14.43 seconds, including the longest clip and both eligible right-edge frame
cases.

The first fit exceeds the 0.65 MPS memory guard once optimizer state is present.
Its partial outputs remain separate. Training-only activation checkpointing
reduces memory, but ordinary checkpointing initially changes dropout gradients:
the installed Torch 2.14.1 checkpoint code does not capture the MPS random state.
Explicit per-layer MPS state preservation restores identical losses, with relative
gradient L2 error of 1.3e-9 on the longest clip. Four accumulated longest-clip
gradients and a real optimizer step then fit with 2.64 GB observed GPU-driver
memory; those profile weights are discarded.

The corrected run keeps the original folds, seeds, objective and optimizer:
AdamW at 1e-5, betas (0.9, 0.98), no weight decay, norm clip one, whole-clip batch
one and accumulation four. It finishes three epochs in 308 seconds. Clean
validation loss falls from 3.405 to 2.090, selecting epoch three; this is a
selection statistic, not word-timing accuracy. Peak process RSS is 2.79 GB and
the largest sampled MPS-driver allocation is 4.88 GB. These memory measures
include different allocations and should not be added together.

The frozen source-word replay compares the original and selected checkpoints
on all 1,359 excluded recordings. It uses the original converter-owned words and
kana, not human reference phone sequences as model input. Its population has
11,747 displayed words and 11,754 source-ledger groups; 11,722 displayed words
have known reference intervals and 25 do not. The 16-record original replay
reproduces every cached source owner and clock exactly. Both full prediction sets
close before the reference join.

| Same 11,722 reference-known words | Original correct / wrong | Adapted correct / wrong |
| --------------------------------- | -----------------------: | ----------------------: |
| Raw observed intervals            |            10,037 /1,576 |           10,131 /1,525 |
| Retained intervals                |             9,827 /1,324 |            9,898 /1,248 |

Correctness requires both endpoints within 150 ms. Retained timing gains 216
correct intervals and loses 145 previously correct intervals, a net increase of 71. Of the newly retained observations, 58 are correct and 54 are wrong. Total
retention falls from 11,174 to 11,169, including 23 reference-unknown observations
in each condition. All four structurally withheld contexts and 30 unsupported
words remain explicit. There are no collector errors.

This is a small controlled timing improvement without a completeness gain. It
does not justify replacing the original model or accepting its new retentions
unconditionally. The opposite training fold remains a separate test of the same
frozen fitting recipe. No adapted model has changed app state or private-song
saved coverage.

## Remaining work

The first experiments do not satisfy the plan's multi-song integration target. Continue
with independently verified English runs, local sung-reading alternatives and stronger
anchor evidence. Keep the ten-song set fixed, test new admission rules against the
existing references and negative controls, and report gains, losses and moved boundaries
separately. Do not rebuild the capture helper or ask the user to annotate songs.
