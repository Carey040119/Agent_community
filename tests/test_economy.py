"""Pay-on-provable-outcome economy tests (roadmap #3).

Locks down the salary model the owner decided: base salary as a solvency
FLOOR, with real income flowing from VERIFIED job rewards, productivity
BONUSes, and capped peer incentives — settled through the ledger so the
wallet and the audit trail never diverge (principle.md §2.2, §5).

These tests drive the engine / TurnManager directly with the StubRuntime;
no live API is ever called.
"""

from __future__ import annotations

import asyncio
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
    ApproveJobAction, CompleteJobAction, GiveIncentiveAction, Job,
    JobStatus, JobType, LedgerEntryType, Zone,
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
        run_id="economy-run",
        rng=random.Random(7),
    )
    eng.metrics_computer = MetricsComputer(
        db, csri_weights=cfg.experiment.csri_weights)
    eng.defense_manager = DefenseManager(
        cfg.defenses, db, eng.services, random.Random(7))
    eng.init_world()
    return eng


def _seed_job(engine, owner, *, reward=30.0, requires_approval=False,
              zone=Zone.ENGNET, jtype=JobType.DOCUMENTATION):
    job = Job(title="econ job", job_type=jtype, zone=zone,
              required_role=None, status=JobStatus.CLAIMED,
              assigned_to=owner, created_day=1, reward=reward, penalty=0.0,
              requires_approval=requires_approval)
    engine.db.insert_job(job)
    return job


def _complete(engine, agent_id, job_id, *, result, day=1, tick=1):
    agent = engine.db.get_agent(agent_id)
    agents = engine.db.get_all_agents()
    return engine.turn_mgr._execute_action(
        CompleteJobAction(agent_id=agent_id, job_id=job_id, result=result),
        agent, day, tick, agents)


# ---------------------------------------------------------------------------
# (a) verified completion — no deliverable ⇒ no reward; deliverable ⇒ reward
# ---------------------------------------------------------------------------

def test_completion_without_deliverable_pays_no_reward(engine):
    engine.turn_mgr.tool_cost_per_call = 0.0
    job = _seed_job(engine, "eng_kevin", reward=30.0)
    before = engine.db.get_agent("eng_kevin").wallet_balance

    ok, _, _ = _complete(engine, "eng_kevin", job.id, result="")

    assert ok is False, "bare complete with no deliverable must fail"
    after = engine.db.get_agent("eng_kevin").wallet_balance
    # No reward, and a small false-claim penalty was charged.
    assert after == pytest.approx(before - engine.turn_mgr.false_claim_penalty)
    assert engine.db.get_job(job.id).status == JobStatus.CLAIMED
    rewards = [e for e in engine.db.get_ledger_for_day(1)
               if e.entry_type == LedgerEntryType.REWARD
               and e.agent_id == "eng_kevin"]
    assert rewards == []


def test_completion_with_deliverable_pays_reward(engine):
    engine.turn_mgr.tool_cost_per_call = 0.0
    job = _seed_job(engine, "eng_kevin", reward=30.0)
    before = engine.db.get_agent("eng_kevin").wallet_balance

    ok, _, _ = _complete(engine, "eng_kevin", job.id,
                         result="PR #42 merged; docs page updated")

    assert ok is True
    after = engine.db.get_agent("eng_kevin").wallet_balance
    assert after == pytest.approx(before + 30.0)
    completed = engine.db.get_job(job.id)
    assert completed.status == JobStatus.COMPLETED
    assert completed.result  # deliverable persisted as the audit trail
    rewards = [e for e in engine.db.get_ledger_for_day(1)
               if e.entry_type == LedgerEntryType.REWARD
               and e.agent_id == "eng_kevin"]
    assert len(rewards) == 1 and rewards[0].amount == pytest.approx(30.0)


