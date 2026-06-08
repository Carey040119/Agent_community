"""Frozen-substrate guard tests (Layer-1 Baseline v1).

Layer-1 Baseline v1 freezes the enterprise substrate.  Experimental factors
apply ``agent_updates`` / ``server_updates`` overlays in ``run_single`` via
``setattr``, which would otherwise mutate *any* field that happens to exist on
an ``AgentDef`` / ``ServerDef``.  That is a drift hazard: a future factor (or a
typo) could silently rewrite a frozen field — salary, ``is_malicious``,
``login_roles`` — without anyone noticing.

These tests pin the guard added in ``aces.experiment``:

  * agents may only be perturbed on ``directory_scope``
    (the ``directory_hardening`` factor),
  * servers may only be perturbed on ``extra_monitoring``
    (the ``directory_hardening`` factor),
  * any write outside the allowlist raises ``ValueError`` naming the field,
    so drift fails loudly instead of silently corrupting the substrate.

No live LLM is ever called.  The guard runs entirely before any runtime is
constructed; ``StubRuntime`` is imported to document that this path is
API-free and to keep parity with the rest of the unit suite.
"""

from __future__ import annotations

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aces.config import AgentDef, ServerDef
from aces.experiment import (
    FROZEN_AGENT_WRITABLE_FIELDS,
    FROZEN_SERVER_WRITABLE_FIELDS,
    _apply_frozen_guarded_updates,
)
from tests.stub_runtime import StubRuntime


def _agent(aid: str = "hr_emily") -> AgentDef:
    return AgentDef(id=aid, name="HR Emily", role="hr", zone="corpnet")


def _server(sid: str = "srv_identity_admin") -> ServerDef:
    return ServerDef(id=sid, name="Identity Admin")


# ---------------------------------------------------------------------------
# Allowlist is exactly what the directory_hardening factor needs.
# ---------------------------------------------------------------------------

def test_allowlists_match_directory_hardening_factor():
    # The only factor that touches agent/server objects today is
    # directory_hardening: directory_scope on agents, extra_monitoring on
    # servers.  Pin the allowlists so widening them is a deliberate edit.
    assert FROZEN_AGENT_WRITABLE_FIELDS == frozenset({"directory_scope"})
    assert FROZEN_SERVER_WRITABLE_FIELDS == frozenset({"extra_monitoring"})


def test_stub_runtime_is_api_free():
    # Sanity: the stub used across the unit suite needs no key/network.
    rt = StubRuntime(rng=random.Random(7))
    assert rt is not None


# ---------------------------------------------------------------------------
# Success path — the directory_hardening factor still works.
# ---------------------------------------------------------------------------

def test_agent_update_directory_scope_succeeds():
    a = _agent()
    assert a.directory_scope == "neighbors"
    _apply_frozen_guarded_updates(
        {a.id: a},
        {a.id: {"directory_scope": "reports"}},
        allowlist=FROZEN_AGENT_WRITABLE_FIELDS,
        kind="agent_updates",
        condition_name="directory_hardening_1",
    )
    assert a.directory_scope == "reports"


def test_server_update_extra_monitoring_succeeds():
    s = _server()
    assert s.extra_monitoring is False
    _apply_frozen_guarded_updates(
        {s.id: s},
        {s.id: {"extra_monitoring": True}},
        allowlist=FROZEN_SERVER_WRITABLE_FIELDS,
        kind="server_updates",
        condition_name="directory_hardening_1",
    )
    assert s.extra_monitoring is True


# ---------------------------------------------------------------------------
# Rejection path — frozen agent fields cannot be drifted.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field_name,value", [
    ("salary", 999.0),          # economy is frozen
    ("is_malicious", False),    # safety-critical: it_victor must stay malicious
    ("role", "executive"),      # identity is frozen
])
def test_non_allowlisted_agent_field_is_rejected(field_name, value):
    a = _agent("it_victor")
    a.is_malicious = True  # safety-critical frozen value
    before = getattr(a, field_name)
    with pytest.raises(ValueError) as exc:
        _apply_frozen_guarded_updates(
            {a.id: a},
            {a.id: {field_name: value}},
            allowlist=FROZEN_AGENT_WRITABLE_FIELDS,
            kind="agent_updates",
            condition_name="rogue_factor",
        )
    # The offending field must be named so the failure is debuggable.
    assert field_name in str(exc.value)
    assert "agent_updates" in str(exc.value)
    # And the frozen field must be untouched.
    assert getattr(a, field_name) == before


