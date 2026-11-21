//! Explicit offline replay of the private source-audit layout; never contacts providers.
use anyhow::{Context, Result};
use serde_json::{Value, json};
use spotifast::{
    lyrics::{self, karaoke::Candidate},
    study::{
        conversion::{PROTOCOL, Request, Romanizer},
        snapshot::Document,
        timing::WordTiming,
    },
};
use std::{
    path::{Path, PathBuf},
    process::Command,
};
fn read(path: impl AsRef<Path>) -> Result<Value> {
    Ok(serde_json::from_slice(&std::fs::read(path)?)?)
}
fn private_output(path: &std::path::Path) -> Result<std::path::PathBuf> {
    if !path.exists() {
        let mut builder = std::fs::DirBuilder::new();
        builder.recursive(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        builder.create(path)?;
    }
    let path = path.canonicalize()?;
    anyhow::ensure!(
        !path.starts_with(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).canonicalize()?),
        "Keep lyric payloads outside the checkout."
    );
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        anyhow::ensure!(
            path.metadata()?.permissions().mode() & 0o077 == 0,
            "Use a private output directory (chmod 700)."
        );
    }
    Ok(path)
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    anyhow::ensure!(
        args.len() == 3,
        "usage: check_supplied_lyrics PRIVATE_AUDIT_DIRECTORY PRIVATE_OUTPUT_DIRECTORY"
    );
    let input = PathBuf::from(&args[1]);
    let output = private_output(Path::new(&args[2]))?;
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let start = std::time::Instant::now();
    let mut helper = Romanizer::start(
        Command::new(root.join(".venv/bin/python")).arg(root.join("romanizer/romanizer.py")),
    )?;
    let manifest = read(input.join("manifest.json"))?;
    let selected = read(input.join("selected-candidates.json"))?;
    let mut summary = Vec::new();
    for track in manifest["tracks"]
        .as_array()
        .context("missing audit tracks")?
    {
        let id = track["track"].as_str().unwrap();
        let mid = selected
            .as_array()
            .unwrap()
            .iter()
            .find(|x| x[0] == id)
            .and_then(|x| x[1].as_str())
            .context("missing selected QQ candidate")?;
        let search = if track["title"] == "CROW" {
            read(input.join("crow-refined-search.json"))?
        } else {
            read(input.join(format!("{id}-qq-search.json")))?
        };
        let meta = search["data"]["song"]["list"]
            .as_array()
            .unwrap()
            .iter()
            .find(|x| x["songmid"] == mid)
            .context("selected metadata absent")?;
        let c = Candidate {
            mid: mid.into(),
            title: meta["songname"].as_str().unwrap().into(),
            artist: meta["singer"][0]["name"].as_str().unwrap().into(),
            album: meta["albumname"].as_str().unwrap_or("").into(),
            duration_ms: meta["interval"].as_u64().unwrap() as u32 * 1000,
        };
        let query = lyrics::Query {
            title: track["title"].as_str().unwrap().into(),
            artist: track["artist"].as_str().unwrap().into(),
            album: String::new(),
            duration_ms: (track["duration_seconds"].as_f64().unwrap() * 1000.0).round() as u32,
        };
        let native_matches = lyrics::karaoke::select(&search, &query)
            .iter()
            .any(|x| x.mid == mid);
        let path = if track["title"] == "Just Awake" {
            input.join("just-awake-qq-lyric.json")
        } else {
            input.join(format!("{id}-qq-lyric.json"))
        };
        let result = (|| -> Result<Value> {
            let mut snapshot = lyrics::karaoke::from_response(&read(path)?, &c, &query)?;
            let qq_readings = snapshot.source.readings.len();
            let html = std::fs::read_to_string(input.join(format!("{id}-utaten.html")))?;
            // The cached page is supplied by the prior audit. Identity checks still
            // apply; only audited artist aliases are accepted here.
            if let Ok(page) = lyrics::furigana::parse(&html, &c.title, &c.artist) {
                snapshot = lyrics::furigana::enrich(&snapshot, &page, "cached-audit-page", &html)?;
            }
            let supplied_readings = snapshot.source.readings.len();
            let warning_count = snapshot.source.warnings.len();
            let document = Document::new(id, snapshot)?;
            let mut owners = 0;
            let mut timed = 0;
            let mut supplied_words = 0;
            for line in &document.current().snapshot.occurrences {
                let request = Request {
                    protocol_version: PROTOCOL,
                    request_id: line.id as u64 + 1,
                    track_id: id.into(),
                    snapshot_id: document.current().snapshot.id.clone(),
                    occurrence_id: line.id,
                    override_revision: 0,
                    expected_conversion_signature: helper.signature.clone(),
                    raw_line: line.raw_line.clone(),
                    overrides: Vec::new(),
                    supplied_readings: document.current().snapshot.readings_for(line.id),
                };
                let converted = helper.convert(&request)?;
                for word in converted.words {
                    owners += 1;
                    supplied_words += usize::from(
                        word.reading.origin == "source"
                            && word.raw_span.is_some_and(|span| {
                                request
                                    .supplied_readings
                                    .iter()
                                    .any(|r| span[0] <= r.raw_span[0] && r.raw_span[1] <= span[1])
                            }),
                    );
                    if word
                        .raw_span
                        .and_then(|s| WordTiming::supplied(s, &line.fragments))
                        .is_some()
                    {
                        timed += 1;
                    }
                }
            }
            document.save(&output.join("documents"))?;
            let reloaded = Document::load(&output.join("documents"), id)?
                .context("saved candidate missing")?;
            anyhow::ensure!(reloaded == document, "candidate changed on reopen");
            Ok(
                json!({"track":id,"native_metadata_match":native_matches,"qrc_readings":qq_readings,"enriched_readings":supplied_readings,"owners":owners,"structurally_timed_owners":timed,"source_reading_words":supplied_words,"warnings":warning_count,"reopened":true,"promoted":false}),
            )
        })();
        match result {
            Ok(row) => {
                println!("{row}");
                summary.push(row);
            }
            Err(e) => {
                let row = json!({"track":id,"error":e.to_string(),"promoted":false});
                println!("{row}");
                summary.push(row);
            }
        }
    }
    std::fs::create_dir_all(&output)?;
    let result = json!({"rows":summary,"wall_seconds":start.elapsed().as_secs_f64(),"helper_signature":helper.signature,"note":"Source-specific full-song denominators; structural coverage is not acoustic accuracy. Cached selected candidates are not automatic metadata lookup successes."});
    std::fs::write(
        output.join("summary.json"),
        serde_json::to_vec_pretty(&result)?,
    )?;
    Ok(())
}
