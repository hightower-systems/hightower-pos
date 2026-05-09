# hightower-pos

AvidMax in-store retail POS. Replaces TCS POS as part of the NetSuite -> Fabric/Sentry migration.

Three components, one repo:

| Component | Path | Where it runs |
|-----------|------|---------------|
| **POS Service** | `pos_service/` | FastAPI backend on a Linux VM. Orchestrates checkout, holds Windcave credentials, owns the SQLite transaction log. |
| **Print Agent** | `print_agent/` | Python service on the cashier's Windows desktop. Bridges the React UI to the USB receipt printer + cash drawer. |
| **Desktop Client** | `desktop_client/` | React (Vite) single-page app served from the POS Service, opened in Chrome `--app=` mode. |

## Quick start (local dev)

Requires Python 3.11+ and Node 20+.

POS Service:

```bash
pip install -e ".[dev]"
cp .env.example .env
# edit .env

alembic upgrade head
uvicorn pos_service.main:app --host 0.0.0.0 --port 8081 --reload
```

Health check: `curl http://localhost:8081/health`. Port 8081 (not 8080)
keeps the local Sentry dev server free on its conventional port.

The migration seeds an `admin` user with password `admin` and
`must_change_password=true`. First login forces a password change before
any other endpoint accepts the session. Add additional cashiers via
`python -m pos_service create-user <name> --display-name "<Display>"`.

Desktop Client (React, in a second terminal):

```bash
cd desktop_client
npm install
npm run dev
```

Vite serves the cashier UI on `http://localhost:5173` and proxies
`/api/*` to the POS Service on `:8081` and `/print-agent/*` to the
local Print Agent on `127.0.0.1:9100`. In production the POS Service
mounts `desktop_client/dist/` at `/` via FastAPI `StaticFiles`, so the
same relative URLs work without a proxy.

### Cashier keyboard shortcuts

The register UI is built around a few function keys so a busy
cashier doesn't have to break flow to reach the mouse:

| Key | Action |
|-----|--------|
| `F1` | Pay Cash (when cart is non-empty and no flow is active) |
| `F2` | Pay Card (same conditions as F1) |
| `F3` | Open the refund lookup modal |
| `F4` | Open the attach-customer modal (when no customer is attached) |
| `Esc` | Close the active modal |

Each shortcut is no-op when its action is currently disabled, so e.g.
hitting F2 with an empty cart does nothing.

## Deploy (Docker)

```bash
cp .env.example .env
# edit .env -- in particular set DATABASE_URL=sqlite:////data/pos.db
# so the SQLite file lands in the persisted pos-data volume

docker compose up -d --build
docker compose logs -f pos
```

The container runs `alembic upgrade head` on startup, so the schema is
always current. The SQLite database is persisted to the `pos-data`
Docker volume; back it up by snapshotting that volume.

The healthcheck polls `/health` every 30 seconds. Live status:

```bash
docker compose ps
```

### Fabric integration

The POS Service talks to one Fabric endpoint -- the transaction
service -- for everything Fabric-related: price catalog reads,
sales-order writes, customer lookups. The transaction service is a
REST API; the POS Service does not touch Fabric SQL directly. All
Fabric calls go through a single `FabricClient` configured via:

```
FABRIC_TRANSACTION_SERVICE_URL=https://...
FABRIC_API_KEY=...
FABRIC_REQUEST_TIMEOUT_S=30
```

Empty `FABRIC_TRANSACTION_SERVICE_URL` puts the client in mock mode
and disables both the price-sync poller and the SO outbox drain, so
dev machines without Azure credentials boot cleanly. The integration
points:

- **Price catalog (read):** four-hour polling worker calls the
  transaction service's catalog endpoint and upserts the response
  into the local `pos_prices` SQLite cache. Cashier reads only from
  the cache, so a Fabric outage never blocks a sale -- prices just
  age until the next sync. Interval is configurable via
  `FABRIC_SYNC_INTERVAL_S` (default `14400`).
- **Sales-order writeback (write):** every COMPLETE sale or refund
  inserts a `fabric_outbox` row in the same DB transaction as the
  status flip. A separate async worker drains pending entries by
  POSTing the payload to the transaction service. Retry schedule
  mirrors the Sentry-side dispatcher (4s, 15s, 60s, 5min, 30min,
  2hr, 12hr -> DLQ at attempt 9). Drain interval and batch size are
  `FABRIC_OUTBOX_DRAIN_INTERVAL_S` (default `5`) and
  `FABRIC_OUTBOX_BATCH_SIZE` (default `50`).
- **Customer lookup (read):** `GET /api/customers/lookup?name=&email=&phone=`
  proxies to the transaction service. The Fabric customer platform
  performs fuzzy matching across an indexed identity store; the POS
  Service forwards whatever the cashier typed and surfaces the match
  (or null) to the UI.

DLQ visibility:

```bash
curl ".../api/admin/fabric-outbox?status=DLQ"
curl -X POST ".../api/admin/fabric-outbox/{id}/retry"
```

### Pricing data sources

Two paths write into the local `pos_prices` SQLite cache. The cashier
reads only from the cache, so a Fabric outage or a missed CSV import
never blocks a sale -- prices just age until the next refresh.

- **Fabric polling (routine):** see Fabric integration above.
- **CSV (manual override):** `POST /api/prices/import` accepts a
  `sku,price` CSV and writes the same `pos_prices` table. Useful
  for a one-off correction without waiting on the next Fabric
  poll.

Whichever wrote a given SKU most recently wins. The `updated_at`
column on `pos_prices` records the last write so an admin can spot
stale rows.

### Reconciliation

If a Sentry write fails after Windcave already approved a payment, the
transaction row lands in `INVENTORY_UPDATE_FAILED` (sales) or
`REFUND_INVENTORY_UPDATE_FAILED` (refunds) and the inbound activity
log is fired as a backstop. Replay them on demand:

```bash
docker compose exec pos python -m pos_service retry-failed-sales
docker compose exec pos python -m pos_service retry-failed-refunds
```

Both commands are idempotent; the same `idempotency_key` is sent to
Sentry on every retry, so a Sentry-side replay returns the existing SO.

## Tests

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

Desktop Client tests:

```bash
cd desktop_client
npm test
npm run typecheck
npm run build
```

CI runs lint + the alembic migration + the full pytest suite plus the
desktop_client typecheck/vitest/Vite build on every push and pull
request via `.github/workflows/ci.yml`.

## License

Apache-2.0. See `LICENSE`.
