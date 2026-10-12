//! One-button local alignment. Durable results are separate from disposable caches.
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};
use std::time::{Duration, Instant};

use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::conversion::{Response, span};
use super::snapshot::{Snapshot, valid_track};
use super::timing::{Fragment, Interval};

pub const MODEL_SHA: &str = "6da6832cd2cb981aae1ccc2d9330f8f7c085ce7977d1eb13bff63531d038a88b";
const MODEL_SIZE: u64 = 150_789_526;
const MODEL_URL: &str = "https://github.com/openvpi/TIFA/releases/download/v1.0.0/TIFA-1.0-ST.zip";
const ENGINE: &str = "TIFA/32a0a13-source-word-v2";
const EXPERIMENTAL_ENGINE: &str = "TIFA+Demucs+Kim+MMS+RomajiASR+Whisper/sung-reading-v1";
const ASSETS: &str = include_str!("../../refinement/refinement-model-files.json");
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Method {
    Tifa,
    Experimental,
}
impl Method {
    fn engine(self) -> &'static str {
        match self {
            Self::Tifa => ENGINE,
            Self::Experimental => EXPERIMENTAL_ENGINE,
        }
    }
    pub fn label(self) -> &'static str {
        match self {
            Self::Tifa => "TIFA",
            Self::Experimental => "Experimental",
        }
    }
    fn fingerprint(self) -> String {
        match self {
            Self::Tifa => MODEL_SHA.into(),
            Self::Experimental => format!("{:x}", Sha256::digest(ASSETS.as_bytes())),
        }
    }
}
const MAX_OUTPUT: u64 = 32 * 1024 * 1024;

#[derive(Clone)]
pub struct Job {
    pub method: Method,
    pub track: String,
    pub snapshot: String,
    pub revision: u64,
    pub delay_ms: i64,
    pub cancel: Arc<AtomicBool>,
    pub status: Arc<Mutex<Status>>,
}
#[derive(Clone)]
pub enum Status {
    Running(String),
    Complete(Box<Generated>),
    Failed(String),
}
impl Job {
    pub fn update(&self, message: String) {
        *self.status.lock().unwrap_or_else(|p| p.into_inner()) = Status::Running(message);
    }
}
pub struct Request {
    pub protected: Vec<super::reading::ProtectedSpan>,
    pub job: Job,
    pub source: Snapshot,
    pub converted: Vec<Response>,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Generated {
    pub track: String,
    pub base_snapshot: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub base_revision: Option<u64>,
    pub model_sha256: String,
    pub engine: String,
    pub audio_sha256: String,
    pub delay_ms: i64,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub repaired_readings: usize,
    pub timed_words: usize,
    pub total_words: usize,
    pub snapshot: Snapshot,
}
fn is_zero(value: &usize) -> bool {
    *value == 0
}
impl Generated {
    fn validate(&self) -> Result<()> {
        self.snapshot.validate()?;
        let hash =
            |value: &str| value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit());
        if !valid_track(&self.track)
            || !hash(&self.base_snapshot)
            || !hash(&self.model_sha256)
            || !hash(&self.audio_sha256)
            || self.engine.is_empty()
            || self.timed_words == 0
            || self.timed_words > self.total_words
            || self.repaired_readings > 256
        {
            bail!("Invalid saved automatic timing identity.");
        }
        if self.repaired_readings > 0
            && !self.snapshot.source.derivation.as_ref().is_some_and(|d| {
                d.parent_snapshot == self.base_snapshot
                    && Some(d.base_revision) == self.base_revision
                    && d.audio_sha256 == self.audio_sha256
                    && d.model_sha256 == self.model_sha256
                    && d.recipe == super::reading::RECIPE
                    && self.repaired_readings <= d.readings.len() + d.text_repairs.len()
            })
        {
            bail!("Reading result does not match its frozen evidence.");
        }
        Ok(())
    }
    pub fn apply(&self, document: &mut super::snapshot::Document) -> Result<bool> {
        self.validate()?;
        if document.track_id != self.track
            || document.current().snapshot.id != self.base_snapshot
            || document.delay_ms != self.delay_ms
            || self
                .base_revision
                .is_some_and(|revision| revision != document.revision)
        {
            return Ok(false);
        }
        let mut updated = document.clone();
        updated.offer(self.snapshot.clone())?;
        updated.use_candidate()?;
        updated.bundles[updated.active].pinned = true;
        *document = updated;
        Ok(true)
    }
    /// Recover a completed job after a crash, without overriding an explicit
    /// selection of an older saved result on the next reopen.
    pub fn restore_if_missing(&self, document: &mut super::snapshot::Document) -> Result<bool> {
        if document
            .bundles
            .iter()
            .any(|bundle| bundle.snapshot.id == self.snapshot.id)
        {
            return Ok(false);
        }
        self.apply(document)
    }
    pub fn save(&self, state: &Path) -> Result<()> {
        self.validate()?;
        let folder = state.join("study/alignment");
        let path = folder.join(format!("{}.json", self.track));
        fastframe_file::write(&path, serde_json::to_vec(self)?)?;
        Ok(())
    }
    pub fn load(state: &Path, track: &str) -> Result<Option<Self>> {
        Self::load_from_study_dir(&state.join("study"), track)
    }
    /// The lyric worker already receives state/study, unlike the alignment job.
    pub fn load_from_study_dir(directory: &Path, track: &str) -> Result<Option<Self>> {
        if !valid_track(track) {
            bail!("Invalid generated track.");
        }
        let path = directory.join("alignment").join(format!("{track}.json"));
        if !path.is_file() {
            return Ok(None);
        }
        if path.metadata()?.len() > 8 * 1024 * 1024 {
            bail!("Generated timing file is too large.");
        }
        let result: Self = serde_json::from_slice(&std::fs::read(path)?)?;
        result.validate()?;
        if result.track != track {
            bail!("Invalid saved automatic timing identity.");
        }
        Ok(Some(result))
    }
}

/// Publish already verified bytes through upstream's atomic file writer.
/// Stream on the blocking pool so large model files do not occupy a runtime thread.
async fn publish_download(temporary: &Path, destination: &Path) -> Result<()> {
    let temporary = temporary.to_owned();
    let destination = destination.to_owned();
    tokio::task::spawn_blocking(move || -> std::io::Result<()> {
        fastframe_file::write_with(&destination, fastframe_file::Access::Default, |output| {
            let mut input = std::fs::File::open(&temporary)?;
            std::io::copy(&mut input, output)?;
            Ok(())
        })?;
        std::fs::remove_file(temporary)
    })
    .await??;
    Ok(())
}

