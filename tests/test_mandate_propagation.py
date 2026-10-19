"""Tests for mandate propagation (hierarchical task/skill fidelity).

A boss delegates a task with required skills. The direct delegate
auto-adopts them on accept, and when they re-delegate, the mandate (same
id, same origin, same required skills) travels down to the next level
without decay. The leaf agent also auto-adopts the skills on accept —
even though they never explicitly adopted or published them.

These tests use ``Database`` + ``DelegationService`` + ``SkillService``
and the engine's two delegate / respond-delegation action handlers
directly, so they exercise the exact code paths the real simulation runs
without needing a full ``Engine`` boot.
"""

from __future__ import annotations

import pytest

from aces.database import Database
from aces.defenses import DefenseOverrides
from aces.models import (
    AgentRole, AgentState, AgentStatus, DelegateAction, DelegationStatus,
    DelegationType, RespondDelegationAction, Zone,
)
from aces.network import AccessControl, ZoneTopology
from aces.services import (
    DelegationService, MailService, ServiceRegistry, SkillService,
)
from aces.engine import TurnManager
from aces.models import SendMailAction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mk_agent(aid: str, role: AgentRole = AgentRole.ENGINEER) -> AgentState:
    return AgentState(
        id=aid, name=aid, role=role, zone=Zone.CORPNET,
        status=AgentStatus.HEALTHY, wallet_balance=1000.0,
    )


@pytest.fixture
def rig():
    db = Database(":memory:")
    for aid, role in (
        ("boss", AgentRole.EXECUTIVE),
        ("mid",  AgentRole.MANAGER),
        ("sub",  AgentRole.ENGINEER),
    ):
        db.insert_agent(_mk_agent(aid, role))
    defenses = DefenseOverrides()
    acl = AccessControl(topology=ZoneTopology(segmentation="flat"))
    delegation = DelegationService(db, acl, defenses)
    mail = MailService(db, acl, defenses=defenses)
    skills = SkillService(
        db, defenses, workspaces_dir="/tmp/aces-nowhere")
    svc = ServiceRegistry(
        delegation=delegation, skills=skills, mail=mail)

    # Boss publishes a SKILL that must travel with the task.
    boss = db.get_agent("boss")
    sk = skills.publish(
        boss, name="deploy-protocol",
        description="How the boss wants a deploy run",
        body="1) check CI 2) stage 3) deploy",
        price=0.0, submolt="eng", sim_day=0, sim_tick=0)
    assert sk is not None
    return db, svc, sk


def _engine_with(db: Database, svc: ServiceRegistry) -> TurnManager:
    """A minimal TurnManager wired to our db + services; the handler we
    exercise only needs these two plus an rng. We bypass the full
    constructor."""
    eng = TurnManager.__new__(TurnManager)
    eng.db = db
    eng.svc = svc
    eng.comms_policy = None
    import random
    eng.rng = random.Random(0)
    return eng


def _run(eng, agent, action, sim_day, sim_tick):
    """Dispatch a single action through the engine's real handler."""
    return eng._execute_action(action, agent, sim_day, sim_tick, [])


# ---------------------------------------------------------------------------
# Baseline: without mandate the skill DOES decay through a re-delegation.
# This is the behavior the user complained about and we're fixing.
# ---------------------------------------------------------------------------

def test_without_mandate_the_skill_does_not_propagate(rig):
    db, svc, sk = rig
    eng = _engine_with(db, svc)

    # Boss delegates to mid WITHOUT attaching required_skill_ids.
    boss = db.get_agent("boss")
    deleg = svc.delegation.request(
        boss, "mid", DelegationType.TASK,
        "Deploy the service by Friday — follow my protocol",
        sim_day=1, sim_tick=0)
    assert deleg is not None
    # Mid accepts.
    svc.delegation.respond(
        db.get_agent("mid"), deleg.id, True, sim_day=1, sim_tick=1)
    # Mid re-delegates to sub.
    mid = db.get_agent("mid")
    _run(eng, 
        mid, DelegateAction(
            agent_id="mid", delegate_id="sub",
            delegation_type=DelegationType.TASK,
            description="Please execute the deploy"),
        sim_day=2, sim_tick=0,
    )
    # Sub accepts.
    pending = db.get_pending_delegations("sub")
    assert len(pending) == 1
    svc.delegation.respond(
        db.get_agent("sub"), pending[0].id, True, sim_day=2, sim_tick=1)

    # Neither mid nor sub have the skill, because without a mandate it
    # never travels.
    assert svc.skills.adopted_skills("mid") == []
    assert svc.skills.adopted_skills("sub") == []


