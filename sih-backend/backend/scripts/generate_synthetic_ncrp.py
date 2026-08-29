"""
backend/scripts/generate_synthetic_ncrp.py — Standalone synthetic NCRP generator.

Generates realistic mock NCRP cyber-fraud complaints with controlled shared-wallet
clusters for testing the Cross-Victim Correlation Engine (USP 1).

Usage:
    # Print summary of generated dataset to console or save to JSON
    python -m scripts.generate_synthetic_ncrp --output dataset.json

    # Seed directly into PostgreSQL database (via DATABASE_URL)
    python -m scripts.generate_synthetic_ncrp --seed-db
"""
import argparse
import asyncio
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

INDIAN_LOCATIONS = [
    ("Maharashtra", ["Mumbai", "Pune", "Nagpur", "Thane", "Nashik"]),
    ("Delhi", ["New Delhi", "North Delhi", "South Delhi", "West Delhi"]),
    ("Karnataka", ["Bengaluru Urban", "Bengaluru Rural", "Mysuru", "Mangaluru"]),
    ("Gujarat", ["Ahmedabad", "Surat", "Vadodara", "Rajkot"]),
    ("Uttar Pradesh", ["Noida", "Lucknow", "Kanpur", "Ghaziabad", "Agra"]),
    ("Telangana", ["Hyderabad", "Cyberabad", "Warangal"]),
    ("Tamil Nadu", ["Chennai", "Coimbatore", "Madurai"]),
    ("Rajasthan", ["Jaipur", "Jodhpur", "Udaipur", "Kota"]),
    ("West Bengal", ["Kolkata", "Howrah", "North 24 Parganas"]),
    ("Haryana", ["Gurugram", "Faridabad", "Panipat"]),
]

FRAUD_TYPOLOGIES = [
    "investment_fraud",
    "task_based_fraud",
    "sextortion",
    "impersonation_scam",
    "phishing",
    "loan_app_fraud",
    "crypto_doubling",
    "part_time_job_fraud",
]

NARRATIVE_TEMPLATES = [
    "Victim received a message on Telegram offering high returns on crypto staking. Instructed to transfer funds to wallet {wallet}.",
    "Victim was lured into a fake YouTube rating task scheme. Asked to deposit ₹{amount} in crypto to unlock earnings at address {wallet}.",
    "Victim reported extortion call claiming compromising video. Forced to purchase USDT and send to suspect wallet {wallet}.",
    "Victim was contacted on WhatsApp posing as institutional crypto brokers promising 300% weekly return. Deposited funds to {wallet}.",
    "Victim fell for a phishing website mimicking a popular exchange login. Assets drained and transferred to {wallet}.",
    "Victim joined a VIP crypto trading signal group. Followed instructions to deposit into malicious smart contract/wallet {wallet}."
]

# Controlled clusters to seed
PLANTED_SHARED_WALLETS = [
    {
        "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2",
        "chain": "BTC",
        "complaint_count": 6,
        "description": "Major BTC Investment Scam Syndicate",
        "fraud_typology": "investment_fraud",
    },
    {
        "address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
        "chain": "ETH",
        "complaint_count": 4,
        "description": "Telegram Task-Based Multi-State Fraud Ring",
        "fraud_typology": "task_based_fraud",
    },
    {
        "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        "chain": "TRON",
        "complaint_count": 3,
        "description": "TRC20 USDT Impersonation Extortion Network",
        "fraud_typology": "sextortion",
    },
    {
        "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
        "chain": "BTC",
        "complaint_count": 2,
        "description": "BTC Part-Time Job Scam Pair",
        "fraud_typology": "part_time_job_fraud",
    },
    {
        "address": "0x89205A3A3b2A69De6Dbf7f01ED13B2108B2c43e7",
        "chain": "ETH",
        "complaint_count": 2,
        "description": "ETH Phishing Drainer Pair",
        "fraud_typology": "phishing",
    },
]


def _random_btc_address(rng: random.Random) -> str:
    chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "1" + "".join(rng.choice(chars) for _ in range(33))


def _random_eth_address(rng: random.Random) -> str:
    hex_chars = "0123456789abcdef"
    return "0x" + "".join(rng.choice(hex_chars) for _ in range(40))


