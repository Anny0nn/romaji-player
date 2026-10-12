# Study view and saved song data

The study view follows the internal playback clock. Lyrics can display romaji,
hiragana above romaji, or hiragana alone; the selected mode persists after reopening.
Line timing remains available when individual word timing is missing. Timed words use
a distinct marker without changing font metrics or wrapping.

## Source identity and readings

Rust retains immutable provider/import snapshots. Occurrences have recording-specific
line timestamps; Japanese text and UTF-8 source spans identify reading corrections and
saved word timing. Multi-timestamp LRC lines expand into separate occurrences. Reading
corrections apply to identical repeated text within the song, while each occurrence's
timing stays independent.

The Python romanizer returns normalization mappings, contextual hiragana/romaji and
display spans tied to original Japanese text. Corrections are source-span edits; a
correction containing spaces remains one highlighted group. Reconversion preserves
original-text anchors and flags ambiguous reattachment rather than silently moving taps
or timings onto different text. Pinned snapshots protect edits from provider refreshes.

## Automatic alignment

**TIFA** runs the original local forced aligner against the current source snapshot.
**Experimental** first checks the sung readings, then times the resulting version.
It compares bounded dictionary alternatives with two MMS vocal views, rejects confident
contradictions using a separate singing phoneme recognizer, and can propose missing
readings from full-song blind Whisper transcription. Supported repairs store canonical
hiragana and derive romaji from it; all three display modes share those same source
anchors and newly aligned timing. The first recipe also supports bounded kana-only
lyric substitutions corroborated by vocal and original-mix transcriptions. It withholds
ambiguous changes and preserves explicit user corrections and earlier source versions.

Rust sends the frozen source/edit revision, delay, recording/model identities and protected
spans. Python returns provisional patches and fresh alignment; Rust validates the patches,
reconverts them and verifies exact timing targets before saving a complete result. No
partially corrected version is applied. Completed results cannot overwrite a later edit,
and reopening restores both scripts and timing without running models again.

Models run sequentially. TIFA downloads about 151 MB; Experimental downloads about
5.3 GB of additional pinned weights once, including Whisper large-v3 and the singing
phoneme recognizer. The standalone bundle contains the inference runtimes. A package
check launches the bundled romanizer from Experimental with no developer environment.

See [reading evaluation](study-reading-evaluation.md) for measured limits.

Candidate repairs must pass source identity, interval bounds and acoustic consistency
checks. Existing baseline intervals are retained unless a tested repair rule authorizes
a replacement. All results record their engine/provenance and remain selectable as
saved versions for that song.

Missing intervals are not interpolated. A coverage count means retained model intervals,
not proven audible accuracy. Listen to sustained notes, fast passages and verse changes
when evaluating a new model or policy.

## Local files

The macOS bundle identity is `io.github.Anny0nn.RomajiPlayer`. App directories and
Keychain namespaces retain that identity across builds. Study data and downloaded
models remain in the user's application data, independently of the source checkout.
Moving or recloning the repository does not move or clear saved song timings.

The build uses local `.env` settings for public Spotify client configuration; account
grants use protected credential storage. Model files download separately and are
verified against pinned manifests. Neither credentials nor audio/lyric caches are part
of the public git history.
