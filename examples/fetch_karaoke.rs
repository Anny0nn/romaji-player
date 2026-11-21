//! Explicit live smoke of the same supplied-source client used by Options.
//! Pass public track metadata and a private output directory; no Spotify login.
use anyhow::{Result, anyhow};
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

#[tokio::main]
async fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    anyhow::ensure!(
        args.len() == 5 || (args.len() == 6 && args[5] == "--offline"),
        "usage: fetch_karaoke TITLE ARTIST DURATION_MS PRIVATE_OUTPUT_DIRECTORY [--offline]"
    );
    let output = private_output(std::path::Path::new(&args[4]))?;
    anyhow::ensure!(
        !output.starts_with(env!("CARGO_MANIFEST_DIR")),
        "Keep fetched lyrics outside the checkout."
    );
    let query = spotifast::lyrics::Query {
        title: args[1].clone(),
        artist: args[2].clone(),
        album: String::new(),
        duration_ms: args[3].parse()?,
    };
    let client = if args.get(5).is_some_and(|s| s == "--offline") {
        reqwest::Client::builder()
            .no_proxy()
            .proxy(reqwest::Proxy::all("http://127.0.0.1:9")?)
            .build()?
    } else {
        spotifast::http::build_client(&Default::default()).map_err(|e| anyhow!(e))?
    };
    let start = std::time::Instant::now();
    let found = spotifast::lyrics::karaoke::fetch(&client, &output, &query, false).await?;
    let candidates=found.as_ref().map(|l|l.candidates.iter().map(|s|serde_json::json!({"provider":s.source.provider,"lines":s.occurrences.len(),"supplied_readings":s.source.readings.len(),"timing_fragments":s.occurrences.iter().map(|l|l.fragments.len()).sum::<usize>()})).collect::<Vec<_>>()).unwrap_or_default();
    println!(
        "{}",
        serde_json::json!({"candidates":candidates,"wall_seconds":start.elapsed().as_secs_f64(),"promoted":false})
    );
    Ok(())
}
