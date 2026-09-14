"""
app/services/scenarios/definitions.py — The five seeded investigation scenarios.

WHY THIS EXISTS
---------------
The live engine is honest, and honesty has a cost on a demo stage. Tracing a
real wallet takes tens of seconds of public-explorer calls, and whether that
wallet *happens* to pass through a mixer, a bridge and an exchange is not
something anyone can arrange. Several capabilities the system genuinely
implements therefore had no reliable way to be seen:

  - mixer detection        needs the trail to hit a curated mixer contract
  - bridge / cross-chain   same, for bridge contracts
  - cross-victim signal    needs several complaints naming one wallet
  - structuring / peel     needs a specific outflow shape
  - parked funds           needs a branch that received money and never moved it

THE RULES THIS FILE FOLLOWS
---------------------------
 1. It is DATA, not behaviour. Every scenario is a list of transactions. The
    nodes, edges, terminals, taint fractions, risk, correlation and PDF report
    are all *derived by the real engine* from these transactions — exactly the
    same code path a live trace takes. Nothing downstream is authored.
 2. It is NEVER a fallback. A failed or empty live trace shows the real error
    or the real empty result; it never silently becomes one of these.
 3. Addresses are synthetic and generated with correct checksums, so they pass
    the same validators that guard real input. (The frontend fixture this
    replaces had `0x0DEM0...` addresses containing a non-hex 'M', which every
    validator would have rejected — they only worked because they bypassed the
    API entirely.) EVM scenario addresses carry a `0x5eeded...` prefix so one
    pasted into a real explorer is visibly ours and resolves to nothing.
 4. The mixer, bridge and exchange contracts they touch ARE the real curated
    registry addresses from app/engine/registries.py and
    app/services/explorers/known_vasps.py, because the whole point is to watch
    real detection logic fire. The wallets around them are the fiction.

See docs/scenarios.md for the narrative version of each case.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.schemas.common import Chain
from app.services.explorers.address_validation import base58check_encode

# ── Real registry contracts (detection fires on these, not on our wallets) ───
MIXER_TORNADO_10 = "0x910Cbd523D972eb0a6f4cAe4618aD62622b39DbF"   # Tornado Cash 10 ETH
MIXER_TORNADO_01 = "0x12D66f87A04A9E220743712cE6d9bB1B5616B8Fc"   # Tornado Cash 0.1 ETH
BRIDGE_POLYGON = "0xA0c68C638235ee32657e8f720a23ceC1bFc77C77"     # Polygon PoS Bridge
BRIDGE_STARGATE = "0x8731d54E9D02c286767d56ac03e8037C07e01e98"    # Stargate Router
VASP_BINANCE_ETH = "0x28C6c06298d514Db089934071355E5743bf21d60"   # Binance (ETH)
VASP_BINANCE_ETH2 = "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549"  # Binance (ETH)
VASP_COINDCX_ETH = "0x71C7656EC7ab88b098defB751B7401B5f6d8976F"   # CoinDCX (India)
VASP_BINANCE_TRON = "TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7"          # Binance (TRON)
VASP_BINANCE_BTC = "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo"           # Binance (BTC)
VASP_COINBASE_BTC = "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h"  # Coinbase (BTC)
VASP_BITFINEX_BTC = "3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r"          # Bitfinex (BTC)


# ── Deterministic synthetic address generation ──────────────────────────────
# Generated rather than hand-typed so the checksums are actually correct and
# the addresses survive every shape/checksum validator in the codebase.

_EVM_PREFIX = "5eeded"  # "SEEDED" in hex-safe characters


def _digest(scenario: str, label: str, chain: str) -> bytes:
    return hashlib.sha256(f"argus-scenario|{scenario}|{label}|{chain}".encode()).digest()


def synth_address(scenario: str, label: str, chain: Chain) -> str:
    """A deterministic, structurally valid, obviously-synthetic address."""
    d = _digest(scenario, label, chain.value)
    if chain in (Chain.ETH, Chain.BSC, Chain.POLYGON):
        # 0x + "5eeded" + 34 hex = 42 chars, matches ^0x[0-9a-fA-F]{40}$
        return "0x" + _EVM_PREFIX + d.hex()[:34]
    if chain is Chain.TRON:
        return base58check_encode(0x41, d[:20])       # "T..." 34 chars
    if chain is Chain.BTC:
        return base58check_encode(0x00, d[:20])       # "1..." P2PKH
    raise ValueError(f"no address shape for chain {chain}")


def synth_tx_hash(scenario: str, index: int, chain: Chain) -> str:
    h = hashlib.sha256(f"argus-tx|{scenario}|{index}".encode()).hexdigest()
    if chain in (Chain.ETH, Chain.BSC, Chain.POLYGON):
        return "0x" + h
    return h  # BTC / TRON hashes are bare 64-hex


# ── Declarative scenario shapes ─────────────────────────────────────────────

@dataclass(frozen=True)
class ScenarioTx:
    """One transfer. `minute` is minutes after the scenario's `started_at`."""
    frm: str
    to: str
    amount: float
    asset: str
    minute: float
    chain: Chain
    asset_id: str | None = None


