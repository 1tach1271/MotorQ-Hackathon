# FleetSafe – real-time driver-safety scoring (prototype)
## MotorQ-Hackathon

Simulates 100,000 vehicles, scores drivers on a 5-minute sliding window, raises alerts, and serves them through a JWT-secured, rate-limited, tenant-isolated API plus a web dashboard.

Run: `docker compose up --build` then open http://localhost:8000 (logins: manager1/pass1, viewer2/pass2)
Local: `pip install -r requirements.txt && uvicorn app.main:app`   Tests: `pytest -q`

Implemented: simulator (duplicates, late events), idempotent ingest (per-vehicle seq), sliding-window score (O(1) amortised), top-K riskiest (heap, O(n log k)), alert hysteresis, SQLite relational store (tenant/vehicle/alert/audit), keyset pagination, HMAC-signed JWT, tenant isolation, per-user rate limit, audit log.
Not implemented (prototype limits): Kafka, TimescaleDB/Redis, ML model, Helm/Terraform, mTLS, load/chaos tests.
