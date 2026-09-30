"""Simulator + real-time scoring engine (pure functions, framework-free)."""
import heapq, random, time
from collections import deque

WINDOW_S = 300
WEIGHTS = {"HARSH_BRAKE": 10, "HARSH_ACCEL": 8, "OVERSPEED": 5}
ALERT_BELOW = 60
TENANTS = 5

def vin(i: int) -> str:
    return f"SIM{i:014d}"          # synthetic 17-char id, no I/O/Q

def tenant_of(i: int) -> int:
    return i % TENANTS

def simulate_tick(n: int, seq: int, rng: random.Random, now: float):
    """One event per vehicle; risky cohort, ~1% duplicates, ~2% late events."""
    ev = []
    for i in range(n):
        p = 0.08 if i % 50 == 0 else 0.002
        evt = rng.choice(("HARSH_BRAKE", "HARSH_ACCEL", "OVERSPEED")) if rng.random() < p else None
        ts = now - (rng.uniform(5, 30) if rng.random() < 0.02 else 0)
        e = {"v": i, "ts": ts, "seq": seq, "evt": evt, "speed": rng.gauss(55, 15)}
        ev.append(e)
        if rng.random() < 0.01:
            ev.append(e)            # duplicate delivery
    return ev

class Engine:
    def __init__(self):
        self.last_seq, self.win, self.alerted = {}, {}, {}
        self.processed = self.dupes = self.late = 0

    def score(self, v, now):
        d = self.win.get(v)
        if not d:
            return 100
        while d and d[0][0] < now - WINDOW_S:
            d.popleft()               # O(1) amortised sliding window
        return max(0, 100 - sum(WEIGHTS[e] for _, e in d))

    def ingest(self, e, now=None):
        """Returns an alert dict when a vehicle newly crosses the threshold."""
        now = now or time.time()
        v = e["v"]
        if self.last_seq.get(v, -1) >= e["seq"]:
            self.dupes += 1
            return None
        self.last_seq[v] = e["seq"]
        self.processed += 1
        if e["ts"] < now - WINDOW_S:
            self.late += 1
            return None
        if e["evt"]:
            self.win.setdefault(v, deque()).append((e["ts"], e["evt"]))
            s = self.score(v, now)
            if s < ALERT_BELOW and not self.alerted.get(v):
                self.alerted[v] = True
                return {"v": v, "ts": now, "score": s, "evt": e["evt"]}
        elif self.alerted.get(v) and self.score(v, now) >= ALERT_BELOW:
            self.alerted[v] = False
        return None

    def worst(self, k, now=None, tenant=None):
        now = now or time.time()
        it = ((self.score(v, now), v) for v in list(self.win)
              if tenant is None or tenant_of(v) == tenant)
        return heapq.nsmallest(k, it)   # O(n log k)