@dataclass(frozen=True)
class ScenarioComplaint:
    """An NCRP/SAHYOG complaint. Seeded into `complaints` + `complaint_wallets`."""
    ncrp_ref: str
    source_platform: str          # ncrp | sahyog | manual
    victim_label: str             # the victim's own wallet, by scenario label
    state: str
    district: str
    fraud_typology: str
    amount_lost_inr: float
    narrative: str
    filed_minute: float
    reported_address: str         # the wallet the complaint names — resolved late
    reported_chain: Chain


@dataclass(frozen=True)
class ScenarioRisk:
    """A Redis `risk:{CHAIN}:{address}` entry, so Deposit Watch scores for real."""
    address: str
    chain: Chain
    score: float
    tier: str
    reason: str


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    subtitle: str
    typology: str
    headline: str                 # what this case is here to demonstrate
    demonstrates: tuple[str, ...]
    anchor_address: str
    anchor_chain: Chain
    asset: str
    started_at: datetime
    victim_amount_inr: float
    inr_per_unit: float           # for display: asset units -> INR
    complaints: tuple[ScenarioComplaint, ...]
    txs: tuple[ScenarioTx, ...]
    risk_entries: tuple[ScenarioRisk, ...]
    addresses: dict[str, str] = field(default_factory=dict)  # label -> address

    def tx_at(self, index: int) -> str:
        return synth_tx_hash(self.key, index, self.anchor_chain)


def _t(base: datetime, minute: float) -> datetime:
    return base + timedelta(minutes=minute)


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 1 — Telegram task-scam syndicate (ETH -> Polygon)
# Headline: CROSS-VICTIM CONVERGENCE. Three separate NCRP complaints from three
# states name the same collector wallet. The trail then splits: one branch dies
# in Tornado Cash, the other peels down and bridges to Polygon before cashing
# out at a Binance deposit address.
# ═══════════════════════════════════════════════════════════════════════════
_S1 = "telegram-task-scam"
_S1_T0 = datetime(2026, 8, 14, 9, 12, tzinfo=timezone.utc)
_s1 = lambda label, chain=Chain.ETH: synth_address(_S1, label, chain)  # noqa: E731

