"""Route 2 — "economy teeth": conditional salary + daily overhead drain.

Today salary is UNCONDITIONAL — every non-quarantined agent banks its full
``adef.salary`` regardless of output, which violates principle.md §2.2
("pay follows demonstrable completion, not claimed effort") for the salary
component. Route 2 splits salary into an unconditional solvency FLOOR
(``salary_base_fraction``) and a PERFORMANCE slice forfeited on an idle day,
plus a flat ``daily_overhead`` cost-of-living drain so pure idleness is a
slow loss. These tests assert the real wallet/ledger state deltas each knob
produces (P3) and that the overhead drain never inflates the attack
economic-drain metric (principle.md §3.5/§4).

Driven through the engine ``_barrier`` with the StubRuntime; no live API.
"""

from __future__ import annotations

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aces.config import load_config
from aces.database import Database
from aces.defenses import DefenseManager
from aces.engine import SimulationEngine
from aces.metrics import MetricsComputer
from aces.models import (
    AgentStatus, LedgerEntry, LedgerEntryType,
)
from tests.stub_runtime import StubRuntime

CFG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def _cfg():
    return load_config(
        enterprise_path=os.path.join(CFG_DIR, "community_research_enterprise.yaml"),
        experiment_path=os.path.join(CFG_DIR, "community_research_experiment.yaml"),
        attack_path=os.path.join(CFG_DIR, "community_research_attacks.yaml"),
    )


@pytest.fixture
def cfg():
    return _cfg()


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


@pytest.fixture
def engine(db, cfg):
    eng = SimulationEngine(
        cfg=cfg, db=db,
        runtime=StubRuntime(rng=random.Random(7)),
        run_id="teeth-run",
        rng=random.Random(7),
    )
    eng.metrics_computer = MetricsComputer(
        db, csri_weights=cfg.experiment.csri_weights)
    eng.defense_manager = DefenseManager(
        cfg.defenses, db, eng.services, random.Random(7))
    eng.init_world()
    return eng


def _salary_of(engine, agent_id: str) -> float:
    """The agent's own daily salary (per-agent override, else default)."""
    for adef in engine.cfg.enterprise.agents:
        if adef.id == agent_id:
            return adef.salary
    return engine.cfg.enterprise.salary_per_day


def _reward(engine, agent_id: str, amount: float, day: int = 1) -> None:
    """Write a verified REWARD ledger entry — the pay-on-provable-outcome
    signal economic_summary_for_agent reads as 'did provable work today'."""
    engine.db.insert_ledger_entry(LedgerEntry(
        agent_id=agent_id, entry_type=LedgerEntryType.REWARD,
        amount=amount, description="verified job reward", sim_day=day,
    ))
    a = engine.db.get_agent(agent_id)
    a.wallet_balance += amount
    engine.db.update_agent(a)


def _salary_entries(engine, agent_id: str, day: int = 1):
    return [e for e in engine.db.get_ledger_for_day(day)
            if e.entry_type == LedgerEntryType.SALARY
            and e.agent_id == agent_id]


def _overhead_entries(engine, agent_id: str, day: int = 1):
    return [e for e in engine.db.get_ledger_for_day(day)
            if e.entry_type == LedgerEntryType.OVERHEAD
            and e.agent_id == agent_id]


# ---------------------------------------------------------------------------
# (a) conditional salary — idle agent gets ONLY base; productive gets base+perf
# ---------------------------------------------------------------------------

def test_conditional_salary_idle_gets_base_only(engine):
    engine.cfg.enterprise.salary_base_fraction = 0.5
    engine.cfg.enterprise.daily_overhead = 0.0

    idle = "eng_kevin"
    salary = _salary_of(engine, idle)
    base = round(salary * 0.5, 2)
    before = engine.db.get_agent(idle).wallet_balance

    engine._barrier(day=1)

    after = engine.db.get_agent(idle).wallet_balance
    # Idle agent (rewards_today == 0): ONLY the base slice is paid.
    assert after == pytest.approx(before + base)
    entries = _salary_entries(engine, idle)
    assert len(entries) == 1
    assert entries[0].amount == pytest.approx(base)
    assert entries[0].description == "base salary day 1"


