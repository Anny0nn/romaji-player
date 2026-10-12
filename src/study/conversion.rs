//! Persistent, bounded helper protocol. All offsets are UTF-8 byte offsets.
use std::io::{BufRead, BufReader, Read, Write};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;

use anyhow::{Result, anyhow, bail};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

const LIMIT: usize = 65_536;
const TIMEOUT: Duration = Duration::from_secs(5);

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
impl Response {
    pub fn validate(&self, request: &Request) -> Result<()> {
        if self.protocol_version != 1
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
        for word in &self.words {
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
                    .take((LIMIT + 1) as u64)
                    .read_until(b'\n', &mut line);
                if result.is_err() || line.is_empty() {
                    return;
                }
                let result = if line.len() > LIMIT {
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
        let hello =
            helper.exchange(&json!({"protocol_version":1,"request_id":0,"command":"hello"}))?;
        if hello.get("protocol_version") != Some(&json!(1))
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
        if bytes.len() >= LIMIT {
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
            protocol_version: 1,
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
