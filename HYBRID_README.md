# MediRoute — Hybrid Prototype (API + multi-region console)

A working prototype: a FastAPI backend that loads the real 212K-node road graph
once and stays warm, serving (a) instant pre-computed demo scenarios and (b) a
live route endpoint that computes on any origin/target. A single-file frontend
consumes it, with region + supply-hub switchers and a delivery animation.

## What's real vs proxy
- **Real:** 306 clinic locations & IDs (MIMU), road topology (OSM, 212K nodes),
  clinic stock/demand (your dataset), disease→region priorities, WHO cold-chain
  windows, blackout-township reporting, hospital identities used as hubs.
- **Proxy/synthetic (flagged):** waterway geometry & docks (Mayu + Chindwin),
  boat speed, transfer penalty, per-segment cold-chain capability, and the
  conflict-proxy portion of telecom status.

## Three regions, three honest stories
- **Rakhine** — boat failover on the Mayu River (coastal/riverine).
- **Sagaing** — river reroute on the Chindwin (Homalin/Kani/Mawlaik barely
  road-reachable).
- **Mandalay** — road-only (landlocked). The engine deliberately does NOT use
  boats here; failover is a risk-weighted road reroute.

## Run it locally
```bash
pip install -r requirements.txt          # includes fastapi, uvicorn
# 1. (once) pre-compute the curated scenarios
python scripts/precompute_scenarios.py
# 2. build the frontend from those scenarios
python scripts/build_frontend.py
# 3. start the warm API (also serves the frontend at http://localhost:8000)
uvicorn app.api:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000 — the console loads and everything works.

## API endpoints
- `GET  /health` — readiness + node count
- `GET  /regions` — region configs + hubs (drives the UI switchers)
- `GET  /precomputed/{region}/{hub}` — instant pre-baked scenario (demo-safe)
- `POST /route` — LIVE route from any origin to any target (the "it's real" proof)
  ```json
  {"origin":"CL-0242","target":"CL-0270","risk_weight":1.5,"equity_weight":1.2}
  ```

## Why hybrid
The demo-critical money-shots (failover, cold-chain break, telecom boost) are
pre-computed and cannot fail. The live `/route` endpoint proves the engine is
really computing on the graph, not replaying a recording — but it is never on
the demo-critical path. The only heavy operation is loading the graph at
startup (~15-30s), after which it stays warm and every request is fast.

## Deploying (for a hosted submission link)
Use a host that keeps a process warm (NOT cold-start serverless), because the
graph must stay in memory:
- Render / Railway / Fly.io "web service" with the uvicorn command above.
- Set the start command to `uvicorn app.api:app --host 0.0.0.0 --port $PORT`.
- First boot loads the graph; after that it's instant.
- The frontend is served by the same process, so one URL is the whole app.

If you'd rather submit something that can't break at all, the frontend also runs
fully standalone (open demo_data/index.html directly) using the embedded
pre-computed scenarios — only the live /route button and map tiles need the
server/internet.
```
