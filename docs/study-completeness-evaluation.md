# Mac word-timing completeness

The approved extension of [PR #3's plan](plans/audio-first-readings.md) prioritizes
retained word timings in the Mac app. The selected `singing-word-recovery-v1` stage
uses the already downloaded singing model to check fresh TIFA intervals, including
bounded phonetic hypotheses for English words sung with Japanese pronunciation.
The original TIFA action and current reading-repair policy remain separate.

## Fourteen-song coverage

The runtime stage ran on all 671 saved lyric windows, with the current fifteen
automatic reading occurrences applied to its targets. Inputs retain original source
byte spans, Rust-exported sample bounds, zero-delay recording clocks and the native
baseline denominator. The stage adds **72 words**, taking retained coverage from
**3,435/4,160 (82.6%) to 3,507/4,160 (84.3%)**. All existing intervals are identical.
All fourteen full native jobs subsequently produced exactly the same counts, independently
repeating separation, transcription, reading selection and alignment with the standalone
runtime. Coverage means a stored interval, not a listening-verified correct highlight.

| Recording            | Previous Experimental | New Experimental |  Added |
| -------------------- | --------------------: | ---------------: | -----: |
| SAKURA               |               265/265 |          265/265 |      0 |
| うれしくて           |               363/423 |          363/423 |      0 |
| departure!           |               209/221 |          209/221 |      0 |
| spiral               |               238/245 |          238/245 |      0 |
| Koino Uta            |               223/307 |          252/307 |     29 |
| Tabi no Tochuu       |               153/153 |          153/153 |      0 |
| NEVER SAY GOODBYE    |               367/430 |          369/430 |      2 |
| Just Awake           |               183/306 |          183/306 |      0 |
| the WORLD            |               135/153 |          135/153 |      0 |
| 色彩                 |               270/291 |          271/291 |      1 |
| 君のせい             |               259/270 |          259/270 |      0 |
| 今世大革命           |               188/246 |          197/246 |      9 |
| Bling-Bang-Bang-Born |               335/473 |          348/473 |     13 |
| 天天天国地獄国       |               247/377 |          265/377 |     18 |
| **Total**            |       **3,435/4,160** |  **3,507/4,160** | **72** |

The stage took **21.9 seconds for the complete suite** on M2 Pro /16 GiB with cached
singing posteriors and fresh TIFA inference. This excludes vocal separation, transcription,
reading selection, inference of the singing posteriors, integrity checks and startup.
It adds no model downloads or new Python dependencies. All input, model and implementation
hashes, per-word observations and timing comparisons remain in private run receipts.
The focused stage's lifetime peak RSS was 885 MB; this excludes the preceding model
processes and accelerator allocations.

## Accuracy checks and limits

Fifteen existing negative inputs contain 105 words: thirteen wrong-verse vocal crops,
one silence crop and one instrumental crop. The exact runtime recovery stage admitted
**zero timings** when started without anchors. These controls cover Japanese phrases;
a second test uses the first eligible English-heavy phrase from each of seven songs
over a different phrase's audio window from that song. It admits **0/38 words**.
Neither control set establishes precision on every English or mixed-language passage.

The existing PJS benchmark supplies 390 uniquely mapped human word envelopes across
62 recordings. With normal TIFA timings, the stage changes none: 389/390 meet onset
error ≤150 ms and offset error ≤200 ms before and after. To exercise recovery, a
separate run hides those frozen timings before inference, keeping audio and readings
unchanged. The stage recovers **138/390**, all **138/138** meeting both limits.
The word-level Wilson interval is **97.3–100%**; words from the same recording are
correlated, so this is not a population confidence guarantee. These artificially hidden
easy intervals do not prove the correctness of the 72 naturally missing commercial words.
Human labels are opened only after inference observations close; no labels select a
reading, candidate path or timestamp. Both runs use the already opened development
corpus, with no fresh holdout claim.

## Other trials

- A Japanese-only fresh TIFA plus singing-verifier pass added 41 words. Dictionary
  pronunciation shadows added 43, but the small difference did not justify changing
  the bundled converter contract in this update. Written/displayed readings stay intact.
- Explicit English Whisper large-v3 recognition on 162 affected windows, each on mix
  and Kim vocals, added four words under unique lexical matching and independent timing
  checks. A nonfinite diagnostic was saved as undefined and an interrupted run resumed
  into a new authenticated directory. No nonfinite value became timing evidence.
- Fixed direct and Japanese loanword phonetic passes individually added 18 and 20 words.
  The shipped deterministic order is selected pronunciation, direct, then loan; all
  stages preserve earlier intervals. Counts cannot simply be summed because words overlap
  and the ordered combination can provide more phrase context.
- The singing-trained [Echora checkpoint](https://huggingface.co/hcX02/echora-mms-300m-multilingual-lyrics-forced-aligner)
  at revision `701595f1be1125cce835d4e32fd432358ea8ed9f` was tested locally on the
  294 windows containing missing words. Its lead head loaded completely; only the
  documented background head was unused. It added six words with TIFA checks, and
  no words when paired directly with RomajiASR under the fixed two-model gate. It
  adds 1.26 GB of weights and has personal noncommercial terms. It is **not adopted,
  bundled or redistributed**. Checkpoint SHA-256:
  `ac97765319ad0f94f42e665adeae668c605ed8b119369586d2e5caaf2f4ead6d`.

## Native app validation

Both standalone timing runtimes ran through the native pipeline on all fourteen cached
recordings. Original TIFA remains **3,121/4,160**, with every interval identical to the
previous release. Experimental reaches **3,507/4,160**, with **72 additions, zero losses
and zero moved existing intervals**. Source snapshots, recording fingerprints, original
denominators and all fifteen saved automatic reading occurrences match the baseline.
No lyric-text substitutions are added. The six verified Tabi corrections remain intact.

All **28 saved action results** passed native reopening, reconversion and earlier-version
restoration checks, including valid word spans in hiragana and romaji. Existing offline
fixtures cover nonzero delay, protected edits, changed grouping, cancelled/stale jobs and
the three persisted display modes. Tests write isolated result directories and never
change the user's app data.

Cached-weight native jobs took a median **199.6 seconds Experimental** (range 149.6–314.9)
and **7.1 seconds TIFA** (range 5.9–11.4). Largest recorded command/child maximum RSS
was **3.16 GB Experimental** and **2.68 GB TIFA**. Two-second process-tree sampling
covered 25 jobs, starting during the second song, and peaked at **2.86 GB summed RSS**.
RSS can count shared pages twice and excludes accelerator allocations; these values are
not a complete unified-memory peak. System swap used fell from 10,990 to 6,546 MiB,
and system free-memory percentage rose from 29% to 65%. This shared-machine observation
includes background compilation and packaging, so neither swap changes nor the latency
difference from the prior 169-second run is attributed solely to this stage. All jobs
completed on M2 Pro /16 GiB without an out-of-memory failure. MPS/MLX allocation peaks
and first-download latency were not remeasured.

The configured ARM64 app and distribution ZIP were rebuilt using the new Experimental
runtime and verified existing helpers. Packaging kept the inference directories stable
while native jobs ran. Signature verification, relocation to a path with spaces, clean
environment conversion, bundled helper checks, notices, library paths and the registered
Spotify callback all passed. No model weights, secrets or private instruction files are
bundled. The inference implementation is `1f330c1`; experiment tools are `c191bfc`.
The full mandatory repository gate passes with 51 romanizer tests, 119 research boundary
tests, 92 TIFA/refinement tests, Rust tests, formatting, lints and export checks.

## Reproduction

Run `scripts/experiment-mac-singing-recovery.py` with a private suite manifest, the
authenticated audio-only RomajiASR recognition run, the matching audio manifest and
the pinned TIFA archive. `scripts/check-singing-recovery-controls.py` tests private
negative cases. `scripts/benchmark-singing-gap-recovery.py` scores the frozen PJS
envelopes; `--mask-frozen` exercises artificial timing gaps. These commands require
local model environments and explicit private inputs. Routine `scripts/check.sh`
tests synthetic protocol, source ownership, rejection and persistence fixtures without
network access, model inference or Spotify. No recordings, lyrics, predictions,
references, models or private instruction files are published.
