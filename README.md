# RomajiPlayer

A free, open-source Japanese sing-along player for Apple Silicon Macs, built on
[Spotifast](https://github.com/crmne/spotifast). Play Spotify music inside the app and
follow large lyrics with a marker on the word being sung. Romaji spells the Japanese
pronunciation with Latin letters; showing hiragana above it helps you learn both.

- Large lyrics with the current line and timed word highlighted.
- Separate **TIFA** and **Experimental** buttons for local automatic word alignment.
- Saved timings and lyric versions per song, preserved across restarts.
- Five lyric views: romaji, hiragana with romaji, hiragana, katakana and original Japanese.
- Experimental sung-reading corrections and missing word timings checked against the audio.
- Compact **Options** controls for import, delay and saved versions.

This is an early study build. Automatic alignment and reading repair can make mistakes;
missing intervals stay unmarked. There is no manual word-timing step.

## Use the app

1. Open `RomajiPlayer.app` and sign in to Spotify. Playback uses your Premium account
   inside the app. If another device is active, choose **Play in this app**.
2. Play a Japanese song from search or your library. Open **Lyrics** using the player
   bar button, or press **L**. You can also paste a Spotify track link under **Options**
   and choose **Play**.
3. Select **Romaji**, **Hiragana + romaji**, **Hiragana**, **Katakana**, or **Japanese**.
   Japanese keeps the original kanji and kana. All views share the saved word timings;
   switching views needs no model run. This preference persists across restarts.
   The expand button gives the lyrics more space.
4. Supplied line timing works immediately. To add word highlighting, choose one of the
   two timing buttons below. Wait for the saved-result message, then sing along.

| Action                        | What it does                                                                                                             | Model download on first use |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------: |
| **Time words · TIFA**         | Times the currently selected lyrics using the original TIFA aligner.                                                     |                About 151 MB |
| **Time words · Experimental** | Separates vocals, checks sung readings and lyric corrections, then times the version and tries to recover missing words. |    About 5.3 GB beyond TIFA |

Both actions prepare the selected recording for analysis without microphone recording.
Models run locally and sequentially; the first run also needs internet for model downloads.
Experimental takes several minutes per song on an M2 Pro with 16 GB unified memory.
Its additional corrections are conservative: uncertain words keep their existing reading.
Run **TIFA** for the simpler timing pass, or **Experimental** when the displayed reading
differs from the singing or word highlighting has gaps. A word-count increase is useful coverage evidence, not proof
that the new intervals or readings are correct.

Timings and corrected versions are saved per song. Once completion is reported, you can
close and reopen the app without running the models again. Use **Cancel timing** to stop
an in-progress job; the previous usable version stays available.

Under **Options**:

- **Saved lyric versions** → **Preview** → **Use these lyrics** restores an earlier
  source or timing result. Experimental keeps the earlier versions.
- **Sung corrections** shows the source word and its accepted hiragana/romaji reading.
- **Delay** shifts lyric highlighting by 250 ms at a time. A positive delay moves it
  later. This is a whole-song adjustment, not word timing.
- **Import lyrics…** accepts UTF-8 `.lrc` or `.txt`. Automatic timing needs line-synced
  lyrics; an LRC file supplies those cues. **Refresh** offers newly downloaded lyrics
  while preserving saved versions and corrections.
- **Original Japanese** lets you inspect the downloaded text. **Follow** resumes
  automatic scrolling after you scroll away from the current line.

## Build on macOS

There is no public binary release for this study build yet. Build it locally on Apple
Silicon with macOS 15 or later. The tested minimum is an M2 Pro with 16 GB unified memory.
Use Rust 1.98.1 (`rust-toolchain.toml` pins it), Python 3.14, Node.js/npm, CMake and Xcode
Command Line Tools. Allow disk space for the Python environments, standalone runtimes,
build output and optional model cache, in addition to the model download sizes above.

### Spotify setup

Create your own application in the [Spotify developer dashboard](https://developer.spotify.com/dashboard).
Copy `.env.example` to `.env`, set `SPOTIFY_CLIENT_ID`, and register this exact redirect URI:

```text
http://127.0.0.1:8989/login
```

Keep the callback unchanged; Spotify requires an explicit loopback IP and disallows
`localhost`. This desktop build uses PKCE, so it needs no client secret, Spotify cookie
or token in `.env`. See Spotify's [redirect rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)
and [PKCE instructions](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow).

In Development Mode, the app owner needs Premium and at most five users can authenticate.
Add each account in the dashboard's **Users Management** allowlist; each account streaming
music also needs Premium. Your build uses your own registration, and a shared configured
build uses that registration's allowlist. See [Spotify quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).
New registrations have restricted Web API access, so some inherited browsing features
may be unavailable; account-specific failures can differ from a working playback login.

### Build and launch

```sh
git clone https://github.com/Anny0nn/romaji-player.git
cd romaji-player
cp .env.example .env
# Edit .env before building.
python3.14 -m venv .venv
.venv/bin/python -m pip install -r romanizer/requirements.lock
python3.14 -m venv .venv-tifa
.venv-tifa/bin/python -m pip install -r tifa/requirements.lock
python3.14 -m venv .venv-experimental
.venv-experimental/bin/python -m pip install --no-deps -r refinement/requirements.lock
python3 scripts/fetch-aligner-source.py
bash scripts/package-romanizer.sh
bash scripts/package-tifa.sh
bash scripts/package-experimental.sh
bash scripts/dev.sh
```

The development command runs the configured native app. After changing a Python helper,
re-run its `package-*.sh` command; the app uses the packaged helpers.

For a standalone app and ZIP:

```sh
bash scripts/package.sh
python3 scripts/check-helper-package.py
python3 scripts/check-app-package.py
open dist/RomajiPlayer.app
```

Output is `dist/RomajiPlayer.app` and `dist/RomajiPlayer.zip`. Recipients need no Python,
Rust or development tools, but need their own Premium login and access to the configured
Spotify app. Each Mac downloads its own models and stores its own lyrics/timings. Local
builds are ad-hoc signed; macOS may require approval to open them or access the saved
Keychain login again after an update. A notarized public release is separate work.

## Models and local data

Downloads are pinned and hash-verified. Lyrics are tried from Spotify, with LRCLIB as a
fallback; provider text is a candidate and can have the wrong recording or reading.
A dictionary can choose 闇夜 as `an'ya` while the singer uses `yamiyo`. Experimental
can save the supported `やみよ` / `yamiyo` reading without replacing the kanji.
Experimental combines Cutlet/UniDic candidates, Demucs and Kim vocals, MMS acoustic
checks, RomajiASR singing phonemes and blind full-song Whisper large-v3 transcription.
It can repair supported readings and bounded kana text substitutions, while retaining
prior versions. It does not freely rewrite ambiguous kanji from audio.
Experimental also retries unsupported same-vowel small-kana spellings such as `あぁ`.
Its missing-word pass checks fresh TIFA intervals against the singing model and tries
Japanese pronunciation patterns for English words. It preserves existing timings and
displayed readings, with no additional model download. Broader context and repeat
approaches are still measured offline.

The converter keeps one selected reading tied to each original Japanese word group.
Hiragana, katakana and romaji use that reading; the original Japanese view highlights
the same source span. Experimental can also check a dictionary's spoken pronunciation,
such as `とーきょー` for written `とうきょう`, to recover missing timings. It keeps the
written lyric and protects saved sung-reading corrections. Changing display script alone
does not fix a wrong reading, and unknown or ambiguous source groups stay unmarked.

Saved study data lives under
`~/Library/Application Support/io.github.Anny0nn.RomajiPlayer/study/`; downloaded weights
are in the adjacent `models/` directory. Back up `study/` to retain your per-song versions.
Updating or moving the app preserves this data. Removing model caches requires another
download, but does not remove the saved study files. Account grants are held separately
in macOS Keychain. Audio preparation and model inference are local; Spotify, lyric
lookups and first-use model downloads still need network access.

On fourteen recorded songs, Experimental retains **3,509/4,160 words (84.4%)**, compared
with TIFA's **3,121/4,160 (75.0%)**. The spoken-pronunciation fallback adds two timings
in 今世大革命 (197 to 199/246), preserving every existing interval, all fifteen reading
corrections and the earlier recovery stage's 72 additions. Tabi no Tochuu stays at
153/153. All 28 timing results passed reopening, reconversion and earlier-version
restoration. Median cached-weight processing time was 168 seconds for Experimental
and 6.5 seconds for TIFA on M2 Pro /16 GB.
These are coverage and persistence results, not a listening-accuracy score; difficult
songs still have substantial gaps. See the [representation evaluation](docs/study-representation-evaluation.md),
[completeness evaluation](docs/study-completeness-evaluation.md),
[earlier reading evaluation](docs/study-reading-evaluation.md) and [data/protocol design](docs/study.md).
The newer [accuracy experiments](docs/study-accuracy-evaluation.md) separate retained-word
counts from human phone-boundary tests and document rejected approaches. They do not
establish perfect lyric recognition or word timing on unfamiliar songs.
The expanded [61-recording catalog](docs/study-song-catalog.md) records the initial
measurements and a frozen ten-song trial set: seven lowest-coverage songs and three
highest-coverage songs below 100%. Fully covered songs stay in regression fixtures.
The [audio-first reading pilot](docs/study-audio-first-evaluation.md) tests recognizing
the sung pronunciation before choosing romaji. Its fallback recovers 19 additional
controlled reading faults with fresh TIFA timing, but also adds two wrong repairs and
has incomplete natural-song validation. These research tools run offline; this pilot
does not change the app's Experimental button.

## Troubleshooting

- **Sign-in or playback denied:** check Premium, the configured Client ID, exact callback
  and allowlist. Playback and Web API authorization are separate integrations inherited
  from Spotifast; successful authorization alone does not confirm in-app audio.
- **Only a line lights up:** the source has no word timing. Run a timing action; withheld
  words remain unmarked when the model cannot validate their intervals.
- **Words do not match the singing:** try Experimental and inspect **Sung corrections**.
  If the provider supplied a different verse/recording, choose the matching lyric candidate
  or import an LRC. This recipe protects saved correction spans, including prior automatic
  corrections; restore an earlier source version to re-evaluate a previously corrected
  word. Unsupported changes keep their current reading.
- **All lyrics consistently lead or lag:** adjust **Delay**. If individual words drift,
  a whole-song delay will not repair their alignment; try the other timing result.
- **A timing job fails or you change versions during it:** the prior version is retained.
  Wait for conversion to finish, then retry the selected version. Keep the app open until
  the job reports completion if you want its result saved.

## Licenses and service limits

Model licenses differ from the MIT application source. TIFA and MMS weights have
noncommercial terms. See [TIFA provenance](tifa/UPSTREAM.md) and the
[experimental model notices](refinement/MODEL-NOTICES.txt); review the original Demucs
weight terms before using that optional model. Weights, recordings, downloaded lyrics,
credentials and personal development configuration are excluded from git.

This is an unofficial Spotify integration. Spotify's
[Compliance Tips](https://developer.spotify.com/compliance-tips) explicitly disallow
synchronizing Spotify recordings with lyrics. Working login or Development Mode access
does not establish approval for this use. Model and service terms apply independently
of the free MIT application source.

## Development

Use feature branches and pull requests targeting this fork. Enable the local hooks with
`git config core.hooksPath .githooks`; run `bash scripts/check.sh` before pushing.
The offline suite does not sign in, download models or contact music/lyrics services.
See [the implementation plan](docs/plans/japanese-study.md) and
[contributing instructions](CONTRIBUTING.md).

## Credits and license

Spotifast is by Carmine Paolino and contributors. RomajiPlayer retains its native
Rust/egui interface, librespot playback and MIT attribution. Application code is
[MIT licensed](LICENSE); bundled dependencies and separately downloaded models retain
their own notices and terms. Upstream's website sources remain in `docs/` for provenance;
they describe Spotifast, while the study build is documented here.
