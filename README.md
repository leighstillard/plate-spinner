# Plate Spinner

Plate Spinner is a local-first concern dashboard. It stores work items in SQLite, scans read-only fixture/source connectors, exposes a FastAPI JSON API, and serves a no-build web dashboard at `/`.

Quickstart:

```bash
uv run --with pytest --with httpx python -m pytest tests/ -q
uv run python -m plate_spinner.cli init --db /tmp/plate-spinner-demo.sqlite
uv run python -m plate_spinner.cli scan --config examples/plate-spinner.yaml --db /tmp/plate-spinner-demo.sqlite
PLATE_SPINNER_DB=/tmp/plate-spinner-demo.sqlite uv run uvicorn plate_spinner.api:app
```

The dashboard attention panel surfaces unmapped candidates, blocked items, connector health, and empty active columns. Source connectors are read-only; UI/CLI actions such as snooze, dismiss, pin, and assign mutate only local SQLite state.
