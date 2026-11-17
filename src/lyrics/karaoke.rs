//! Explicit, bounded supplied-source lookup. Results are candidates, never replacements.
use super::store::Store;
use super::{Line, Lyrics, Query};
use crate::study::snapshot::Snapshot;
use anyhow::{Result, anyhow, bail};
use serde_json::{Value, json};
use std::{path::Path, time::Duration};

const REFERER: &str = "https://y.qq.com/portal/player.html";
const LIMIT: usize = 1_048_576;
pub(super) fn normalized(s: &str) -> String {
    s.chars()
        .flat_map(char::to_lowercase)
        .filter(|c| c.is_alphanumeric())
        .collect()
}
#[derive(Clone, Debug)]
pub struct Candidate {
    pub mid: String,
    pub title: String,
    pub artist: String,
    pub album: String,
    pub duration_ms: u32,
}
pub fn select(payload: &Value, query: &Query) -> Vec<Candidate> {
    if query.duration_ms == 0
        || normalized(&query.title).is_empty()
        || normalized(&query.artist).is_empty()
    {
        return Vec::new();
    }
    let Some(items) = payload.pointer("/data/song/list").and_then(Value::as_array) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for item in items.iter().take(20) {
        let Some(mid) = item["songmid"].as_str().filter(|s| {
            !s.is_empty() && s.len() <= 64 && s.bytes().all(|b| b.is_ascii_alphanumeric())
        }) else {
            continue;
        };
        let Some(title) = item["songname"].as_str() else {
            continue;
        };
        let Some(seconds) = item["interval"]
            .as_u64()
            .and_then(|n| u32::try_from(n).ok())
            .and_then(|n| n.checked_mul(1000))
        else {
            continue;
        };
        let Some(singers) = item["singer"].as_array() else {
            continue;
        };
        let matched = singers
            .iter()
            .filter_map(|a| a["name"].as_str())
            .find(|s| normalized(s) == normalized(&query.artist));
        if seconds.abs_diff(query.duration_ms) > 3_000
            || matched.is_none()
            || normalized(&super::clean_title(title))
                != normalized(&super::clean_title(&query.title))
        {
            continue;
        }
        if out.iter().any(|c: &Candidate| c.mid == mid) {
            continue;
        }
        out.push(Candidate {
            mid: mid.into(),
            title: title.into(),
            artist: matched.unwrap().into(),
            album: item["albumname"].as_str().unwrap_or("").into(),
            duration_ms: seconds,
        });
    }
    out.sort_by_key(|c| c.duration_ms.abs_diff(query.duration_ms));
    out.truncate(3);
    out
}
async fn body<T>(
    store: &Store<'_>,
    request: reqwest::RequestBuilder,
    validate: impl Fn(&str) -> Result<T>,
) -> Result<T> {
    let (http, request) = request
        .timeout(Duration::from_secs(15))
        .header("User-Agent", "RomajiPlayer/0.12 supplied-lyrics")
        .build_split();
    let request = request?;
    let key = Store::request_key(&request)?;
    if let Some(cached) = store.response(&key)
        && let Ok(parsed) = validate(&cached)
    {
        return Ok(parsed);
    }
    let mut response = http.execute(request).await?.error_for_status()?;
    if response.content_length().is_some_and(|n| n > LIMIT as u64) {
        bail!("lyric response exceeds 1 MiB");
    }
    let mut out = Vec::new();
    while let Some(chunk) = response.chunk().await? {
        if chunk.len() > LIMIT - out.len() {
            bail!("lyric response exceeds 1 MiB");
        }
        out.extend_from_slice(&chunk);
    }
    let text = String::from_utf8(out)?;
    let parsed = validate(&text)?;
    store.save_response(&key, &text)?;
    Ok(parsed)
}
fn qq_response(text: &str) -> Result<Value> {
    let value: Value = serde_json::from_str(text)?;
    if value["code"].as_i64() != Some(0)
        || value
            .get("req")
            .is_some_and(|req| req["code"].as_i64() != Some(0))
    {
        bail!("The lyric source is temporarily unavailable; retry later.");
    }
    Ok(value)
}

