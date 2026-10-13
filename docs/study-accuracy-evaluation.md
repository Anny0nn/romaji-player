# Singing accuracy: implementation experiments

This report records work after approval of the [accuracy plan](plans/singing-accuracy.md)
on 2026-10-13. Tests use the existing fourteen private recordings on an Apple M2 Pro with
16 GiB memory. The shipped Experimental recipe remains at **3,434/4,160 retained words**.
The challengers below are offline experiments; neither timing button enables them yet.

## Reproduced diagnostic

`scripts/diagnose-song-suite.py` joins explicit hashed case, historical TIFA diagnostic and
saved Experimental result inputs. It verifies source UTF-8 spans, exact lyric occurrences,
word grouping and declared coverage. Its private ledger records crop/audio/source identity,
conversion signatures and saved recipe/model identity. It rejects stale or mismatched inputs.

The Rust export test calls the same `crop_targets` function as the app. All fourteen
recording hashes, **671 crop windows** and source target-span lists matched the cached
cases exactly. A regression distinguishes recording origin from a nonzero saved delay.
Legacy diagnostic reasons remain labelled historical, even after validating their windows.

| Measure                                                          |      Result |
| ---------------------------------------------------------------- | ----------: |
| Original words                                                   |       4,160 |
| Saved Experimental timings                                       |       3,434 |
| Missing timings                                                  |         726 |
| Missing spans containing ASCII Latin letters                     |         404 |
| Missing spans containing Latin letters and only ASCII characters |         397 |
| Crops reaching 30 seconds                                        |       1/671 |
| Historical TIFA token-agreement rejections among missing spans   |         683 |
| Historical duration / unsupported / incomplete                   | 25 / 12 / 6 |

Latin script is not a language label, and historical rejections do not establish why the
current Experimental recipe abstains. This supports investigating pronunciation and mixed
language before changing the crop cap. Full lyric/audio evidence stays outside the checkout.

## Pronunciation selection pilot

TIFA normally takes the first valid whole-word pronunciation path. The challenger uses
its pinned backend's acoustic scorer to select complete alternatives, preserving phone
ownership. It changes no numerical vendor source, timing thresholds or source mappings.

Across all fourteen mix recordings, it retained **3,118/4,160**, compared with TIFA's
3,121. It gained 36 spans, lost 39 and moved 42 shared intervals by more than 150 ms at
either endpoint. The run took **56.1 seconds**, including one model load for the suite;
the process lifetime peak RSS was **1.25 GB**. This is not a per-song app latency or
unified GPU-memory measurement.

| Recording                 | Baseline TIFA | Scored alternatives | Gains | Losses | Shared spans moved >150 ms |
| ------------------------- | ------------: | ------------------: | ----: | -----: | -------------------------: |
| Bling-Bang-Bang-Born      |           303 |                 312 |    24 |     15 |                         16 |
| Just Awake                |           178 |                 172 |     2 |      8 |                         17 |
| NEVER SAY GOODBYE         |           341 |                 337 |     8 |     12 |                          7 |
| departure!                |           204 |                 204 |     1 |      1 |                          2 |
| 今世大革命                |           154 |                 152 |     1 |      3 |                          0 |
| Remaining nine recordings |     unchanged |           unchanged |     0 |      0 |                          0 |

**Decision:** reject replacing the first-path strategy. Candidate scoring may later
nominate a bounded alternative, but these results do not justify accepting its choice.
TIFA's token-agreement diagnostic is self-consistency, not a calibrated correctness score.

The CLI exposes `--score-pronunciations`; the helper defaults to the original behavior.
An offline regression checks that an alternative adding a phone is selected as a whole
word, rather than mixing individual phones from incompatible readings.

## Whisper language pilot

The shipped transcription helper now permits explicit Japanese, English or detection
**for experiments**, with Japanese remaining its default. It stays blind to source lyrics,
uses transcription rather than translation, and releases the model between recordings.

Full-song detection ran on the mix and Kim vocals for Tabi no Tochuu, Just Awake,
Bling-Bang-Bang-Born and 天天天国地獄国: **all eight inputs detected Japanese**. Total
decode time was **258.9 seconds** with weights cached. These initial detection runs do not
measure reading precision or recovery. They show that detection alone will not route
those mixed-language songs to an English pass.

`scripts/experiment-song-language.py` verifies pinned assets and recording hashes, records
decoder/model-manifest identity and explicit language settings, and writes private segment
results without changing app documents. The initial eight pilot outputs predate the added
decoder/model provenance fields; they remain exploratory. Bounded English retries need
an independently evaluated English acoustic path before any app promotion.

## Human phone-boundary calibration

