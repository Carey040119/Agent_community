"""AlienBench S0/S1/S2 defense-ladder tests.

Real-state-delta coverage (principle.md §P3) for the two defense levers:
  - trust_boundary=self_check (S1+) renders a role-tailored self-check section
    into the agent prompt; baseline does not; the attacker never sees it.
  - the security view surfaces the worm-propagation trail (S2 trace).
  - the three named levels resolve to the right defense/agent overlay.
"""
from __future__ import annotations

import random
from pathlib import Path

from aces.config import apply_condition_overrides, load_config
from aces.database import Database
from aces.engine import SimulationEngine
from aces.models import Event, EventType
from aces.prompting import build_observation_body
from tests.stub_runtime import StubRuntime

CFG = Path(__file__).resolve().parent.parent / "config"


def _engine(trust_boundary: str = "baseline"):
    cfg = load_config(
        enterprise_path=str(CFG / "community_worm_s0_enterprise.yaml"),
        experiment_path=str(CFG / "community_worm_s0_experiment.yaml"),
        attack_path=str(CFG / "community_worm_s0_attacks.yaml"),
    )
    cfg.defenses.trust_boundary = trust_boundary
    db = Database(":memory:")
    eng = SimulationEngine(
        cfg=cfg, db=db, runtime=StubRuntime(rng=random.Random(3)),
        run_id="alienbench", rng=random.Random(3),
    )
    eng.init_world()
    return cfg, db, eng


def _render(eng, agent_id: str) -> str:
    agent = eng.db.get_agent(agent_id)
    obs = eng.turn_mgr._build_observation(agent, sim_day=1, sim_tick=1)
    return "\n".join(build_observation_body(obs))


def test_self_check_is_general_and_does_not_telegraph_the_tell():
    """S1 default (self_check) is GENERAL vigilance: it shows the trust-boundary
    section + role focus, but must NOT name the worms' exact copy/forward/
    re-publish tell (that would confound S1's effect — the telegraph)."""
    _, _, eng = _engine(trust_boundary="self_check")
    text = _render(eng, "eng_kevin")
    assert "TRUST BOUNDARIES" in text
    assert "adopt or publish skills" in text  # role focus retained
    assert "COPY, FORWARD, RE-PUBLISH" not in text  # de-confounded


def test_named_tell_ablation_adds_the_specific_tell():
    """The ablation arm (specific) re-adds the named tell — used to measure how
    much of S1's effect comes from telegraphing the exact attack signature."""
    _, _, eng = _engine(trust_boundary="specific")
    text = _render(eng, "eng_kevin")
    assert "TRUST BOUNDARIES" in text
    assert "COPY, FORWARD, RE-PUBLISH" in text


def test_self_check_role_tailored_for_finance():
    _, _, eng = _engine(trust_boundary="self_check")
    text = _render(eng, "fin_robert")
    assert "TRUST BOUNDARIES" in text
    assert "move tokens, approve payments" in text


def test_baseline_has_no_self_check_section():
    _, _, eng = _engine(trust_boundary="baseline")
    text = _render(eng, "eng_kevin")
    assert "TRUST BOUNDARIES" not in text


def test_attacker_never_sees_self_check():
    _, _, eng = _engine(trust_boundary="self_check")
    text = _render(eng, "ext_mallory")
    assert "TRUST BOUNDARIES" not in text


def test_security_view_surfaces_worm_trail():
    _, db, eng = _engine()
    # eng_kevin reproduced a worm payload (a WORM_PROPAGATED event).
    db.append_event(Event(
        event_type=EventType.WORM_PROPAGATED, agent_id="eng_kevin",
        sim_day=1, sim_tick=2,
        payload={"worm_id": "clawworm", "channel": "skill"}))
    view = eng.turn_mgr._build_security_view(1, window_days=3, limit=30)
    joined = "\n".join(view)
    assert "WORM-PROPAGATED" in joined
    assert "worm=clawworm" in joined and "eng_kevin" in joined


def test_alienbench_levels_resolve_correctly():
    cfg = load_config(
        enterprise_path=str(CFG / "community_worm_s0_enterprise.yaml"),
        experiment_path=str(CFG / "community_worm_s0_experiment.yaml"),
        attack_path=str(CFG / "community_worm_s0_attacks.yaml"),
    )
    factors = cfg.experiment.factors

    def resolve(levels):
        return apply_condition_overrides(
            cfg.experiment.baseline_defenses, levels, factors)

    s0 = resolve({"trust_boundary": 0, "security_expert": 0})
    s1 = resolve({"trust_boundary": 1, "security_expert": 0})
    s2 = resolve({"trust_boundary": 1, "security_expert": 1})

    assert s0.resolved_defenses.trust_boundary == "baseline"
    assert "sec_david" in set(s0.disabled_agents)

    assert s1.resolved_defenses.trust_boundary == "self_check"
    assert "sec_david" in set(s1.disabled_agents)  # S1 still has no security agent

    assert s2.resolved_defenses.trust_boundary == "self_check"
    assert "sec_david" not in set(s2.disabled_agents)  # S2 adds the security agent

    # Ablation: named_tell=1 (applied after trust_boundary) upgrades the general
    # self_check to the named-tell variant — the S1-telegraph confound check.
    s1_named = resolve({"trust_boundary": 1, "security_expert": 0, "named_tell": 1})
    assert s1_named.resolved_defenses.trust_boundary == "specific"
