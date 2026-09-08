"""
live_deployed_fp_check.py — Post-promotion live false-positive re-check.

Exercises the ACTUAL deployed /api/v1/wallets/{address}/risk endpoint (FastAPI app
via ASGITransport) against six well-known benign wallets. Uses the real explorer
integration path (live tx history) and the promoted 92f model artifact, with
test doubles only for the DB (in-memory SQLite) and Redis (FakeRedis), mirroring
the e2e endpoint test in tests/conftest.py + tests/test_risk.py.

Gate: all six must be `low` (<0.30); a hard failure is any score >= 0.60.
Explorer rate-limit/downtime caveat: graph features fall back to KNOWN_VASPS when
a live explorer lookup is unavailable, as in production.
"""
import asyncio
import sys
import os

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.routers.check_wallet import get_redis
from app.db.session import Base, get_db
from app.main import app as fastapi_app
import app.models  # noqa: F401 — register all models in Base.metadata

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex=None):
        self._store[key] = value
        return True

    async def aclose(self):
        pass


FP_ADDRESSES: list[tuple[str, str, str]] = [
    ("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "BTC", "Satoshi genesis"),
    ("1FfmbHfnpaZjKFvyi1okTjJJusN455paPH", "BTC", "Bitfinex cold"),
    ("3FHNBLobJnbCTFTVakh5TXmEneyf5PT61B", "BTC", "Binance cold"),
    ("1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s", "BTC", "Binance hot"),
    ("0x28C6c06298d514Db089934071355E5743bf21d60", "ETH", "Binance-8"),
    ("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "ETH", "Vitalik"),
    ("0x503828976D22510aad0201ac7EC88293211D23Da", "ETH", "Coinbase ETH"),
]


async def main() -> int:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    TestSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    fake_redis = FakeRedis()

    async def _override_get_db():
        async with TestSessionLocal() as session:
            yield session

    def _override_get_redis():
        return fake_redis

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    fastapi_app.dependency_overrides[get_redis] = _override_get_redis

    failures = []
    results: list[dict] = []
    try:
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://testserver"
        ) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": "investigator@i4c.gov.in", "password": "devpass"},
            )
            if login.status_code != 200:
                print("AUTH_LOGIN_FAILED", login.status_code, login.text)
                return 1
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            for addr, chain, label in FP_ADDRESSES:
                try:
                    resp = await client.get(f"/api/v1/wallets/{addr}/risk?chain={chain}", headers=headers)
                    if resp.status_code != 200:
                        results.append({"label": label, "chain": chain, "status": resp.status_code, "error": resp.text[:200]})
                        failures.append(f"{label}: HTTP {resp.status_code}")
                        continue
                    data = resp.json()
                    results.append({
                        "label": label,
                        "chain": chain,
                        "status": 200,
                        "risk_score": data["risk_score"],
                        "risk_tier": data["risk_tier"],
                        "evidence_len": len(data["evidence"]),
                    })
                except Exception as exc:  # noqa: BLE001 — report explorer/timing failures per address
                    results.append({"label": label, "chain": chain, "error": repr(exc)[:200]})
                    failures.append(f"{label}: {exc!r}")
    finally:
        fastapi_app.dependency_overrides.clear()
        await engine.dispose()

    print("\n=== LIVE /risk ENDPOINT FP RE-CHECK (post-promotion, 92f artifact) ===")
    for r in results:
        print(f"  {r['label']!r:20} {r['chain']:4} -> score={r.get('risk_score', '-'):<6} tier={r.get('risk_tier', '-')} {r.get('evidence_len', '') and f'evidence={r['evidence_len']}'} {r.get('status', '') and r.get('error', '')}")

    scored = [r for r in results if r.get("risk_score") is not None]
    low_ok = all(r["risk_score"] < 0.30 for r in scored)
    hard_ok = all(r["risk_score"] < 0.60 for r in scored)
    tiers_ok = all(r["risk_tier"] == "low" for r in scored)
    verdict = "PASS" if (not failures and low_ok and hard_ok and tiers_ok) else "FAIL"
    print(f"\nScored {len(scored)}/{len(FP_ADDRESSES)} addresses; all<0.30={low_ok}, all<0.60={hard_ok}, all_tier==low={tiers_ok}, errors={len(failures)}")
    print(f"VERDICT: {verdict}")
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))