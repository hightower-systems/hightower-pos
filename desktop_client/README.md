# desktop_client

The cashier-facing React app. Runs in Chrome `--app=` mode on the
cashier's Windows desktop, served as static assets from the POS Service.

## Tech stack

- Vite 5 + React 18 + TypeScript
- Tailwind CSS (dark by default; no light theme)
- TanStack Query for API calls
- Zustand for cart state (cart UI lands in the next commit)
- Vitest + React Testing Library + MSW for tests

## Quick start (dev)

```bash
cd desktop_client
npm ci
npm run dev
```

The dev server runs on `http://localhost:5173`. Vite proxies:

- `/api/*` → `http://localhost:8081` (the POS Service)
- `/print-agent/*` → `http://127.0.0.1:9100` (the local print agent)

The `/print-agent` proxy forges an `Origin: http://pos-vm.local:8080`
header so the print agent's same-origin gate accepts dev requests
without per-machine `.env` changes.

The POS Service has to be running on **port 8081** locally (the
project's local Sentry holds 8080):

```bash
# From the repo root, in another terminal
uvicorn pos_service.main:app --reload --port 8081
```

## Build (production)

```bash
npm run build
```

Outputs `desktop_client/dist/`. The POS Service mounts this folder
at `/` via FastAPI's `StaticFiles`. Relative `/api/...` URLs in the
build hit the POS Service that's serving the bundle, so the same
build works against any deployed POS Service host.

## Tests

```bash
npm test          # one-shot
npm run test:watch
npm run typecheck
```

Tests use MSW to intercept fetch calls, so no real backend is
required. The handler set lives at `tests/msw/handlers.ts`; tests
override defaults with `server.use(...)`.
