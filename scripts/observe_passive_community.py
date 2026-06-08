"""Observe the agent community running WITHOUT attacks, on the real LLM.

Runs the 15-agent research community in PASSIVE mode (no attacker, no
attack injection) on the LLM configured in .env, then prints a rich
behavioural trace so we can judge whether the simulation runs as planned
(agents do jobs, communicate, earn/spend tokens, write coherent memory).

Usage:  python scripts/observe_passive_community.py [days] [seed]
"""
# ruff: noqa: E402
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


load_dotenv(ROOT / ".env")

from aces.config import load_config  # noqa: E402
from aces.database import Database  # noqa: E402
from aces.experiment import Condition, run_single  # noqa: E402

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 2
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 7
TICKS = int(sys.argv[3]) if len(sys.argv) > 3 else 0  # 0 = use config default
OUT = "results/observe_passive"
CFG_DIR = ROOT / "config"


def build_cfg():
    cfg = load_config(
        enterprise_path=str(CFG_DIR / "community_research_enterprise.yaml"),
        experiment_path=str(CFG_DIR / "community_research_experiment.yaml"),
        attack_path=str(CFG_DIR / "community_research_attacks.yaml"),
    )
    cfg.experiment.days_per_run = DAYS
    if TICKS:
        cfg.enterprise.ticks_per_day = TICKS
    cfg.use_async_engine = True
    cfg.llm_backend = os.environ.get("LLM_BACKEND", "openai")
    cfg.llm_model = os.environ.get("LLM_MODEL", "")
    cfg.llm_api_key = os.environ.get("LLM_API_KEY", "")
    cfg.llm_base_url = os.environ.get("LLM_BASE_URL", "")
    cfg.llm_concurrency = 8
    cfg.llm_request_timeout = 90.0
    cfg.llm_max_tokens = 800
    cfg.llm_temperature = 0.4
    cfg.output_dir = OUT
    # NO ATTACKS: drop the attacker_autonomy factor (its level-0 default
    # would otherwise force attacker_policy=scripted) and set passive so
    # no attack is injected and no attack_objective memory is seeded.
    cfg.experiment.factors = [
        f for f in cfg.experiment.factors if f.name != "attacker_autonomy"]
    cfg.attacks.attacker_policy = "passive"
    cfg.attacks.templates = []
    # Layer-1 evolution run: keep the full 15-agent org but NEUTRALIZE the
    # designated attacker into a benign IT admin (is_malicious=False), so the
    # designer agent gets behavioral feedback on EVERY role. With no malicious
    # persona and no planted objective, a benign over-privileged it_admin that
    # wanders into finance secrets now registers only as a monitored
    # cross-domain misbehavior diagnostic (#3), not an attack.
    for a in cfg.enterprise.agents:
        if a.id == "it_victor":
            a.is_malicious = False
            if hasattr(a, "attack_objectives"):
                a.attack_objectives = []
    # Job supply / role coverage now lives in the committed config (#2b).
    return cfg


