"""Pure monotonic decoding of observed native timestamp-class distributions.

No neural model, source phones, TIFA observations or reference clocks are inputs.
Every successful path owns exactly two actual native classes per original word.
The caller authenticates original source bytes and waveform identity. This helper
checks structural owner order/spans; it does not authenticate text content.
"""

import math
import struct
from fractions import Fraction
from pathlib import Path

import numpy as np

MIN_WORD_MS = 80
DROP_ARMS = (
    ("peak_drop_0", 0.0),
    ("peak_drop_ln2", math.log(2)),
    ("peak_drop_ln10", math.log(10)),
)


def read_QWTLOG02(path):
    """Return real logits and runtime class geometry from the observer header."""
    raw = Path(path).read_bytes()
    if len(raw) < 28 or raw[:8] != b"QWTLOG02":
        raise ValueError("invalid_native_timestamp_v2_ledger_magic")
    version, rows, classes, step, origin = struct.unpack_from("<IIIII", raw, 8)
    if (
        version != 2
        or not rows
        or rows % 2
        or not classes
        or not step
        or origin != 0
        or len(raw) != 28 + rows * classes * 4
    ):
        raise ValueError("invalid_native_timestamp_v2_shape_step_origin_or_bytes")
    logits = np.frombuffer(raw, dtype="<f4", offset=28).reshape(rows, classes).copy()
    metadata = {
        "ledger_schema_version": version,
        "marker_rows": rows,
        "classify_num": classes,
        "timestamp_segment_time_ms": step,
        "clip_relative_origin_ms": origin,
        "class_time_mapping": "class_index_times_timestamp_segment_time_ms",
        "all_timestamp_classes_known": True,
        "original_owner_count": rows // 2,
    }
    return logits, metadata


def validate(raw_logits, owners, metadata, crop_duration_ms):
    if not isinstance(owners, list) or not owners:
        raise ValueError("missing_complete_original_owners")
    if metadata.get("original_owner_count") != len(owners):
        raise ValueError("original_owner_denominator_mismatch")
    if (
        type(metadata.get("clip_relative_origin_ms")) not in (int, float)
        or metadata.get("clip_relative_origin_ms") != 0
        or metadata.get("class_time_mapping")
        != "class_index_times_timestamp_segment_time_ms"
    ):
        raise ValueError("unknown_or_nonzero_timestamp_origin_or_class_mapping")
    step = metadata.get("timestamp_segment_time_ms")
    if type(step) not in (int, float) or not math.isfinite(step) or step <= 0:
        raise ValueError("missing_or_invalid_native_timestamp_step")
    if metadata.get("all_timestamp_classes_known") is not True:
        raise ValueError("unknown_timestamp_classes_not_permitted")
    if (
        type(crop_duration_ms) not in (int, float)
        or not math.isfinite(crop_duration_ms)
        or crop_duration_ms <= 0
    ):
        raise ValueError("invalid_actual_crop_duration")
    a = np.asarray(raw_logits)
    if (
        type(metadata.get("classify_num")) is not int
        or a.dtype.kind != "f"
        or a.ndim != 2
        or a.shape[0] != 2 * len(owners)
        or a.shape[1] != metadata.get("classify_num")
        or not a.shape[1]
    ):
        raise ValueError("marker_rows_or_actual_class_count_mismatch")
    if "marker_rows" in metadata and (
        type(metadata["marker_rows"]) is not int
        or metadata["marker_rows"] != a.shape[0]
    ):
        raise ValueError("metadata_marker_rows_mismatch_actual_complete_owner_sequence")
    # -inf is an impossible observation, never a selectable class. NaN/+inf do
    # not define a full-vocabulary probability distribution and reject the cue.
    a = a.astype(np.float64, copy=True)
    if (
        np.isnan(a).any()
        or np.isposinf(a).any()
        or not np.isfinite(a).any(axis=1).all()
    ):
        raise ValueError("NaN_positive_inf_or_no_finite_timestamp_class")
    previous_end = -1
    ids = set()
    for i, owner in enumerate(owners):
        if (
            type(owner.get("owner_index")) is not int
            or owner.get("owner_index") != i
            or not isinstance(owner.get("owner_id"), str)
            or not owner["owner_id"]
            or owner["owner_id"] in ids
        ):
            raise ValueError("original_owner_identity_or_order_mismatch")
        ids.add(owner["owner_id"])
        span = owner.get("raw_span")
        if (
            not isinstance(span, list)
            or len(span) != 2
            or any(type(v) is not int for v in span)
            or not 0 <= span[0] < span[1]
            or span[0] < previous_end
        ):
            raise ValueError("invalid_or_overlapping_original_UTF8_owner_span")
        previous_end = span[1]
    return a, Fraction(str(step)), Fraction(str(crop_duration_ms))


