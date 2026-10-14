//! Frozen reading-repair protocol. Python proposes; Rust admits and versions patches.
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};

use super::alignment::Request;
use super::conversion::{Override, Request as ConversionRequest, Response, Romanizer, span};
use super::snapshot::{Bundle, Derivation, ReadingRepair, Snapshot, TextRepair};

pub const RECIPE: &str = "sung-reading-v1";

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProtectedSpan {
    pub occurrence_id: usize,
    pub raw_span: [usize; 2],
}
#[derive(Serialize)]
struct Input<'a> {
    protocol_version: u32,
    track: &'a str,
    snapshot: &'a str,
    revision: u64,
    delay_ms: i64,
    model_sha256: &'a str,
    audio_sha256: &'a str,
    recipe: &'a str,
    requests: Vec<ConversionRequest>,
    protected: &'a [ProtectedSpan],
}
#[derive(Deserialize)]
pub struct Package {
    pub kind: String,
    pub protocol_version: u32,
    pub track: String,
    pub snapshot: String,
    pub revision: u64,
    pub delay_ms: i64,
    pub model_sha256: String,
    pub audio_sha256: String,
    pub recipe: String,
    pub readings: Vec<ReadingRepair>,
    pub text_repairs: Vec<TextRepair>,
}

fn overrides(output: &Response) -> Vec<Override> {
    output
        .words
        .iter()
        .filter_map(|word| {
            Some(Override {
                id: word.override_id.clone()?,
                kind: if word.override_id.as_ref()?.starts_with("automatic:") {
                    "mapping_kana"
                } else {
                    "mapping"
                }
                .into(),
                raw_span: word.raw_span?,
                expected_text: word.expected_text.clone()?,
                replacement: span(&output.romaji, &word.output_span)?.into(),
                hiragana: word
                    .override_id
                    .as_ref()?
                    .starts_with("automatic:")
                    .then(|| {
                        word.hiragana_span
                            .and_then(|s| span(&output.hiragana, &s))
                            .map(str::to_owned)
                    })
                    .flatten(),
            })
        })
        .collect()
}
fn conversion_request(request: &Request, output: &Response) -> ConversionRequest {
    ConversionRequest {
        protocol_version: crate::study::conversion::PROTOCOL,
        request_id: output.occurrence_id as u64 + 1,
        track_id: request.job.track.clone(),
        snapshot_id: request.source.id.clone(),
        occurrence_id: output.occurrence_id,
        override_revision: request.job.revision,
        expected_conversion_signature: output.conversion_signature.clone(),
        raw_line: request.source.occurrences[output.occurrence_id]
            .raw_line
            .clone(),
        overrides: overrides(output),
    }
}
pub fn write_input(request: &Request, path: &Path, model: &str, audio: &str) -> Result<()> {
    let input = Input {
        protocol_version: 1,
        track: &request.job.track,
        snapshot: &request.source.id,
        revision: request.job.revision,
        delay_ms: request.job.delay_ms,
        model_sha256: model,
        audio_sha256: audio,
        recipe: RECIPE,
        requests: request
            .converted
            .iter()
            .map(|output| conversion_request(request, output))
            .collect(),
        protected: &request.protected,
    };
    let bytes = serde_json::to_vec(&input)?;
    if bytes.len() > 8 * 1024 * 1024 {
        bail!("Reading repair input exceeds its limit.");
    }
    std::fs::write(path, bytes)?;
    Ok(())
}
fn complete_envelope(
    request: &Request,
    occurrence: usize,
    range: [usize; 2],
    expected: &str,
) -> bool {
    let Some(line) = request.source.occurrences.get(occurrence) else {
        return false;
    };
    let Some(output) = request
        .converted
        .iter()
        .find(|r| r.occurrence_id == occurrence)
    else {
        return false;
    };
    if span(&line.raw_line, &range) != Some(expected)
        || request.protected.iter().any(|p| {
            p.occurrence_id == occurrence && p.raw_span[0] < range[1] && p.raw_span[1] > range[0]
        })
    {
        return false;
    }
    let words: Vec<_> = output
        .words
        .iter()
        .filter(|word| {
            word.raw_span
                .is_some_and(|s| s[0] < range[1] && s[1] > range[0])
        })
        .collect();
    if words.is_empty()
        || words.len() > 4
        || words.first().and_then(|w| w.raw_span).map(|s| s[0]) != Some(range[0])
        || words.last().and_then(|w| w.raw_span).map(|s| s[1]) != Some(range[1])
    {
        return false;
    }
    let mut cursor = range[0];
    for word in words {
        let Some(s) = word.raw_span else {
            return false;
        };
        if word.mapping_status != "mapped"
            || word.override_id.is_some()
            || s[0] < cursor
            || s[1] > range[1]
            || !line
                .raw_line
                .get(cursor..s[0])
                .is_some_and(|gap| gap.chars().all(char::is_whitespace))
        {
            return false;
        }
        cursor = s[1];
    }
    true
}

