# Print Agent

The cashier-side bridge between the POS web app and the USB receipt
printer + cash drawer. Runs on the cashier's Windows desktop next to
the printer. Listens on `http://127.0.0.1:9100` and rejects requests
from any Origin other than the configured POS web app URL.

## Endpoints

| Method | Path           | Body                                      | Purpose                          |
|--------|----------------|-------------------------------------------|----------------------------------|
| POST   | `/print`       | `{format, content, cut, open_drawer_after}` | Print receipt content            |
| POST   | `/open-drawer` | (none)                                    | Kick the cash drawer             |
| GET    | `/status`      | (none)                                    | Agent + printer status           |
| POST   | `/test-print`  | (none)                                    | Print a small diagnostic receipt |

## Install (manual, Phase 1)

The Windows install in this phase is "double-click a .bat file." Phase 2
will replace this with an autostart installer.

1. Install Python 3.11+ from python.org (tick **Add Python to PATH**).
2. Copy this folder to the cashier desktop, e.g. `C:\AvidMax\pos-print-agent\`.
3. Edit `.env` (or copy from `.env.example`) with the POS web app URL
   and the printer's USB ids if they differ from the Star TSP100
   defaults.
4. Double-click `start_print_agent.bat`. The first run creates a venv
   and installs dependencies (~30 seconds); subsequent runs start
   immediately.
5. Closing the black terminal window stops the agent.

## Verify

With the agent running:

```bash
curl -X POST http://127.0.0.1:9100/test-print \
  -H "Origin: http://pos-vm.local:8080"
```

A short diagnostic slip should print. (The Origin header has to match
`ALLOWED_ORIGIN` in `.env`; without it the agent returns 403
`forbidden_origin`.)

## Common problems

- **Printer offline / 503 printer_offline.** Check the USB cable and
  paper. If the printer recently ran out of paper and was reloaded,
  try the next print again - the agent reconnects on transient USB
  errors.
- **Drawer not opening.** Check the phone-jack cable from the printer
  to the drawer. Verify `DRAWER_PIN` in `.env` matches the wiring (2
  is typical, some setups use 5).
- **Origin forbidden / 403.** The POS web app URL changed, or the
  request is coming from a different origin (e.g. from `localhost`
  during dev). Update `ALLOWED_ORIGIN` in `.env` and restart.
- **Python is not on PATH.** Reinstall Python 3.11+ with the **Add to
  PATH** checkbox ticked.

## Tests

```bash
pip install -e ".[dev]"
pytest -q print_agent/tests/
```

Tests use a mocked printer, so libusb is not required to run them.

## Deploy alongside the POS Service

The print agent is operationally independent of the POS Service. The
POS Service runs in Docker on a Linux VM; the print agent runs as a
native Python process on each cashier desktop. They communicate over
the LAN: the POS web app (served from the POS Service) calls
`http://127.0.0.1:9100/print` from the cashier's browser, which loops
back to the print agent on the same machine.
