"""
app/graph/neo4j_client.py — Neo4j driver wrapper.

Phase 0: connection stub. Driver is created lazily on first use.
Phase 3 will add graph-build and nearest-VASP Cypher queries.

Neo4j schema (PRD §9.4):
  (:Wallet {address, chain})
  (:Transaction {tx_hash, amount, timestamp, chain})
  (:VASP {name, jurisdiction})
  (:Cluster {id, confidence})
  (:Wallet)-[:SENT]->(:Transaction)-[:RECEIVED_BY]->(:Wallet)
  (:Wallet)-[:BELONGS_TO]->(:Cluster)
  (:Wallet)-[:DEPOSITS_TO]->(:VASP)
"""
import structlog
from time import perf_counter
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

_driver: AsyncDriver | None = None


async def get_driver() -> AsyncDriver:
    """Return the singleton Neo4j async driver, creating it on first call."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        logger.info("neo4j_driver_created", extra={"uri": settings.neo4j_uri})
    return _driver


async def close_driver() -> None:
    """Close the driver — called on app shutdown."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
        logger.info("neo4j_driver_closed")


async def run_query(cypher: str, parameters: dict[str, Any] | None = None) -> list[dict]:
    """
    Execute a read Cypher query and return results as a list of dicts.
    Phase 3 will add write queries for graph building.

    Audit OBSERVABILITY (Group 1): every executed Cypher query is logged with
    its provenance (queried address), row count, and latency — the "did Neo4j
    return real data vs. empty/skip" signal. The full returned records are
    logged only at DEBUG level (Group 2, gated).
    """
    driver = await get_driver()
    params = parameters or {}
    start = perf_counter()
    async with driver.session() as session:
        result = await session.run(cypher, params)
        records = await result.data()
    elapsed_ms = (perf_counter() - start) * 1000.0

    query_tag = cypher[:60].replace("\n", " ").strip()
    if len(cypher) >= 15:
        logger.info(
            "neo4j_query",
            query_id=query_tag,
            param_address=params.get("address"),
            row_count=len(records),
            elapsed_ms=round(elapsed_ms, 2),
        )
        if records:
            logger.debug(
                "neo4j_query_records",
                query_id=query_tag,
                param_address=params.get("address"),
                records=records,
            )
    return records
