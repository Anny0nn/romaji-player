//! Source-anchored singalong foundations; playback remains upstream's engine.
pub mod alignment;
pub mod audio;
pub mod controller;
pub mod conversion;
pub mod snapshot;
pub mod source;
pub mod timing;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum LyricMode {
    #[default]
    Romaji,
    Both,
    Hiragana,
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
