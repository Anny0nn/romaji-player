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
availability after that time is not guaranteed. No further Google calls ran.
Three song crops and the main silence control remain unattempted in the timing
arm. A source-selected shifted-audio control has been prepared but not submitted;
unrelated-audio source joins also remain unevaluated. These missing checks prevent
calling the pilot complete or promoting any backend. No full-song expansion ran.

## Reuse and offline checks

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