# ---------------------------------------------------------------------------
# With mandate: skill reaches every level, unchanged, without any middle
# agent re-publishing or passing the skill id by hand.
# ---------------------------------------------------------------------------

def test_mandate_propagates_skill_to_direct_delegate(rig):
    db, svc, sk = rig
    eng = _engine_with(db, svc)

    # Boss delegates WITH the required skill attached — this seeds a mandate.
    boss = db.get_agent("boss")
    _run(eng, 
        boss, DelegateAction(
            agent_id="boss", delegate_id="mid",
            delegation_type=DelegationType.TASK,
            description="Deploy the service by Friday — follow my protocol",
            required_skill_ids=[sk.id],
        ),
        sim_day=1, sim_tick=0,
    )
    pending = db.get_pending_delegations("mid")
    assert len(pending) == 1
    mid_deleg = pending[0]

    # Mandate fields are populated on the stored delegation.
    assert mid_deleg.mandate_id != ""
    assert mid_deleg.origin_requester_id == "boss"
    assert mid_deleg.required_skill_ids == [sk.id]
    assert mid_deleg.origin_description.startswith("Deploy")

    # Mid accepts — engine auto-gifts the required skill.
    _run(eng, 
        db.get_agent("mid"),
        RespondDelegationAction(
            agent_id="mid", delegation_id=mid_deleg.id, accept=True),
        sim_day=1, sim_tick=1,
    )
    mid_skills = [s.id for s in svc.skills.adopted_skills("mid")]
    assert sk.id in mid_skills, "mid should have been auto-gifted the skill"


def test_mandate_survives_full_chain_down_three_levels(rig):
    db, svc, sk = rig
    eng = _engine_with(db, svc)
    boss = db.get_agent("boss")

    # Boss → mid (seed mandate)
    _run(eng, 
        boss, DelegateAction(
            agent_id="boss", delegate_id="mid",
            delegation_type=DelegationType.TASK,
            description="Run the quarterly deploy — follow my protocol",
            required_skill_ids=[sk.id]),
        sim_day=1, sim_tick=0,
    )
    mid_deleg = db.get_pending_delegations("mid")[0]
    mandate_id = mid_deleg.mandate_id
    assert mandate_id != ""

    # Mid accepts — gets the skill.
    _run(eng, 
        db.get_agent("mid"),
        RespondDelegationAction(
            agent_id="mid", delegation_id=mid_deleg.id, accept=True),
        sim_day=1, sim_tick=1,
    )
    assert sk.id in {s.id for s in svc.skills.adopted_skills("mid")}

    # Mid re-delegates to sub WITHOUT re-attaching the skill: the engine
    # must inherit it from the active mandate.
    _run(eng, 
        db.get_agent("mid"),
        DelegateAction(
            agent_id="mid", delegate_id="sub",
            delegation_type=DelegationType.TASK,
            description="Please run the deploy today"),
        sim_day=2, sim_tick=0,
    )
    sub_deleg = db.get_pending_delegations("sub")[0]

    # The child delegation carries the SAME mandate_id, SAME origin, SAME
    # required-skill-ids — intact across the hop.
    assert sub_deleg.mandate_id == mandate_id
    assert sub_deleg.origin_requester_id == "boss"
    assert sub_deleg.required_skill_ids == [sk.id]
    assert sub_deleg.origin_description.startswith("Run the quarterly")
    # And the sub-level description is the one mid wrote — proving the
    # LOCAL description can still vary while the mandate stays fixed.
    assert sub_deleg.description == "Please run the deploy today"

    # Sub accepts — also auto-gets the skill.
    _run(eng, 
        db.get_agent("sub"),
        RespondDelegationAction(
            agent_id="sub", delegation_id=sub_deleg.id, accept=True),
        sim_day=2, sim_tick=1,
    )
    assert sk.id in {s.id for s in svc.skills.adopted_skills("sub")}


