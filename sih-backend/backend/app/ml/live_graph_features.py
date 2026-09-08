"""
app/ml/live_graph_features.py — Compute engineered graph features from live Neo4j data.

For inference, we query the Neo4j graph to find:
  - illicit_neighbor_ratio_1hop: share of direct neighbors labeled illicit
  - illicit_neighbor_ratio_2hop: share of 2-hop neighbors labeled illicit
  - shortest_path_to_known_illicit: min distance to any illicit node (capped at 6)

The live Neo4j schema is bipartite:
    (:Wallet)-[:SENT]->(:Transaction)-[:RECEIVED_BY]->(:Wallet)
Wallet-to-wallet adjacency means the two Wallets are parties to a shared
Transaction. All queries below follow that schema (a direct `-[r]-` Wallet-Wallet
pattern silently returns zero rows and is NOT the correct physical model).

Graph-feature semantics mirror the training-time computation in
app/ml/graph_features.py exactly:
  - 2-hop neighbors exclude 1-hop neighbors and the wallet itself
  - shortest_path_to_known_illicit = 0 when the wallet itself is illicit, else
    the number of wallet-hops to the nearest illicit wallet, capped at 6.

If the graph neighborhood is too sparse or Neo4j is unavailable, we fall back to
defaults (0 ratios / 6 shortest path), reporting a mode that distinguishes
"ran successfully, found real neighbors" (loaded), "ran successfully, genuinely
zero neighbors" (empty), and "failed" (query error/timeout).
"""
import asyncio
import structlog

from app.graph.neo4j_client import run_query

logger = structlog.get_logger(__name__)

DEFAULT_GRAPH_FEATURES: dict[str, float] = {
    "illicit_neighbor_ratio_1hop": 0.0,
    "illicit_neighbor_ratio_2hop": 0.0,
    "shortest_path_to_known_illicit": 6,
}

# One wallet-to-wallet hop = SENT + RECEIVED_BY, i.e. 2 physical relationships.
# Cap of 6 wallet-hops => `*..12` relationships.
SHORTEST_PATH_REL_CAP = 12
ONE_HOP_LIMIT = 1000
TWO_HOP_LIMIT = 5000


async def _query_neighbors_1hop(address: str, chain: str) -> dict[str, bool]:
    """
    Return {neighbor_address: is_illicit} for all Wallets sharing a transaction
    with the target (both directions: senders of transactions the target
    received, and receivers of transactions the target sent).
    Deduplicates by address (the graph may hold duplicate Wallet nodes).
    """
    query = """
    MATCH (wallet:Wallet {address: $address, chain: $chain})
    OPTIONAL MATCH (sender:Wallet)-[:SENT]->(:Transaction)-[:RECEIVED_BY]->(wallet)
    WITH wallet, collect(DISTINCT sender) AS senders
    OPTIONAL MATCH (wallet)-[:SENT]->(:Transaction)-[:RECEIVED_BY]->(receiver:Wallet)
    WITH wallet, senders, collect(DISTINCT receiver) AS receivers
    WITH wallet,
         reduce(ns = [], n IN senders + receivers |
           CASE WHEN n IS NULL OR n IN ns THEN ns ELSE ns + [n] END
         ) AS nbrs
    UNWIND nbrs AS neighbor
    RETURN DISTINCT neighbor.address AS neighbor_address,
                    neighbor.illicit   AS is_illicit
    LIMIT $limit
    """
    rows = await run_query(
        query, {"address": address, "chain": chain, "limit": ONE_HOP_LIMIT}
    )
    neighbors: dict[str, bool] = {}
    for row in rows:
        addr = row.get("neighbor_address")
        if addr is None:
            continue
        neighbors[str(addr)] = bool(row.get("is_illicit") is True)
    return neighbors


async def _query_neighbors_2hop(
    address: str, chain: str, direct: list[str],
) -> dict[str, bool]:
    """
    Return {neighbor_address: is_illicit} for 2-hop neighbors, excluding the
    wallet itself and any 1-hop neighbor (matches graph_features.py semantics).
    """
    query = """
    MATCH (n1:Wallet) WHERE n1.address IN $direct AND n1.chain = $chain
    OPTIONAL MATCH (a:Wallet)-[:SENT]->(:Transaction)-[:RECEIVED_BY]->(n1)
    WITH n1, collect(DISTINCT a) AS senders
    OPTIONAL MATCH (n1)-[:SENT]->(:Transaction)-[:RECEIVED_BY]->(b:Wallet)
    WITH n1, senders, collect(DISTINCT b) AS receivers
    WITH n1,
         reduce(ns = [], n IN senders + receivers |
           CASE WHEN n IS NULL OR n IN ns THEN ns ELSE ns + [n] END
         ) AS nbrs
    UNWIND nbrs AS neighbor
    WITH DISTINCT neighbor
    WHERE neighbor.address <> $address AND NOT neighbor.address IN $direct
    RETURN DISTINCT neighbor.address AS neighbor_address,
                    neighbor.illicit   AS is_illicit
    LIMIT $limit
    """
    rows = await run_query(
        query,
        {
            "address": address,
            "chain": chain,
            "direct": direct,
            "limit": TWO_HOP_LIMIT,
        },
    )
    neighbors: dict[str, bool] = {}
    for row in rows:
        addr = row.get("neighbor_address")
        if addr is None:
            continue
        neighbors[str(addr)] = bool(row.get("is_illicit") is True)
    return neighbors


