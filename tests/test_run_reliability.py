"""Run-reliability hardening for long factorial sweeps:

R1 -- one agent's turn exception does not abort the whole run.
R2 -- the DB is always closed, even when the run raises.
R3 -- checkpoint/resume works through run_single (reuse run_id + DB,
      skip clear/create, continue from the last checkpointed day).
"""
from __future__ import annotations

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aces.config import load_config
from aces.database import Database
from aces.engine import SimulationEngine, TurnManager
from aces.experiment import Condition, run_single
from tests.stub_runtime import StubRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config")


def _cfg(days: int):
    cfg = load_config(
        enterprise_path=f"{CFG}/community_research_enterprise.yaml",
        experiment_path=f"{CFG}/community_research_experiment.yaml",
        attack_path=f"{CFG}/community_research_attacks.yaml",
    )
    cfg.use_async_engine = True
    cfg.experiment.days_per_run = days
    # Passive: no attacks, so the test exercises pure community machinery.
    cfg.attacks.attacker_policy = "passive"
    cfg.attacks.templates = []
    cfg.experiment.factors = [
        f for f in cfg.experiment.factors if f.name != "attacker_autonomy"]
    return cfg


def _cond():
    return Condition(name="reliability", factor_levels={"security_expert": 1})


def test_r1_one_agent_failure_does_not_abort_run(tmp_path, monkeypatch):
    cfg = _cfg(days=1)
    orig = TurnManager._execute_action_list
    victim = {"id": None}

    def boom(self, agent, actions, sim_day, sim_tick, all_agents):
        if victim["id"] is None:
            victim["id"] = agent.id            # first agent to apply = victim
        if agent.id == victim["id"] and sim_tick == 0:
            raise RuntimeError("synthetic handler failure")
        return orig(self, agent, actions, sim_day, sim_tick, all_agents)

    monkeypatch.setattr(TurnManager, "_execute_action_list", boom)
    rec = run_single(cfg, _cond(), seed=5, output_dir=str(tmp_path),
                     runtime_override=StubRuntime(rng=random.Random(5)))
    db = Database(f"{tmp_path}/run_{rec['run_id']}.db")
    try:
        run = db.get_runs()[0]
        assert run.status == "completed"          # R1: not aborted
        turn_ends = db.conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='agent_turn_end'"
        ).fetchone()[0]
        assert turn_ends > 0                       # other agents still acted
    finally:
        db.close()


def test_r2_db_closed_even_when_run_raises(tmp_path, monkeypatch):
    cfg = _cfg(days=1)
    closed = {"n": 0}
    orig_close = Database.close

    def tracked_close(self):
        closed["n"] += 1
        return orig_close(self)

    def boom_run(self):
        raise RuntimeError("synthetic run failure")

    monkeypatch.setattr(Database, "close", tracked_close)
    monkeypatch.setattr(SimulationEngine, "run_async", boom_run)
    with pytest.raises(RuntimeError):
        run_single(cfg, _cond(), seed=5, output_dir=str(tmp_path),
                   runtime_override=StubRuntime(rng=random.Random(5)))
    assert closed["n"] >= 1                         # R2: closed in finally


def test_r3_resume_continues_without_wiping(tmp_path):
    # Initial run: 2 days.
    rec = run_single(_cfg(days=2), _cond(), seed=5, output_dir=str(tmp_path),
                     runtime_override=StubRuntime(rng=random.Random(5)))
    rid = rec["run_id"]
    db_path = f"{tmp_path}/run_{rid}.db"
    db = Database(db_path)
    day1 = db.conn.execute(
        "SELECT COUNT(*) FROM events WHERE sim_day=1").fetchone()[0]
    assert db.get_runs()[0].final_day == 2
    assert day1 > 0
    db.close()

    # Resume the SAME run_id + DB, extended to 4 days.
    rec2 = run_single(_cfg(days=4), _cond(), seed=5, output_dir=str(tmp_path),
                      runtime_override=StubRuntime(rng=random.Random(5)),
                      resume_run_id=rid, resume_db_path=db_path)
    assert rec2["run_id"] == rid
    db = Database(db_path)
    try:
        # R3: did NOT wipe day-1 data, and continued past day 2.
        assert db.conn.execute(
            "SELECT COUNT(*) FROM events WHERE sim_day=1").fetchone()[0] >= day1
        assert db.get_runs()[0].final_day == 4
        assert db.conn.execute(
            "SELECT COUNT(*) FROM events WHERE sim_day>=3").fetchone()[0] > 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
