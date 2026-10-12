//! Durable source identity and edits. Conversion caches are never authoritative.
use std::path::{Path, PathBuf};

use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::conversion::{Override, Response, Word, span};
use super::timing::{Fragment, Interval};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Occurrence {
    /// Ordinal in source expansion order, before playback sorting.
    pub id: usize,
    pub raw_line: String,
    pub start_ms: Option<i64>,
    pub fragments: Vec<Fragment>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Source {
    pub imported: bool,
    pub provider: String,
    pub candidate: String,
    pub payload: String,
    pub warnings: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Snapshot {
    pub id: String,
    pub text_fingerprint: String,
    pub source: Source,
    pub occurrences: Vec<Occurrence>,
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn text_fingerprint(occurrences: &[Occurrence]) -> String {
    let lines: Vec<_> = occurrences.iter().map(|line| &line.raw_line).collect();
    // serde_json emits literal UTF-8 and compact standard JSON escaping.
    digest(&serde_json::to_vec(&(1, lines)).expect("strings always serialize"))
}

impl Snapshot {
    pub fn new(source: Source, occurrences: Vec<Occurrence>) -> Result<Self> {
        let snapshot = Self {
            id: digest(&serde_json::to_vec(&(&source, &occurrences))?),
            text_fingerprint: text_fingerprint(&occurrences),
            source,
            occurrences,
        };
        snapshot.validate()?;
        Ok(snapshot)
    }

    pub fn validate(&self) -> Result<()> {
        if self.text_fingerprint != text_fingerprint(&self.occurrences)
            || self.id != digest(&serde_json::to_vec(&(&self.source, &self.occurrences))?)
            || self.occurrences.len() > 2_000
            || self.source.payload.len() > 1_048_576
        {
            bail!("invalid lyric snapshot identity or size");
        }
        for (ordinal, line) in self.occurrences.iter().enumerate() {
            if line.id != ordinal || line.raw_line.len() > 8_192 || line.raw_line.contains('\n') {
                bail!("invalid lyric occurrence");
            }
            for fragment in &line.fragments {
                if span(&line.raw_line, &fragment.raw_span).is_none() || !fragment.interval.valid()
                {
                    bail!("invalid source timing fragment");
                }
            }
        }
        Ok(())
    }

    pub fn playback_order(&self) -> Vec<usize> {
        let mut ids: Vec<_> = (0..self.occurrences.len()).collect();
        ids.sort_by_key(|id| (self.occurrences[*id].start_ms.unwrap_or(i64::MAX), *id));
        ids
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Anchor {
    pub track_id: String,
    pub text_fingerprint: String,
    pub occurrence_id: usize,
    pub raw_span: [usize; 2],
    pub expected_text: String,
    pub raw_line: String,
    /// Explicitly displaced associations remain available for review/Undo.
    #[serde(default)]
    pub review_reason: Option<String>,
}

impl Anchor {
    pub fn new(
        track: &str,
        snapshot: &Snapshot,
        occurrence: usize,
        range: [usize; 2],
    ) -> Result<Self> {
        let line = snapshot
            .occurrences
            .get(occurrence)
            .ok_or_else(|| anyhow::anyhow!("unknown occurrence"))?;
        let text = span(&line.raw_line, &range)
            .filter(|text| !text.trim().is_empty())
            .ok_or_else(|| anyhow::anyhow!("select a nonblank original-text span"))?;
        Ok(Self {
            track_id: track.into(),
            text_fingerprint: snapshot.text_fingerprint.clone(),
            occurrence_id: occurrence,
            raw_span: range,
            expected_text: text.into(),
            raw_line: line.raw_line.clone(),
            review_reason: None,
        })
    }

    fn matches(&self, track: &str, snapshot: &Snapshot, occurrence: usize, repeated: bool) -> bool {
        self.track_id == track
            && self.review_reason.is_none()
            && self.text_fingerprint == snapshot.text_fingerprint
            && (repeated || self.occurrence_id == occurrence)
            && snapshot.occurrences.get(occurrence).is_some_and(|line| {
                line.raw_line == self.raw_line
                    && span(&line.raw_line, &self.raw_span) == Some(self.expected_text.as_str())
            })
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Edit {
    Reading {
        id: String,
        anchor: Anchor,
        replacement: String,
        mapping: bool,
    },
    Timing {
        id: String,
        anchor: Anchor,
        interval: Interval,
        displayed_at_annotation: String,
        conversion_signature: String,
    },
}

impl Edit {
    pub fn id(&self) -> &str {
        match self {
            Self::Reading { id, .. } | Self::Timing { id, .. } => id,
        }
    }
    pub fn anchor(&self) -> &Anchor {
        match self {
            Self::Reading { anchor, .. } | Self::Timing { anchor, .. } => anchor,
        }
    }
    pub fn is_reading(&self) -> bool {
        matches!(self, Self::Reading { .. })
    }
    fn anchor_mut(&mut self) -> &mut Anchor {
        match self {
            Self::Reading { anchor, .. } | Self::Timing { anchor, .. } => anchor,
        }
    }
    fn same_attachment(&self, other: &Self) -> bool {
        let a = self.anchor();
        let b = other.anchor();
        self.is_reading() == other.is_reading()
            && a.text_fingerprint == b.text_fingerprint
            && a.raw_line == b.raw_line
            && a.raw_span == b.raw_span
            && (self.is_reading() || a.occurrence_id == b.occurrence_id)
    }
    pub fn applies(&self, track: &str, snapshot: &Snapshot, occurrence: usize) -> bool {
        self.anchor()
            .matches(track, snapshot, occurrence, self.is_reading())
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Bundle {
    pub snapshot: Snapshot,
    pub pinned: bool,
    pub edits: Vec<Edit>,
}

impl Bundle {
    pub fn overrides(&self, track: &str, occurrence: usize) -> Vec<Override> {
        self.edits
            .iter()
            .filter_map(|edit| {
                if let Edit::Reading {
                    id,
                    anchor,
                    replacement,
                    mapping,
                } = edit
                    && edit.applies(track, &self.snapshot, occurrence)
                {
                    Some(Override {
                        id: id.clone(),
                        kind: if *mapping { "mapping" } else { "reading" }.into(),
                        raw_span: anchor.raw_span,
                        expected_text: anchor.expected_text.clone(),
                        replacement: replacement.clone(),
                    })
                } else {
                    None
                }
            })
            .collect()
    }

    pub fn manual_timing(
        &self,
        track: &str,
        occurrence: usize,
        word: &Word,
        all_words: &[Word],
    ) -> Option<Interval> {
        let range = word.raw_span?;
        if word.mapping_status != "mapped"
            || all_words
                .iter()
                .filter(|word| word.raw_span == Some(range))
                .count()
                != 1
        {
            return None;
        }
        self.edits.iter().find_map(|edit| {
            if let Edit::Timing {
                anchor, interval, ..
            } = edit
                && edit.applies(track, &self.snapshot, occurrence)
                && anchor.raw_span == range
                && interval.valid()
            {
                Some(interval.clone())
            } else {
                None
            }
        })
    }

    pub fn pending_timings(&self, track: &str, converted: &[(usize, Vec<Word>)]) -> Vec<String> {
        self.edits
            .iter()
            .filter_map(|edit| {
                let Edit::Timing { id, anchor, .. } = edit else {
                    return None;
                };
                if !edit.applies(track, &self.snapshot, anchor.occurrence_id) {
                    return Some(id.clone());
                }
                let (_, words) = converted
                    .iter()
                    .find(|(id, _)| *id == anchor.occurrence_id)?;
                if words
                    .iter()
                    .filter(|word| {
                        word.raw_span == Some(anchor.raw_span) && word.mapping_status == "mapped"
                    })
                    .count()
                    != 1
                {
                    Some(id.clone())
                } else {
                    None
                }
            })
            .collect()
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Document {
    pub schema_version: u32,
    pub track_id: String,
    pub delay_ms: i64,
    pub revision: u64,
    pub active: usize,
    pub bundles: Vec<Bundle>,
    pub candidate: Option<Snapshot>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AttachmentPreview {
    pub edit: Edit,
    pub affected_occurrences: Vec<usize>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReviewItem {
    pub edit_id: String,
    pub occurrence_id: Option<usize>,
    pub reason: String,
}

impl Document {
    pub fn new(track: &str, snapshot: Snapshot) -> Result<Self> {
        let document = Self {
            schema_version: 1,
            track_id: track.into(),
            delay_ms: 0,
            revision: 0,
            active: 0,
            bundles: vec![Bundle {
                pinned: snapshot.source.imported,
                snapshot,
                edits: Vec::new(),
            }],
            candidate: None,
        };
        document.validate()?;
        Ok(document)
    }
    pub fn validate(&self) -> Result<()> {
        if self.schema_version != 1
            || !valid_track(&self.track_id)
            || self.active >= self.bundles.len()
        {
            bail!("invalid saved song document");
        }
        for bundle in &self.bundles {
            bundle.snapshot.validate()?;
            let mut ids = std::collections::HashSet::new();
            for edit in &bundle.edits {
                let anchor = edit.anchor();
                if !ids.insert(edit.id())
                    || edit.id().is_empty()
                    || anchor.track_id != self.track_id
                    || span(&anchor.raw_line, &anchor.raw_span)
                        != Some(anchor.expected_text.as_str())
                {
                    bail!("invalid saved edit anchor");
                }
                match edit {
                    Edit::Reading { replacement, .. } if !valid_reading(replacement) => {
                        bail!("invalid saved reading")
                    }
                    Edit::Timing { interval, .. } if !interval.valid() => {
                        bail!("invalid saved timing")
                    }
                    _ => {}
                }
            }
        }
        if let Some(candidate) = &self.candidate {
            candidate.validate()?;
        }
        Ok(())
    }
    pub fn current(&self) -> &Bundle {
        &self.bundles[self.active]
    }
    /// Background refresh proposes a candidate; even a timing-only change is explicit.
    pub fn offer(&mut self, candidate: Snapshot) -> Result<()> {
        candidate.validate()?;
        self.candidate = Some(candidate);
        Ok(())
    }
    pub fn use_candidate(&mut self) -> Result<()> {
        let snapshot = self
            .candidate
            .take()
            .ok_or_else(|| anyhow::anyhow!("no lyric candidate"))?;
        if let Some(index) = self
            .bundles
            .iter()
            .position(|bundle| bundle.snapshot.id == snapshot.id)
        {
            self.active = index;
        } else {
            let edits = self.current().edits.clone();
            let pinned = self.current().pinned || snapshot.source.imported;
            self.bundles.push(Bundle {
                snapshot,
                pinned,
                edits,
            });
            self.active = self.bundles.len() - 1;
        }
        self.revision += 1;
        Ok(())
    }
    pub fn save_edit(&mut self, mut edit: Edit) -> Result<()> {
        if let Edit::Reading { replacement, .. } = &mut edit {
            if replacement.contains(['\n', '\r']) {
                bail!("a reading correction cannot contain line breaks");
            }
            *replacement = replacement.trim().to_string();
        }
        if !edit.applies(
            &self.track_id,
            &self.current().snapshot,
            edit.anchor().occurrence_id,
        ) {
            bail!("edit belongs to a different lyric snapshot");
        }
        let mut next = self.clone();
        let edits = &mut next.bundles[next.active].edits;
        if edits.iter().any(|existing| existing.id() == edit.id())
            && edits.iter().any(|existing| {
                existing.id() != edit.id()
                    && existing.same_attachment(&edit)
                    && existing.applies(
                        &self.track_id,
                        &self.current().snapshot,
                        edit.anchor().occurrence_id,
                    )
            })
        {
            bail!(
                "selected word already has a local edit; reset or discard that edit before attaching another"
            );
        }
        // Re-editing the same unit updates one record, even from another chorus.
        if let Some(index) = edits.iter().position(|existing| {
            existing.id() == edit.id()
                || (existing.same_attachment(&edit)
                    && existing.applies(
                        &self.track_id,
                        &self.current().snapshot,
                        edit.anchor().occurrence_id,
                    ))
        }) {
            let id = edits[index].id().to_string();
            match &mut edit {
                Edit::Reading { id: next, .. } | Edit::Timing { id: next, .. } => *next = id,
            }
        }
        if let Edit::Reading {
            anchor, mapping, ..
        } = &edit
        {
            for existing in edits
                .iter_mut()
                .filter(|existing| existing.is_reading() && existing.id() != edit.id())
            {
                let original = existing.anchor();
                if original.review_reason.is_none()
                    && original.text_fingerprint == anchor.text_fingerprint
                    && original.raw_line == anchor.raw_line
                    && original.raw_span[0] < anchor.raw_span[1]
                    && anchor.raw_span[0] < original.raw_span[1]
                {
                    if !mapping {
                        bail!(
                            "reading overlaps an existing correction; select the full mapping group"
                        );
                    }
                    existing.anchor_mut().review_reason = Some("replaced_by_mapping".into());
                }
            }
        }
        if let Some(existing) = edits.iter_mut().find(|existing| existing.id() == edit.id()) {
            *existing = edit;
        } else {
            edits.push(edit);
        }
        next.bundles[next.active].pinned = true;
        next.revision += 1;
        next.validate()?;
        *self = next;
        Ok(())
    }
    pub fn needs_review(&self, converted: &[Response]) -> Vec<ReviewItem> {
        let bundle = self.current();
        let mut review = Vec::new();
        for edit in &bundle.edits {
            if !edit.applies(
                &self.track_id,
                &bundle.snapshot,
                edit.anchor().occurrence_id,
            ) {
                review.push(ReviewItem {
                    edit_id: edit.id().into(),
                    occurrence_id: None,
                    reason: edit
                        .anchor()
                        .review_reason
                        .clone()
                        .unwrap_or_else(|| "different_lyric_text".into()),
                });
                continue;
            }
            for output in converted.iter().filter(|output| {
                output.track_id == self.track_id
                    && output.snapshot_id == bundle.snapshot.id
                    && output.override_revision == self.revision
                    && edit.applies(&self.track_id, &bundle.snapshot, output.occurrence_id)
            }) {
                let reason = match edit {
                    Edit::Reading { .. } => output
                        .pending_overrides
                        .iter()
                        .find(|pending| pending.id == edit.id())
                        .map(|pending| pending.reason.clone()),
                    Edit::Timing { anchor, .. } => (output
                        .words
                        .iter()
                        .filter(|word| {
                            word.raw_span == Some(anchor.raw_span)
                                && word.mapping_status == "mapped"
                        })
                        .count()
                        != 1)
                        .then(|| "changed_word_mapping".into()),
                };
                if let Some(reason) = reason {
                    review.push(ReviewItem {
                        edit_id: edit.id().into(),
                        occurrence_id: Some(output.occurrence_id),
                        reason,
                    });
                }
            }
        }
        review
    }
    /// Pure preview: confirmation uses save_edit, retaining timing without shifting choruses.
    pub fn attachment_preview(
        &self,
        id: &str,
        output: &Response,
        selected_word: usize,
    ) -> Result<AttachmentPreview> {
        if output.track_id != self.track_id
            || output.snapshot_id != self.current().snapshot.id
            || output.override_revision != self.revision
        {
            bail!("selection belongs to a stale lyric conversion");
        }
        let word = output
            .words
            .get(selected_word)
            .ok_or_else(|| anyhow::anyhow!("select a current word"))?;
        let range = word
            .raw_span
            .ok_or_else(|| anyhow::anyhow!("fix this word mapping before attaching an edit"))?;
        if word.mapping_status != "mapped"
            || output
                .words
                .iter()
                .filter(|word| word.raw_span == Some(range))
                .count()
                != 1
        {
            bail!("word has no unique source mapping");
        }
        let anchor = Anchor::new(
            &self.track_id,
            &self.current().snapshot,
            output.occurrence_id,
            range,
        )?;
        if word.expected_text.as_deref() != Some(anchor.expected_text.as_str()) {
            bail!("word source text differs from saved lyrics");
        }
        let mut edit = self
            .current()
            .edits
            .iter()
            .find(|edit| edit.id() == id)
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("unknown saved edit"))?;
        let affected_occurrences = if edit.is_reading() {
            self.current()
                .snapshot
                .occurrences
                .iter()
                .filter(|line| line.raw_line == anchor.raw_line)
                .map(|line| line.id)
                .collect()
        } else {
            vec![output.occurrence_id]
        };
        *edit.anchor_mut() = anchor;
        Ok(AttachmentPreview {
            edit,
            affected_occurrences,
        })
    }
    /// Returns the full record for Undo; no source baseline is removed.
    pub fn discard(&mut self, id: &str) -> Option<Edit> {
        let bundle = &mut self.bundles[self.active];
        let index = bundle.edits.iter().position(|edit| edit.id() == id)?;
        self.revision += 1;
        Some(bundle.edits.remove(index))
    }
    pub fn restore(&mut self, edit: Edit) -> Result<()> {
        // Pending records may be undone without attaching them to current text.
        let mut next = self.clone();
        if next
            .current()
            .edits
            .iter()
            .any(|record| record.id() == edit.id())
        {
            bail!("edit already exists");
        }
        next.bundles[next.active].edits.push(edit);
        next.bundles[next.active].pinned = true;
        next.revision += 1;
        next.validate()?;
        *self = next;
        Ok(())
    }
    pub fn save(&self, directory: &Path) -> Result<()> {
        self.validate()?;
        let path = directory.join(format!("{}.json", self.track_id));
        let bytes = serde_json::to_vec(self)?;
        fastframe_file::write(&path, bytes)?;
        Ok(())
    }
    pub fn load(directory: &Path, track: &str) -> Result<Option<Self>> {
        if !valid_track(track) {
            bail!("invalid Spotify track ID");
        }
        let path = directory.join(format!("{track}.json"));
        let bytes = match std::fs::read(path) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error.into()),
        };
        let saved: Self = serde_json::from_slice(&bytes)?;
        saved.validate()?;
        if saved.track_id != track {
            bail!("saved song identity mismatch");
        }
        Ok(Some(saved))
    }
}

pub fn valid_track(track: &str) -> bool {
    track.len() == 22 && track.bytes().all(|byte| byte.is_ascii_alphanumeric())
}
pub fn valid_reading(reading: &str) -> bool {
    !reading.contains(['\n', '\r'])
        && reading.trim() == reading
        && reading.chars().any(char::is_alphanumeric)
}
pub fn directory(dirs: &crate::paths::AppDirs) -> PathBuf {
    dirs.state.join("study")
}

#[cfg(test)]
mod tests {
    use super::super::conversion::{Request, Response, Romanizer};
    use super::super::source::import;
    use super::*;
    use std::process::Command;
    const TRACK: &str = "0000000000000000000000";

    fn song() -> Snapshot {
        import("[00:12][01:30]桜\n[01:40]", "fixture.lrc").unwrap()
    }
    fn reading(snapshot: &Snapshot, occurrence: usize, replacement: &str) -> Edit {
        Edit::Reading {
            id: "reading".into(),
            anchor: Anchor::new(TRACK, snapshot, occurrence, [0, 3]).unwrap(),
            replacement: replacement.into(),
            mapping: false,
        }
    }
    fn tap(
        snapshot: &Snapshot,
        occurrence: usize,
        range: [usize; 2],
        start: i64,
        id: &str,
    ) -> Edit {
        Edit::Timing {
            id: id.into(),
            anchor: Anchor::new(TRACK, snapshot, occurrence, range).unwrap(),
            interval: Interval {
                start_ms: start,
                end_ms: Some(start + 500),
            },
            displayed_at_annotation: "old reading".into(),
            conversion_signature: "old-converter".into(),
        }
    }
    fn word(range: [usize; 2]) -> Word {
        Word {
            raw_span: Some(range),
            normalized_span: Some(range),
            output_span: [0, 3],
            hiragana_span: None,
            expected_text: None,
            constituent_nodes: vec![range],
            override_id: None,
            mapping_status: "mapped".into(),
            mapping_reason: None,
        }
    }
    fn convert(helper: &mut Romanizer, document: &Document, occurrence: usize) -> Response {
        let current = document.current();
        helper
            .convert(&Request {
                protocol_version: 1,
                request_id: document.revision,
                track_id: TRACK.into(),
                snapshot_id: current.snapshot.id.clone(),
                occurrence_id: occurrence,
                override_revision: document.revision,
                expected_conversion_signature: helper.signature.clone(),
                raw_line: current.snapshot.occurrences[occurrence].raw_line.clone(),
                overrides: current.overrides(TRACK, occurrence),
            })
            .unwrap()
    }

    #[test]
    fn golden_text_identity_excludes_clocks_metadata_and_normalization() {
        let first = song();
        assert_eq!(
            first.text_fingerprint,
            "5353e874dd051ef9f20e0175f2c4eec89cafe02108885131f6e1266190575476"
        );
        let second = import("[ar:other]\n[00:15][01:35]桜\n[01:45]", "different.lrc").unwrap();
        assert_eq!(first.text_fingerprint, second.text_fingerprint);
        assert_ne!(first.id, second.id);
        assert_ne!(
            import("ｶﾞ", "x").unwrap().text_fingerprint,
            import("ガ", "x").unwrap().text_fingerprint
        );
    }

    #[test]
    fn reattaching_an_edit_cannot_silently_overwrite_a_different_local_record() {
        let snapshot = import("[00:01]桜 を", "collision.lrc").unwrap();
        let mut document = Document::new(TRACK, snapshot.clone()).unwrap();
        let mut first = reading(&snapshot, 0, "sakura");
        if let Edit::Reading { id, .. } = &mut first {
            *id = "first".into();
        }
        document.save_edit(first).unwrap();
        let second = Edit::Reading {
            id: "second".into(),
            anchor: Anchor::new(TRACK, &snapshot, 0, [4, 7]).unwrap(),
            replacement: "o".into(),
            mapping: false,
        };
        document.save_edit(second.clone()).unwrap();
        let before = document.clone();
        let mut moved = second;
        *moved.anchor_mut() = Anchor::new(TRACK, &snapshot, 0, [0, 3]).unwrap();
        assert!(document.save_edit(moved).is_err());
        assert_eq!(document, before);
        assert_eq!(document.current().edits.len(), 2);
    }
    #[test]
    fn repeated_readings_share_one_record_but_taps_remain_independent() {
        let mut document = Document::new(TRACK, song()).unwrap();
        document
            .save_edit(reading(&document.current().snapshot, 0, "sakura tree"))
            .unwrap();
        let mut edited_repeat = reading(&document.current().snapshot, 1, "new reading");
        if let Edit::Reading { id, .. } = &mut edited_repeat {
            *id = "new-id".into();
        }
        document.save_edit(edited_repeat).unwrap();
        assert_eq!(document.current().edits.len(), 1);
        assert_eq!(document.current().overrides(TRACK, 0)[0].id, "reading");
        assert_eq!(
            document.current().overrides(TRACK, 1)[0].replacement,
            "new reading"
        );
        document
            .save_edit(tap(
                &document.current().snapshot,
                0,
                [0, 3],
                11_500,
                "tap-first",
            ))
            .unwrap();
        document
            .save_edit(tap(
                &document.current().snapshot,
                1,
                [0, 3],
                89_500,
                "tap-repeat",
            ))
            .unwrap();
        let words = vec![word([0, 3])];
        assert_eq!(
            document
                .current()
                .manual_timing(TRACK, 0, &words[0], &words)
                .unwrap()
                .start_ms,
            11_500
        );
        assert_eq!(
            document
                .current()
                .manual_timing(TRACK, 1, &words[0], &words)
                .unwrap()
                .start_ms,
            89_500
        );
    }
    #[test]
    fn changed_grouping_or_projection_is_pending_without_dropping_old_times() {
        let mut document = Document::new(TRACK, import("[00:12]食べた", "x").unwrap()).unwrap();
        let edit = tap(&document.current().snapshot, 0, [0, 9], 11_500, "tap");
        document.save_edit(edit.clone()).unwrap();
        let exact = vec![word([0, 9])];
        assert!(
            document
                .current()
                .pending_timings(TRACK, &[(0, exact.clone())])
                .is_empty()
        );
        let split = vec![word([0, 6]), word([6, 9])];
        assert_eq!(
            document
                .current()
                .pending_timings(TRACK, &[(0, split.clone())]),
            ["tap"]
        );
        assert!(
            document
                .current()
                .manual_timing(TRACK, 0, &split[0], &split)
                .is_none()
        );
        let mut ambiguous = vec![word([0, 9])];
        ambiguous[0].mapping_status = "needs_review".into();
        assert_eq!(
            document.current().pending_timings(TRACK, &[(0, ambiguous)]),
            ["tap"]
        );
        assert_eq!(document.current().edits[0], edit);
        assert!(document.current().pending_timings(TRACK, &[]).is_empty()); // Still converting is not a failed mapping.
    }
    #[test]
    fn refresh_only_proposes_and_switching_retains_old_bundles_and_pending_records() {
        let original = song();
        let mut document = Document::new(TRACK, original.clone()).unwrap();
        document.save_edit(reading(&original, 0, "sakura")).unwrap();
        document
            .save_edit(tap(&original, 0, [0, 3], 11_500, "tap"))
            .unwrap();
        let saved = document.current().clone();
        document
            .offer(import("[00:13][01:31]桜\n[01:41]", "new.lrc").unwrap())
            .unwrap();
        assert_eq!(*document.current(), saved);
        document.use_candidate().unwrap();
        assert_eq!(document.current().overrides(TRACK, 1).len(), 1);
        assert_eq!(document.current().edits, saved.edits);
        document
            .offer(import("[00:13]別の歌詞", "other.lrc").unwrap())
            .unwrap();
        document.use_candidate().unwrap();
        assert!(document.current().overrides(TRACK, 0).is_empty());
        assert_eq!(document.current().pending_timings(TRACK, &[]), ["tap"]);
        assert_eq!(document.current().edits, saved.edits);
        let removed = document.discard("tap").unwrap();
        document.restore(removed).unwrap();
        document.offer(original).unwrap();
        document.use_candidate().unwrap();
        assert_eq!(*document.current(), saved);
    }
    #[test]
    fn full_mapping_group_displaces_overlapping_edits_for_visible_review() {
        let snapshot = import("[00:12]桜 花", "x").unwrap();
        let mut document = Document::new(TRACK, snapshot.clone()).unwrap();
        document.save_edit(reading(&snapshot, 0, "sakura")).unwrap();
        let mut group = Edit::Reading {
            id: "group".into(),
            anchor: Anchor::new(TRACK, &snapshot, 0, [0, 7]).unwrap(),
            replacement: "sakura hana".into(),
            mapping: false,
        };
        assert!(document.save_edit(group.clone()).is_err());
        assert_eq!(document.current().edits.len(), 1);
        if let Edit::Reading { mapping, .. } = &mut group {
            *mapping = true;
        }
        document.save_edit(group).unwrap();
        assert_eq!(document.current().overrides(TRACK, 0).len(), 1);
        assert_eq!(
            document.current().edits[0]
                .anchor()
                .review_reason
                .as_deref(),
            Some("replaced_by_mapping")
        );
        assert_eq!(document.current().edits.len(), 2);
    }
    #[test]
    fn correction_restart_and_cache_clear_keep_atomic_word_timing_and_neighbors() {
        let snapshot = import(
            "[00:12]<00:12>桜 <00:13>を<00:14>\n[01:30]<01:30>桜 <01:31>を<01:32>",
            "test.lrc",
        )
        .unwrap();
        let mut document = Document::new(TRACK, snapshot).unwrap();
        document.delay_ms = 500;
        document
            .save_edit(reading(
                &document.current().snapshot,
                0,
                "new spaced reading",
            ))
            .unwrap();
        document
            .save_edit(tap(&document.current().snapshot, 0, [0, 3], 11_500, "tap"))
            .unwrap();
        let folder = std::env::temp_dir().join(format!("romaji-study-test-{}", std::process::id()));
        std::fs::create_dir_all(&folder).unwrap();
        let cache = folder.join("cache");
        std::fs::create_dir_all(&cache).unwrap();
        document.save(&folder.join("state")).unwrap();
        std::fs::remove_dir_all(cache).unwrap();
        let restored = Document::load(&folder.join("state"), TRACK)
            .unwrap()
            .unwrap();
        assert_eq!(document, restored);
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut command = Command::new(root.join(".venv/bin/python"));
        command.arg(root.join("romanizer/romanizer.py"));
        let mut helper = Romanizer::start(&mut command).unwrap();
        for occurrence in [0, 1] {
            let output = convert(&mut helper, &restored, occurrence);
            assert_eq!(output.romaji, "new spaced reading o");
            assert_eq!(output.words.len(), 2);
            assert_eq!(output.words[0].raw_span, Some([0, 3]));
            assert_eq!(output.words[1].raw_span, Some([4, 7]));
            let supplied = super::super::timing::WordTiming::supplied(
                [0, 3],
                &restored.current().snapshot.occurrences[occurrence].fragments,
            );
            let manual = restored.current().manual_timing(
                TRACK,
                occurrence,
                &output.words[0],
                &output.words,
            );
            assert_eq!(manual.is_some(), occurrence == 0);
            let effective = super::super::timing::WordTiming::effective(supplied, manual).unwrap();
            assert!(effective.active(if occurrence == 0 { 12_000 } else { 90_500 }, 500, None));
            assert!(
                super::super::timing::WordTiming::supplied(
                    [4, 7],
                    &restored.current().snapshot.occurrences[occurrence].fragments
                )
                .is_some()
            );
            assert!(
                restored
                    .current()
                    .pending_timings(TRACK, &[(occurrence, output.words.clone())])
                    .is_empty()
            );
        }
        std::fs::remove_dir_all(folder).unwrap();
    }
    #[test]
    fn attachment_previews_scope_without_mutating_and_keeps_old_tap_times() {
        let original = song();
        let mut document = Document::new(TRACK, original.clone()).unwrap();
        document
            .save_edit(reading(&original, 0, "spaced reading"))
            .unwrap();
        document
            .save_edit(tap(&original, 0, [0, 3], 11_500, "tap"))
            .unwrap();
        document
            .offer(import("[00:20][01:40]花", "new.lrc").unwrap())
            .unwrap();
        document.use_candidate().unwrap();
        assert_eq!(document.needs_review(&[]).len(), 2);
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut command = Command::new(root.join(".venv/bin/python"));
        command.arg(root.join("romanizer/romanizer.py"));
        let mut helper = Romanizer::start(&mut command).unwrap();
        let output = convert(&mut helper, &document, 1);
        let before = document.clone();
        let timing = document.attachment_preview("tap", &output, 0).unwrap();
        assert_eq!(timing.affected_occurrences, [1]);
        if let Edit::Timing { interval, .. } = &timing.edit {
            assert_eq!(interval.start_ms, 11_500);
        } else {
            panic!("expected tap");
        }
        let reading = document.attachment_preview("reading", &output, 0).unwrap();
        assert_eq!(reading.affected_occurrences, [0, 1]);
        assert_eq!(document, before);
        document.save_edit(timing.edit).unwrap();
        assert!(document.attachment_preview("reading", &output, 0).is_err()); // Confirmation changed revision.
        let current = convert(&mut helper, &document, 1);
        document
            .save_edit(
                document
                    .attachment_preview("reading", &current, 0)
                    .unwrap()
                    .edit,
            )
            .unwrap();
        assert!(document.needs_review(&[]).is_empty());
        assert_eq!(
            document.current().overrides(TRACK, 0)[0].replacement,
            "spaced reading"
        );
    }
    #[test]
    fn invalid_anchors_readings_and_paths_do_not_mutate_or_delete_saved_data() {
        let snapshot = song();
        assert!(Anchor::new(TRACK, &snapshot, 0, [1, 3]).is_err());
        assert!(Anchor::new(TRACK, &snapshot, 2, [0, 1]).is_err());
        let mut document = Document::new(TRACK, snapshot.clone()).unwrap();
        for replacement in ["", " ... ", "\nword", "word\n"] {
            assert!(
                document
                    .save_edit(reading(&snapshot, 0, replacement))
                    .is_err()
            );
            assert!(document.current().edits.is_empty());
        }
        document
            .save_edit(reading(&snapshot, 0, " spaced reading "))
            .unwrap();
        assert_eq!(
            document.current().overrides(TRACK, 0)[0].replacement,
            "spaced reading"
        );
        assert!(Document::new("../elsewhere", snapshot).is_err());
        assert!(Document::load(Path::new("/not-used"), "../../a").is_err());
        assert!(valid_reading("spaced reading!"));
    }
}
