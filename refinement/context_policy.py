"""Bounded neighboring-phrase timing proposals, with original word ownership.

Joint spans are an internal inference namespace. They are never persisted; every
result is mapped back through the frozen crop/word indices before Rust sees it.
"""

import itertools

from refinement_policy import coherent_line, repair_regions
from tifa_helper import pronunciation


def validate(crops, baseline):
    if len(crops) != len(baseline):
        raise ValueError("Changed context crop count.")
    seen = set()
    for (occurrence, first, last, targets), units in zip(crops, baseline, strict=True):
        if occurrence in seen or not 0 <= first < last or first % 16:
            raise ValueError("Invalid context crop clock or occurrence.")
        seen.add(occurrence)
        if [t["raw_span"] for t in targets] != [u["raw_span"] for u in units]:
            raise ValueError("Changed context source word anchors.")


def joint_crops(crops, baseline, counts):
    validate(crops, baseline)
    jobs = []
    for index in range(len(crops) - 1):
        left, right = crops[index], crops[index + 1]
        if left[1] >= right[1] or right[2] - left[1] > 480000:
            continue
        words, owners, nominated, offset = [], [], [], 0
        for line in (index, index + 1):
            targets = crops[line][3]
            for word, target in enumerate(targets):
                words.append(
                    {**target, "raw_span": [v + offset for v in target["raw_span"]]}
                )
                owners.append((line, word))
                nominated.append(
                    baseline[line][word]["start_ms"] < 0
                    and pronunciation(target["text"], target["romaji"])[1] == "ja"
                )
            offset += max(t["raw_span"][1] for t in targets) + 1
        if any(nominated):
            jobs.append(
                {
                    "crop": (len(jobs), left[1], right[2], words),
                    "owners": owners,
                    "nominated": nominated,
                    "source_words": sum(
                        counts[str(crops[line][0])] for line in (index, index + 1)
                    ),
                }
            )
    return jobs


def apply_context(baseline, crops, jobs, trials, evidence):
    validate(crops, baseline)
    if not len(jobs) == len(trials) == len(evidence):
        raise ValueError("Incomplete context evidence.")
    proposals = []
    for job, trial, proof in zip(jobs, trials, evidence, strict=True):
        _, first, last, targets = job["crop"]
        lines = sorted({line for line, _ in job["owners"]})
        if (
            len(lines) != 2
            or lines[1] != lines[0] + 1
            or not 0 <= lines[0] < lines[1] < len(crops)
        ):
            raise ValueError("Invalid joint source occurrences.")
        expected_owners = [
            (line, word) for line in lines for word in range(len(crops[line][3]))
        ]
        if (
            job["owners"] != expected_owners
            or first != crops[lines[0]][1]
            or last != crops[lines[1]][2]
        ):
            raise ValueError("Changed joint source ownership or Rust crop endpoints.")
        expected = [t["raw_span"] for t in targets]
        if expected != [u["raw_span"] for u in trial["units"]] or expected != [
            u["raw_span"] for u in proof
        ]:
            raise ValueError("Changed joint inference word ownership.")
        current, candidates, checks = [], [], []
        for target, candidate, observation, (line, word), nominated in zip(
            targets, trial["units"], proof, job["owners"], job["nominated"], strict=True
        ):
            source = crops[line][3][word]
            if (
                any(target[k] != source[k] for k in ("text", "romaji"))
                or target["raw_span"][1] - target["raw_span"][0]
                != source["raw_span"][1] - source["raw_span"][0]
            ):
                raise ValueError("Joint target differs from its original source word.")
            original = baseline[line][word]
            offset = (crops[line][1] - first) // 16
            current.append(
                {
                    **original,
                    "raw_span": target["raw_span"],
                    "start_ms": original["start_ms"] + offset
                    if original["start_ms"] >= 0
                    else -1,
                    "end_ms": original["end_ms"] + offset
                    if original["start_ms"] >= 0
                    else -1,
                }
            )
            probability = observation.get("mean_probability", 0)
            supported = (
                offset
                <= candidate["start_ms"]
                < candidate["end_ms"]
                <= offset + (crops[line][2] - crops[line][1]) // 16
                and candidate["end_ms"] - candidate["start_ms"] >= 80
                and 0.45 <= probability <= 1
                and 0 <= observation["start_ms"] < observation["end_ms"]
                and all(
                    abs(candidate[k] - observation[k]) <= 150
                    for k in ("start_ms", "end_ms")
                )
                and pronunciation(target["text"], target["romaji"])[1] == "ja"
            )
            checks.append(
                {**observation, "mean_probability": probability if supported else 0}
            )
            allowed = supported and (original["start_ms"] >= 0 or nominated)
            candidates.append(
                candidate if allowed else {**candidate, "start_ms": -1, "end_ms": -1}
            )
        if not coherent_line(candidates, checks, job["source_words"]):
            continue
        repaired = repair_regions(current, candidates, checks)
        change, recovered = {}, False
        for old, new, (line, word) in zip(
            current, repaired, job["owners"], strict=True
        ):
            if all(old[k] == new[k] for k in ("start_ms", "end_ms")):
                continue
            recovered |= old["start_ms"] < 0 <= new["start_ms"]
            offset = (crops[line][1] - first) // 16
            original = baseline[line][word]
            change[(line, word)] = {
                **original,
                "start_ms": new["start_ms"] - offset,
                "end_ms": new["end_ms"] - offset,
            }
        # Context helps inference but does not extend a source occurrence's
        # admissible clock. Rust validates the same original crop bounds.
        if recovered:
            proposals.append(change)
    # Conflicting contexts cannot vote a timestamp into existence. Reject both
    # affected proposals. Compatible overlapping regions keep their first atomic
    # proposal; do not splice timings from different joint alignments.
    conflicts = set()
    for a, left in enumerate(proposals):
        for b in range(a + 1, len(proposals)):
            right = proposals[b]
            if any(
                any(
                    abs(left[k][field] - right[k][field]) > 150
                    for field in ("start_ms", "end_ms")
                )
                for k in left.keys() & right.keys()
            ):
                conflicts.update((a, b))
    result = [[dict(u) for u in units] for units in baseline]
    committed = set()
    for index, proposal in enumerate(proposals):
        if index in conflicts or committed & proposal.keys():
            continue
        tentative = [[dict(u) for u in units] for units in result]
        for (line, word), unit in proposal.items():
            tentative[line][word] = unit
        # Reject the entire proposal on new overlap; never trim or stretch it.
        if any(
            any(a["end_ms"] > b["start_ms"] for a, b in itertools.pairwise(valid))
            for units in tentative
            for valid in [[u for u in units if u["start_ms"] >= 0]]
        ):
            continue
        result = tentative
        committed.update(proposal)
    return result
