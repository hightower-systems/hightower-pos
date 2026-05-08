# hightower-pos

AvidMax in-store retail POS. Replaces TCS POS as part of the NetSuite -> Fabric/Sentry migration.

Three components, one repo:

| Component | Path | Where it runs |
|-----------|------|---------------|
| **POS Service** | `pos_service/` | FastAPI backend on a Linux VM. Orchestrates checkout, holds Windcave credentials, owns the SQLite transaction log. |
| **Print Agent** | `print_agent/` | Python service on the cashier's Windows desktop. Bridges the React UI to the USB receipt printer + cash drawer. |
| **Desktop Client** | `desktop_client/` | React (Vite) single-page app served from the POS Service, opened in Chrome `--app=` mode. |

## Quick start (POS Service)

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
cp .env.example .env
# edit .env

alembic upgrade head
python -m pos_service create-user mike --display-name "Mike Hightower"

uvicorn pos_service.main:app --host 0.0.0.0 --port 8080 --reload
```

Health check: `curl http://localhost:8080/health`.

## License

Apache-2.0. See `LICENSE`.