def full_vocab_log_softmax(logits):
    peaks = np.max(logits, axis=1)
    shifted = logits - peaks[:, None]
    log_normalizer = np.log(np.exp(shifted).sum(axis=1))
    result = shifted - log_normalizer[:, None]
    return result


def prefix_max_earliest(values):
    prefix = np.maximum.accumulate(values)
    previous = np.r_[-np.inf, prefix[:-1]]
    new_max = values > previous
    indices = np.maximum.accumulate(np.where(new_max, np.arange(len(values)), -1))
    return prefix, indices


def _path(logps, interior, minimum_class_distance, max_drop):
    rows, classes = logps.shape
    peak = np.max(logps, axis=1)
    allowed = np.isfinite(logps) & interior[None, :]
    if max_drop is not None:
        allowed &= (peak[:, None] - logps) <= max_drop
    score = np.where(allowed[0], logps[0], -np.inf)
    back = np.full((rows, classes), -1, dtype=np.int32)
    columns = np.arange(classes)
    for marker in range(1, rows):
        prefix, indices = prefix_max_earliest(score)
        # start→end requires80ms; end→next start allows shared boundary.
        limit = columns - (minimum_class_distance if marker % 2 else 0)
        valid = allowed[marker] & (limit >= 0)
        previous = np.full(classes, -np.inf)
        predecessors = np.full(classes, -1, dtype=np.int32)
        previous[valid] = prefix[limit[valid]]
        predecessors[valid] = indices[limit[valid]]
        valid &= np.isfinite(previous) & (predecessors >= 0)
        score = np.where(valid, previous + logps[marker], -np.inf)
        back[marker, valid] = predecessors[valid]
    if not np.isfinite(score).any():
        return None
    # np.argmax returns earliest index on an exact floating-point tie.
    final = int(np.argmax(score))
    path = [final]
    for marker in range(rows - 1, 0, -1):
        final = int(back[marker, final])
        if final < 0:
            raise AssertionError("broken_complete_native_timestamp_backtrace")
        path.append(final)
    return list(reversed(path))