pub fn from_response(response: &Value, candidate: &Candidate, query: &Query) -> Result<Snapshot> {
    if response["req"]["code"].as_i64() != Some(0)
        || response["req"]["data"]["qrc"].as_i64() != Some(1)
    {
        bail!("QQ has no karaoke timing for this candidate");
    }
    let cipher = response["req"]["data"]["lyric"]
        .as_str()
        .ok_or_else(|| anyhow!("missing QRC lyrics"))?;
    let xml = super::qq_des::decode(cipher)?;
    let payload = serde_json::to_string(
        &json!({"candidate":{"mid":candidate.mid,"title":candidate.title,"artist":candidate.artist,"album":candidate.album,"duration_ms":candidate.duration_ms},"query":{"title":query.title,"artist":query.artist,"duration_ms":query.duration_ms},"response":response}),
    )?;
    let mut snapshot = super::qrc::parse(
        &xml,
        &payload,
        &format!(
            "{} — {} · {} · {:.1}s",
            candidate.artist,
            candidate.title,
            candidate.album,
            f64::from(candidate.duration_ms) / 1000.0
        ),
        query.duration_ms,
    )?;
    snapshot.source.warnings.push("Match this lyric version to the playing recording before using it. Supplied clocks have not been acoustically verified.".into());
    Snapshot::new(snapshot.source, snapshot.occurrences)
}
async fn furigana(
    store: &Store<'_>,
    http: &reqwest::Client,
    snapshot: &Snapshot,
    c: &Candidate,
) -> Result<(Snapshot, bool)> {
    let links = body(
        store,
        http.get("https://utaten.com/lyric/search").query(&[
            ("sort", "popular_sort_asc"),
            ("artist_name", c.artist.as_str()),
            ("title", c.title.as_str()),
            ("beginning", ""),
            ("body", ""),
            ("lyricist", ""),
            ("composer", ""),
            ("sub_title", ""),
            ("tag", ""),
            ("show_artists", "1"),
        ]),
        super::furigana::search_links,
    )
    .await?;
    let mut complete = true;
    for path in links {
        let url = format!("https://utaten.com{path}");
        let page = body(store, http.get(&url), |html| {
            Ok((super::furigana::parse_page(html)?, html.to_owned()))
        })
        .await;
        let (page, html) = match page {
            Ok(page) => page,
            Err(_) => {
                complete = false;
                continue;
            }
        };
        if !page.matches(&c.title, &c.artist) {
            continue;
        }
        let enriched = super::furigana::enrich(snapshot, &page, &url, &html)?;
        if enriched.id != snapshot.id {
            return Ok((enriched, true));
        }
    }
    Ok((snapshot.clone(), complete))
}
fn lyric_request(mid: &str) -> Value {
    json!({"comm":{"ct":19,"cv":1859,"uin":"0"},"req":{"module":"music.musichallSong.PlayLyricInfo","method":"GetPlayLyricInfo","param":{"songMID":mid,"songID":0,"crypt":1,"qrc":1,"roma":1,"trans":1,"lrc_t":0,"qrc_t":0,"roma_t":0,"trans_t":0,"interval":0,"type":0,"format":"json","ct":19,"cv":1859}}})
}
async fn lookup(
    store: &Store<'_>,
    http: &reqwest::Client,
    query: &Query,
) -> Result<(Option<Lyrics>, bool)> {
    let search = body(
        store,
        http.get("https://c.y.qq.com/soso/fcgi-bin/search_for_qq_cp")
            .header("Referer", REFERER)
            .query(&[
                ("w", query.title.as_str()),
                ("format", "json"),
                ("p", "1"),
                ("n", "20"),
            ]),
        |text| {
            let value = qq_response(text)?;
            if value
                .pointer("/data/song/list")
                .and_then(Value::as_array)
                .is_none()
            {
                bail!("Unexpected lyric search response; retry later.");
            }
            Ok(value)
        },
    )
    .await?;
    let matches = select(&search, query);
    if matches.is_empty() {
        return Ok((None, true));
    }
    let mut candidates = Vec::new();
    let mut complete = true;
    for c in matches {
        let request = lyric_request(&c.mid);
        let snapshot = body(
            store,
            http.post("https://u.y.qq.com/cgi-bin/musicu.fcg")
                .header("Referer", "https://y.qq.com/")
                .json(&request),
            |text| {
                let value = qq_response(text)?;
                match value["req"]["data"]["qrc"].as_i64() {
                    Some(0) => Ok(None),
                    Some(1) => from_response(&value, &c, query).map(Some),
                    _ => bail!("Unexpected karaoke response; retry later."),
                }
            },
        )
        .await?;
        let Some(snapshot) = snapshot else {
            continue;
        };
        let (mut snapshot, enriched) = furigana(store, http, &snapshot, &c)
            .await
            .unwrap_or((snapshot, false));
        complete &= enriched;
        if !enriched {
            snapshot.source.warnings.push(
                "Furigana is temporarily unavailable. Find karaoke lyrics again to retry.".into(),
            );
            snapshot = Snapshot::new(snapshot.source, snapshot.occurrences)?;
        }
        candidates.push(snapshot);
    }
    if candidates.is_empty() {
        return Ok((None, true));
    }
    let lines = candidates[0]
        .occurrences
        .iter()
        .map(|l| Line {
            text: l.raw_line.clone(),
            at_ms: l.start_ms.and_then(|n| u32::try_from(n).ok()),
        })
        .collect();
    Ok((
        Some(Lyrics {
            lines,
            synced: true,
            instrumental: false,
            source_snapshot: None,
            candidates,
        }),
        complete,
    ))
}
pub async fn fetch(
    http: &reqwest::Client,
    directory: &Path,
    query: &Query,
    refresh: bool,
) -> Result<Option<Lyrics>> {
    static LOOKUP_LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());
    if query.duration_ms == 0
        || normalized(&query.title).is_empty()
        || normalized(&query.artist).is_empty()
    {
        bail!("Song title, artist and duration are needed to find karaoke lyrics.");
    }
    tokio::time::timeout(Duration::from_secs(90), async {
        // Serialize explicit lookups so rapid requests for one missing song do
        // not all contact the provider before the first response is stored.
        let _guard = LOOKUP_LOCK.lock().await;
        let store = Store { directory, refresh };
        if let Some(saved) = store.lookup(query) {
            return Ok(saved);
        }
        let (found, complete) = lookup(&store, http, query).await?;
        if complete {
            store.save_lookup(query, &found)?;
        }
        Ok(found)
    })
    .await
    .map_err(|_| anyhow!("Karaoke lookup timed out; existing lyrics are preserved."))?
}

