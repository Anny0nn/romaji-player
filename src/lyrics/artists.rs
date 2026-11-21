//! Audited artist aliases shared by supplied-source identity checks.
//! Add identities only with a primary source explicitly naming both forms.

// Increment when matching changes so old candidates and misses are rechecked
// using stored raw responses. Saved song versions and edits are unaffected.
pub(super) const MATCHING_VERSION: u32 = 1;

struct Identity {
    names: &'static [&'static str],
    evidence: &'static str,
}
const IDENTITIES: &[Identity] = &[Identity {
    names: &["Masayuki Suzuki", "鈴木雅之"],
    evidence: "https://www.japanmusic.jp/talent/masayuki-suzuki/",
}];

pub(super) fn evidence(a: &str, b: &str) -> Option<&'static str> {
    let a = super::karaoke::normalized(a);
    let b = super::karaoke::normalized(b);
    if a.is_empty() || b.is_empty() || a == b {
        return None;
    }
    IDENTITIES
        .iter()
        .find(|identity| {
            identity
                .names
                .iter()
                .any(|s| super::karaoke::normalized(s) == a)
                && identity
                    .names
                    .iter()
                    .any(|s| super::karaoke::normalized(s) == b)
        })
        .map(|identity| identity.evidence)
}
pub(super) fn matches(a: &str, b: &str) -> bool {
    let name = super::karaoke::normalized(a);
    !name.is_empty() && (name == super::karaoke::normalized(b) || evidence(a, b).is_some())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn verified_aliases_are_symmetric_and_do_not_guess_other_performers() {
        assert!(matches("Masayuki Suzuki", "鈴木雅之"));
        assert!(matches("鈴木雅之", "MASAYUKI SUZUKI"));
        assert!(matches("Artist", "artist"));
        for other in [
            "鈴木愛理",
            "CHEMISTRY",
            "Suzuki",
            "Masayuki",
            "Suzuki Masayuki",
            "",
        ] {
            assert!(!matches("Masayuki Suzuki", other));
        }
        assert!(!matches("", " "));
        assert!(evidence("Masayuki Suzuki", "鈴木雅之").is_some());
        assert!(evidence("Artist", "artist").is_none());
    }
}
