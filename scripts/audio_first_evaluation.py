"""Authentication and phone-error summaries, used only after blind outputs close."""

import json
from pathlib import Path

from audio_first_ctc import edit_counts
from audio_first_models import digest


def read_run(directory, manifest):
    directory = Path(directory)
    recipe_path, complete_path = directory / "recipe.json", directory / "complete.json"
    recipe = json.loads(recipe_path.read_text())
    complete = json.loads(complete_path.read_text())
    if complete["recipe_sha256"] != digest(recipe_path) or recipe[
        "manifest_sha256"
    ] != digest(manifest):
        raise ValueError("Changed recognition recipe or audio manifest.")
    cases = json.loads(Path(manifest).read_text())["cases"]
    if len(cases) != len(complete["records"]):
        raise ValueError("Incomplete recognition run.")
    rows = {}
    for case, saved in zip(cases, complete["records"], strict=True):
        filename = saved["file"]
        if (
            Path(filename).name != filename
            or digest(directory / filename) != saved["sha256"]
        ):
            raise ValueError("Changed recognition record.")
        row = json.loads((directory / filename).read_text())
        if row["case"] != case or row["recipe_sha256"] != complete["recipe_sha256"]:
            raise ValueError("Recognition belongs to different audio or recipe.")
        if case["id"] in rows:
            raise ValueError("Duplicate recognition identity.")
        if row["failure"] is None:
            if set(row["heads"]) != set(recipe["model"]["heads"]):
                raise ValueError("Successful recognition is missing an acoustic head.")
        elif row["heads"]:
            raise ValueError("Failed recognition cannot contain successful heads.")
        if recipe["engine"] == "whisper" and row.get("transcript"):
            path = row["transcript"]
            if (
                Path(path).name != path
                or digest(directory / path) != row["transcript_sha256"]
            ):
                raise ValueError("Changed raw Whisper transcript.")
        for head in row["heads"].values():
            if recipe["engine"] == "whisper":
                continue
            path = head["posterior"]
            if (
                Path(path).name != path
                or digest(directory / path) != head["posterior_sha256"]
            ):
                raise ValueError("Changed acoustic posterior.")
        rows[case["id"]] = row
    return recipe, rows, complete


def score_sequences(references, predictions):
    if set(references) != set(predictions):
        raise ValueError("Reference and prediction identities differ.")
    rows = [
        edit_counts(references[key], predictions[key]) for key in sorted(references)
    ]
    totals = {key: sum(row[key] for row in rows) for key in rows[0]} if rows else {}
    count = totals.get("reference_phones", 0)
    totals.update(
        clips=len(rows),
        phone_error_rate=totals.get("errors", 0) / count if count else None,
        exact_clip_fraction=totals.get("exact", 0) / len(rows) if rows else None,
    )
    return totals
