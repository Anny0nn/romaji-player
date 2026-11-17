# Free Google audio API pilot

The API collector is implemented; the app migration is **not implemented**. The
2026-11-16 pilot establishes working free-project access and exposes recognition,
timing and service limitations. It does not establish improved singing accuracy
or qualify a replacement for the shipped transcription/alignment pipeline.
The [approved plan](plans/google-api-transcription.md) remains in progress.

## Inputs and collection

The maintainer confirmed that the supplied key belongs to a Free-tier project
with billing disabled and accepts free-tier product-improvement use of public
song data. Model discovery listed all four planned candidates. No billing was
enabled and no paid endpoint was selected.

The earlier temporary recordings were unavailable. The unchanged, fingerprinted,
already authorized capture helper recovered the same frozen ten recording IDs.
These are fresh captures, not byte-identical historical observations. Rust's
existing explicit crop exporter authenticated the new float32 recordings and
exported their source snapshots, owners and exact sample bounds. Earlier saved
coverage figures cannot be treated as reference clocks for these new captures.

Before opening pilot outputs, select the first Rust crop at or after 20 seconds
with at least four source groups for each recording, ordered by sample start and
occurrence. This gives **10 song crops /66 source groups /51.59 seconds**.
All models receive identical mono 16 kHz PCM16 WAV bytes, converted by rounding
float32 samples multiplied by 32768 and clipping to the PCM16 range. Preserve
both source and upload hashes. The main manifest SHA-256 is
`a78fbca8f6e00366e269f2953ef2a8c23143030f60d165496ee6a5e1a9d96171`.

Add five seconds of digital silence as a control. Requests contain no downloaded
lyrics, title, artist or reference clocks. General models receive the frozen
audio-only transcription prompt; Transcribe uses verbatim mode, automatic
language routing and no vocabulary hints. Its word-annotation setting defines a
separate arm. Preliminary one-second silence transport checks are not part of
the main pilot table.

All lyric-bearing responses, source ledgers, collector source snapshots and
request/recipe hashes remain private. Hosted weight revisions are unknown where
the response supplies only a model name. Existing local results were not rerun
or represented as independent listening references.

## Partial results

| Model /arm                                | Song crops attempted /10 | Nonempty usable transcripts | Other observations                                                   | Main silence control                         |
| ----------------------------------------- | -----------------------: | --------------------------: | -------------------------------------------------------------------- | -------------------------------------------- |
| `gemini-3.5-transcribe`, timestamps off   |                       10 |                           2 | Seven empty completed song replies; one HTTP 503 failure after retry | Empty text                                   |
| `gemini-3.5-transcribe`, word annotations |                        7 |                           4 | One rejected timing reply; one HTTP 503 failure; one HTTP 429        | Not reached                                  |
| `gemini-3.5-flash-lite`                   |                       10 |                          10 | All main requests completed                                          | Hallucinated “La la la la la”                |
| `gemini-4-hydrogen`                       |                       10 |                          10 | All main requests completed                                          | Explicit “No audible sung words.” abstention |
| `gemini-3.8-flash`                        |                        1 |                           0 | Service failure followed by transport timeout; 151.68 seconds total  | Not reached                                  |

Continuation manifests contain only previously unattempted cases from the same
frozen main manifest. Failed crops remain failures and are not retried through
new projects or keys. The initial timestamp reply was inspected before collecting
the remaining cases; parser changes preserved rejection and allowed independent
later crops to be collected rather than ending the entire timing comparison.

The rejected timestamp reply genuinely contains word annotations whose start
and end offsets are equal. This is not a field-name/parser mismatch. Four other
song replies yield **26 structurally valid observed annotations**. Those are API
tokens, not 26 source-owned timing recoveries or verified boundaries. No missing
endpoints are invented, and source ownership and both-endpoint acoustic accuracy
are not established. The current report therefore has no correct-boundary rate.

Text availability also does not certify sung readings. A kanji transcript does
not identify the pronunciation actually sung; downloaded lyric agreement is not
ground truth. No reading corrections or new saved timing versions were admitted.
Hydrogen's silence abstention is encouraging. Flash-Lite's hallucination makes
unconditional acceptance unsafe, and Transcribe's empty singing replies need
investigation before treating it as a replacement.

## Latency, memory and quota

