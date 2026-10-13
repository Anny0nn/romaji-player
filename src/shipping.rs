//! Public build configuration; no client secret, cookie or token belongs here.
use std::path::PathBuf;
use std::process::Command;

use anyhow::{Result, bail};

pub const BUNDLE_ID: &str = "io.github.Anny0nn.RomajiPlayer";
pub const CLIENT_ID: &str = match option_env!("SPOTIFY_CLIENT_ID") {
    Some(value) => value,
    None => "",
};
pub const REDIRECT_URI: &str = match option_env!("SPOTIFY_REDIRECT_URI") {
    Some(value) => value,
    None => "",
};

pub fn validate(client_id: &str, redirect_uri: &str) -> Result<()> {
    if client_id.len() != 32 || !client_id.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        bail!("a configured Spotify development application is required");
    }
    if redirect_uri
        != format!(
            "http://127.0.0.1:{}{}",
            crate::auth::WEB_REDIRECT_PORT,
            crate::auth::REDIRECT_PATH
        )
    {
        bail!("the Spotify callback must match the native loopback listener");
    }
    Ok(())
}

pub fn helper_command() -> Result<Command> {
    let executable = std::env::current_exe()?;
    let folder = executable
        .parent()
        .ok_or_else(|| anyhow::anyhow!("app executable unavailable"))?;
    let helper = if folder.file_name().is_some_and(|name| name == "MacOS") {
        // A distributed app never falls back to a developer installation.
        folder
            .parent()
            .ok_or_else(|| anyhow::anyhow!("app resources unavailable"))?
            .join("Resources/RomajiRomanizer/RomajiRomanizer")
    } else {
        PathBuf::from(
            std::env::var_os("ROMAJI_HELPER_PATH")
                .ok_or_else(|| anyhow::anyhow!("build the romanizer and set ROMAJI_HELPER_PATH"))?,
        )
    };
    if !helper.is_file() {
        bail!("bundled romanizer unavailable");
    }
    Ok(Command::new(helper))
}

pub fn aligner_command() -> Result<Command> {
    let executable = std::env::current_exe()?;
    let folder = executable
        .parent()
        .ok_or_else(|| anyhow::anyhow!("App executable unavailable."))?;
    let helper = if folder.file_name().is_some_and(|name| name == "MacOS") {
        folder
            .parent()
            .unwrap()
            .join("Resources/RomajiAligner/RomajiAligner")
    } else {
        PathBuf::from(std::env::var_os("ROMAJI_ALIGNER_PATH").ok_or_else(|| {
            anyhow::anyhow!("Build the local aligner and set ROMAJI_ALIGNER_PATH.")
        })?)
    };
    if !helper.is_file() {
        bail!("Bundled local aligner unavailable.");
    }
    Ok(Command::new(helper))
}

pub fn tifa_command() -> Result<Command> {
    let executable = std::env::current_exe()?;
    let folder = executable
        .parent()
        .ok_or_else(|| anyhow::anyhow!("App executable unavailable."))?;
    let helper = if folder.file_name().is_some_and(|name| name == "MacOS") {
        folder
            .parent()
            .unwrap()
            .join("Resources/RomajiTIFA/RomajiTIFA")
    } else {
        PathBuf::from(
            std::env::var_os("ROMAJI_TIFA_PATH")
                .ok_or_else(|| anyhow::anyhow!("Build TIFA and set ROMAJI_TIFA_PATH."))?,
        )
    };
    if !helper.is_file() {
        bail!("Bundled TIFA aligner unavailable.");
    }
    Ok(Command::new(helper))
}

pub fn experimental_command() -> Result<Command> {
    let executable = std::env::current_exe()?;
    let folder = executable
        .parent()
        .ok_or_else(|| anyhow::anyhow!("App executable unavailable."))?;
    let helper = if folder.file_name().is_some_and(|name| name == "MacOS") {
        folder
            .parent()
            .unwrap()
            .join("Resources/RomajiExperimental/RomajiExperimental")
    } else {
        PathBuf::from(std::env::var_os("ROMAJI_EXPERIMENTAL_PATH").ok_or_else(|| {
            anyhow::anyhow!("Build the experimental runtime and set ROMAJI_EXPERIMENTAL_PATH.")
        })?)
    };
    if !helper.is_file() {
        bail!("Bundled experimental aligner unavailable.");
    }
    Ok(Command::new(helper))
}

pub fn check_romaji() -> Result<serde_json::Value> {
    use crate::study::conversion::{Request, Romanizer};
    let mut helper = Romanizer::start(&mut helper_command()?)?;
    let request = Request {
        protocol_version: 1,
        request_id: 1,
        track_id: "synthetic".into(),
        snapshot_id: "package-check".into(),
        occurrence_id: 0,
        override_revision: 0,
        expected_conversion_signature: helper.signature.clone(),
        raw_line: "ｶﾞ 食べた を".into(),
        overrides: Vec::new(),
    };
    let response = helper.convert(&request)?;
    Ok(
        serde_json::json!({"romaji":response.romaji,"hiragana":response.hiragana,"raw_spans":response.words.iter().map(|word|word.raw_span).collect::<Vec<_>>() }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn packaging_requires_explicit_public_identity_and_the_actual_callback() {
        let client = "00000000000000000000000000000000";
        assert!(validate(client, "http://127.0.0.1:8989/login").is_ok());
        assert!(validate("", "http://127.0.0.1:8989/login").is_err());
        assert!(validate(client, "http://localhost:8989/login").is_err());
        assert!(validate(client, "http://127.0.0.1:5173/callback").is_err());
        assert!(validate(client, "http://127.0.0.1:8898/login").is_err());
    }
    #[test]
    fn identity_never_defaults_to_the_upstream_shared_web_application() {
        assert!(
            CLIENT_ID.is_empty() || CLIENT_ID == option_env!("SPOTIFY_CLIENT_ID").unwrap_or("")
        );
        assert_eq!(crate::auth::DEFAULT_WEB_CLIENT_ID, CLIENT_ID);
        assert_eq!(
            crate::auth::Grant::shared_web_api().redirect_uri(),
            "http://127.0.0.1:8989/login"
        );
        assert_ne!(CLIENT_ID, crate::auth::PLAYBACK_CLIENT_ID);
    }
}