def decode_timestamp_classes(
    raw_logits, owners, metadata, crop_duration_ms, *, min_source_word_ms=80
):
    logits, step, duration = validate(raw_logits, owners, metadata, crop_duration_ms)
    if type(min_source_word_ms) is not int or min_source_word_ms not in (0, 80):
        raise ValueError("only_frozen_source_min0_and_min80_conditions_permitted")
    logps = full_vocab_log_softmax(logits)
    rows, classes = logps.shape
    minimum_bins_fraction = Fraction(min_source_word_ms) / step
    minimum_bins = (
        minimum_bins_fraction.numerator + minimum_bins_fraction.denominator - 1
    ) // minimum_bins_fraction.denominator
    times = [step * i for i in range(classes)]
    interior = np.array([0 < t < duration for t in times], dtype=bool)
    peaks = np.argmax(logps, axis=1).tolist()

    def package(name, path, max_drop, require_constraints=True):
        if path is None:
            return {
                "arm": name,
                "status": "whole_cue_withheld_no_complete_feasible_path",
                "max_per_marker_peak_relative_logp_drop": max_drop,
                "original_owner_count": len(owners),
                "words": [
                    {
                        "owner": dict(o),
                        "interval_ms": None,
                        "status": "whole_cue_withheld",
                        "word_timing_qualified": False,
                        "qualifying_word_interval_ms": None,
                    }
                    for o in owners
                ],
                "marker_observations": [],
                "selected_classes": None,
                "full_vocab_path_log_probability": None,
            }
        markers = []
        for marker, c in enumerate(path):
            p = float(logps[marker, c])
            best = float(np.max(logps[marker]))
            drop = best - p
            assert math.isfinite(p) and np.isfinite(logits[marker, c])
            markers.append(
                {
                    "marker_index": marker,
                    "owner_index": marker // 2,
                    "endpoint": "start" if marker % 2 == 0 else "end",
                    "selected_actual_native_class": int(c),
                    "selected_class_time_ms": float(times[c]),
                    "raw_argmax_class": int(peaks[marker]),
                    "changed_from_raw_argmax": c != peaks[marker],
                    "selected_full_vocabulary_log_probability": p,
                    "selected_full_vocabulary_probability": math.exp(p),
                    "raw_peak_full_vocabulary_log_probability": best,
                    "peak_relative_logp_drop": drop,
                    "probability_relative_to_raw_peak": math.exp(-drop),
                }
            )
        words, source_order, all_physical = [], True, True
        for i, owner in enumerate(owners):
            start, end = times[path[2 * i]], times[path[2 * i + 1]]
            qualified = 0 < start < end < duration and end - start >= MIN_WORD_MS
            source_slot = (
                0 < start <= end < duration and end - start >= min_source_word_ms
            )
            prior_order = i == 0 or times[path[2 * i - 1]] <= start
            source_order &= source_slot and prior_order
            all_physical &= qualified and prior_order
            words.append(
                {
                    "owner": dict(owner),
                    "interval_ms": [float(start), float(end)],
                    "selected_start_class": path[2 * i],
                    "selected_end_class": path[2 * i + 1],
                    "strict_interior_min80ms": bool(qualified),
                    "nonoverlap_with_prior": bool(prior_order),
                    "source_slot_constraints_satisfied": bool(
                        source_slot and prior_order
                    ),
                    "word_timing_qualified": bool(qualified and prior_order),
                    "qualifying_word_interval_ms": [float(start), float(end)]
                    if qualified and prior_order
                    else None,
                    "word_status": "observed_qualifying_word_interval"
                    if qualified and prior_order
                    else "observed_timestamp_point_invalid_for_word_timing"
                    if start == end
                    else "observed_slot_invalid_for_word_timing",
                    "observed_class_interval_no_interpolation": True,
                }
            )
        if require_constraints:
            assert source_order and len(words) == len(owners)
            if max_drop is not None:
                assert all(m["peak_relative_logp_drop"] <= max_drop for m in markers)
        status = (
            (
                "complete_observed_class_path"
                if all_physical
                else "complete_source_class_path_with_unqualified_word_slots"
            )
            if source_order
            else "raw_argmax_has_invalid_geometry_or_order"
        )
        return {
            "arm": name,
            "status": status,
            "max_per_marker_peak_relative_logp_drop": max_drop,
            "original_owner_count": len(owners),
            "selected_classes": [int(i) for i in path],
            "words": words,
            "marker_observations": markers,
            "full_vocab_path_log_probability": float(
                sum(logps[i, c] for i, c in enumerate(path))
            ),
            "zero_duration_source_point_slots": sum(
                w["interval_ms"][0] == w["interval_ms"][1] for w in words
            ),
            "physically_qualifying_word_count": sum(
                w["word_timing_qualified"] for w in words
            ),
            "maximum_marker_peak_relative_logp_drop": max(
                m["peak_relative_logp_drop"] for m in markers
            ),
            "changed_marker_count_from_raw_argmax": sum(
                c != peaks[i] for i, c in enumerate(path)
            ),
        }

    arms = [
        package(
            "unrestricted_monotonic", _path(logps, interior, minimum_bins, None), None
        )
    ]
    arms.extend(
        package(name, _path(logps, interior, minimum_bins, cap), cap)
        for name, cap in DROP_ARMS
    )
    return {
        "schema": "model-free-native-timestamp-class-monotonic-decoder-v2",
        "metadata_unmodified": dict(metadata),
        "actual_crop_duration_ms": float(duration),
        "source_slot_minimum_duration_ms": min_source_word_ms,
        "physical_word_qualification_minimum_duration_ms": MIN_WORD_MS,
        "metadata_derived_minimum_class_distance": minimum_bins,
        "all_original_owner_count": len(owners),
        "marker_rows": rows,
        "actual_native_class_count": classes,
        "probability_semantics": "Full-vocabulary logsoftmax over ALL actual finite native timestamp classes BEFORE crop, order or peak-drop masks. No candidate-mask renormalization.",
        "tie_policy": "Exact float64 objective ties use earliest predecessor class at each prefix and earliest final class; equivalently stable reverse-marker lexicographic class order. No epsilon score ties.",
        "raw_argmax": package(
            "raw_independent_argmax", peaks, None, require_constraints=False
        ),
        "arms": arms,
        "no_original_owners_dropped": True,
        "no_TIFA_reference_phone_or_model_forward_inputs": True,
    }


def decode_all_eight_frozen_conditions(raw_logits, owners, metadata, crop_duration_ms):
    profiles = {
        str(minimum): decode_timestamp_classes(
            raw_logits, owners, metadata, crop_duration_ms, min_source_word_ms=minimum
        )
        for minimum in (80, 0)
    }
    assert (
        profiles["80"]["raw_argmax"]["selected_classes"]
        == profiles["0"]["raw_argmax"]["selected_classes"]
    )
    conditions = []
    for minimum in (80, 0):
        for arm in profiles[str(minimum)]["arms"]:
            conditions.append(
                {
                    "condition_id": f"source_min{minimum}ms/{arm['arm']}",
                    "source_slot_minimum_duration_ms": minimum,
                    "physical_word_qualification_minimum_duration_ms": MIN_WORD_MS,
                    **arm,
                }
            )
    assert len(conditions) == 8
    return {
        "schema": "native-Qwen-timestamp-eight-frozen-conditions-v1",
        "all_original_owner_count": len(owners),
        "metadata_unmodified": dict(metadata),
        "actual_crop_duration_ms": crop_duration_ms,
        "raw_independent_argmax_diagnostic": profiles["80"]["raw_argmax"],
        "conditions": conditions,
        "min0_point_slots_are_invalid_word_timings": True,
        "condition_winner_or_per_word_best_not_selected": True,
        "all_actual_full_vocab_scores_without_probability_mask_renormalization": True,
    }
