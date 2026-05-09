# hightower-pos

AvidMax in-store retail POS. Replaces TCS POS as part of the NetSuite -> Fabric/Sentry migration.

Three components, one repo:

| Component | Path | Where it runs |
|-----------|------|---------------|
| **POS Service** | `pos_service/` | FastAPI backend on a Linux VM. Orchestrates checkout, holds Windcave credentials, owns the SQLite transaction log. |
| **Print Agent** | `print_agent/` | Python service on the cashier's Windows desktop. Bridges the React UI to the USB receipt printer + cash drawer. |
| **Desktop Client** | `desktop_client/` | React (Vite) single-page app served from the POS Service, opened in Chrome `--app=` mode. |

## Quick start (local dev)

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
cp .env.example .env
# edit .env

alembic upgrade head
uvicorn pos_service.main:app --host 0.0.0.0 --port 8080 --reload
```

Health check: `curl http://localhost:8080/health`.

The migration seeds an `admin` user with password `admin` and
`must_change_password=true`. First login forces a password change before
any other endpoint accepts the session. Add additional cashiers via
`python -m pos_service create-user <name> --display-name "<Display>"`.

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

CI runs lint + the alembic migration + the full pytest suite on every
push and pull request via `.github/workflows/ci.yml`.

## License

Apache-2.0. See `LICENSE`.
