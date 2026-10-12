//! Lossless lyric text extraction; inline clocks are supplied data, never guessed.
use anyhow::{Result, bail};

use super::snapshot::{Occurrence, Snapshot, Source};
use super::timing::{Fragment, Interval};

/// Keep the complete Spotify answer, including unknown fine-timing fields.
/// Until a fine-timing schema is verified, it is retained rather than guessed.
pub fn spotify(json: &serde_json::Value) -> Result<Snapshot> {
    let lyrics = json
        .get("lyrics")
        .ok_or_else(|| anyhow::anyhow!("missing lyrics"))?;
    let sync = lyrics.get("syncType").and_then(serde_json::Value::as_str);
    let timed = matches!(sync, Some("LINE_SYNCED" | "SYLLABLE_SYNCED"));
    let lines = lyrics
        .get("lines")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| anyhow::anyhow!("missing lyric lines"))?;
    let mut warnings = Vec::new();
    let mut occurrences = Vec::new();
    for line in lines {
        let raw = line
            .get("words")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| anyhow::anyhow!("invalid lyric text"))?;
        let start = line
            .get("startTimeMs")
            .and_then(|value| {
                value
                    .as_str()
                    .and_then(|value| value.parse().ok())
                    .or_else(|| value.as_i64())
            })
            .filter(|_| timed);
        if line
            .get("syllables")
            .and_then(serde_json::Value::as_array)
            .is_some_and(|items| !items.is_empty())
        {
            warnings.push("Spotify includes unverified finer timing; retained in the source, not counted as word coverage.".into());
        }
        occurrences.push(Occurrence {
            id: occurrences.len(),
            raw_line: raw.into(),
            start_ms: start,
            fragments: Vec::new(),
        });
    }
    warnings.sort();
    warnings.dedup();
    Snapshot::new(
        Source {
            derivation: None,
            imported: false,
            provider: "Spotify".into(),
            candidate: lyrics
                .get("providerDisplayName")
                .and_then(serde_json::Value::as_str)
                .unwrap_or("Spotify lyrics")
                .into(),
            payload: serde_json::to_string(json)?,
            warnings,
        },
        occurrences,
    )
}

pub fn lrclib(payload: &serde_json::Value, text: &str) -> Result<Snapshot> {
    let imported = import(text, "LRCLIB")?;
    let title = payload
        .get("trackName")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("");
    let artist = payload
        .get("artistName")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("");
    let album = payload
        .get("albumName")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("");
    let duration = payload
        .get("duration")
        .and_then(serde_json::Value::as_f64)
        .unwrap_or(0.0);
    Snapshot::new(
        Source {
            derivation: None,
            imported: false,
            provider: "LRCLIB".into(),
            candidate: format!("{artist} — {title} · {album} · {duration:.1}s"),
            payload: serde_json::to_string(payload)?,
            warnings: imported.source.warnings,
        },
        imported.occurrences,
    )
}

#[cfg(test)]
mod provider_tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn spotify_preserves_blank_events_unicode_and_unknown_fine_fields() {
        let payload = json!({"lyrics":{"syncType":"LINE_SYNCED","providerDisplayName":"Fixture","lines":[
            {"startTimeMs":"12000","words":"  ｶﾞ 食べた  ","syllables":[{"unverified":true}]},
            {"startTimeMs":"14000","words":""},
            {"startTimeMs":"15000","words":"  ｶﾞ 食べた  "}
        ]},"futureField":{"retained":true}});
        let snapshot = spotify(&payload).unwrap();
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(&snapshot.source.payload).unwrap(),
            payload
        );
        assert_eq!(snapshot.occurrences[0].raw_line, "  ｶﾞ 食べた  ");
        assert_eq!(snapshot.occurrences[1].raw_line, "");
        assert_eq!(snapshot.occurrences[1].start_ms, Some(14000));
        assert!(
            snapshot
                .occurrences
                .iter()
                .all(|line| line.fragments.is_empty())
        );
        assert_eq!(snapshot.source.warnings.len(), 1);
    }

    #[test]
    fn lrclib_retains_provider_record_and_exact_imported_cues() {
        let payload = json!({"id":123,"trackName":"Fixture","artistName":"Artist","albumName":"Album","duration":200,"syncedLyrics":"[offset:500]\n[00:12]<00:12>桜<00:13>","unknown":42});
        let snapshot = lrclib(&payload, payload["syncedLyrics"].as_str().unwrap()).unwrap();
        assert!(!snapshot.source.imported);
        assert!(snapshot.source.candidate.contains("200.0s"));
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(&snapshot.source.payload).unwrap(),
            payload
        );
        assert_eq!(
            snapshot.occurrences[0].fragments[0].interval,
            Interval {
                start_ms: 12500,
                end_ms: Some(13500)
            }
        );
    }
}