The [PJS corpus](https://sites.google.com/site/shinnosuketakamichi/research-topics/pjs_corpus)
and [human monophone relabels](https://github.com/UtaUtaUtau/pjs-manual-labels) state
CC BY-SA 4.0. Their audio and labels are stored privately. Twenty whole-song IDs were
reserved before inspecting label contents; eighty form the development partition.

`scripts/benchmark-singing-phones.py` hashes the archives, extracted recordings/labels,
split, recipes and implementation. It imports integer HTK 100 ns times as recording
milliseconds and compares **raw phone boundaries**, with silence excluded. Supplied
reference phones bypass G2P, recognition and app word-retention policy: this is a decoder
boundary calibration, not a reading or word-accuracy evaluation.

On eighty development recordings there were **5,448 non-silence reference phones**.
Thirteen recordings contain uppercase `I/U/O`, whose PJS convention is undocumented;
the runner abstained on those complete sequences rather than dropping or relabelling the
unknown phones. That leaves **4,506 aligned phones and 942 abstentions**.

| Metric on aligned phones            |               Result |
| ----------------------------------- | -------------------: |
| Onset ≤150 ms and offset ≤200 ms    | 4,500/4,506 (99.87%) |
| Onset median / p90 / p95 error      | 3.9 / 12.3 / 18.3 ms |
| Offset median / p90 / p95 error     | 3.8 / 11.7 / 16.5 ms |
| Joint phrase-bootstrap 95% interval |         99.73–99.98% |

Three TIFA skip penalties (0, 0.5 and 1) produced identical boundaries. The complete
three-recipe run took **26.6 seconds** after loading, with **0.85 GB** process lifetime
peak RSS. **Decision:** changing that penalty has no demonstrated value on this reference
pilot. No twenty-song reserved result has been opened or used for tuning.

PJS is one male singer in controlled conditions. `cl` also labels glottal stops in the
human relabel; this score preserves the supplied label instead of claiming a geminate
recognition test. References have no published per-boundary uncertainty; the importer
records it as unknown. [TIFA's release](https://github.com/openvpi/TIFA/releases/tag/v1.0.0)
discloses private training data without enough detail to rule out PJS. The partition is
held out from this project's tuning, **not certified unseen by the pretrained model**.
These results therefore cannot establish 99.87% accuracy on commercial songs.

The heldout command requires a previously frozen receipt matching recipes, archives,
split and implementation. The runner emits no partial per-song heldout reports; evidence
is released only when the entire run finishes. Offline tests cover stale receipts,
partition overlap, HTK units, abstentions and invalid/mismatched prediction identities.

## Reproduction and next checks

Models and private inputs are never downloaded by hooks or unit tests. The diagnostic
manifest contains `cases`, `diagnostics`, `results: [{track, path}]`, `crop_provenance`
and optional `rust_manifests` paths. Outputs require a fresh directory outside git.

```sh
python3 scripts/diagnose-song-suite.py /path/to/private/manifest.json \
  --output /path/to/private/fresh-diagnostic
```

Export app windows explicitly using a private document, its recording, a bundled
romanizer and a fresh output directory:

```sh
ROMAJI_TEST_DOCUMENT=/path/to/private/document.json \
ROMAJI_TEST_PCM=/path/to/private/audio.pcm \
ROMAJI_TEST_MANIFEST_DIR=/path/to/private/fresh-crops \
ROMAJI_HELPER_PATH=/path/to/RomajiRomanizer \
cargo test --locked --no-default-features recorded_song_exports_rust_crop_manifest \
  -- --ignored --exact study::alignment::tests::recorded_song_exports_rust_crop_manifest
```

The PJS private root contains `audio.zip`, `labels.zip`, extracted `audio/<id>_song.wav`,
`labels/<id>.lab`, and `split.json` with disjoint `development` and `heldout` ID lists.
Recipes are a JSON map from names to TIFA skip penalties. Run `--partition development`
first; use `freeze` with a new output directory before a heldout `run --receipt ...`.
Both commands need `--archive`, `--recipes` and `--output`.

The small-vowel mix pilot recovered three words and lost none, but moved five shared
intervals by >150 ms; broad replacement is unsuitable. The vocal trials took 60.5 seconds
(Kim) and 54.4 seconds (Demucs), with process lifetime peak RSS about 0.91 GB each.
A targeted replay joined all 671 source/audio/crop identities in each view to the saved
Experimental result. Both independently checked views recovered the same one word in
色彩 and adjusted one neighboring interval through the existing bounded repair policy.
The other two gaps remained withheld. This is a specific conversion-fallback candidate,
not a passing general-recovery recipe; its application integration and negative controls
remain to be completed. Neighboring-phrase context and repeat localization are next.

The pre-existing pyshiro adapter is not a new result. Checkpoint terms/provenance remain
unresolved for its v2 model and the Intunist models, so this work adds neither runtime
nor weights. No passing general-recovery recipe or packaged app change is claimed yet.

The [SingAlign English model card](https://huggingface.co/pymaster/SingAlign) describes a
singing-specific HuBERT alignment head with separate encoder weights and CC-BY-NC-SA
terms. Its linked toolkit source is unavailable, and bundled TIFA's SSL inference class
is a stub with a different feature/model contract. It is deferred rather than treated
as a compatible checkpoint. [NUS-48E](https://smcnus.comp.nus.edu.sg/) is a possible
private human English-singing phone/word reference if an eligible verifier becomes usable.