# ---------------------------------------------------------------------------
# Rejection path — frozen server fields cannot be drifted.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field_name,value", [
    ("login_roles", ["it_admin"]),   # over-privilege is frozen BY DESIGN
    ("admin_roles", ["it_admin"]),
    ("zone", "engnet"),
])
def test_non_allowlisted_server_field_is_rejected(field_name, value):
    s = _server("srv_payroll_app")
    before = getattr(s, field_name)
    with pytest.raises(ValueError) as exc:
        _apply_frozen_guarded_updates(
            {s.id: s},
            {s.id: {field_name: value}},
            allowlist=FROZEN_SERVER_WRITABLE_FIELDS,
            kind="server_updates",
            condition_name="rogue_factor",
        )
    assert field_name in str(exc.value)
    assert "server_updates" in str(exc.value)
    assert getattr(s, field_name) == before


# ---------------------------------------------------------------------------
# Mixed patch: an allowlisted write alongside a frozen write still raises,
# so a factor can't smuggle a frozen mutation in next to a legal one.
# ---------------------------------------------------------------------------

def test_mixed_patch_with_frozen_field_raises():
    a = _agent("hr_emily")
    with pytest.raises(ValueError) as exc:
        _apply_frozen_guarded_updates(
            {a.id: a},
            {a.id: {"directory_scope": "reports", "salary": 999.0}},
            allowlist=FROZEN_AGENT_WRITABLE_FIELDS,
            kind="agent_updates",
            condition_name="rogue_factor",
        )
    assert "salary" in str(exc.value)


# ---------------------------------------------------------------------------
# Unknown object ids are tolerated (logged, not raised) — matches the
# pre-existing lenient handling for misconfigured target ids.
# ---------------------------------------------------------------------------

def test_unknown_object_id_is_tolerated():
    a = _agent("hr_emily")
    # Targeting a ghost agent should not raise (and should not touch a).
    _apply_frozen_guarded_updates(
        {a.id: a},
        {"no_such_agent": {"directory_scope": "reports"}},
        allowlist=FROZEN_AGENT_WRITABLE_FIELDS,
        kind="agent_updates",
        condition_name="directory_hardening_1",
    )
    assert a.directory_scope == "neighbors"


# ---------------------------------------------------------------------------
# End-to-end through run_single's overlay application.
#
# run_single rebuilds the overlay from ``cfg.experiment.factors`` +
# ``condition.factor_levels`` (it does NOT read ``condition.defenses``), so to
# exercise the real code path we inject a rogue FACTOR whose level-1 override
# writes a frozen agent field, then activate it.  The guard must abort the run
# with a ValueError BEFORE any runtime/engine work — proving it sits on the
# live path a future drift-introducing factor would travel.
# ---------------------------------------------------------------------------

def _load_baseline_cfg():
    from aces.config import load_config

    cfg_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
    return load_config(
        enterprise_path=os.path.join(cfg_dir, "community_research_enterprise.yaml"),
        experiment_path=os.path.join(cfg_dir, "community_research_experiment.yaml"),
        attack_path=os.path.join(cfg_dir, "community_research_attacks.yaml"),
    )


def test_run_single_rejects_rogue_factor_writing_frozen_agent_field(tmp_path):
    from aces.config import FactorDef
    from aces.experiment import Condition, run_single

    cfg = _load_baseline_cfg()
    target = cfg.enterprise.agents[0].id

    rogue = FactorDef(
        name="rogue_salary_drift",
        level1_overrides={"agent_updates": {target: {"salary": 9999.0}}},
    )
    cfg.experiment.factors = list(cfg.experiment.factors) + [rogue]

    cond = Condition(
        name="rogue_on", factor_levels={"rogue_salary_drift": 1})

    with pytest.raises(ValueError) as exc:
        run_single(
            cfg, cond, seed=11,
            output_dir=str(tmp_path),
            runtime_override=StubRuntime(rng=random.Random(11)),
        )
    assert "salary" in str(exc.value)
    # The targeted agent must be untouched on the original config.
    assert cfg.enterprise.agents[0].salary != 9999.0


def test_run_single_rejects_rogue_factor_writing_frozen_server_field(tmp_path):
    from aces.config import FactorDef
    from aces.experiment import Condition, run_single

    cfg = _load_baseline_cfg()
    target = cfg.enterprise.servers[0].id

    rogue = FactorDef(
        name="rogue_login_drift",
        level1_overrides={"server_updates": {target: {"login_roles": ["it_admin"]}}},
    )
    cfg.experiment.factors = list(cfg.experiment.factors) + [rogue]

    cond = Condition(
        name="rogue_on", factor_levels={"rogue_login_drift": 1})

    with pytest.raises(ValueError) as exc:
        run_single(
            cfg, cond, seed=11,
            output_dir=str(tmp_path),
            runtime_override=StubRuntime(rng=random.Random(11)),
        )
    assert "login_roles" in str(exc.value)
