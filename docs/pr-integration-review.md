# Open PR integration review — 2026-09-15

## Scope

Open PRs verified using the authenticated GitHub API:

| PR | Head | Integration |
| --- | --- | --- |
| #27 — CP-SAT scheduler | `7b3bb41102151e3ac6388a08c25f713be0514446` | Starting point of the local working copy; retained in full. |
| #31 — D+3 freeze and urgent review states | `b0328d18a7337dbb6c27f63ff926cf40caea547d` | Merged on top of #27 and the local fixes. |
| #30 — Dashboard calendar and demo requesters | `8c26b9afb590e351d25916199a429fecf4b326f2` | Merged with the preservation decisions below. |

Base main: `99657641f3b2ecd2e9b46fd9fb48567c310486b0`.

## Preserved local behavior

The 34 modified/untracked files were archived before integration and committed as a separate snapshot (`019cccf`). The original checkout was left in place; integration used a separate clone.

- Existing tentative calendar entries outside D+3 remain eligible during Generate Schedule.
- Generate Schedule leaves tentative work movable and tentative; explicit approval or Freeze promotes work to locked.
- Explicitly locked work retains its scheduling constraints.
- Calendar details, compact event rendering, import/seed approval-state resets, Python compatibility changes, development launch scripts, and the manual verification CSV remain included.

## Merge decisions

- Retain the Predefined Dependencies panel and its styles, which #30 removed.
- Combine month navigation, six-week calendar display, requester selection, and status badges with local calendar details.
- Retain the existing 24px minimum event height instead of #30's 60px minimum, which could visually overlap short adjacent events.
- Put requester identity in the shared request payload so both recommendation and submission use it; preserve #27/#31 urgent-review handling.
- Include existing request owners in the account selector so legacy/imported owners remain selectable.
- Retain #31's inclusive D+3 approval boundary, requester notes, urgent-review UI guards, and regression tests.

## Validation

- Original local snapshot: 55 backend tests passed.
- Integrated tree: 59 backend tests passed, including a new regression covering near-term tentative work moving around a newly added block without becoming locked.
- Frontend TypeScript route generation and type check passed.
- Production build using `next build --webpack` passed.
- Whitespace/conflict-marker checks passed.

The build emits an existing multiple-lockfile workspace-root warning. Browser interaction was not manually exercised; production compilation and backend tests are the validation performed.

This integration PR is intended for review against main. Existing PRs are not closed or merged by this operation.