#[cfg(test)]
mod tests {
    use super::*;
    fn stored(store: &Store<'_>, request: reqwest::RequestBuilder, text: &str) {
        store
            .save_response(
                &Store::request_key(&request.build().unwrap()).unwrap(),
                text,
            )
            .unwrap();
    }
    // Only synthetic lyrics and loopback/blocked-proxy traffic enter these tests.
    #[tokio::test]
    async fn optional_reading_failure_retries_without_refetching_qq() {
        let temp = crate::study::testutil::TestDir::new();
        let store = Store {
            directory: temp.path(),
            refresh: false,
        };
        let client = reqwest::Client::builder()
            .proxy(reqwest::Proxy::all("http://127.0.0.1:9").unwrap())
            .build()
            .unwrap();
        let query = Query {
            title: "Fixture".into(),
            artist: "Artist".into(),
            album: String::new(),
            duration_ms: 2000,
        };
        stored(&store, client.get("https://c.y.qq.com/soso/fcgi-bin/search_for_qq_cp").query(&[("w", "Fixture"), ("format", "json"), ("p", "1"), ("n", "20")]), &json!({"code":0,"data":{"song":{"list":[{"songmid":"fixture","songname":"Fixture","singer":[{"name":"Artist"}],"interval":2}]}}}).to_string());
        // Modified DES encoding of <QrcInfos><Lyric_1 LyricContent="[0,1000]空(0,1000)"/></QrcInfos>.
        stored(&store, client.post("https://u.y.qq.com/cgi-bin/musicu.fcg").json(&lyric_request("fixture")), &json!({"code":0,"req":{"code":0,"data":{"qrc":1,"lyric":"ee7befb746f93831d42dcdf2e21f0d5d924943e250c9b32f6d731ce7c8a4cd01eca6eb73c8a868b20f938d844361773f4cec1bb6d759bd0e10fc23e59d2d8dfb"}}}).to_string());
        stored(
            &store,
            client.get("https://utaten.com/lyric/search").query(&[
                ("sort", "popular_sort_asc"),
                ("artist_name", "Artist"),
                ("title", "Fixture"),
                ("beginning", ""),
                ("body", ""),
                ("lyricist", ""),
                ("composer", ""),
                ("sub_title", ""),
                ("tag", ""),
                ("show_artists", "1"),
            ]),
            "<a href='/lyric/fixture/'>Result</a>",
        );
        let partial = fetch(&client, temp.path(), &query, false)
            .await
            .unwrap()
            .unwrap();
        assert!(!partial.candidates[0].occurrences[0].fragments.is_empty());
        assert!(partial.candidates[0].source.readings.is_empty());
        assert!(store.lookup(&query).is_none());
        stored(
            &store,
            client.get("https://utaten.com/lyric/fixture/"),
            "<h2 class='newLyricTitle__main'>Fixture<span>歌詞</span></h2><h3><a href='/artist/lyric/1'>Artist</a></h3><div class='lyricBody'><div class='hiragana'><span class='ruby'><span class='rb'>空</span><span class='rt'>そら</span></span></div></div>",
        );
        let complete = fetch(&client, temp.path(), &query, false)
            .await
            .unwrap()
            .unwrap();
        assert_eq!(complete.candidates[0].source.readings[0].hiragana, "そら");
        assert_eq!(
            complete.candidates[0].occurrences[0].fragments,
            partial.candidates[0].occurrences[0].fragments
        );
        assert!(store.lookup(&query).unwrap().is_some());
    }
    fn mock_response(text: &'static str) -> (String, std::thread::JoinHandle<()>) {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let url = format!("http://{}/fixture", listener.local_addr().unwrap());
        let worker = std::thread::spawn(move || {
            let deadline = std::time::Instant::now() + Duration::from_secs(5);
            let mut stream = loop {
                match listener.accept() {
                    Ok((stream, _)) => break stream,
                    Err(e)
                        if e.kind() == std::io::ErrorKind::WouldBlock
                            && std::time::Instant::now() < deadline =>
                    {
                        std::thread::sleep(Duration::from_millis(5))
                    }
                    Err(e) => panic!("mock request failed: {e}"),
                }
            };
            stream
                .set_read_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                assert!(request.len() < 4096, "mock request headers too large");
                let mut byte = [0];
                stream.read_exact(&mut byte).unwrap();
                request.push(byte[0]);
            }
            write!(
                stream,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{text}",
                text.len()
            )
            .unwrap();
        });
        (url, worker)
    }
    #[tokio::test]
    async fn malformed_success_is_not_stored_and_invalid_old_cache_can_recover() {
        let temp = crate::study::testutil::TestDir::new();
        let store = Store {
            directory: temp.path(),
            refresh: false,
        };
        let client = reqwest::Client::builder().no_proxy().build().unwrap();
        let (url, worker) = mock_response("<html>Try later</html>");
        let req = client.get(&url);
        let key = Store::request_key(&req.try_clone().unwrap().build().unwrap()).unwrap();
        assert!(body(&store, req, qq_response).await.is_err());
        worker.join().unwrap();
        assert!(store.response(&key).is_none());
        let (url, worker) = mock_response(r#"{"code":0,"data":{"song":{"list":[]}}}"#);
        let req = client.get(&url);
        let key = Store::request_key(&req.try_clone().unwrap().build().unwrap()).unwrap();
        store
            .save_response(&key, "<html>Old invalid response</html>")
            .unwrap();
        assert_eq!(body(&store, req, qq_response).await.unwrap()["code"], 0);
        worker.join().unwrap();
        assert!(qq_response(&store.response(&key).unwrap()).is_ok());
    }

    #[tokio::test]
    async fn confirmed_no_qrc_is_a_durable_missing_result() {
        let temp = crate::study::testutil::TestDir::new();
        let store = Store {
            directory: temp.path(),
            refresh: false,
        };
        let client = reqwest::Client::builder()
            .proxy(reqwest::Proxy::all("http://127.0.0.1:9").unwrap())
            .build()
            .unwrap();
        let query = Query {
            title: "Fixture".into(),
            artist: "Artist".into(),
            album: String::new(),
            duration_ms: 2000,
        };
        let search = client
            .get("https://c.y.qq.com/soso/fcgi-bin/search_for_qq_cp")
            .query(&[
                ("w", "Fixture"),
                ("format", "json"),
                ("p", "1"),
                ("n", "20"),
            ])
            .build()
            .unwrap();
        store.save_response(&Store::request_key(&search).unwrap(),&json!({"code":0,"data":{"song":{"list":[{"songmid":"fixture","songname":"Fixture","singer":[{"name":"Artist"}],"interval":2}]}}}).to_string()).unwrap();
        let lyric = client
            .post("https://u.y.qq.com/cgi-bin/musicu.fcg")
            .json(&lyric_request("fixture"))
            .build()
            .unwrap();
        store
            .save_response(
                &Store::request_key(&lyric).unwrap(),
                &json!({"code":0,"req":{"code":0,"data":{"qrc":0}}}).to_string(),
            )
            .unwrap();
        assert!(
            fetch(&client, temp.path(), &query, false)
                .await
                .unwrap()
                .is_none()
        );
        assert_eq!(store.lookup(&query), Some(None));
    }

    #[tokio::test]
    async fn stored_negative_and_raw_responses_need_no_provider_request() {
        let temp = crate::study::testutil::TestDir::new();
        let client = reqwest::Client::builder()
            .proxy(reqwest::Proxy::all("http://127.0.0.1:9").unwrap())
            .build()
            .unwrap();
        let query = Query {
            title: "Fixture".into(),
            artist: "Artist".into(),
            album: String::new(),
            duration_ms: 2000,
        };
        let store = Store {
            directory: temp.path(),
            refresh: false,
        };
        store.save_lookup(&query, &None).unwrap();
        assert!(
            fetch(&client, temp.path(), &query, false)
                .await
                .unwrap()
                .is_none()
        );
        assert!(fetch(&client, temp.path(), &query, true).await.is_err());
        assert_eq!(store.lookup(&query), Some(None));
        let request = client.get("https://utaten.com/lyric/fixture/");
        let key = Store::request_key(&request.try_clone().unwrap().build().unwrap()).unwrap();
        store
            .save_response(&key, "<html>stored fixture</html>")
            .unwrap();
        assert_eq!(
            body(&store, request, |text| Ok(text.to_owned()))
                .await
                .unwrap(),
            "<html>stored fixture</html>"
        );
    }

    #[test]
    fn metadata_selection_rejects_other_recordings_missing_identity_and_bad_ids() {
        let query = Query {
            artist: "Artist".into(),
            title: "Song".into(),
            album: "".into(),
            duration_ms: 200_000,
        };
        let song = |mid: &str, title: &str, artist: &str, seconds: u32| json!({"songmid":mid,"songname":title,"singer":[{"name":artist}],"interval":seconds});
        let value = json!({"data":{"song":{"list":[song("good","Song","Artist",200),song("cover","Song","Other",200),song("live","Song (Live)","Artist",250),song("wrong","Other","Artist",200),song("../bad","Song","Artist",200),song("long","Song","Artist",204)]}}});
        let out = select(&value, &query);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].mid, "good");
        assert!(
            select(
                &value,
                &Query {
                    duration_ms: 0,
                    ..query
                }
            )
            .is_empty()
        );
    }
}