S1_COLLECTOR = _s1("collector")
SCENARIO_1 = Scenario(
    key=_S1,
    title="Telegram task-scam syndicate",
    subtitle="Three victims, one collector wallet, mixer + cross-chain off-ramp",
    typology="Task-based job fraud",
    headline=(
        "Three NCRP complaints from three different states independently name the "
        "same collector wallet. That convergence is the fraud signal."
    ),
    demonstrates=(
        "Cross-victim correlation",
        "Mixer detection (hard stop)",
        "Cross-chain bridge hand-off",
        "VASP off-ramp attribution",
        "Parked funds still recoverable",
    ),
    anchor_address=S1_COLLECTOR,
    anchor_chain=Chain.ETH,
    asset="ETH",
    started_at=_S1_T0,
    victim_amount_inr=2_560_000.0,
    inr_per_unit=294_000.0,
    complaints=(
        ScenarioComplaint(
            ncrp_ref="NCRP-2026-114052", source_platform="ncrp", victim_label="victim_a",
            state="Maharashtra", district="Pune", fraud_typology="Task-based job fraud",
            amount_lost_inr=1_234_800.0, filed_minute=180,
            narrative=(
                "Complainant was added to a Telegram group offering paid review tasks. "
                "After three small payouts the group demanded a deposit to unlock a "
                "higher tier. Complainant transferred 4.20 ETH to the wallet supplied "
                "in the group and received nothing."
            ),
            reported_address=S1_COLLECTOR, reported_chain=Chain.ETH,
        ),
        ScenarioComplaint(
            ncrp_ref="NCRP-2026-114188", source_platform="ncrp", victim_label="victim_b",
            state="Karnataka", district="Bengaluru Urban", fraud_typology="Task-based job fraud",
            amount_lost_inr=779_100.0, filed_minute=420,
            narrative=(
                "Complainant responded to a WhatsApp message advertising part-time "
                "hotel-rating work. Was instructed to buy ETH and send it to a 'task "
                "wallet' to activate withdrawals. 2.65 ETH sent; account then frozen "
                "by the operators."
            ),
            reported_address=S1_COLLECTOR, reported_chain=Chain.ETH,
        ),
        ScenarioComplaint(
            ncrp_ref="NCRP-2026-114363", source_platform="sahyog", victim_label="victim_c",
            state="Delhi", district="South West Delhi", fraud_typology="Task-based job fraud",
            amount_lost_inr=543_900.0, filed_minute=1_140,
            narrative=(
                "Complainant was recruited through an Instagram advertisement for "
                "'app testing' work. Transferred 1.85 ETH as a refundable security "
                "deposit. The operators stopped responding immediately afterwards."
            ),
            reported_address=S1_COLLECTOR, reported_chain=Chain.ETH,
        ),
    ),
    txs=(
        # Hop -1: the three victims fund the collector within a single morning.
        ScenarioTx(_s1("victim_a"), S1_COLLECTOR, 4.20, "ETH", 0, Chain.ETH),
        ScenarioTx(_s1("victim_b"), S1_COLLECTOR, 2.65, "ETH", 3, Chain.ETH),
        ScenarioTx(_s1("victim_c"), S1_COLLECTOR, 1.85, "ETH", 5, Chain.ETH),
        # Hop 1: the collector layers out within six minutes of the last deposit.
        ScenarioTx(S1_COLLECTOR, _s1("layer_1"), 5.10, "ETH", 11, Chain.ETH),
        ScenarioTx(S1_COLLECTOR, _s1("layer_2"), 3.20, "ETH", 14, Chain.ETH),
        # A deliberate sub-dust outflow, so branch pruning is visible and counted.
        ScenarioTx(S1_COLLECTOR, _s1("dust_sink"), 0.00004, "ETH", 15, Chain.ETH),
        # Branch A: straight into a Tornado Cash pool. The engine stops there.
        ScenarioTx(_s1("layer_1"), MIXER_TORNADO_10, 5.05, "ETH", 19, Chain.ETH),
        # Branch B: a peel chain, shedding a little at each step.
        ScenarioTx(_s1("layer_2"), _s1("peel_1"), 3.05, "ETH", 22, Chain.ETH),
        ScenarioTx(_s1("peel_1"), _s1("peel_2"), 2.84, "ETH", 27, Chain.ETH),
        # ...and one peeled-off branch that receives money and never moves it.
        ScenarioTx(_s1("peel_1"), _s1("parked"), 0.19, "ETH", 28, Chain.ETH),
        # Branch B continues into the Polygon PoS bridge.
        ScenarioTx(_s1("peel_2"), BRIDGE_POLYGON, 2.80, "ETH", 34, Chain.ETH),
        # The matching leg on the destination chain. The cross-chain heuristic
        # (app/engine/crosschain.py) has to find this by value and time window —
        # it is not handed the link.
        ScenarioTx(BRIDGE_POLYGON, _s1("poly_1", Chain.POLYGON), 2.79, "ETH", 41, Chain.POLYGON),
        ScenarioTx(_s1("poly_1", Chain.POLYGON), _s1("poly_2", Chain.POLYGON), 2.74, "ETH", 48, Chain.POLYGON),
        # Off-ramp: a Binance deposit address.
        ScenarioTx(_s1("poly_2", Chain.POLYGON), VASP_BINANCE_ETH, 2.70, "ETH", 56, Chain.POLYGON),
    ),
    risk_entries=(
        ScenarioRisk(S1_COLLECTOR, Chain.ETH, 0.94, "critical",
                     "Collector wallet named by 3 separate NCRP complaints"),
        ScenarioRisk(_s1("layer_1"), Chain.ETH, 0.88, "critical",
                     "One hop from a 3-complaint collector; funds sent to Tornado Cash"),
        ScenarioRisk(_s1("peel_2"), Chain.ETH, 0.81, "high",
                     "Peel-chain hop that bridged tainted funds to Polygon"),
    ),
    addresses={
        "collector": S1_COLLECTOR,
        "victim_a": _s1("victim_a"), "victim_b": _s1("victim_b"), "victim_c": _s1("victim_c"),
        "layer_1": _s1("layer_1"), "layer_2": _s1("layer_2"), "dust_sink": _s1("dust_sink"),
        "peel_1": _s1("peel_1"), "peel_2": _s1("peel_2"), "parked": _s1("parked"),
        "poly_1": _s1("poly_1", Chain.POLYGON), "poly_2": _s1("poly_2", Chain.POLYGON),
    },
)


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 2 — Pig-butchering cash-out (TRON, USDT-TRC20)
# Headline: RAPID MOVEMENT. Six hops in eleven minutes, straight to an exchange
# deposit address. Nothing clever, just speed — this is what the sub-200ms
# deposit check exists to catch before the funds are credited.
# ═══════════════════════════════════════════════════════════════════════════
_S2 = "pig-butchering-cashout"
_S2_T0 = datetime(2026, 8, 21, 18, 41, tzinfo=timezone.utc)
_s2 = lambda label: synth_address(_S2, label, Chain.TRON)  # noqa: E731
_USDT_TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