The client ran on Apple M2 Pro /16 GiB. Median wall time for completed requests,
including the main silence control where reached, was **6.63 seconds** for plain
Transcribe, **6.74 seconds** for usable word-annotation replies, **3.17 seconds**
for Flash-Lite and **34.95 seconds** for Hydrogen. Backoff is included where it
occurred. These short-crop request measurements cannot predict full-song latency
or be compared directly with historical full-song local alignment time. The
plain-Transcribe continuation and first word-annotation request briefly overlapped;
this was not a controlled latency comparison.

Later collector runs record client maximum RSS; observed process peaks were
approximately **34.4–36.4 MiB**. Earlier main Flash-Lite/Hydrogen runs did not
record RSS. This is neither remote model memory nor a simultaneous process-tree
peak. Server compute and memory are unavailable.

The final timing continuation returned **HTTP 429**, with `Retry-After: 30422`
(about 8 hours 27 minutes). Collection stopped without retrying that quota error.
Its receipt places the earliest indicated retry at **2026-11-17 07:59:59 UTC**;
availability after that time is not guaranteed. No further Google calls ran during that audio pilot.
Three song crops and the main silence control remain unattempted in the timing
arm. A source-selected shifted-audio control has been prepared but not submitted;
unrelated-audio source joins also remain unevaluated. These missing checks prevent
calling the pilot complete or promoting any backend. No full-song expansion ran.

## Offline hybrid follow-up

The maintainer prioritized Google lyric candidates followed by local timing and
independent acoustic checks. This follow-up uses the cached Hydrogen replies and
the exact original float32 Rust crops: **no API, Spotify, Keychain, password,
recording, model download or app-state write is involved**. It tests the hybrid
mechanism without waiting for another free API allocation.

Close both text versions and their converter-owned UTF-8 spans before inference.
Authenticate every cached Google request against the original WAV payload hash,
and authenticate the float32 recording, native crop export and source document.
The existing-text conversion must exactly reproduce Rust's target spans, target
text, romaji, group count and converter signature. A Google transcript becomes a
separate candidate snapshot; its groups never inherit the earlier source's clocks.
Join response line breaks with spaces, preserving the original response privately.

TIFA then aligns each version to the same original mixture samples. The existing
Japanese singing recognizer independently observes the audio without lyric input;
its source-conditioned CTC word decoder checks the two fixed target sequences.
Count endpoint support only for positive TIFA intervals of at least 80 ms,
independent mean probability at least 0.45 and both observed endpoints within
150 ms. Compute the existing phrase-coherence diagnostic separately, keeping
unsupported groups in its denominator. These are model diagnostics, not listening
references or automatic permission to replace text.

| Diagnostic                               | Existing text | Cached Google text |
| ---------------------------------------- | ------------: | -----------------: |
| Source-owned groups in that version      |            66 |                 73 |
| Structurally retained TIFA intervals     |            54 |                 42 |
| Groups with independent endpoint support |            11 |                  8 |
| Cues passing existing phrase coherence   |             2 |                  2 |

Eight candidate texts differ; the two unchanged texts, CROW and たぶん, reproduce
identical target ownership and TIFA intervals. The denominators above are separate:
42/73 is not a count of recovered original groups. In particular, the TEENAGE CITY
RIOT candidate expands four existing groups to 21 candidate groups and retains no
TIFA intervals. It cannot be accepted because it is fluent or more detailed.

The Google candidate for 天天天国地獄国 has two groups with independent endpoint support
and passes phrase coherence, versus no endpoint-supported groups for its existing
text. Its three groups replace a four-group source, so this is a shortlisted
alternative, **not two recovered original groups or verified lyric corrections**.
Kyouran Hey Kids!! shows the opposite direction: its existing text passes phrase
coherence, while the changed Google text does not. たぶん passes in both versions.

The Japanese verifier cannot establish English correctness; unsupported English
and mixed-language cues remain unknown. Google supplied orthographic text, not
an explicit sung-kana transcript, so candidate kana here comes from the existing
converter and does not prove an unusual sung reading. This comparison uses TIFA
on the original mix, not the full shipped Experimental separation/MMS/repair
recipe. It provides no new correct-boundary rate or end-to-end accuracy claim.

On M2 Pro /16 GiB, the final combined TIFA alignment calls took **16.68 seconds**,
excluding asset validation/model initialization. Alternating existing/candidate
calls share caches, so their individual timings are not a fair speed comparison.
Peak process RSS was approximately **706 MiB** for alignment and **563 MiB** for
independent verification. Verification wall time was not recorded. A first verify
attempt exposed a missing vendored phoneme import; after fixing it, the repeated
TIFA pass reproduced all twenty earlier unit arrays exactly. The failed run and
repeat are not additional independent evidence or additional recordings.

