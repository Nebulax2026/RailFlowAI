# PS1 validation and compatibility contract

Outputs are decoded and parsed independently of solver variables. Exactly three CSVs and their official headers are required. Unknown references, malformed rows, duplicate occupancies/results, non-binary ECLO, and non-positive/non-contiguous/non-chronological access sequences are hard failures. Invalid schedules receive diagnostics but no `objective_score` or `formula_version`.

## Scheduling checks

Workload uses integer half-units: standard = 2, ECLO = 3, delivered >= twice requested workload. Surplus is valid. Each activity has at most one occurrence per week; starts respect the planned start week. FS+0 means the successor starts in a strictly later week. Contract/type/week-local night indices must respect weekly allocation and distinct-activity workfront limits. These indices are not network-wide dates.

Completion is recomputed from the final access week, using the last day of the horizon-relative week. Contract completion is the latest activity completion. Every contract requires exactly one matching RESULTS row. B checks the recomputed date, including deadlines in the middle of a week; falsified overrun values cannot pass.

Occupancy must exactly match expanded work sectors and platforms. Within each location/week/group, the only legal mixes are one PM alone, one PC plus up to three C, or up to four C. Group labels carry no meaning outside that location/week. Different local possessions can run during the same week.

## README-based supply and physical-night safety

Policy ID: `readme-physical-night-v3`. The user confirmed that the provided submission sample is **format-only, not a feasible answer**. This clarification supersedes our earlier reliance on the README section 2.7 sample-feasibility sentence. The normative scheduling rules in section 2.4 drive implementation; the original PS1 pack is preserved unchanged.

1. **Supply (rules 5?6):** distinct exported `(location_id, week, co_share_group)` work possessions consume supply. Protection-only footprints never consume additional slots. A allows zero excess; C allows one; B scores excess.
2. **One night per access:** an activity/week occupies its entire expanded work span on one of seven anonymous physical nights in the calendar week. This is an existence witness, not a booking of dated maintenance windows; the input provides supply counts, not available dates.
3. **Local allocation/workfronts (rules 7?8 and section 2.6):** local access indices remain contract/type/week-specific. Equal indices within that scope map to the same physical night; distinct indices map to distinct physical nights. Numeric indices from different contracts are never directly equated.
4. **Sharing (rule 6):** a matching location/week/group imposes the same physical night. Different groups at the same location/week impose different nights. Those relations must agree across the whole activity span and through other activities. Different group *names* at different locations are permitted; names are not global night identifiers.
5. **Closures (rule 4):** configured sector buffers, their endpoint platforms, Live opposite-bound mirroring and Live interchange crossover define protected footprints. Without a direct legal co-sharing exemption, work/buffer and buffer/buffer intersections require different nights across **all contracts and scenarios**, including B. Sharing through a third activity does not waive an external pair's protection conflict. Platform footprint extension remains the documented geometric interpretation; an unavailable official checker is not claimed to have certified it.
6. **Independent verification:** the solver jointly chooses accesses, local groups and physical nights. The CSV validator independently rebuilds equality components and conflict edges, then performs a bounded exact seven-color search without consulting CP-SAT state. Conflicting equalities, forbidden overlaps or an impossible seven-night assignment are hard failures. Search exhaustion is `safety_unknown`, not an infeasibility proof, and withholds the score.
7. **Evidence:** `detail.physical_night_assignment` contains a verified activity/week/night witness; `safety_status` is `verified`, `failed` or `unknown`. The activity UI shows the witness. The CSV headers remain unchanged, and ZIP validation metadata carries the same witness. This proves compatibility with the modeled README rules, not official executable-validator parity or availability on particular dates.

`location_usage.used` equals `work_possessions`. The legacy fields `protection_possessions` and `protection_groups` describe protecting activities, not supply reservations. Invalid incumbents from older policies are revalidated and never retained as successful results.

### Sample and historical results

The sample remains a schema fixture and a **negative safety fixture**, with no ID-specific bypass. A001/A007 demonstrates a same-night buffer conflict; A023/A070 demonstrates inconsistent sharing across locations. Neither must pass just because the files are supplied. [The clarification record](safety-clarification.md) explains the change of premise.

Earlier `local-protection-reservations-v1` and `work-supply-local-night-v2` reports are historical. A v2 score of 25.2 did not establish global night consistency. Newly generated results must pass v3, even if the numeric score happens to be identical. Audit JSONs in `docs/` retain their original hashes and policy IDs and are not current validation certificates.

## ECLO and score

A forbids ECLO. B allows ECLO anywhere but forbids planned-date overrun. C chooses one at-most-two-week span per line; cross-line Live ECLO must fit both spans.

Activity delay cost = contract weight (100/10/1) × activity multiplier (1.3/1.2/1.0) × calendar days after the contract's planned date. A minimizes delay, B minimizes 7 × excess work slots + 5 × ECLO, C minimizes all three. The entire CP-SAT objective is scaled by 10. CSV validation recomputes the same cost and checks model/objective agreement. Formula ID: `ps1-2026-v2`.

Earlier placement is a second pass only after the primary optimum is proved and fixed. There is no additive tie-breaker that can worsen the published cost. Export validation uses topology helpers but never CP-SAT variables or its feasibility flag; handwritten topology fixtures and independent tiny-instance enumeration guard against correlated mistakes.