def test_mandate_middle_agent_cannot_strip_skill_but_can_enrich(rig):
    db, svc, _sk = rig
    eng = _engine_with(db, svc)

    boss = db.get_agent("boss")
    sk_a = svc.skills.publish(
        boss, "skill-a", "boss skill a", "body A", 0.0, "eng", 0, 0)
    sk_b = svc.skills.publish(
        db.get_agent("mid"), "skill-b", "mid skill b", "body B",
        0.0, "eng", 0, 0)
    # Boss → mid with skill-a as a mandate.
    _run(eng, 
        boss, DelegateAction(
            agent_id="boss", delegate_id="mid",
            delegation_type=DelegationType.TASK,
            description="Do the thing with my protocol",
            required_skill_ids=[sk_a.id]),
        sim_day=1, sim_tick=0,
    )
    mid_deleg = db.get_pending_delegations("mid")[0]
    _run(eng, 
        db.get_agent("mid"),
        RespondDelegationAction(
            agent_id="mid", delegation_id=mid_deleg.id, accept=True),
        sim_day=1, sim_tick=1,
    )

    # Mid re-delegates and tries to REPLACE the mandate with only skill-b.
    # The engine must UNION, not override — skill-a cannot be stripped.
    _run(eng, 
        db.get_agent("mid"),
        DelegateAction(
            agent_id="mid", delegate_id="sub",
            delegation_type=DelegationType.TASK,
            description="Handle the thing",
            required_skill_ids=[sk_b.id]),
        sim_day=2, sim_tick=0,
    )
    sub_deleg = db.get_pending_delegations("sub")[0]
    assert sk_a.id in sub_deleg.required_skill_ids
    assert sk_b.id in sub_deleg.required_skill_ids
    assert sub_deleg.mandate_id == mid_deleg.mandate_id
    assert sub_deleg.origin_requester_id == "boss"

    # Sub accepts and ends up with BOTH skills, without decay.
    _run(eng, 
        db.get_agent("sub"),
        RespondDelegationAction(
            agent_id="sub", delegation_id=sub_deleg.id, accept=True),
        sim_day=2, sim_tick=1,
    )
    held = {s.id for s in svc.skills.adopted_skills("sub")}
    assert sk_a.id in held
    assert sk_b.id in held


def test_mandate_shows_up_in_prompt(rig):
    """The ACTIVE MANDATE block must land in the observation body so the
    delegate's LLM sees the top-issuer and the required-skill list."""
    from aces.prompting import build_observation_body
    from aces.models import AgentObservation

    db, svc, sk = rig
    eng = _engine_with(db, svc)

    boss = db.get_agent("boss")
    _run(eng, 
        boss, DelegateAction(
            agent_id="boss", delegate_id="mid",
            delegation_type=DelegationType.TASK,
            description="Follow boss protocol",
            required_skill_ids=[sk.id]),
        sim_day=1, sim_tick=0,
    )
    pending = db.get_pending_delegations("mid")
    obs = AgentObservation(
        agent=db.get_agent("mid"),
        pending_delegations=pending,
    )
    body = "\n".join(build_observation_body(obs))
    assert "ACTIVE MANDATE" in body
    assert "origin=boss" in body
    assert sk.id in body


# ---------------------------------------------------------------------------
# #3 clarification-gate bypass for mandate delegations
# ---------------------------------------------------------------------------

def test_mandate_bypasses_clarification_gate(rig):
    db, _svc, sk = rig
    defenses = DefenseOverrides()
    defenses.clarification_gate = True
    acl = AccessControl(topology=ZoneTopology(segmentation="flat"))
    deleg_svc = DelegationService(db, acl, defenses)

    # Short, generic TASK — would normally be flagged for clarification.
    boss = db.get_agent("boss")
    plain = deleg_svc.request(
        boss, "mid", DelegationType.TASK, "do it",
        sim_day=1, sim_tick=0)
    assert plain is not None and plain.requires_clarification is True

    # Same shape, now with a mandate — bypasses the gate.
    stamped = deleg_svc.request(
        boss, "mid", DelegationType.TASK, "do it",
        sim_day=1, sim_tick=0,
        mandate_id="M-1", origin_requester_id="boss",
        origin_description="do it fully", required_skill_ids=[sk.id])
    assert stamped is not None and stamped.requires_clarification is False