The hybrid is technically workable, but this short-crop candidate batch does not
justify wholesale replacement. No candidate was applied to the app. A useful next
trial, when API quota permits, should give the recognizer more song context and
separately request sung kana before checking any disputed readings. Preserve this
small-crop result, finish the negative controls and require evidence before
promoting a recipe. This next trial needs cached audio/API access, not Spotify
credential access.

The research command closes proposals before acoustic observation:

```sh
python3 scripts/hybrid_google_timing.py prepare \
  --pilot /private/tmp/romaji-google-pilot \
  --captures /private/tmp/romaji-google-song-capture \
  --romanizer /path/to/RomajiRomanizer \
  --output /private/tmp/romaji-google-hybrid

.venv-experimental/bin/python scripts/hybrid_google_timing.py align \
  --output /private/tmp/romaji-google-hybrid \
  --tifa-model /path/to/verified-tifa-model

.venv-experimental/bin/python scripts/hybrid_google_timing.py verify \
  --output /private/tmp/romaji-google-hybrid \
  --refinement-model /path/to/writable-private-refinement-cache
```

The final cache contains the existing `singing/model_safetensors.zip`; the helper
verifies its extracted files against pinned hashes. Metal access is required for
the local models. Two offline regression tests cover candidate line handling and
rejection of changed original owner spans, text, readings, group counts or converter
signatures. Recordings, proposals, source snapshots and model observations stay
private; models never select a source spelling by retained coverage alone.

## Provider-first lyrics, timing, then Gemini kana

The next maintainer-directed approach preserves the fetched provider lyrics,
computes local timing with the existing converter, and requests Gemini kana only
afterward. It uses the original provider source from the cached captures, not the
Google-transcribed alternative text. The already measured original-text baseline
remains **54/66 timed groups**; it is reused rather than measured again.

