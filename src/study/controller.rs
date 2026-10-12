//! One background worker owns disk I/O and the persistent conversion process.
//! Generation IDs discard results from a previous song, snapshot or edit revision.
use std::collections::BTreeMap;
use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, SyncSender, TrySendError};
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};

use anyhow::{Result, anyhow};

use super::conversion::{Request, Response, Romanizer};
use super::snapshot::{Anchor, AttachmentPreview, Document, Edit, Snapshot};
use super::timing::{Interval, WordTiming, tap_lyric_ms};

enum Work {
    Load {
        track: String,
        source: Option<Snapshot>,
    },
    Save(Document),
    Import {
        track: String,
        path: PathBuf,
        current: Option<Document>,
    },
}
struct Job {
    generation: u64,
    work: Work,
}
enum Reply {
    Document(Option<Document>),
    Line(Response),
    Error(String),
    Done,
}
struct Message {
    generation: u64,
    reply: Reply,
}
struct Worker {
    jobs: SyncSender<Job>,
    replies: Receiver<Message>,
    closing: Arc<AtomicBool>,
    thread: std::thread::JoinHandle<()>,
}

#[derive(Default)]
pub struct Study {
    track: Option<String>,
    generation: u64,
    worker: Option<Worker>,
    pending: Option<Job>,
    pending_saves: BTreeMap<String, Job>,
    pub document: Option<Document>,
    pub converted: BTreeMap<usize, Response>,
    pub busy: bool,
    pub error: Option<String>,
    pub selected: Option<(usize, usize)>,
    selected_source: Option<[usize; 2]>,
    pub editor: Editor,
    pub undo: Option<Edit>,
    pub preview: Option<AttachmentPreview>,
    pub link: String,
    pub show_original: bool,
    pub review_open: bool,
    pub alignment: Option<super::alignment::Job>,
    pub alignment_message: Option<String>,
}

#[derive(Default)]
pub struct Editor {
    pub reading: String,
    pub start: Option<i64>,
    pub end: Option<i64>,
    pub mapping: bool,
    /// Character boundaries selected by the user; converted to raw UTF-8 offsets.
    pub mapping_start: usize,
    pub mapping_end: usize,
}

impl Drop for Study {
    fn drop(&mut self) {
        self.shutdown();
    }
}

impl Study {
    pub fn shutdown(&mut self) {
        if let Some(job) = &self.alignment {
            job.cancel.store(true, Ordering::Release);
        }
        if let Some(worker) = self.worker.take() {
            // Stop conversion and flush the newest edits at quit. Suppress replies
            // so the bounded reply queue cannot deadlock while the UI is closing.
            worker.closing.store(true, Ordering::Release);
            for (_, job) in std::mem::take(&mut self.pending_saves) {
                let _ = worker.jobs.send(job);
            }
            if let Some(document) = self.document.take() {
                let _ = worker.jobs.send(Job {
                    generation: self.generation,
                    work: Work::Save(document),
                });
            }
            drop(worker.jobs);
            let _ = worker.thread.join();
        }
    }
}

