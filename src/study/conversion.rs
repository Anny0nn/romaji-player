//! Persistent, bounded helper protocol. All offsets are UTF-8 byte offsets.
use std::io::{BufRead, BufReader, Read, Write};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;

use anyhow::{Result, anyhow, bail};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

const REQUEST_LIMIT: usize = 65_536;
// Protocol-2 source groups expand a short transcript into rich word records.
const REPLY_LIMIT: usize = 1024 * 1024;
const TIMEOUT: Duration = Duration::from_secs(5);
pub const PROTOCOL: u32 = 2;
pub const REPRESENTATION: &str = "source-reading-v1";

#[derive(Clone, Debug, Default, Deserialize)]
pub struct Reading {
    pub written: Option<String>,
    pub romaji: String,
    pub alignment_text: String,
    pub pronunciation: Option<String>,
    pub origin: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Override {
    pub id: String,
    pub kind: String,
    pub raw_span: [usize; 2],
    pub expected_text: String,
    pub replacement: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hiragana: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReadingCandidate {
    pub hiragana: String,
    pub romaji: String,
}
#[derive(Clone, Debug, Deserialize)]
pub struct CandidateGroup {
    pub raw_span: [usize; 2],
    pub expected_text: String,
    pub candidates: Vec<ReadingCandidate>,
}
pub fn valid_hiragana(text: &str) -> bool {
    !text.is_empty()
        && text.len() <= 512
        && text.trim() == text
        && !text.contains("  ")
        && text
            .chars()
            .all(|ch| ('ぁ'..='ゖ').contains(&ch) || ch == 'ー' || ch == ' ')
}
#[derive(Clone, Debug, Serialize)]
pub struct Request {
    pub protocol_version: u32,
    pub request_id: u64,
    pub track_id: String,
    pub snapshot_id: String,
    pub occurrence_id: usize,
    pub override_revision: u64,
    pub expected_conversion_signature: String,
    pub raw_line: String,
    pub overrides: Vec<Override>,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Word {
    pub raw_span: Option<[usize; 2]>,
    pub normalized_span: Option<[usize; 2]>,
    pub output_span: [usize; 2],
    #[serde(default)]
    pub hiragana_span: Option<[usize; 2]>,
    pub katakana_span: Option<[usize; 2]>,
    pub reading: Reading,
    pub expected_text: Option<String>,
    pub constituent_nodes: Vec<[usize; 2]>,
    pub override_id: Option<String>,
    pub mapping_status: String,
    pub mapping_reason: Option<String>,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Pending {
    pub id: String,
    pub reason: String,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Response {
    pub protocol_version: u32,
    pub request_id: u64,
    pub track_id: String,
    pub snapshot_id: String,
    pub occurrence_id: usize,
    pub override_revision: u64,
    pub conversion_signature: String,
    pub normalized_line: String,
    pub romaji: String,
    #[serde(default)]
    pub hiragana: String,
    pub katakana: String,
    pub representation: String,
    pub words: Vec<Word>,
    pub boundary_associations: Vec<[usize; 2]>,
    pub applied_override_ids: Vec<String>,
    pub pending_overrides: Vec<Pending>,
    #[serde(default)]
    pub reading_candidates: Vec<CandidateGroup>,
}
pub fn span<'a>(text: &'a str, range: &[usize; 2]) -> Option<&'a str> {
    (range[0] < range[1])
        .then(|| text.get(range[0]..range[1]))
        .flatten()
}
pub fn katakana(text: &str) -> String {
    text.chars()
        .map(|ch| {
            if ('ぁ'..='ゖ').contains(&ch) || matches!(ch, 'ゝ' | 'ゞ') {
                char::from_u32(ch as u32 + 0x60).unwrap()
            } else {
                ch
            }
        })
        .collect()
}
impl Response {
    pub fn display_text<'a>(&'a self, raw: &'a str, mode: super::LyricMode) -> &'a str {
        match mode {
            super::LyricMode::Romaji | super::LyricMode::Both => &self.romaji,
            super::LyricMode::Hiragana => &self.hiragana,
            super::LyricMode::Katakana => &self.katakana,
            super::LyricMode::Japanese => raw,
        }
    }
    pub fn display_spans(&self, raw: &str, mode: super::LyricMode) -> Vec<Option<[usize; 2]>> {
        let mut end = 0;
        let exact_original = self.words.iter().all(|word| {
            let Some(range) = word.raw_span else {
                return false;
            };
            let valid = word.expected_text.is_some()
                && range[0] >= end
                && span(raw, &range) == word.expected_text.as_deref();
            end = range[1];
            valid
        });
        self.words
            .iter()
            .map(|word| match mode {
                super::LyricMode::Romaji | super::LyricMode::Both => Some(word.output_span),
                super::LyricMode::Hiragana => word.hiragana_span,
                super::LyricMode::Katakana => word.katakana_span,
                super::LyricMode::Japanese => exact_original.then_some(word.raw_span).flatten(),
            })
            .collect()
    }
    pub fn validate(&self, request: &Request) -> Result<()> {
        if self.protocol_version != PROTOCOL
            || request.protocol_version != PROTOCOL
            || self.representation != REPRESENTATION
            || self.katakana != katakana(&self.hiragana)
            || self.request_id != request.request_id
            || self.track_id != request.track_id
            || self.snapshot_id != request.snapshot_id
            || self.occurrence_id != request.occurrence_id
            || self.override_revision != request.override_revision
            || self.conversion_signature != request.expected_conversion_signature
        {
            bail!("stale or incompatible romanizer response");
        }
        let mut previous_end = 0;
        let mut previous_hiragana_end = 0;
        let mut previous_katakana_end = 0;
        for word in &self.words {
            let kana = word
                .hiragana_span
                .and_then(|range| span(&self.hiragana, &range));
            let kata = word
                .katakana_span
                .and_then(|range| span(&self.katakana, &range));
            if kana.is_none()
                || kata.is_none()
                || word
                    .katakana_span
                    .is_some_and(|range| range[0] < previous_katakana_end)
                || kata != kana.map(katakana).as_deref()
                || kana != Some(word.reading.written.as_deref().unwrap_or("？"))
                || !["dictionary", "saved", "song", "source", "unavailable"]
                    .contains(&word.reading.origin.as_str())
                || word
                    .reading
                    .pronunciation
                    .as_ref()
                    .is_some_and(|pronunciation| {
                        word.reading.origin != "dictionary" || !valid_hiragana(pronunciation)
                    })
                || word.reading.written.is_none() != (word.reading.origin == "unavailable")
            {
                bail!("invalid selected reading or katakana span");
            }
            previous_katakana_end = word.katakana_span.unwrap()[1];
            if word.hiragana_span.is_some_and(|range| {
                span(&self.hiragana, &range).is_none() || range[0] < previous_hiragana_end
            }) {
                bail!("Invalid hiragana output span");
            }
            if let Some(range) = word.hiragana_span {
                previous_hiragana_end = range[1];
            }
            if span(&self.romaji, &word.output_span).is_none() || word.output_span[0] < previous_end
            {
                bail!("invalid romanizer output span");
            }
            previous_end = word.output_span[1];
            let selected = word
                .reading
                .written
                .as_deref()
                .filter(|text| !text.contains('？'))
                .unwrap_or(word.expected_text.as_deref().unwrap_or(""));
            if span(&self.romaji, &word.output_span) != Some(word.reading.romaji.as_str())
                || word.reading.alignment_text
                    != selected
                        .chars()
                        .filter(|c| c.is_alphanumeric())
                        .collect::<String>()
            {
                bail!("alignment target differs from selected reading");
            }
            match word.raw_span {
                Some(range)
                    if word.expected_text.is_some()
                        && span(&request.raw_line, &range) == word.expected_text.as_deref()
                        && word.mapping_status == "mapped" => {}
                None if word.mapping_status == "needs_review" && word.expected_text.is_none() => {}
                _ => bail!("invalid romanizer raw anchor"),
            }
            if word
                .normalized_span
                .is_some_and(|range| span(&self.normalized_line, &range).is_none())
                || word
                    .constituent_nodes
                    .iter()
                    .any(|range| span(&self.normalized_line, range).is_none())
            {
                bail!("invalid romanizer normalized span");
            }
        }
        for [raw, normalized] in &self.boundary_associations {
            if *raw > request.raw_line.len()
                || !request.raw_line.is_char_boundary(*raw)
                || *normalized > self.normalized_line.len()
                || !self.normalized_line.is_char_boundary(*normalized)
            {
                bail!("invalid romanizer boundary association");
            }
        }
        let mut accounted = std::collections::HashSet::new();
        for id in self
            .applied_override_ids
            .iter()
            .chain(self.pending_overrides.iter().map(|pending| &pending.id))
        {
            if !accounted.insert(id) || !request.overrides.iter().any(|item| &item.id == id) {
                bail!("invalid romanizer override identity");
            }
        }
        if accounted.len() != request.overrides.len() {
            bail!("romanizer omitted a saved override");
        }
        for id in &self.applied_override_ids {
            let edit = request
                .overrides
                .iter()
                .find(|item| &item.id == id)
                .ok_or_else(|| anyhow!("unknown applied override"))?;
            let matches: Vec<_> = self
                .words
                .iter()
                .filter(|word| word.override_id.as_ref() == Some(id))
                .collect();
            if matches.len() != 1
                || matches[0].raw_span != Some(edit.raw_span)
                || span(&self.romaji, &matches[0].output_span) != Some(edit.replacement.trim())
                || edit.hiragana.as_ref().is_some_and(|kana| {
                    matches[0]
                        .hiragana_span
                        .and_then(|range| span(&self.hiragana, &range))
                        != Some(kana.as_str())
                })
            {
                bail!("invalid romanizer reading correction");
            }
        }
        if self.words.iter().any(|word| {
            word.override_id
                .as_ref()
                .is_some_and(|id| !self.applied_override_ids.contains(id))
        }) {
            bail!("unknown word override");
        }
        let mut candidate_spans = std::collections::HashSet::new();
        for group in &self.reading_candidates {
            if !candidate_spans.insert(group.raw_span)
                || group.candidates.len() > 16
                || span(&request.raw_line, &group.raw_span) != Some(group.expected_text.as_str())
                || !self
                    .words
                    .iter()
                    .any(|word| word.raw_span == Some(group.raw_span) && word.override_id.is_none())
                || group.candidates.iter().any(|c| {
                    !valid_hiragana(&c.hiragana) || c.romaji.is_empty() || c.romaji.len() > 512
                })
            {
                bail!("invalid source-anchored reading candidates");
            }
        }
        if self
            .reading_candidates
            .iter()
            .map(|g| g.candidates.len())
            .sum::<usize>()
            > 192
        {
            bail!("too many reading candidates");
        }
        Ok(())
    }
}

// The writer is separate so a helper that stops reading cannot defeat the deadline.
struct WriteJob(Vec<u8>, mpsc::Sender<Result<()>>);
pub struct Romanizer {
    child: Child,
    input: mpsc::SyncSender<WriteJob>,
    output: mpsc::Receiver<Result<Value>>,
    pub signature: String,
}
impl Romanizer {
    /// Run on the background conversion worker, never the UI thread.
    pub fn start(command: &mut Command) -> Result<Self> {
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()?;
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| anyhow!("romanizer stdin unavailable"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow!("romanizer stdout unavailable"))?;
        let (input, jobs) = mpsc::sync_channel::<WriteJob>(1);
        std::thread::spawn(move || {
            while let Ok(WriteJob(bytes, reply)) = jobs.recv() {
                let result = stdin
                    .write_all(&bytes)
                    .and_then(|()| stdin.flush())
                    .map_err(|_| anyhow!("romanizer input closed"));
                let failed = result.is_err();
                let _ = reply.send(result);
                if failed {
                    break;
                }
            }
        });
        let (sender, output) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                let mut line = Vec::new();
                let result = reader
                    .by_ref()
                    .take((REPLY_LIMIT + 1) as u64)
                    .read_until(b'\n', &mut line);
                if result.is_err() || line.is_empty() {
                    return;
                }
                let result = if line.len() > REPLY_LIMIT {
                    Err(anyhow!("romanizer response exceeds limit"))
                } else {
                    serde_json::from_slice(&line).map_err(|_| anyhow!("invalid romanizer JSON"))
                };
                if sender.send(result).is_err() {
                    return;
                }
            }
        });
        let mut helper = Self {
            child,
            input,
            output,
            signature: String::new(),
        };
        let hello = helper
            .exchange(&json!({"protocol_version":PROTOCOL,"request_id":0,"command":"hello"}))?;
        if hello.get("protocol_version") != Some(&json!(PROTOCOL))
            || hello.get("request_id") != Some(&json!(0))
        {
            bail!("unsupported romanizer handshake");
        }
        helper.signature = hello
            .get("conversion_signature")
            .and_then(Value::as_str)
            .filter(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
            .ok_or_else(|| anyhow!("invalid romanizer signature"))?
            .to_owned();
        Ok(helper)
    }
    fn exchange(&mut self, request: &impl Serialize) -> Result<Value> {
        let mut bytes = serde_json::to_vec(request)?;
        if bytes.len() >= REQUEST_LIMIT {
            bail!("romanizer request exceeds limit");
        }
        bytes.push(b'\n');
        let (reply, written) = mpsc::channel();
        self.input
            .try_send(WriteJob(bytes, reply))
            .map_err(|_| anyhow!("romanizer stopped or busy"))?;
        match written.recv_timeout(TIMEOUT) {
            Ok(result) => result?,
            Err(_) => {
                let _ = self.child.kill();
                bail!("romanizer write timed out");
            }
        }
        match self.output.recv_timeout(TIMEOUT) {
            Ok(result) => result,
            Err(_) => {
                let _ = self.child.kill();
                bail!("romanizer response timed out");
            }
        }
    }
    pub fn convert(&mut self, request: &Request) -> Result<Response> {
        let value = self.exchange(request)?;
        let response: Response =
            serde_json::from_value(value).map_err(|_| anyhow!("romanizer rejected request"))?;
        response.validate(request)?;
        Ok(response)
    }
    pub fn candidates(&mut self, request: &Request) -> Result<Response> {
        let mut value = serde_json::to_value(request)?;
        value["command"] = json!("candidates");
        let response: Response = serde_json::from_value(self.exchange(&value)?)
            .map_err(|_| anyhow!("romanizer rejected candidate request"))?;
        response.validate(request)?;
        Ok(response)
    }
}
impl Drop for Romanizer {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;
    fn helper() -> Romanizer {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut command = Command::new(root.join(".venv/bin/python"));
        command.arg(root.join("romanizer/romanizer.py"));
        Romanizer::start(&mut command).unwrap()
    }
    fn fixture(helper: &Romanizer) -> Request {
        Request {
            protocol_version: crate::study::conversion::PROTOCOL,
            request_id: 1,
            track_id: "synthetic".into(),
            snapshot_id: "fixture".into(),
            occurrence_id: 0,
            override_revision: 0,
            expected_conversion_signature: helper.signature.clone(),
            raw_line: "ｶﾞ 食べた を".into(),
            overrides: Vec::new(),
        }
    }
    #[test]
    fn real_helper_preserves_raw_offsets_and_joined_words() {
        let mut helper = helper();
        let request = fixture(&helper);
        let response = helper.convert(&request).unwrap();
        assert_eq!(response.romaji, "ga tabeta o");
        assert_eq!(response.words[0].raw_span, Some([0, 6]));
        assert_eq!(response.words[1].raw_span, Some([7, 16]));
        assert_eq!(response.words[1].constituent_nodes.len(), 2);
        assert_eq!(response.words[2].raw_span, Some([17, 20]));
        assert_eq!(helper.convert(&request).unwrap().romaji, response.romaji);
    }

