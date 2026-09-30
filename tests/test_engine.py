import random, time
from app.engine import Engine, simulate_tick, vin, WINDOW_S

def ev(v, seq, evt, ts): return {"v": v, "ts": ts, "seq": seq, "evt": evt, "speed": 50}

def test_duplicate_is_idempotent():
    e, now = Engine(), time.time()
    e.ingest(ev(1, 1, "HARSH_BRAKE", now), now); e.ingest(ev(1, 1, "HARSH_BRAKE", now), now)
    assert e.processed == 1 and e.dupes == 1 and e.score(1, now) == 90

def test_alert_fires_once_below_threshold():
    e, now = Engine(), time.time()
    alerts = [e.ingest(ev(2, s, "HARSH_BRAKE", now), now) for s in range(1, 8)]
    assert len([a for a in alerts if a]) == 1 and e.score(2, now) == 30

def test_window_expires():
    e, now = Engine(), time.time()
    e.ingest(ev(3, 1, "HARSH_BRAKE", now), now)
    assert e.score(3, now + WINDOW_S + 1) == 100

def test_stale_event_ignored():
    e, now = Engine(), time.time()
    e.ingest(ev(4, 1, "HARSH_BRAKE", now - 1000), now)
    assert e.late == 1 and e.score(4, now) == 100

def test_worst_orders_lowest_first():
    e, now = Engine(), time.time()
    e.ingest(ev(5, 1, "HARSH_BRAKE", now), now)
    for s in (1, 2): e.ingest(ev(6, s, "HARSH_ACCEL", now), now)
    assert e.worst(2, now)[0][1] == 6

def test_simulator_shape():
    out = simulate_tick(1000, 1, random.Random(1), time.time())
    assert len(out) >= 1000 and len(vin(5)) == 17
