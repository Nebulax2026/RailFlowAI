# PS1 validation and compatibility contract

Outputs are decoded and parsed independently of solver variables. Exactly three CSVs and their official headers are required. Unknown references, malformed rows, duplicate occupancies/results, non-binary ECLO, and non-positive/non-contiguous/non-chronological access sequences are hard failures. Invalid schedules receive diagnostics but no `objective_score` or `formula_version`.

## Scheduling checks

Workload uses integer half-units: standard = 2, ECLO = 3, delivered >= twice requested workload. Surplus is valid. Each activity has at most one occurrence per week; starts respect the planned start week. FS+0 means the successor starts in a strictly later week. Contract/type/week-local night indices must respect weekly allocation and distinct-activity workfront limits. These indices are not network-wide dates.

Completion is recomputed from the final access week, using the last day of the horizon-relative week. Contract completion is the latest activity completion. Every contract requires exactly one matching RESULTS row. B checks the recomputed date, including deadlines in the middle of a week; falsified overrun values cannot pass.

Occupancy must exactly match expanded work sectors and platforms. Within each location/week/group, the only legal mixes are one PM alone, one PC plus up to three C, or up to four C. Group labels carry no meaning outside that location/week. Different local possessions can run during the same week.

## Explicit conservative protection policy

Policy ID: `local-protection-reservations-v1`. This is an implementation assumption, not a claim about the unavailable reference validator.

1. Extend Live/Consist work by the configured sector count at both ends, clipped at line ends. Include the platforms belonging to those buffer sectors. Others have no buffer.
2. Live mirrors work and buffer onto the opposite bound. Live work traversing H01_H02 additionally protects both bounds of the other line's H01_H02 sector and H01/H02 platforms. Non-Live never crosses lines.
3. Exported work groups each consume one local slot. Protection-only footprints reserve additional, separate local slots. Protected slots cannot host unrelated work or another protection reservation. A allows no excess total slots; C allows one; B may procure additional slots.
4. A legal co-sharing clique may pool its protection union when it has a common work location and its members agree on their group at every overlapping work location. Labels at unrelated sites are not equated. Ambiguous local memberships are conservatively partitioned in activity-ID order; no global night identity is invented.
5. The solver selects coherent legal possession patterns (up to four activities with a common work location) and protects each pattern's union once. This is a conservative subset of all possible locally varying group assignments. Reported optimality/infeasibility is for this model only.

The published work-capacity penalty counts distinct **exported work** groups above nominal supply, not protection-only reservations. Safety uses total work + protection slots. The UI reports both values so this difference remains visible.

The organizers label their sample feasible. Our initial strengthened audit finds **36 closure-reservation differences** in that sample and **16** in the previous generated A schedule. These are interpretation/compatibility differences, not proof that the organizers' sample is unsafe. The old B/C outputs pass the strengthened checks. `submission/public-results/compatibility_report.json` records the baseline diagnostics. We do not waive checks to make the sample green, and official parity remains unverified. A policy change following organizer clarification requires updated tests and regeneration.

## ECLO and score

A forbids ECLO. B allows ECLO anywhere but forbids planned-date overrun. C chooses one at-most-two-week span per line; cross-line Live ECLO must fit both spans.

Activity delay cost = contract weight (100/10/1) × activity multiplier (1.3/1.2/1.0) × calendar days after the contract's planned date. A minimizes delay, B minimizes 7 × excess work slots + 5 × ECLO, C minimizes all three. The entire CP-SAT objective is scaled by 10. CSV validation recomputes the same cost and checks model/objective agreement. Formula ID: `ps1-2026-v2`.

Earlier placement is a second pass only after the primary optimum is proved and fixed. There is no additive tie-breaker that can worsen the published cost. Export validation uses topology helpers but never CP-SAT variables or its feasibility flag; handwritten topology fixtures and independent tiny-instance enumeration guard against correlated mistakes.