`scripts/gemini_source_kana.py` has prepared **ten text-only requests /66 fixed
word owners**. Each includes the complete fetched lyric context, target line,
stable source-owned word IDs and exact written surfaces. The initial plain arm excludes clock values,
dictionary kana, artist/account metadata and audio. The
[documented JSON response format](https://aistudio.google.com/docs/structured-output)
requires one kana-or-null result per owner. The parser rejects stale request IDs,
missing/duplicate/reordered owners, rewritten text, extra timing/confidence fields
and invalid kana syntax. Matching the JSON schema is not an acoustic correctness
test.

The input manifest, local baseline timing, provider document, prompt bytes and
transport/runner versions are fingerprinted. The provider's saved HTTP 429 receipt
sets a hard earliest-request guard at **2026-11-17 07:59:59 UTC**. An offline test
against the actual prepared manifest confirms that the guard stops execution
before credential loading or network access. A separate all-null fixture retains
all 66 owners and their earlier timing records; **that fixture is not a Gemini
result**. That preparation checkpoint preceded the live comparison below.

Valid replies remain unverified reading proposals. The offline `trials` stage
canonicalizes proposed kana using the same converter signature. It preserves raw
source spans and group counts, removes dictionary pronunciation shadows only from
changed targets, and creates fresh local-alignment proposals for changed cues.
Unchanged/abstained owners retain the earlier version; missing timing stays missing.
The original lyric text is never replaced. Independent acoustic checks and the
normal admission policy remain necessary before applying a correction to the app.

Audio-assisted readings and trimmed excerpts are optional later comparisons. This
first pass does not require them. If used later, keep the clip's original recording
origin; removing internal pauses requires an explicit mapping rather than reusing
shifted clocks. Text-only context cannot determine a singer's unusual pronunciation
with certainty.

Prepare from authenticated local timing results and fetched lyric snapshots:

```sh
python3 scripts/gemini_source_kana.py prepare \
  --hybrid /private/tmp/romaji-google-hybrid-v3 \
  --pilot /private/tmp/romaji-google-pilot \
  --captures /private/tmp/romaji-google-song-capture \
  --quota-receipt /path/to/latest-provider-429-receipt.json \
  --output /private/tmp/romaji-provider-first-kana-v4
```

Supply the most recent quota receipt whenever one exists. A project with no
prior quota rejection can omit it; this pilot has one and its wait remains enforced.
The prepared collection can run when the provider permits requests:

```sh
python3 scripts/gemini_source_kana.py run \
  --output /private/tmp/romaji-provider-first-kana-v4 \
  --env-file /path/to/ignored/.env --free-project-confirmed
```

After valid replies, prepare only the changed cues for local evaluation:

```sh
python3 scripts/gemini_source_kana.py trials \
  --output /private/tmp/romaji-provider-first-kana-v4 \
  --hybrid /private/tmp/romaji-google-hybrid-v3 \
  --romanizer /path/to/RomajiRomanizer \
  --trials-output /private/tmp/romaji-source-kana-timing
```

Run the existing hybrid `align` and `verify` stages against that trial directory.
If there are no accepted changed readings, no local rerun is needed. Twelve offline
tests cover fixed ownership/text, changed-reading realignment, unchanged/null
fallbacks, removal of stale dictionary pronunciation, prompt separation, malformed
readings, manifest integrity, response-cache reuse and quota enforcement before credentials/network.
The app workflow remains unmodified pending demonstrated accuracy gains.

## Simpler model and provisional kana hints (2026-11-17)

The maintainer authorized a lighter model and partial reading hints. Compare
`gemini-3.5-flash-lite` with `gemini-4-hydrogen`, each with plain and hinted
prompts, on the same ten provider-source cases /66 fixed owners. Flash-Lite is
listed with free standard input/output in the provider's
[pricing documentation](https://aistudio.google.com/docs/pricing). The original
Free-tier, billing-disabled project remains unchanged. Collection began after
the saved quota deadline; no new quota rejection occurred in this comparison.

The full original lyrics and exact owner surfaces remain authoritative for
spelling. Hints are explicitly provisional: check and correct them against the
original lyrics and context, or abstain. Select hints before requests using both
existing phrase coherence and independent endpoint support, retaining only valid
kana. This yields **four hints in two cases**, not 66 assumed-correct dictionary
readings. Model support is not listening ground truth. Do not send local clocks.

Freeze model, prompt, evidence and manifests before collection. Collect serially,
interleaving cases/arms, with at most 24 distinct planned requests because eight
cases per model have byte-identical plain/hinted prompts. Reuse exact observations
with hash lineage and revalidate raw replies; reused observations are not new
votes. Preserve failed observations too. The transport permits one bounded
service retry; explicit continuation skips saved service failures after their
wait deadline without resending them. Quota/auth/client failures still stop.
Disable a model after three consecutive service failures.

| Arm                           |   Valid cases | Owners in valid replies | Changed readings | Null readings |
| ----------------------------- | ------------: | ----------------------: | ---------------: | ------------: |
| Flash-Lite, plain             |          8/10 |                      50 |                0 |             4 |
| Flash-Lite, provisional hints |          8/10 |                      50 |                0 |             4 |
| Hydrogen, plain               | 0/3 attempted |                       0 |          Unknown |       Unknown |
| Hydrogen, provisional hints   | 0/2 attempted |                       0 |          Unknown |       Unknown |

Flash-Lite returned matching baseline kana for 46 owners and abstained on four
English words. Both arms failed with HTTP 503 on the other two cases /16 owners;
missing replies cannot count as agreement. Three of the four eligible hints were
in one failed case, leaving only **one hint with usable paired results**.
Hydrogen's three distinct transport/timeouts triggered its stop; its hinted
observations reused identical failures. Unattempted Hydrogen cases remain unknown.
This run measures service availability and dictionary agreement, not sung-reading
accuracy. The canonical local trial stage confirmed zero changed cues in both
Flash-Lite arms, so no fresh alignment was required. The original 54/66 baseline
timings and saved app data remain unchanged.

Early collection versions stopped on service failures while continuation/reuse
was being implemented. One identical failed Hydrogen request was redundantly
submitted in that debugging pass before transport-failure reuse was fixed.
Preserve those receipts and frozen runner versions; do not count that resubmission
as independent evidence or hide it within the final comparison. Existing exact
observations were reused rather than rerunning the full matrix.

Separately freeze **two existing known-reading development fixtures**, without
audio or timing, and submit each to Flash-Lite with and without its known kana as
a provisional hint. These are curated examples from the existing romanizer
regressions, not a held-out evaluation or newly measured recordings. A third
compound-reading fixture was omitted before collection to conserve requests.

| Written target | Known sung reading | Plain reply | Hinted reply |
| -------------- | ------------------ | ----------- | ------------ |
| 地球           | ほし               | ちきゅう    | ほし         |
| 故郷           | まち               | ふるさと    | ふるさと     |

All four replies preserved the fixed source owner. One request completed after
its bounded HTTP 503 retry. Hints preserved one of these two unusual readings,
while the other was normalized incorrectly despite its hint. This is a concrete
reason to protect curated sung readings and independently check proposed changes;
it does not establish a general improvement rate or justify automatic overwrites.
Full lyrics help ordinary contextual readings, but text alone cannot reliably
recover a singer's exceptional pronunciation. No model has been promoted into
the app. Optional audio remains the next way to test disputed readings using
cached recordings, without Spotify/Keychain access or another capture.

For reproducible controlled arms, add `--model gemini-3.5-flash-lite` and,
for the hinted arm, `--reading-hints` to `prepare`. `run --limit 1` bounds each
collection step; `--reuse-output /path/to/plain-arm` reuses only identical request
bytes. `--continue-service-errors` explicitly permits advancing past saved
service failures after their wait; it never retries those failed requests or
skips quota/auth errors. Twelve network-free tests cover these controls, fixed
ownership and changed-reading realignment. Private manifests, lyric-bearing raw
responses, development labels and source snapshots are retained outside Git.

## Supplied karaoke timing and furigana audit (2026-11-17)

The maintainer authorized trying a simpler lookup-first approach after three Luna
research agents examined existing sources and tools. This is a live source-data
availability audit, not another model benchmark or an app integration. Use the
same ten frozen recording IDs and cached provider/source snapshots. No new audio
was recorded, uploaded or measured, no Google calls were made, and no credentials,
Spotify/Keychain access or password prompts were required.

### What was fetched

QQ's public-facing search endpoint returned candidates without login. Search by
song title, inspect artist and duration, and exclude explicit covers/live versions
when an ordinary matching-artist candidate exists. CROW initially needed correcting
an artist guess using its Spotify track page: the recording is UPIKO's カラス.
Refine that query before selecting its lyric candidate. Preserve all search
responses, the selected IDs and metadata corrections privately.

Request `music.musichallSong.PlayLyricInfo/GetPlayLyricInfo` with QRC, romanization
and translation enabled. All ten selected candidates returned successful lyric
responses. Decode privately using the reviewed pure decoding routines from the
existing [karaoke-video-maker implementation](https://github.com/Mihaly-Ma/karaoke-video-maker/blob/main/backend/kvm/lyrics/qq.py).
The prototype uses no new installed dependency or production code. QRC is supplied
character/token timing, not inferred word boundaries. Keep `(start, duration)`
pairs and real gaps; do not interpolate finer clocks. Strip metadata before
counting timed body tokens: kana metadata can itself contain timed entries.

Locate matching UtaTen pages by title/artist and extract the first hiragana lyric
body, preserving each written ruby surface and supplied reading separately.
Ignore its duplicate romaji display body. A direct search-page request returned
an empty body; the pages below were discovered through web search, then fetched
directly. Therefore this proves page/data availability, not a finished automatic
UtaTen discovery API.

| Song               | QQ timed body tokens | QQ kana track | UtaTen ruby pairs |
| ------------------ | -------------------: | ------------- | ----------------: |
| 嘘                 |                  358 | Yes           |                87 |
| CROW / カラス      |                  498 | Yes           |               111 |
| Just Awake         |                  447 | Yes           |                51 |
| 残酷な天使のテーゼ |                  465 | Yes           |                87 |
| Wild Side          |                  374 | Yes           |                35 |
| 天天天国地獄国     |                  765 | Yes           |               191 |
| 狂乱 Hey Kids!!    |                  419 | No            |               153 |
| たぶん             |                  608 | Yes           |               105 |
| TEENAGE CITY RIOT  |                  484 | Yes           |                62 |
| LOST IN PARADISE   |                  583 | Yes           |                34 |

**10/10 candidates contain QRC timing, 9/10 contain a kana track, and 10/10
matching-song UtaTen pages contain furigana.** These are lookup success counts,
not 5,001 verified word timings or a singing-accuracy rate. QQ candidate recording
identity remains unverified: artist/title/duration do not prove the same master,
and several search results offer covers, live versions, remasters or alternate
editions. No timing was transferred to saved app data.

### Readings and mapping checks

Two separate existing known-reading development fixtures were checked as text
lookups, without adding recordings to the frozen ten-song suite:

| Fixture                                                  | Supplied UtaTen ruby | Known fixture reading |
| -------------------------------------------------------- | -------------------- | --------------------- |
| [departure!](https://utaten.com/lyric/yl15120426/), 地球 | ほし                 | ほし                  |
| [SAKURA](https://utaten.com/lyric/jb10604002/), 故郷     | まち                 | まち                  |

Both are explicit written-surface/reading pairs in the fetched page markup. This
resolves both small development examples through supplied data, whereas the
hinted Gemini trial preserved only one. It does not validate every UtaTen reading
or establish a general accuracy rate. The two fixtures were selected because
their readings were already known, not as a held-out benchmark.

After NFKC/case normalization and removing punctuation/whitespace, nine of the
ten original crop texts occur in each candidate source's concatenated full
lyrics. The remaining existing 嘘 source is already romanized, while these
candidates are Japanese. Two crop texts repeat within each candidate song.
Some crops cross provider line boundaries, so a single-line match alone would
incorrectly classify them as missing. Normalized matches are diagnostics only;
they do not authorize fuzzy source joins or timestamp transplantation.

A conservative exact, same-line prototype finds six crop matches whose token
boundaries coincide with all **32 source owners** in those crops, without
interpolation. Repeated occurrences in two of those cases still require recording
identity and occurrence checks; 32 is structurally mappable, not admitted or
verified timing. The associated QQ line starts differ from the existing crop
origins by 299–1,772 ms; another normalized-only line differs by 2,049 ms. These
are differences between candidate clocks, not measured errors or a correction
offset to apply globally.

QQ's kana track is a separate counted stream rather than source-anchored ruby.
A simple CJK-kanji coverage checksum agrees in six of the nine available streams
and differs in three. This does not prove those three streams wrong: digits and
other provider conventions need explicit handling. It does establish that blindly
zipping kana entries onto kanji would be unsafe. UtaTen's explicit ruby pairs are
an easier reading input for an initial implementation. QQ timestamps remain useful
only at the supplied boundaries; zero-duration spacing tokens do not become
positive word intervals.

### Decision

Prioritize supplied source readings and karaoke timing before more inference.
The smallest next implementation is a candidate-source adapter: retrieve matching
QQ data, preserve its own original text/clock provenance, map exact complete
source groups, and use UtaTen's ruby where text ownership is unambiguous. Keep
existing saved/curated readings protected and retain TIFA when timing or recording
identity is missing. No confidence in provider data should be invented.

This audit supports pursuing that adapter instead of expanding general Gemini
transcription/kana orchestration. It does **not** qualify automatic backend
promotion or removal of alignment. Source lookup needs production error handling,
reliable discovery, exact recording/occurrence checks, mapping regressions and
paired acoustic timing checks before app integration. Any unresolved mapping
keeps the existing version; earlier source snapshots and timings remain durable.
The raw responses, HTML, decoded lyrics, small audit scripts, upstream decoder
reference and source/recipe hashes remain private outside Git.

## Collector reuse and offline checks

The collector accepts a frozen audio-only manifest:

```json
{
  "version": 1,
  "cases": [
    {
      "id": "synthetic-crop",
      "path": "crop.wav",
      "sha256": "SHA256_OF_WAV_BYTES",
      "origin_sample": 0
    }
  ]
}
```

Supply mono 16 kHz PCM16 WAV crops no longer than 30 seconds. The output directory
must be private and outside the checkout. Each run is bounded to 40 crops and
two attempts per crop; only temporary service errors have one bounded retry.
Quota errors stop immediately. Resume authenticates the recipe, uploads and
cached case identities, and never resends a saved observation. A failed network
case requires inspecting the private receipt and an explicit continuation trial.

```sh
python3 scripts/transcribe-google-audio.py /private/tmp/pilot/manifest.json \
  --output /private/tmp/pilot/hydrogen \
  --env-file /path/to/ignored/.env \
  --model gemini-4-hydrogen --free-project-confirmed
```

The credential can instead be supplied as runtime `GEMINI_API_KEY`; its value
never belongs in command arguments. `--timestamps` is supported only with
`gemini-3.5-transcribe`. The command does not run local inference, apply edits,
or change the app's backend.

Nine network-free tests cover absent confidence, genuine observed timestamps,
invalid clocks, incomplete/malformed responses, model restrictions, credential
echo redaction, bounded service retry, quota stopping, and resume identity for
both successful and rejected observations. Existing `scripts/check.sh` Python
globs include the collector's formatting/lints and test discovery automatically.
A separate branding-fixture regression prevents inherited hook Git paths from
reinitializing the real checkout or staging temporary files.