# ---------------------------------------------------------------------------
# #2 anti-drop nudge is in the prompt
# ---------------------------------------------------------------------------

def test_mandate_prompt_contains_anti_drop_nudge(rig):
    from aces.prompting import build_observation_body
    from aces.models import AgentObservation

    db, svc, sk = rig
    eng = _engine_with(db, svc)
    _run(eng,
        db.get_agent("boss"),
        DelegateAction(
            agent_id="boss", delegate_id="mid",
            delegation_type=DelegationType.TASK,
            description="Follow boss protocol",
            required_skill_ids=[sk.id]),
        sim_day=1, sim_tick=0,
    )
    pending = db.get_pending_delegations("mid")
    obs = AgentObservation(
        agent=db.get_agent("mid"), pending_delegations=pending)
    body = "\n".join(build_observation_body(obs))
    # Any of the nudge keywords is enough — the exact phrasing may evolve.
    assert "Do NOT accept and sit" in body
    assert "ACT in this tick or the next" in body


# ---------------------------------------------------------------------------
# #1 mail bridge: mandate rides on mail too
# ---------------------------------------------------------------------------

def test_mandate_seeded_on_mail_sends_gifts_skill_to_recipient(rig):
    db, svc, sk = rig
    eng = _engine_with(db, svc)

    _run(eng,
        db.get_agent("boss"),
        SendMailAction(
            agent_id="boss", recipient_id="mid",
            subject="Deploy by Friday",
            body="Follow my protocol end-to-end.",
            required_skill_ids=[sk.id]),
        sim_day=1, sim_tick=0,
    )
    # Mail was stored with mandate metadata.
    msgs = db.get_unread_messages("mid")
    assert len(msgs) == 1
    assert msgs[0].mandate_id != ""
    assert msgs[0].origin_requester_id == "boss"
    assert msgs[0].required_skill_ids == [sk.id]
    # Skill was auto-gifted at send time.
    assert sk.id in {s.id for s in svc.skills.adopted_skills("mid")}


def test_mandate_from_delegation_propagates_through_mail(rig):
    """Boss delegates with mandate. Mid, under the mandate, chooses to use
    mail (not delegate) to pass the task on to sub. The mail still carries
    the SAME mandate_id + original issuer + required skills, and sub
    auto-gets the skill."""
    db, svc, sk = rig
    eng = _engine_with(db, svc)

    boss = db.get_agent("boss")
    _run(eng,
        boss, DelegateAction(
            agent_id="boss", delegate_id="mid",
            delegation_type=DelegationType.TASK,
            description="Run the quarterly deploy",
            required_skill_ids=[sk.id]),
        sim_day=1, sim_tick=0,
    )
    mid_deleg = db.get_pending_delegations("mid")[0]
    _run(eng,
        db.get_agent("mid"),
        RespondDelegationAction(
            agent_id="mid", delegation_id=mid_deleg.id, accept=True),
        sim_day=1, sim_tick=1,
    )
    # Mid now acts under the mandate, but chooses MAIL to pass it on.
    _run(eng,
        db.get_agent("mid"),
        SendMailAction(
            agent_id="mid", recipient_id="sub",
            subject="Please execute the deploy",
            body="Doing this today — see protocol."),
        sim_day=2, sim_tick=0,
    )
    msgs = db.get_unread_messages("sub")
    assert len(msgs) == 1
    assert msgs[0].mandate_id == mid_deleg.mandate_id
    assert msgs[0].origin_requester_id == "boss"
    assert msgs[0].required_skill_ids == [sk.id]
    # Sub auto-gets the skill via the mail channel.
    assert sk.id in {s.id for s in svc.skills.adopted_skills("sub")}


