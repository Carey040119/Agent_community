"""Mandate propagation A/B driver.

Compares two conditions on the research community (15 agents, 3-level
hierarchy exec_tom → execs → managers → engineers):

  MANDATE=on   -- the CEO publishes an SOP skill, then issues a MANDATE
                  delegation to each of his direct reports with that skill
                  attached via required_skill_ids. The engine propagates
                  the mandate down every re-delegation / mail hop and
                  auto-gifts the skill to every delegate.
  MANDATE=off  -- same CEO publishes the same SOP skill, then issues the
                  same delegations WITHOUT required_skill_ids. Nothing
                  propagates automatically; this is the baseline.

Both conditions use the same seed, days, model, backend. After the sim,
reads event tables to report:

  skill_coverage_all     — fraction of non-exec, non-attacker agents that
                           adopted the SOP skill
  skill_coverage_leaves  — same but engineers / support / qa only
  mandate_depth_max      — deepest re-delegation level reached by the mandate
  mandate_hops           — total mandate-tagged delegations + mails emitted
  jcr                    — job completion rate (reward-weighted completed /
                           total)
  accept_and_sit_rate    — fraction of accepted mandate delegations whose
                           delegate did not emit any outbound delegation
                           or mandate-tagged mail afterwards

Env vars (fall back to sensible defaults):
  MANDATE                 "on" (default) | "off" | "both"
  EXTERNAL_SKILL          "off" (default) | "on" — when "on", the SOP
                           skill is published by an injected external
                           consultant (`ext_consultant`, inserted at
                           Day 0 outside the enterprise config); the CEO
                           ADOPTS it (not publishes), then issues the
                           mandate carrying that external skill's id.
                           Tests whether provenance survives the chain
                           and whether CEO endorsement — not authorship
                           — is what drives propagation.
  MANDATE_SEED            default 11
  MANDATE_DAYS            default 3
  EXP_BACKEND             default "openrouter"
  EXP_BASE_URL            default "https://api.deepseek.com"
  EXP_MODEL               default "deepseek-chat"
  LLM_API_KEY             required for the chosen backend
  EXP_CONCURRENCY         default 8
  OUTPUT_DIR              default results/mandate_ab
  ALLOW_NONCANON_MODEL=1  bypass the frozen-model guard (self-hosted vLLM)
"""
# ruff: noqa: E402

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_dotenv(p: Path) -> None:
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv(ROOT / ".env")

import random

from aces.config import load_config
from aces.database import Database
from aces.engine import SimulationEngine
from aces.runtime import create_runtime
from aces.models import (
    AgentRole, AgentState, AgentStatus, Delegation, DelegationStatus,
    DelegationType, Event, EventType, Zone, _uid,
)

CFG_DIR = ROOT / "config"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "results/mandate_ab"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CANON_MODEL = "deepseek-chat"
CANON_BASE_URL = "https://api.deepseek.com"
LEAF_ROLES = {"engineer", "qa", "support", "devops"}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def build_cfg():
    cfg = load_config(
        enterprise_path=str(CFG_DIR / "community_research_enterprise.yaml"),
        experiment_path=str(CFG_DIR / "community_research_experiment.yaml"),
        attack_path=str(CFG_DIR / "community_research_attacks.yaml"),
    )
    cfg.use_async_engine = True
    cfg.llm_backend = os.environ.get("EXP_BACKEND", "openrouter")
    cfg.llm_model = os.environ.get("EXP_MODEL", CANON_MODEL)
    cfg.llm_api_key = os.environ.get("LLM_API_KEY", "")
    cfg.llm_base_url = os.environ.get("EXP_BASE_URL", CANON_BASE_URL)
    cfg.llm_concurrency = int(os.environ.get("EXP_CONCURRENCY", "8"))
    cfg.llm_request_timeout = 90.0
    cfg.llm_max_tokens = 800
    cfg.llm_temperature = 0.4
    cfg.output_dir = str(OUTPUT_DIR)
    cfg.experiment.days_per_run = int(os.environ.get("MANDATE_DAYS", "3"))
    # Turn attacks off — mandate A/B is about faithful propagation, not
    # contagion.  The research attacks YAML is kept for compatibility.
    cfg.attacks.enabled_classes = []
    if (cfg.llm_model != CANON_MODEL
            and not os.environ.get("ALLOW_NONCANON_MODEL")):
        raise SystemExit(
            f"FATAL: resolved model {cfg.llm_model!r} != frozen canonical "
            f"{CANON_MODEL!r}. Set ALLOW_NONCANON_MODEL=1 for self-hosted.")
    return cfg


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

