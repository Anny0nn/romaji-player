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
**Experimental** also tries vocal isolation and independent MMS phonetic evidence.
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