    #[test]
    fn expanded_word_records_fit_a_separate_reply_bound_without_losing_next_reply() {
        let mut helper = helper();
        let mut request = fixture(&helper);
        request.raw_line = vec!["word"; 200].join(" ");
        let value = helper.exchange(&request).unwrap();
        assert!(serde_json::to_vec(&value).unwrap().len() > REQUEST_LIMIT);
        let response: Response = serde_json::from_value(value).unwrap();
        response.validate(&request).unwrap();
        assert_eq!(response.words.len(), 200);
        request.request_id += 1;
        request.raw_line = "桜".into();
        assert_eq!(helper.convert(&request).unwrap().romaji, "sakura");
    }

    #[test]
    fn dotted_kana_preserves_exact_word_spans_in_every_script() {
        use super::super::LyricMode;
        let mut helper = helper();
        let mut request = fixture(&helper);
        request.raw_line = "ゲ・ン・カ・イを歌う".into();
        let response = helper.convert(&request).unwrap();
        let expected = ["ゲ", "ン", "カ", "イ", "を", "歌う"];
        assert_eq!(response.words.len(), expected.len());
        assert_eq!(
            response
                .words
                .iter()
                .map(|word| word.raw_span)
                .collect::<Vec<_>>(),
            [[0, 3], [6, 9], [12, 15], [18, 21], [21, 24], [24, 30]].map(Some)
        );
        assert_eq!(
            response.display_text(&request.raw_line, LyricMode::Japanese),
            request.raw_line
        );
        for (range, source) in response
            .display_spans(&request.raw_line, LyricMode::Japanese)
            .iter()
            .zip(expected)
        {
            assert_eq!(span(&request.raw_line, &range.unwrap()), Some(source));
        }
        for mode in [
            LyricMode::Romaji,
            LyricMode::Hiragana,
            LyricMode::Katakana,
            LyricMode::Japanese,
        ] {
            let text = response.display_text(&request.raw_line, mode);
            assert!(
                response
                    .display_spans(&request.raw_line, mode)
                    .iter()
                    .all(|range| { range.is_some_and(|range| span(text, &range).is_some()) })
            );
        }
    }

