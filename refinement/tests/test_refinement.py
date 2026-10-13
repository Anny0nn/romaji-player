"""Offline source-identity and negative-evidence checks; no real models or songs."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from refinement_helper import phonetic_units, repair, verify_assets
from refinement_policy import ctc_path


def unit(span, start, end, **extra):
    return {"raw_span": span, "start_ms": start, "end_ms": end, **extra}


def test_no_wrong_verse_is_authorized_by_one_coincident_word():
    targets = [{"raw_span": [i, i + 1], "text": "あ", "romaji": "a"} for i in range(4)]
    baseline = [unit(t["raw_span"], -1, -1) for t in targets]
    trial = {
        "units": [
            unit(t["raw_span"], i * 100, i * 100 + 90) for i, t in enumerate(targets)
        ],
        "raw_units": baseline,
    }
    evidence = [unit(t["raw_span"], -1, -1, mean_probability=0) for t in targets]
    evidence[0] = unit([0, 1], 0, 90, mean_probability=0.9)
    result = repair(baseline, trial, evidence, targets, 1000)
    assert all(u["start_ms"] == -1 for u in result)
    assert [u["text"] for u in result] == [t["text"] for t in targets]


def test_independent_supported_repair_keeps_text_and_existing_real_intervals():
    targets = [{"raw_span": [i, i + 1], "text": "あ", "romaji": "a"} for i in range(3)]
    baseline = [unit([0, 1], 0, 100), unit([1, 2], -1, -1), unit([2, 3], 400, 500)]
    vocals = [unit([0, 1], 0, 100), unit([1, 2], 200, 300), unit([2, 3], 400, 500)]
    evidence = [{**u, "mean_probability": 0.8} for u in vocals]
    result = repair(
        baseline, {"units": vocals, "raw_units": baseline}, evidence, targets, 1000
    )
    assert [u["start_ms"] for u in result] == [0, 200, 400]
    assert all(u["text"] == "あ" for u in result)
    # Unmapped original words remain part of the line-consistency denominator.
    limited = repair(
        baseline,
        {"units": vocals, "raw_units": baseline},
        evidence,
        targets,
        1000,
        source_words=10,
    )
    assert limited[1]["start_ms"] == -1
    evidence[1]["raw_span"] = [0, 1]
    with pytest.raises(ValueError, match="anchors"):
        repair(
            baseline, {"units": vocals, "raw_units": baseline}, evidence, targets, 1000
        )


def test_ctc_uses_observed_20ms_grid_and_25ms_window_without_duration_scaling():
    logp = np.full((8, 4), -10.0)
    logp[np.arange(8), [0, 1, 1, 2, 0, 3, 3, 0]] = 0
    targets = [{"raw_span": [0, 1], "romaji": "a"}, {"raw_span": [1, 2], "romaji": "b"}]
    result = phonetic_units(logp, 0, targets, {"a": 1, "|": 2, "b": 3})
    assert (result[0]["start_ms"], result[0]["end_ms"]) == (20, 65)
    assert (result[1]["start_ms"], result[1]["end_ms"]) == (100, 145)
    assert ctc_path([[0, -1]], [1, 1]) is None


def test_invalid_model_bytes_fail_before_any_network_or_model_import(
    tmp_path, monkeypatch
):
    import refinement_helper

    content = b"synthetic checkpoint"
    asset = {
        "path": "tiny.safetensors",
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    (tmp_path / "refinement-model-files.json").write_text(json.dumps([asset]))
    (tmp_path / asset["path"]).write_bytes(content)
    monkeypatch.setattr(refinement_helper, "ROOT", tmp_path)
    verify_assets(tmp_path)
    (tmp_path / asset["path"]).write_bytes(bytes(len(content)))
    with pytest.raises(ValueError, match="integrity"):
        verify_assets(tmp_path)


def test_research_runner_and_app_share_the_measured_policy():
    spec = importlib.util.spec_from_file_location(
        "research", ROOT / "scripts/experiment-phonetic-alignment.py"
    )
    research = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(research)
    assert research.ctc_path([[0, -1], [-1, 0]], [1]) == ctc_path(
        [[0, -1], [-1, 0]], [1]
    )
    assert research.repair_regions.__code__.co_filename == str(
        ROOT / "refinement/refinement_policy.py"
    )
