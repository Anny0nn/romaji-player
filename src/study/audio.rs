//! Silent, one-track decoding through the existing authenticated librespot session.
//! Packet timestamps are paired by producer order, never callback arrival time.
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};
use std::time::Duration;

use anyhow::{Result, bail};
use librespot_core::{SpotifyUri, session::Session};
use librespot_metadata::audio::AudioItem;
use librespot_playback::{
    NUM_CHANNELS, SAMPLE_RATE,
    audio_backend::{Sink, SinkError, SinkResult},
    config::{Bitrate, PlayerConfig},
    convert::Converter,
    decoder::AudioPacket,
    mixer::NoOpVolume,
    player::{Player, PlayerEvent},
};

const MAX_SECONDS: usize = 600;
const MAX_PACKETS: usize = 60_000;

#[derive(Default)]
struct Captured {
    mono: Vec<f32>,
    packets: Vec<usize>,
    stereo: Option<Vec<f32>>,
}
struct CaptureSink {
    captured: Arc<Mutex<Captured>>,
    cancelled: Arc<AtomicBool>,
}
impl Sink for CaptureSink {
    fn write(&mut self, packet: AudioPacket, _: &mut Converter) -> SinkResult<()> {
        let AudioPacket::Samples(samples) = packet else {
            return Err(SinkError::OnWrite("Unsupported analysis audio".into()));
        };
        let mut captured = self.captured.lock().unwrap_or_else(|p| p.into_inner());
        let count = samples.len() / NUM_CHANNELS as usize;
        if self.cancelled.load(Ordering::Acquire)
            || samples.len() % NUM_CHANNELS as usize != 0
            || captured.mono.len() + count > SAMPLE_RATE as usize * MAX_SECONDS
            || captured.packets.len() == MAX_PACKETS
            || samples.iter().any(|sample| !sample.is_finite())
        {
            return Err(SinkError::OnWrite(
                "Analysis cancelled or audio limit exceeded".into(),
            ));
        }
        captured.packets.push(count);
        if let Some(stereo) = &mut captured.stereo {
            stereo.extend(samples.iter().map(|sample| *sample as f32));
        }
        captured.mono.extend(
            samples
                .as_chunks::<{ NUM_CHANNELS as usize }>()
                .0
                .iter()
                .map(|frame| (frame.iter().sum::<f64>() / f64::from(NUM_CHANNELS)) as f32),
        );
        Ok(())
    }
}

/// Validate the independent decoder's complete sequence, including every packet origin.
fn validate_capture(captured: &Captured, positions: &[u32], duration: u32) -> Result<u32> {
    let surplus = positions.len().saturating_sub(captured.packets.len());
    // Vorbis emits empty priming packets: Player sends their PTS but suppresses
    // their sink write. Only discard a bounded prefix at the identical origin;
    // validate every remaining packet and the complete sample duration below.
    if positions.is_empty()
        || captured.packets.is_empty()
        || positions.len() < captured.packets.len()
        || surplus > 4
        || positions[..=surplus]
            .windows(2)
            .any(|pair| pair[0] != pair[1])
    {
        bail!("The analysis decoder did not provide a timestamp for every audio packet.");
    }
    let positions = &positions[surplus..];
    let origin = positions[0];
    if origin > 50 || captured.mono.is_empty() {
        bail!("Analysis audio does not start at the beginning of the recording.");
    }
    let mut frames = 0u64;
    for (position, count) in positions.iter().zip(&captured.packets) {
        let expected = u64::from(origin) + frames * 1000 / u64::from(SAMPLE_RATE);
        if expected.abs_diff(u64::from(*position)) > 2 {
            bail!("The analysis audio has a gap or discontinuity. Retry timing this song.");
        }
        frames += *count as u64;
    }
    let end = u64::from(origin) + frames * 1000 / u64::from(SAMPLE_RATE);
    if end.abs_diff(u64::from(duration)) > 200
        || frames != captured.mono.len() as u64
        || captured
            .stereo
            .as_ref()
            .is_some_and(|samples| samples.len() != captured.mono.len() * NUM_CHANNELS as usize)
    {
        bail!("Analysis audio is incomplete or belongs to a different recording.");
    }
    Ok(origin)
}

pub struct Audio {
    pub origin_ms: u32,
    pub samples: Vec<f32>,
}

fn validate_recording(
    requested: &SpotifyUri,
    actual: &SpotifyUri,
    alternatives: &[SpotifyUri],
) -> Result<()> {
    if actual != requested && !alternatives.contains(actual) {
        bail!("Analysis recording changed: Spotify returned an unlisted alternative ({actual}).");
    }
    Ok(())
}