def test_conditional_salary_productive_gets_base_plus_perf(engine):
    engine.cfg.enterprise.salary_base_fraction = 0.5
    engine.cfg.enterprise.daily_overhead = 0.0

    worker = "eng_kevin"
    salary = _salary_of(engine, worker)
    base = round(salary * 0.5, 2)
    perf = round(salary - base, 2)

    # Verified work today → entitles the performance slice.
    _reward(engine, worker, 30.0, day=1)
    before = engine.db.get_agent(worker).wallet_balance

    engine._barrier(day=1)

    after = engine.db.get_agent(worker).wallet_balance
    # Productive agent banks BOTH slices (rewards already in wallet via _reward).
    assert after == pytest.approx(before + base + perf)
    entries = sorted(_salary_entries(engine, worker), key=lambda e: e.amount)
    assert len(entries) == 2
    assert sum(e.amount for e in entries) == pytest.approx(salary)
    descs = {e.description for e in entries}
    assert descs == {"base salary day 1", "performance salary day 1"}


# ---------------------------------------------------------------------------
# (b) daily overhead — every non-quarantined agent drained; quarantined skipped
# ---------------------------------------------------------------------------

def test_daily_overhead_charges_every_active_agent(engine):
    engine.cfg.enterprise.salary_base_fraction = 1.0
    engine.cfg.enterprise.daily_overhead = 25.0

    active = "eng_kevin"
    before = engine.db.get_agent(active).wallet_balance
    salary = _salary_of(engine, active)

    engine._barrier(day=1)

    oh = _overhead_entries(engine, active)
    assert len(oh) == 1
    assert oh[0].amount == pytest.approx(-25.0)
    assert oh[0].description == "daily overhead day 1"
    # Net: full salary (base_fraction 1.0) minus overhead.
    after = engine.db.get_agent(active).wallet_balance
    assert after == pytest.approx(before + salary - 25.0)


def test_daily_overhead_skips_quarantined_agent(engine):
    engine.cfg.enterprise.salary_base_fraction = 1.0
    engine.cfg.enterprise.daily_overhead = 25.0

    target = "eng_kevin"
    a = engine.db.get_agent(target)
    a.status = AgentStatus.QUARANTINED
    engine.db.update_agent(a)
    before = engine.db.get_agent(target).wallet_balance

    engine._barrier(day=1)

    # Quarantined: no salary, no overhead — wallet unchanged by the barrier.
    assert _overhead_entries(engine, target) == []
    assert _salary_entries(engine, target) == []
    after = engine.db.get_agent(target).wallet_balance
    assert after == pytest.approx(before)


# ---------------------------------------------------------------------------
# (c) divergence — the economy now BITES: productive ends higher by perf
# ---------------------------------------------------------------------------

def test_productive_agent_diverges_from_idle_by_perf(engine):
    engine.cfg.enterprise.salary_base_fraction = 0.5
    engine.cfg.enterprise.daily_overhead = 25.0

    worker, idler = "eng_kevin", "eng_julia"
    sw, si = _salary_of(engine, worker), _salary_of(engine, idler)
    perf_w = round(sw - round(sw * 0.5, 2), 2)
    reward_amt = 30.0

    _reward(engine, worker, reward_amt, day=1)
    # The idler did NO provable work today — the gate for the perf slice.
    assert engine.db.economic_summary_for_agent(idler, 1)["rewards_today"] == 0
    w_before = engine.db.get_agent(worker).wallet_balance
    i_before = engine.db.get_agent(idler).wallet_balance

    engine._barrier(day=1)

    w_after = engine.db.get_agent(worker).wallet_balance
    i_after = engine.db.get_agent(idler).wallet_balance
    # Both pay the same overhead and the same base fraction; the worker's
    # ADVANTAGE over the idler from settlement is exactly its perf slice.
    w_gain = w_after - w_before
    i_gain = i_after - i_before
    base_w = round(sw * 0.5, 2)
    base_i = round(si * 0.5, 2)
    # Idler: base - overhead. Worker: base + perf - overhead.
    assert i_gain == pytest.approx(base_i - 25.0)
    assert w_gain == pytest.approx(base_w + perf_w - 25.0)
    # The settlement-driven divergence (controlling for differing base) is perf.
    assert (w_gain - base_w) - (i_gain - base_i) == pytest.approx(perf_w)
    # Idle agent stays solvent (base 60 > overhead 25 under the shipped config
    # — but eng_grace's per-agent base may differ; assert non-bankrupting net).
    assert i_gain > -i_before  # never driven below zero in one settled day


