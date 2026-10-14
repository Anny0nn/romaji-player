# Singing test catalog

The catalog contains **61 unique Spotify recording IDs**: fourteen existing recordings
and 47 additions. The submitted 53-link list contains six recordings already in the
existing suite. Deduplication uses recording IDs; different versions remain distinct.

All 47 new recordings have completed an initial Experimental measurement, saving
**11,756/13,401 words (87.7%)**. The combined catalog
retains **15,265/17,561 (86.9%)**. The original fourteen authenticated
receipts are reused; they are not new measurements or a fresh accuracy holdout.
Retained intervals measure coverage, not correct sung readings or endpoint accuracy.

Later candidate trials use the frozen **ten-song set** marked below: seven lowest-
completeness recordings and three highest-completeness recordings below 100%. Fully
covered songs remain known-reading and persistence fixtures. Ranking uses exact ratios,
track-ID tie breaks, a single recipe/model identity, and immutable source/result hashes.
The set is not reranked after gains. See the [extension plan](plans/japanese-lyric-modes.md).

## Initial measurements

Measured on 2026-10-14 on M2 Pro /16 GiB with cached weights, using the Experimental
app recipe at `5483d28`. Three songs initially failed because protocol-2 converter
records exceeded the old 64 KiB reply limit: Monster, NEVER SAY GOODBYE - With ensemble
and Eden. All three completed after transport fix `6faad84`, which raises only the
bounded reply capacity to 1 MiB; requests, targets, model weights and acoustic gates
are unchanged. Initial failure logs and successful retry provenance remain private;
the other 44 new results were not replaced or rerun.

All 47 new results passed native reopening, reconversion across the five views and
earlier-version restoration checks. Median new-song processing time was
**179.0 seconds**
(range 141.8–254.0).
The largest recorded command/child maximum RSS was
**3.59 GB**; this is not a simultaneous
process-tree or full unified-memory peak. Download latency and capture time are excluded.
These are shared-machine observations, including concurrent compilation during retries,
not a controlled latency comparison against earlier releases.

GIRI GIRI has two dotted-kana lines whose dictionary node cannot be attached to each
displayed syllable unambiguously. Japanese mode correctly uses line highlighting for
those lines; the other script spans and all 239 saved word intervals survive reopening.
The acceptance check initially required exact original-script spans on every line,
contradicting the approved fallback. It now verifies that fallback explicitly, with a
synthetic dotted-kana regression, and still requires exact coverage, all usable script
spans, playback/delay behavior and earlier-version restoration. Saved results are unchanged.

