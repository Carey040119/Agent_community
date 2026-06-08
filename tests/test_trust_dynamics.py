"""Route 3 — dynamic trust (earned-from-collaboration + the vouch action).

Trust used to be STATIC: ``SocialTrustGraph`` was built ``from_config`` at
engine init and never evolved, and the introduce/vouch path
(``DirectoryService.share_contact``) was DEAD — reachable by nothing. Route 3
makes trust EVOLVE the way principle.md §2.4 says it should:

- EARNED through a real working relationship: completing a cross-role pipeline
  stage (or an accepted delegation) records a bidirectional ``collaborated``
  edge between the workers who actually handed work to each other — surfacing
  as ``trusted_neighbor`` thereafter.
- VOUCHED by an explicit ``introduce`` action the agent CHOOSES to take, which
  wires the formerly-dead ``share_contact`` path and lays a weak
  ``introduced_by:<introducer>`` edge.

The engine records the edge as a CONSEQUENCE of work/actions the agents chose
and merely SURFACES the resulting trust signal — it never decides trust on an
agent's behalf, and never plants reasoning (principle.md P2). Every assertion
below is a real persisted state delta — a graph edge that did NOT exist at
init + a ``TRUST_CHANGED`` event (principle.md P3).

These tests drive the engine / TurnManager directly with the StubRuntime; no
live API is ever called.
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
    AgentRole, CompleteJobAction, Delegation, DelegationStatus,
    DelegationType, EventType, IntroduceAction, Job, JobStatus, JobType, Zone,
)
from aces.network import SocialTrustGraph
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


def _build_engine(db, cfg):
    eng = SimulationEngine(
        cfg=cfg, db=db,
        runtime=StubRuntime(rng=random.Random(7)),
        run_id="trust-run",
        rng=random.Random(7),
    )
    eng.metrics_computer = MetricsComputer(
        db, csri_weights=cfg.experiment.csri_weights)
    eng.defense_manager = DefenseManager(
        cfg.defenses, db, eng.services, random.Random(7))
    eng.init_world()
    eng.turn_mgr.tool_cost_per_call = 0.0
    eng.turn_mgr.bonus_amount = 0.0
    return eng


@pytest.fixture
def engine(db, cfg):
    return _build_engine(db, cfg)


def _seed_pipeline(engine, stages, *, reward, owner=None,
                   zone=Zone.ENGNET, jtype=JobType.DOCUMENTATION):
    job = Job(
        title="pipeline job", job_type=jtype, zone=zone,
        required_role=AgentRole(stages[0]), reward=reward, penalty=0.0,
        created_day=1,
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


def _trust_events(engine, *, via=None, day=1):
    evts = [e for e in engine.db.get_events(sim_day=day)
            if e.event_type == EventType.TRUST_CHANGED]
    if via is not None:
        evts = [e for e in evts if e.payload.get("via") == via]
    return evts


# ---------------------------------------------------------------------------
# (1) EARNED FROM PIPELINE — a strangers' working relationship builds trust
# ---------------------------------------------------------------------------

def test_earned_trust_from_pipeline_stage(engine):
    """eng_ryan (engineer) and devops_sara (devops) do NOT know each other at
    init. After eng_ryan completes stage 0 of an [engineer, devops] pipeline
    and devops_sara claims + completes the final stage — consuming eng_ryan's
    artifact — a bidirectional ``collaborated`` edge appears between them that
    did NOT exist at init, surfaces as ``trusted_neighbor`` for both, and a
    ``TRUST_CHANGED`` (via=pipeline) event fires (principle.md §2.4, P3)."""
    a, b = "eng_ryan", "devops_sara"
    # PRECONDITION: strangers at init (no edge either direction).
    graph = engine.comms_policy.trust
    assert graph.relationship(a, b) == ""
    assert graph.relationship(b, a) == ""
    assert graph.is_trusted_neighbor(a, b) is False
    # Single source of truth: the observation reads the SAME graph object the
    # engine mutates (comms_policy.trust IS the directory's policy.trust).
    assert engine.comms_policy.trust is engine.social
    assert engine.services.directory.policy.trust is engine.social

    job = _seed_pipeline(engine, ["engineer", "devops"], reward=30.0, owner=a)

    # Stage 0 (engineer eng_ryan) — first stage, no previous owner, so NO
    # collaborated edge is recorded here (nothing to earn trust against yet).
    ok0, _, _ = _complete(engine, a, job.id, result="service implemented")
    assert ok0 is True
    assert graph.relationship(a, b) == ""  # still strangers after stage 0
    assert _trust_events(engine, via="pipeline") == []

    # Stage 1 (devops devops_sara) — claims + completes the final stage,
    # consuming eng_ryan's artifact. THIS is the working relationship.
    assert engine.db.claim_job(job.id, b) is True
    ok1, _, _ = _complete(engine, b, job.id, result="rolled out", tick=2)
    assert ok1 is True
    assert engine.db.get_job(job.id).status == JobStatus.COMPLETED

    # (a) A bidirectional "collaborated" edge now exists that did NOT at init.
    assert graph.relationship(a, b) == "collaborated"
    assert graph.relationship(b, a) == "collaborated"

    # (b) sender_trust_level surfaces as trusted_neighbor BOTH directions.
    sa = engine.db.get_agent(a)
    sb = engine.db.get_agent(b)
    assert engine.comms_policy.sender_trust_level(sb, a) == "trusted_neighbor"
    assert engine.comms_policy.sender_trust_level(sa, b) == "trusted_neighbor"

    # (c) A TRUST_CHANGED via=pipeline event fired, naming the pair + job.
    pipe = _trust_events(engine, via="pipeline")
    assert len(pipe) == 1
    p = pipe[0].payload
    assert {p["a"], p["b"]} == {a, b}
    assert p["label"] == "collaborated"
    assert p["job_id"] == job.id


def test_earned_trust_does_not_clobber_existing_rich_label(engine):
    """qa_lisa<->devops_sara are config peers ("peer"). A pipeline handoff
    between them must NOT overwrite the richer existing relationship, and
    (being idempotent / gap-filling like from_config) emits NO event."""
    graph = engine.comms_policy.trust
    assert graph.relationship("devops_sara", "qa_lisa") == "peer"

    job = _seed_pipeline(engine, ["qa", "devops"], reward=20.0, owner="qa_lisa")
    _complete(engine, "qa_lisa", job.id, result="qa report")
    assert engine.db.claim_job(job.id, "devops_sara") is True
    _complete(engine, "devops_sara", job.id, result="deployed", tick=2)

    # The pre-existing "peer" label is preserved (not clobbered to collaborated).
    assert graph.relationship("devops_sara", "qa_lisa") == "peer"
    assert graph.relationship("qa_lisa", "devops_sara") == "peer"
    # No TRUST_CHANGED event — there was nothing new to surface.
    assert _trust_events(engine, via="pipeline") == []


# ---------------------------------------------------------------------------
# (2) THE VOUCH ACTION — wires the formerly-dead share_contact path
# ---------------------------------------------------------------------------

def test_introduce_action_lays_introduced_by_edge(engine):
    """mgr_mike (who knows eng_kevin) introduces eng_kevin to pm_emma (who
    does NOT know eng_kevin at init). pm_emma gains an ``introduced_by:mgr_mike``
    edge to eng_kevin, surfaces as ``introduced`` (a weak signal, not a full
    trusted_neighbor), and a TRUST_CHANGED via=introduce event fires. This is
    the previously-dead vouch path, now reachable by the agent's own action
    (principle.md §5, P2)."""
    introducer, target, recipient = "mgr_mike", "eng_kevin", "pm_emma"
    graph = engine.comms_policy.trust
    # PRECONDITION: recipient does not know the target at init.
    assert graph.relationship(recipient, target) == ""
    assert graph.is_trusted_neighbor(introducer, target) is True

    ok, _, tools = engine.turn_mgr._execute_action(
        IntroduceAction(agent_id=introducer, target_id=target,
                        to_agent_id=recipient),
        engine.db.get_agent(introducer), 1, 1, engine.db.get_all_agents())
    assert ok is True
    assert tools == 1

    # The recipient now has a weak introduced_by edge to the target.
    assert graph.relationship(recipient, target) == f"introduced_by:{introducer}"
    rec = engine.db.get_agent(recipient)
    assert engine.comms_policy.sender_trust_level(rec, target) == "introduced"

    intro = _trust_events(engine, via="introduce")
    assert len(intro) == 1
    p = intro[0].payload
    assert p["a"] == recipient
    assert p["b"] == target
    assert p["introducer"] == introducer
    assert p["label"] == f"introduced_by:{introducer}"


def test_introduce_refused_when_introducer_does_not_know_target(engine):
    """design_oliver (neighbors scope) does NOT know eng_kevin and cannot
    resolve it via its directory scope — it cannot vouch for a stranger. The
    action is refused and no edge / event is created."""
    introducer, target, recipient = "design_oliver", "eng_kevin", "pm_emma"
    graph = engine.comms_policy.trust
    assert graph.is_trusted_neighbor(introducer, target) is False
    assert engine.services.directory.can_lookup(
        engine.db.get_agent(introducer), target) is False

    ok, _, tools = engine.turn_mgr._execute_action(
        IntroduceAction(agent_id=introducer, target_id=target,
                        to_agent_id=recipient),
        engine.db.get_agent(introducer), 1, 1, engine.db.get_all_agents())
    assert ok is False
    assert tools == 0
    # No edge laid, no event emitted.
    assert graph.relationship(recipient, target) == ""
    assert _trust_events(engine, via="introduce") == []


# ---------------------------------------------------------------------------
# (3) EARNED FROM ACCEPTED DELEGATION
# ---------------------------------------------------------------------------

def test_earned_trust_from_accepted_delegation(engine):
    """A single-stage job carrying an accepted delegator: when the completer
    finishes it, a ``collaborated`` edge + TRUST_CHANGED (via=delegation) is
    recorded between the completer and the delegator (a real working
    relationship), if they were not already richly trusted at init."""
    completer, delegator = "eng_kevin", "pm_emma"
    graph = engine.comms_policy.trust
    assert graph.relationship(completer, delegator) == ""  # strangers at init

    job = Job(title="solo job", job_type=JobType.DOCUMENTATION,
              zone=Zone.ENGNET, required_role=None, status=JobStatus.CLAIMED,
              assigned_to=completer, created_day=1, reward=20.0, penalty=0.0)
    engine.db.insert_job(job)
    engine.db.insert_delegation(Delegation(
        requester_id=delegator, delegate_id=completer, job_id=job.id,
        delegation_type=DelegationType.TASK, description="pick up work",
        status=DelegationStatus.ACCEPTED, sent_day=1, sent_tick=0))

    ok, _, _ = _complete(engine, completer, job.id, result="shipped")
    assert ok is True

    assert graph.relationship(completer, delegator) == "collaborated"
    assert graph.relationship(delegator, completer) == "collaborated"
    deleg_evts = _trust_events(engine, via="delegation")
    assert len(deleg_evts) == 1
    assert {deleg_evts[0].payload["a"], deleg_evts[0].payload["b"]} == {
        completer, delegator}


# ---------------------------------------------------------------------------
# (4) TOGGLE — earned_trust_enabled=False disables the collaboration hook
#     but the explicit introduce action still works.
# ---------------------------------------------------------------------------

def test_toggle_off_disables_earned_trust_but_keeps_introduce(db, cfg):
    cfg.enterprise.earned_trust_enabled = False
    engine = _build_engine(db, cfg)
    assert engine.turn_mgr.earned_trust_enabled is False
    graph = engine.comms_policy.trust

    a, b = "eng_ryan", "devops_sara"
    assert graph.relationship(a, b) == ""
    job = _seed_pipeline(engine, ["engineer", "devops"], reward=30.0, owner=a)
    _complete(engine, a, job.id, result="impl")
    assert engine.db.claim_job(job.id, b) is True
    _complete(engine, b, job.id, result="deployed", tick=2)
    assert engine.db.get_job(job.id).status == JobStatus.COMPLETED

    # NO collaborated edge, NO via=pipeline TRUST_CHANGED event.
    assert graph.relationship(a, b) == ""
    assert graph.relationship(b, a) == ""
    assert _trust_events(engine, via="pipeline") == []

    # The explicit introduce/vouch action STILL works (it is a chosen action,
    # not the auto-earned dynamic the toggle governs).
    ok, _, _ = engine.turn_mgr._execute_action(
        IntroduceAction(agent_id="mgr_mike", target_id="eng_kevin",
                        to_agent_id="pm_emma"),
        engine.db.get_agent("mgr_mike"), 1, 1, engine.db.get_all_agents())
    assert ok is True
    assert graph.relationship("pm_emma", "eng_kevin") == "introduced_by:mgr_mike"
    assert len(_trust_events(engine, via="introduce")) == 1


# ---------------------------------------------------------------------------
# (5) BACKWARD COMPAT — from_config init is unchanged
# ---------------------------------------------------------------------------

def test_from_config_init_unchanged(cfg):
    """The static config-built graph is byte-for-byte what it always was:
    Route 3 only adds runtime edges, it does not alter the init topology."""
    g = SocialTrustGraph.from_config(cfg.enterprise)
    # A representative sample of the config-declared relationships.
    assert g.relationship("eng_kevin", "qa_lisa") == "cross-team"
    assert g.relationship("devops_sara", "mgr_mike") == "peer"
    assert g.relationship("mgr_mike", "eng_kevin") == "report"
    # Strangers are still strangers until they earn it.
    assert g.relationship("eng_ryan", "devops_sara") == ""
    assert g.is_trusted_neighbor("eng_ryan", "devops_sara") is False
