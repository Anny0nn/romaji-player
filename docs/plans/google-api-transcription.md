# Free Google API transcription and singing timing trial

Status: Approved (2026-11-16; maintainer directly approved implementation)

## Goal

Use the maintainer's free Google API access to test cloud transcription as the next
Experimental backend, reducing local model work where measured singing accuracy
supports it. Compare Japanese, English and mixed singing on the existing recordings;
assess word timing separately from lyric recognition. Keep the native macOS app,
five lyric views, original TIFA action and durable per-song versions.

The maintainer explicitly accepts Google's free-tier use of submitted public song
data to improve its models. Cloud processing is authorized for this trial; the
earlier local-only preference does not exclude it. API access is provided by each
user's own key, with no application server or shared developer credential.

This branch starts from `main`. It does not depend on the unfinished local-model
research in [PR #5](https://github.com/Anny0nn/romaji-player/pull/5). Existing recordings,
frozen selections and authenticated cached observations may be reused; importing
unmerged implementation requires an explicit plan update in this PR.

## Approach

### Eligible models and free access

Google documentation checked on **2026-11-16** lists free Standard API input/output
for the following candidates. Recheck pricing, audio support, exact model IDs and
the supplied project's actual access before running; a model listing alone does
not prove free access. Start on a project whose AI Studio tier is Free and billing
is not enabled. A billed project requires separate consideration even when the
same model also advertises a free tier.

| Candidate               | First comparison                                                          |
| ----------------------- | ------------------------------------------------------------------------- |
| `gemini-3.5-transcribe` | Dedicated transcription, with word timestamps off and on as separate arms |
| `gemini-4-hydrogen`     | New general multimodal model, audio-only lyric transcription              |
| `gemini-3.8-flash`      | General multimodal transcription challenger                               |
| `gemini-3.5-flash-lite` | Faster general multimodal comparator                                      |

The [pricing table](https://aistudio.google.com/docs/pricing) establishes advertised
free access, subject to [project-specific quotas](https://aistudio.google.com/docs/rate-limits).
The [Transcribe model card](https://aistudio.google.com/docs/models/gemini-3.5-transcribe)
lists Japanese and warns that timestamps can degrade recognition. General models
accept audio according to their linked cards: [Hydrogen](https://aistudio.google.com/docs/models/gemini-4-hydrogen),
[Flash](https://aistudio.google.com/docs/models/gemini-3.8-flash) and
[Flash-Lite](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite).

Also inspect the key's other free Google endpoints before freezing the roster.
Gemini Transcribe Live is a possible later streaming comparator, rather than a
prerequisite for this file-based trial. [Gemma 4](https://ai.google.dev/gemma/docs/core/model_card_4)
has audio-capable E2B/E4B/12B variants, but the
[hosted Interactions roster](https://aistudio.google.com/docs/interactions-overview#supported-models)
lists 31B and 26B variants, which lack audio input. Do not substitute local Gemma
execution for a free hosted audio endpoint. Text-only models can propose spelling
alternatives, but cannot verify what was sung. Google Cloud Speech-to-Text is a
separate product: its [pricing](https://cloud.google.com/speech-to-text/pricing)
shows a limited V1 free allowance and metered V2 recognition. Exclude paid services
and temporary trial credits from the default no-cost roster.

### Reproducible API collector

Add an explicit research command using Python's existing standard-library HTTP
facilities, with no new SDK dependency initially. Use Google's documented
[Interactions API](https://aistudio.google.com/docs/interactions-overview) and
[transcription configuration](https://aistudio.google.com/docs/transcribe).
Read `GEMINI_API_KEY` at runtime from the environment; document loading it from
the ignored `.env`, with an empty placeholder in `.env.example`. Never put a key
in command arguments, request URLs, diagnostics, caches or build-time settings.

Start with authenticated original-mix crops from the frozen ten-song suite in the
[catalog](../study-song-catalog.md). Choose one existing crop per song by a
source-only rule before opening API outputs; include Japanese, English,
romanized Japanese, mixed language and known reading regressions. All candidates
receive the same samples. Use existing vocal crops only as a separately named
second comparison if original-mix failures justify them. No new capture or local
model run is needed for the first API pass.

Persist a private manifest with recording/crop hashes, sample rate, exact sample
bounds and global origin; freeze the model roster, prompts, language routing,
generation limits, timestamp setting and controls before collection. General
models receive only audio and an instruction to transcribe audible sung words in
their original languages, preserve repetitions and omit uncertain words. Supply
no title, artist, downloaded lyric text or reference clocks. Transcribe uses
verbatim mode without custom vocabulary, diarization or smart rewriting. Start
with automatic language detection; any explicit Japanese/English hint is a
separate frozen comparison, never chosen from whichever output looks better.

Use documented audio encodings; hash both source samples and actual uploaded
bytes, recording any conversion. Bound inline requests including base64 overhead.
Where the endpoint requires Files API uploads, track remote IDs and clean up on
success, failure and cancellation; retain failed-cleanup receipts for retry.
Request stateless interactions where supported. These controls do not change the
maintainer's acceptance of free-tier product improvement.

Run sequentially with a frozen request/audio/token budget, checkpoint every crop,
and reuse successful identical requests after restart. Retain the exact requested
model and any returned model version, API revision, UTC time, response status,
finish reason, usage, latency and recipe hashes. Hosted weights cannot be pinned
like local files; identify missing version metadata explicitly. Redact credentials
before saving errors; keep lyric-bearing payloads outside Git in restricted files.
Malformed, blocked, truncated or timed-out replies remain explicit failures.
An invalid candidate remains a rejected observation while collection proceeds to
the next preselected crop; network/quota failures stop collection. This allows the
offline timing comparison to retain zero-duration predictions without accepting them.

Respect Retry-After and provider retry metadata with bounded backoff. Daily quota
exhaustion leaves work resumable; cancellation stops further requests. Do not
rotate keys/projects, enable billing, choose paid endpoints or silently invoke a
local model when a free request cannot run. API quotas may span several days.

### Recognition and timing are separate evidence

Retain immutable API output before matching it to source groups. A proposed reading
must map uniquely to complete original UTF-8 owners, preserving protected edits
and earlier versions. Ambiguous repetitions, partial words and unsupported
romanization remain withheld. Generated kanji spelling is not a verified reading.

The current local transcript adapter consumes Whisper word probabilities and
timestamps. Introduce an explicit provider-neutral candidate representation:
missing confidence stays absent, segment timing stays segment timing, and a
model's written confidence is not a calibrated probability. Do not manufacture
Whisper-compatible scores to satisfy existing admission checks. Two Google
models, repeated prompts or mix/vocal views do not establish independent acoustic
verification merely by agreeing.

Evaluate Transcribe's returned word annotations as timing proposals in a separate
arm. General-model generated clocks are also proposals. Require finite ordered
intervals inside the actual crop, source ownership, physical/context checks and
boundary validation against existing references before app admission. Never divide
line duration among words, split a provider interval to invent word endpoints or
borrow another occurrence's clocks. Report both-endpoint error within 150 ms
separately from retained coverage, and keep missing references unknown.

Use cached local results as the comparison baseline, rather than rerunning all
models. Include silence, unrelated-audio and shifted-crop controls: public-song
memorization can produce plausible text without following the supplied audio.
Training overlap is acceptable, but these recordings are development data and
cannot establish unseen-song generalization. The agent owns evaluation; the
maintainer is not asked to label or time recordings.

### App integration after evidence

The latest maintainer-directed experiment is provider-first: use the already
fetched Spotify/LRCLIB source, obtain initial local timings with existing readings,
then ask Gemini for contextual kana tied to the exact original word IDs. Keep
the full fetched lyric context, source text, group boundaries and earlier timing
version fixed. Do not provide timing or dictionary kana as model hints. Null or
unchanged suggestions preserve that version; changed acoustic targets require
canonical conversion, independent checks and fresh alignment of the affected cue.
Text-only suggestions cannot certify unusual sung readings. Optional audio clips
or silence trimming may be tested later, but are not a prerequisite. Any future
clip keeps its original recording origin and explicit time mapping.

The [provider-first checkpoint](../study-google-api-evaluation.md#provider-first-lyrics-timing-then-gemini-kana)
has ten prepared requests /66 owners and strict response/realignment tests. Fresh
Gemini readings remain blocked by the existing quota deadline; no app promotion
or further recording/password access is required for preparing this experiment.

The maintainer subsequently prioritized the hybrid: Google proposes lyric text
and sung readings; existing local models check and time accepted candidates.
Start from the cached Hydrogen outputs and authenticated recordings, requiring
no API, Spotify or Keychain access. Keep alternative text in separate candidate
snapshots. Compare the existing and candidate text on identical float32 Rust
crops with original-source identity checks and independent singing observations.
The [offline follow-up](../study-google-api-evaluation.md#offline-hybrid-follow-up)
records this completed comparison; its mixed results do not authorize app promotion.

Publish an aggregate pilot report before expanding to the same frozen ten full
recordings. Freeze any selected recipe before that expansion. Compare correct
changes, wrong changes, preserved correct readings, omissions, hallucinations,
source-owned coverage, boundary errors, request failures, quota use, wall time
and client memory on M2 Pro /16 GiB. Do not call unknown boundaries correct or
choose the winning model separately for each word.

The first integration can replace Experimental's heavy transcription stage if
recognition improves on the paired pilot without new known reading regressions
or false acceptance of controls. Adopt API word timing only if reference checks
also improve correctness while preserving known-correct intervals. If cloud text
helps but cloud clocks fail, report a hybrid explicitly and retain the measured
aligner. If neither helps, record the result and leave the backend unpromoted.
Full removal of local alignment requires evidence; an API-only result remains
the intended comparison, not an assumed outcome.

Integrate the selected provider with the existing Rust HTTP/proxy infrastructure.
Keep credentials in the existing native credential-store architecture and place
key/model/backend settings under Options. Each installation supplies its own key.
Show the selected cloud backend and actionable missing-key/quota errors; saved
results reopen without API access. Preserve the two timing actions rather than
adding a third button. Avoid local weight downloads for stages replaced by cloud
inference. Cancellation and stale-result checks must cover network completion,
and save only complete source-validated versions with provider/model provenance.
Update implemented design and setup documentation only as behavior lands.

## Steps

Implementation checkpoint (2026-11-16): the collector and offline tests are
implemented. The [partial pilot report](../study-google-api-evaluation.md) records
all four model trials, rejected zero-duration word annotations and the provider's
quota stop until at least 2026-11-17 07:59:59 UTC. Remaining controls, accuracy
evaluation and conditional app integration are unfinished; no backend is promoted.

1. Review this draft, then record direct implementation approval in its own commit.
2. Add the bounded API collector, neutral candidate contract and offline fixtures;
   verify supplied free-project access without exposing the key.
3. Run the frozen paired pilot and negative controls; publish aggregate results and
   a concrete backend decision, then expand promising recipes within the ten-song cap.
4. Integrate qualified cloud stages, credential/settings handling and durable result
   provenance on this branch. Document any remaining local stages and their evidence.
5. Run repository and package checks, update this plan to Implemented when its work
   is complete, and retain a draft PR until the result is ready for review.

## Tests and checks

The initial pre-push run exposed a branding fixture inheriting Git hook repository
variables and modifying the caller's index/configuration. Isolate its Git commands
from those variables so subsequent required checks cannot alter the real checkout.

Add network-free fixtures for provider response parsing, Unicode source ownership,
ambiguous repeats, absent confidence, segment-versus-word timestamps, invalid clocks,
truncation, refusal, quota/backoff, bounded retries, resume identity and secret
redaction. Use synthetic lyrics and HTTP responses. Add source/reading and sync
regressions for every changed mapping or timing behavior. Exercise cancellation,
stale source/edit revisions, key replacement, older-version loading and reopening
all five views without network access.

Wire new checks into `scripts/check.sh`, with fast syntax/lint in `--quick`; neither
gate calls Google or loads real models. Run the full gate at the PR head. After app
integration, run the relevant standalone package smoke checks with cloud calls
mocked; live trials remain explicit commands outside hooks. A green check suite
does not substitute for the reported singing measurements.

## Out of scope

Paid APIs or automatic billing upgrades, shared keys, a hosted backend, manual word
timing, fabricated clocks, new lyric modes, changing the frozen song selection,
publishing recordings/full lyrics/credentials/private research artifacts, and
deleting the established local paths before a qualified replacement exists.
