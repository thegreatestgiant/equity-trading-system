Load test for the API, run as the `locust-load-tester` deployment in the cluster.

- **`locustfile.py`** — defines `EquityTradingUser`: on start it registers a user and opens 3 accounts, then repeatedly books single trades, batch trades, and reads positions/trades/health at weighted rates (`@task(n)`) with a 1-3s wait between actions.

After editing `locustfile.py`, run `./locust_reload.sh` from the repo root to push the change into the cluster's ConfigMap and restart the Locust pods, without waiting for a full GitOps sync. Trigger runs and chaos scenarios via `make chaos` (see [DEVELOPERS.md](../DEVELOPERS.md)).