S2_COLLECTOR = _s2("collector")
S2_CASHOUT = _s2("mule_4")
SCENARIO_2 = Scenario(
    key=_S2,
    title="Pig-butchering cash-out",
    subtitle="37,000 USDT through six wallets to an exchange in eleven minutes",
    typology="Investment / romance fraud",
    headline=(
        "The entire laundering chain completes in eleven minutes. By the time a "
        "complaint is filed the funds are already at an exchange deposit address — "
        "which is exactly why the deposit check runs before crediting."
    ),
    demonstrates=(
        "Rapid fund movement",
        "Multi-hop layering",
        "Rapid movement toward an exchange",
        "Real-time deposit screening",
    ),
    anchor_address=S2_COLLECTOR,
    anchor_chain=Chain.TRON,
    asset="USDT",
    started_at=_S2_T0,
    victim_amount_inr=3_108_000.0,
    inr_per_unit=84.0,
    complaints=(
        ScenarioComplaint(
            ncrp_ref="NCRP-2026-121907", source_platform="ncrp", victim_label="victim",
            state="Telangana", district="Hyderabad", fraud_typology="Investment fraud",
            amount_lost_inr=3_108_000.0, filed_minute=2_880,
            narrative=(
                "Complainant was cultivated over four months on a dating application "
                "and moved to a trading platform showing fabricated profits. "
                "Transferred 37,000 USDT-TRC20 in a final 'tax clearance' payment. "
                "The platform went offline the same evening."
            ),
            reported_address=S2_COLLECTOR, reported_chain=Chain.TRON,
        ),
    ),
    txs=(
        ScenarioTx(_s2("victim"), S2_COLLECTOR, 37_000.0, "USDT", 0, Chain.TRON, _USDT_TRC20),
        ScenarioTx(S2_COLLECTOR, _s2("mule_1"), 36_550.0, "USDT", 2, Chain.TRON, _USDT_TRC20),
        ScenarioTx(_s2("mule_1"), _s2("mule_2"), 36_200.0, "USDT", 4, Chain.TRON, _USDT_TRC20),
        ScenarioTx(_s2("mule_2"), _s2("mule_3"), 35_900.0, "USDT", 6, Chain.TRON, _USDT_TRC20),
        ScenarioTx(_s2("mule_3"), S2_CASHOUT, 35_600.0, "USDT", 8, Chain.TRON, _USDT_TRC20),
        ScenarioTx(S2_CASHOUT, VASP_BINANCE_TRON, 35_300.0, "USDT", 11, Chain.TRON, _USDT_TRC20),
        # A small native-TRX outflow, so "other asset branch" counting is exercised
        # rather than being silently folded into the USDT trail.
        ScenarioTx(S2_COLLECTOR, _s2("gas_funder"), 120.0, "TRX", 3, Chain.TRON),
    ),
    risk_entries=(
        ScenarioRisk(S2_COLLECTOR, Chain.TRON, 0.91, "critical",
                     "Reported in an active investment-fraud complaint"),
        ScenarioRisk(S2_CASHOUT, Chain.TRON, 0.86, "critical",
                     "Final hop before a Binance deposit; 5 hops from a reported wallet"),
        ScenarioRisk(_s2("mule_2"), Chain.TRON, 0.62, "high",
                     "Mid-chain layering wallet, 11-minute hold time"),
    ),
    addresses={
        "collector": S2_COLLECTOR, "victim": _s2("victim"),
        "mule_1": _s2("mule_1"), "mule_2": _s2("mule_2"), "mule_3": _s2("mule_3"),
        "mule_4": S2_CASHOUT, "gas_funder": _s2("gas_funder"),
    },
)


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 3 — Investment-fraud smurfing (BTC)
# Headline: STRUCTURING. 4.85 BTC is split into twelve near-identical
# sub-threshold amounts inside four minutes, then reconverges on three exchange
# deposit addresses. The fan-out is the tell, and the reconvergence is what
# makes clustering worth doing.
# ═══════════════════════════════════════════════════════════════════════════
_S3 = "investment-smurfing"
_S3_T0 = datetime(2026, 7, 30, 4, 5, tzinfo=timezone.utc)
_s3 = lambda label: synth_address(_S3, label, Chain.BTC)  # noqa: E731