async def _query_shortest_path(address: str, chain: str) -> tuple[bool | None, int | None]:
    """
    Return (self_illicit, rel_length) where rel_length is the number of physical
    relationships on the shortest path to a Wallet with illicit=true (None when
    unreachable within the cap). Presence of the shortestPath bound is OPTIONAL,
    so a hitless run yields (self_illicit, None).
    """
    query = f"""
    MATCH (wallet:Wallet {{address: $address, chain: $chain}})
    OPTIONAL MATCH p = shortestPath(
      (wallet)-[:SENT|RECEIVED_BY*1..{SHORTEST_PATH_REL_CAP}]-(illicit:Wallet {{illicit: true}})
    )
    RETURN wallet.illicit AS self_illicit, length(p) AS rel_len
    LIMIT 1
    """
    rows = await run_query(query, {"address": address, "chain": chain})
    if not rows:
        return None, None
    return rows[0].get("self_illicit"), rows[0].get("rel_len")


async def compute_live_graph_features(
    address: str,
    chain: str = "BTC",
) -> tuple[dict[str, float], str]:
    """
    Compute graph topology features from live Neo4j data.

    Returns:
        (features, mode) where features has keys all in GRAPH_FEATURE_COLUMNS
        and mode is:
          - "loaded": queries ran successfully and at least one real neighbor
            was found
          - "empty":  queries ran successfully but the wallet has genuinely
            zero neighbors in the graph
          - "failed": a query errored (feature values degraded to defaults)
    """
    features = dict(DEFAULT_GRAPH_FEATURES)
    had_error = False

    # Query 1: 1-hop neighbors and their illicit status
    n_1hop = 0
    illicit_1hop = 0
    try:
        neighbors_1hop = await _query_neighbors_1hop(address, chain)
        n_1hop = len(neighbors_1hop)
        illicit_1hop = sum(1 for flag in neighbors_1hop.values() if flag)
        if n_1hop:
            features["illicit_neighbor_ratio_1hop"] = illicit_1hop / n_1hop
        logger.debug(
            "graph_features_1hop",
            address=address,
            chain=chain,
            neighbors_1hop=n_1hop,
            illicit_1hop=illicit_1hop,
        )
    except Exception as e:
        had_error = True
        logger.warning(
            "graph_features_1hop_failed",
            address=address,
            chain=chain,
            error=str(e),
        )
        features["illicit_neighbor_ratio_1hop"] = 0.0

    # Query 2: 2-hop neighbors (exclude 1-hop neighbors and self)
    n_2hop = 0
    illicit_2hop = 0
    try:
        if n_1hop:
            direct = list(neighbors_1hop.keys())
            neighbors_2hop = await _query_neighbors_2hop(address, chain, direct)
            n_2hop = len(neighbors_2hop)
            illicit_2hop = sum(1 for flag in neighbors_2hop.values() if flag)
            if n_2hop:
                features["illicit_neighbor_ratio_2hop"] = illicit_2hop / n_2hop
        logger.debug(
            "graph_features_2hop",
            address=address,
            chain=chain,
            neighbors_2hop=n_2hop,
            illicit_2hop=illicit_2hop,
        )
    except Exception as e:
        had_error = True
        logger.warning(
            "graph_features_2hop_failed",
            address=address,
            chain=chain,
            error=str(e),
        )
        features["illicit_neighbor_ratio_2hop"] = 0.0

    # Query 3: shortest path to any illicit node (0 if wallet illicit, capped 6)
    shortest_path = 6
    try:
        self_illicit, rel_len = await _query_shortest_path(address, chain)
        if self_illicit is True:
            shortest_path = 0
        elif rel_len is not None:
            shortest_path = int(min((rel_len + 1) // 2, 6))
        logger.debug(
            "graph_features_shortest_path",
            address=address,
            chain=chain,
            self_illicit=self_illicit,
            rel_len=rel_len,
            shortest_path=shortest_path,
        )
    except Exception as e:
        had_error = True
        logger.warning(
            "graph_features_shortest_path_failed",
            address=address,
            chain=chain,
            error=str(e),
        )
        shortest_path = 6
    features["shortest_path_to_known_illicit"] = shortest_path

    # Mode: genuinely-zero neighbors is distinct from "ran, found real ones"
    # and from "query failed". Both loaded and empty mean the queries succeeded.
    if had_error:
        mode = "failed"
    elif n_1hop > 0 or shortest_path == 0:
        mode = "loaded"
    else:
        mode = "empty"

    # Audit OBSERVABILITY (Group 1): the "did Neo4j return real topology vs.
    # empty" signal — neighbor/illicit counts + resolved mode, not raw records.
    logger.info(
        "graph_features_computed",
        address=address,
        chain=chain,
        mode=mode,
        neighbors_1hop=n_1hop,
        illicit_1hop=illicit_1hop,
        neighbors_2hop=n_2hop,
        illicit_2hop=illicit_2hop,
        shortest_path=shortest_path,
    )

    return features, mode


async def compute_live_graph_features_with_fallback(
    address: str,
    chain: str = "BTC",
    timeout_seconds: float = 2.0,
) -> tuple[dict[str, float], str]:
    """
    Compute graph features with timeout fallback.

    If Neo4j queries time out or fail outright, returns default graph features
    and mode='failed'.

    Returns:
        (features_dict, mode) where mode is 'loaded', 'empty' or 'failed'
    """
    try:
        features, mode = await asyncio.wait_for(
            compute_live_graph_features(address, chain),
            timeout=timeout_seconds,
        )
        return features, mode
    except asyncio.TimeoutError:
        logger.warning(
            "graph_features_timeout_fallback",
            address=address,
            chain=chain,
        )
        return dict(DEFAULT_GRAPH_FEATURES), "failed"
    except Exception as e:
        logger.warning(
            "graph_features_fallback",
            address=address,
            chain=chain,
            error=str(e),
        )
        return dict(DEFAULT_GRAPH_FEATURES), "failed"