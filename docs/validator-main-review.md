# Main validator integration review — 2026-09-18

Updated local main from `82dc917` to `d68611f` (fast-forward). Preserved the
uncommitted Scenario A implementation, CLI, benchmarks and frontend selector.
Backup stash: `22aa1614be752b7ef6d41df6bfa6759df432832c`.

## Validation comparison

These are two internal, specification-based validators. Neither is the
organizer's executable validator. Scores below are weighted activity delay;
an invalid output does not receive a valid objective score.

| CSV source | Main validator | Scenario A validator | Weighted delay |
| --- | --- | --- | ---: |
| Main `submission/public-results/scenario_A` | Valid, 0 violations | Valid, 0 violations | 40.6 |
| Earlier `submission/scenario-a-tuning-integrated` | Invalid, 31 closure violations | Valid, 0 violations | 40.6 |
| Organizer sample, A results | Invalid, 36 closure violations | Invalid, 18 closure/buffer violations | 48.3 |

Main's checked-in B and C outputs also pass its validator: scores 30 and 25.2.
All CSVs were re-read; raw comparison results, including violation examples,
are in `benchmarks/scenario-a/validator-main-comparison.json`.

## Why the validators differ

- Main `local-protection-reservations-v1` forms cohorts in activity-ID order.
  Members need a common work location and matching groups at every overlapping
  work location. Each cohort reserves its external protection separately.
- Scenario A `local-witnessed-sharing-v1` permits location-specific packing of
  protection, provided every sharing pair has an actual shared-work witness.
- Work and protection footprints match for every activity in the public input.
  The observed 31 differences arise from grouping, not delay arithmetic or
  missing public-input footprints.
- A further potential difference on other inputs: main extends Live closure to
  the interchange when actual work reaches it; Scenario A also does so when a
  buffer reaches it. This remains a documented interpretation question.

The earlier Scenario A CSV must not be described as passing the new main
validator. The organizer sample disagreement also prevents treating either
internal policy as confirmed official behavior. Do not compare algorithm
quality across these policies as if they had identical feasible sets.

## Integration

Preserved main's two-pass legacy solver, evidence UI and revision-aware
downloads. Scenario A remains selectable and retains its independent policy.
Its revision/status updates now work with main's polling. Main's location
evidence panel is shown only when that validator supplies the evidence;
Scenario A retains its own diagnostics and hotspot display.

Verified backend suite: 81 tests passed. Frontend lint/type checking passed.
An additional integration regression checks that an infeasible Scenario A run
with no incumbent keeps its search outcome instead of failing in status formatting.
Browser smoke checks passed: selection, public A-only run, ZIP download, ALNS
completion, cancellation with retained result, CSV upload, mobile layout and
switching back to the existing planner.
