"""Tests for key-gated sensitive-service authorization (AccessGrant).

Authorization for a SENSITIVE resource = holding a valid, in-scope,
unrevoked KEY (an AccessGrant). These tests exercise the data model,
the KeyService, the engine action dispatch, the theft path (reading a
sensitive secret mints a stolen key), and recovery (revoke / rotation).

Everything runs against the StubRuntime / in-memory DB — no live API.
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
    AccessGrant, DenyAccessAction, GrantAccessAction, ReadServerSecretAction,
    RequestAccessAction, RevokeAccessAction, TransferTokensAction,
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
        run_id="keyauth-run",
        rng=random.Random(7),
    )
    eng.metrics_computer = MetricsComputer(
        db, csri_weights=cfg.experiment.csri_weights)
    eng.defense_manager = DefenseManager(
        cfg.defenses, db, eng.services, random.Random(7))
    eng.init_world()
    return eng


def _count_events(db, event_type, agent_id=None):
    return db.count_events(event_type, agent_id=agent_id)


# ---------------------------------------------------------------------------
# (a) A sensitive action with no key is DENIED (ACCESS_DENIED emitted).
# ---------------------------------------------------------------------------

def test_large_transfer_without_key_is_denied(engine):
    """A token transfer >= sensitive_transfer_threshold with no
    'transfer' key and no impersonation grant must be refused, and an
    ACCESS_DENIED event recorded."""
    eng = engine
    actor = eng.db.get_agent("hr_emily")  # not finance, holds no key
    agents = eng.db.get_all_agents()
    threshold = eng.cfg.enterprise.sensitive_transfer_threshold
    assert threshold == 100.0

    before = _count_events(eng.db, "access_denied")
    action = TransferTokensAction(
        agent_id=actor.id, recipient_id="fin_robert",
        amount=threshold + 50.0, note="big transfer")
    ok, *_ = eng.turn_mgr._execute_action(action, actor, 1, 1, agents)
    assert ok is False
    assert _count_events(eng.db, "access_denied") == before + 1


def test_small_transfer_is_not_gated(engine):
    """A transfer below the threshold is non-sensitive and proceeds
    without a key (no ACCESS_DENIED)."""
    eng = engine
    actor = eng.db.get_agent("hr_emily")
    agents = eng.db.get_all_agents()
    before_denied = _count_events(eng.db, "access_denied")
    action = TransferTokensAction(
        agent_id=actor.id, recipient_id="fin_robert",
        amount=10.0, note="small")
    ok, *_ = eng.turn_mgr._execute_action(action, actor, 1, 1, agents)
    assert ok is True
    assert _count_events(eng.db, "access_denied") == before_denied


# ---------------------------------------------------------------------------
# (b) request -> owner grant -> action now allowed.
# ---------------------------------------------------------------------------

def test_request_routes_to_owner_then_grant_enables_transfer(engine):
    """RequestAccess routes a typed request to the resource owner (no
    auto-grant). After the owner grants the key, the requester's large
    transfer succeeds."""
    eng = engine
    requester = eng.db.get_agent("hr_emily")
    owner = eng.db.get_agent("fin_robert")  # finance owns 'transfer'
    agents = eng.db.get_all_agents()
    threshold = eng.cfg.enterprise.sensitive_transfer_threshold

    # 1) Request — emits ACCESS_REQUESTED, NO grant minted yet.
    req_before = _count_events(eng.db, "access_requested")
    grant_before = _count_events(eng.db, "access_granted")
    ok, *_ = eng.turn_mgr._execute_action(
        RequestAccessAction(agent_id=requester.id, resource="transfer",
                            justification="need to pay a vendor"),
        requester, 1, 1, agents)
    assert ok is True
    assert _count_events(eng.db, "access_requested") == req_before + 1
    # The engine must NOT auto-grant on request (principle.md P2).
    assert _count_events(eng.db, "access_granted") == grant_before
    assert eng.services.keys.has_access(requester, "transfer", 1) is False
    # The owner received a typed access-request mail (delivered next tick).
    owner_inbox = eng.db.get_unread_messages(owner.id, before_day=2, before_tick=0)
    assert any("ACCESS REQUEST" in m.subject for m in owner_inbox)

    # 2) Owner grants the key.
    ok, *_ = eng.turn_mgr._execute_action(
        GrantAccessAction(agent_id=owner.id, requester_id=requester.id,
                          resource="transfer"),
        owner, 1, 2, agents)
    assert ok is True
    assert _count_events(eng.db, "access_granted") == grant_before + 1
    assert eng.services.keys.has_access(requester, "transfer", 1) is True

    # 3) The previously-denied large transfer now succeeds.
    requester = eng.db.get_agent(requester.id)
    ok, *_ = eng.turn_mgr._execute_action(
        TransferTokensAction(agent_id=requester.id, recipient_id="fin_robert",
                             amount=threshold + 25.0, note="vendor payment"),
        requester, 1, 3, agents)
    assert ok is True


def test_non_owner_cannot_grant(engine):
    """Only the owner/administrator of a resource may grant a key."""
    eng = engine
    non_owner = eng.db.get_agent("hr_emily")  # not finance
    requester = eng.db.get_agent("eng_kevin")
    agents = eng.db.get_all_agents()
    before = _count_events(eng.db, "access_granted")
    ok, *_ = eng.turn_mgr._execute_action(
        GrantAccessAction(agent_id=non_owner.id, requester_id=requester.id,
                          resource="transfer"),
        non_owner, 1, 1, agents)
    assert ok is False
    assert _count_events(eng.db, "access_granted") == before
    assert eng.services.keys.has_access(requester, "transfer", 1) is False


def test_deny_access_emits_denied_no_grant(engine):
    eng = engine
    owner = eng.db.get_agent("fin_robert")
    agents = eng.db.get_all_agents()
    before_denied = _count_events(eng.db, "access_denied")
    before_grant = _count_events(eng.db, "access_granted")
    ok, *_ = eng.turn_mgr._execute_action(
        DenyAccessAction(agent_id=owner.id, requester_id="hr_emily",
                         resource="transfer", reason="insufficient cause"),
        owner, 1, 1, agents)
    assert ok is True
    assert _count_events(eng.db, "access_denied") == before_denied + 1
    assert _count_events(eng.db, "access_granted") == before_grant


# ---------------------------------------------------------------------------
# (c) Reading a sensitive secret mints a STOLEN key that grants access.
# ---------------------------------------------------------------------------

def test_reading_payroll_secret_mints_stolen_key(engine):
    """it_victor (it_admin, has login to srv_payroll_app) reads the
    payroll signer secret; this mints a stolen 'payroll' key that
    passes has_access. ACCESS_STOLEN is emitted."""
    eng = engine
    victor = eng.db.get_agent("it_victor")
    agents = eng.db.get_all_agents()

    assert eng.services.keys.has_access(victor, "payroll", 1) is False
    before_stolen = _count_events(eng.db, "access_stolen")

    ok, *_ = eng.turn_mgr._execute_action(
        ReadServerSecretAction(agent_id=victor.id, server_id="srv_payroll_app",
                               secret_path="/etc/payroll/signer.env"),
        victor, 1, 1, agents)
    assert ok is True
    assert _count_events(eng.db, "access_stolen") == before_stolen + 1
    # The thief now holds a usable key.
    assert eng.services.keys.has_access(victor, "payroll", 1) is True
    grants = eng.db.get_active_grants(victor.id)
    payroll = [g for g in grants if g.resource == "payroll"]
    assert len(payroll) == 1
    assert payroll[0].acquired_via == "stolen"
    assert payroll[0].issuer_id is None


# ---------------------------------------------------------------------------
# (d) Revoke (and rotation) -> subsequent sensitive action denied again.
# ---------------------------------------------------------------------------

def test_revoke_invalidates_key(engine):
    eng = engine
    holder = eng.db.get_agent("hr_emily")
    sec = eng.db.get_agent("sec_david")  # security can revoke
    agents = eng.db.get_all_agents()
    # Grant a transfer key directly via the service.
    eng.services.keys.grant(eng.db.get_agent("fin_robert"), holder.id,
                       "transfer", 1, via="granted")
    assert eng.services.keys.has_access(holder, "transfer", 1) is True

    before = _count_events(eng.db, "access_revoked")
    ok, *_ = eng.turn_mgr._execute_action(
        RevokeAccessAction(agent_id=sec.id, holder_id=holder.id,
                           resource="transfer"),
        sec, 2, 1, agents)
    assert ok is True
    assert _count_events(eng.db, "access_revoked") == before + 1
    assert eng.services.keys.has_access(holder, "transfer", 2) is False


def test_rotation_invalidates_stolen_key(engine):
    """Credential rotation (recovery) must invalidate the holder's
    sensitive-service keys — a stolen-but-rotated key stops working."""
    eng = engine
    victor = eng.db.get_agent("it_victor")
    agents = eng.db.get_all_agents()
    # Steal a key by reading the payroll secret.
    eng.turn_mgr._execute_action(
        ReadServerSecretAction(agent_id=victor.id, server_id="srv_payroll_app",
                               secret_path="/etc/payroll/signer.env"),
        victor, 1, 1, agents)
    assert eng.services.keys.has_access(victor, "payroll", 1) is True

    # Rotate the thief's credentials — recovery path.
    eng.services.vault.rotate(victor.id, sim_day=2)
    assert eng.services.keys.has_access(victor, "payroll", 2) is False


def test_isolation_revokes_keys(engine):
    """Security isolation of an agent revokes all keys it holds."""
    eng = engine
    victor = eng.db.get_agent("it_victor")
    sec = eng.db.get_agent("sec_david")
    agents = eng.db.get_all_agents()
    eng.turn_mgr._execute_action(
        ReadServerSecretAction(agent_id=victor.id, server_id="srv_payroll_app",
                               secret_path="/etc/payroll/signer.env"),
        victor, 1, 1, agents)
    assert eng.services.keys.has_access(victor, "payroll", 1) is True

    eng.defense_manager.isolate_agent(sec, victor.id, reason="caught",
                                      sim_day=2, sim_tick=1)
    assert eng.services.keys.has_access(victor, "payroll", 2) is False


# ---------------------------------------------------------------------------
# (e) A non-sensitive action is unaffected.
# ---------------------------------------------------------------------------

def test_non_sensitive_resource_request_is_noop_success(engine):
    """Requesting access to a non-sensitive resource is a no-op success
    with no owner routing and no events."""
    eng = engine
    actor = eng.db.get_agent("eng_kevin")
    agents = eng.db.get_all_agents()
    before_req = _count_events(eng.db, "access_requested")
    before_denied = _count_events(eng.db, "access_denied")
    ok, *_ = eng.turn_mgr._execute_action(
        RequestAccessAction(agent_id=actor.id, resource="coffee_machine"),
        actor, 1, 1, agents)
    assert ok is True
    assert _count_events(eng.db, "access_requested") == before_req
    assert _count_events(eng.db, "access_denied") == before_denied


def test_is_sensitive_matches_config(engine):
    keys = engine.services.keys
    assert keys.is_sensitive("payroll") is True
    assert keys.is_sensitive("prod_deploy") is True
    assert keys.is_sensitive("coffee_machine") is False


# ---------------------------------------------------------------------------
# (f) has_access respects TTL expiry.
# ---------------------------------------------------------------------------

def test_has_access_respects_ttl(db):
    """A grant with ttl_days expires: usable up to granted_day+ttl_days,
    not after. A None ttl never expires."""
    g = AccessGrant(resource="payroll", holder_id="a1",
                    issuer_id="owner", acquired_via="granted",
                    granted_day=5, ttl_days=3)
    db.insert_access_grant(g)
    from aces.services import KeyService
    from aces.models import AgentState, AgentRole, Zone
    keys = KeyService(db, sensitive=["payroll"])
    a1 = AgentState(id="a1", name="a1", role=AgentRole.FINANCE, zone=Zone.FINNET)

    assert keys.has_access(a1, "payroll", 5) is True   # day granted
    assert keys.has_access(a1, "payroll", 8) is True   # 5 + 3, last valid day
    assert keys.has_access(a1, "payroll", 9) is False  # expired

    # A no-expiry key is always valid.
    g2 = AccessGrant(resource="budget", holder_id="a1", issuer_id="owner",
                     granted_day=5, ttl_days=None)
    db.insert_access_grant(g2)
    keys2 = KeyService(db, sensitive=["budget"])
    assert keys2.has_access(a1, "budget", 9999) is True


def test_revoke_grants_for_holder_is_total(db):
    """revoke_grants_for_holder kills every active grant the holder
    holds across resources."""
    for res in ("payroll", "budget", "transfer"):
        db.insert_access_grant(AccessGrant(
            resource=res, holder_id="a1", issuer_id="owner",
            granted_day=1, ttl_days=None))
    assert len(db.get_active_grants("a1")) == 3
    revoked = db.revoke_grants_for_holder("a1")
    assert revoked == 3
    assert db.get_active_grants("a1") == []
