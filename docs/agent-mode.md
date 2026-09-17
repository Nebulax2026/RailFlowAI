# AI Agent mode

The Planning Board has a **Standard Mode / AI Agent Mode** switch. Agent mode keeps the existing calendar on the left and places chat on the right. On narrow screens the chat appears below the calendar. Standard mode keeps the existing dashboard controls.

## Configuration

Set `OPENAI_API_KEY` on the **backend** service. `OPENAI_MODEL` defaults to `gpt-4.1-mini` and can be changed in the backend environment. Do not set the key in Next.js or use a `NEXT_PUBLIC_` prefix. The backend calls the OpenAI Responses API; the browser calls only RailFlowAI's `/api/agent/*` routes.

The backend and frontend still require the existing `RAILFLOW_API_BASE_URL`, CORS, database, and deployment settings. A missing or failing model connection returns a visible error in chat.

## Actions and approval

The backend exposes an explicit allowlist of RailFlowAI actions in `app/api/agent.py`. Read actions run immediately. Each write action creates a preview card with the action, parameters, and affected items. Schedule generation, alternative application, and freeze previews also calculate proposed work and moved items. CSV and JSON files use the existing import preview validation before a confirmation card is shown.

Approval cards are single use and expire after ten minutes. If application state changes after preview, the server rejects the old approval and requires a fresh preview. The backend calls existing APIs for execution and preserves their validation, conflict checks, audit events, and hosted demo restrictions. A replacement request uses one unit of work to create the new request and remove the old scheduled work.

Typed `yes`, `approve`, `confirm`, or `apply` approves the most recent pending card. All other messages are handled by the model. The approval and rejection buttons remain available on the card.

## Operational limits

The application still has role selectors instead of real user authentication. An approver role selected in the browser is therefore not a verified identity. Do not treat Agent mode as an access-control boundary. Deployment documentation already requires one backend instance because application state is cached in memory. Pending approvals are also held in that process and are lost on a restart; the user can request a new preview afterward.
