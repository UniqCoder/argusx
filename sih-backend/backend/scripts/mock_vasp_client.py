"""
backend/scripts/mock_vasp_client.py — Mock VASP deposit client & chokepoint load tester.

Simulates external exchange deposit requests to POST /check-wallet and benchmarks
latency to verify the p95 < 200ms non-functional requirement.

Usage:
    # 1. Single check
    python -m scripts.mock_vasp_client --address 1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2 --chain BTC --amount 0.75

    # 2. Seed test risk registry entries into Redis
    python -m scripts.mock_vasp_client --seed-registry

    # 3. Run latency & load benchmark (verifies p95 < 200ms)
    python -m scripts.mock_vasp_client --benchmark --requests 200 --concurrency 10
"""
import argparse
import asyncio
import json
import statistics
import time
from typing import Any, List

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_API_KEY = "dev_vasp_key_1"

SAMPLE_WALLETS = [
    {"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2", "chain": "BTC", "amount": 1.25, "expected": "block"},
    {"address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e", "chain": "ETH", "amount": 4.50, "expected": "hold"},
    {"address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "chain": "TRON", "amount": 5000.0, "expected": "hold"},
    {"address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "chain": "BTC", "amount": 0.05, "expected": "allow"},
    {"address": "0x89205A3A3b2A69De6Dbf7f01ED13B2108B2c43e7", "chain": "ETH", "amount": 0.10, "expected": "allow"},
]


async def seed_risk_registry(redis_url: str = "redis://localhost:6379/0"):
    """Populate Redis risk registry with demo risk entries."""
    import redis.asyncio as aioredis
    r = aioredis.from_url(redis_url, decode_responses=True)
    print(f"Connecting to Redis at {redis_url}...")

    # 1. Critical syndicate wallet -> block
    await r.set(
        "risk:BTC:1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2",
        json.dumps({
            "score": 0.94,
            "tier": "critical",
            "case_ref": "NCRP-2026-001001",
            "flagged_at": "2026-08-28T10:00:00Z",
            "ttl": 2592000,
        })
    )

    # 2. High risk task scam wallet -> hold
    await r.set(
        "risk:ETH:0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
        json.dumps({
            "score": 0.78,
            "tier": "high",
            "case_ref": "NCRP-2026-001002",
            "flagged_at": "2026-08-28T10:30:00Z",
            "ttl": 2592000,
        })
    )

    # 3. Medium risk sextortion wallet -> hold
    await r.set(
        "risk:TRON:TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        json.dumps({
            "score": 0.45,
            "tier": "medium",
            "case_ref": "NCRP-2026-001003",
            "flagged_at": "2026-08-28T11:00:00Z",
            "ttl": 2592000,
        })
    )

    await r.aclose()
    print("Successfully seeded demo risk registry keys into Redis.")


async def send_check_wallet_request(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    address: str,
    chain: str,
    amount: float,
) -> tuple[float, dict[str, Any], int]:
    """Execute single /check-wallet POST and measure round-trip time in milliseconds."""
    url = f"{base_url.rstrip('/')}/check-wallet"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "address": address,
        "chain": chain,
        "amount": amount,
    }

    start = time.perf_counter()
    resp = await client.post(url, json=payload, headers=headers)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    return elapsed_ms, resp.json() if resp.status_code == 200 else {}, resp.status_code


async def run_benchmark(
    base_url: str,
    api_key: str,
    total_requests: int = 100,
    concurrency: int = 10,
):
    """Run load test against /check-wallet and compute latency percentiles."""
    print(f"\n--- Running /check-wallet Benchmark ---")
    print(f"Target URL:    {base_url}/check-wallet")
    print(f"Total Checks:  {total_requests}")
    print(f"Concurrency:   {concurrency}")

    latencies: List[float] = []
    actions_count: dict[str, int] = {"allow": 0, "hold": 0, "block": 0, "error": 0}

    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=10.0) as client:
        async def _worker(idx: int):
            item = SAMPLE_WALLETS[idx % len(SAMPLE_WALLETS)]
            async with sem:
                ms, data, status_code = await send_check_wallet_request(
                    client=client,
                    base_url=base_url,
                    api_key=api_key,
                    address=item["address"],
                    chain=item["chain"],
                    amount=item["amount"],
                )
                latencies.append(ms)
                if status_code == 200 and "action" in data:
                    action = data["action"]
                    actions_count[action] = actions_count.get(action, 0) + 1
                else:
                    actions_count["error"] += 1

        tasks = [_worker(i) for i in range(total_requests)]
        await asyncio.gather(*tasks)

    latencies.sort()
    p50 = statistics.median(latencies)
    p90 = latencies[int(len(latencies) * 0.90)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = statistics.mean(latencies)

    print(f"\n--- Benchmark Results ---")
    print(f"Total Requests: {len(latencies)}")
    print(f"Decisions:      {actions_count}")
    print(f"Avg Latency:    {avg:.2f} ms")
    print(f"p50 Latency:    {p50:.2f} ms")
    print(f"p90 Latency:    {p90:.2f} ms")
    print(f"p95 Latency:    {p95:.2f} ms")
    print(f"p99 Latency:    {p99:.2f} ms")

    if p95 < 200.0:
        print(f"\n✅ PASS: p95 latency ({p95:.2f}ms) is well under the 200ms target!")
    else:
        print(f"\n❌ FAIL: p95 latency ({p95:.2f}ms) exceeded 200ms target.")


def main():
    parser = argparse.ArgumentParser(description="Mock VASP Deposit Client & Benchmark")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Base API URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="VASP API Key for X-API-Key header")
    parser.add_argument("--address", help="Wallet address to check")
    parser.add_argument("--chain", default="BTC", help="Blockchain network (BTC|ETH|TRON)")
    parser.add_argument("--amount", type=float, default=1.0, help="Deposit amount")
    parser.add_argument("--seed-registry", action="store_true", help="Seed demo keys into Redis")
    parser.add_argument("--benchmark", action="store_true", help="Run latency benchmark test")
    parser.add_argument("--requests", type=int, default=100, help="Total requests for benchmark")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrency for benchmark")
    args = parser.parse_args()

    if args.seed_registry:
        asyncio.run(seed_risk_registry())
        return

    if args.benchmark:
        asyncio.run(run_benchmark(args.url, args.api_key, args.requests, args.concurrency))
        return

    # Single check mode
    addr = args.address or SAMPLE_WALLETS[0]["address"]
    chain = args.chain or SAMPLE_WALLETS[0]["chain"]
    amount = args.amount

    async def _single():
        async with httpx.AsyncClient() as client:
            ms, data, status = await send_check_wallet_request(client, args.url, args.api_key, addr, chain, amount)
            print(f"Checked {addr} ({chain}) with amount {amount}")
            print(f"Status Code: {status}")
            print(f"Latency:     {ms:.2f} ms")
            print(f"Response:    {json.dumps(data, indent=2)}")

    asyncio.run(_single())


if __name__ == "__main__":
    main()
