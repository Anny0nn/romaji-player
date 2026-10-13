//! Exact source coverage and manual precedence; no inferred syllable times.
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Interval {
    pub start_ms: i64,
    pub end_ms: Option<i64>,
}
impl Interval {
    pub fn valid(&self) -> bool {
        self.end_ms.is_none_or(|end| end > self.start_ms)
    }
    pub fn active(&self, lyric_ms: i64, selection_bound: Option<i64>) -> bool {
        self.valid()
            && lyric_ms >= self.start_ms
            && self
                .end_ms
                .or(selection_bound)
                .is_none_or(|end| lyric_ms < end)
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Fragment {
    pub raw_span: [usize; 2],
    pub interval: Interval,
    pub source: String,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WordTiming {
    pub intervals: Vec<Interval>,
    pub fragments: Vec<Fragment>,
    pub manual: bool,
}
impl WordTiming {
    /// Merge only fragments that exactly tile the raw word, including inside a token.
    pub fn supplied(word: [usize; 2], fragments: &[Fragment]) -> Option<Self> {
        if word[0] >= word[1] {
            return None;
        }
        let mut matching: Vec<_> = fragments
            .iter()
            .filter(|fragment| fragment.raw_span[0] < word[1] && fragment.raw_span[1] > word[0])
            .cloned()
            .collect();
        matching.sort_by_key(|fragment| fragment.raw_span);
        let mut boundary = word[0];
        for fragment in &matching {
            if fragment.raw_span[0] != boundary
                || fragment.raw_span[1] <= boundary
                || fragment.raw_span[1] > word[1]
                || !fragment.interval.valid()
            {
                return None;
            }
            boundary = fragment.raw_span[1];
        }
        (boundary == word[1]).then(|| Self {
            intervals: matching
                .iter()
                .map(|fragment| fragment.interval.clone())
                .collect(),
            fragments: matching,
            manual: false,
        })
    }
    /// A pending edit is represented as None by the attachment validator.
    pub fn effective(supplied: Option<Self>, manual: Option<Interval>) -> Option<Self> {
        match manual.filter(Interval::valid) {
            Some(interval) => Some(Self {
                intervals: vec![interval],
                fragments: Vec::new(),
                manual: true,
            }),
            None => supplied,
        }
    }
    pub fn active(&self, playback_ms: i64, delay_ms: i64, selection_bound: Option<i64>) -> bool {
        playback_ms.checked_sub(delay_ms).is_some_and(|lyric_ms| {
            self.intervals.iter().enumerate().any(|(index, interval)| {
                interval.active(
                    lyric_ms,
                    self.intervals
                        .get(index + 1)
                        .map(|next| next.start_ms)
                        .or(selection_bound),
                )
            })
        })
    }
}
pub fn tap_lyric_ms(playback_ms: i64, saved_delay_ms: i64) -> Option<i64> {
    playback_ms.checked_sub(saved_delay_ms)
}
pub fn playback_seek(lyric_ms: i64, delay_ms: i64, duration_ms: i64) -> Option<i64> {
    lyric_ms
        .checked_add(delay_ms)
        .map(|time| time.clamp(0, duration_ms.max(0)))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fragment(span: [usize; 2], start: i64, end: Option<i64>) -> Fragment {
        Fragment {
            raw_span: span,
            interval: Interval {
                start_ms: start,
                end_ms: end,
            },
            source: "synthetic".into(),
        }
    }
    #[test]
    fn kana_fragments_inside_a_node_are_valid_word_timing_with_real_gaps() {
        let fragments = vec![
            fragment([0, 3], 100, Some(150)),
            fragment([3, 6], 200, Some(250)),
            fragment([6, 9], 300, Some(400)),
        ];
        let word = WordTiming::supplied([0, 9], &fragments).unwrap();
        assert!(word.active(100, 0, None));
        assert!(!word.active(175, 0, None));
        assert!(word.active(350, 0, None));
        assert!(!word.active(400, 0, None));
        assert_eq!(word.fragments, fragments);
    }
    #[test]
    fn a_joined_word_can_use_one_fragment_but_coarse_cross_word_timing_cannot() {
        let whole = vec![fragment([0, 9], 100, None)];
        assert!(WordTiming::supplied([0, 9], &whole).is_some());
        assert!(WordTiming::supplied([0, 6], &whole).is_none());
        assert!(WordTiming::supplied([0, 9], &[fragment([0, 3], 100, None)]).is_none());
    }
    #[test]
    fn manual_timing_shadows_supplied_ends_and_reset_restores_source() {
        let supplied = WordTiming::supplied([0, 3], &[fragment([0, 3], 100, Some(200))]).unwrap();
        let selected = WordTiming::effective(
            Some(supplied.clone()),
            Some(Interval {
                start_ms: 500,
                end_ms: None,
            }),
        )
        .unwrap();
        assert!(selected.manual);
        assert_eq!(selected.intervals[0].end_ms, None);
        assert!(!selected.active(150, 0, None));
        assert!(selected.active(700, 0, Some(800)));
        assert!(!selected.active(800, 0, Some(800)));
        assert_eq!(
            WordTiming::effective(Some(supplied.clone()), None),
            Some(supplied)
        );
    }
    #[test]
    fn taps_use_lyric_time_and_changing_delay_never_rewrites_them() {
        let saved = tap_lyric_ms(12_000, 500).unwrap();
        assert_eq!(saved, 11_500);
        let word = WordTiming::effective(
            None,
            Some(Interval {
                start_ms: saved,
                end_ms: Some(11_600),
            }),
        )
        .unwrap();
        assert!(word.active(12_000, 500, None));
        assert!(!word.active(12_000, 750, None));
        assert!(word.active(12_250, 750, None));
        assert_eq!(word.intervals[0].start_ms, saved);
        assert_eq!(tap_lyric_ms(100, 500), Some(-400));
        assert_eq!(playback_seek(saved, 750, 20_000), Some(12_250));
        assert_eq!(playback_seek(-400, 0, 20_000), Some(0));
    }
    #[test]
    fn malformed_fragments_and_times_never_become_coverage() {
        assert!(
            WordTiming::supplied(
                [0, 9],
                &[fragment([0, 6], 100, None), fragment([3, 9], 200, None)]
            )
            .is_none()
        );
        assert!(
            !Interval {
                start_ms: 100,
                end_ms: Some(100)
            }
            .valid()
        );
        assert_eq!(tap_lyric_ms(i64::MIN, 1), None);
        assert_eq!(playback_seek(i64::MAX, 1, 20_000), None);
    }
}