pub async fn prepare(
    session: Session,
    track: &str,
    cancelled: Arc<AtomicBool>,
    progress: Arc<dyn Fn(String) + Send + Sync>,
) -> Result<Audio> {
    Ok(prepare_inner(session, track, cancelled, progress, false)
        .await?
        .0)
}

/// Preserve original stereo for experimental vocal separation, alongside the
/// same validated 16 kHz mono recording and packet-derived origin.
pub async fn prepare_stereo(
    session: Session,
    track: &str,
    cancelled: Arc<AtomicBool>,
    progress: Arc<dyn Fn(String) + Send + Sync>,
) -> Result<(Audio, Vec<f32>)> {
    let (audio, stereo) = prepare_inner(session, track, cancelled, progress, true).await?;
    Ok((
        audio,
        stereo.ok_or_else(|| anyhow::anyhow!("Missing stereo capture."))?,
    ))
}

async fn prepare_inner(
    session: Session,
    track: &str,
    cancelled: Arc<AtomicBool>,
    progress: Arc<dyn Fn(String) + Send + Sync>,
    stereo: bool,
) -> Result<(Audio, Option<Vec<f32>>)> {
    if !super::snapshot::valid_track(track) {
        bail!("Invalid analysis track.");
    }
    let uri = SpotifyUri::from_uri(&format!("spotify:track:{track}"))?;
    // The pinned player can load a Spotify-advertised alternative when the
    // requested item has no audio files. Its packet events still use `uri`.
    let requested = {
        let metadata = AudioItem::get_file(&session, uri.clone());
        tokio::pin!(metadata);
        tokio::time::timeout(Duration::from_secs(20), async {
            loop {
                if cancelled.load(Ordering::Acquire) {
                    bail!("Automatic timing cancelled.");
                }
                tokio::select! {
                    result = &mut metadata => return Ok::<_, anyhow::Error>(result?),
                    _ = tokio::time::sleep(Duration::from_millis(100)) => {},
                }
            }
        })
        .await
        .map_err(|_| anyhow::anyhow!("Spotify metadata timed out. Retry this song."))??
    };
    let alternatives = if requested.files.is_empty() {
        requested
            .alternatives
            .map_or_else(Vec::new, |tracks| tracks.0)
    } else {
        Vec::new()
    };
    let captured = Arc::new(Mutex::new(Captured {
        stereo: stereo.then(Vec::new),
        ..Captured::default()
    }));
    let sink_capture = captured.clone();
    let sink_cancel = cancelled.clone();
    let player = Player::new(
        PlayerConfig {
            bitrate: Bitrate::Bitrate160,
            gapless: false,
            normalisation: false,
            // The pinned decoder emits this event before each non-passthrough packet.
            // Pair its PTS with the sink's packet sequence only after EOS.
            position_update_interval: Some(Duration::ZERO),
            ..PlayerConfig::default()
        },
        session,
        Box::new(NoOpVolume),
        move || {
            Box::new(CaptureSink {
                captured: sink_capture,
                cancelled: sink_cancel,
            })
        },
    );
    let mut events = player.get_player_event_channel();
    player.load(uri.clone(), true, 0);
    let result = tokio::time::timeout(Duration::from_secs(180), async {
        let mut positions = Vec::new();
        let mut duration = None;
        let mut last_progress = 0;
        loop {
            if cancelled.load(Ordering::Acquire) { bail!("Automatic timing cancelled."); }
            tokio::select! {
                _ = tokio::time::sleep(Duration::from_millis(100)) => {},
                event = events.recv() => match event {
                    Some(PlayerEvent::TrackChanged { audio_item }) => {
                        if duration.is_some() { bail!("Analysis recording changed during decoding."); }
                        validate_recording(&uri, &audio_item.track_id, &alternatives)?;
                        duration = Some(audio_item.duration_ms);
                        if audio_item.duration_ms as usize > MAX_SECONDS * 1000 { bail!("This recording exceeds the ten-minute analysis limit."); }
                    }
                    Some(PlayerEvent::PositionChanged { track_id, position_ms, .. }) if track_id == uri => {
                        if positions.len() == MAX_PACKETS { bail!("Too many analysis packets."); }
                        positions.push(position_ms);
                        let percent = duration.map_or(0, |duration| position_ms.saturating_mul(100) / duration.max(1));
                        if percent / 5 > last_progress / 5 { progress(format!("Preparing song audio · {}%", percent.min(100))); last_progress = percent; }
                    }
                    Some(PlayerEvent::EndOfTrack { track_id, .. }) if track_id == uri => break,
                    Some(PlayerEvent::Unavailable { .. } | PlayerEvent::AudioKeyUnavailable { .. }) | None => bail!("Spotify could not prepare this song's audio. Retry after playback sign-in."),
                    _ => {},
                }
            }
        }
        let captured = std::mem::take(&mut *captured.lock().unwrap_or_else(|p| p.into_inner()));
        let origin_ms = validate_capture(&captured, &positions, duration.ok_or_else(|| anyhow::anyhow!("Missing recording duration."))?)?;
        let samples = rodio::source::UniformSourceIterator::new(
            rodio::buffer::SamplesBuffer::new(1, SAMPLE_RATE, captured.mono), 1, 16_000,
        ).collect();
        Ok((Audio { origin_ms, samples }, captured.stereo))
    }).await;
    player.stop();
    // Dropping Player joins its thread; keep that join off the interface/runtime thread.
    tokio::task::spawn_blocking(move || drop(player));
    result.map_err(|_| anyhow::anyhow!("Audio preparation timed out. Retry this song."))?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn spotify_advertised_alternative_keeps_requested_packet_identity() {
        let uri = |id: &str| SpotifyUri::from_uri(&format!("spotify:track:{id}")).unwrap();
        let requested = uri("1Gqpa08T7eBAvPQj9O9L2Q");
        let alternative = uri("15St0qWPnH4xKflV39vk28");
        let foreign = uri("1lTfD2M6UpJRWi3YLb8qb5");
        assert!(validate_recording(&requested, &requested, &[]).is_ok());
        assert!(
            validate_recording(&requested, &alternative, std::slice::from_ref(&alternative),)
                .is_ok()
        );
        assert!(validate_recording(&requested, &alternative, &[]).is_err());
        assert!(
            validate_recording(&requested, &foreign, std::slice::from_ref(&alternative),).is_err()
        );
    }
    #[test]
    fn packet_pts_validate_origin_and_reject_gaps_without_wall_clock_guessing() {
        let captured = Captured {
            mono: vec![0.1; 4410],
            packets: vec![2205, 2205],
            stereo: None,
        };
        assert_eq!(validate_capture(&captured, &[0, 50], 100).unwrap(), 0);
        assert_eq!(validate_capture(&captured, &[10, 60], 110).unwrap(), 10);
        assert!(validate_capture(&captured, &[0, 90], 100).is_err());
        assert!(validate_capture(&captured, &[0], 100).is_err());
        assert!(validate_capture(&captured, &[0, 50], 1000).is_err());
        assert!(validate_capture(&captured, &[100, 150], 200).is_err());
    }

    #[test]
    fn diagnostic_stereo_preserves_channels_and_uses_the_same_packet_ledger() {
        let captured = Arc::new(Mutex::new(Captured {
            stereo: Some(Vec::new()),
            ..Captured::default()
        }));
        let mut sink = CaptureSink {
            captured: captured.clone(),
            cancelled: Arc::new(AtomicBool::new(false)),
        };
        let mut converter = Converter::new(None);
        sink.write(
            AudioPacket::Samples(vec![0.5, -0.25, 0.25, -0.5]),
            &mut converter,
        )
        .unwrap();
        let mut captured = captured.lock().unwrap();
        assert_eq!(captured.mono, vec![0.125, -0.125]);
        assert_eq!(
            captured.stereo.as_ref().unwrap(),
            &vec![0.5, -0.25, 0.25, -0.5]
        );
        assert_eq!(validate_capture(&captured, &[0], 0).unwrap(), 0);
        captured.stereo.as_mut().unwrap().pop();
        assert!(validate_capture(&captured, &[0], 0).is_err());
    }

    #[test]
    fn pinned_vorbis_decoder_produces_an_exact_sink_packet_ledger() {
        use librespot_playback::decoder::{AudioDecoder, SymphoniaDecoder};
        let bytes = include_bytes!("../../aligner/synthetic-tone.ogg").to_vec();
        let mut decoder =
            SymphoniaDecoder::new(std::io::Cursor::new(bytes), Default::default()).unwrap();
        decoder.seek(0).unwrap();
        let captured = Arc::new(Mutex::new(Captured::default()));
        let mut sink = CaptureSink {
            captured: captured.clone(),
            cancelled: Arc::new(AtomicBool::new(false)),
        };
        let mut converter = Converter::new(None);
        let mut positions = Vec::new();
        while let Some((position, packet)) = decoder.next_packet().unwrap() {
            positions.push(position.position_ms);
            if !packet.is_empty() {
                sink.write(packet, &mut converter).unwrap();
            }
        }
        let captured = captured.lock().unwrap();
        assert!(
            positions.len() > captured.packets.len(),
            "Fixture must cover empty codec priming packets"
        );
        let origin = validate_capture(&captured, &positions, 300).unwrap_or_else(|error| {
            panic!("{error}; PTS={positions:?}; frames={:?}", captured.packets)
        });
        assert_eq!(origin, 0);
    }
}