impl Study {
    pub fn activate(&mut self, track: Option<&str>) {
        let track = track.filter(|track| super::snapshot::valid_track(track));
        if self.track.as_deref() == track {
            return;
        }
        self.track = track.map(str::to_owned);
        self.document = None;
        self.converted.clear();
        self.selected = None;
        self.editor = Editor::default();
        self.preview = None;
        self.undo = None;
        self.error = None;
        self.alignment_message = None;
        if let Some(track) = self.track.clone() {
            self.queue(Work::Load {
                track,
                source: None,
            });
        } else {
            self.generation += 1;
            self.pending = None;
            self.busy = false;
        }
    }
    pub fn offer(&mut self, snapshot: Snapshot) -> Result<()> {
        let track = self
            .track
            .clone()
            .ok_or_else(|| anyhow!("Play a Spotify song first."))?;
        if let Some(document) = &mut self.document {
            if document.current().snapshot.id == snapshot.id {
                return Ok(());
            }
            document.offer(snapshot)?;
            self.persist();
        } else {
            self.queue(Work::Load {
                track,
                source: Some(snapshot),
            });
        }
        Ok(())
    }
    pub fn import(&mut self, path: PathBuf) {
        if let Some(track) = &self.track {
            self.queue(Work::Import {
                track: track.clone(),
                path,
                current: self.document.clone(),
            });
        }
    }
    fn queue(&mut self, work: Work) {
        self.generation += 1;
        let job = Job {
            generation: self.generation,
            work,
        };
        if let Work::Save(document) = &job.work {
            self.pending_saves.insert(document.track_id.clone(), job);
            self.pending = None;
        } else {
            self.pending = Some(job);
        }
        self.busy = true;
        self.error = None;
    }
    pub fn persist(&mut self) {
        if let Some(document) = self.document.clone() {
            self.queue(Work::Save(document));
        }
    }
    pub fn poll(&mut self, directory: PathBuf, ctx: &egui::Context) {
        self.poll_alignment(ctx);
        if self.worker.is_none() && (self.pending.is_some() || !self.pending_saves.is_empty()) {
            self.worker = Some(start_worker(directory, ctx.clone()));
        }
        let Some(worker) = &self.worker else {
            return;
        };
        if let Some(job) = self
            .pending_saves
            .pop_first()
            .map(|(_, job)| job)
            .or_else(|| self.pending.take())
        {
            match worker.jobs.try_send(job) {
                Ok(()) => {}
                Err(TrySendError::Full(job)) => {
                    if let Work::Save(document) = &job.work {
                        self.pending_saves.insert(document.track_id.clone(), job);
                    } else {
                        self.pending = Some(job);
                    }
                }
                Err(TrySendError::Disconnected(_)) => {
                    self.error = Some("The lyric worker stopped. Restart the app to retry.".into());
                    self.busy = false;
                }
            }
        }
        for message in worker.replies.try_iter() {
            if message.generation != self.generation {
                continue;
            }
            match message.reply {
                Reply::Document(document) => {
                    self.document = document;
                    self.converted.clear();
                }
                Reply::Line(output) => {
                    if self
                        .document
                        .as_ref()
                        .is_some_and(|document| current_output(document, &output))
                    {
                        if let Some((occurrence, index)) = self.selected
                            && occurrence == output.occurrence_id
                            && output
                                .words
                                .get(index)
                                .is_none_or(|word| word.raw_span != self.selected_source)
                        {
                            self.selected = None;
                            self.preview = None;
                        }
                        self.converted.insert(output.occurrence_id, output);
                    }
                }
                Reply::Error(error) => self.error = Some(error),
                Reply::Done => self.busy = false,
            }
        }
        if self.busy {
            ctx.request_repaint_after(std::time::Duration::from_millis(50));
        }
    }
    pub fn alignment_request(
        &mut self,
        method: super::alignment::Method,
    ) -> Result<super::alignment::Request> {
        if self.alignment.is_some() || self.busy {
            return Err(anyhow!("Wait for the current lyric operation to finish."));
        }
        let document = self
            .document
            .as_ref()
            .ok_or_else(|| anyhow!("Play a song with lyrics first."))?;
        if !document
            .current()
            .snapshot
            .occurrences
            .iter()
            .any(|line| line.start_ms.is_some() && !line.raw_line.trim().is_empty())
        {
            return Err(anyhow!(
                "Automatic timing needs line-synced lyrics. Try Refresh."
            ));
        }
        let converted: Vec<_> = self
            .converted
            .values()
            .filter(|line| current_output(document, line))
            .cloned()
            .collect();
        if converted.len() != document.current().snapshot.occurrences.len() {
            return Err(anyhow!("Wait for the romaji conversion to finish."));
        }
        let job = super::alignment::Job {
            method,
            track: document.track_id.clone(),
            snapshot: document.current().snapshot.id.clone(),
            revision: document.revision,
            delay_ms: document.delay_ms,
            cancel: Arc::new(AtomicBool::new(false)),
            status: Arc::new(std::sync::Mutex::new(super::alignment::Status::Running(
                "Starting automatic word timing…".into(),
            ))),
        };
        let request = super::alignment::Request {
            job: job.clone(),
            source: document.current().snapshot.clone(),
            converted,
        };
        self.alignment = Some(job);
        self.alignment_message = None;
        Ok(request)
    }
    fn poll_alignment(&mut self, ctx: &egui::Context) {
        let Some(job) = self.alignment.clone() else {
            return;
        };
        let status = job.status.lock().unwrap_or_else(|p| p.into_inner()).clone();
        match status {
            super::alignment::Status::Running(_) => {
                ctx.request_repaint_after(std::time::Duration::from_millis(100))
            }
            super::alignment::Status::Failed(message) => {
                self.alignment = None;
                self.alignment_message = Some(message);
            }
            super::alignment::Status::Complete(result) => {
                self.alignment = None;
                let applied = self
                    .document
                    .as_mut()
                    .filter(|doc| doc.revision == job.revision && doc.delay_ms == job.delay_ms)
                    .map(|doc| result.apply(doc))
                    .transpose();
                match applied {
                    Ok(Some(true)) => { self.selected = None; self.converted.clear(); self.persist(); self.alignment_message = Some(format!("{} · saved {}/{} words", job.method.label(), result.timed_words, result.total_words)); }
                    Ok(_) => self.alignment_message = Some("Automatic timing saved for the previous lyric version. Return to that version to use it.".into()),
                    Err(_) => self.alignment_message = Some("Timing saved, but the current lyrics changed. Retry for this version.".into()),
                }
            }
        }
    }
    pub fn output(&self, occurrence: usize) -> Option<&Response> {
        let document = self.document.as_ref()?;
        self.converted
            .get(&occurrence)
            .filter(|output| current_output(document, output))
    }
    pub fn active_line(&self, playback_ms: i64) -> Option<usize> {
        let document = self.document.as_ref()?;
        let lyric = playback_ms.checked_sub(document.delay_ms)?;
        document
            .current()
            .snapshot
            .occurrences
            .iter()
            .filter_map(|line| {
                let cue = line.start_ms.or_else(|| {
                    self.timings(line.id)
                        .into_iter()
                        .flatten()
                        .flat_map(|timing| {
                            timing
                                .intervals
                                .into_iter()
                                .map(|interval| interval.start_ms)
                        })
                        .min()
                })?;
                (cue <= lyric).then_some((cue, line.id))
            })
            .max()
            .map(|(_, id)| id)
    }
    pub fn timings(&self, occurrence: usize) -> Vec<Option<WordTiming>> {
        let Some(document) = &self.document else {
            return Vec::new();
        };
        let Some(output) = self.output(occurrence) else {
            return Vec::new();
        };
        let bundle = document.current();
        let line = &bundle.snapshot.occurrences[occurrence];
        output
            .words
            .iter()
            .map(|word| {
                let supplied = word
                    .raw_span
                    .and_then(|range| WordTiming::supplied(range, &line.fragments));
                WordTiming::effective(
                    supplied,
                    bundle.manual_timing(&document.track_id, occurrence, word, &output.words),
                )
            })
            .collect()
    }
    /// Start-only words select until the next genuinely supplied/annotated cue.
    /// Blank line cues bound the last word without inventing a measured end.
    pub fn cues(&self) -> Vec<i64> {
        let Some(document) = &self.document else {
            return Vec::new();
        };
        let mut cues = Vec::new();
        for line in &document.current().snapshot.occurrences {
            cues.extend(line.start_ms);
            for timing in self.timings(line.id).into_iter().flatten() {
                cues.extend(timing.intervals.iter().map(|interval| interval.start_ms));
            }
        }
        cues.sort_unstable();
        cues.dedup();
        cues
    }
    pub fn select(&mut self, occurrence: usize, word: usize) -> Result<()> {
        let output = self
            .output(occurrence)
            .ok_or_else(|| anyhow!("Wait for this line to convert."))?;
        let selected = output
            .words
            .get(word)
            .ok_or_else(|| anyhow!("Select a word."))?;
        let reading = super::conversion::span(&output.romaji, &selected.output_span)
            .unwrap_or("")
            .to_string();
        let raw = &self
            .document
            .as_ref()
            .unwrap()
            .current()
            .snapshot
            .occurrences[occurrence]
            .raw_line;
        let range = selected.raw_span.unwrap_or([0, raw.len()]);
        let mapping = selected.raw_span.is_none();
        let selected_source = selected.raw_span;
        let start = raw[..range[0]].chars().count();
        let end = raw[..range[1]].chars().count();
        let timing = self.timings(occurrence).get(word).cloned().flatten();
        self.selected = Some((occurrence, word));
        self.selected_source = selected_source;
        self.editor = Editor {
            reading,
            start: timing
                .as_ref()
                .and_then(|timing| timing.intervals.first().map(|interval| interval.start_ms)),
            end: timing
                .as_ref()
                .and_then(|timing| timing.intervals.last().and_then(|interval| interval.end_ms)),
            mapping,
            mapping_start: start,
            mapping_end: end,
        };
        self.preview = None;
        Ok(())
    }
    pub fn selected_anchor(&self) -> Result<Anchor> {
        let (occurrence, word) = self
            .selected
            .ok_or_else(|| anyhow!("Select a word first."))?;
        let document = self
            .document
            .as_ref()
            .ok_or_else(|| anyhow!("No lyric source."))?;
        let output = self
            .output(occurrence)
            .ok_or_else(|| anyhow!("Wait for the updated conversion."))?;
        let selected = &output.words[word];
        let range = selected
            .raw_span
            .ok_or_else(|| anyhow!("Fix the original-text mapping first."))?;
        if output
            .words
            .iter()
            .filter(|word| word.raw_span == Some(range))
            .count()
            != 1
        {
            return Err(anyhow!("Fix the original-text mapping first."));
        }
        Anchor::new(
            &document.track_id,
            &document.current().snapshot,
            occurrence,
            range,
        )
    }
    pub fn save_reading(&mut self) -> Result<()> {
        let (occurrence, _) = self
            .selected
            .ok_or_else(|| anyhow!("Select a word first."))?;
        let document = self
            .document
            .as_ref()
            .ok_or_else(|| anyhow!("No lyric source."))?;
        let anchor = if self.editor.mapping {
            let raw = &document.current().snapshot.occurrences[occurrence].raw_line;
            let boundaries: Vec<_> = raw
                .char_indices()
                .map(|(index, _)| index)
                .chain(std::iter::once(raw.len()))
                .collect();
            let range = [
                *boundaries
                    .get(self.editor.mapping_start)
                    .ok_or_else(|| anyhow!("Invalid selection."))?,
                *boundaries
                    .get(self.editor.mapping_end)
                    .ok_or_else(|| anyhow!("Invalid selection."))?,
            ];
            Anchor::new(
                &document.track_id,
                &document.current().snapshot,
                occurrence,
                range,
            )?
        } else {
            self.selected_anchor()?
        };
        let edit = Edit::Reading {
            id: self.new_id("reading"),
            anchor,
            replacement: self.editor.reading.clone(),
            mapping: self.editor.mapping,
        };
        self.document.as_mut().unwrap().save_edit(edit)?;
        self.selected = None;
        self.persist();
        Ok(())
    }
    fn new_id(&self, kind: &str) -> String {
        format!(
            "{kind}-{}-{}",
            self.generation,
            self.document
                .as_ref()
                .map_or(0, |document| document.revision)
        )
    }
    pub fn tap(&mut self, playback_ms: i64, end: bool) -> Result<()> {
        self.selected_anchor()?;
        let time = tap_lyric_ms(playback_ms, self.document.as_ref().unwrap().delay_ms)
            .ok_or_else(|| anyhow!("Playback time is out of range."))?;
        if end {
            self.editor.end = Some(time);
        } else {
            self.editor.start = Some(time);
        }
        Ok(())
    }
    pub fn save_timing(&mut self) -> Result<()> {
        let anchor = self.selected_anchor()?;
        let (occurrence, word) = self.selected.unwrap();
        let output = self.output(occurrence).unwrap();
        let interval = Interval {
            start_ms: self
                .editor
                .start
                .ok_or_else(|| anyhow!("Tap or enter a start time."))?,
            end_ms: self.editor.end,
        };
        let edit = Edit::Timing {
            id: self.new_id("timing"),
            anchor,
            interval,
            displayed_at_annotation: super::conversion::span(
                &output.romaji,
                &output.words[word].output_span,
            )
            .unwrap_or("")
            .into(),
            conversion_signature: output.conversion_signature.clone(),
        };
        self.document.as_mut().unwrap().save_edit(edit)?;
        self.persist();
        Ok(())
    }
    pub fn reset_selected(&mut self, reading: bool) -> Result<()> {
        let anchor = self.selected_anchor()?;
        let document = self.document.as_mut().unwrap();
        let id = document
            .current()
            .edits
            .iter()
            .find(|edit| {
                edit.is_reading() == reading
                    && edit.applies(
                        &document.track_id,
                        &document.current().snapshot,
                        anchor.occurrence_id,
                    )
                    && edit.anchor().raw_span == anchor.raw_span
            })
            .map(|edit| edit.id().to_string());
        if let Some(id) = id {
            self.undo = document.discard(&id);
            self.persist();
        }
        Ok(())
    }
}

