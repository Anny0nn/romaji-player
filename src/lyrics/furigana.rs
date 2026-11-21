//! Explicit UtaTen ruby, joined by exact text (whitespace only is ignored).
use super::qrc::kana;
use crate::study::snapshot::{Snapshot, SuppliedReading};
use anyhow::{Result, anyhow, bail};
use scraper::{ElementRef, Html, Node, Selector};

#[derive(Debug)]
pub struct Page {
    title: String,
    artist: String,
    text: String,
    readings: Vec<([usize; 2], String)>,
}
fn sel(s: &str) -> Selector {
    Selector::parse(s).unwrap()
}
fn walk(element: ElementRef<'_>, text: &mut String, readings: &mut Vec<([usize; 2], String)>) {
    for child in element.children() {
        match child.value() {
            Node::Text(t) => text.push_str(t),
            Node::Element(e) => {
                let el = ElementRef::wrap(child).unwrap();
                if e.name() == "br" {
                    text.push('\n');
                } else if e.has_class("ruby", scraper::CaseSensitivity::CaseSensitive) {
                    let rb: Vec<_> = el.select(&sel(".rb")).collect();
                    let rt: Vec<_> = el.select(&sel(".rt")).collect();
                    if rb.len() == 1 && rt.len() == 1 {
                        let written = rb[0].text().collect::<String>();
                        let reading = kana(&rt[0].text().collect::<String>());
                        let at = text.len();
                        text.push_str(&written);
                        if crate::study::conversion::valid_hiragana(&reading) {
                            readings.push(([at, text.len()], reading));
                        }
                    }
                } else {
                    walk(el, text, readings);
                }
            }
            _ => {}
        }
    }
}
pub(super) fn parse_page(html: &str) -> Result<Page> {
    if html.len() > 1_048_576 {
        bail!("invalid furigana page size or identity");
    }
    let doc = Html::parse_document(html);
    let title_node = doc
        .select(&sel("h2.newLyricTitle__main"))
        .next()
        .ok_or_else(|| anyhow!("missing furigana song title"))?;
    let page_title = title_node
        .children()
        .filter_map(|n| {
            if let Node::Text(t) = n.value() {
                Some::<&str>(t)
            } else {
                None
            }
        })
        .collect::<String>();
    let page_artist = doc
        .select(&sel("h3 a[href^='/artist/lyric/']"))
        .next()
        .ok_or_else(|| anyhow!("missing furigana artist"))?
        .text()
        .collect::<String>();
    let bodies: Vec<_> = doc.select(&sel(".lyricBody .hiragana")).collect();
    if bodies.len() != 1 {
        bail!("expected one hiragana lyric body");
    }
    let mut text = String::new();
    let mut readings = Vec::new();
    walk(bodies[0], &mut text, &mut readings);
    Ok(Page {
        title: page_title,
        artist: page_artist,
        text,
        readings,
    })
}
impl Page {
    pub(super) fn matches(&self, title: &str, artist: &str) -> bool {
        let title = super::karaoke::normalized(&super::clean_title(title));
        let artist = super::karaoke::normalized(artist);
        !title.is_empty()
            && !artist.is_empty()
            && super::karaoke::normalized(&super::clean_title(&self.title)) == title
            && super::artists::matches(&self.artist, &artist)
    }
}
pub fn parse(html: &str, title: &str, artist: &str) -> Result<Page> {
    let page = parse_page(html)?;
    if !page.matches(title, artist) {
        bail!("furigana page is for another song");
    }
    Ok(page)
}
pub(super) fn search_links(html: &str) -> Result<Vec<String>> {
    let found = links(html);
    // An empty/interstitial page is not evidence that readings do not exist.
    // Leave the optional lookup retryable rather than persisting a false miss.
    if found.is_empty() {
        bail!("Furigana search returned no verifiable results; retry later.");
    }
    Ok(found)
}