/// Admit a whole package before reconstructing its display with the trusted converter.
/// No document or app data is changed here; fresh timing still has to succeed.
pub fn admit(
    request: &Request,
    package: Package,
    model: &str,
    audio: &str,
    helper: &mut Romanizer,
) -> Result<(Snapshot, Vec<Response>, usize)> {
    if package.kind != "repairs"
        || package.protocol_version != 1
        || package.track != request.job.track
        || package.snapshot != request.source.id
        || package.revision != request.job.revision
        || package.delay_ms != request.job.delay_ms
        || package.model_sha256 != model
        || package.audio_sha256 != audio
        || package.recipe != RECIPE
        || package.readings.len() + package.text_repairs.len() > 256
    {
        bail!("Stale or incompatible sung-reading evidence.");
    }
    let count = package.readings.len() + package.text_repairs.len();
    if count == 0 {
        return Ok((request.source.clone(), request.converted.clone(), 0));
    }
    let mut ranges: BTreeMap<String, Vec<[usize; 2]>> = BTreeMap::new();
    let mut keys = BTreeSet::new();
    for patch in &package.readings {
        if !complete_envelope(
            request,
            patch.occurrence_id,
            patch.raw_span,
            &patch.expected_text,
        ) || request.source.occurrences[patch.occurrence_id].raw_line != patch.raw_line
            || !keys.insert((&patch.raw_line, patch.raw_span))
        {
            bail!("Invalid or conflicting original-text reading envelope.");
        }
        // Shared corrections must preserve all identical occurrences, including edits.
        for line in request
            .source
            .occurrences
            .iter()
            .filter(|line| line.raw_line == patch.raw_line)
        {
            if !complete_envelope(request, line.id, patch.raw_span, &patch.expected_text) {
                bail!("A repeated reading would displace a saved correction.");
            }
        }
        ranges
            .entry(patch.raw_line.clone())
            .or_default()
            .push(patch.raw_span);
    }
    for patch in &package.text_repairs {
        if !complete_envelope(
            request,
            patch.occurrence_id,
            patch.original_span,
            &patch.expected_text,
        ) || request.source.occurrences[patch.occurrence_id].raw_line != patch.original_line
            || !super::conversion::valid_hiragana(&patch.expected_text)
            || !super::conversion::valid_hiragana(&patch.replacement)
            || patch.expected_text == patch.replacement
            || !patch.verification.transcript_supported
        {
            bail!("Ungrounded lyric text repair.");
        }
        // Exact text reattachment cannot be guaranteed on a line with existing edits.
        if request.protected.iter().any(|p| {
            request
                .source
                .occurrences
                .get(p.occurrence_id)
                .is_some_and(|line| line.raw_line == patch.original_line)
        }) || request
            .source
            .source
            .derivation
            .as_ref()
            .is_some_and(|d| d.readings.iter().any(|r| r.raw_line == patch.original_line))
        {
            bail!("Lyric text repair would move an existing correction.");
        }
        for line in request
            .source
            .occurrences
            .iter()
            .filter(|l| l.raw_line == patch.original_line)
        {
            if !complete_envelope(request, line.id, patch.original_span, &patch.expected_text) {
                bail!("A repeated text repair would displace a saved correction.");
            }
        }
        if request.source.source.derivation.as_ref().is_some_and(|d| {
            d.text_repairs
                .iter()
                .any(|p| p.result_line == patch.original_line)
        }) {
            bail!("A previous text repair must remain in its immutable source version.");
        }
        ranges
            .entry(patch.original_line.clone())
            .or_default()
            .push(patch.original_span);
    }
    for values in ranges.values_mut() {
        values.sort();
        if values.windows(2).any(|pair| pair[0][1] > pair[1][0]) {
            bail!("Overlapping automatic repairs.");
        }
    }
    let mut source = request.source.source.clone();
    let mut occurrences = request.source.occurrences.clone();
    // Reading and text changes on the same line are deliberately withheld by this recipe.
    if package.text_repairs.iter().any(|t| {
        package
            .readings
            .iter()
            .any(|r| r.raw_line == t.original_line)
    }) {
        bail!("Mixed reading/text repairs require an unambiguous new envelope.");
    }
    for line in &mut occurrences {
        let patches: Vec<_> = package
            .text_repairs
            .iter()
            .filter(|t| t.original_line == line.raw_line)
            .collect();
        if !patches.is_empty() {
            let original = line.raw_line.clone();
            let mut ordered = patches.clone();
            ordered.sort_by_key(|p| std::cmp::Reverse(p.original_span[0]));
            for patch in ordered {
                line.raw_line.replace_range(
                    patch.original_span[0]..patch.original_span[1],
                    &patch.replacement,
                );
            }
            if patches.iter().any(|p| p.result_line != line.raw_line) {
                bail!("Changed lyric repair result.");
            }
            line.fragments.clear();
            if line.raw_line == original {
                bail!("Empty lyric repair.");
            }
        } else {
            for patch in package
                .readings
                .iter()
                .filter(|p| p.raw_line == line.raw_line)
            {
                line.fragments.retain(|f| {
                    f.raw_span[0] >= patch.raw_span[1] || f.raw_span[1] <= patch.raw_span[0]
                });
            }
        }
    }
    let mut derived = Derivation {
        parent_snapshot: request.source.id.clone(),
        base_revision: request.job.revision,
        audio_sha256: audio.into(),
        model_sha256: model.into(),
        recipe: RECIPE.into(),
        readings: source
            .derivation
            .as_ref()
            .map(|d| d.readings.clone())
            .unwrap_or_default(),
        text_repairs: source
            .derivation
            .as_ref()
            .map(|d| d.text_repairs.clone())
            .unwrap_or_default(),
    };
    derived.readings.extend(package.readings);
    derived.text_repairs.extend(package.text_repairs);
    source.derivation = Some(derived);
    let snapshot = Snapshot::new(source, occurrences)?;
    let bundle = Bundle {
        snapshot: snapshot.clone(),
        pinned: true,
        edits: Vec::new(),
    };
    let converted = request
        .converted
        .iter()
        .map(|old| {
            let mut input = conversion_request(request, old);
            input.raw_line = snapshot.occurrences[old.occurrence_id].raw_line.clone();
            input.overrides.retain(|o| !o.id.starts_with("automatic:"));
            input
                .overrides
                .extend(bundle.overrides(&request.job.track, old.occurrence_id));
            if input.expected_conversion_signature != helper.signature {
                bail!("Converter changed during reading repair.");
            }
            let output = helper.convert(&input)?;
            if !output.pending_overrides.is_empty() {
                bail!("A sung-reading correction could not be mapped.");
            }
            Ok(output)
        })
        .collect::<Result<Vec<_>>>()?;
    Ok((snapshot, converted, count))
}

