# Feedback-loop experiment report (FLE-4)

**Branch:** `feedback_loop_exp` · **Harness:** `experiments/feedback_loop/`
(deterministic, key-free, replaying the SHIPPED pipeline — real
`add_delivery`, real flush, real `run_salience_pass`, real `decide()`).
**Bar (set before the learner existed):** precision ≥ the static
baseline, missed-critical no worse, zero clamp violations.

## 1. Salience tuner vs the static frontier

World: `prod-incidents` (urgency 4–5, endorsement 0.9), `build-noise`
(3–4, 0.05), `batch-info` (1–2, 0.5); 30 rounds; scripted eager judge;
scripted human deciding through the shipped decision engine.

| condition | judge calls | precision | missed-critical | judge reward | clamp violations |
|---|---|---|---|---|---|
| static floor 2 | 75 | 0.493 | 0 | −1 | — |
| static floor 3 (shipped default) | 60 | 0.483 | 0 | −2 | — |
| static floor 4 (best static) | 45 | 0.622 | 0 | +11 | — |
| static floor 5 | 15 | 0.867 | **15** | +11 | — |
| **learner (auto, start 3)** | 55 | **0.655** | **0** | **+17** | **0** |

**Verdict: the bar is cleared.** 0.655 > 0.622 (best static) and > 0.483
(the default it started from), at zero missed-critical, zero clamp
violations. Total judge reward (+17) beats every static point.

**Dynamics, reported rather than tuned away:** the tuner muted
`build-noise` once its window filled (endorsement 0.067 ≤ 0.10), which
left a golden prod-only mix (0.9 > 0.8) — so the floor-down rule slid the
floor to 2, admitting `batch-info` (0.533). That trade lowered precision
from a theoretical mute-only ~0.9 to 0.655 while raising total reward.
A more conservative `FLOOR_DOWN_ABOVE` would hold higher precision at
lower reward; we deliberately did NOT tune this against the harness
world — over-fitting the synthetic world is the anti-pattern the M24
precedent warns about. The floor track was `3→3→2→2→2→2→2`: one move,
then stable — no oscillation.

**Rule change forced by the harness** (also noted in the tuner's
docstring): the research doc's mute trigger said "zero endorsements";
a noise category that is still 5% valuable never hits zero in a rolling
window, so the shipped rule is endorsement ≤ 0.10 over ≥ 5 decided.

**Harness bug found and fixed honestly:** the first baseline run judged
only 12 of 90 candidates — the M23 notification budget (3/day, by
design) was throttling tier-0 flushes and degenerating the endorsement
patterns. The harness world now runs the delivery plane unthrottled,
with the reason commented in the script.

## 2. Forget-gate sweep (M44 hybrid gate, quantified)

Populations seeded at the two live-measured paraphrase cosines
(0.876, 0.847), 40 each of paraphrases / value-updates / unrelated:

| configuration | false-admit (paraphrases) | false-suppress (others) |
|---|---|---|
| threshold-only 0.85 | 0.200 | 0.025 |
| threshold-only 0.80 | 0.000 | 0.175 |
| **shipped hybrid (0.85 / band 0.70 / anchors)** | **0.025** | **0.050** |

The anchor mechanism is decisively on-frontier — every frontier point
uses anchors. The shipped 0.85 sits one grid step off this synthetic
frontier (0.86–0.90 dominate it through exactly two synthetic update
points near 0.85). **This is population-sensitive, not grounds to
re-ship a default** — it is precisely the knob a future forget-tuner
should adjust from real per-install suppression history, which is why
`memory_forget_similarity` is a live setting.

## 3. Scope decision

The extraction tuner (tombstone-metadata consumer) was deliberately NOT
built in this pass: the evidence-first discipline says one learner
proves the pattern before the second is written, and its harness
(forget-gate sweep) currently measures the gate, not a learner. It
remains the next candidate, entering under `memory_extraction_learning`
when built.

## 4. Exit criterion, applied

Per the FLE-1 bar: (1) precision ≥ baseline ✅ (2) missed-critical no
worse ✅ (3) zero clamp violations ✅ (4) this report keeps the
counter-evidence visible (the precision-vs-reward trade in §1, the
threshold sensitivity in §2). The branch is therefore eligible for a PR
to `dev` as milestone M45.
