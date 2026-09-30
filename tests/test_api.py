import os; os.environ["FLEET_SIZE"] = "2000"
from fastapi.testclient import TestClient
from app.main import app

def test_auth_and_tenant_isolation():
    with TestClient(app) as c:
        assert c.get("/api/summary").status_code == 401
        t = c.post("/token?username=manager1&password=pass1").json()["access_token"]
        r = c.get("/api/summary", headers={"Authorization": f"Bearer {t}"})
        assert r.status_code == 200 and r.json()["vehicles"] == 400
        assert c.post("/token?username=manager1&password=bad").status_code == 401
        assert c.get("/api/summary", headers={"Authorization": "Bearer x.y"}).status_code == 401