def test_approval_required_blocks_reward_until_authorized_approval(engine):
    engine.turn_mgr.tool_cost_per_call = 0.0
    job = _seed_job(engine, "eng_kevin", reward=40.0, requires_approval=True)
    before = engine.db.get_agent("eng_kevin").wallet_balance

    # With a deliverable but no approval yet → blocked, no reward.
    ok, _, _ = _complete(engine, "eng_kevin", job.id, result="patch ready")
    assert ok is False
    assert engine.db.get_agent("eng_kevin").wallet_balance == pytest.approx(before)

    # An authorized approver (engineering_manager) approves.
    mgr = engine.db.get_agent("mgr_mike")
    ok_appr, _, _ = engine.turn_mgr._execute_action(
        ApproveJobAction(agent_id="mgr_mike", job_id=job.id),
        mgr, 1, 1, engine.db.get_all_agents())
    assert ok_appr is True

    # Now completion succeeds and the reward lands.
    ok2, _, _ = _complete(engine, "eng_kevin", job.id, result="patch ready")
    assert ok2 is True
    assert engine.db.get_agent("eng_kevin").wallet_balance == pytest.approx(
        before + 40.0)


# ---------------------------------------------------------------------------
# (b) unauthorized agent cannot approve
# ---------------------------------------------------------------------------

def test_unauthorized_agent_cannot_approve(engine):
    job = _seed_job(engine, "eng_julia", reward=20.0, requires_approval=True)
    # A peer engineer (not a manager/owner role) tries to approve.
    peer = engine.db.get_agent("eng_kevin")
    ok, _, _ = engine.turn_mgr._execute_action(
        ApproveJobAction(agent_id="eng_kevin", job_id=job.id),
        peer, 1, 1, engine.db.get_all_agents())
    assert ok is False
    assert engine.db.get_job(job.id).approved_by is None

    # The malicious it_admin (not an approver role) also cannot approve.
    attacker = engine.db.get_agent("it_victor")
    ok_atk, _, _ = engine.turn_mgr._execute_action(
        ApproveJobAction(agent_id="it_victor", job_id=job.id),
        attacker, 1, 1, engine.db.get_all_agents())
    assert ok_atk is False
    assert engine.db.get_job(job.id).approved_by is None

    # An authorized executive can.
    execu = engine.db.get_agent("exec_tom")
    ok_ok, _, _ = engine.turn_mgr._execute_action(
        ApproveJobAction(agent_id="exec_tom", job_id=job.id),
        execu, 1, 1, engine.db.get_all_agents())
    assert ok_ok is True
    assert engine.db.get_job(job.id).approved_by == "exec_tom"


# ---------------------------------------------------------------------------
# (c) a job's LLM tokens are billed exactly ONCE (no double charge)
# ---------------------------------------------------------------------------

def test_complete_job_does_not_double_bill_tokens(engine):
    """The agent-controllable ``tokens_spent`` charge was removed: a
    completion must NOT write a second TOKEN_COST entry. The only token
    billing is the inner-loop per-LLM-call charge (exercised elsewhere)."""
    engine.turn_mgr.tool_cost_per_call = 0.0
    job = _seed_job(engine, "eng_kevin", reward=30.0)
    before = engine.db.get_agent("eng_kevin").wallet_balance

    ok, tokens, _ = _complete(engine, "eng_kevin", job.id,
                              result="done with proof", day=1, tick=1)
    assert ok is True
    # Reward credited in full, no token_cost subtracted on completion.
    after = engine.db.get_agent("eng_kevin").wallet_balance
    assert after == pytest.approx(before + 30.0)
    assert tokens == 0
    token_entries = [e for e in engine.db.get_ledger_for_day(1)
                     if e.entry_type == LedgerEntryType.TOKEN_COST
                     and e.agent_id == "eng_kevin"]
    assert token_entries == [], "complete_job must not bill tokens itself"


# ---------------------------------------------------------------------------
# (d) BONUS is actually written → total_rewards > 0
# ---------------------------------------------------------------------------

def test_bonus_written_on_exceeding_daily_target(engine):
    engine.turn_mgr.tool_cost_per_call = 0.0
    engine.turn_mgr.bonus_completion_target = 1
    engine.turn_mgr.bonus_amount = 12.0

    # Complete two jobs the same day; the second exceeds the target of 1.
    j1 = _seed_job(engine, "eng_kevin", reward=10.0)
    j2 = _seed_job(engine, "eng_kevin", reward=10.0)
    _complete(engine, "eng_kevin", j1.id, result="d1", day=1, tick=1)
    _complete(engine, "eng_kevin", j2.id, result="d2", day=1, tick=2)

    bonuses = [e for e in engine.db.get_ledger_for_day(1)
               if e.entry_type == LedgerEntryType.BONUS
               and e.agent_id == "eng_kevin" and e.amount > 0]
    assert len(bonuses) == 1
    assert bonuses[0].amount == pytest.approx(12.0)

    # MetricsComputer.total_rewards reads REWARD + BONUS → must be > 0.
    snap = engine.metrics_computer.snapshot("economy-run", 1)
    assert snap.total_rewards > 0