fn compact(s: &str) -> String {
    s.chars().filter(|c| !c.is_whitespace()).collect()
}
pub fn enrich(snapshot: &Snapshot, page: &Page, url: &str, html: &str) -> Result<Snapshot> {
    let full = compact(&page.text);
    let ruby: Vec<_> = page
        .readings
        .iter()
        .map(|(span, k)| {
            (
                [
                    compact(&page.text[..span[0]]).len(),
                    compact(&page.text[..span[1]]).len(),
                ],
                k,
            )
        })
        .collect();
    let mut readings = Vec::new();
    for line in &snapshot.occurrences {
        let needle = compact(&line.raw_line);
        if needle.is_empty() {
            continue;
        }
        let mut mapping = Vec::new();
        let mut pos = 0;
        for (raw, c) in line
            .raw_line
            .char_indices()
            .filter(|(_, c)| !c.is_whitespace())
        {
            let end = pos + c.len_utf8();
            mapping.push((pos, end, raw, raw + c.len_utf8()));
            pos = end;
        }
        let mut variants = Vec::new();
        for start in full
            .char_indices()
            .filter_map(|(at, _)| full[at..].starts_with(&needle).then_some(at))
        {
            let mut local = Vec::new();
            for (span, k) in &ruby {
                if span[0] < start || span[1] > start + needle.len() {
                    continue;
                }
                let a = mapping.iter().find(|m| m.0 == span[0] - start).map(|m| m.2);
                let b = mapping.iter().find(|m| m.1 == span[1] - start).map(|m| m.3);
                if let (Some(a), Some(b)) = (a, b) {
                    local.push(SuppliedReading {
                        raw_line: line.raw_line.clone(),
                        raw_span: [a, b],
                        expected_text: line.raw_line[a..b].into(),
                        hiragana: (*k).clone(),
                    });
                }
            }
            variants.push(local);
        }
        if let Some(first) = variants.first()
            && variants.iter().all(|v| v == first)
        {
            for r in first {
                if !readings.contains(r) {
                    readings.push(r.clone());
                }
            }
        }
    }
    if readings.is_empty() {
        return Ok(snapshot.clone());
    }
    let mut source = snapshot.source.clone();
    source.readings.retain(|old| {
        !readings.iter().any(|r| {
            r.raw_line == old.raw_line
                && r.raw_span[0] < old.raw_span[1]
                && old.raw_span[0] < r.raw_span[1]
        })
    });
    source.readings.extend(readings);
    source.payload = serde_json::to_string(
        &serde_json::json!({"qq":serde_json::from_str::<serde_json::Value>(&source.payload).unwrap_or_else(|_|serde_json::Value::String(source.payload.clone())),"utaten":{"url":url,"html":html}}),
    )?;
    source.provider = "QQ Music + UtaTen".into();
    Snapshot::new(source, snapshot.occurrences.clone())
}
pub(super) fn links(html: &str) -> Vec<String> {
    let doc = Html::parse_document(html);
    let mut out = Vec::new();
    for n in doc.select(&sel("a[href]")) {
        if let Some(path) = n.value().attr("href")
            && let Some(id) = path
                .strip_prefix("/lyric/")
                .and_then(|s| s.strip_suffix('/'))
            && !id.is_empty()
            && id.bytes().all(|b| b.is_ascii_alphanumeric())
            && !out.iter().any(|p| p == path)
        {
            out.push(path.to_string());
        }
        if out.len() == 3 {
            break;
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    fn page(body: &str) -> String {
        format!(
            "<h2 class='newLyricTitle__main'>Fixture<span>歌詞</span></h2><h3><a href='/artist/lyric/1'>Artist</a></h3><div class='lyricBody'><div class='hiragana'>{body}</div><div class='romaji'>ignored</div></div>"
        )
    }
    fn snapshot(text: &str) -> Snapshot {
        crate::study::source::import(text, "fixture").unwrap()
    }
    #[test]
    fn explicit_ruby_maps_utf8_across_lines_with_only_whitespace_changes() {
        let html = page(
            "青い<span class='ruby'><span class='rb'>地球</span><span class='rt'>ほし</span></span><br>にありがとう",
        );
        let p = parse(&html, "Fixture", "Artist").unwrap();
        let s = enrich(
            &snapshot("青い 地球 にありがとう"),
            &p,
            "https://utaten.com/lyric/fixture/",
            &html,
        )
        .unwrap();
        assert_eq!(s.source.readings[0].raw_span, [7, 13]);
        assert_eq!(s.source.readings[0].hiragana, "ほし");
        let doc = crate::study::snapshot::Document::new("0ODOmKxO0CKv4DzoP3HHIC", s).unwrap();
        let json = serde_json::to_vec(&doc).unwrap();
        let saved: crate::study::snapshot::Document = serde_json::from_slice(&json).unwrap();
        saved.validate().unwrap();
        assert_eq!(saved.current().snapshot.source.readings.len(), 1);
    }
    #[test]
    fn page_identity_accepts_a_verified_artist_alias_but_not_other_performers() {
        let html = page("空").replace("Artist</a>", "鈴木雅之</a>");
        assert!(parse(&html, "Fixture", "Masayuki Suzuki").is_ok());
        assert!(parse(&html, "Fixture", "CHEMISTRY").is_err());
        assert!(parse(&html, "Other", "Masayuki Suzuki").is_err());
    }
    #[test]
    fn rejects_other_songs_and_abstains_on_conflicting_repeats() {
        let html = page(
            "<span class='ruby'><span class='rb'>花</span><span class='rt'>はな</span></span><br><span class='ruby'><span class='rb'>花</span><span class='rt'>か</span></span>",
        );
        assert!(parse(&html, "Other", "Artist").is_err());
        assert!(parse(&html, "Fixt", "Artist").is_err());
        assert!(parse(&html, "Fixture", " ").is_err());
        let p = parse(&html, "Fixture", "Artist").unwrap();
        assert!(
            enrich(&snapshot("花"), &p, "url", &html)
                .unwrap()
                .source
                .readings
                .is_empty()
        );
    }
    #[test]
    fn overlapping_repeat_matches_cannot_choose_a_reading_by_first_match() {
        let html = page(
            "<span class='ruby'><span class='rb'>花</span><span class='rt'>はな</span></span><span class='ruby'><span class='rb'>花</span><span class='rt'>か</span></span><span class='ruby'><span class='rb'>花</span><span class='rt'>はな</span></span>",
        );
        let p = parse(&html, "Fixture", "Artist").unwrap();
        assert!(
            enrich(&snapshot("花花"), &p, "url", &html)
                .unwrap()
                .source
                .readings
                .is_empty()
        );
    }
    #[test]
    fn empty_and_interstitial_search_pages_remain_retryable() {
        for html in [
            "",
            "<html>Temporarily unavailable</html>",
            "<a href='/help/'>Help</a>",
        ] {
            assert!(search_links(html).is_err());
        }
        assert_eq!(
            search_links("<a href='/lyric/fixture/'>Result</a>").unwrap(),
            vec!["/lyric/fixture/"]
        );
    }
    #[test]
    fn discovery_accepts_only_local_lyric_ids() {
        assert_eq!(
            links(
                "<a href='https://evil.test/lyric/x/'>x</a><a href='/lyric/x/?q=1'>x</a><a href='/lyric/x/'>x</a><a href='/lyric/x/'>x</a><a href='/lyric/../'>x</a>"
            ),
            vec!["/lyric/x/"]
        );
    }
}
