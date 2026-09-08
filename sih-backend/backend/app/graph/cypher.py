"""
app/graph/cypher.py — Named Cypher query constants for Neo4j.

Centralised here so queries are visible, diffable, and not scattered across service files.
Import from here, never write raw Cypher in services.
"""

# Upsert wallet node
UPSERT_WALLET = """
MERGE (w:Wallet {address: $address, chain: $chain})
ON CREATE SET w.created_at = datetime(), w.first_seen = datetime($timestamp)
ON MATCH SET w.last_seen = datetime($timestamp)
RETURN w
"""

# Ingest transaction hop: (Wallet)-[:SENT]->(Transaction)-[:RECEIVED_BY]->(Wallet)
UPSERT_TRANSACTION_HOP = """
MERGE (w_from:Wallet {address: $from_address, chain: $chain})
ON CREATE SET w_from.first_seen = datetime($timestamp), w_from.created_at = datetime()
ON MATCH SET w_from.last_seen = datetime($timestamp)

MERGE (w_to:Wallet {address: $to_address, chain: $chain})
ON CREATE SET w_to.first_seen = datetime($timestamp), w_to.created_at = datetime()
ON MATCH SET w_to.last_seen = datetime($timestamp)

MERGE (tx:Transaction {tx_hash: $tx_hash})
ON CREATE SET tx.amount = $amount, tx.timestamp = datetime($timestamp), tx.chain = $chain
ON MATCH SET tx.amount = $amount, tx.timestamp = datetime($timestamp), tx.chain = $chain

MERGE (w_from)-[:SENT]->(tx)
MERGE (tx)-[:RECEIVED_BY]->(w_to)
"""

# Link destination wallet to known VASP entity
ATTACH_VASP_NODE = """
MERGE (w:Wallet {address: $address, chain: $chain})
MERGE (v:VASP {name: $vasp_name})
ON CREATE SET v.jurisdiction = $jurisdiction
MERGE (w)-[:DEPOSITS_TO]->(v)
"""

# Nearest VASP shortest-path query (1 to 5 hops BFS)
FIND_NEAREST_VASP_PATH = """
MATCH (w:Wallet {address: $address, chain: $chain})
MATCH (v:Wallet)-[:DEPOSITS_TO]->(vasp:VASP)
MATCH p = shortestPath((w)-[:SENT|RECEIVED_BY*1..10]->(v))
WHERE w <> v
RETURN p, vasp.name AS vasp_name, vasp.jurisdiction AS jurisdiction, length(p) / 2 AS hops_count
ORDER BY hops_count ASC
LIMIT 1
"""

# Query direct transaction hops for a wallet
GET_WALLET_HOPS = """
MATCH (w:Wallet {address: $address, chain: $chain})-[:SENT]->(tx:Transaction)-[:RECEIVED_BY]->(to:Wallet)
OPTIONAL MATCH (to)-[:DEPOSITS_TO]->(vasp:VASP)
RETURN w.address AS from_address, to.address AS to_address, tx.tx_hash AS tx_hash,
       tx.amount AS amount, toString(tx.timestamp) AS timestamp, tx.chain AS chain,
       vasp.name AS vasp_name
ORDER BY tx.timestamp DESC
LIMIT $limit
"""
