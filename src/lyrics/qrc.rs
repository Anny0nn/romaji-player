//! Source-owned QRC token clocks; no interpolation or cross-source timing joins.
use crate::study::{
    snapshot::{Occurrence, Snapshot, Source, SuppliedReading},
    timing::{Fragment, Interval},
};
use anyhow::{Result, anyhow, bail};
use scraper::{Html, Selector};

pub(super) fn kana(text: &str) -> String {
    text.chars()
        .map(|c| {
            if ('ァ'..='ヶ').contains(&c) {
                char::from_u32(c as u32 - 0x60).unwrap()
            } else {
                c
            }
        })
        .collect()
}

pub fn parse(xml: &str, payload: &str, candidate: &str, duration_ms: u32) -> Result<Snapshot> {
    if xml.len() > 1_048_576 || duration_ms == 0 {
        bail!("invalid QRC size or recording duration");
    }
    // HTML attributes retain literal newlines, unlike XML attribute normalization.
    let html = Html::parse_fragment(xml);
    let selector = Selector::parse("[lyriccontent]").unwrap();
    let found: Vec<_> = html.select(&selector).collect();
    if found.len() != 1 {
        bail!("QRC needs exactly one lyric content attribute");
    }
    let body = found[0].value().attr("lyriccontent").unwrap();
    let limit = i64::from(duration_ms) + 5_000;
    let mut occurrences = Vec::new();
    let mut warnings = Vec::new();
    let mut kana_track = None;
    for raw in body.lines() {
        if let Some(k) = raw.strip_prefix("[kana:").and_then(|s| s.strip_suffix(']')) {
            if kana_track.replace(k).is_some() {
                bail!("duplicate QRC kana track");
            }
            continue;
        }
        if !raw.starts_with('[') {
            if !raw.trim().is_empty() {
                bail!("invalid QRC line");
            }
            continue;
        }
        let (header, body) = raw[1..]
            .split_once(']')
            .ok_or_else(|| anyhow!("unclosed QRC line"))?;
        if header.chars().next().is_none_or(|c| !c.is_ascii_digit()) {
            continue;
        }
        let (start, duration) = clock(header)?;
        let end = start
            .checked_add(duration)
            .ok_or_else(|| anyhow!("QRC clock overflow"))?;
        if end > limit || start < 0 {
            bail!("QRC line outside the recording");
        }
        let mut text = String::new();
        let mut fragments = Vec::new();
        let mut at = 0;
        let mut token_start = 0;
        let mut last_end = start;
        let mut bad_timing = false;
        while let Some(relative) = body[at..].find('(') {
            let open = at + relative;
            let Some(relative_end) = body[open + 1..].find(')') else {
                break;
            };
            let close = open + 1 + relative_end;
            let inside = &body[open + 1..close];
            if !inside
                .chars()
                .next()
                .is_some_and(|c| c.is_ascii_digit() || c == '-')
            {
                at = open + 1;
                continue;
            }
            let (t, d) = clock(inside)?;
            let e = t
                .checked_add(d)
                .ok_or_else(|| anyhow!("QRC token overflow"))?;
            let piece = &body[token_start..open];
            let begin = text.len();
            text.push_str(piece);
            if !piece.is_empty() && d > 0 {
                if t < start || e > end || t < last_end {
                    bad_timing = true;
                }
                fragments.push(Fragment {
                    raw_span: [begin, text.len()],
                    interval: Interval {
                        start_ms: t,
                        end_ms: Some(e),
                    },
                    source: "QQ Music QRC".into(),
                });
                if !piece.trim().is_empty() {
                    last_end = e;
                }
            }
            token_start = close + 1;
            at = close + 1;
        }
        if token_start == 0 || !body[token_start..].is_empty() {
            bail!("QRC line has untimed or malformed trailing text");
        }
        if bad_timing {
            fragments.clear();
            warnings.push(
                "Some QRC token clocks overlap or escape their line; those lines need TIFA timing."
                    .into(),
            );
        }
        occurrences.push(Occurrence {
            id: occurrences.len(),
            raw_line: text,
            start_ms: Some(start),
            fragments,
        });
    }
    if occurrences.is_empty() {
        bail!("QRC contains no timed lyric lines");
    }
    let readings = match kana_track {
        Some(k) => match counted_kana(k, &occurrences) {
            Ok(r) => r,
            Err(_) => {
                warnings.push("QQ kana could not be mapped completely; dictionary and saved readings are retained.".into());
                Vec::new()
            }
        },
        None => Vec::new(),
    };
    warnings.sort();
    warnings.dedup();
    Snapshot::new(
        Source {
            imported: false,
            provider: "QQ Music".into(),
            candidate: candidate.into(),
            payload: payload.into(),
            warnings,
            readings,
            derivation: None,
        },
        occurrences,
    )
}
fn clock(s: &str) -> Result<(i64, i64)> {
    let (a, b) = s
        .split_once(',')
        .ok_or_else(|| anyhow!("invalid QRC clock"))?;
    if a.is_empty() || b.is_empty() || !a.bytes().chain(b.bytes()).all(|c| c.is_ascii_digit()) {
        bail!("invalid QRC clock");
    }
    Ok((a.parse()?, b.parse()?))
}
fn kanji(c: char) -> bool {
    matches!(c,'㐀'..='䶿'|'一'..='鿿'|'豈'..='﫿')
}
fn counted_kana(track: &str, lines: &[Occurrence]) -> Result<Vec<SuppliedReading>> {
    let bases: Vec<_> = lines
        .iter()
        .flat_map(|l| {
            l.raw_line
                .char_indices()
                .filter(|(_, c)| kanji(*c))
                .map(move |(at, c)| (l.id, at, at + c.len_utf8()))
        })
        .collect();
    let mut rest = track;
    let mut cursor: usize = 0;
    let mut out = Vec::new();
    while !rest.is_empty() {
        let cover = rest.as_bytes()[0];
        if !cover.is_ascii_digit() {
            bail!("invalid counted kana");
        }
        let cover = usize::from(cover - b'0');
        rest = &rest[1..];
        let mut reading = String::new();
        while !rest.is_empty() && !rest.as_bytes()[0].is_ascii_digit() {
            if let Some(t) = rest.strip_prefix('(') {
                let (c, r) = t
                    .split_once(')')
                    .ok_or_else(|| anyhow!("unclosed kana clock"))?;
                clock(c)?;
                rest = r;
            } else {
                let c = rest.chars().next().unwrap();
                reading.push(c);
                rest = &rest[c.len_utf8()..];
            }
        }
        let end = cursor
            .checked_add(cover)
            .ok_or_else(|| anyhow!("kana coverage overflow"))?;
        if end > bases.len() {
            bail!("kana coverage differs from written source");
        }
        let kana = kana(&reading);
        if cover > 0 && crate::study::conversion::valid_hiragana(&kana) {
            let (id, a, _) = bases[cursor];
            let (last, _, b) = bases[end - 1];
            if id == last && lines[id].raw_line[a..b].chars().all(kanji) {
                out.push(SuppliedReading {
                    raw_line: lines[id].raw_line.clone(),
                    raw_span: [a, b],
                    expected_text: lines[id].raw_line[a..b].into(),
                    hiragana: kana,
                });
            }
        }
        cursor = end;
    }
    if cursor != bases.len() {
        bail!("incomplete kana coverage");
    }
    // Repeated equal text shares readings; conflicting occurrences abstain.
    let mut unique = Vec::new();
    for r in &out {
        if out.iter().any(|other| {
            other.raw_line == r.raw_line
                && other.raw_span == r.raw_span
                && other.hiragana != r.hiragana
        }) {
            continue;
        }
        if !unique.contains(r) {
            unique.push(r.clone());
        }
    }
    Ok(unique)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn xml(body: &str) -> String {
        format!("<QrcInfos><Lyric_1 LyricContent=\"{body}\"/></QrcInfos>")
    }
    #[test]
    fn preserves_utf8_gaps_and_withholds_zero_duration() {
        let s = parse(
            &xml("[100,900]空(100,200) (300,0)花(600,200)"),
            "fixture",
            "song",
            2000,
        )
        .unwrap();
        let l = &s.occurrences[0];
        assert_eq!(l.raw_line, "空 花");
        assert_eq!(l.fragments.len(), 2);
        assert_eq!(l.fragments[1].raw_span, [4, 7]);
        assert_eq!(l.fragments[0].interval.end_ms, Some(300));
        assert!(crate::study::timing::WordTiming::supplied([0, 7], &l.fragments).is_none());
        assert_eq!(
            crate::study::timing::WordTiming::supplied([4, 7], &l.fragments)
                .unwrap()
                .intervals[0]
                .start_ms,
            600
        );
    }
    #[test]
    fn parses_literal_parentheses_entities_and_real_newlines() {
        let s = parse(
            &xml("[0,100]A &amp; B ((0,100)\n[200,100]花(200,100)"),
            "fixture",
            "x",
            2000,
        )
        .unwrap();
        assert_eq!(s.occurrences[0].raw_line, "A & B (");
        assert_eq!(s.occurrences.len(), 2);
    }
    #[test]
    fn rejects_bad_clocks_and_drops_overlapping_line_timing() {
        for bad in [
            "[0,100]花(0,-1)",
            "[0,100]花(0,100)tail",
            "[0,100]花(0,100",
            "[0,999999]花(0,1)",
        ] {
            assert!(parse(&xml(bad), "fixture", "x", 2000).is_err());
        }
        let s = parse(&xml("[0,1000]空(0,600)花(500,100)"), "fixture", "x", 2000).unwrap();
        assert!(s.occurrences[0].fragments.is_empty());
    }
    #[test]
    fn counted_kana_is_all_or_nothing_and_preserves_repeats() {
        let body =
            "[kana:1そら1はな1そら1はな]\n[0,100]空(0,50)花(50,50)\n[200,100]空(200,50)花(250,50)";
        let s = parse(&xml(body), "fixture", "x", 2000).unwrap();
        assert_eq!(s.source.readings.len(), 2);
        assert_eq!(s.source.readings[0].raw_span, [0, 3]);
        let s = parse(
            &xml(&body.replace("1そら1はな1そら1はな", "1そら1はな")),
            "fixture",
            "x",
            2000,
        )
        .unwrap();
        assert!(s.source.readings.is_empty());
        assert!(!s.source.warnings.is_empty());
    }
}