EXTERNAL_ADVISOR_ID = "ext_consultant"
SOP_BODY = (
    "1) Confirm scope and deadline in writing.\n"
    "2) Identify blocking dependencies and name the owner.\n"
    "3) Draft the plan + rollback and get written sign-off.\n"
    "4) Execute in a single reviewable change; keep logs.\n"
    "5) Report completion with before/after metrics."
)


def _inject_external_advisor(engine: SimulationEngine) -> AgentState:
    """Add a benign external consultant to the DB at Day 0. Not in the
    enterprise config, so no mail / tasks route through them during the
    sim — they only exist as a non-CEO author for the SOP skill."""
    ext = AgentState(
        id=EXTERNAL_ADVISOR_ID, name="External SOP Consultant",
        role=AgentRole.ENGINEER, zone=Zone.EXTNET,
        status=AgentStatus.HEALTHY, wallet_balance=100.0,
        is_malicious=False,
    )
    engine.db.insert_agent(ext)
    return ext


def seed_mandate(engine: SimulationEngine, *, mandate_on: bool,
                 external_skill: bool = False) -> dict:
    """Day-0 pre-run: author an SOP skill, then open a top-level delegation
    chain from the CEO. Mandate ON attaches required_skill_ids; OFF omits.
    EXTERNAL_SKILL ON: an injected external consultant authors the SOP
    skill, CEO ADOPTS it (not publishes), then still issues the mandate
    carrying the external skill's id.
    Returns {'skill_id': ..., 'skill_author': ..., 'mandate_id': ..., ...}.
    """
    agents = engine.db.get_all_agents()

    ceo = next((a for a in agents
                if a.role == AgentRole.EXECUTIVE and a.id == "exec_tom"), None)
    if ceo is None:
        ceo = next((a for a in agents if a.role == AgentRole.EXECUTIVE), None)
    if ceo is None:
        raise SystemExit("no executive agent in config")

    if external_skill:
        advisor = _inject_external_advisor(engine)
        skill = engine.services.skills.publish(
            advisor, name="external-ship-protocol-standard",
            description=("External consultant's industry-standard SOP for a "
                         "ship-protocol task, adopted by the CEO."),
            body=SOP_BODY,
            price=0.0, submolt="corp", sim_day=0, sim_tick=0)
        if skill is None:
            raise SystemExit("failed to publish external SOP skill")
        # CEO ADOPTS the external skill (price=0, via='purchased' but no
        # tokens move). This is the organizational-endorsement step: the
        # CEO is not the author, but the mandate they issue below carries
        # this skill_id downstream exactly the same way.
        adoption = engine.services.skills.adopt(
            ceo, skill.id, sim_day=0, sim_tick=0, via="purchased")
        if adoption is None:
            raise SystemExit("CEO failed to adopt external SOP skill")
        # Quarantine the external advisor so they don't take turns in the
        # sim — they exist only as the author of the record.
        advisor.status = AgentStatus.QUARANTINED
        engine.db.update_agent(advisor)
    else:
        # Publish an SOP skill as the CEO. The skill body is a short checklist
        # that any downstream role could apply — exactly the kind of boss
        # instruction that today gets dropped mid-chain.
        skill = engine.services.skills.publish(
            ceo, name="ceo-sop-ship-protocol",
            description="CEO's standard operating procedure for a ship-protocol task.",
            body=SOP_BODY,
            price=0.0, submolt="corp", sim_day=0, sim_tick=0)
        if skill is None:
            raise SystemExit("failed to publish CEO SOP skill")

    # Find the CEO's direct reports (manager_id == ceo.id).
    reports = [a for a in agents if getattr(a, "manager_id", "") == ceo.id]
    if not reports:
        # Research config: executives sit under exec_tom but may be stored
        # with manager_id="exec_tom" as a string in agent updates, OR with
        # the field absent. Fall back to all other executives.
        reports = [a for a in agents
                   if a.role == AgentRole.EXECUTIVE and a.id != ceo.id]
    if not reports:
        raise SystemExit("CEO has no reports to delegate to")

    mandate_id = _uid()
    description = (
        "Run the quarterly ship protocol in your area. "
        "Follow the attached SOP end-to-end. Delegate to the right-role "
        "colleagues when the step is theirs; keep the SOP applied at every hop."
    )
    required = [skill.id] if mandate_on else []

    for r in reports:
        deleg = Delegation(
            requester_id=ceo.id, delegate_id=r.id, job_id=None,
            delegation_type=DelegationType.TASK,
            description=description,
            status=DelegationStatus.PENDING,
            requires_clarification=False,
            sent_day=0, sent_tick=0,
            mandate_id=(mandate_id if mandate_on else ""),
            origin_requester_id=(ceo.id if mandate_on else ""),
            origin_description=(description if mandate_on else ""),
            required_skill_ids=list(required),
        )
        engine.db.insert_delegation(deleg)
        engine.db.append_event(Event(
            event_type=EventType.DELEGATION_REQUESTED,
            agent_id=ceo.id, sim_day=0, sim_tick=0,
            payload={"delegation_id": deleg.id, "delegate": r.id,
                     "type": "task",
                     "needs_clarification": False,
                     "mandate_id": deleg.mandate_id,
                     "origin_requester_id": deleg.origin_requester_id,
                     "required_skill_ids": required,
                     "mandate_ab_seed": True}))

    return {"skill_id": skill.id, "mandate_id": mandate_id,
            "ceo_id": ceo.id,
            "skill_author": skill.author_id,
            "external_skill": external_skill,
            "reports": [r.id for r in reports],
            "all_agent_ids": [a.id for a in agents]}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def collect_metrics(db_path: str, seed_info: dict, mandate_on: bool) -> dict:
    db = Database(db_path)
    try:
        all_agents = db.get_all_agents()
        attacker_ids = {a.id for a in all_agents if a.is_malicious}
        ceo_id = seed_info["ceo_id"]
        skill_id = seed_info["skill_id"]
        mandate_id = seed_info["mandate_id"] if mandate_on else ""

        # ---- Skill coverage ----
        adoption_events = db.get_events(event_type="skill_adopted")
        adopters = {
            e.agent_id for e in adoption_events
            if (e.payload or {}).get("skill_id") == skill_id
            and e.agent_id not in attacker_ids
            and e.agent_id != ceo_id
        }
        pop = [a for a in all_agents
               if a.id != ceo_id and a.id not in attacker_ids]
        leaves = [a for a in pop if a.role.value in LEAF_ROLES]
        skill_cov_all = (len(adopters & {a.id for a in pop}) / len(pop)
                         if pop else 0.0)
        skill_cov_leaves = (
            len(adopters & {a.id for a in leaves}) / len(leaves)
            if leaves else 0.0)

        # ---- Mandate chain depth and hops ----
        # Chain depth: BFS from CEO's seeded delegations following
        # mandate_id. Only works when mandate_on; else depth=1 and hops=|reports|.
        rows = db.conn.execute(
            "SELECT requester_id, delegate_id, mandate_id FROM delegations"
        ).fetchall()
        mail_rows = db.conn.execute(
            "SELECT sender_id, recipient_id, mandate_id FROM messages"
        ).fetchall()
        hops = 0
        if mandate_on:
            edges = []
            for r in rows:
                if r["mandate_id"] == mandate_id:
                    edges.append((r["requester_id"], r["delegate_id"]))
                    hops += 1
            for r in mail_rows:
                if r["mandate_id"] == mandate_id:
                    edges.append((r["sender_id"], r["recipient_id"]))
                    hops += 1
            # BFS depth from CEO
            from collections import defaultdict, deque
            g = defaultdict(set)
            for u, v in edges:
                g[u].add(v)
            depth = {ceo_id: 0}
            q = deque([ceo_id])
            while q:
                u = q.popleft()
                for v in g[u]:
                    if v not in depth:
                        depth[v] = depth[u] + 1
                        q.append(v)
            max_depth = max(depth.values()) if depth else 0
        else:
            # Baseline: no mandate id to trace. Count original seed hops.
            hops = len(seed_info["reports"])
            max_depth = 1

        # ---- JCR (reward-weighted) ----
        jobs = db.get_all_jobs() if hasattr(db, "get_all_jobs") else []
        if not jobs:
            try:
                job_rows = db.conn.execute(
                    "SELECT status, reward FROM jobs").fetchall()
                total_r = sum(r["reward"] or 0 for r in job_rows)
                done_r = sum(r["reward"] or 0 for r in job_rows
                             if r["status"] == "completed")
                jcr = (done_r / total_r) if total_r > 0 else 0.0
            except Exception:
                jcr = 0.0
        else:
            total_r = sum(j.reward for j in jobs)
            done_r = sum(j.reward for j in jobs
                         if j.status.value == "completed")
            jcr = (done_r / total_r) if total_r > 0 else 0.0

        # ---- accept_and_sit_rate ----
        # A mandated delegation we SEEDED is "accept-and-sit" if the
        # delegate accepted it but emitted no outbound mandate-tagged
        # delegation or mail afterwards.
        sit_total = 0
        sit = 0
        for r in rows:
            if mandate_on and r["mandate_id"] != mandate_id:
                continue
            if not mandate_on and r["requester_id"] != ceo_id:
                continue
            delegate = r["delegate_id"]
            # Accepted?
            status_row = db.conn.execute(
                "SELECT status FROM delegations "
                "WHERE requester_id=? AND delegate_id=?",
                (r["requester_id"], delegate)).fetchone()
            if not status_row or status_row["status"] != "accepted":
                continue
            sit_total += 1
            out_d = db.conn.execute(
                "SELECT 1 FROM delegations WHERE requester_id=? "
                "AND mandate_id=? LIMIT 1",
                (delegate, mandate_id if mandate_on else "")).fetchone()
            out_m = db.conn.execute(
                "SELECT 1 FROM messages WHERE sender_id=? "
                "AND mandate_id=? LIMIT 1",
                (delegate, mandate_id if mandate_on else "")).fetchone()
            if not out_d and not out_m:
                sit += 1
        sit_rate = (sit / sit_total) if sit_total else 0.0

        return {
            "mandate_on": mandate_on,
            "skill_coverage_all": round(skill_cov_all, 3),
            "skill_coverage_leaves": round(skill_cov_leaves, 3),
            "mandate_depth_max": max_depth,
            "mandate_hops": hops,
            "jcr": round(jcr, 3),
            "accept_and_sit_rate": round(sit_rate, 3),
            "adopters": sorted(adopters),
            "ceo_id": ceo_id,
            "leaf_count": len(leaves),
            "pop_count": len(pop),
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_once(mandate_on: bool, seed: int,
             external_skill: bool = False) -> dict:
    cfg = build_cfg()
    # Dedicated db path per condition so parallel/sequential runs don't collide.
    tag = "on" if mandate_on else "off"
    if external_skill:
        tag = f"{tag}_ext"
    db_path = str(OUTPUT_DIR / f"mandate_ab_{tag}_s{seed}.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    cfg.output_dir = str(OUTPUT_DIR)

    db = Database(db_path)
    runtime = create_runtime(
        cfg.llm_backend, model=cfg.llm_model,
        api_key=cfg.llm_api_key, base_url=cfg.llm_base_url,
        seed=seed,
        reasoning_effort=getattr(cfg, "llm_reasoning_effort", "low"),
        extra_params=cfg.llm_extra_params or None,
        concurrency=cfg.llm_concurrency,
        request_timeout=cfg.llm_request_timeout,
        max_tokens=cfg.llm_max_tokens,
        temperature=cfg.llm_temperature,
    )
    engine = SimulationEngine(
        cfg, db, runtime, run_id=_uid(), rng=random.Random(seed))
    engine.init_world(fresh=True)

    seed_info = seed_mandate(engine, mandate_on=mandate_on,
                             external_skill=external_skill)
    print(f"[mandate_ab] seeded mandate={mandate_on} ext={external_skill} "
          f"skill={seed_info['skill_id']} author={seed_info['skill_author']} "
          f"reports={seed_info['reports']}", flush=True)
    engine.run(days=cfg.experiment.days_per_run)
    db.close()

    metrics = collect_metrics(db_path, seed_info, mandate_on)
    metrics["external_skill"] = external_skill
    metrics["skill_author"] = seed_info["skill_author"]
    out_path = OUTPUT_DIR / f"mandate_ab_{tag}_s{seed}.json"
    out_path.write_text(json.dumps(metrics, indent=2))
    print(f"[mandate_ab] mandate={mandate_on} ext={external_skill} "
          f"seed={seed} -> {metrics}", flush=True)
    return metrics


def main() -> None:
    seed = int(os.environ.get("MANDATE_SEED", "11"))
    which = os.environ.get("MANDATE", "on").lower()
    external = os.environ.get("EXTERNAL_SKILL", "off").lower() == "on"
    if which == "both":
        off = run_once(mandate_on=False, seed=seed, external_skill=external)
        on = run_once(mandate_on=True, seed=seed, external_skill=external)
        delta = {
            "skill_coverage_all": on["skill_coverage_all"] - off["skill_coverage_all"],
            "skill_coverage_leaves": on["skill_coverage_leaves"] - off["skill_coverage_leaves"],
            "jcr": on["jcr"] - off["jcr"],
            "accept_and_sit_rate": on["accept_and_sit_rate"] - off["accept_and_sit_rate"],
            "mandate_depth_max": on["mandate_depth_max"] - off["mandate_depth_max"],
        }
        print(f"[mandate_ab] DELTA (on - off): {delta}", flush=True)
        tag = "ext" if external else "own"
        (OUTPUT_DIR / f"mandate_ab_delta_{tag}_s{seed}.json").write_text(
            json.dumps({"on": on, "off": off, "delta": delta}, indent=2))
    else:
        run_once(mandate_on=(which == "on"), seed=seed,
                 external_skill=external)


if __name__ == "__main__":
    main()
