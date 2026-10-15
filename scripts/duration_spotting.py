"""A complete duration-model word amid a source-independent acoustic background.

An exact semi-Markov sum and MAP path, with a uniform start prior and normalized
discrete state durations. The alternative is background on every frame. This is
conditional acoustic evidence, not recognition confidence or lyric spelling truth.
"""

import math


def _validated_model(emissions, background, duration_logpmf):
    import numpy as np

    emissions = np.asarray(emissions, dtype=np.float64)
    background = np.asarray(background, dtype=np.float64)
    durations = np.asarray(duration_logpmf, dtype=np.float64)
    if (
        emissions.ndim != 2
        or not 0 < emissions.shape[0] <= 1600
        or not 0 < emissions.shape[1] <= 384
        or background.shape != (emissions.shape[0],)
        or not np.isfinite(emissions).all()
        or not np.isfinite(background).all()
        or durations.ndim != 2
        or durations.shape[0] != emissions.shape[1]
        or not 1 < durations.shape[1] <= 2001
        or np.isnan(durations).any()
        or np.isposinf(durations).any()
        or np.any(durations > 1e-6)
        or not np.isneginf(durations[:, 0]).all()
        or not np.allclose(np.logaddexp.reduce(durations, axis=1), 0, atol=1e-6)
    ):
        raise ValueError("Invalid bounded density/duration model.")
    return emissions, background, durations


def spot_word(emissions, background, duration_logpmf):
    """Return measured state frames, boundary marginals and conditional log ratio.

    Inputs are per-frame joint log densities (frames x ordered target states),
    background log densities, and normalized duration PMFs (states x durations;
    duration zero must be impossible). Every target state consumes actual frames.
    Normalize the hypothesis's duration/start prior conditional on fitting inside
    this window; otherwise short windows artificially favor short pronunciations.
    """
    import numpy as np

    emissions, background, durations = _validated_model(
        emissions, background, duration_logpmf
    )
    frames, states = emissions.shape
    duration_count = min(frames, durations.shape[1] - 1)
    d = np.arange(1, duration_count + 1)
    ends = np.arange(frames + 1)
    starts = ends[:, None] - d
    valid = starts >= 0
    safe = np.maximum(starts, 0)
    cumulative = np.vstack(
        [np.zeros(states), (emissions - background[:, None]).cumsum(axis=0)]
    )
    forward = np.full((states + 1, frames + 1), -np.inf)
    best = forward.copy()
    forward[0] = best[0] = -math.log(frames + 1)
    chosen = np.zeros((states, frames + 1), dtype=np.int32)
    # The prior-only pass calculates exactly the mass discarded by the finite
    # window; its normalizer depends on length, never on observed human clocks.
    prior = forward[0].copy()
    for state in range(states):
        local = (
            cumulative[:, state, None] - cumulative[safe, state] + durations[state, d]
        )
        local[~valid] = -np.inf
        forward[state + 1] = np.logaddexp.reduce(local + forward[state, safe], axis=1)
        candidates = local + best[state, safe]
        winners = np.argmax(candidates, axis=1)
        best[state + 1] = candidates[ends, winners]
        chosen[state] = d[winners]
        prior_local = np.where(valid, durations[state, d], -np.inf)
        prior = np.logaddexp.reduce(prior_local + prior[safe], axis=1)
    log_mass = float(np.logaddexp.reduce(forward[-1]))
    normalizer = float(np.logaddexp.reduce(prior))
    if not math.isfinite(log_mass) or not math.isfinite(normalizer):
        return None
    end = int(np.argmax(best[-1]))
    intervals = []
    for state in reversed(range(states)):
        start = end - int(chosen[state, end])
        intervals.append([start, end])
        end = start
    intervals.reverse()

    backward = np.zeros(frames + 1)
    destinations = ends[:, None] + d
    valid = destinations <= frames
    safe = np.minimum(destinations, frames)
    for state in reversed(range(states)):
        local = (
            cumulative[safe, state]
            - cumulative[:, state, None]
            + durations[state, d]
            + backward[safe]
        )
        local[~valid] = -np.inf
        backward = np.logaddexp.reduce(local, axis=1)
    start_prob = np.exp(backward - math.log(frames + 1) - log_mass)
    end_prob = np.exp(forward[-1] - log_mass)

    def credible(probability):
        total = probability.sum()
        if not np.isclose(total, 1, atol=1e-7):
            raise ValueError("Boundary posterior mass is not normalized.")
        cdf = (probability / total).cumsum()
        return [int(np.searchsorted(cdf, q)) for q in (0.05, 0.95)]

    return {
        "first_frame": intervals[0][0],
        "last_frame_exclusive": intervals[-1][1],
        "state_intervals": intervals,
        "conditional_log_likelihood_ratio": log_mass - normalizer,
        "fit_prior_log_mass": normalizer,
        "start_90pct_frames": credible(start_prob),
        "end_90pct_frames": credible(end_prob),
        "start_probabilities": start_prob.tolist(),
        "end_probabilities": end_prob.tolist(),
    }


