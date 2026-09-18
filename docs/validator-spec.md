# PS1 Validator Specification

RailFlowAI validates exported bytes, not only solver objects. Each output is decoded, its exact header is checked, and rows are reconstructed before rule evaluation.

## Hard Rule Tags

| Tag | Check |
| --- | --- |
| `schema` | Required output file, exact header, integer/date parsing |
| `scenario` | `RESULTS.csv` contains exactly one matching scenario |
| `activity` | Every access references a known activity |
| `workload` | Standard yield 1.0 and ECLO yield 1.5 sum to `total_accesses` |
| `horizon` | Week is within `1..horizon_weeks` |
| `weekly_activity` | At most one occurrence per activity-week |
| `planned_start` | No occurrence before the planned-start week |
| `predecessor` | Predecessor completes before successor starts; input cycles are rejected |
| `weekly_allocation` | Local access-night is within the contract cap |
| `workfront` | Contract/type/week/night concurrency is within workfront count |
| `occupancy` | Every access expands to exactly its required platforms and sectors |
| `capacity` | A uses nominal capacity; C allows at most one excess possession |
| `eclo` | A forbids ECLO |
| `eclo_continuity` | C ECLO use per affected line fits a two-week span |
| `planned_date` | B contract completion does not exceed planned completion |
| `results` | Every contract has a completion row |

## Scores

```text
A = priority_weighted_overrun
B = 7 * excess_access_nights + 5 * eclo_nights
C = priority_weighted_overrun + 7 * excess_access_nights + 5 * eclo_nights
```

Contract priority bands are 100, 10, and 1. Result overrun is the number of calendar days after `planned_completion_date`. Contract completion is the Sunday ending its latest scheduled week.

## Possession Packing

Capacity counts possession groups, not raw activities. Legal groups are one `PM`; one `PC` with up to three `C`; or up to four `C`. RailFlowAI creates deterministic groups per location-week and counts distinct group labels against supply.

## Known Boundary

The information pack does not include the official executable validator. The supplied sample is the golden compatibility fixture and passes with zero RailFlowAI hard violations. Published wording contains minor numbering and formula-description inconsistencies; the worked examples and explicit scenario equations take precedence.