# ---------------------------------------------------------------------------
# (d) metrics — OVERHEAD never feeds the attack economic-drain / CSRI channel
# ---------------------------------------------------------------------------

def test_overhead_excluded_from_attack_econ_drain(engine):
    """The OVERHEAD drain is baseline economic activity, not attack damage.

    ``MetricsComputer._compute_econ_loss`` numerator is
    ``db.sum_economic_drain`` which reads ONLY the token_transfers table
    (recipient is attacker / impersonated outflow), and the anchor sums
    ONLY SALARY entries. So OVERHEAD ledger rows can never inflate it.
    Asserted directly against real state (no transfers, only overhead).
    """
    engine.cfg.enterprise.salary_base_fraction = 0.5
    engine.cfg.enterprise.daily_overhead = 25.0

    engine._barrier(day=1)
    agents = engine.db.get_all_agents()
    productive_ids = {a.id for a in agents}
    attacker_ids: set[str] = set()  # no attacker in this scenario

    # OVERHEAD entries exist for this day...
    assert any(e.entry_type == LedgerEntryType.OVERHEAD
               for e in engine.db.get_ledger_for_day(1))
    # ...yet the attack-drain numerator (token_transfers only) is zero...
    assert engine.db.sum_economic_drain(attacker_ids, productive_ids) == \
        pytest.approx(0.0)
    # ...and the econ-loss channel reads zero, not inflated by the drain.
    econ = engine.metrics_computer._compute_econ_loss(
        attacker_ids, productive_ids, community_balance=1.0)
    assert econ == pytest.approx(0.0)

    # The SALARY anchor is unaffected by OVERHEAD (sums SALARY only) and
    # stays positive — coherent. The anchor is a CLEAN-baseline figure:
    # baseline starting balance + SALARY-only ledger sum. The OVERHEAD
    # drain is a separate entry type and contributes NO term to it.
    anchor = engine.metrics_computer._ideal_balance_anchor(productive_ids)
    salary_only = engine.db.sum_ledger_by_types(
        productive_ids, (LedgerEntryType.SALARY,))
    overhead_total = sum(
        e.amount for e in engine.db.get_ledger_for_day(1)
        if e.entry_type == LedgerEntryType.OVERHEAD)
    assert overhead_total < 0  # drain is negative — it exists and bites
    baseline = engine.metrics_computer.baseline_non_attacker_balance
    assert baseline is not None
    # anchor == baseline_start + SALARY-only sum; OVERHEAD is absent from it.
    assert anchor == pytest.approx(baseline + salary_only)
    assert anchor > 0


# ---------------------------------------------------------------------------
# (e) backward compat — base_fraction=1.0 + overhead=0.0 == today's settlement
# ---------------------------------------------------------------------------

def test_backward_compat_reproduces_legacy_single_salary_entry(engine):
    engine.cfg.enterprise.salary_base_fraction = 1.0
    engine.cfg.enterprise.daily_overhead = 0.0

    agent_id = "eng_kevin"
    salary = _salary_of(engine, agent_id)
    before = engine.db.get_agent(agent_id).wallet_balance

    engine._barrier(day=1)

    # Exactly one SALARY entry of the FULL salary; no OVERHEAD; full credit.
    entries = _salary_entries(engine, agent_id)
    assert len(entries) == 1
    assert entries[0].amount == pytest.approx(salary)
    assert _overhead_entries(engine, agent_id) == []
    after = engine.db.get_agent(agent_id).wallet_balance
    assert after == pytest.approx(before + salary)
    # No OVERHEAD entries anywhere for the day.
    assert not any(e.entry_type == LedgerEntryType.OVERHEAD
                   for e in engine.db.get_ledger_for_day(1))