pub fn current_output(document: &Document, output: &Response) -> bool {
    output.track_id == document.track_id
        && output.snapshot_id == document.current().snapshot.id
        && output.override_revision == document.revision
}

fn start_worker(directory: PathBuf, ctx: egui::Context) -> Worker {
    worker_with(directory, ctx, crate::shipping::helper_command)
}

fn worker_with(
    directory: PathBuf,
    ctx: egui::Context,
    command: impl Fn() -> Result<std::process::Command> + Send + 'static,
) -> Worker {
    let (jobs, receiver) = mpsc::sync_channel::<Job>(1);
    let (sender, replies) = mpsc::sync_channel::<Message>(8);
    let closing = Arc::new(AtomicBool::new(false));
    let stopping = closing.clone();
    let thread = std::thread::spawn(move || {
        let mut helper: Option<Romanizer> = None;
        let mut next = None;
        let mut request_id = 0;
        'jobs: while let Some(job) = next.take().or_else(|| receiver.recv().ok()) {
            let generation = job.generation;
            let send = |reply| {
                if stopping.load(Ordering::Acquire) {
                    return true;
                }
                ctx.request_repaint();
                let mut message = Message { generation, reply };
                loop {
                    match sender.try_send(message) {
                        Ok(()) => return true,
                        Err(TrySendError::Disconnected(_)) => return false,
                        Err(TrySendError::Full(returned)) => {
                            if stopping.load(Ordering::Acquire) {
                                return true;
                            }
                            message = returned;
                            std::thread::sleep(std::time::Duration::from_millis(5));
                        }
                    }
                }
            };
            let loaded: Result<Option<Document>> = (|| match job.work {
                Work::Load { track, source } => {
                    let mut document = Document::load(&directory, &track).map_err(|_| {
                        anyhow!("Saved lyrics could not be read. The saved file was preserved.")
                    })?;
                    if let Some(source) = source {
                        if let Some(saved) = &mut document {
                            if saved.current().snapshot.id != source.id {
                                saved.offer(source)?;
                            }
                        } else {
                            document = Some(Document::new(&track, source)?);
                        }
                    }
                    if let Some(saved) = &mut document {
                        match super::alignment::Generated::load_from_study_dir(&directory, &track) {
                            Ok(Some(generated)) if generated.restore_if_missing(saved)? => {
                                saved.save(&directory)?
                            }
                            Err(_) => {
                                send(Reply::Error("Saved automatic timings could not be read. Existing lyric versions are preserved; retry timing.".into()));
                            }
                            _ => {}
                        }
                    }
                    Ok(document)
                }
                Work::Save(document) => {
                    document.save(&directory).map_err(|_| {
                        anyhow!("Changes could not be saved. Choose Retry save before closing.")
                    })?;
                    Ok(Some(document))
                }
                Work::Import {
                    track,
                    path,
                    current,
                } => {
                    use std::io::Read;
                    let file = std::fs::File::open(&path)
                        .map_err(|_| anyhow!("Could not read the lyrics file."))?;
                    let mut bytes = Vec::new();
                    file.take(1_048_577).read_to_end(&mut bytes)?;
                    if bytes.len() > 1_048_576 {
                        return Err(anyhow!("Lyrics file exceeds 1 MiB."));
                    }
                    let text = std::str::from_utf8(&bytes)
                        .map_err(|_| anyhow!("Import a UTF-8 lyrics file."))?;
                    let source = super::source::import(
                        text,
                        path.file_name()
                            .and_then(|name| name.to_str())
                            .unwrap_or("Imported lyrics"),
                    )?;
                    let mut document =
                        current.or(Document::load(&directory, &track).map_err(|_| {
                            anyhow!("Saved lyrics could not be read. The saved file was preserved.")
                        })?);
                    if let Some(saved) = &mut document {
                        saved.offer(source)?;
                    } else {
                        document = Some(Document::new(&track, source)?);
                    }
                    if let Some(saved) = &document {
                        saved
                            .save(&directory)
                            .map_err(|_| anyhow!("Imported lyrics could not be saved."))?;
                    }
                    Ok(document)
                }
            })();
            let document = match loaded {
                Ok(document) => document,
                Err(error) => {
                    if !send(Reply::Error(error.to_string())) {
                        break;
                    }
                    send(Reply::Done);
                    continue;
                }
            };
            if !send(Reply::Document(document.clone())) {
                break;
            }
            if let Some(document) = document {
                if stopping.load(Ordering::Acquire) {
                    continue;
                }
                if helper.is_none() {
                    helper = command()
                        .and_then(|mut command| Romanizer::start(&mut command))
                        .ok();
                }
                let Some(converter) = &mut helper else {
                    if !send(Reply::Error("The romanizer could not start. Original lyrics and playback are available; Retry save retries conversion.".into())) { break; }
                    send(Reply::Done);
                    continue;
                };
                for line in &document.current().snapshot.occurrences {
                    if stopping.load(Ordering::Acquire) {
                        break;
                    }
                    if let Ok(job) = receiver.try_recv() {
                        next = Some(job);
                        continue 'jobs;
                    }
                    request_id += 1;
                    let request = Request {
                        protocol_version: 1,
                        request_id,
                        track_id: document.track_id.clone(),
                        snapshot_id: document.current().snapshot.id.clone(),
                        occurrence_id: line.id,
                        override_revision: document.revision,
                        expected_conversion_signature: converter.signature.clone(),
                        raw_line: line.raw_line.clone(),
                        overrides: document.current().overrides(&document.track_id, line.id),
                    };
                    match converter.convert(&request) {
                        Ok(output) => {
                            if !send(Reply::Line(output)) {
                                break 'jobs;
                            }
                        }
                        Err(_) => {
                            send(Reply::Error("Conversion failed. Original lyrics and saved edits were preserved; retry conversion.".into()));
                            helper = None;
                            break;
                        }
                    }
                }
            }
            if !send(Reply::Done) {
                break;
            }
        }
    });
    Worker {
        jobs,
        replies,
        closing,
        thread,
    }
}

