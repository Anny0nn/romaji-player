//! Explicit private acceptance capture; never run by offline hooks.
//! Uses the existing Keychain playback grant. Does not transfer playback or play audio.
//! Writes copyrighted lyrics/audio only to the requested local scratch directory.
//! cargo run --example record_alignment_acceptance -- /private/tmp/romaji-acceptance
//! Following track IDs explicitly select the recordings; there is no default song list.
//! Add --stereo to preserve decoded 44.1 kHz stereo for separation experiments.

use std::io::Write;
use std::path::PathBuf;
use std::sync::{Arc, atomic::AtomicBool};

use librespot_core::{Session, SessionConfig, SpotifyId, SpotifyUri, cache::Cache};
use librespot_metadata::audio::{AudioItem, UniqueFields};
use sha1::{Digest, Sha1};
use spotifast::study::{audio, snapshot::Document};

#[cfg(target_os = "macos")]
fn playback_grant(
    dirs: &spotifast::paths::AppDirs,
) -> anyhow::Result<librespot_core::authentication::Credentials> {
    use keyring_core::api::CredentialStoreApi;
    use sha2::{Digest, Sha256};
    // This explicit diagnostic waits for the OS dialog instead of the app's UI timeout.
    // Read only the active playback item, respect sign-out, and never log its bytes.
    let revoked = || -> anyhow::Result<bool> {
        let path = dirs.state.join("credential-storage/playback.json");
        if !path.is_file() {
            return Ok(false);
        }
        let marker: serde_json::Value = serde_json::from_slice(&std::fs::read(path)?)?;
        anyhow::ensure!(
            marker["version"] == 1,
            "Invalid playback revocation marker."
        );
        marker["revoked"]
            .as_bool()
            .ok_or_else(|| anyhow::anyhow!("Invalid playback marker."))
    };
    anyhow::ensure!(!revoked()?, "Playback was signed out.");
    let profile = std::fs::read_to_string(dirs.state.join("credential-profile"))
        .ok()
        .filter(|value| value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit()))
        .unwrap_or_else(|| {
            format!(
                "{:x}",
                Sha256::digest(dirs.state.to_string_lossy().as_bytes())
            )
        });
    let backend = apple_native_keyring_store::keychain::Store::new()?;
    let bytes = backend
        .build(
            spotifast::shipping::BUNDLE_ID,
            &format!("{profile}:playback"),
            None,
        )?
        .get_secret()?;
    #[derive(serde::Deserialize)]
    struct Record {
        version: u32,
        slot: spotifast::credentials::Slot,
        grant: spotifast::credentials::Grant,
    }
    let record: Record = serde_json::from_slice(&bytes)?;
    anyhow::ensure!(
        record.version == 1 && record.slot == spotifast::credentials::Slot::Playback && !revoked()?,
        "Invalid or signed-out playback record."
    );
    match record.grant {
        spotifast::credentials::Grant::Playback(credentials) => Ok(credentials),
        _ => anyhow::bail!("Sign into playback in RomajiPlayer first."),
    }
}