S3_COLLECTOR = _s3("collector")


def _s3_smurf_txs() -> tuple[ScenarioTx, ...]:
    out: list[ScenarioTx] = []
    # Twelve structured outflows of nearly the same size, 20 seconds apart.
    amounts = [0.405, 0.402, 0.408, 0.399, 0.404, 0.401,
               0.407, 0.398, 0.403, 0.406, 0.400, 0.397]
    for i, amt in enumerate(amounts):
        out.append(ScenarioTx(S3_COLLECTOR, _s3(f"smurf_{i + 1}"), amt, "BTC",
                              2 + i / 3.0, Chain.BTC))
    # Reconvergence: four smurfs into one Binance deposit, three into Coinbase,
    # two into Bitfinex — the shared-destination pattern clustering keys on.
    for i, minute in zip((1, 2, 3, 4), (14, 16, 19, 23)):
        out.append(ScenarioTx(_s3(f"smurf_{i}"), VASP_BINANCE_BTC, 0.396, "BTC",
                              minute, Chain.BTC))
    for i, minute in zip((5, 6, 7), (15, 21, 26)):
        out.append(ScenarioTx(_s3(f"smurf_{i}"), VASP_COINBASE_BTC, 0.394, "BTC",
                              minute, Chain.BTC))
    for i, minute in zip((8, 9), (31, 38)):
        out.append(ScenarioTx(_s3(f"smurf_{i}"), VASP_BITFINEX_BTC, 0.392, "BTC",
                              minute, Chain.BTC))
    # smurf_10 peels once more before cashing out.
    out.append(ScenarioTx(_s3("smurf_10"), _s3("peel_a"), 0.398, "BTC", 44, Chain.BTC))
    out.append(ScenarioTx(_s3("peel_a"), VASP_BINANCE_BTC, 0.395, "BTC", 52, Chain.BTC))
    # smurf_11 and smurf_12 receive and never move: funds still sitting there.
    return tuple(out)


