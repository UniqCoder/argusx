"""
app/services/scenarios — Seeded investigation scenarios.

Five fraud cases, defined as transaction lists, served to the taint engine
through the same `BlockchainExplorer` interface a live chain uses. See
definitions.py for why they exist and the rules they follow.
"""
from app.services.scenarios.definitions import (  # noqa: F401
    ALL_SCENARIOS,
    SCENARIOS_BY_KEY,
    Scenario,
    ScenarioComplaint,
    ScenarioRisk,
    ScenarioTx,
    all_scenario_addresses,
    is_scenario_address,
    scenario_for_address,
)
from app.services.scenarios.fixture_explorer import (  # noqa: F401
    FixtureExplorer,
    fixture_explorer_for,
    transactions_for,
)

__all__ = [
    "ALL_SCENARIOS",
    "SCENARIOS_BY_KEY",
    "Scenario",
    "ScenarioComplaint",
    "ScenarioRisk",
    "ScenarioTx",
    "all_scenario_addresses",
    "is_scenario_address",
    "scenario_for_address",
    "FixtureExplorer",
    "fixture_explorer_for",
    "transactions_for",
]
