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
transformed timestamps are unusable. The next bounded factor changes F0 contour
variance while preserving median register; it does not repeat the failed shift.

## Remaining work

The first experiments do not satisfy the plan's multi-song integration target. Continue
with independently verified English runs, local sung-reading alternatives and stronger
anchor evidence. Keep the ten-song set fixed, test new admission rules against the
existing references and negative controls, and report gains, losses and moved boundaries
separately. Do not rebuild the capture helper or ask the user to annotate songs.