def _random_tron_address(rng: random.Random) -> str:
    chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "T" + "".join(rng.choice(chars) for _ in range(33))


def generate_synthetic_dataset(seed: int = 42, single_count: int = 35) -> dict[str, Any]:
    """
    Generate synthetic complaints, wallets, and complaint_wallets junction entries.
    Guarantees deterministic output when seed is specified.
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)

    wallets_list = []
    complaints_list = []
    complaint_wallets_list = []

    complaint_idx = 1000

    # 1. Generate planted shared-wallet clusters
    for cluster in PLANTED_SHARED_WALLETS:
        w_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        w_addr = cluster["address"]
        w_chain = cluster["chain"]

        wallets_list.append({
            "id": w_id,
            "address": w_addr,
            "chain": w_chain,
            "risk_score": None,
            "risk_tier": "critical" if cluster["complaint_count"] >= 4 else "high",
            "vasp_identified": None,
            "cluster_id": None,
            "first_seen": (now - timedelta(days=rng.randint(30, 90))).isoformat(),
            "last_seen": (now - timedelta(days=rng.randint(1, 10))).isoformat(),
        })

        # Select distinct states for this cluster to simulate multi-state reach
        selected_states = rng.sample(INDIAN_LOCATIONS, min(cluster["complaint_count"], len(INDIAN_LOCATIONS)))

        for i in range(cluster["complaint_count"]):
            complaint_idx += 1
            c_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
            state, districts = selected_states[i % len(selected_states)]
            district = rng.choice(districts)
            amount = round(rng.uniform(50000, 750000), 2)
            filed_time = now - timedelta(days=rng.randint(1, 45), hours=rng.randint(0, 23))

            template = rng.choice(NARRATIVE_TEMPLATES)
            narrative = template.format(wallet=w_addr, amount=f"{amount:,.2f}")

            complaint = {
                "id": c_id,
                "ncrp_ref": f"NCRP-2026-{complaint_idx:06d}",
                "source_platform": rng.choice(["ncrp", "sahyog", "manual"]),
                "complainant_id": str(uuid.uuid4()),
                "narrative_text": narrative,
                "fraud_typology": cluster["fraud_typology"],
                "amount_lost": amount,
                "filed_at": filed_time.isoformat(),
                "state": state,
                "district": district,
                "created_at": (filed_time + timedelta(minutes=5)).isoformat(),
            }
            complaints_list.append(complaint)

            complaint_wallets_list.append({
                "complaint_id": c_id,
                "wallet_id": w_id,
                "reported_at": (filed_time + timedelta(minutes=5)).isoformat(),
            })

    # 2. Generate isolated single-victim complaints and unshared wallets
    for _ in range(single_count):
        complaint_idx += 1
        c_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        w_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))

        chain = rng.choice(["BTC", "ETH", "TRON"])
        if chain == "BTC":
            addr = _random_btc_address(rng)
        elif chain == "ETH":
            addr = _random_eth_address(rng)
        else:
            addr = _random_tron_address(rng)

        state, districts = rng.choice(INDIAN_LOCATIONS)
        district = rng.choice(districts)
        amount = round(rng.uniform(15000, 300000), 2)
        filed_time = now - timedelta(days=rng.randint(1, 60))
        typology = rng.choice(FRAUD_TYPOLOGIES)

        wallets_list.append({
            "id": w_id,
            "address": addr,
            "chain": chain,
            "risk_score": None,
            "risk_tier": "unknown",
            "vasp_identified": None,
            "cluster_id": None,
            "first_seen": filed_time.isoformat(),
            "last_seen": filed_time.isoformat(),
        })

        narrative = f"Complainant reported fraudulent transaction to {addr} on {chain} blockchain."

        complaints_list.append({
            "id": c_id,
            "ncrp_ref": f"NCRP-2026-{complaint_idx:06d}",
            "source_platform": rng.choice(["ncrp", "sahyog", "manual"]),
            "complainant_id": str(uuid.uuid4()),
            "narrative_text": narrative,
            "fraud_typology": typology,
            "amount_lost": amount,
            "filed_at": filed_time.isoformat(),
            "state": state,
            "district": district,
            "created_at": filed_time.isoformat(),
        })

        complaint_wallets_list.append({
            "complaint_id": c_id,
            "wallet_id": w_id,
            "reported_at": filed_time.isoformat(),
        })

    return {
        "wallets": wallets_list,
        "complaints": complaints_list,
        "complaint_wallets": complaint_wallets_list,
        "metadata": {
            "total_complaints": len(complaints_list),
            "total_wallets": len(wallets_list),
            "total_links": len(complaint_wallets_list),
            "planted_clusters_count": len(PLANTED_SHARED_WALLETS),
        }
    }


async def seed_database_async(dataset: dict[str, Any]) -> None:
    """Insert the dataset directly into the PostgreSQL database using SQLAlchemy session."""
    from sqlalchemy.dialects.postgresql import insert
    from app.db.session import AsyncSessionLocal
    from app.models.wallet import Wallet
    from app.models.complaint import Complaint, ComplaintWallet

    async with AsyncSessionLocal() as session:
        # Insert wallets
        for w in dataset["wallets"]:
            stmt = insert(Wallet).values(
                id=uuid.UUID(w["id"]),
                address=w["address"],
                chain=w["chain"],
                risk_score=w["risk_score"],
                risk_tier=w["risk_tier"],
                vasp_identified=w["vasp_identified"],
                cluster_id=uuid.UUID(w["cluster_id"]) if w["cluster_id"] else None,
                first_seen=datetime.fromisoformat(w["first_seen"]) if w["first_seen"] else None,
                last_seen=datetime.fromisoformat(w["last_seen"]) if w["last_seen"] else None,
            ).on_conflict_do_nothing(index_elements=["address", "chain"])
            await session.execute(stmt)

        # Insert complaints
        for c in dataset["complaints"]:
            stmt = insert(Complaint).values(
                id=uuid.UUID(c["id"]),
                ncrp_ref=c["ncrp_ref"],
                source_platform=c["source_platform"],
                complainant_id=uuid.UUID(c["complainant_id"]) if c["complainant_id"] else None,
                narrative_text=c["narrative_text"],
                fraud_typology=c["fraud_typology"],
                amount_lost=c["amount_lost"],
                filed_at=datetime.fromisoformat(c["filed_at"]),
                state=c["state"],
                district=c["district"],
                created_at=datetime.fromisoformat(c["created_at"]),
            ).on_conflict_do_nothing(index_elements=["ncrp_ref"])
            await session.execute(stmt)

        # Insert complaint_wallets links
        for cw in dataset["complaint_wallets"]:
            stmt = insert(ComplaintWallet).values(
                complaint_id=uuid.UUID(cw["complaint_id"]),
                wallet_id=uuid.UUID(cw["wallet_id"]),
                reported_at=datetime.fromisoformat(cw["reported_at"]),
            ).on_conflict_do_nothing(index_elements=["complaint_id", "wallet_id"])
            await session.execute(stmt)

        await session.commit()
    print(f"Successfully seeded {len(dataset['complaints'])} complaints and {len(dataset['wallets'])} wallets into database.")


def main():
    parser = argparse.ArgumentParser(description="Synthetic NCRP Complaint Data Generator for Unigraph")
    parser.add_argument("--output", "-o", type=str, help="Output JSON filepath to save dataset")
    parser.add_argument("--seed-db", action="store_true", help="Seed database directly using current app settings")
    parser.add_argument("--count", type=int, default=35, help="Number of single-victim complaints to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    dataset = generate_synthetic_dataset(seed=args.seed, single_count=args.count)

    print(f"--- Synthetic NCRP Generator ---")
    print(f"Total Complaints: {dataset['metadata']['total_complaints']}")
    print(f"Total Wallets:    {dataset['metadata']['total_wallets']}")
    print(f"Planted Clusters: {dataset['metadata']['planted_clusters_count']}")
    for cluster in PLANTED_SHARED_WALLETS:
        print(f"  * {cluster['address']} ({cluster['chain']}) -> {cluster['complaint_count']} complaints ({cluster['description']})")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2)
        print(f"Dataset exported to {args.output}")

    if args.seed_db:
        print("Seeding database...")
        asyncio.run(seed_database_async(dataset))


if __name__ == "__main__":
    main()
