//! Source-anchored singalong foundations; playback remains upstream's engine.
pub mod alignment;
pub mod audio;
pub mod controller;
pub mod conversion;
pub mod reading;
pub mod snapshot;
pub mod source;
pub mod timing;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum LyricMode {
    #[default]
    Romaji,
    Both,
    Hiragana,
    Katakana,
    Japanese,
}

impl LyricMode {
    pub const ALL: [Self; 5] = [
        Self::Romaji,
        Self::Both,
        Self::Hiragana,
        Self::Katakana,
        Self::Japanese,
    ];
    pub fn label(self) -> &'static str {
        match self {
            Self::Romaji => "Romaji",
            Self::Both => "Hiragana + romaji",
            Self::Hiragana => "Hiragana",
            Self::Katakana => "Katakana",
            Self::Japanese => "Japanese",
        }
    }
    pub fn scripts(self) -> &'static [Self] {
        match self {
            Self::Romaji => &[Self::Romaji],
            Self::Both => &[Self::Hiragana, Self::Romaji],
            Self::Hiragana => &[Self::Hiragana],
            Self::Katakana => &[Self::Katakana],
            Self::Japanese => &[Self::Japanese],
        }
    }
}

#[cfg(test)]
pub(crate) mod testutil {
    use std::path::{Path, PathBuf};
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    pub struct TestDir(PathBuf);
    impl TestDir {
        pub fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "romaji-fixture-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir_all(&path).unwrap();
            Self(path)
        }
        pub fn path(&self) -> &Path {
            &self.0
        }
    }
    impl Drop for TestDir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
}