#[cfg(test)]
mod tests {
    use super::super::alignment::{Job, Method, Status};
    use super::super::snapshot::{AcousticView, ReadingVerification};
    use super::*;
    use std::sync::{Arc, Mutex, atomic::AtomicBool};
    fn fixture() -> (Request, Romanizer) {
        fixture_text("闇夜を歩く")
    }
    fn fixture_text(raw: &str) -> (Request, Romanizer) {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut command = std::process::Command::new(root.join(".venv/bin/python"));
        command.arg(root.join("romanizer/romanizer.py"));
        let mut helper = Romanizer::start(&mut command).unwrap();
        let source = super::super::source::import(
            &format!("[00:01.00]{raw}\n[00:05.00]{raw}"),
            "fixture.lrc",
        )
        .unwrap();
        let job = Job {
            method: Method::Experimental,
            track: "0000000000000000000000".into(),
            snapshot: source.id.clone(),
            revision: 2,
            delay_ms: 250,
            cancel: Arc::new(AtomicBool::new(false)),
            status: Arc::new(Mutex::new(Status::Running("test".into()))),
        };
        let mut request = Request {
            protected: vec![],
            job,
            source,
            converted: vec![],
        };
        for line in &request.source.occurrences {
            let input = ConversionRequest {
                protocol_version: crate::study::conversion::PROTOCOL,
                request_id: line.id as u64 + 1,
                track_id: request.job.track.clone(),
                snapshot_id: request.source.id.clone(),
                occurrence_id: line.id,
                override_revision: 2,
                expected_conversion_signature: helper.signature.clone(),
                raw_line: line.raw_line.clone(),
                overrides: vec![],
            };
            request.converted.push(helper.convert(&input).unwrap());
        }
        (request, helper)
    }
    fn package(request: &Request) -> Package {
        Package {
            kind: "repairs".into(),
            protocol_version: 1,
            track: request.job.track.clone(),
            snapshot: request.source.id.clone(),
            revision: 2,
            delay_ms: 250,
            model_sha256: "a".repeat(64),
            audio_sha256: "b".repeat(64),
            recipe: RECIPE.into(),
            readings: vec![ReadingRepair {
                occurrence_id: 0,
                raw_line: request.source.occurrences[0].raw_line.clone(),
                raw_span: [0, 6],
                expected_text: "闇夜".into(),
                hiragana: "やみよ".into(),
                romaji: "yamiyo".into(),
                views: vec![
                    AcousticView {
                        gain_milli: 20_000,
                        margin_milli: 12_000,
                        probability_ppm: 800_000,
                        context_ppm: 1_000_000
                    };
                    2
                ],
                verification: ReadingVerification {
                    gain_milli: 5_000,
                    margin_milli: 3_000,
                    phone_ratio_ppm: 1_500_000,
                    transcript_supported: false,
                },
            }],
            text_repairs: vec![],
        }
    }
    #[test]
    fn repaired_reading_reconverts_repeats_without_changing_source_text_or_clocks() {
        let (request, mut helper) = fixture();
        let (snapshot, output, count) = admit(
            &request,
            package(&request),
            &"a".repeat(64),
            &"b".repeat(64),
            &mut helper,
        )
        .unwrap();
        assert_eq!(count, 1);
        assert_eq!(snapshot.text_fingerprint, request.source.text_fingerprint);
        assert_ne!(snapshot.id, request.source.id);
        assert_eq!(snapshot.occurrences, request.source.occurrences);
        assert!(
            output
                .iter()
                .all(|r| r.hiragana.starts_with("やみよ") && r.romaji.starts_with("yamiyo"))
        );
        let reopened: Snapshot =
            serde_json::from_slice(&serde_json::to_vec(&snapshot).unwrap()).unwrap();
        reopened.validate().unwrap();
        assert_eq!(
            Bundle {
                snapshot: reopened,
                pinned: true,
                edits: vec![]
            }
            .overrides(&request.job.track, 1)[0]
                .hiragana
                .as_deref(),
            Some("やみよ")
        );
    }
    #[test]
    fn changed_offset_revision_audio_or_acoustics_rejects_the_whole_package() {
        let (request, mut helper) = fixture();
        for kind in 0..5 {
            let mut p = package(&request);
            match kind {
                0 => p.delay_ms = 0,
                1 => p.revision = 3,
                2 => p.audio_sha256 = "c".repeat(64),
                3 => p.readings[0].verification.margin_milli = -2001,
                _ => p.readings[0].views[0].probability_ppm = 449_999,
            };
            assert!(admit(&request, p, &"a".repeat(64), &"b".repeat(64), &mut helper).is_err());
        }
    }
    #[test]
    fn partial_word_overlap_and_a_protected_repeat_cannot_displace_edits() {
        let (mut request, mut helper) = fixture();
        let mut partial = package(&request);
        partial.readings[0].raw_span = [0, 3];
        partial.readings[0].expected_text = "闇".into();
        assert!(
            admit(
                &request,
                partial,
                &"a".repeat(64),
                &"b".repeat(64),
                &mut helper
            )
            .is_err()
        );
        let mut duplicate = package(&request);
        duplicate.readings.push(duplicate.readings[0].clone());
        assert!(
            admit(
                &request,
                duplicate,
                &"a".repeat(64),
                &"b".repeat(64),
                &mut helper
            )
            .is_err()
        );
        request.protected.push(ProtectedSpan {
            occurrence_id: 1,
            raw_span: [0, 6],
        });
        assert!(
            admit(
                &request,
                package(&request),
                &"a".repeat(64),
                &"b".repeat(64),
                &mut helper
            )
            .is_err()
        );
    }
    #[test]
    fn canonical_kana_and_display_romaji_must_agree() {
        let (request, mut helper) = fixture();
        let mut p = package(&request);
        p.readings[0].romaji = "anya".into();
        assert!(admit(&request, p, &"a".repeat(64), &"b".repeat(64), &mut helper).is_err());
    }
    #[test]
    fn kana_text_repair_versions_the_source_and_reconverts_identical_repeats() {
        let (request, mut helper) = fixture_text("あおい きみ よ");
        let mut p = package(&request);
        let reading = p.readings.remove(0);
        p.text_repairs.push(TextRepair {
            occurrence_id: 0,
            original_line: "あおい きみ よ".into(),
            original_span: [10, 16],
            expected_text: "きみ".into(),
            replacement: "ほし".into(),
            result_line: "あおい ほし よ".into(),
            result_span: [10, 16],
            views: reading.views,
            verification: ReadingVerification {
                transcript_supported: true,
                ..reading.verification
            },
        });
        let (snapshot, converted, count) =
            admit(&request, p, &"a".repeat(64), &"b".repeat(64), &mut helper).unwrap();
        assert_eq!(count, 1);
        assert_ne!(snapshot.text_fingerprint, request.source.text_fingerprint);
        assert_eq!(snapshot.source.payload, request.source.source.payload);
        assert!(
            snapshot
                .occurrences
                .iter()
                .all(|r| r.raw_line == "あおい ほし よ")
        );
        assert!(converted.iter().all(|r| r.romaji.contains("hoshi")));
    }
}