async fn model(state: &Path, job: &Job) -> Result<PathBuf> {
    use tokio::io::AsyncWriteExt;
    let folder = state.join("models");
    tokio::fs::create_dir_all(&folder).await?;
    let path = folder.join(format!("tifa-1.0-ST-{MODEL_SHA}.zip"));
    if path.is_file() {
        job.update("Checking local timing model…".into());
        let check = path.clone();
        let valid = tokio::task::spawn_blocking(move || -> Result<bool> {
            let mut file = std::fs::File::open(check)?;
            if file.metadata()?.len() != MODEL_SIZE {
                return Ok(false);
            }
            let mut digest = Sha256::new();
            std::io::copy(&mut file, &mut digest)?;
            Ok(format!("{:x}", digest.finalize()) == MODEL_SHA)
        })
        .await??;
        if valid {
            return Ok(path);
        }
    }
    let temporary = path.with_extension("zip.part");
    let result = async {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(600))
            .build()?;
        let mut response = client.get(MODEL_URL).send().await?.error_for_status()?;
        let mut output = tokio::fs::File::create(&temporary).await?;
        let mut digest = Sha256::new();
        let mut bytes = 0u64;
        while let Some(chunk) = response.chunk().await? {
            if job.cancel.load(Ordering::Acquire) {
                bail!("Automatic timing cancelled.");
            }
            bytes += chunk.len() as u64;
            if bytes > MODEL_SIZE {
                bail!("Timing model download exceeds its pinned size.");
            }
            digest.update(&chunk);
            output.write_all(&chunk).await?;
            job.update(format!(
                "Downloading TIFA timing model · {}% · once, about 151 MB",
                bytes * 100 / MODEL_SIZE
            ));
        }
        if bytes != MODEL_SIZE || format!("{:x}", digest.finalize()) != MODEL_SHA {
            bail!("Timing model integrity check failed. Retry the download.");
        }
        output.sync_all().await?;
        drop(output);
        publish_download(&temporary, &path).await?;
        Ok(path.clone())
    };
    let cancelled = async {
        loop {
            if job.cancel.load(Ordering::Acquire) {
                return Err(anyhow::anyhow!("Automatic timing cancelled."));
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    };
    let result = tokio::select! { result = result => result, result = cancelled => result };
    if result.is_err() {
        let _ = tokio::fs::remove_file(temporary).await;
    }
    result
}

#[derive(Clone, Deserialize)]
struct Asset {
    path: String,
    url: String,
    size: u64,
    sha256: String,
}
fn valid_asset(path: &Path, asset: &Asset) -> Result<bool> {
    if !path.is_file() || path.metadata()?.len() != asset.size {
        return Ok(false);
    }
    let mut file = std::fs::File::open(path)?;
    let mut digest = Sha256::new();
    std::io::copy(&mut file, &mut digest)?;
    Ok(format!("{:x}", digest.finalize()) == asset.sha256)
}
async fn experimental_models(state: &Path, job: &Job) -> Result<PathBuf> {
    use tokio::io::AsyncWriteExt;
    let folder = state.join("models/refinement-v1");
    let assets: Vec<Asset> = serde_json::from_str(ASSETS)?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(900))
        .build()?;
    for (index, asset) in assets.iter().enumerate() {
        if job.cancel.load(Ordering::Acquire) {
            bail!("Automatic timing cancelled.");
        }
        let path = folder.join(&asset.path);
        job.update(format!(
            "Checking experimental models · {}/{}",
            index + 1,
            assets.len()
        ));
        let check_path = path.clone();
        let check_asset = asset.clone();
        if tokio::task::spawn_blocking(move || valid_asset(&check_path, &check_asset)).await?? {
            continue;
        }
        tokio::fs::create_dir_all(path.parent().unwrap()).await?;
        let temporary = path.with_extension("download.part");
        let result = async {
            let mut response = client.get(&asset.url).send().await?.error_for_status()?;
            let mut output = tokio::fs::File::create(&temporary).await?;
            let mut digest = Sha256::new();
            let mut bytes = 0;
            while let Some(chunk) = response.chunk().await? {
                bytes += chunk.len() as u64;
                if bytes > asset.size {
                    bail!("Experimental model exceeds its pinned size.");
                }
                output.write_all(&chunk).await?;
                digest.update(&chunk);
                job.update(format!(
                    "Downloading experimental models · {}/{} · {}%",
                    index + 1,
                    assets.len(),
                    bytes * 100 / asset.size
                ));
            }
            if bytes != asset.size || format!("{:x}", digest.finalize()) != asset.sha256 {
                bail!("Experimental model integrity check failed.");
            }
            output.sync_all().await?;
            drop(output);
            publish_download(&temporary, &path).await?;
            Ok::<(), anyhow::Error>(())
        };
        let cancelled = async {
            loop {
                if job.cancel.load(Ordering::Acquire) {
                    return Err(anyhow::anyhow!("Automatic timing cancelled."));
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        };
        let result = tokio::select! { result = result => result, result = cancelled => result };
        // The entire download can be cancelled while waiting on the network.
        if result.is_err() {
            let _ = tokio::fs::remove_file(&temporary).await;
        }
        result?;
    }
    Ok(folder)
}

#[derive(Clone)]
struct Crop {
    occurrence: usize,
    start: u32,
    end: u32,
    lyric_origin_ms: i64,
}
fn crops(source: &Snapshot, delay: i64, audio: &super::audio::Audio) -> Vec<Crop> {
    let end_ms = i64::from(audio.origin_ms) + audio.samples.len() as i64 * 1000 / 16_000;
    source
        .occurrences
        .iter()
        .filter_map(|line| {
            let cue = line.start_ms?.checked_add(delay)?;
            let next = source
                .occurrences
                .iter()
                .filter_map(|next| next.start_ms?.checked_add(delay))
                .filter(|next| *next > cue)
                .min()
                .unwrap_or(end_ms);
            let start = cue.saturating_sub(500).max(i64::from(audio.origin_ms));
            let end = next
                .saturating_add(300)
                .min(end_ms)
                .min(start.saturating_add(30_000));
            if end - start < 100 || line.raw_line.trim().is_empty() {
                return None;
            }
            Some(Crop {
                occurrence: line.id,
                start: ((start - i64::from(audio.origin_ms)) * 16) as u32,
                end: ((end - i64::from(audio.origin_ms)) * 16) as u32,
                lyric_origin_ms: start.checked_sub(delay)?,
            })
        })
        .collect()
}

#[derive(Deserialize)]
struct LineResult {
    occurrence: usize,
    units: Vec<Unit>,
}
#[derive(Deserialize)]
struct Unit {
    raw_span: [usize; 2],
    text: String,
    start_ms: i64,
    end_ms: i64,
}

#[derive(Clone)]
struct Target {
    raw_span: [usize; 2],
    text: String,
    romaji: String,
}

/// Model units match displayed words; punctuation removal never changes saved anchors.
fn word_targets(raw: &str, converted: &Response) -> Vec<Target> {
    converted
        .words
        .iter()
        .filter_map(|word| {
            let range = word.raw_span?;
            let source = span(raw, &range)?;
            if Some(source) != word.expected_text.as_deref() {
                return None;
            }
            let reading = word
                .hiragana_span
                .and_then(|range| span(&converted.hiragana, &range));
            let text: String = reading
                .filter(|text| !text.contains('？'))
                .unwrap_or(source)
                .chars()
                .filter(|ch| ch.is_alphanumeric())
                .collect();
            (!text.is_empty()).then_some(Target {
                raw_span: range,
                text,
                romaji: span(&converted.romaji, &word.output_span)?.to_string(),
            })
        })
        .collect()
}

/// Discard individual bad predictions, retaining the largest ordered set of real endpoints.
/// No clock is interpolated, snapped, or assigned to a different source word.
fn predicted_words(
    targets: &[Target],
    units: &[Unit],
    length_ms: i64,
) -> Option<Vec<([usize; 2], Interval)>> {
    if units.is_empty() {
        return Some(Vec::new());
    }
    if units.len() != targets.len() {
        return None;
    }
    let mut candidates = Vec::new();
    for (target, unit) in targets.iter().zip(units) {
        if unit.raw_span != target.raw_span || unit.text != target.text {
            return None;
        }
        if unit.start_ms >= 0 && unit.end_ms > unit.start_ms && unit.end_ms <= length_ms {
            candidates.push((
                target.raw_span,
                Interval {
                    start_ms: unit.start_ms,
                    end_ms: Some(unit.end_ms),
                },
            ));
        }
    }
    let mut lengths = vec![1usize; candidates.len()];
    let mut previous = vec![None; candidates.len()];
    let mut longest = None;
    for index in 0..candidates.len() {
        for earlier in 0..index {
            if candidates[earlier].1.start_ms < candidates[index].1.start_ms
                && candidates[earlier].1.end_ms <= candidates[index].1.end_ms
                && lengths[earlier] + 1 > lengths[index]
            {
                lengths[index] = lengths[earlier] + 1;
                previous[index] = Some(earlier);
            }
        }
        if longest.is_none_or(|best| lengths[index] > lengths[best]) {
            longest = Some(index);
        }
    }
    let mut ordered = Vec::new();
    while let Some(index) = longest {
        ordered.push(candidates[index].clone());
        longest = previous[index];
    }
    ordered.reverse();
    Some(ordered)
}

struct Scratch(PathBuf);
impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
struct Child(std::process::Child);
impl Drop for Child {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
fn infer(request: &Request, audio: super::audio::Audio, model: PathBuf) -> Result<Generated> {
    infer_with_stereo(request, audio, model, None, None)
}
fn infer_with_stereo(
    request: &Request,
    audio: super::audio::Audio,
    model: PathBuf,
    stereo: Option<Vec<f32>>,
    assets: Option<PathBuf>,
) -> Result<Generated> {
    let mut crop_list: Vec<_> = crops(&request.source, request.job.delay_ms, &audio)
        .into_iter()
        .filter_map(|crop| {
            let raw = &request
                .source
                .occurrences
                .iter()
                .find(|line| line.id == crop.occurrence)?
                .raw_line;
            let converted = request
                .converted
                .iter()
                .find(|line| line.occurrence_id == crop.occurrence)?;
            let targets = word_targets(raw, converted);
            (!targets.is_empty()).then_some((crop, targets))
        })
        .collect();
    if crop_list.is_empty() {
        bail!("Automatic timing needs line-synced Japanese lyrics. Refresh to try another source.");
    }
    let name = format!(
        "Romaji alignment {}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos()
    );
    let scratch = Scratch(std::env::temp_dir().join(name));
    std::fs::create_dir(&scratch.0)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&scratch.0, std::fs::Permissions::from_mode(0o700))?;
    }
    let mut pcm = std::io::BufWriter::new(std::fs::File::create(scratch.0.join("audio.pcm"))?);
    let mut digest = Sha256::new();
    for sample in &audio.samples {
        let bytes = sample.to_le_bytes();
        pcm.write_all(&bytes)?;
        digest.update(bytes);
    }
    pcm.flush()?;
    drop(pcm);
    if let Some(stereo) = &stereo {
        let mut file =
            std::io::BufWriter::new(std::fs::File::create(scratch.0.join("stereo.pcm"))?);
        for sample in stereo {
            let bytes = sample.to_le_bytes();
            file.write_all(&bytes)?;
            digest.update(bytes);
        }
        file.flush()?;
    }
    let audio_sha256 = format!("{:x}", digest.finalize());
    let mut input = std::fs::File::create(scratch.0.join("crops.bin"))?;
    input.write_all(&3u32.to_le_bytes())?;
    input.write_all(&(crop_list.len() as u32).to_le_bytes())?;
    for (crop, targets) in &crop_list {
        for value in [
            crop.occurrence as u32,
            crop.start,
            crop.end,
            targets.len() as u32,
        ] {
            input.write_all(&value.to_le_bytes())?;
        }
        for target in targets {
            for value in [
                target.raw_span[0] as u32,
                target.raw_span[1] as u32,
                target.text.len() as u32,
            ] {
                input.write_all(&value.to_le_bytes())?;
            }
            input.write_all(target.text.as_bytes())?;
            input.write_all(&(target.romaji.len() as u32).to_le_bytes())?;
            input.write_all(target.romaji.as_bytes())?;
        }
    }
    drop(input);
    let source_counts: std::collections::BTreeMap<_, _> = crop_list
        .iter()
        .map(|(crop, _)| {
            let total = request
                .converted
                .iter()
                .find(|line| line.occurrence_id == crop.occurrence)
                .unwrap()
                .words
                .len();
            (crop.occurrence.to_string(), total)
        })
        .collect();
    std::fs::write(
        scratch.0.join("crops.counts.json"),
        serde_json::to_vec(&source_counts)?,
    )?;
    let output_path = scratch.0.join("results.jsonl");
    let output = std::fs::File::create(&output_path)?;
    let progress_path = scratch.0.join("progress.txt");
    let mut command = match request.job.method {
        Method::Tifa => {
            let mut c = crate::shipping::tifa_command()?;
            c.arg(model)
                .arg(scratch.0.join("audio.pcm"))
                .arg(scratch.0.join("crops.bin"));
            c
        }
        Method::Experimental => {
            if stereo.is_none() {
                bail!("Experimental timing needs original stereo audio.");
            }
            super::reading::write_input(
                request,
                &scratch.0.join("crops.readings.json"),
                &request.job.method.fingerprint(),
                &audio_sha256,
            )?;
            let romanizer = crate::shipping::helper_command()?;
            let mut c = crate::shipping::experimental_command()?;
            c.arg(model)
                .arg(assets.ok_or_else(|| anyhow::anyhow!("Experimental models unavailable."))?)
                .arg(scratch.0.join("audio.pcm"))
                .arg(scratch.0.join("stereo.pcm"))
                .arg(scratch.0.join("crops.bin"))
                .arg(&progress_path)
                .arg(romanizer.get_program());
            c
        }
    };
    let mut child = Child(
        command
            .stdin(std::process::Stdio::null())
            .stdout(output)
            .stderr(if cfg!(test) {
                std::process::Stdio::inherit()
            } else {
                std::process::Stdio::null()
            })
            .spawn()?,
    );
    let started = Instant::now();
    let status = loop {
        if request.job.cancel.load(Ordering::Acquire)
            || started.elapsed()
                > Duration::from_secs(if request.job.method == Method::Experimental {
                    1800
                } else {
                    300
                })
            || output_path.metadata()?.len() > MAX_OUTPUT
        {
            bail!("Automatic timing cancelled or exceeded its processing limit.");
        }
        if let Some(status) = child.0.try_wait()? {
            break status;
        }
        let message = std::fs::metadata(&progress_path)
            .ok()
            .filter(|m| m.len() <= 512)
            .and_then(|_| std::fs::read_to_string(&progress_path).ok())
            .unwrap_or_else(|| format!("Aligning locally · {}…", request.job.method.label()));
        request.job.update(message);
        std::thread::sleep(Duration::from_millis(100));
    };
    if !status.success() {
        bail!("The local timing model failed. Playback and saved lyrics are intact; retry timing.");
    }
    let mut lines = std::io::BufReader::new(std::fs::File::open(output_path)?).lines();
    let (repaired_source, converted, repaired_readings) =
        if request.job.method == Method::Experimental {
            let header = lines
                .next()
                .ok_or_else(|| anyhow::anyhow!("Missing reading evidence."))??;
            if header.len() > 1_048_576 {
                bail!("Reading evidence exceeds reply limit.");
            }
            let package = serde_json::from_str(&header)?;
            let mut helper =
                super::conversion::Romanizer::start(&mut crate::shipping::helper_command()?)?;
            super::reading::admit(
                request,
                package,
                &request.job.method.fingerprint(),
                &audio_sha256,
                &mut helper,
            )?
        } else {
            (request.source.clone(), request.converted.clone(), 0)
        };
    for (crop, targets) in &mut crop_list {
        let raw = &repaired_source.occurrences[crop.occurrence].raw_line;
        let output = converted
            .iter()
            .find(|r| r.occurrence_id == crop.occurrence)
            .ok_or_else(|| anyhow::anyhow!("Missing corrected occurrence."))?;
        *targets = word_targets(raw, output);
    }
    let mut occurrences = repaired_source.occurrences.clone();
    let mut seen = std::collections::BTreeSet::new();
    let mut timed_words = 0;
    let total_words = converted.iter().map(|line| line.words.len()).sum();
    for line in lines {
        let line = line?;
        if line.len() > 1_048_576 {
            bail!("The timing helper exceeded its reply limit.");
        }
        let result: LineResult = serde_json::from_str(&line)?;
        let (crop, targets) = crop_list
            .iter()
            .find(|(crop, _)| crop.occurrence == result.occurrence)
            .ok_or_else(|| anyhow::anyhow!("Unexpected timing occurrence."))?;
        if !seen.insert(result.occurrence) {
            bail!("Duplicate timing occurrence.");
        }
        let occurrence = occurrences
            .iter_mut()
            .find(|line| line.id == result.occurrence)
            .ok_or_else(|| anyhow::anyhow!("Missing timing occurrence."))?;
        // Replace this run's scope only after a new result succeeds; historical
        // snapshots remain intact, but rejected words must not reuse old model guesses.
        occurrence
            .fragments
            .retain(|fragment| !fragment.source.starts_with("alignment:"));
        let Some(mut words) = predicted_words(
            targets,
            &result.units,
            i64::from(crop.end - crop.start) / 16,
        ) else {
            bail!("Timing reply does not match the freshly converted lyrics.");
        };
        for (_, interval) in &mut words {
            interval.start_ms += crop.lyric_origin_ms;
            interval.end_ms = interval.end_ms.map(|end| end + crop.lyric_origin_ms);
        }
        // At 80 ms resolution predicted word spans can overlap. Use the next
        // word's observed onset as the bound, never an evenly divided estimate.
        for index in 0..words.len() {
            let (range, mut interval) = words[index].clone();
            if let Some((_, next)) = words.get(index + 1) {
                interval.end_ms = interval.end_ms.map(|end| end.min(next.start_ms));
            }
            if !interval.valid() {
                continue;
            }
            occurrence
                .fragments
                .retain(|old| old.raw_span[0] >= range[1] || old.raw_span[1] <= range[0]);
            occurrence.fragments.push(Fragment {
                raw_span: range,
                interval,
                source: format!(
                    "alignment:{}:{}",
                    request.job.method.engine(),
                    request.job.method.fingerprint()
                ),
            });
            timed_words += 1;
        }
    }
    if seen.len() != crop_list.len() || timed_words == 0 {
        bail!(
            "The model could not time these words reliably. Existing lyrics are preserved; retry timing."
        );
    }
    let mut source = repaired_source.source.clone();
    source
        .warnings
        .retain(|warning| !warning.starts_with("Automatic word timing:"));
    source.warnings.push(format!(
        "Automatic word timing: {timed_words}/{total_words} words · {}.",
        request.job.method.label()
    ));
    let snapshot = Snapshot::new(source, occurrences)?;
    Ok(Generated {
        track: request.job.track.clone(),
        base_snapshot: request.source.id.clone(),
        base_revision: Some(request.job.revision),
        model_sha256: request.job.method.fingerprint(),
        engine: request.job.method.engine().into(),
        audio_sha256,
        delay_ms: request.job.delay_ms,
        repaired_readings,
        timed_words,
        total_words,
        snapshot,
    })
}

pub async fn run(
    session: librespot_core::session::Session,
    request: Request,
    state: PathBuf,
) -> Result<Generated> {
    request.source.validate()?;
    if request.job.snapshot != request.source.id
        || !valid_track(&request.job.track)
        || request.converted.iter().any(|line| {
            line.track_id != request.job.track
                || line.snapshot_id != request.source.id
                || line.override_revision != request.job.revision
        })
    {
        bail!("The lyrics changed. Retry timing with the current lyrics.");
    }
    let cancel = request.job.cancel.clone();
    let model = model(&state, &request.job).await?;
    request.job.update("Preparing song audio silently…".into());
    let progress_job = request.job.clone();
    let progress = Arc::new(move |message| progress_job.update(message));
    let result = if request.job.method == Method::Experimental {
        let assets = experimental_models(&state, &request.job).await?;
        let (audio, stereo) = super::audio::prepare_stereo(
            session,
            &request.job.track,
            request.job.cancel.clone(),
            progress,
        )
        .await?;
        tokio::task::spawn_blocking(move || {
            infer_with_stereo(&request, audio, model, Some(stereo), Some(assets))
        })
        .await??
    } else {
        let audio = super::audio::prepare(
            session,
            &request.job.track,
            request.job.cancel.clone(),
            progress,
        )
        .await?;
        tokio::task::spawn_blocking(move || infer(&request, audio, model)).await??
    };
    if cancel.load(Ordering::Acquire) {
        bail!("Automatic timing cancelled.");
    }
    result.save(&state)?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn publishing_a_verified_model_replaces_the_old_cache_atomically() {
        let directory = crate::study::testutil::TestDir::new();
        let temporary = directory.path().join("model.part");
        let destination = directory.path().join("model.bin");
        std::fs::write(&temporary, b"verified model").unwrap();
        std::fs::write(&destination, b"old cache").unwrap();
        publish_download(&temporary, &destination).await.unwrap();
        assert_eq!(std::fs::read(&destination).unwrap(), b"verified model");
        assert!(!temporary.exists());
    }

    #[tokio::test]
    async fn an_unreadable_model_download_preserves_the_previous_cache() {
        let directory = crate::study::testutil::TestDir::new();
        let temporary = directory.path().join("missing.part");
        let destination = directory.path().join("model.bin");
        std::fs::write(&destination, b"kept cache").unwrap();
        assert!(publish_download(&temporary, &destination).await.is_err());
        assert_eq!(std::fs::read(&destination).unwrap(), b"kept cache");
        assert_eq!(std::fs::read_dir(directory.path()).unwrap().count(), 1);
    }
    #[test]
    fn selecting_an_earlier_timing_version_survives_recovery_and_reopen() {
        use super::super::snapshot::Document;
        let directory = crate::study::testutil::TestDir::new();
        let source = super::super::source::import("[00:12.00]食べた", "synthetic.lrc").unwrap();
        let mut document = Document::new("25C3HZIvRGGtkasbrZe7D1", source.clone()).unwrap();
        for method in [Method::Tifa, Method::Experimental] {
            let mut occurrences = source.occurrences.clone();
            occurrences[0].fragments.push(Fragment {
                raw_span: [0, 9],
                interval: Interval {
                    start_ms: 12_000,
                    end_ms: Some(12_300),
                },
                source: format!("alignment:{}", method.engine()),
            });
            let result = Generated {
                track: document.track_id.clone(),
                base_snapshot: document.current().snapshot.id.clone(),
                base_revision: Some(document.revision),
                model_sha256: method.fingerprint(),
                engine: method.engine().into(),
                audio_sha256: "a".repeat(64),
                delay_ms: 0,
                repaired_readings: 0,
                timed_words: 1,
                total_words: 1,
                snapshot: Snapshot::new(source.source.clone(), occurrences).unwrap(),
            };
            assert!(result.apply(&mut document).unwrap());
            result.save(directory.path()).unwrap();
        }
        assert_eq!(document.bundles.len(), 3);
        let latest = Generated::load(directory.path(), &document.track_id)
            .unwrap()
            .unwrap();
        let previous = document.bundles[1].snapshot.clone();
        document.offer(previous.clone()).unwrap();
        document.use_candidate().unwrap();
        assert!(!latest.restore_if_missing(&mut document).unwrap());
        document.save(directory.path()).unwrap();
        let restored = Document::load(directory.path(), &document.track_id)
            .unwrap()
            .unwrap();
        assert_eq!(restored.current().snapshot.id, previous.id);
        assert_eq!(restored.bundles.len(), 3);
    }

    #[test]
    fn recovery_does_not_override_an_edit_made_after_a_completed_job() {
        use super::super::snapshot::{Anchor, Document, Edit};
        let source = super::super::source::import("[00:12.00]桜", "synthetic.lrc").unwrap();
        let mut document = Document::new("0000000000000000000000", source.clone()).unwrap();
        let result = Generated {
            track: document.track_id.clone(),
            base_snapshot: source.id.clone(),
            base_revision: Some(document.revision),
            model_sha256: MODEL_SHA.into(),
            engine: ENGINE.into(),
            audio_sha256: "a".repeat(64),
            delay_ms: 0,
            repaired_readings: 0,
            timed_words: 1,
            total_words: 1,
            snapshot: source.clone(),
        };
        document
            .save_edit(Edit::Reading {
                id: "mine".into(),
                anchor: Anchor::new(&document.track_id, &source, 0, [0, 3]).unwrap(),
                replacement: "my reading".into(),
                mapping: false,
            })
            .unwrap();
        let unchanged = document.clone();
        assert!(!result.apply(&mut document).unwrap());
        assert!(!result.restore_if_missing(&mut document).unwrap());
        assert_eq!(document, unchanged);
        let mut value = serde_json::to_value(result).unwrap();
        value.as_object_mut().unwrap().remove("base_revision");
        let legacy: Generated = serde_json::from_value(value).unwrap();
        assert!(legacy.base_revision.is_none());
    }
    #[tokio::test]
    async fn cancelling_experimental_setup_preserves_files_without_contacting_models() {
        let directory = crate::study::testutil::TestDir::new();
        let job = Job {
            method: Method::Experimental,
            track: "25C3HZIvRGGtkasbrZe7D1".into(),
            snapshot: "a".repeat(64),
            revision: 0,
            delay_ms: 0,
            cancel: Arc::new(AtomicBool::new(true)),
            status: Arc::new(Mutex::new(Status::Running("test".into()))),
        };
        let error = experimental_models(directory.path(), &job)
            .await
            .unwrap_err();
        assert_eq!(error.to_string(), "Automatic timing cancelled.");
        assert!(!directory.path().join("models").exists());
    }
    #[test]
    fn experimental_assets_are_size_and_digest_verified_before_loading() {
        let directory = crate::study::testutil::TestDir::new();
        let path = directory.path().join("model.safetensors");
        let bytes = b"synthetic checkpoint";
        let asset = Asset {
            path: "model.safetensors".into(),
            url: "https://example.invalid/unused".into(),
            size: bytes.len() as u64,
            sha256: format!("{:x}", Sha256::digest(bytes)),
        };
        assert!(!valid_asset(&path, &asset).unwrap());
        std::fs::write(&path, bytes).unwrap();
        assert!(valid_asset(&path, &asset).unwrap());
        std::fs::write(&path, vec![0; bytes.len()]).unwrap();
        assert!(!valid_asset(&path, &asset).unwrap());
        assert_ne!(
            Method::Tifa.fingerprint(),
            Method::Experimental.fingerprint()
        );
        assert_ne!(Method::Tifa.engine(), Method::Experimental.engine());
        let assets: Vec<Asset> = serde_json::from_str(ASSETS).unwrap();
        assert_eq!(assets.len(), 12);
        assert!(assets.iter().all(|a| {
            (a.url.starts_with("https://huggingface.co/")
                || a.url
                    .starts_with("https://github.com/Xiantaidu/RomajiASR/releases/"))
                && !a.path.contains("..")
        }));
    }
    #[test]
    #[ignore = "Explicit private recorded-song/model acceptance smoke; no bundled song audio"]
    fn recorded_song_pipeline_preserves_source_versions_and_reports_coverage() {
        use super::super::conversion::{Request as ConversionRequest, Romanizer};
        let mut document: super::super::snapshot::Document = serde_json::from_slice(
            &std::fs::read(std::env::var_os("ROMAJI_TEST_DOCUMENT").unwrap()).unwrap(),
        )
        .unwrap();
        document.validate().unwrap();
        let original = document.current().snapshot.clone();
        let old_versions = document.bundles.clone();
        let mut helper = Romanizer::start(&mut crate::shipping::helper_command().unwrap()).unwrap();
        let converted: Vec<_> = original
            .occurrences
            .iter()
            .map(|line| {
                helper
                    .convert(&ConversionRequest {
                        protocol_version: 1,
                        request_id: line.id as u64 + 1,
                        track_id: document.track_id.clone(),
                        snapshot_id: original.id.clone(),
                        occurrence_id: line.id,
                        override_revision: document.revision,
                        expected_conversion_signature: helper.signature.clone(),
                        raw_line: line.raw_line.clone(),
                        overrides: document.current().overrides(&document.track_id, line.id),
                    })
                    .unwrap()
            })
            .collect();
        let bytes = std::fs::read(std::env::var_os("ROMAJI_TEST_PCM").unwrap()).unwrap();
        let input_pcm_sha256 = format!("{:x}", Sha256::digest(&bytes));
        let samples = bytes
            .as_chunks::<4>()
            .0
            .iter()
            .map(|bytes| f32::from_le_bytes(*bytes))
            .collect();
        let method = if std::env::var("ROMAJI_TEST_METHOD").ok().as_deref() == Some("experimental")
        {
            Method::Experimental
        } else {
            Method::Tifa
        };
        let request = Request {
            protected: original
                .occurrences
                .iter()
                .flat_map(|line| {
                    document
                        .current()
                        .edits
                        .iter()
                        .filter(|edit| edit.applies(&document.track_id, &original, line.id))
                        .map(|edit| super::super::reading::ProtectedSpan {
                            occurrence_id: line.id,
                            raw_span: edit.anchor().raw_span,
                        })
                })
                .collect(),
            job: Job {
                method,
                track: document.track_id.clone(),
                snapshot: original.id.clone(),
                revision: document.revision,
                delay_ms: document.delay_ms,
                cancel: Arc::new(AtomicBool::new(false)),
                status: Arc::new(Mutex::new(Status::Running("test".into()))),
            },
            source: original.clone(),
            converted,
        };
        let audio = super::super::audio::Audio {
            origin_ms: 0,
            samples,
        };
        let model = PathBuf::from(std::env::var_os("ROMAJI_TEST_MODEL").unwrap());
        assert!(
            model.is_file(),
            "Explicit acceptance model archive must exist."
        );
        let started = Instant::now();
        let result = if method == Method::Experimental {
            let bytes = std::fs::read(std::env::var_os("ROMAJI_TEST_STEREO").unwrap()).unwrap();
            let stereo = bytes
                .as_chunks::<4>()
                .0
                .iter()
                .map(|b| f32::from_le_bytes(*b))
                .collect();
            infer_with_stereo(
                &request,
                audio,
                model,
                Some(stereo),
                Some(PathBuf::from(
                    std::env::var_os("ROMAJI_TEST_ASSETS").unwrap(),
                )),
            )
            .unwrap()
        } else {
            infer(&request, audio, model).unwrap()
        };
        let processing_seconds = started.elapsed().as_secs_f64();
        assert!(result.timed_words > 0);
        if method == Method::Tifa {
            assert_eq!(result.snapshot.text_fingerprint, original.text_fingerprint);
        }
        assert_eq!(result.engine, method.engine());
        assert!(result.snapshot.occurrences.iter().all(|line| {
            line.fragments
                .iter()
                .filter(|fragment| fragment.source.starts_with("alignment:"))
                .all(|fragment| {
                    fragment
                        .source
                        .starts_with(&format!("alignment:{}:", method.engine()))
                })
        }));
        let already_saved = old_versions
            .iter()
            .any(|bundle| bundle.snapshot.id == result.snapshot.id);
        assert!(result.apply(&mut document).unwrap());
        assert_eq!(
            document.bundles.len(),
            old_versions.len() + usize::from(!already_saved)
        );
        assert_eq!(&document.bundles[..old_versions.len()], old_versions);
        assert_eq!(document.current().snapshot.id, result.snapshot.id);
        assert!(document.current().pinned);
        let output = PathBuf::from(std::env::var_os("ROMAJI_TEST_RESULT_DIR").unwrap());
        result.save(&output).unwrap();
        assert_eq!(
            Generated::load(&output, &result.track)
                .unwrap()
                .unwrap()
                .snapshot,
            result.snapshot
        );
        document.save(&output.join("study")).unwrap();
        let reopened =
            super::super::snapshot::Document::load(&output.join("study"), &document.track_id)
                .unwrap()
                .unwrap();
        assert_eq!(reopened, document);
        println!(
            "Acceptance metrics: {}",
            serde_json::json!({
                "track": result.track,
                "method": method.label(),
                "engine": result.engine,
                "base_snapshot": result.base_snapshot,
                "audio_sha256": result.audio_sha256,
                "input_pcm_sha256": input_pcm_sha256,
                "timed_words": result.timed_words,
                "total_words": result.total_words,
                "repaired_readings": result.repaired_readings,
                "processing_seconds": processing_seconds,
                "previous_versions": old_versions.len(),
                "saved_versions": reopened.bundles.len(),
                "reopened": true,
            })
        );
        println!(
            "Recorded-song word coverage: {}/{}; {} readings repaired; previous versions retained.",
            result.timed_words, result.total_words, result.repaired_readings
        );
    }
    #[test]
    #[ignore = "Explicit local Metal/model smoke; not part of offline hooks"]
    fn packaged_model_maps_synthetic_speech_and_withholds_silence() {
        use super::super::conversion::{Request as ConversionRequest, Romanizer};
        let model = PathBuf::from(std::env::var_os("ROMAJI_TEST_MODEL").unwrap());
        let bytes = std::fs::read(std::env::var_os("ROMAJI_TEST_PCM").unwrap()).unwrap();
        let samples: Vec<_> = bytes
            .as_chunks::<4>()
            .0
            .iter()
            .map(|bytes| f32::from_le_bytes(*bytes))
            .collect();
        let source =
            super::super::source::import("[00:00.00]桜を食べた。今日は晴れです。", "synthetic.lrc")
                .unwrap();
        let mut helper = Romanizer::start(&mut crate::shipping::helper_command().unwrap()).unwrap();
        let track = "0000000000000000000000".to_string();
        let converted = helper
            .convert(&ConversionRequest {
                protocol_version: 1,
                request_id: 1,
                track_id: track.clone(),
                snapshot_id: source.id.clone(),
                occurrence_id: 0,
                override_revision: 0,
                expected_conversion_signature: helper.signature.clone(),
                raw_line: source.occurrences[0].raw_line.clone(),
                overrides: vec![],
            })
            .unwrap();
        let request = Request {
            protected: Vec::new(),
            job: Job {
                method: Method::Tifa,
                track,
                snapshot: source.id.clone(),
                revision: 0,
                delay_ms: 0,
                cancel: Arc::new(AtomicBool::new(false)),
                status: Arc::new(Mutex::new(Status::Running("test".into()))),
            },
            source,
            converted: vec![converted],
        };
        let result = infer(
            &request,
            super::super::audio::Audio {
                origin_ms: 0,
                samples: samples.clone(),
            },
            model.clone(),
        )
        .unwrap();
        assert!(result.timed_words >= 6);
        let word = result.snapshot.occurrences[0]
            .fragments
            .iter()
            .find(|fragment| fragment.raw_span == [6, 15])
            .unwrap();
        assert_eq!(
            word.interval,
            Interval {
                start_ms: 560,
                // Pinned TIFA's observed endpoint (10 ms frames), replacing Qwen's 80 ms grid.
                end_ms: Some(1090)
            }
        );
        assert!(
            infer(
                &request,
                super::super::audio::Audio {
                    origin_ms: 0,
                    samples: vec![0.0; samples.len()]
                },
                model
            )
            .is_err()
        );
    }
    fn target(raw_span: [usize; 2], text: &str) -> Target {
        Target {
            raw_span,
            text: text.into(),
            romaji: text.into(),
        }
    }
    fn prediction(raw_span: [usize; 2], text: &str, start_ms: i64, end_ms: i64) -> Unit {
        Unit {
            raw_span,
            text: text.into(),
            start_ms,
            end_ms,
        }
    }

    #[test]
    fn repeated_words_keep_explicit_source_spans_and_reject_cross_attachment() {
        let targets = vec![target([0, 9], "食べた"), target([10, 19], "食べた")];
        let mut units = vec![
            prediction([0, 9], "食べた", 100, 500),
            prediction([10, 19], "食べた", 600, 900),
        ];
        let words = predicted_words(&targets, &units, 1000).unwrap();
        assert_eq!(
            words[0],
            (
                [0, 9],
                Interval {
                    start_ms: 100,
                    end_ms: Some(500)
                }
            )
        );
        assert_eq!(
            words[1],
            (
                [10, 19],
                Interval {
                    start_ms: 600,
                    end_ms: Some(900)
                }
            )
        );
        units[1].raw_span = [0, 9];
        assert!(predicted_words(&targets, &units, 1000).is_none());
        assert!(predicted_words(&targets, &units[..1], 1000).is_none());
        assert!(predicted_words(&targets, &[], 1000).unwrap().is_empty());
    }

    #[test]
    fn invalid_word_predictions_do_not_discard_valid_neighbors_or_invent_times() {
        let targets = vec![
            target([0, 3], "桜"),
            target([4, 7], "を"),
            target([8, 11], "風"),
            target([12, 15], "に"),
            target([16, 19], "春"),
            target([20, 23], "へ"),
        ];
        let units = vec![
            prediction([0, 3], "桜", 100, 180),
            prediction([4, 7], "を", 200, 200),
            prediction([8, 11], "風", 310, 290),
            prediction([12, 15], "に", 330, 600),
            prediction([16, 19], "春", -5, 20),
            prediction([20, 23], "へ", 480, 540),
        ];
        let words = predicted_words(&targets, &units, 550).unwrap();
        assert_eq!(
            words,
            vec![
                (
                    [0, 3],
                    Interval {
                        start_ms: 100,
                        end_ms: Some(180)
                    }
                ),
                (
                    [20, 23],
                    Interval {
                        start_ms: 480,
                        end_ms: Some(540)
                    }
                )
            ]
        );
    }

    #[test]
    fn backwards_word_is_omitted_without_shifting_remaining_model_endpoints() {
        let targets = vec![
            target([0, 3], "桜"),
            target([3, 6], "を"),
            target([6, 9], "風"),
            target([9, 12], "に"),
        ];
        let units = vec![
            prediction([0, 3], "桜", 100, 220),
            prediction([3, 6], "を", 450, 550),
            prediction([6, 9], "風", 300, 420),
            prediction([9, 12], "に", 600, 800),
        ];
        let words = predicted_words(&targets, &units, 1000).unwrap();
        assert_eq!(
            words.iter().map(|(range, _)| *range).collect::<Vec<_>>(),
            vec![[0, 3], [3, 6], [9, 12]]
        );
        assert_eq!(
            words[1].1,
            Interval {
                start_ms: 450,
                end_ms: Some(550)
            }
        );
        assert_eq!(
            words[2].1,
            Interval {
                start_ms: 600,
                end_ms: Some(800)
            }
        );
        assert!(
            predicted_words(
                &targets[..1],
                &[prediction([0, 3], "wrong", 100, 220)],
                1000
            )
            .is_none()
        );
    }

    #[test]
    fn model_word_overlap_is_preserved_until_display_selection_is_bounded() {
        let targets = vec![target([0, 3], "桜"), target([3, 6], "を")];
        let units = vec![
            prediction([0, 3], "桜", 100, 380),
            prediction([3, 6], "を", 300, 500),
        ];
        let words = predicted_words(&targets, &units, 1000).unwrap();
        assert_eq!(words[0].1.end_ms, Some(380));
        assert_eq!(words[1].1.start_ms, 300);
    }

    #[test]
    fn model_targets_preserve_source_spans_when_stripping_punctuation() {
        use super::super::conversion::{Request as ConversionRequest, Romanizer};
        let source = super::super::source::import("桜を食べた。", "synthetic.txt").unwrap();
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut command = std::process::Command::new(root.join(".venv/bin/python"));
        command.arg(root.join("romanizer/romanizer.py"));
        let mut helper = Romanizer::start(&mut command).unwrap();
        let converted = helper
            .convert(&ConversionRequest {
                protocol_version: 1,
                request_id: 1,
                track_id: "0000000000000000000000".into(),
                snapshot_id: source.id,
                occurrence_id: 0,
                override_revision: 0,
                expected_conversion_signature: helper.signature.clone(),
                raw_line: source.occurrences[0].raw_line.clone(),
                overrides: vec![],
            })
            .unwrap();
        let targets = word_targets(&source.occurrences[0].raw_line, &converted);
        assert_eq!(targets.len(), 3);
        assert_eq!(targets[2].raw_span, [6, 15]);
        assert_eq!(targets[2].text, "たべた");
    }

    #[test]
    fn offset_clock_and_durable_results_survive_cache_clear_without_replacing_other_versions() {
        use super::super::snapshot::Document;
        let state = std::env::temp_dir().join(format!(
            "romaji-generated-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let source = super::super::source::import("[00:12.00]食べた", "synthetic.lrc").unwrap();
        let audio = super::super::audio::Audio {
            origin_ms: 0,
            samples: vec![0.0; 16_000 * 15],
        };
        let crop = &crops(&source, 500, &audio)[0];
        // Audio crop begins at P=12,000. Saved timestamps use P-d, exactly once.
        assert_eq!(crop.start, 12_000 * 16);
        assert_eq!(crop.lyric_origin_ms + 200, 11_700);
        let mut occurrences = source.occurrences.clone();
        occurrences[0].fragments = vec![Fragment {
            raw_span: [0, 9],
            interval: Interval {
                start_ms: crop.lyric_origin_ms + 200,
                end_ms: Some(crop.lyric_origin_ms + 500),
            },
            source: "alignment:test".into(),
        }];
        let result = Generated {
            track: "25C3HZIvRGGtkasbrZe7D1".into(),
            base_snapshot: source.id.clone(),
            base_revision: None,
            model_sha256: MODEL_SHA.into(),
            engine: ENGINE.into(),
            audio_sha256: "a".repeat(64),
            delay_ms: 500,
            repaired_readings: 0,
            timed_words: 1,
            total_words: 1,
            snapshot: Snapshot::new(source.source.clone(), occurrences).unwrap(),
        };
        let mut document = Document::new(&result.track, source.clone()).unwrap();
        document.delay_ms = 500;
        result.save(&state).unwrap();
        assert!(
            Generated::load(&state, &result.track)
                .unwrap()
                .unwrap()
                .apply(&mut document)
                .unwrap()
        );
        assert!(document.current().pinned);
        document.save(&state).unwrap();
        std::fs::create_dir_all(state.join("cache")).unwrap();
        std::fs::remove_dir_all(state.join("cache")).unwrap();
        let restored = Document::load(&state, &result.track).unwrap().unwrap();
        assert_eq!(restored.current().snapshot.id, result.snapshot.id);
        assert_eq!(restored.bundles.len(), 2);
        let mut different = Document::new(&result.track, source).unwrap();
        assert!(!result.apply(&mut different).unwrap()); // changed delay must not silently shift alignment
        different.delay_ms = 500;
        different.track_id = "1lTfD2M6UpJRWi3YLb8qb5".into();
        assert!(!result.apply(&mut different).unwrap());
        let mut invalid = result.clone();
        invalid.audio_sha256 = "z".repeat(64);
        assert!(invalid.save(&state).is_err());
        std::fs::remove_dir_all(state).unwrap();
    }
}