#[cfg(test)]
mod tests {
    use super::super::source::import;
    use super::*;
    use std::process::Command;
    use std::time::{Duration, Instant};
    const TRACK: &str = "0000000000000000000000";
    const OTHER: &str = "1111111111111111111111";

    fn command() -> Result<Command> {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut command = Command::new(root.join(".venv/bin/python"));
        command.arg(root.join("romanizer/romanizer.py"));
        Ok(command)
    }
    fn convert(study: &mut Study) {
        let mut helper = Romanizer::start(&mut command().unwrap()).unwrap();
        let document = study.document.as_ref().unwrap();
        for line in &document.current().snapshot.occurrences {
            let request = Request {
                protocol_version: 1,
                request_id: line.id as u64 + 1,
                track_id: document.track_id.clone(),
                snapshot_id: document.current().snapshot.id.clone(),
                occurrence_id: line.id,
                override_revision: document.revision,
                expected_conversion_signature: helper.signature.clone(),
                raw_line: line.raw_line.clone(),
                overrides: document.current().overrides(&document.track_id, line.id),
            };
            study
                .converted
                .insert(line.id, helper.convert(&request).unwrap());
        }
    }
    fn fixture() -> Study {
        let source = import(
            "[00:10]<00:10>桜<00:11> を<00:12>\n[00:15]\n[00:20]<00:20>桜<00:21> を<00:22>",
            "fixture.lrc",
        )
        .unwrap();
        let mut study = Study::default();
        study.activate(Some(TRACK));
        study.document = Some(Document::new(TRACK, source).unwrap());
        convert(&mut study);
        study
    }
    #[test]
    fn controller_taps_use_saved_delay_manual_wins_and_reset_restores_supplied() {
        let mut study = fixture();
        study.document.as_mut().unwrap().delay_ms = 500;
        study.select(0, 0).unwrap();
        study.tap(12000, false).unwrap();
        study.tap(12300, true).unwrap();
        study.save_timing().unwrap();
        convert(&mut study);
        let timing = study.timings(0)[0].clone().unwrap();
        assert!(timing.manual);
        assert_eq!(
            timing.intervals[0],
            Interval {
                start_ms: 11500,
                end_ms: Some(11800)
            }
        );
        assert!(timing.active(12050, 500, None));
        assert!(!timing.active(12500, 500, None));
        assert!(!study.timings(2)[0].as_ref().unwrap().manual);
        study.reset_selected(false).unwrap();
        convert(&mut study);
        assert!(!study.timings(0)[0].as_ref().unwrap().manual);
        assert_eq!(
            study.timings(0)[0].as_ref().unwrap().intervals[0].start_ms,
            10000
        );
    }
    #[test]
    fn reading_edit_keeps_word_timings_on_identical_repeats_and_neighbor() {
        let mut study = fixture();
        study.select(0, 0).unwrap();
        study.editor.reading = "new reading".into();
        study.save_reading().unwrap();
        assert!(study.output(0).is_none()); // old revision cannot drive a marker
        convert(&mut study);
        for occurrence in [0, 2] {
            let output = study.output(occurrence).unwrap();
            assert_eq!(output.romaji, "new reading o");
            assert_eq!(output.words.len(), 2);
            assert!(study.timings(occurrence).iter().all(Option::is_some));
        }
        assert_eq!(study.active_line(15500), Some(1)); // blank cue clears chorus following
    }