/// LRC import convention: a positive header offset moves all cues later.
/// Preserve negative lyric times; only eventual playback seeks are clamped.
pub fn import(payload: &str, filename: &str) -> Result<Snapshot> {
    if payload.len() > 1_048_576 {
        bail!("lyrics file exceeds 1 MiB");
    }
    let original_payload = payload;
    let payload = payload.strip_prefix('\u{feff}').unwrap_or(payload);
    let mut offset = None;
    for raw in payload.lines() {
        if let Some(value) = raw
            .trim()
            .strip_prefix("[offset:")
            .and_then(|text| text.strip_suffix(']'))
        {
            let parsed: i64 = value
                .trim()
                .parse()
                .map_err(|_| anyhow::anyhow!("invalid LRC offset"))?;
            if offset.is_some_and(|previous| previous != parsed) {
                bail!("conflicting LRC offsets");
            }
            offset = Some(parsed);
        }
    }
    let offset = offset.unwrap_or(0);
    let mut occurrences = Vec::new();
    let mut warnings = Vec::new();
    for (file_line, raw) in payload.lines().enumerate() {
        let mut rest = raw.trim_start();
        let mut times = Vec::new();
        let mut metadata = false;
        while let Some(inner) = rest.strip_prefix('[') {
            let end = inner
                .find(']')
                .ok_or_else(|| anyhow::anyhow!("unclosed LRC tag on line {}", file_line + 1))?;
            let tag = &inner[..end];
            if tag.as_bytes().first().is_some_and(u8::is_ascii_digit) {
                times.push(timestamp(tag)?);
                rest = &inner[end + 1..];
            } else if times.is_empty()
                && tag.split_once(':').is_some_and(|(key, _)| {
                    !key.is_empty() && key.bytes().all(|byte| byte.is_ascii_alphabetic())
                })
            {
                metadata = true;
                rest = &inner[end + 1..];
                if rest.trim().is_empty() {
                    break;
                }
            } else {
                break;
            }
        }
        if times.is_empty() {
            if metadata && rest.trim().is_empty() {
                continue;
            }
            // Untimed text is retained, including blank gap lines. An inline tag
            // without a line tag still supplies its own genuine word clock.
            let (text, fragments) = inline(if metadata { rest } else { raw }, offset, file_line)?;
            occurrences.push(Occurrence {
                id: occurrences.len(),
                raw_line: text,
                start_ms: None,
                fragments,
            });
        } else {
            let (text, fragments) = inline(rest, offset, file_line)?;
            let ambiguous = times.len() > 1 && !fragments.is_empty();
            if ambiguous {
                warnings.push(format!("Line {}: repeated line tags with absolute inline timing need separate timed lines; word timing withheld.", file_line + 1));
            }
            for time in times {
                occurrences.push(Occurrence {
                    id: occurrences.len(),
                    raw_line: text.clone(),
                    start_ms: Some(shift(time, offset)?),
                    fragments: if ambiguous {
                        Vec::new()
                    } else {
                        fragments.clone()
                    },
                });
            }
        }
    }
    if occurrences
        .iter()
        .all(|line| line.raw_line.trim().is_empty())
    {
        bail!("lyrics file has no text");
    }
    Snapshot::new(
        Source {
            derivation: None,
            imported: true,
            provider: "import".into(),
            candidate: filename.into(),
            payload: original_payload.into(),
            warnings,
        },
        occurrences,
    )
}

fn shift(time: i64, offset: i64) -> Result<i64> {
    time.checked_add(offset)
        .ok_or_else(|| anyhow::anyhow!("lyric timestamp overflows"))
}