def contrast_pronunciation(
    emissions, background, duration_logpmf, phone_states, target
):
    """Exact duration sums against all same-length single-phone substitutions.

    Phone identities are distinct complete state paths in a shared acoustic bank.
    Sum every competing sequence's likelihood, each with its own finite-window
    prior normalizer. This unweighted sum is stricter than a best-alternative test;
    it is not a probability of a union of disjoint acoustic events. Shared target
    prefixes/suffixes avoid decoding each entire alternative word separately.
    These conditional density ratios neither recognize spelling nor supply clocks.
    """
    import numpy as np

    emissions, background, durations = _validated_model(
        emissions, background, duration_logpmf
    )
    if (
        not 2 <= len(phone_states) <= 64
        or not target
        or len(target) > 128
        or any(type(p) is not int or not 0 <= p < len(phone_states) for p in target)
        or any(
            not states
            or len(states) > 8
            or any(
                type(s) is not int or not 0 <= s < emissions.shape[1] for s in states
            )
            for states in phone_states
        )
        or len({tuple(states) for states in phone_states}) != len(phone_states)
        or sum(len(phone_states[p]) for p in target) > 384
    ):
        raise ValueError("Expected distinct bounded phone paths and complete target.")
    frames = len(emissions)
    d = np.arange(1, min(frames, durations.shape[1] - 1) + 1)
    ends = np.arange(frames + 1)
    starts = ends[:, None] - d
    valid = starts >= 0
    safe = np.maximum(starts, 0)
    cumulative = np.vstack(
        [np.zeros(emissions.shape[1]), (emissions - background[:, None]).cumsum(axis=0)]
    )

    def advance(previous, state, *, prior=False, reverse=False):
        # Reverse the time axis, not the acoustic/duration parameters. It computes
        # exact suffix mass for any boundary, with no duplicated boundary frame.
        delta = cumulative[:, state]
        if reverse:
            delta = delta[-1] - delta[::-1]
            previous = previous[::-1]
        local = np.broadcast_to(durations[state, d], starts.shape).copy()
        if not prior:
            local += delta[:, None] - delta[safe]
        local[~valid] = -np.inf
        result = np.logaddexp.reduce(local + previous[safe], axis=1)
        return result[::-1] if reverse else result

    initial = np.full(frames + 1, -math.log(frames + 1))
    forward, prior_forward = [initial], [initial]
    for phone in target:
        value, prior = forward[-1], prior_forward[-1]
        for state in phone_states[phone]:
            value, prior = advance(value, state), advance(prior, state, prior=True)
        forward.append(value)
        prior_forward.append(prior)
    backward, prior_backward = [np.zeros(frames + 1)], [np.zeros(frames + 1)]
    for phone in reversed(target):
        value, prior = backward[-1], prior_backward[-1]
        for state in reversed(phone_states[phone]):
            value = advance(value, state, reverse=True)
            prior = advance(prior, state, prior=True, reverse=True)
        backward.append(value)
        prior_backward.append(prior)
    backward.reverse()
    prior_backward.reverse()

    def normalized(value, prior):
        mass, fit = float(np.logaddexp.reduce(value)), float(np.logaddexp.reduce(prior))
        return mass - fit if math.isfinite(mass) and math.isfinite(fit) else None

    score = normalized(forward[-1], prior_forward[-1])
    alternatives = []
    for position, original in enumerate(target):
        for phone, states in enumerate(phone_states):
            if phone == original:
                continue
            value, prior = forward[position], prior_forward[position]
            for state in states:
                value = advance(value, state)
                prior = advance(prior, state, prior=True)
            alternative = normalized(
                value + backward[position + 1], prior + prior_backward[position + 1]
            )
            alternatives.append(
                {"position": position, "phone": phone, "conditional_llr": alternative}
            )
    finite = [
        a["conditional_llr"] for a in alternatives if a["conditional_llr"] is not None
    ]
    total = float(np.logaddexp.reduce(finite)) if finite else None
    return {
        "target_conditional_llr": score,
        "substitution_sum_conditional_llr": total,
        "substitution_margin": score - total
        if score is not None and total is not None
        else None,
        "alternatives": alternatives,
    }
