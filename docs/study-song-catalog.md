# Singing test catalog

The catalog contains **61 unique Spotify recording IDs**: fourteen existing recordings
and 47 additions. The submitted 53-link list contains six recordings already in the
existing suite. Deduplication uses recording IDs; different versions of a song remain
different test inputs.

Every new recording gets one initial Experimental measurement before ranking. Later
candidate trials use a frozen ten-song set: seven lowest-completeness recordings and
three highest-completeness recordings below 100%. Failed/unmeasured inputs and fully
covered songs are excluded from the ranking. Fully covered songs still supply known
reading and persistence fixtures. See the [extension plan](plans/japanese-lyric-modes.md).

The initial sweep uses the app recipe at `5483d28`. Existing measurements are in the
[representation evaluation](study-representation-evaluation.md); the new measurements
are in progress. URLs identify test recordings; audio, full lyrics and source snapshots
are not part of this catalog.

| Recording                                                                                  | Initial measurement       |
| ------------------------------------------------------------------------------------------ | ------------------------- |
| [今世大革命](https://open.spotify.com/track/5cDdNqff2mAutAWAM2Zs2c)                        | Existing verified receipt |
| [Koino Uta](https://open.spotify.com/track/15St0qWPnH4xKflV39vk28)                         | Existing verified receipt |
| [SAKURA](https://open.spotify.com/track/1lTfD2M6UpJRWi3YLb8qb5)                            | Existing verified receipt |
| [うれしくて](https://open.spotify.com/track/25C3HZIvRGGtkasbrZe7D1)                        | Existing verified receipt |
| [departure!](https://open.spotify.com/track/4cH6RfZ1qIuz6sumRoDEGK)                        | Existing verified receipt |
| [Tabi no Tochuu](https://open.spotify.com/track/6KeWalxT7jDYdNfwiBtBzt)                    | Existing verified receipt |
| [spiral](https://open.spotify.com/track/6xAIVrhyFQaHwPVWfUvWvE)                            | Existing verified receipt |
| [Bling-Bang-Bang-Born](https://open.spotify.com/track/0kdqcbwei4MDWFEX5f33yG)              | Existing verified receipt |
| [Just Awake](https://open.spotify.com/track/1Gqpa08T7eBAvPQj9O9L2Q)                        | Existing verified receipt |
| [NEVER SAY GOODBYE](https://open.spotify.com/track/1NVQvAvYhYUluRrRQpdCjg)                 | Existing verified receipt |
| [the WORLD](https://open.spotify.com/track/1g0SlTCGN9j3OicWHfSKEn)                         | Existing verified receipt |
| [色彩](https://open.spotify.com/track/1uveEvgKX4irLcp1BUTIFD)                              | Existing verified receipt |
| [天天天国地獄国](https://open.spotify.com/track/2dkIbR4mudsHg45av3YwxQ)                    | Existing verified receipt |
| [君のせい](https://open.spotify.com/track/7jEwBMtA7gM43NxiuvfF3h)                          | Existing verified receipt |
| [感電](https://open.spotify.com/track/6H0PLsSYMzDOqhLgyOlzIj)                              | New baseline required     |
| [Kyouran Hey Kids!!](https://open.spotify.com/track/38kcwx5znepLWCIBID0Bwm)                | New baseline required     |
| [doppelgänger](https://open.spotify.com/track/22pJeRZ0Mex0B85PQD4mUD)                      | New baseline required     |
| [遥か彼方](https://open.spotify.com/track/052C0m9kD30nZqcPWPPRqm)                          | New baseline required     |
| [CROW](https://open.spotify.com/track/0QGWqZnE4C5MU4YMWG9BOk)                              | New baseline required     |
| [モノトーン](https://open.spotify.com/track/42XeicjBjdyu7boDDtHkvu)                        | New baseline required     |
| [ファタール - Fatal](https://open.spotify.com/track/7gJD9BarjoFwL2BNQ0rpWT)                | New baseline required     |
| [Dawn in the Adan](https://open.spotify.com/track/5Wdyg2LLFZPPlYUntexViV)                  | New baseline required     |
| [のびしろ](https://open.spotify.com/track/3bbIIVIwBoLqVcLebiEJFo)                          | New baseline required     |
| [かつて天才だった俺たちへ](https://open.spotify.com/track/4qjpey2aljl28C40NmTcgQ)          | New baseline required     |
| [たぶん](https://open.spotify.com/track/398dL22bDbKbAmiOnPaq7o)                            | New baseline required     |
| [ベルベットの詩](https://open.spotify.com/track/2N4lCwOeFRX7qrbMPRcZ7d)                    | New baseline required     |
| [アイドル](https://open.spotify.com/track/7ovUcF5uHTBRzUpB6ZOmvt)                          | New baseline required     |
| [ギターと孤独と蒼い惑星](https://open.spotify.com/track/1rgncjmlpHMP3DBhpagyVb)            | New baseline required     |
| [絆ノ奇跡](https://open.spotify.com/track/2VBLFxCUyFp5BfmsZpxcis)                          | New baseline required     |
| [CHAINSAW BLOOD](https://open.spotify.com/track/3lUOzabhWYyRImRszpJGOU)                    | New baseline required     |
| [サクラミツツキ](https://open.spotify.com/track/4Q8Xekfd9ihkVPCBxGK0ec)                    | New baseline required     |
| [crossing field](https://open.spotify.com/track/4BvuZVf9KyBN3QiPfeI9hw)                    | New baseline required     |
| [Monster](https://open.spotify.com/track/6MWSM29PKOAyGPl2Xtnt1j)                           | New baseline required     |
| [メフィスト](https://open.spotify.com/track/45LUKiex0D78VuhP3Oz6mG)                        | New baseline required     |
| [Suzume](https://open.spotify.com/track/1n1y2kFPISpF9WGD3JaFo5)                            | New baseline required     |
| [NEVER SAY GOODBYE - With ensemble](https://open.spotify.com/track/6GuC4atFKmPfVAE8nPheyy) | New baseline required     |
| [ブルーバード - 2021 Remastered](https://open.spotify.com/track/2tsWKbVFxGMAAzYqRZMnZ3)    | New baseline required     |
| [BAKU](https://open.spotify.com/track/6IJ777JlDiPkA8SeIhBIqF)                              | New baseline required     |
| [Cry Baby](https://open.spotify.com/track/7nF9c1EmRF3BNAtKDCwUAK)                          | New baseline required     |
| [DESPERADO](https://open.spotify.com/track/1jFdZdOTsMqrntJjGKd3C2)                         | New baseline required     |
| [LOST IN PARADISE](https://open.spotify.com/track/7kRKlFCFLAUwt43HWtauhX)                  | New baseline required     |
| [ピースサイン - Peace Sign](https://open.spotify.com/track/364JzOajs76bJymjHm3sVY)         | New baseline required     |
| [KICK BACK](https://open.spotify.com/track/3khEEPRyBeOUabbmOPJzAG)                         | New baseline required     |
| [GIRI GIRI](https://open.spotify.com/track/5RtsmtLsEnwa96TEf56tJQ)                         | New baseline required     |
| [ホタルノヒカリ](https://open.spotify.com/track/7AffKWcNn5Zv7QFgScW2ox)                    | New baseline required     |
| [紅蓮華](https://open.spotify.com/track/0qMip0B2D4ePEjBJvAtYre)                            | New baseline required     |
| [Eden](https://open.spotify.com/track/7CZKnz9mEt8Z638tyY5cKL)                              | New baseline required     |
| [残酷な天使のテーゼ](https://open.spotify.com/track/23phSRwoMy48rwFpmuAP8q)                | New baseline required     |
| [Black Catcher](https://open.spotify.com/track/2y7f8qkrgIqY5KsfPNcuix)                     | New baseline required     |
| [veil](https://open.spotify.com/track/1dGF5ymTyBB2ZmOypkeU1F)                              | New baseline required     |
| [嘘](https://open.spotify.com/track/0ODOmKxO0CKv4DzoP3HHIC)                                | New baseline required     |
| [打上花火](https://open.spotify.com/track/7pcTLUekZJQnzDOUDuExVJ)                          | New baseline required     |
| [DREAMER](https://open.spotify.com/track/7yKbjz9hzbUY6zmIJ8nDDL)                           | New baseline required     |
| [TEENAGE CITY RIOT](https://open.spotify.com/track/3LT9TScu8L84wBZLHfpSwu)                 | New baseline required     |
| [Wild Side](https://open.spotify.com/track/2RSPQJ483jRL1KNtMuKqgh)                         | New baseline required     |
| [Shinkai](https://open.spotify.com/track/44VYdLnwvhn1H1cfieb84a)                           | New baseline required     |
| [Kaikai Kitan](https://open.spotify.com/track/6y4GYuZszeXNOXuBFsJlos)                      | New baseline required     |
| [紅蓮](https://open.spotify.com/track/39DdyYjRIjRNE1yFTnIAIB)                              | New baseline required     |
| [わがまま](https://open.spotify.com/track/6QKCqaDyP2Pazrpk2lbAq4)                          | New baseline required     |
| [カワキヲアメク](https://open.spotify.com/track/1gUAX2ImxDsB3YDcyxMXlB)                    | New baseline required     |
| [Dance In The Game](https://open.spotify.com/track/5deMG1Ko0ycpPVYPwW0yi8)                 | New baseline required     |

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
