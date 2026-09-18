# Resolution of the sample premise

The user subsequently confirmed that the supplied submission sample demonstrates
**format only, not a working feasible answer**. This supersedes the sample-feasibility
premise in the historical investigation below. No official source file has been edited.

Implementation now follows the README section 2.4 rules under
`readme-physical-night-v3`: one physical night per activity/week, consistent local
sharing, injective contract/type night mappings, and cross-contract protection
conflicts. The independent CSV validator reconstructs a seven-night witness.
Sample safety failures are expected negative examples, not compatibility targets.
See [validator-spec.md](validator-spec.md) for current semantics and limitations.

---

The following is the **historical investigation**, retained for provenance.
Its references to current behavior and pending clarification describe v2 only.

# Safety semantics: unresolved specification conflict

This is a reproducible clarification package, not a new rule or an official
validation result. No organizer-provided executable validator or additional
clarification is available. Do not remove safety checks merely to pass the sample.

## Two independent witnesses

1. **Local-night buffer witness:** the published sample places A001 and A007 in
   C001/Renewal, week 22, `access_night=3` (SCHEDULE_ACCESS rows 2 and 21).
   Their work sectors are disjoint but their one-sector Consist buffers meet at
   `SEC:BET:H02_S15:EB`. This intersection exists even if platform buffering is
   removed. The current checker reports one closure violation. Whether the local
   index implies physical simultaneity and whether an exemption applies requires
   clarification; this is not proof that the organizer's schedule is unsafe.

2. **Physical-night interpretation witness:** A023 and A070 in week 26 share
   `b4` at `SEC:ALP:S03_S04:WB` (SCHEDULE_OCCUPANCY rows 317 and 902), but use
   `b1` and `b2` at `PLAT:ALP:S03:WB` (rows 315 and 900). If each activity/week
   occurs on one physical night across its entire span, and different groups at
   one location mean different nights, these four rows require both equal and
   unequal nights for the same pair. This contradiction uses neither buffers
   nor capacity assumptions nor globally comparable group names.

There are 45 distinct activity-pair/week witnesses of the second kind in the
sample. These are **conditional interpretation contradictions**, not 45 new hard
violations in our validator. A physical-night coloring solver cannot resolve
contradictory equalities and inequalities by adding more available nights.

## Reproduction

From the repository root:

```powershell
python.exe scripts/audit_safety_semantics.py --output docs/safety-semantics-audit.json
python.exe scripts/audit_safety_semantics.py --schedule submission/public-results/scenario_A --output docs/current-a-semantics-audit.json
```

Reports include input SHA-256 hashes and CSV row numbers. The clock audit uses
only occupancy rows, independent of topology expansion and CP-SAT. It detects
direct pair contradictions only; a clean result is not a physical safety proof.
Synthetic tests cover contradictory relations, consistent location-local names,
and unrelated locations/weeks.

## Exact questions requiring an authoritative answer

- Does one activity/week represent one physical night over its whole expanded
  work span, or can occupancy at different locations represent different nights?
- Are different co_share_group labels at a location necessarily different
  physical nights, as rule 6 states? How should the four-row witness be interpreted?
- Does an equal contract/type/week access_night index enforce simultaneity for
  safety, or is it solely an allocation/workfront counter? Which exemption makes
  the A001/A007 sample pair valid if it does enforce simultaneity?
- What physical-night availability and synchronization rules connect different
  contracts and locations? LOCATION_SUPPLY gives counts, not dated calendars.

## Implementation boundary

Production remains `work-supply-local-night-v2`. We have not silently chosen a
global clock interpretation, waived the sample exception, changed the official
inputs, or regenerated results under new assumptions. The 25.2 A score is an
optimum of that internal model, not a demonstrated physically dispatchable
network schedule. The current A diagnostic is included to audit our own output
under the same proposed interpretation; the sample is not singled out.

The current generated A has 51 direct pair/week contradictions under that
hypothesis, despite zero hard violations under the current local policy. This
confirms that internal feasibility must not be presented as a global night
assignment certificate for our own output either.

This issue cannot be declared resolved from the supplied material alone. Once
the semantics are confirmed, encode them jointly in the scheduler, independently
check a concrete night-assignment witness in the validator, add the confirmed
sample cases as regression tests, and regenerate all outputs. A stricter physical
planning mode before clarification would be a separately named policy, not a
claim of PS1 parity.
