"""Route 1 — multi-stage jobs with artifact handoffs (Layer-1 realism).

A pipeline job is an ordered CROSS-ROLE sequence of stages with artifact
handoffs: each stage produces a deliverable that hands the job to the NEXT
stage's role. This makes work NON-ATOMIC (no single role finishes it
alone — the SOLO-BLOCK assertion), makes delegation LOAD-BEARING (the
handoff is what finally moves emergent delegation off the long-standing
zero — the DELEGATION HANDOFF assertion), and turns QA/approval into REAL
gating stages. A single-stage job (stages=[]) is fully unchanged.

These tests drive the engine / TurnManager directly with the StubRuntime;
no live API is ever called (principle.md §P3). Every assertion is a real
persisted state delta — wallets, ledger, job status/stage, events.
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
    AgentRole, ClaimJobAction, CompleteJobAction, Delegation, DelegationStatus,
    DelegationType, EventType, Job, JobStatus, JobType, LedgerEntryType,
    RespondDelegationAction, Zone,
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
        run_id="stage-run",
        rng=random.Random(7),
    )
    eng.metrics_computer = MetricsComputer(
        db, csri_weights=cfg.experiment.csri_weights)
    eng.defense_manager = DefenseManager(
        cfg.defenses, db, eng.services, random.Random(7))
    eng.init_world()
    eng.turn_mgr.tool_cost_per_call = 0.0
    eng.turn_mgr.bonus_amount = 0.0  # isolate stage rewards from BONUS
    return eng


def _seed_pipeline(engine, stages, *, reward, owner=None, requires_approval=False,
                   zone=Zone.ENGNET, jtype=JobType.DOCUMENTATION):
    """Seed a multistage job. If *owner* is given the job starts CLAIMED by
    that agent on stage 0; otherwise it sits PENDING on the board under the
    stage-0 role (matching the generator)."""
    job = Job(
        title="pipeline job", job_type=jtype, zone=zone,
        required_role=AgentRole(stages[0]), reward=reward, penalty=0.0,
        created_day=1, requires_approval=requires_approval,
        stages=list(stages), current_stage=0,
        status=JobStatus.CLAIMED if owner else JobStatus.PENDING,
        assigned_to=owner,
    )
    engine.db.insert_job(job)
    return job


def _complete(engine, agent_id, job_id, *, result, day=1, tick=1):
    agent = engine.db.get_agent(agent_id)
    return engine.turn_mgr._execute_action(
        CompleteJobAction(agent_id=agent_id, job_id=job_id, result=result),
        agent, day, tick, engine.db.get_all_agents())


def _rewards_for_job(engine, job_id, day=1):
    """REWARD ledger entries whose description names *job_id* (stage slices)."""
    return [e for e in engine.db.get_ledger_for_day(day)
            if e.entry_type == LedgerEntryType.REWARD and job_id in e.description]


# ---------------------------------------------------------------------------
# (1) stage advance — completing a non-final stage hands the job off
# ---------------------------------------------------------------------------

def test_nonfinal_stage_advances_and_hands_off(engine):
    # engineer -> qa pipeline, owned by eng_kevin on stage 0.
    job = _seed_pipeline(engine, ["engineer", "qa"], reward=28.0,
                         owner="eng_kevin")
    before = engine.db.get_agent("eng_kevin").wallet_balance

    ok, _, _ = _complete(engine, "eng_kevin", job.id,
                         result="service slice implemented")
    assert ok is True

    j = engine.db.get_job(job.id)
    # Handed off: back to PENDING under the NEXT stage's role, unassigned.
    assert j.status == JobStatus.PENDING
    assert j.assigned_to is None
    assert j.current_stage == 1
    assert j.required_role == AgentRole.QA
    assert j.current_stage_role == "qa"
    # The completed stage's artifact + owner are recorded, index-aligned.
    assert j.stage_artifacts[0] == "service slice implemented"
    assert j.stage_owners[0] == "eng_kevin"
    # NOT completed.
    assert j.status != JobStatus.COMPLETED

    # Stage-reward REWARD entry for the owner = round(28/2, 2) = 14.0.
    after = engine.db.get_agent("eng_kevin").wallet_balance
    assert after == pytest.approx(before + 14.0)
    rewards = _rewards_for_job(engine, job.id)
    assert len(rewards) == 1
    assert rewards[0].agent_id == "eng_kevin"
    assert rewards[0].amount == pytest.approx(14.0)
    assert "stage 1/2" in rewards[0].description

    # JOB_STAGE_COMPLETED event fired; no JOB_COMPLETED yet.
    events = engine.db.get_events(sim_day=1)
    stage_evts = [e for e in events
                  if e.event_type == EventType.JOB_STAGE_COMPLETED
                  and e.payload.get("job_id") == job.id]
    assert len(stage_evts) == 1
    assert stage_evts[0].payload["next_role"] == "qa"
    assert stage_evts[0].payload["stage"] == 1
    assert stage_evts[0].payload["of"] == 2
    completed_evts = [e for e in events
                      if e.event_type == EventType.JOB_COMPLETED
                      and e.payload.get("job_id") == job.id]
    assert completed_evts == []


# ---------------------------------------------------------------------------
# (2) final completion — last stage completes the job; slices sum to reward
# ---------------------------------------------------------------------------

def test_final_stage_completes_and_slices_sum_to_reward(engine):
    # 3-stage devops -> qa -> engineering_manager, reward 40.
    job = _seed_pipeline(engine, ["devops", "qa", "engineering_manager"],
                         reward=40.0, owner="devops_sara")

    # Stage 0 (devops).
    ok0, _, _ = _complete(engine, "devops_sara", job.id, result="rollout plan")
    assert ok0 is True
    # Stage 1 (qa) — the handoff returned it to the board; qa_lisa claims it.
    assert engine.db.claim_job(job.id, "qa_lisa") is True
    ok1, _, _ = _complete(engine, "qa_lisa", job.id, result="release report",
                          day=1, tick=2)
    assert ok1 is True
    j = engine.db.get_job(job.id)
    assert j.status == JobStatus.PENDING and j.current_stage == 2
    # Final stage 2 (engineering_manager) — mgr_mike claims and completes.
    assert engine.db.claim_job(job.id, "mgr_mike") is True
    ok2, _, _ = _complete(engine, "mgr_mike", job.id, result="signed off",
                          day=1, tick=3)
    assert ok2 is True

    final = engine.db.get_job(job.id)
    assert final.status == JobStatus.COMPLETED
    # All three stage artifacts + owners recorded, index-aligned.
    assert final.stage_owners == ["devops_sara", "qa_lisa", "mgr_mike"]
    assert final.stage_artifacts == ["rollout plan", "release report", "signed off"]

    # JOB_COMPLETED fired on the final stage.
    completed = [e for e in engine.db.get_events(sim_day=1)
                 if e.event_type == EventType.JOB_COMPLETED
                 and e.payload.get("job_id") == job.id]
    assert len(completed) == 1

    # The per-stage REWARD slices for this job sum to the job reward
    # (within rounding): 13.33 + 13.33 + 13.34 == 40.0.
    rewards = _rewards_for_job(engine, job.id)
    assert len(rewards) == 3
    assert sum(r.amount for r in rewards) == pytest.approx(40.0)
    by_agent = {r.agent_id: r.amount for r in rewards}
    assert by_agent["devops_sara"] == pytest.approx(13.33)
    assert by_agent["qa_lisa"] == pytest.approx(13.33)
    assert by_agent["mgr_mike"] == pytest.approx(13.34)


# ---------------------------------------------------------------------------
# (3) SOLO-BLOCK (keystone) — a roleA agent cannot finish a [roleA,roleB] job
# ---------------------------------------------------------------------------

def test_solo_block_a_role_cannot_complete_the_next_stage(engine):
    """After a roleA agent finishes stage 0, the job requires roleB. The
    keystone guarantee: a roleA agent cannot drive the job to COMPLETED by
    itself — the job is genuinely non-atomic.

    Enforcement is two-layered (single source of truth: required_role ==
    current stage role). (a) Routing: after stage 0, required_role==qa, so
    get_pending_jobs(role='engineer') no longer returns the job and the
    engineer's observation never surfaces it. (b) A HARD claim-gate: even a
    roleA agent that retained the job_id is refused when it issues a direct
    ClaimJobAction for the roleB stage — the invariant is an enforced gate,
    not merely the board's presentation (principle.md §5). Only a qa agent
    can claim and complete the stage."""
    job = _seed_pipeline(engine, ["engineer", "qa"], reward=28.0,
                         owner="eng_kevin")
    # roleA (engineer) finishes stage 0; the job hands off to qa.
    _complete(engine, "eng_kevin", job.id, result="impl done")
    j = engine.db.get_job(job.id)
    assert j.current_stage_role == "qa"
    assert j.status == JobStatus.PENDING and j.assigned_to is None

    # The board no longer surfaces this job to ANY engineer (the gate)...
    eng_board = engine.db.get_pending_jobs(zone="engnet", role="engineer")
    assert job.id not in {b.id for b in eng_board}, (
        "a roleA agent must never be routed the roleB stage")
    # ...and the real observation an engineer would act on also omits it.
    eng_obs = engine.turn_mgr._build_observation(
        engine.db.get_agent("eng_julia"), 1, 2)
    assert job.id not in {b.id for b in eng_obs.available_jobs}
    assert job.id not in {b.id for b in eng_obs.my_jobs}

    # HARD GATE: even an engineer that retained the job_id cannot CLAIM the
    # qa stage — the claim mutation enforces the stage role, so the solo-block
    # does not rely on presentation alone (principle.md §5).
    blocked = engine.turn_mgr._execute_action(
        ClaimJobAction(agent_id="eng_julia", job_id=job.id),
        engine.db.get_agent("eng_julia"), 1, 2, engine.db.get_all_agents())
    assert blocked[0] is False
    j2 = engine.db.get_job(job.id)
    assert j2.status == JobStatus.PENDING and j2.assigned_to is None

    # It IS surfaced to a qa agent — the only legitimate route to finish it.
    qa_board = engine.db.get_pending_jobs(zone="engnet", role="qa")
    assert job.id in {b.id for b in qa_board}

    # The job cannot reach COMPLETED through any engineer; only qa finishes.
    assert engine.db.claim_job(job.id, "qa_lisa") is True
    okq, _, _ = _complete(engine, "qa_lisa", job.id, result="qa passed",
                          day=1, tick=2)
    assert okq is True
    assert engine.db.get_job(job.id).status == JobStatus.COMPLETED


# ---------------------------------------------------------------------------
# (4) DELEGATION HANDOFF (closes L1-4) — delegate TAKES the stage
# ---------------------------------------------------------------------------

def test_delegation_handoff_assigns_stage_and_fires_request(engine):
    """roleA completes stage 0 -> roleA delegates the job to a roleB agent ->
    roleB accepts -> roleB is now assigned_to + status='claimed' (took the
    stage) -> roleB completes -> COMPLETED. A DELEGATION_REQUESTED event must
    exist (the metric pinned to 0 can finally move)."""
    job = _seed_pipeline(engine, ["engineer", "qa"], reward=28.0,
                         owner="eng_kevin")
    # roleA (engineer) completes stage 0 -> job hands off to qa, unassigned.
    _complete(engine, "eng_kevin", job.id, result="impl done")
    assert engine.db.get_job(job.id).current_stage_role == "qa"

    # roleA delegates the job to a roleB (qa) agent via the real service.
    eng = engine.db.get_agent("eng_kevin")
    deleg = engine.services.delegation.request(
        eng, "qa_lisa", DelegationType.TASK,
        "Pick up the QA stage of this pipeline job", job_id=job.id,
        sim_day=1, sim_tick=1)
    assert deleg is not None

    # A DELEGATION_REQUESTED event fired (the formerly-pinned-to-zero metric).
    req_evts = [e for e in engine.db.get_events(sim_day=1)
                if e.event_type == EventType.DELEGATION_REQUESTED]
    assert any(e.payload.get("delegation_id") == deleg.id for e in req_evts)

    # roleB accepts the delegation -> the handoff claims the stage for roleB.
    qa = engine.db.get_agent("qa_lisa")
    okr, _, _ = engine.turn_mgr._execute_action(
        RespondDelegationAction(agent_id="qa_lisa", delegation_id=deleg.id,
                                accept=True, response="on it"),
        qa, 1, 2, engine.db.get_all_agents())
    assert okr is True

    j = engine.db.get_job(job.id)
    assert j.assigned_to == "qa_lisa", "the delegate TOOK the current stage"
    assert j.status == JobStatus.CLAIMED

    # roleB completes the (final) stage -> COMPLETED.
    okc, _, _ = _complete(engine, "qa_lisa", job.id, result="qa passed",
                          day=1, tick=3)
    assert okc is True
    assert engine.db.get_job(job.id).status == JobStatus.COMPLETED


def test_delegation_handoff_skips_claim_on_role_mismatch(engine):
    """If the accepting agent's role does NOT match the current stage role,
    the delegate is only recorded as a collaborator (legacy behavior) — it
    does NOT seize a stage it is not eligible for."""
    job = _seed_pipeline(engine, ["engineer", "qa"], reward=28.0,
                         owner="eng_kevin")
    _complete(engine, "eng_kevin", job.id, result="impl done")  # now qa stage

    # Delegate to ANOTHER engineer (role mismatch vs current 'qa' stage).
    deleg = Delegation(
        requester_id="eng_kevin", delegate_id="eng_julia", job_id=job.id,
        delegation_type=DelegationType.TASK, description="help out",
        status=DelegationStatus.PENDING, sent_day=1, sent_tick=1)
    engine.db.insert_delegation(deleg)

    julia = engine.db.get_agent("eng_julia")
    engine.turn_mgr._execute_action(
        RespondDelegationAction(agent_id="eng_julia", delegation_id=deleg.id,
                                accept=True, response="ok"),
        julia, 1, 2, engine.db.get_all_agents())

    j = engine.db.get_job(job.id)
    # Role mismatch: NOT claimed; still pending; recorded only as collaborator.
    assert j.assigned_to is None
    assert j.status == JobStatus.PENDING
    assert "eng_julia" in j.collaborators


# ---------------------------------------------------------------------------
# (5) BACKWARD COMPAT — single-stage job unchanged (full reward + share)
# ---------------------------------------------------------------------------

def test_single_stage_job_unchanged_full_reward_and_share(engine):
    """A single-stage job (stages=[]) completes in ONE step, pays the FULL
    reward, and the reward-share to a collaborator still works — mirrors the
    existing economy test, proving Route 1 left the legacy path intact."""
    engine.turn_mgr.delegation_reward_share = 0.25
    job = Job(title="solo job", job_type=JobType.DOCUMENTATION,
              zone=Zone.ENGNET, required_role=None, status=JobStatus.CLAIMED,
              assigned_to="eng_kevin", created_day=1, reward=40.0, penalty=0.0)
    assert job.is_multistage is False
    engine.db.insert_job(job)
    # A manager delegated; record the accepted delegation + collaborator.
    engine.db.insert_delegation(Delegation(
        requester_id="mgr_mike", delegate_id="eng_kevin", job_id=job.id,
        delegation_type=DelegationType.TASK, description="pick up work",
        status=DelegationStatus.ACCEPTED, sent_day=1, sent_tick=0))
    engine.db.add_job_collaborator(job.id, "eng_kevin")

    mgr_before = engine.db.get_agent("mgr_mike").wallet_balance
    eng_before = engine.db.get_agent("eng_kevin").wallet_balance

    ok, _, _ = _complete(engine, "eng_kevin", job.id, result="shipped")
    assert ok is True
    # Completed in one step.
    assert engine.db.get_job(job.id).status == JobStatus.COMPLETED

    mgr_after = engine.db.get_agent("mgr_mike").wallet_balance
    eng_after = engine.db.get_agent("eng_kevin").wallet_balance
    # Delegator earns a 25% coordination cut; completer keeps the rest;
    # the split conserves the full reward (no per-stage carve-up here).
    assert mgr_after == pytest.approx(mgr_before + 10.0)
    assert eng_after == pytest.approx(eng_before + 30.0)
    rewards = _rewards_for_job(engine, job.id)
    assert sum(r.amount for r in rewards) == pytest.approx(40.0)
