//! Durable supplied-source responses and lookup results; no automatic expiry.
use super::{Lyrics, Query};
use anyhow::{Result, bail};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use sha2::{Digest, Sha256};
use std::{
    io::Read,
    path::{Path, PathBuf},
};
const BODY_LIMIT: usize = 1_048_576;
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn read_json<T: DeserializeOwned>(path: &Path, limit: u64) -> Option<T> {
    let file = std::fs::File::open(path).ok()?;
    if file.metadata().ok()?.len() > limit {
        return None;
    }
    serde_json::from_reader(file.take(limit + 1)).ok()
}
fn write(path: &Path, bytes: impl AsRef<[u8]>) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    fastframe_file::write_private(path, bytes.as_ref())?;
    Ok(())
}
#[derive(Serialize, Deserialize)]
struct ResponseIndex {
    version: u32,
    request_sha256: String,
    response_sha256: String,
}
#[derive(Serialize, Deserialize)]
struct Lookup {
    version: u32,
    query: Query,
    found: Option<Lyrics>,
}
pub(super) struct Store<'a> {
    pub directory: &'a Path,
    pub refresh: bool,
}
impl Store<'_> {
    fn lookup_path(&self, query: &Query) -> PathBuf {
        self.directory.join("lookups").join(format!(
            "{}.json",
            sha(&serde_json::to_vec(query).expect("query serializes"))
        ))
    }
    pub fn lookup(&self, query: &Query) -> Option<Option<Lyrics>> {
        if self.refresh {
            return None;
        }
        let saved: Lookup = read_json(&self.lookup_path(query), 32 * 1024 * 1024)?;
        if saved.version != 1 || &saved.query != query {
            return None;
        }
        if let Some(lyrics) = &saved.found
            && (lyrics.source_snapshot.is_some()
                || lyrics.candidates.is_empty()
                || lyrics.candidates.len() > 3
                || lyrics.candidates.iter().any(|s| s.validate().is_err()))
        {
            return None;
        }
        Some(saved.found)
    }
    pub fn save_lookup(&self, query: &Query, found: &Option<Lyrics>) -> Result<()> {
        write(
            &self.lookup_path(query),
            serde_json::to_vec(&Lookup {
                version: 1,
                query: query.clone(),
                found: found.clone(),
            })?,
        )
    }
    pub fn request_key(request: &reqwest::Request) -> Result<String> {
        let bytes = request
            .body()
            .map(|b| {
                b.as_bytes()
                    .ok_or_else(|| anyhow::anyhow!("cannot cache a streaming lyric request"))
            })
            .transpose()?
            .unwrap_or_default();
        Ok(sha(&serde_json::to_vec(&(
            request.method().as_str(),
            request.url().as_str(),
            bytes,
        ))?))
    }
    pub fn response(&self, key: &str) -> Option<String> {
        if self.refresh {
            return None;
        }
        let index: ResponseIndex = read_json(
            &self.directory.join("requests").join(format!("{key}.json")),
            4096,
        )?;
        if index.version != 1
            || index.request_sha256 != key
            || index.response_sha256.len() != 64
            || !index.response_sha256.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return None;
        }
        let path = self
            .directory
            .join("responses")
            .join(format!("{}.txt", index.response_sha256));
        let file = std::fs::File::open(path).ok()?;
        let mut bytes = Vec::new();
        file.take(BODY_LIMIT as u64 + 1)
            .read_to_end(&mut bytes)
            .ok()?;
        if bytes.len() > BODY_LIMIT || sha(&bytes) != index.response_sha256 {
            return None;
        }
        String::from_utf8(bytes).ok()
    }
    pub fn save_response(&self, key: &str, body: &str) -> Result<()> {
        if body.len() > BODY_LIMIT || body.trim().is_empty() {
            bail!("invalid stored lyric response");
        }
        let hash = sha(body.as_bytes());
        // Refresh changes the request index, retaining earlier immutable bodies.
        write(
            &self.directory.join("responses").join(format!("{hash}.txt")),
            body,
        )?;
        write(
            &self.directory.join("requests").join(format!("{key}.json")),
            serde_json::to_vec(&ResponseIndex {
                version: 1,
                request_sha256: key.into(),
                response_sha256: hash,
            })?,
        )
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn raw_responses_are_reused_and_refresh_retains_prior_versions() {
        let temp = crate::study::testutil::TestDir::new();
        let store = Store {
            directory: temp.path(),
            refresh: false,
        };
        let req = reqwest::Client::new()
            .get("https://example.test/lyrics?q=fixture")
            .build()
            .unwrap();
        let key = Store::request_key(&req).unwrap();
        assert!(store.response(&key).is_none());
        store.save_response(&key, "first response").unwrap();
        assert_eq!(store.response(&key).as_deref(), Some("first response"));
        let refresh = Store {
            directory: temp.path(),
            refresh: true,
        };
        assert!(refresh.response(&key).is_none());
        refresh.save_response(&key, "changed response").unwrap();
        assert_eq!(store.response(&key).as_deref(), Some("changed response"));
        assert!(
            temp.path()
                .join("responses")
                .join(format!("{}.txt", sha(b"first response")))
                .is_file()
        );
        let post = reqwest::Client::new()
            .post("https://example.test/lyrics?q=fixture")
            .body("different")
            .build()
            .unwrap();
        assert_ne!(Store::request_key(&post).unwrap(), key);
    }
    #[test]
    fn confirmed_missing_tracks_are_stored_and_corrupt_data_is_not_trusted() {
        let temp = crate::study::testutil::TestDir::new();
        let store = Store {
            directory: temp.path(),
            refresh: false,
        };
        let q = Query {
            title: "Fixture".into(),
            artist: "Artist".into(),
            album: "".into(),
            duration_ms: 2000,
        };
        assert!(store.lookup(&q).is_none());
        store.save_lookup(&q, &None).unwrap();
        assert_eq!(store.lookup(&q), Some(None));
        assert!(
            Store {
                directory: temp.path(),
                refresh: true
            }
            .lookup(&q)
            .is_none()
        );
        let source = crate::study::source::import("[00:01]空", "stored fixture").unwrap();
        let saved = Some(Lyrics {
            lines: vec![super::super::Line {
                at_ms: Some(1000),
                text: "空".into(),
            }],
            synced: true,
            instrumental: false,
            source_snapshot: None,
            candidates: vec![source],
        });
        store.save_lookup(&q, &saved).unwrap();
        std::fs::File::options()
            .write(true)
            .open(store.lookup_path(&q))
            .unwrap()
            .set_times(std::fs::FileTimes::new().set_modified(std::time::SystemTime::UNIX_EPOCH))
            .unwrap();
        assert_eq!(store.lookup(&q), Some(saved));

        let key = "a".repeat(64);
        store.save_response(&key, "source body").unwrap();
        std::fs::write(
            temp.path()
                .join("responses")
                .join(format!("{}.txt", sha(b"source body"))),
            "changed bytes",
        )
        .unwrap();
        assert!(store.response(&key).is_none());
    }
}