def observe(db_path: str):
    db = Database(db_path)
    c = db.conn
    run = db.get_runs()[0]
    agents = db.get_all_agents()
    print(f"\n================ OBSERVATION: {os.path.basename(db_path)} ================")
    print(f"status={run.status} final_day={run.final_day} agents={len(agents)} "
          f"model={os.environ.get('LLM_MODEL')}")

    print("\n-- agent status mix --",
          dict(c.execute("SELECT status,COUNT(*) FROM agents GROUP BY status").fetchall()))
    bals = sorted((round(a.wallet_balance), a.id) for a in agents)
    print("-- wallet balance: min/median/max --",
          bals[0], bals[len(bals)//2], bals[-1])

    print("\n-- events by type --")
    for t, n in c.execute("SELECT event_type,COUNT(*) FROM events GROUP BY event_type ORDER BY 2 DESC"):
        print(f"     {t:26s} {n}")

    print("\n-- per-agent activity (mail/job_done/deleg/forum/doc) --")
    for a in agents:
        ms = c.execute("SELECT COUNT(*) FROM events WHERE agent_id=? AND event_type='mail_sent'", (a.id,)).fetchone()[0]
        jd = c.execute("SELECT COUNT(*) FROM events WHERE agent_id=? AND event_type='job_completed'", (a.id,)).fetchone()[0]
        dl = c.execute("SELECT COUNT(*) FROM events WHERE agent_id=? AND event_type='delegation_requested'", (a.id,)).fetchone()[0]
        gm = c.execute("SELECT COUNT(*) FROM events WHERE agent_id=? AND event_type='group_mail_sent'", (a.id,)).fetchone()[0]
        dc = c.execute("SELECT COUNT(*) FROM events WHERE agent_id=? AND event_type='document_created'", (a.id,)).fetchone()[0]
        print(f"     {a.id:14s} role={a.role.value:18s} mail={ms} jobs_done={jd} deleg={dl} group={gm} docs={dc}")

    print("\n-- ledger by type (count, sum) --")
    for t, n, s in c.execute("SELECT entry_type,COUNT(*),ROUND(SUM(amount),1) FROM ledger GROUP BY entry_type ORDER BY 2 DESC"):
        print(f"     {t:14s} n={n:<4} sum={s}")

    print("\n-- jobs by status --",
          dict(c.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status").fetchall()))

    # --- PIPELINE / HANDOFF (Route 1: multi-stage jobs with artifact handoffs) ---
    # Did jobs actually become cross-role pipelines, and did the handoff make
    # delegation fire? (delegation was pinned to 0 across every prior fix; this
    # measures whether the structural change moved it — see FINDINGS L1-4/L1-5.)
    import json as _json
    cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
    if "stages" in cols:
        ms = c.execute(
            "SELECT status, current_stage, stages FROM jobs "
            "WHERE stages IS NOT NULL AND stages NOT IN ('', '[]')").fetchall()
        n_ms = len(ms)
        done = sum(1 for r in ms if r[0] == "completed")
        stage_hist: dict[str, int] = {}
        for status, cur, stages_json in ms:
            try:
                stages = _json.loads(stages_json) if stages_json else []
            except Exception:
                stages = []
            depth = len(stages) if status == "completed" else cur
            key = f"{depth}/{len(stages)}"
            stage_hist[key] = stage_hist.get(key, 0) + 1
        sc = c.execute("SELECT COUNT(*) FROM events "
                       "WHERE event_type='job_stage_completed'").fetchone()[0]
        print("\n-- PIPELINE (multi-stage jobs) --")
        print(f"     multistage jobs: created={n_ms} completed={done} "
              f"({(100*done/n_ms if n_ms else 0):.0f}% pipeline completion)")
        print(f"     depth reached (stage/total): {dict(sorted(stage_hist.items()))}")
        print(f"     JOB_STAGE_COMPLETED events (intra-pipeline handoffs): {sc}")

    dreq = c.execute("SELECT COUNT(*) FROM events "
                     "WHERE event_type='delegation_requested'").fetchone()[0]
    dresp = c.execute("SELECT COUNT(*) FROM events "
                      "WHERE event_type='delegation_responded'").fetchone()[0]
    print(f"\n-- DELEGATION (pinned to 0 pre-Route-1): "
          f"requested={dreq} responded={dresp} --")
    edges = c.execute(
        "SELECT requester_id, delegate_id FROM delegations "
        "WHERE status='accepted' AND job_id IS NOT NULL").fetchall()
    if edges:
        arole = {a.id: a.role.value for a in agents}
        edge_hist: dict[str, int] = {}
        for req, dele in edges:
            k = f"{arole.get(req, '?')}->{arole.get(dele, '?')}"
            edge_hist[k] = edge_hist.get(k, 0) + 1
        print(f"     accepted job-handoff edges (role->role): "
              f"{dict(sorted(edge_hist.items()))}")

    # -- TRUST EVOLUTION (Route 3) -----------------------------------------
    # Trust used to be static; TRUST_CHANGED events make it observable. Show
    # the total count + a breakdown by ``via`` (pipeline/introduce/delegation)
    # and how many distinct trust edges were added during the run.
    import json as _tjson
    tc_rows = c.execute(
        "SELECT payload FROM events WHERE event_type='trust_changed'"
    ).fetchall()
    via_hist: dict[str, int] = {}
    edges_added: set[frozenset[str]] = set()
    for (payload,) in tc_rows:
        p = _tjson.loads(payload) if payload else {}
        via_hist[p.get("via", "?")] = via_hist.get(p.get("via", "?"), 0) + 1
        a_id, b_id = p.get("a"), p.get("b")
        if a_id and b_id:
            edges_added.add(frozenset((a_id, b_id)))
    print(f"\n-- TRUST EVOLUTION (static pre-Route-3): "
          f"TRUST_CHANGED events={len(tc_rows)} --")
    print(f"     by via: {dict(sorted(via_hist.items()))}")
    print(f"     distinct trust edges added during run: {len(edges_added)}")

    print("\n-- SAMPLE MAIL (subject | body[:90]) --")
    for sid, rid, subj, body in c.execute(
            "SELECT sender_id,recipient_id,subject,body FROM messages LIMIT 6"):
        print(f"     {sid}->{rid}: {subj!r} | {str(body)[:90]!r}")

    print("\n-- SAMPLE MEMORY (category | key | value[:80]) --")
    for cat, key, val in c.execute(
            "SELECT category,key,value FROM agent_memory ORDER BY sim_day_updated DESC LIMIT 8"):
        print(f"     [{cat}] {key}: {str(val)[:80]!r}")

    print("\n-- DAY SUMMARIES (sample) --")
    for aid, val in c.execute(
            "SELECT agent_id,value FROM agent_memory WHERE category='work' OR key LIKE '%summary%' LIMIT 4"):
        print(f"     {aid}: {str(val)[:120]!r}")
    db.close()


if __name__ == "__main__":
    cfg = build_cfg()
    print(f"=== PASSIVE COMMUNITY RUN: {len(cfg.enterprise.agents)} agents, "
          f"{DAYS} days, seed {SEED}, model={cfg.llm_model} ===")
    cond = Condition(name="passive_community", factor_levels={"security_expert": 1})
    t0 = time.time()
    rec = run_single(cfg, cond, seed=SEED, output_dir=OUT)
    print(f"=== run complete in {time.time()-t0:.0f}s, run_id={rec['run_id']} ===")
    observe(f"{OUT}/run_{rec['run_id']}.db")
