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
import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings

logger = logging.getLogger(__name__)
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
    """
    driver = await get_driver()
    async with driver.session() as session:
        result = await session.run(cypher, parameters or {})
        records = await result.data()
    return records