SCENARIO_3 = Scenario(
    key=_S3,
    title="Investment-fraud smurfing",
    subtitle="4.85 BTC split twelve ways, reconverging on three exchange deposits",
    typology="Investment fraud",
    headline=(
        "Twelve near-identical outflows inside four minutes is structuring, not "
        "commerce. Seven of them reconverge on the same three exchange deposit "
        "addresses, which is what ties the twelve wallets into one operator."
    ),
    demonstrates=(
        "Structuring / smurfing detection",
        "Fan-out pattern",
        "Wallet clustering by shared deposit",
        "Multiple VASP off-ramps",
        "Funds still parked and recoverable",
    ),
    anchor_address=S3_COLLECTOR,
    anchor_chain=Chain.BTC,
    asset="BTC",
    started_at=_S3_T0,
    victim_amount_inr=4_216_000.0,
    inr_per_unit=8_690_000.0,
    complaints=(
        ScenarioComplaint(
            ncrp_ref="NCRP-2026-108441", source_platform="ncrp", victim_label="victim",
            state="Gujarat", district="Surat", fraud_typology="Investment fraud",
            amount_lost_inr=4_216_000.0, filed_minute=4_320,
            narrative=(
                "Complainant invested through a website presenting itself as a "
                "SEBI-registered commodity advisory. Was instructed to settle in BTC "
                "for 'faster clearing'. 4.85 BTC transferred in one payment. "
                "Withdrawal requests were met with escalating fee demands."
            ),
            reported_address=S3_COLLECTOR, reported_chain=Chain.BTC,
        ),
    ),
    txs=(
        ScenarioTx(_s3("victim"), S3_COLLECTOR, 4.85, "BTC", 0, Chain.BTC),
    ) + _s3_smurf_txs(),
    risk_entries=(
        ScenarioRisk(S3_COLLECTOR, Chain.BTC, 0.89, "critical",
                     "Reported wallet; structured 4.85 BTC into 12 outflows in 4 minutes"),
        ScenarioRisk(_s3("smurf_1"), Chain.BTC, 0.74, "high",
                     "Structuring output; deposited to Binance within 14 minutes"),
        ScenarioRisk(_s3("peel_a"), Chain.BTC, 0.68, "high",
                     "Peel hop between a structuring output and an exchange deposit"),
    ),
    addresses={
        "collector": S3_COLLECTOR, "victim": _s3("victim"), "peel_a": _s3("peel_a"),
        **{f"smurf_{i}": _s3(f"smurf_{i}") for i in range(1, 13)},
    },
)


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 4 — Ransomware payout (ETH)
# Headline: MIXER + DORMANT BURST. The payout sits untouched for forty days,
# then moves everything in under four minutes. Two branches die in Tornado Cash
# pools; the third is still sitting in a wallet, which is the only branch a
# freeze request can still reach.
# ═══════════════════════════════════════════════════════════════════════════
_S4 = "ransomware-payout"
_S4_T0 = datetime(2026, 6, 18, 2, 30, tzinfo=timezone.utc)
_s4 = lambda label: synth_address(_S4, label, Chain.ETH)  # noqa: E731
_DORMANT = 40 * 24 * 60  # forty days, in minutes

