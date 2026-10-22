# ObservaBot

Platform health dashboard and Slack bot. Ask service-health questions in plain English and get answers
backed by live Prometheus data, firing Alertmanager alerts and runbooks. The same tools are exposed over
MCP, so any MCP-compatible client can query platform health.

```
            ┌──────────── Slack (Socket Mode) ────────────┐
  user ───► │ observabot-bot  ──► Claude tool-calling agent│
            └──────────────────────────┬──────────────────┘
                                       │ shared tools (observabot/tools.py)
  MCP client ─► observabot-mcp ────────┤
                                       ▼
                     Prometheus API    Alertmanager API    runbooks/*.md
                          ▲
             catalog, payments  (Flask + prometheus_client)
                          ▲
                   Grafana dashboards (Service Health)
```

## What's included

| Path | What it is |
| --- | --- |
| `observabot/slack_app.py` | Slack Bolt bot. Mention it in a channel or DM it. |
| `observabot/agent.py` | Claude tool-use loop (Anthropic Messages API) with a step limit. |
| `observabot/tools.py` | The five read-only tools, their JSON schemas, and dispatch. |
| `observabot/mcp_server.py` | MCP server with the same tools (stdio or streamable HTTP). |
| `observabot/prometheus.py`, `alertmanager.py` | Read-only API clients. |
| `observabot/runbooks.py` | Keyword search over `runbooks/*.md`. |
| `demo_service/` | Flask service instrumented with RED metrics and a runtime chaos switch. |
| `prometheus/`, `alertmanager/`, `grafana/` | Scrape config, alert rules, receivers, and a provisioned dashboard. |
| `docker-compose.yml` | Runs everything with one command. |
| `pipeline/`, `airflow/` | Daily snapshot collector, Spark trends job, and the Airflow DAG. |
| `tests/` | Unit tests, including a real local Spark run (no running services needed). |

### Tools

| Tool | Purpose |
| --- | --- |
| `list_services` | Every scrape job and whether it is up. |
| `service_health` | Request rate, 5xx error ratio, p95 latency, for one service over 5 minutes. |
| `get_firing_alerts` | Active, non-silenced alerts, optionally filtered by service. |
| `query_prometheus` | Arbitrary read-only PromQL, for anything the other tools don't cover. |
| `lookup_runbook` | Finds the runbook for an alert name or symptom. |

The service name is the Prometheus `job` label, so `catalog` and `payments` are the demo services.

## Daily trends pipeline (Airflow + Spark)

A small batch pipeline that shows how the health data fits into a data platform.

```
Prometheus ──► collect_snapshot (Airflow) ──► data/snapshots/dt=YYYY-MM-DD/health.jsonl
                                                   │
                                                   ▼
                                  spark_trends (Spark) ──► data/trends/service_trends.csv
```

- `pipeline/snapshot.py` records one health row per service per day.
- `pipeline/spark_trends.py` reads every snapshot and writes one row per service per day: average request rate, average and peak 5xx error rate, peak p95 latency, and percentage of snapshots where the service was down.
- `airflow/dags/service_health_daily.py` runs both steps daily.

Run the pipeline by hand (needs Java 17 for Spark):

```bash
export JAVA_HOME=$(brew --prefix openjdk@17)
.venv/bin/python -m pipeline.snapshot --date $(date -u +%F)
.venv/bin/python -m pipeline.spark_trends
```

To run it under Airflow, use a separate virtualenv so its dependencies don't clash with the app's:

```bash
python3.12 -m venv .venv-airflow
.venv-airflow/bin/pip install "apache-airflow==3.3.2" --constraint \
  "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt"
export AIRFLOW_HOME=$PWD/.airflow PROJECT_DIR=$PWD
.venv-airflow/bin/airflow standalone
```

Then open the Airflow UI, unpause `service_health_daily`, and trigger a run.

## Quick start (demo stack)

1. Start everything except the bot and MCP server:

   ```bash
   docker compose up -d --build catalog payments prometheus alertmanager grafana
   ```

   Open Grafana at http://localhost:3000 (the "ObservaBot" folder holds the Service Health dashboard) and
   Prometheus at http://localhost:9090.

2. Make `catalog` misbehave, then generate traffic. After about 2 minutes `HighErrorRate` fires:

   ```bash
   curl -X POST 'http://localhost:8081/chaos?error_rate=0.5&latency_ms=700'
   for i in $(seq 1 300); do curl -s http://localhost:8081/api/items > /dev/null; done
   ```

   Reset it with `curl -X POST 'http://localhost:8081/chaos?error_rate=0&latency_ms=0'`.

3. Check the alert at http://localhost:9093, or ask ObservaBot once the bot is running.

## Setting up the Slack bot

1. Create a Slack app at https://api.slack.com/apps, using "From scratch".
2. **Socket Mode**: enable it and create an app-level token with the `connections:write` scope. This is `SLACK_APP_TOKEN`.
3. **OAuth & Permissions**: add bot scopes `app_mentions:read`, `chat:write`, `im:history`, `im:read`, `im:write`. Install to your workspace and copy the bot token. This is `SLACK_BOT_TOKEN`.
4. **Event Subscriptions**: enable events and subscribe to the bot events `app_mention` and `message.im`.
5. Copy `.env.example` to `.env`, fill in the three keys, then start the bot:

   ```bash
   docker compose up -d --build observabot-bot
   ```

   Or run it locally against a local stack (defaults point at `localhost`):

   ```bash
   python -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/python -m observabot.slack_app
   ```

Then in Slack: `@ObservaBot how is catalog doing?` or `@ObservaBot what's firing right now?`

## Using the MCP server

Over stdio (Claude Code, Claude Desktop, or any client that launches a local process):

```json
{
  "mcpServers": {
    "observabot": {
      "command": "/absolute/path/to/observabot/.venv/bin/python",
      "args": ["-m", "observabot.mcp_server"],
      "env": {
        "PROMETHEUS_URL": "http://localhost:9090",
        "ALERTMANAGER_URL": "http://localhost:9093",
        "RUNBOOK_DIR": "/absolute/path/to/observabot/runbooks"
      }
    }
  }
}
```

Over HTTP, use the `observabot-mcp` container, which listens on `http://localhost:8001/mcp`:

```bash
docker compose up -d --build observabot-mcp
```

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` | — | Required by the bot. |
| `ANTHROPIC_API_KEY` | — | Required by the bot. |
| `CLAUDE_MODEL` | `claude-sonnet-5-5` | Any Claude model ID. |
| `PROMETHEUS_URL` | `http://localhost:9090` | |
| `ALERTMANAGER_URL` | `http://localhost:9093` | |
| `RUNBOOK_DIR` | `runbooks` | Markdown files; the first `# ` heading is the title. |
| `MCP_HOST`, `MCP_PORT` | `127.0.0.1`, `8001` | Used with `--http`. |

## Adding a service

1. Expose `/metrics` with `http_requests_total{method,endpoint,status}` and `http_request_duration_seconds` (histogram), the same names as `demo_service/app.py`.
2. Add a scrape job to `prometheus/prometheus.yml`. The job name becomes the service name everywhere.
3. Alerts in `prometheus/alert_rules.yml` apply to every job automatically.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

## Limitations

- The Slack bot answers each message on its own. It does not carry conversation history across messages.
- The tools are read-only. ObservaBot cannot silence alerts, scale services, or roll back deploys.
- `query_prometheus` accepts any PromQL. Put Prometheus behind auth before exposing the MCP server beyond your network.
