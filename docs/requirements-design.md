# Product Requirements

RailFlowAI accepts the eight PS1 CSV inputs, solves all three policy scenarios, validates the exported CSVs, and exposes the resulting evidence and ZIP downloads. The Operations tab also supports disruption re-planning and grounded schedule questions for a completed result.

Inputs and result jobs remain in memory for a bounded lifetime. The product does not retain hidden demand books in a database. Synthetic benchmark suites and legacy policy compatibility paths are intentionally out of scope.

AI Agent Mode uses read-only evidence tools and a separate preview → approval → validation re-plan workflow; the model cannot execute a re-plan directly.