fn timestamp(tag: &str) -> Result<i64> {
    let (minutes, seconds) = tag
        .split_once(':')
        .ok_or_else(|| anyhow::anyhow!("invalid lyric timestamp"))?;
    let split = seconds.split_once(['.', ':']);
    if split.is_some_and(|(_, fraction)| fraction.is_empty()) {
        bail!("empty timestamp fraction");
    }
    let (seconds, fraction) = split.unwrap_or((seconds, ""));
    if minutes.is_empty()
        || seconds.is_empty()
        || !minutes.bytes().all(|b| b.is_ascii_digit())
        || !seconds.bytes().all(|b| b.is_ascii_digit())
        || !fraction.bytes().all(|b| b.is_ascii_digit())
    {
        bail!("invalid lyric timestamp");
    }
    let minutes: i64 = minutes.parse()?;
    let seconds: i64 = seconds.parse()?;
    if seconds >= 60 {
        bail!("lyric seconds must be below 60");
    }
    let fraction: i64 = if fraction.is_empty() {
        0
    } else {
        fraction
            .chars()
            .take(3)
            .collect::<String>()
            .parse::<i64>()?
            * 10_i64.pow(3 - fraction.len().min(3) as u32)
    };
    minutes
        .checked_mul(60_000)
        .and_then(|time| {
            seconds
                .checked_mul(1_000)
                .and_then(|part| time.checked_add(part))
        })
        .and_then(|time| time.checked_add(fraction))
        .ok_or_else(|| anyhow::anyhow!("lyric timestamp overflows"))
}

fn inline(body: &str, offset: i64, file_line: usize) -> Result<(String, Vec<Fragment>)> {
    let mut text = String::new();
    let mut marks = Vec::new();
    let mut rest = body;
    while let Some(start) = rest.find('<') {
        text.push_str(&rest[..start]);
        let tag = &rest[start + 1..];
        if !tag.as_bytes().first().is_some_and(u8::is_ascii_digit) {
            text.push('<');
            rest = tag;
            continue;
        }
        let end = tag
            .find('>')
            .ok_or_else(|| anyhow::anyhow!("unclosed inline timestamp"))?;
        let time = shift(timestamp(&tag[..end])?, offset)?;
        marks.push((text.len(), time));
        rest = &tag[end + 1..];
    }
    text.push_str(rest);
    let mut fragments = Vec::new();
    for (index, (start, time)) in marks.iter().copied().enumerate() {
        let next = marks.get(index + 1).copied();
        let end = next.map_or(text.len(), |(end, _)| end);
        if start == end {
            continue;
        } // A trailing empty tag supplies the previous end.
        let original = &text[start..end];
        let trimmed = original.trim();
        if trimmed.is_empty() {
            continue;
        }
        if next.is_some_and(|(_, next_time)| next_time <= time) {
            bail!("non-increasing inline timestamp on line {}", file_line + 1);
        }
        // A next word's start bounds selection but is not a measured end.
        // Only an empty/blank marker explicitly closes the preceding segment.
        let end_ms = next.and_then(|(position, next_time)| {
            let following = marks
                .get(index + 2)
                .map_or(text.len(), |(position, _)| *position);
            text[position..following]
                .trim()
                .is_empty()
                .then_some(next_time)
        });
        let leading = original.len() - original.trim_start().len();
        let interval = Interval {
            start_ms: time,
            end_ms,
        };
        if !interval.valid() {
            bail!("non-increasing inline timestamp on line {}", file_line + 1);
        }
        fragments.push(Fragment {
            raw_span: [start + leading, start + leading + trimmed.len()],
            interval,
            source: format!("enhanced-lrc:line:{}:segment:{}", file_line + 1, index),
        });
    }
    Ok((text, fragments))
}

#[cfg(test)]
mod tests {
    use super::super::timing::WordTiming;
    use super::*;

