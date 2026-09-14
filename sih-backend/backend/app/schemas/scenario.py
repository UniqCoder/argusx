"""
app/schemas/scenario.py — Read models for the seeded investigation scenarios.

Every field here is descriptive metadata about a seeded case. Nothing in this
schema feeds the engine; the engine reads the scenarios' transactions through
the fixture explorer like it reads any other chain data.
"""
from pydantic import BaseModel, Field

from app.schemas.common import Chain


class ScenarioComplaintRead(BaseModel):
    ncrp_ref: str
    source_platform: str
    state: str
    district: str
    fraud_typology: str
    amount_lost_inr: float


class ScenarioRead(BaseModel):
    key: str = Field(description="Stable identifier, e.g. 'telegram-task-scam'")
    title: str
    subtitle: str
    typology: str
    headline: str = Field(description="One line: what this case is here to demonstrate")
    demonstrates: list[str]
    anchor_address: str = Field(description="The reported wallet an investigator traces")
    anchor_chain: Chain
    asset: str
    chains: list[Chain] = Field(description="Every chain this case's money touches")
    victim_amount_inr: float
    complaint_count: int
    transaction_count: int
    complaints: list[ScenarioComplaintRead]
    case_id: str | None = Field(
        default=None,
        description="The seeded case, if the database has been seeded. Null means "
                    "the scenario is defined but not present in this database.",
    )


class ScenarioListResponse(BaseModel):
    seeded: bool = Field(description="False when no scenario has been seeded into this database")
    scenarios: list[ScenarioRead]
