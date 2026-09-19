# Closure compatibility fix for A, B and C

The official checker rejected a historical Scenario A submission with 64 closure messages across 13 weeks. The same CSVs passed our previous local policy at score 25.2. The [original comparison](official-validator-98b06b7e-audit.json) records their hashes and all messages; it is historical evidence, not current validation.

The replacement policy, `observed-weekly-closures-v4`, makes two changes:

- Work cannot enter another group's closure in the same week merely by choosing another local or reconstructed physical night. Direct legal co-sharing must agree at every common work location. Separate work groups, including overlapping work spans, are treated conservatively as separate closures.
- Live work at H01–H02 extends the configured buffer on the receiving line, on both bounds. Previously only the other line's interchange and hub platforms were included. The corrected geometry covers every reported location in all 64 messages; five messages previously included locations outside our footprint.

All A/B/C strategies now use the same model and CSV validation gate. Scenario A's former independent model/validator entry points delegate to that implementation. Scenario rules remain enforced: A forbids ECLO and extra supply; B forbids planned-date overrun; C retains its supply allowance and per-line ECLO windows. Buffer/buffer night consistency, legal mixes, workfronts, precedence and full workload delivery remain checked.

Submission files are in [submission/final-submission](../submission/final-submission/). Each scenario archive (`A.zip`, `B.zip`, `C.zip`) contains only the required three CSVs at its root, accompanied by `manifest.json`.

The official validator accepted all three replacement ZIPs (A, B, and C). These are the confirmed results:

| Scenario | Official objective | Contract overrun | Excess access | ECLO | Official constraints |
|---|---:|---:|---:|---:|---|
| A | 608.3 | 42 days / 5 contracts | 0 | 0 | Passed |
| B | 50.0 | 0 days / 0 contracts | 0 | 10 | Passed |
| C | 122.4 | 21 days / 2 contracts | 0 | 6 | Passed |

The official scores exposed a separate local scoring error. The validator charges a contract's completion overrun to the multiplier of every activity in that contract. Applying that rule reproduces all three official scores exactly. The local scorer and optimizer now use this confirmed contract-level formula. The earlier claims that A's local score 131.6 was optimal and C scored 55.9 are retired because they used activity completion dates independently.

After correcting the objective, a fresh exact search proved A's accepted 608.3 schedule optimal under the confirmed formula. It found an optimized Scenario C schedule with score 122.4: 92.4 weighted contract-overrun cost plus 30 for six ECLO nights, with zero excess access. The schedule moves contract overrun to lower-cost combinations and is packaged at `submission/final-submission/C.zip`, which is officially accepted.

The official validator remains inaccessible, so hidden cases may still reveal further grouping or geometry rules. In particular, the evidence does not settle crossover triggered solely by a buffer reaching the interchange, or every possible group-level closure construction on hidden inputs.

Historical synthetic benchmark claims were removed with the obsolete benchmark suite. Official results and strict CSV validation remain the evidence used for submission candidates.