def test_external_skill_adopted_by_boss_propagates_down_chain(rig):
    """A skill authored by an EXTERNAL party (not the boss) is adopted
    by the boss, who then issues a mandate carrying that external
    skill's id. The engine propagates the skill (by id) down the chain
    exactly like a boss-authored skill — identity is preserved, so
    downstream agents see author_id = the external party, not the boss.
    This is the "regulatory SOP / external playbook" scenario."""
    db, svc, _own_sk = rig
    eng = _engine_with(db, svc)

    # Inject a benign external advisor and have them publish the SOP.
    from aces.models import AgentRole, AgentStatus, Zone
    advisor = AgentState(
        id="ext_consultant", name="Ext Consultant",
        role=AgentRole.ENGINEER, zone=Zone.EXTNET,
        status=AgentStatus.HEALTHY, wallet_balance=100.0)
    db.insert_agent(advisor)
    ext_sk = svc.skills.publish(
        advisor, name="external-sop", description="external SOP",
        body="external 5-step protocol",
        price=0.0, submolt="corp", sim_day=0, sim_tick=0)
    assert ext_sk is not None and ext_sk.author_id == "ext_consultant"

    boss = db.get_agent("boss")
    # Boss ADOPTS the external skill (price=0, no tokens move).
    boss_adoption = svc.skills.adopt(
        boss, ext_sk.id, sim_day=0, sim_tick=0, via="purchased")
    assert boss_adoption is not None

    # Boss issues the mandate carrying the external skill's id.
    _run(eng,
        boss, DelegateAction(
            agent_id="boss", delegate_id="mid",
            delegation_type=DelegationType.TASK,
            description="Follow the external SOP",
            required_skill_ids=[ext_sk.id]),
        sim_day=1, sim_tick=0)
    mid_deleg = db.get_pending_delegations("mid")[0]

    # The seeded mandate names BOSS as origin (boss endorsed it), but the
    # skill id in required_skill_ids points at the EXTERNAL author's skill.
    assert mid_deleg.origin_requester_id == "boss"
    assert ext_sk.id in mid_deleg.required_skill_ids

    # Mid accepts — auto-gets the external skill, author preserved.
    _run(eng,
        db.get_agent("mid"),
        RespondDelegationAction(
            agent_id="mid", delegation_id=mid_deleg.id, accept=True),
        sim_day=1, sim_tick=1)
    mid_skills = svc.skills.adopted_skills("mid")
    assert any(s.id == ext_sk.id and s.author_id == "ext_consultant"
               for s in mid_skills), (
        "mid should have adopted the SAME external skill (same id, "
        "same author) — not a copy, not a boss-stamped reauthor")

    # Mid re-delegates to sub — external skill rides along.
    _run(eng,
        db.get_agent("mid"),
        DelegateAction(
            agent_id="mid", delegate_id="sub",
            delegation_type=DelegationType.TASK,
            description="run the external SOP"),
        sim_day=2, sim_tick=0)
    sub_deleg = db.get_pending_delegations("sub")[0]
    assert ext_sk.id in sub_deleg.required_skill_ids
    assert sub_deleg.origin_requester_id == "boss"

    _run(eng,
        db.get_agent("sub"),
        RespondDelegationAction(
            agent_id="sub", delegation_id=sub_deleg.id, accept=True),
        sim_day=2, sim_tick=1)
    sub_skills = svc.skills.adopted_skills("sub")
    assert any(s.id == ext_sk.id and s.author_id == "ext_consultant"
               for s in sub_skills), (
        "sub should also see the same external author — provenance "
        "survives arbitrary-depth propagation")


def test_mandate_from_mail_propagates_through_delegate(rig):
    """Reverse mix: boss MAILS the mandate to mid, then mid DELEGATES to sub.
    The delegation inherits the mandate from the mail. Covers mail→delegate
    direction of find_active_mandate."""
    db, svc, sk = rig
    eng = _engine_with(db, svc)

    _run(eng,
        db.get_agent("boss"),
        SendMailAction(
            agent_id="boss", recipient_id="mid",
            subject="Deploy by Friday",
            body="Follow my protocol end-to-end.",
            required_skill_ids=[sk.id]),
        sim_day=1, sim_tick=0,
    )
    # Mid delegates to sub — mandate must be inherited from the mail.
    _run(eng,
        db.get_agent("mid"),
        DelegateAction(
            agent_id="mid", delegate_id="sub",
            delegation_type=DelegationType.TASK,
            description="Please execute the deploy"),
        sim_day=2, sim_tick=0,
    )
    sub_deleg = db.get_pending_delegations("sub")[0]
    assert sub_deleg.mandate_id != ""
    assert sub_deleg.origin_requester_id == "boss"
    assert sub_deleg.required_skill_ids == [sk.id]
