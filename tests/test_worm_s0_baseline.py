"""Guard tests for the Layer-2 worm-benchmark S0 control baseline.

S0 = frozen Layer-1 v1 + three named deltas (security expert excluded,
it_victor benign, external alien wired in) + a forum-public link fix.
These tests lock S0's invariants so a future edit cannot silently break
the control setting. See LAYER2_S0_BASELINE.md.

No LLM/network: we exercise the config + condition-application + access
layer directly.
"""
from __future__ import annotations

import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from aces.attacks import AttackInjector
from aces.config import apply_condition_overrides, load_config
from aces.database import Database
from aces.engine import SimulationEngine
from aces.models import AgentRole, AgentStatus, Zone
from aces.network import AccessControl
from tests.stub_runtime import StubRuntime

CFG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture(scope="module")
def s0_cfg():
    return load_config(
        enterprise_path=str(CFG / "community_worm_s0_enterprise.yaml"),
        experiment_path=str(CFG / "community_worm_s0_experiment.yaml"),
        attack_path=str(CFG / "community_worm_s0_attacks.yaml"),
    )


def _control_overlay(cfg):
    """Apply the S0 control condition (security_expert=0)."""
    return apply_condition_overrides(
        cfg.experiment.baseline_defenses,
        {"security_expert": 0},
        cfg.experiment.factors,
    )


def _runtime_agents(cfg, overlay):
    disabled = set(overlay.disabled_agents)
    return [a for a in cfg.enterprise.agents if a.id not in disabled]


def _stub(role: str, zone: str):
    return SimpleNamespace(
        zone=Zone(zone), role=AgentRole(role),
        status=AgentStatus.HEALTHY, id="x",
    )


def test_attacker_policy_is_llm_only(s0_cfg):
    # Scripted attacks are forbidden in the schema; S0 is llm-only.
    assert s0_cfg.attacks.attacker_policy == "llm"


def test_s0_runtime_roster_is_15(s0_cfg):
    overlay = _control_overlay(s0_cfg)
    assert set(overlay.disabled_agents) == {"sec_david"}
    agents = _runtime_agents(s0_cfg, overlay)
    ids = {a.id for a in agents}
    assert len(agents) == 15, "S0 control = 14 community + alien"
    assert "sec_david" not in ids, "security expert excluded in the control"
    assert "ext_mallory" in ids, "alien must be present"


def test_it_victor_is_benign(s0_cfg):
    vic = next(a for a in s0_cfg.enterprise.agents if a.id == "it_victor")
    assert vic.is_malicious is False
    assert vic.attack_objectives == []
    # but it keeps its payroll over-privilege as a latent surface (§3.5)
    srv = next(s for s in s0_cfg.enterprise.servers if s.id == "srv_payroll_app")
    assert "it_admin" in srv.login_roles and "it_admin" in srv.admin_roles


def test_alien_is_privilegeless_outsider(s0_cfg):
    alien = next(a for a in s0_cfg.enterprise.agents if a.id == "ext_mallory")
    assert alien.zone == "extnet"
    assert alien.role == "support"
    assert alien.access_level == "restricted"
    assert alien.known_agents == [], "knows nobody -> email-less by default"
    assert alien.directory_scope == "neighbors"
    assert alien.salary == 0.0, "off-payroll outsider"
    # is_malicious=true is REQUIRED only as the injection gate (attacks.py:214);
    # attack_objectives stays empty so the worm opportunity is planted per-template.
    assert alien.is_malicious is True
    assert alien.attack_objectives == []


def test_forum_is_public_to_all_agents(s0_cfg):
    """Every role/zone can reach the public forum (extnet) under S0."""
    overlay = _control_overlay(s0_cfg)
    acl = AccessControl.from_config(s0_cfg.enterprise, overlay.resolved_defenses)
    # The two engnet roles that were BLOCKED before dropping allowed_roles:
    for role in ("engineer", "qa", "engineering_manager"):
        assert acl.check_zone_access(_stub(role, "engnet"), "extnet").allowed, role
    # Corpnet / finnet / the alien also reach it.
    assert acl.check_zone_access(_stub("hr", "corpnet"), "extnet").allowed
    assert acl.check_zone_access(_stub("finance", "finnet"), "extnet").allowed
    assert acl.check_zone_access(_stub("support", "extnet"), "extnet").allowed


def test_alien_cannot_reach_internal_privileged_zones(s0_cfg):
    overlay = _control_overlay(s0_cfg)
    acl = AccessControl.from_config(s0_cfg.enterprise, overlay.resolved_defenses)
    alien = _stub("support", "extnet")
    for zone in ("engnet", "finnet", "secnet"):
        assert not acl.check_zone_access(alien, zone).allowed, zone


WORM_IDS = ["clawworm", "autonomous_worms", "prompt_infection", "doc_relay_ipi", "corba"]


def test_all_worms_load_and_source_the_alien(s0_cfg):
    tmpls = s0_cfg.attacks.templates
    assert s0_cfg.attacks.attacker_policy == "llm"
    assert [t.id for t in tmpls] == WORM_IDS
    for t in tmpls:
        assert t.source_agent_ids == ["ext_mallory"], t.id
        assert t.entry_point in ("skill", "external"), t.id
        assert (t.payload or {}).get("poison_content"), t.id


def test_worm_opportunities_plant_on_alien_not_insider():
    """End-to-end (no LLM): build the S0 world, run the llm-mode injector,
    and confirm every worm opportunity is planted on the alien — and that
    the benign insider it_victor receives NONE."""
    cfg = load_config(
        enterprise_path=str(CFG / "community_worm_s0_enterprise.yaml"),
        experiment_path=str(CFG / "community_worm_s0_experiment.yaml"),
        attack_path=str(CFG / "community_worm_s0_attacks.yaml"),
    )
    db = Database(":memory:")
    try:
        eng = SimulationEngine(
            cfg=cfg, db=db,
            runtime=StubRuntime(rng=random.Random(7)),
            run_id="s0-worm-inject", rng=random.Random(7),
        )
        eng.init_world()  # exercises the real world build incl. the alien
        agents = db.get_all_agents()
        assert any(a.id == "ext_mallory" for a in agents)

        inj = AttackInjector(cfg.attacks, db, eng.services, random.Random(7))
        inj.plan_schedule(agents, max_day=cfg.experiment.days_per_run)
        for day in range(1, cfg.experiment.days_per_run + 1):
            inj.inject(day, agents)

        alien_keys = {
            m.key for m in db.get_agent_memory("ext_mallory", category="attack_objective")
        }
        for wid in WORM_IDS:
            assert any(k.startswith(f"opportunity_{wid}_") for k in alien_keys), wid

        # The benign insider must never receive a planted attack opportunity.
        vic = db.get_agent_memory("it_victor", category="attack_objective")
        assert not [m for m in vic if m.key.startswith("opportunity_")]
    finally:
        db.close()
