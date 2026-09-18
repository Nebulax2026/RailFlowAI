# Submission Short Answers

## What does your solution do? (107 words)

RailFlowAI turns the eight PS1 demand-book CSVs into complete, auditable railway possession schedules for Scenarios A, B, and C. It validates the input, expands each activity into its platform, sector, buffer, and protection footprint, then uses CP-SAT to choose access weeks, legal co-sharing groups, local nights, and ECLO use while enforcing precedence, capacity, workfront, and weekly closure constraints. A separate CSV-level validator rereads the exported files before download, so the artifact is checked independently of the solver. The workspace compares scenario scores, overruns, excess capacity, ECLO usage, and total search time, then exports the three required CSVs in a submission-ready ZIP.

## What tech stack was used to build this solution? (67 words)

The backend is Python 3.12 with FastAPI, Pydantic-style data models, and Google OR-Tools CP-SAT for optimisation. The frontend uses Next.js 16, React 19, TypeScript, and Lucide icons. Pytest covers parsing, topology, solver, CSV validation, and regression cases; TypeScript checks validate the frontend. Docker builds the static Next.js frontend and serves it from the FastAPI service as one deployable application.

## What challenges did you face, and how did you overcome them? (116 words)

The main challenge was validator parity. An early schedule passed our local checks but the official validator rejected activities that entered another group's weekly closure zone. We converted the reported conflicts into regression tests and strengthened the model and CSV validator so different local nights no longer waive a weekly closure conflict; only direct legal co-sharing can do so. Official feedback also revealed that delay is charged at contract completion, so we corrected the objective and re-optimised the model. The replacement A and B schedules were accepted officially at 608.3 and 50.0. Our current Scenario C candidate scores 122.4 under the strict local model and is pending official confirmation. We also benchmarked integrated CP-SAT and adaptive LNS as alternative search strategies while retaining the validated CP-SAT path for final submissions.

## Status wording

Use “officially accepted” only for the submitted A/B/C replacement run. Describe C=122.4 as a “locally validated, strict-model candidate pending official confirmation.”
