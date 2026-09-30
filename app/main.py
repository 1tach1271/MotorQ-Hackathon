import base64, hashlib, hmac, json, os, sqlite3, threading, time, random
from collections import defaultdict, deque
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .engine import Engine, simulate_tick, vin, tenant_of, TENANTS

FLEET = int(os.getenv("FLEET_SIZE", "100000"))
SECRET = os.getenv("JWT_SECRET", "dev-only-change-me").encode()
USERS = {"manager1": ("pass1", 0, "manager"), "viewer2": ("pass2", 1, "viewer")}
RATE = 120  # requests / minute / user
ROOT = os.path.join(os.path.dirname(__file__), "..", "static")

db = sqlite3.connect(os.getenv("DB", ":memory:"), check_same_thread=False)
db.executescript("""
CREATE TABLE tenant(id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE vehicle(id INTEGER PRIMARY KEY, vin TEXT UNIQUE, tenant_id INTEGER REFERENCES tenant(id));
CREATE TABLE alert(id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id INTEGER REFERENCES vehicle(id),
  tenant_id INTEGER, ts REAL, score INTEGER, evt TEXT);
CREATE INDEX ix_alert_tenant_id ON alert(tenant_id, id DESC);
CREATE TABLE audit(ts REAL, user TEXT, action TEXT);
""")
db.executemany("INSERT INTO tenant VALUES(?,?)", [(t, f"Fleet {t}") for t in range(TENANTS)])
db.executemany("INSERT INTO vehicle VALUES(?,?,?)", ((i, vin(i), tenant_of(i)) for i in range(FLEET)))
db.commit()
lock = threading.Lock()
engine = Engine()
stats = {"eps": 0, "ticks": 0, "latency_ms": 0}

def pipeline():
    rng, seq = random.Random(42), 0
    while True:
        t0 = time.time(); seq += 1
        events = simulate_tick(FLEET, seq, rng, t0)
        alerts = [a for e in events if (a := engine.ingest(e, t0))]
        with lock:
            db.executemany("INSERT INTO alert(vehicle_id,tenant_id,ts,score,evt) VALUES(?,?,?,?,?)",
                           [(a["v"], tenant_of(a["v"]), a["ts"], a["score"], a["evt"]) for a in alerts])
            db.commit()
        dt = time.time() - t0
        stats.update(eps=int(len(events) / dt), ticks=seq, latency_ms=round(dt * 1000))
        time.sleep(max(0, 1 - dt))

app = FastAPI(title="FleetSafe")
@app.on_event("startup")
def _start(): threading.Thread(target=pipeline, daemon=True).start()

def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def sign(p):
    body = b64(json.dumps(p).encode())
    return f"{body}.{b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())}"

hits = defaultdict(deque)
def auth(authorization: str = Header(None)):
    try:
        body, sig = authorization.split(" ")[1].split(".")
        if not hmac.compare_digest(sig, b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())):
            raise ValueError
        p = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if p["exp"] < time.time(): raise ValueError
    except Exception:
        raise HTTPException(401, "invalid or missing token")
    q = hits[p["sub"]]; now = time.time()
    while q and q[0] < now - 60: q.popleft()
    if len(q) >= RATE: raise HTTPException(429, "rate limit exceeded")
    q.append(now)
    with lock:
        db.execute("INSERT INTO audit VALUES(?,?,?)", (now, p["sub"], "api_access"))
    return p

@app.post("/token")
def token(username: str, password: str):
    u = USERS.get(username)
    if not u or not hmac.compare_digest(u[0], password): raise HTTPException(401, "bad credentials")
    return {"access_token": sign({"sub": username, "tenant": u[1], "role": u[2], "exp": time.time() + 3600})}

@app.get("/api/summary")
def summary(p=Depends(auth)):
    with lock:
        n = db.execute("SELECT COUNT(*) FROM alert WHERE tenant_id=?", (p["tenant"],)).fetchone()[0]
    return {"tenant": p["tenant"], "vehicles": FLEET // TENANTS, "alerts_total": n,
            "events_per_sec": stats["eps"], "tick_ms": stats["latency_ms"],
            "dedup_dropped": engine.dupes, "late_dropped": engine.late, "processed": engine.processed}

@app.get("/api/alerts")
def alerts(limit: int = 20, before_id: int | None = None, p=Depends(auth)):
    limit = min(max(limit, 1), 100)      # keyset pagination, not OFFSET
    with lock:
        rows = db.execute("SELECT id,vehicle_id,ts,score,evt FROM alert WHERE tenant_id=? AND id<? "
                          "ORDER BY id DESC LIMIT ?", (p["tenant"], before_id or 1 << 60, limit)).fetchall()
    items = [{"id": r[0], "vin": vin(r[1]), "ts": r[2], "score": r[3], "evt": r[4]} for r in rows]
    return {"items": items, "next_before_id": items[-1]["id"] if len(items) == limit else None}

@app.get("/api/drivers/worst")
def worst(k: int = 10, p=Depends(auth)):
    return [{"vin": vin(v), "score": s} for s, v in engine.worst(min(k, 50), tenant=p["tenant"])]

@app.get("/health")
def health(): return {"ok": True}

app.mount("/static", StaticFiles(directory=ROOT), name="s")
@app.get("/")
def index(): return FileResponse(os.path.join(ROOT, "index.html"))