    #[test]
    fn ambiguous_gemination_retains_explicit_original_line_fallback() {
        use super::super::LyricMode;
        let mut helper = helper();
        let mut request = fixture(&helper);
        request.raw_line = "桜ぱっ と歌う".into();
        let response = helper.convert(&request).unwrap();
        assert!(response.words.iter().any(|word| word.raw_span.is_none()));
        assert!(response.words.iter().any(|word| word.raw_span.is_some()));
        assert_eq!(
            response.display_text(&request.raw_line, LyricMode::Japanese),
            request.raw_line
        );
        assert!(
            response
                .display_spans(&request.raw_line, LyricMode::Japanese)
                .iter()
                .all(Option::is_none)
        );
        for mode in [LyricMode::Romaji, LyricMode::Hiragana, LyricMode::Katakana] {
            let text = response.display_text(&request.raw_line, mode);
            assert!(
                response
                    .display_spans(&request.raw_line, mode)
                    .iter()
                    .all(|range| range.is_some_and(|range| span(text, &range).is_some()))
            );
        }
    }

    #[test]
    fn geminated_group_has_exact_source_and_both_display_spans() {
        let mut helper = helper();
        let mut request = fixture(&helper);
        request.raw_line = "桜ぱっと飛ぶ".into();
        let response = helper.convert(&request).unwrap();
        assert_eq!(response.romaji, "sakura patto tobu");
        let word = &response.words[1];
        assert_eq!(word.raw_span, Some([3, 12]));
        assert_eq!(word.expected_text.as_deref(), Some("ぱっと"));
        assert_eq!(span(&response.romaji, &word.output_span), Some("patto"));
        assert_eq!(
            span(&response.hiragana, &word.hiragana_span.unwrap()),
            Some("ぱっと")
        );
        assert_eq!(word.constituent_nodes, [[3, 9], [9, 12]]);
        assert_eq!(word.mapping_status, "mapped");
    }