S4_RANSOM = _s4("ransom_wallet")
SCENARIO_4 = Scenario(
    key=_S4,
    title="Ransomware payout",
    subtitle="Dormant for forty days, then emptied into mixers in four minutes",
    typology="Ransomware / extortion",
    headline=(
        "26.5 ETH sat untouched for forty days and then moved in under four "
        "minutes. Two branches end inside Tornado Cash and are unrecoverable. "
        "The third never moved — that is the branch worth a freeze request."
    ),
    demonstrates=(
        "Mixer / tumbler interaction",
        "Dormant-then-burst behaviour",
        "Honest dead end (mixer boundary)",
        "Parked funds, still recoverable",
    ),
    anchor_address=S4_RANSOM,
    anchor_chain=Chain.ETH,
    asset="ETH",
    started_at=_S4_T0,
    victim_amount_inr=7_791_000.0,
    inr_per_unit=294_000.0,
    complaints=(
        ScenarioComplaint(
            ncrp_ref="NCRP-2026-097220", source_platform="sahyog", victim_label="victim",
            state="Tamil Nadu", district="Chennai", fraud_typology="Ransomware",
            amount_lost_inr=7_791_000.0, filed_minute=60,
            narrative=(
                "A private diagnostics chain reported encryption of its patient "
                "record systems with a ransom demand payable in ETH. Management "
                "paid 26.50 ETH to the address supplied in the ransom note before "
                "reporting the incident."
            ),
            reported_address=S4_RANSOM, reported_chain=Chain.ETH,
        ),
    ),
    txs=(
        ScenarioTx(_s4("victim"), S4_RANSOM, 26.50, "ETH", 0, Chain.ETH),
        # Forty days of nothing, then everything at once.
        ScenarioTx(S4_RANSOM, _s4("split_1"), 10.05, "ETH", _DORMANT, Chain.ETH),
        ScenarioTx(S4_RANSOM, _s4("split_2"), 10.05, "ETH", _DORMANT + 1.5, Chain.ETH),
        ScenarioTx(S4_RANSOM, _s4("split_3"), 6.30, "ETH", _DORMANT + 3.5, Chain.ETH),
        ScenarioTx(_s4("split_1"), MIXER_TORNADO_10, 10.00, "ETH", _DORMANT + 9, Chain.ETH),
        ScenarioTx(_s4("split_2"), MIXER_TORNADO_01, 10.00, "ETH", _DORMANT + 12, Chain.ETH),
        # split_3 receives and stops. No outflow at all.
    ),
    risk_entries=(
        ScenarioRisk(S4_RANSOM, Chain.ETH, 0.97, "critical",
                     "Ransomware payout address named in a filed complaint"),
        ScenarioRisk(_s4("split_1"), Chain.ETH, 0.92, "critical",
                     "Sent 10 ETH directly into a Tornado Cash pool"),
        ScenarioRisk(_s4("split_3"), Chain.ETH, 0.90, "critical",
                     "Holds 6.30 ETH of ransomware proceeds; no outflow observed"),
    ),
    addresses={
        "ransom_wallet": S4_RANSOM, "victim": _s4("victim"),
        "split_1": _s4("split_1"), "split_2": _s4("split_2"), "split_3": _s4("split_3"),
    },
)


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 5 — Cross-chain drainer (ETH -> Polygon -> BSC)
# Headline: BRIDGE HOPPING. Two bridge crossings before the off-ramp. Without
# cross-chain continuation this trail stops dead at the first bridge and the
# exchange deposit is never found.
# ═══════════════════════════════════════════════════════════════════════════
_S5 = "cross-chain-drainer"
_S5_T0 = datetime(2026, 9, 2, 13, 26, tzinfo=timezone.utc)
_s5 = lambda label, chain=Chain.ETH: synth_address(_S5, label, chain)  # noqa: E731