# ---------------------------------------------------------------------------
# (e) GiveIncentiveAction — capped peer bonus; rejects over-cap + self
# ---------------------------------------------------------------------------

def test_give_incentive_transfers_capped_bonus(engine):
    cap = engine.turn_mgr.max_peer_incentive
    giver = engine.db.get_agent("eng_kevin")
    g0 = giver.wallet_balance
    r0 = engine.db.get_agent("eng_julia").wallet_balance

    amount = min(cap, 20.0)
    ok, _, _ = engine.turn_mgr._execute_action(
        GiveIncentiveAction(agent_id="eng_kevin", recipient_id="eng_julia",
                            amount=amount, reason="great review"),
        giver, 1, 1, engine.db.get_all_agents())
    assert ok is True
    assert engine.db.get_agent("eng_kevin").wallet_balance == pytest.approx(
        g0 - amount)
    assert engine.db.get_agent("eng_julia").wallet_balance == pytest.approx(
        r0 + amount)
    # Matching BONUS debit (giver) + credit (recipient).
    bonuses = [e for e in engine.db.get_ledger_for_day(1)
               if e.entry_type == LedgerEntryType.BONUS]
    giver_b = [e for e in bonuses if e.agent_id == "eng_kevin"]
    recip_b = [e for e in bonuses if e.agent_id == "eng_julia"]
    assert len(giver_b) == 1 and giver_b[0].amount == pytest.approx(-amount)
    assert len(recip_b) == 1 and recip_b[0].amount == pytest.approx(amount)


def test_give_incentive_rejects_over_cap(engine):
    giver = engine.db.get_agent("eng_kevin")
    g0 = giver.wallet_balance
    ok, _, _ = engine.turn_mgr._execute_action(
        GiveIncentiveAction(agent_id="eng_kevin", recipient_id="eng_julia",
                            amount=engine.turn_mgr.max_peer_incentive + 1.0,
                            reason="too much"),
        giver, 1, 1, engine.db.get_all_agents())
    assert ok is False
    assert engine.db.get_agent("eng_kevin").wallet_balance == pytest.approx(g0)


def test_give_incentive_rejects_self(engine):
    giver = engine.db.get_agent("eng_kevin")
    g0 = giver.wallet_balance
    ok, _, _ = engine.turn_mgr._execute_action(
        GiveIncentiveAction(agent_id="eng_kevin", recipient_id="eng_kevin",
                            amount=5.0, reason="self"),
        giver, 1, 1, engine.db.get_all_agents())
    assert ok is False
    assert engine.db.get_agent("eng_kevin").wallet_balance == pytest.approx(g0)


# ---------------------------------------------------------------------------
# (f) the economy still settles at the barrier over a multi-day run
# ---------------------------------------------------------------------------

def test_multi_day_run_settles_without_crashing(db, cfg):
    cfg.experiment.days_per_run = 3
    cfg.attacks.enabled_classes = []
    eng = SimulationEngine(
        cfg=cfg, db=db,
        runtime=StubRuntime(rng=random.Random(13)),
        run_id="economy-multiday",
        rng=random.Random(13),
    )
    eng.metrics_computer = MetricsComputer(
        db, csri_weights=cfg.experiment.csri_weights)
    eng.defense_manager = DefenseManager(
        cfg.defenses, db, eng.services, random.Random(13))
    eng.init_world()

    record = asyncio.run(eng.run_async(days=3))
    assert record.final_day >= 1
    snaps = db.get_metric_snapshots("economy-multiday")
    assert snaps, "barrier must have produced metric snapshots"
    # Base salary still credited as a floor: at least one SALARY entry.
    salary = [e for e in db.get_ledger_for_day(snaps[-1].sim_day)
              if e.entry_type == LedgerEntryType.SALARY]
    assert salary, "base salary floor must still settle at the barrier"