    #[test]
    fn song_reading_default_passes_protocol_validation_and_preserves_saved_word_identity() {
        let mut helper = helper();
        let mut request = fixture(&helper);
        request.track_id = "1lTfD2M6UpJRWi3YLb8qb5".into();
        request.raw_line = "君は故郷を出た".into();
        let response = helper.convert(&request).unwrap();
        let word = response
            .words
            .iter()
            .find(|word| word.raw_span == Some([6, 12]))
            .unwrap();
        assert_eq!(span(&response.romaji, &word.output_span), Some("machi"));
        assert_eq!(
            span(&response.hiragana, &word.hiragana_span.unwrap()),
            Some("まち")
        );
        assert_eq!(word.expected_text.as_deref(), Some("故郷"));
        assert!(word.override_id.is_none());
        request.overrides.push(Override {
            id: "saved".into(),
            kind: "reading".into(),
            raw_span: [6, 12],
            expected_text: "故郷".into(),
            replacement: "furusato".into(),
            hiragana: None,
        });
        let edited = helper.convert(&request).unwrap();
        let word = edited
            .words
            .iter()
            .find(|word| word.raw_span == Some([6, 12]))
            .unwrap();
        assert_eq!(span(&edited.romaji, &word.output_span), Some("furusato"));
    }
    #[test]
    fn stale_results_and_invalid_unicode_boundaries_are_rejected() {
        let mut helper = helper();
        let request = fixture(&helper);
        let mut response = helper.convert(&request).unwrap();
        response.words[0].hiragana_span = Some([0, 1]);
        assert!(response.validate(&request).is_err());
        response = helper.convert(&request).unwrap();
        response.words[1].hiragana_span = response.words[0].hiragana_span;
        assert!(response.validate(&request).is_err());
        response = helper.convert(&request).unwrap();
        response.override_revision += 1;
        assert!(response.validate(&request).is_err());
        response.override_revision = 0;
        response.words[0].raw_span = Some([1, 6]);
        assert!(response.validate(&request).is_err());
    }
    #[test]
    fn spaced_correction_rebuilds_output_without_moving_source() {
        let mut helper = helper();
        let mut request = fixture(&helper);
        request.overrides.push(Override {
            id: "local".into(),
            kind: "reading".into(),
            raw_span: [7, 16],
            expected_text: "食べた".into(),
            replacement: "new reading".into(),
            hiragana: None,
        });
        let response = helper.convert(&request).unwrap();
        assert_eq!(response.romaji, "ga new reading o");
        assert_eq!(response.words[1].raw_span, Some([7, 16]));
        assert_eq!(
            span(&response.romaji, &response.words[1].output_span),
            Some("new reading")
        );
        assert_eq!(response.words[2].raw_span, Some([17, 20]));
    }
    #[test]
    fn original_script_preserves_spacing_and_a_spaced_correction_is_one_word() {
        use crate::study::LyricMode;
        let mut helper = helper();
        let mut request = fixture(&helper);
        request.raw_line = "  闇夜、行こう! ".into();
        request.overrides.push(Override {
            id: "sung".into(),
            kind: "mapping_kana".into(),
            raw_span: [2, 8],
            expected_text: "闇夜".into(),
            replacement: "yami yo".into(),
            hiragana: Some("やみ よ".into()),
        });
        let response = helper.convert(&request).unwrap();
        let japanese = response.display_spans(&request.raw_line, LyricMode::Japanese);
        let index = response
            .words
            .iter()
            .position(|word| word.override_id.as_deref() == Some("sung"))
            .unwrap();
        assert_eq!(
            response.display_text(&request.raw_line, LyricMode::Japanese),
            request.raw_line
        );
        assert_eq!(
            span(&request.raw_line, &japanese[index].unwrap()),
            Some("闇夜")
        );
        assert_eq!(
            span(
                &response.katakana,
                &response.words[index].katakana_span.unwrap()
            ),
            Some("ヤミ ヨ")
        );
        assert!(response.words[index].reading.pronunciation.is_none());
        let mut ambiguous = response.clone();
        ambiguous.words[index + 1].raw_span = ambiguous.words[index].raw_span;
        assert!(
            ambiguous
                .display_spans(&request.raw_line, LyricMode::Japanese)
                .iter()
                .all(Option::is_none)
        );
        assert!(
            ambiguous
                .display_spans(&request.raw_line, LyricMode::Romaji)
                .iter()
                .all(Option::is_some)
        );
    }
    #[test]
    fn inconsistent_reading_target_script_or_pronunciation_is_rejected() {
        let mut helper = helper();
        let request = fixture(&helper);
        let original = helper.convert(&request).unwrap();
        let mut response = original.clone();
        response.words[0].reading.alignment_text = "さくら".into();
        assert!(response.validate(&request).is_err());
        response = original.clone();
        response.words[0].katakana_span = Some([1, 3]);
        assert!(response.validate(&request).is_err());
        response = original.clone();
        response.words[0].reading.origin = "saved".into();
        response.words[0].reading.pronunciation = Some("とーきょー".into());
        assert!(response.validate(&request).is_err());
        response = original;
        response.protocol_version = 1;
        assert!(response.validate(&request).is_err());
    }
    #[test]
    fn missing_duplicated_or_misapplied_saved_overrides_are_rejected() {
        let mut helper = helper();
        let mut request = fixture(&helper);
        request.overrides.push(Override {
            id: "correction".into(),
            kind: "reading".into(),
            raw_span: [7, 16],
            expected_text: "食べた".into(),
            replacement: "new reading".into(),
            hiragana: None,
        });
        let valid = helper.convert(&request).unwrap();
        let mut omitted = valid.clone();
        omitted.applied_override_ids.clear();
        assert!(omitted.validate(&request).is_err());
        let mut duplicate = valid.clone();
        duplicate.applied_override_ids.push("correction".into());
        assert!(duplicate.validate(&request).is_err());
        let mut wrong_word = valid;
        wrong_word.words[1].raw_span = Some([17, 20]);
        wrong_word.words[1].expected_text = Some("を".into());
        assert!(wrong_word.validate(&request).is_err());
    }
}