    #[test]
    fn manual_words_in_plain_lyrics_drive_following_and_bound_previous_start_only_word() {
        let mut study = fixture();
        study.document =
            Some(Document::new(TRACK, import("桜\n食べた", "plain.txt").unwrap()).unwrap());
        study.converted.clear();
        convert(&mut study);
        for (occurrence, start) in [(0, 1000), (1, 2000)] {
            study.select(occurrence, 0).unwrap();
            study.editor.start = Some(start);
            study.editor.end = None;
            study.save_timing().unwrap();
            convert(&mut study);
        }
        assert_eq!(study.active_line(500), None);
        assert_eq!(study.active_line(1500), Some(0));
        assert_eq!(study.active_line(2500), Some(1));
        let cues = study.cues();
        let bound = cues
            .get(cues.partition_point(|time| *time <= 1000))
            .copied();
        assert_eq!(bound, Some(2000));
        assert!(!study.timings(0)[0].as_ref().unwrap().active(2500, 0, bound));
    }
    #[test]
    fn track_change_and_immediate_quit_flush_queued_edits_without_reply_deadlock() {
        let dir = crate::study::testutil::TestDir::new();
        let mut study = fixture();
        study.worker = Some(worker_with(
            dir.path().into(),
            egui::Context::default(),
            command,
        ));
        study.select(0, 0).unwrap();
        study.editor.reading = "saved reading".into();
        study.save_reading().unwrap(); // not yet dispatched by a UI frame
        study.activate(Some(OTHER));
        drop(study);
        let saved = Document::load(dir.path(), TRACK).unwrap().unwrap();
        assert!(saved.current().pinned);
        assert!(
            matches!(&saved.current().edits[0],Edit::Reading { replacement,.. } if replacement == "saved reading")
        );
    }
    fn settle(study: &mut Study, directory: &std::path::Path) {
        let deadline = Instant::now() + Duration::from_secs(10);
        let ctx = egui::Context::default();
        while study.busy || study.pending.is_some() || !study.pending_saves.is_empty() {
            assert!(Instant::now() < deadline, "worker failed to settle");
            study.poll(directory.into(), &ctx);
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    #[test]
    fn saved_alignment_loads_from_real_study_directory_and_survives_reopening() {
        use super::super::alignment::Generated;
        use super::super::timing::Fragment;

        let state = crate::study::testutil::TestDir::new();
        let directory = state.path().join("study");
        let source = import("[00:10]桜 を", "fixture.lrc").unwrap();
        let mut original = Document::new(TRACK, source.clone()).unwrap();
        original.delay_ms = 500;
        original
            .save_edit(Edit::Reading {
                id: "saved-reading".into(),
                anchor: Anchor::new(TRACK, &source, 0, [0, 3]).unwrap(),
                replacement: "sakura".into(),
                mapping: false,
            })
            .unwrap();
        original.save(&directory).unwrap();
        let mut occurrences = source.occurrences.clone();
        occurrences[0].fragments = vec![
            Fragment {
                raw_span: [0, 3],
                interval: Interval {
                    start_ms: 10_000,
                    end_ms: Some(10_700),
                },
                source: "alignment:synthetic-model".into(),
            },
            Fragment {
                raw_span: [4, 7],
                interval: Interval {
                    start_ms: 10_900,
                    end_ms: Some(11_100),
                },
                source: "alignment:synthetic-model".into(),
            },
        ];
        let generated = Generated {
            track: TRACK.into(),
            base_snapshot: source.id.clone(),
            model_sha256: "a".repeat(64),
            engine: "synthetic-model".into(),
            audio_sha256: "b".repeat(64),
            delay_ms: 500,
            timed_words: 2,
            total_words: 2,
            snapshot: Snapshot::new(source.source.clone(), occurrences).unwrap(),
        };
        generated.save(state.path()).unwrap();
        let mut study = Study::default();
        study.worker = Some(worker_with(
            directory.clone(),
            egui::Context::default(),
            command,
        ));
        study.activate(Some(TRACK));
        settle(&mut study, &directory);
        assert!(study.error.is_none());
        let applied = study.document.as_ref().unwrap().clone();
        assert_eq!(applied.current().snapshot.id, generated.snapshot.id);
        assert!(applied.current().pinned);
        assert_eq!(applied.bundles.len(), 2);
        assert_eq!(applied.bundles[0], original.bundles[0]);
        assert_eq!(applied.current().edits, original.current().edits);
        let timings = study.timings(0);
        assert_eq!(timings.len(), 2);
        assert!(timings[0].as_ref().unwrap().active(10_800, 500, None));
        assert!(!timings[0].as_ref().unwrap().active(11_300, 500, None));
        assert!(timings[1].as_ref().unwrap().active(11_500, 500, None));
        drop(study);

        std::fs::create_dir_all(state.path().join("cache")).unwrap();
        std::fs::remove_dir_all(state.path().join("cache")).unwrap();
        let mut reopened = Study::default();
        reopened.worker = Some(worker_with(
            directory.clone(),
            egui::Context::default(),
            command,
        ));
        reopened.activate(Some(TRACK));
        settle(&mut reopened, &directory);
        assert!(reopened.error.is_none());
        assert_eq!(reopened.document.as_ref(), Some(&applied));
        assert_eq!(reopened.timings(0), timings);
    }
    #[test]
    fn background_worker_discards_previous_song_results_and_preserves_corrupt_state() {
        let dir = crate::study::testutil::TestDir::new();
        let mut study = Study::default();
        study.activate(Some(TRACK));
        study.worker = Some(worker_with(
            dir.path().into(),
            egui::Context::default(),
            command,
        ));
        study
            .offer(import("[00:01]桜", "first.lrc").unwrap())
            .unwrap();
        study.poll(dir.path().into(), &egui::Context::default());
        study.activate(Some(OTHER));
        study
            .offer(import("[00:02]食べた", "second.lrc").unwrap())
            .unwrap();
        settle(&mut study, dir.path());
        assert_eq!(study.document.as_ref().unwrap().track_id, OTHER);
        assert_eq!(study.output(0).unwrap().romaji, "tabeta");
        assert!(
            study
                .converted
                .values()
                .all(|output| output.track_id == OTHER)
        );
        std::fs::write(
            dir.path().join(format!("{TRACK}.json")),
            "preserve corrupt file",
        )
        .unwrap();
        study.activate(Some(TRACK));
        study.offer(import("桜", "new.lrc").unwrap()).unwrap();
        settle(&mut study, dir.path());
        assert!(study.document.is_none());
        assert!(study.error.as_deref().unwrap().contains("preserved"));
        drop(study);
        assert_eq!(
            std::fs::read_to_string(dir.path().join(format!("{TRACK}.json"))).unwrap(),
            "preserve corrupt file"
        );
    }
}
