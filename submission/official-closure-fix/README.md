# Replacement schedules

Generated under observed-weekly-closures-v4 from PS1/01_data. Local validation passes with complete workload delivery for A, B and C. Official-validator acceptance is not yet confirmed.

Use scenario_A/A.zip, scenario_B/B.zip and scenario_C/C.zip with the corresponding official scenario setting. Each ZIP contains exactly the three required CSVs at its root. RailFlowAI-closure-fix.zip contains all scenarios plus local validation metadata.

Official validator: all constraints passed. Scores: A 608.3, B 50.0, C 173.5. The local scorer now reproduces these values using the confirmed contract-completion overrun formula. See docs/official-closure-fix.md for details. The original rejected railflow-98b06b7e-results submission is preserved.