    #[test]
    fn expands_before_sorting_and_keeps_blank_duplicate_events_and_source_bytes() {
        let snapshot = import(
            "[ar:fixture]\n[01:30.00][00:12.00] 桜 \n[00:12.00]\n[00:12.00]桜",
            "test.lrc",
        )
        .unwrap();
        assert_eq!(
            snapshot
                .occurrences
                .iter()
                .map(|line| (line.id, line.raw_line.as_str()))
                .collect::<Vec<_>>(),
            [(0, " 桜 "), (1, " 桜 "), (2, ""), (3, "桜")]
        );
        assert_eq!(snapshot.playback_order(), [1, 2, 3, 0]);
    }
    #[test]
    fn inline_kana_and_joined_nodes_exactly_cover_words_and_preserve_explicit_ends() {
        let snapshot = import(
            "[00:10]<00:10>さ<00:10.20>く<00:10.40>ら<00:11> <00:11.20>食べた<00:12>",
            "fine.lrc",
        )
        .unwrap();
        let line = &snapshot.occurrences[0];
        assert_eq!(line.raw_line, "さくら 食べた");
        assert_eq!(line.fragments.len(), 4);
        assert_eq!(line.fragments[0].interval.end_ms, None);
        assert_eq!(line.fragments[1].interval.end_ms, None);
        let first = WordTiming::supplied([0, 9], &line.fragments).unwrap();
        assert_eq!(first.intervals[2].end_ms, Some(11_000));
        assert!(WordTiming::supplied([10, 19], &line.fragments).is_some());
        assert!(!first.active(11_100, 0, Some(11_200)));
    }
    #[test]
    fn header_offset_changes_line_and_inline_times_once_and_keeps_negative_times() {
        let positive = import("[offset:500]\n[00:00]<00:00>桜<00:01>", "offset.lrc").unwrap();
        assert_eq!(positive.occurrences[0].start_ms, Some(500));
        assert_eq!(
            positive.occurrences[0].fragments[0].interval,
            Interval {
                start_ms: 500,
                end_ms: Some(1500)
            }
        );
        let negative = import("[offset:-500]\n[00:00]<00:00>桜", "negative.lrc").unwrap();
        assert_eq!(negative.occurrences[0].start_ms, Some(-500));
        assert_eq!(negative.occurrences[0].fragments[0].interval.end_ms, None);
        assert_eq!(positive.text_fingerprint, negative.text_fingerprint);
    }
    #[test]
    fn does_not_make_up_inline_clocks_for_repeated_outer_tags() {
        let snapshot = import("[00:10][00:30]<00:10>桜<00:11>", "ambiguous.lrc").unwrap();
        assert_eq!(snapshot.occurrences.len(), 2);
        assert!(
            snapshot
                .occurrences
                .iter()
                .all(|line| line.fragments.is_empty())
        );
        assert_eq!(snapshot.source.warnings.len(), 1);
        assert!(snapshot.source.payload.contains("<00:10>"));
    }
    #[test]
    fn plain_lyrics_and_start_only_inline_segments_keep_their_uncertainty() {
        let snapshot = import("桜\n\n<00:01>食べた", "plain.txt").unwrap();
        assert_eq!(snapshot.occurrences[1].raw_line, "");
        assert!(
            snapshot
                .occurrences
                .iter()
                .all(|line| line.start_ms.is_none())
        );
        assert_eq!(snapshot.occurrences[2].fragments[0].interval.end_ms, None);
    }
    #[test]
    fn empty_inline_markers_preserve_internal_silence_inside_one_displayed_word() {
        let snapshot = import("[00:10]<00:10>さ<00:11><00:12>く<00:13>", "gap.lrc").unwrap();
        let fragments = &snapshot.occurrences[0].fragments;
        assert_eq!(snapshot.occurrences[0].raw_line, "さく");
        let word = WordTiming::supplied([0, 6], fragments).unwrap();
        assert!(word.active(10_500, 0, None));
        assert!(!word.active(11_500, 0, None));
        assert!(word.active(12_500, 0, None));
        assert!(!word.active(13_000, 0, None));
    }
    #[test]
    fn preserves_plain_brackets_leading_whitespace_and_original_bom_payload() {
        let raw = "\u{feff}[ar:fixture]\n[Chorus] 桜\n  花";
        let snapshot = import(raw, "mixed.txt").unwrap();
        assert_eq!(snapshot.source.payload, raw);
        assert_eq!(snapshot.occurrences[0].raw_line, "[Chorus] 桜");
        assert_eq!(snapshot.occurrences[1].raw_line, "  花");
        assert!(import("[00:01.]桜", "bad.lrc").is_err());
    }
    #[test]
    fn rejects_bad_stamps_intervals_and_overflow_without_partial_import() {
        for raw in [
            "[00:60]桜",
            "[00:10] <00:12>桜<00:11>",
            "[99999999999999999:01]桜",
            "[00:00] <00:00桜",
            "[offset:5]\n[offset:6]\n桜",
            "[00:0x]桜",
        ] {
            assert!(import(raw, "bad.lrc").is_err(), "{raw}");
        }
        assert_eq!(timestamp("01:02.5").unwrap(), 62_500);
        assert_eq!(timestamp("01:02:50").unwrap(), 62_500);
        assert_eq!(timestamp("01:02.5009").unwrap(), 62_500);
    }
}