fn main() -> anyhow::Result<()> {
    let mut args = std::env::args().skip(1);
    let output = PathBuf::from(
        args.next()
            .ok_or_else(|| anyhow::anyhow!("Provide a private scratch directory."))?,
    );
    let mut tracks: Vec<String> = args.collect();
    let stereo = tracks.iter().any(|arg| arg == "--stereo");
    tracks.retain(|arg| arg != "--stereo");
    anyhow::ensure!(!tracks.is_empty(), "Provide explicit Spotify track IDs.");
    for track in &tracks {
        anyhow::ensure!(
            track.len() == 22 && track.bytes().all(|byte| byte.is_ascii_alphanumeric()),
            "Provide Spotify track IDs, not URLs or paths."
        );
        SpotifyId::from_base62(track)?;
    }
    std::fs::create_dir_all(&output)?;
    let dirs = spotifast::paths::AppDirs::discover();
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()?;
    runtime.block_on(async move {
        #[cfg(target_os = "macos")]
        let credentials = {
            let protected_dirs = dirs.clone();
            tokio::task::spawn_blocking(move || playback_grant(&protected_dirs)).await??
        };
        #[cfg(not(target_os = "macos"))]
        let loaded = spotifast::credentials::Store::new(dirs.clone())
            .lease(spotifast::credentials::Slot::Playback)
            .load()
            .await?;
        #[cfg(not(target_os = "macos"))]
        let Some(spotifast::credentials::Grant::Playback(credentials)) = loaded.grant else {
            anyhow::bail!("Sign into playback in RomajiPlayer first.");
        };
        let cache =
            Cache::new::<&std::path::Path>(None, None, None, None)?.with_memory_credentials();
        let session = Session::new(SessionConfig::default(), Some(cache));
        session.connect(credentials, false).await?;
        for track in tracks {
            let folder = output.join(&track);
            std::fs::create_dir_all(&folder)?;
            let document = match Document::load(&dirs.state.join("study"), &track)? {
                Some(document) => document,
                None => {
                    let spotify = tokio::time::timeout(
                        std::time::Duration::from_secs(20),
                        session
                            .spclient()
                            .get_lyrics(&SpotifyId::from_base62(&track)?),
                    )
                    .await
                    .ok()
                    .and_then(Result::ok)
                    .and_then(|bytes| serde_json::from_slice(&bytes).ok())
                    .and_then(|json| spotifast::lyrics::from_spotify(&json))
                    .and_then(|lyrics| lyrics.source_snapshot);
                    let source = if let Some(source) = spotify.filter(|source| {
                        source
                            .occurrences
                            .iter()
                            .any(|line| line.start_ms.is_some())
                    }) {
                        source
                    } else {
                        // Match the app's existing exact-metadata LRCLIB fallback.
                        // Cache only in this private diagnostic directory.
                        let uri = SpotifyUri::from_uri(&format!("spotify:track:{track}"))?;
                        let item = AudioItem::get_file(&session, uri).await?;
                        let UniqueFields::Track { artists, album, .. } = item.unique_fields else {
                            anyhow::bail!("Expected song metadata.");
                        };
                        let query = spotifast::lyrics::Query {
                            artist: artists
                                .first()
                                .ok_or_else(|| anyhow::anyhow!("Missing song artist."))?
                                .name
                                .clone(),
                            title: item.name,
                            album,
                            duration_ms: std::fs::metadata(folder.join("audio.pcm"))
                                .ok()
                                .map_or(item.duration_ms, |metadata| (metadata.len() / 64) as u32),
                        };
                        let cache = folder.join("lyrics-cache");
                        let key = format!(
                            "{:x}.json",
                            Sha1::digest(format!(
                                "{}|{}|{}|{}",
                                query.artist, query.title, query.album, query.duration_ms
                            ))
                        );
                        let existing = dirs.lyrics_cache_dir().join(&key);
                        if existing.is_file() {
                            std::fs::create_dir_all(&cache)?;
                            std::fs::copy(existing, cache.join(key))?;
                        }
                        let source = spotifast::lyrics::fetch(
                            &reqwest::Client::builder()
                                .timeout(std::time::Duration::from_secs(20))
                                .build()?,
                            &cache,
                            &query,
                        )
                        .await?
                        .and_then(|lyrics| lyrics.source_snapshot)
                        .ok_or_else(|| {
                            anyhow::anyhow!("This recording has no matching lyric snapshot.")
                        })?;
                        println!("{track}: using exact-metadata LRCLIB fallback.");
                        source
                    };
                    Document::new(&track, source)?
                }
            };
            document.validate()?;
            std::fs::write(folder.join("document.json"), serde_json::to_vec(&document)?)?;
            if !folder.join("audio.pcm").is_file()
                || (stereo && !folder.join("stereo.pcm").is_file())
            {
                let (audio, stereo_samples) = if stereo {
                    let (audio, samples) = audio::prepare_stereo(
                        session.clone(),
                        &track,
                        Arc::new(AtomicBool::new(false)),
                        Arc::new(|_| {}),
                    )
                    .await?;
                    (audio, Some(samples))
                } else {
                    (
                        audio::prepare(
                            session.clone(),
                            &track,
                            Arc::new(AtomicBool::new(false)),
                            Arc::new(|_| {}),
                        )
                        .await?,
                        None,
                    )
                };
                anyhow::ensure!(
                    audio.origin_ms == 0,
                    "Acceptance PCM must begin at recording zero."
                );
                let mut file =
                    std::io::BufWriter::new(std::fs::File::create(folder.join("audio.pcm"))?);
                for sample in &audio.samples {
                    file.write_all(&sample.to_le_bytes())?;
                }
                file.flush()?;
                if let Some(samples) = stereo_samples {
                    let mut file =
                        std::io::BufWriter::new(std::fs::File::create(folder.join("stereo.pcm"))?);
                    for sample in samples {
                        file.write_all(&sample.to_le_bytes())?;
                    }
                    file.flush()?;
                }
                println!(
                    "{track}: captured {} ms silently.",
                    audio.samples.len() / 16
                );
            }
        }
        anyhow::Ok(())
    })
}