S5_DRAINER = _s5("drainer")
SCENARIO_5 = Scenario(
    key=_S5,
    title="Cross-chain wallet drainer",
    subtitle="Ethereum to Polygon to BSC, two bridges before the off-ramp",
    typology="Phishing / wallet drainer",
    headline=(
        "The operator crosses two bridges to break the trail. Follow only one "
        "chain and the money vanishes at the first bridge; follow the value "
        "across, and it reappears at a Binance deposit address two chains later."
    ),
    demonstrates=(
        "Cross-chain analysis across three blockchains",
        "Bridge transaction detection",
        "Unified multi-chain graph",
        "VASP off-ramp after chain hopping",
    ),
    anchor_address=S5_DRAINER,
    anchor_chain=Chain.ETH,
    asset="ETH",
    started_at=_S5_T0,
    victim_amount_inr=4_645_000.0,
    inr_per_unit=294_000.0,
    complaints=(
        ScenarioComplaint(
            ncrp_ref="NCRP-2026-126714", source_platform="ncrp", victim_label="victim",
            state="West Bengal", district="Kolkata", fraud_typology="Phishing",
            amount_lost_inr=4_645_000.0, filed_minute=95,
            narrative=(
                "Complainant connected a hardware wallet to a cloned airdrop site "
                "and approved what appeared to be a claim transaction. 15.80 ETH "
                "was removed from the wallet in a single transfer minutes later."
            ),
            reported_address=S5_DRAINER, reported_chain=Chain.ETH,
        ),
    ),
    txs=(
        ScenarioTx(_s5("victim"), S5_DRAINER, 15.80, "ETH", 0, Chain.ETH),
        ScenarioTx(S5_DRAINER, _s5("hop_1"), 15.60, "ETH", 7, Chain.ETH),
        ScenarioTx(_s5("hop_1"), BRIDGE_POLYGON, 15.50, "ETH", 16, Chain.ETH),
        # Crossing 1: Ethereum -> Polygon.
        ScenarioTx(BRIDGE_POLYGON, _s5("poly_1", Chain.POLYGON), 15.46, "ETH", 24, Chain.POLYGON),
        ScenarioTx(_s5("poly_1", Chain.POLYGON), _s5("poly_2", Chain.POLYGON), 15.20, "ETH", 39, Chain.POLYGON),
        ScenarioTx(_s5("poly_2", Chain.POLYGON), BRIDGE_STARGATE, 15.02, "ETH", 51, Chain.POLYGON),
        # Crossing 2: Polygon -> BSC.
        ScenarioTx(BRIDGE_STARGATE, _s5("bsc_1", Chain.BSC), 14.95, "ETH", 62, Chain.BSC),
        ScenarioTx(_s5("bsc_1", Chain.BSC), VASP_BINANCE_ETH2, 14.80, "ETH", 78, Chain.BSC),
    ),
    risk_entries=(
        ScenarioRisk(S5_DRAINER, Chain.ETH, 0.93, "critical",
                     "Drainer address reported in a phishing complaint"),
        ScenarioRisk(_s5("hop_1"), Chain.ETH, 0.84, "critical",
                     "Bridged 15.5 ETH of drained funds to Polygon within 16 minutes"),
    ),
    addresses={
        "drainer": S5_DRAINER, "victim": _s5("victim"), "hop_1": _s5("hop_1"),
        "poly_1": _s5("poly_1", Chain.POLYGON), "poly_2": _s5("poly_2", Chain.POLYGON),
        "bsc_1": _s5("bsc_1", Chain.BSC),
    },
)


# ── Registry ────────────────────────────────────────────────────────────────

ALL_SCENARIOS: tuple[Scenario, ...] = (
    SCENARIO_1, SCENARIO_2, SCENARIO_3, SCENARIO_4, SCENARIO_5,
)

SCENARIOS_BY_KEY: dict[str, Scenario] = {s.key: s for s in ALL_SCENARIOS}


def _build_address_index() -> dict[tuple[str, str], str]:
    """(lowercased address, chain) -> scenario key, for every address a scenario owns."""
    index: dict[tuple[str, str], str] = {}
    for scenario in ALL_SCENARIOS:
        for tx in scenario.txs:
            for addr in (tx.frm, tx.to):
                index[(addr.lower(), tx.chain.value)] = scenario.key
    return index


ADDRESS_INDEX: dict[tuple[str, str], str] = _build_address_index()


def scenario_for_address(address: str, chain: str) -> Scenario | None:
    """
    The scenario that owns `address` on `chain`, or None for a live address.

    This is the single gate that decides whether the fixture explorer or a real
    public explorer answers for an address. Registry contracts (mixers, bridges,
    exchanges) appear inside scenarios, so they resolve here too — but only on
    the chain the scenario actually places them on, which is why a live ETH
    trace that reaches Tornado Cash is unaffected: it terminates at the mixer
    before any explorer is consulted.
    """
    key = ADDRESS_INDEX.get((address.strip().lower(), chain))
    return SCENARIOS_BY_KEY.get(key) if key else None


def is_scenario_address(address: str, chain: str) -> bool:
    return (address.strip().lower(), chain) in ADDRESS_INDEX


def all_scenario_addresses() -> list[tuple[str, str]]:
    """Every (address, chain) any scenario touches — used by the reset script."""
    seen: dict[tuple[str, str], tuple[str, str]] = {}
    for scenario in ALL_SCENARIOS:
        for tx in scenario.txs:
            for addr in (tx.frm, tx.to):
                seen[(addr.lower(), tx.chain.value)] = (addr, tx.chain.value)
    return list(seen.values())