All 47 new recordings were captured with the preserved authorized helper. Ten transient
audio-preparation failures succeeded on a bounded retry without rebuilding it or asking
for another login. 絆ノ奇跡 needed an explicit private import of
[LRCLIB record 24116704](https://lrclib.net/api/get/24116704), matching Spotify's title,
both artists and exact 223.32-second duration. LRCLIB supplies no Spotify ID/ISRC for
that record; the match is by metadata/duration. The default artist lookup missed the
collaborative credit. This input therefore measures alignment after a documented source
import, not automatic source discovery. User app data and caches were not modified.

Audio, full lyrics, source snapshots, per-word observations and model files remain
outside Git. URLs below identify the exact tested recording.

| Recording                                                                                  | Retained / total | Coverage | Seconds | Trial set      |
| ------------------------------------------------------------------------------------------ | ---------------: | -------: | ------: | -------------- |
| [今世大革命](https://open.spotify.com/track/5cDdNqff2mAutAWAM2Zs2c)                        |          199/246 |    80.9% |   163.6 | —              |
| [Koino Uta](https://open.spotify.com/track/15St0qWPnH4xKflV39vk28)                         |          252/307 |    82.1% |   161.7 | —              |
| [SAKURA](https://open.spotify.com/track/1lTfD2M6UpJRWi3YLb8qb5)                            |          265/265 |   100.0% |   229.2 | Excluded: 100% |
| [うれしくて](https://open.spotify.com/track/25C3HZIvRGGtkasbrZe7D1)                        |          363/423 |    85.8% |   263.7 | —              |
| [departure!](https://open.spotify.com/track/4cH6RfZ1qIuz6sumRoDEGK)                        |          209/221 |    94.6% |   171.5 | —              |
| [Tabi no Tochuu](https://open.spotify.com/track/6KeWalxT7jDYdNfwiBtBzt)                    |          153/153 |   100.0% |   183.9 | Excluded: 100% |
| [spiral](https://open.spotify.com/track/6xAIVrhyFQaHwPVWfUvWvE)                            |          238/245 |    97.1% |   159.4 | —              |
| [Bling-Bang-Bang-Born](https://open.spotify.com/track/0kdqcbwei4MDWFEX5f33yG)              |          348/473 |    73.6% |   164.1 | —              |
| [Just Awake](https://open.spotify.com/track/1Gqpa08T7eBAvPQj9O9L2Q)                        |          183/306 |    59.8% |   161.5 | Low            |
| [NEVER SAY GOODBYE](https://open.spotify.com/track/1NVQvAvYhYUluRrRQpdCjg)                 |          369/430 |    85.8% |   194.4 | —              |
| [the WORLD](https://open.spotify.com/track/1g0SlTCGN9j3OicWHfSKEn)                         |          135/153 |    88.2% |   153.4 | —              |
| [色彩](https://open.spotify.com/track/1uveEvgKX4irLcp1BUTIFD)                              |          271/291 |    93.1% |   143.9 | —              |
| [天天天国地獄国](https://open.spotify.com/track/2dkIbR4mudsHg45av3YwxQ)                    |          265/377 |    70.3% |   192.7 | Low            |
| [君のせい](https://open.spotify.com/track/7jEwBMtA7gM43NxiuvfF3h)                          |          259/270 |    95.9% |   175.9 | —              |
| [感電](https://open.spotify.com/track/6H0PLsSYMzDOqhLgyOlzIj)                              |          324/334 |    97.0% |   202.2 | —              |
| [Kyouran Hey Kids!!](https://open.spotify.com/track/38kcwx5znepLWCIBID0Bwm)                |          164/246 |    66.7% |   173.3 | Low            |
| [doppelgänger](https://open.spotify.com/track/22pJeRZ0Mex0B85PQD4mUD)                      |          323/416 |    77.6% |   167.4 | —              |
| [遥か彼方](https://open.spotify.com/track/052C0m9kD30nZqcPWPPRqm)                          |          133/143 |    93.0% |   162.6 | —              |
| [CROW](https://open.spotify.com/track/0QGWqZnE4C5MU4YMWG9BOk)                              |          243/244 |    99.6% |   191.8 | High           |
| [モノトーン](https://open.spotify.com/track/42XeicjBjdyu7boDDtHkvu)                        |          319/326 |    97.9% |   165.4 | —              |
| [ファタール - Fatal](https://open.spotify.com/track/7gJD9BarjoFwL2BNQ0rpWT)                |          328/390 |    84.1% |   182.7 | —              |
| [Dawn in the Adan](https://open.spotify.com/track/5Wdyg2LLFZPPlYUntexViV)                  |          115/117 |    98.3% |   190.5 | —              |
| [のびしろ](https://open.spotify.com/track/3bbIIVIwBoLqVcLebiEJFo)                          |          420/440 |    95.5% |   190.3 | —              |
| [かつて天才だった俺たちへ](https://open.spotify.com/track/4qjpey2aljl28C40NmTcgQ)          |          344/412 |    83.5% |   179.0 | —              |
| [たぶん](https://open.spotify.com/track/398dL22bDbKbAmiOnPaq7o)                            |          294/295 |    99.7% |   176.2 | High           |
| [ベルベットの詩](https://open.spotify.com/track/2N4lCwOeFRX7qrbMPRcZ7d)                    |          290/327 |    88.7% |   193.5 | —              |
| [アイドル](https://open.spotify.com/track/7ovUcF5uHTBRzUpB6ZOmvt)                          |          392/407 |    96.3% |   178.3 | —              |
| [ギターと孤独と蒼い惑星](https://open.spotify.com/track/1rgncjmlpHMP3DBhpagyVb)            |          245/252 |    97.2% |   160.2 | —              |
| [絆ノ奇跡](https://open.spotify.com/track/2VBLFxCUyFp5BfmsZpxcis)                          |          208/214 |    97.2% |   174.3 | —              |
| [CHAINSAW BLOOD](https://open.spotify.com/track/3lUOzabhWYyRImRszpJGOU)                    |          225/312 |    72.1% |   162.3 | —              |
| [サクラミツツキ](https://open.spotify.com/track/4Q8Xekfd9ihkVPCBxGK0ec)                    |          195/200 |    97.5% |   153.4 | —              |
| [crossing field](https://open.spotify.com/track/4BvuZVf9KyBN3QiPfeI9hw)                    |          191/208 |    91.8% |   170.5 | —              |
| [Monster](https://open.spotify.com/track/6MWSM29PKOAyGPl2Xtnt1j)                           |          386/466 |    82.8% |   165.5 | —              |
| [メフィスト](https://open.spotify.com/track/45LUKiex0D78VuhP3Oz6mG)                        |          225/238 |    94.5% |   160.4 | —              |
| [Suzume](https://open.spotify.com/track/1n1y2kFPISpF9WGD3JaFo5)                            |          244/290 |    84.1% |   172.8 | —              |
| [NEVER SAY GOODBYE - With ensemble](https://open.spotify.com/track/6GuC4atFKmPfVAE8nPheyy) |          358/432 |    82.9% |   213.6 | —              |
| [ブルーバード - 2021 Remastered](https://open.spotify.com/track/2tsWKbVFxGMAAzYqRZMnZ3)    |          174/175 |    99.4% |   154.4 | —              |
| [BAKU](https://open.spotify.com/track/6IJ777JlDiPkA8SeIhBIqF)                              |          241/250 |    96.4% |   168.0 | —              |
| [Cry Baby](https://open.spotify.com/track/7nF9c1EmRF3BNAtKDCwUAK)                          |          215/238 |    90.3% |   176.3 | —              |
| [DESPERADO](https://open.spotify.com/track/1jFdZdOTsMqrntJjGKd3C2)                         |          338/458 |    73.8% |   244.4 | —              |
| [LOST IN PARADISE](https://open.spotify.com/track/7kRKlFCFLAUwt43HWtauhX)                  |          330/476 |    69.3% |   254.0 | Low            |
| [ピースサイン - Peace Sign](https://open.spotify.com/track/364JzOajs76bJymjHm3sVY)         |          366/378 |    96.8% |   214.8 | —              |
| [KICK BACK](https://open.spotify.com/track/3khEEPRyBeOUabbmOPJzAG)                         |          230/295 |    78.0% |   168.4 | —              |
| [GIRI GIRI](https://open.spotify.com/track/5RtsmtLsEnwa96TEf56tJQ)                         |          239/304 |    78.6% |   204.5 | —              |
| [ホタルノヒカリ](https://open.spotify.com/track/7AffKWcNn5Zv7QFgScW2ox)                    |          233/238 |    97.9% |   192.2 | —              |
| [紅蓮華](https://open.spotify.com/track/0qMip0B2D4ePEjBJvAtYre)                            |          221/242 |    91.3% |   187.3 | —              |
| [Eden](https://open.spotify.com/track/7CZKnz9mEt8Z638tyY5cKL)                              |          283/295 |    95.9% |   192.0 | —              |
| [残酷な天使のテーゼ](https://open.spotify.com/track/23phSRwoMy48rwFpmuAP8q)                |          204/205 |    99.5% |   188.3 | High           |
| [Black Catcher](https://open.spotify.com/track/2y7f8qkrgIqY5KsfPNcuix)                     |          208/250 |    83.2% |   163.5 | —              |
| [veil](https://open.spotify.com/track/1dGF5ymTyBB2ZmOypkeU1F)                              |          237/257 |    92.2% |   180.1 | —              |
| [嘘](https://open.spotify.com/track/0ODOmKxO0CKv4DzoP3HHIC)                                |          116/167 |    69.5% |   162.9 | Low            |
| [打上花火](https://open.spotify.com/track/7pcTLUekZJQnzDOUDuExVJ)                          |          221/228 |    96.9% |   219.1 | —              |
| [DREAMER](https://open.spotify.com/track/7yKbjz9hzbUY6zmIJ8nDDL)                           |          162/185 |    87.6% |   215.6 | —              |
| [TEENAGE CITY RIOT](https://open.spotify.com/track/3LT9TScu8L84wBZLHfpSwu)                 |          241/351 |    68.7% |   194.0 | Low            |
| [Wild Side](https://open.spotify.com/track/2RSPQJ483jRL1KNtMuKqgh)                         |          170/260 |    65.4% |   141.8 | Low            |
| [Shinkai](https://open.spotify.com/track/44VYdLnwvhn1H1cfieb84a)                           |          202/203 |    99.5% |   196.1 | —              |
| [Kaikai Kitan](https://open.spotify.com/track/6y4GYuZszeXNOXuBFsJlos)                      |          316/343 |    92.1% |   192.4 | —              |
| [紅蓮](https://open.spotify.com/track/39DdyYjRIjRNE1yFTnIAIB)                              |          168/173 |    97.1% |   176.4 | —              |
| [わがまま](https://open.spotify.com/track/6QKCqaDyP2Pazrpk2lbAq4)                          |          199/210 |    94.8% |   185.3 | —              |
| [カワキヲアメク](https://open.spotify.com/track/1gUAX2ImxDsB3YDcyxMXlB)                    |          249/281 |    88.6% |   181.4 | —              |
| [Dance In The Game](https://open.spotify.com/track/5deMG1Ko0ycpPVYPwW0yi8)                 |          227/230 |    98.7% |   166.4 | —              |

## Frozen-set diagnostic

The selected ten recordings contain **2,210/2,927 retained groups**, leaving **717**
gaps across **518 Rust-exported crop windows**. Of the missing groups, 583 contain only
Latin-script letters, 85 contain kanji, 48 contain kana without Latin/kanji, and one is
neither. No selected window reaches the 30-second crop cap. Exact source-span joins
reproduce every saved numerator and denominator; the lyric-bearing ledger remains private.

Latin script does not imply English. The LRCLIB source for 嘘 contains pre-romanized
Japanese, and all 51 missing groups are Latin-script words. The current TIFA language
router sends Latin targets through English pronunciation; existing Japanese loanword
hypotheses do not explicitly reconstruct the original Japanese romaji. This is a concrete
input-routing hypothesis for the next trial, alongside alternate kanji reading selection.
Script counts alone do not diagnose acoustic failures or prove the lyrics match the audio.

A preliminary private probe on 嘘 keeps its 167 original groups and existing intervals.
Literal Japanese-romaji phones add **0** words; additionally expanding marked long vowels
adds **1**, from 116 to 117/167. Nine macron-bearing targets otherwise prevent complete
line parsing. With those targets represented, fresh TIFA retains 43 of the 51 missing
words, but only nine have both endpoints within 150 ms of the singing recognizer;
seven also pass its probability gate, and one survives context/overlap checks against
the saved intervals. This is a diagnostic probe on one selected song, not a promoted
recipe or a correctness benchmark. Its vocals, posteriors, candidate intervals and code
receipts remain private for further investigation. The app has no routing change yet.

## Freezing later trials

`scripts/select-song-suite.py` reads a versioned private measurement file, validates
recording/recipe/source-result identities, and writes a new frozen selection. It sorts
exact retained/total ratios with deterministic ID ties and excludes missing/failed or
100%-covered inputs. A small eligible pool reports a shortfall and uses the nearest
70/30 allocation for its reduced cap. It never replaces an existing selection file.
Pending baselines prevent freezing a set before the initial sweep finishes.

```sh
python3 scripts/select-song-suite.py /private/tmp/measurements.json \
  --cap 10 --output /private/tmp/frozen-song-set.json
```

A measured row contains `track`, `status: "measured"`, `engine`, `model_sha256`, `base_snapshot`,
`timed_words`, `total_words` and `result_sha256`. Other statuses have no invented
coverage score. The file is `{"schema_version": 1, "songs": [...]}`. Freeze the
result and its corresponding source snapshots before tuning; reranking is a separate
documented comparison, not an automatic response to each improvement.
