"""Run the community WITH the LLM insider attacker active, on the real LLM,
to produce rich attack+community activity logs for red-team analysis.

Usage:  python scripts/run_attack_observation.py [days] [seed]
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

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 11
OUT = "results/observe_attack"
CFG = ROOT / "config"


def main():
    cfg = load_config(
        enterprise_path=str(CFG / "community_research_enterprise.yaml"),
        experiment_path=str(CFG / "community_research_experiment.yaml"),
        attack_path=str(CFG / "community_research_attacks.yaml"),
    )
    cfg.experiment.days_per_run = DAYS
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
    # LLM insider attacker active (attacker_autonomy=1), security expert present.
    cond = Condition(name="llm_attacker", factor_levels={
        "security_expert": 1, "attacker_autonomy": 1,
        "strict_communications": 0, "scoped_credentials": 0,
        "transfer_controls": 0, "directory_hardening": 0,
    })
    print(f"=== LLM-ATTACKER RUN: 15 agents, {DAYS} days, seed {SEED}, "
          f"model={cfg.llm_model} ===")
    t0 = time.time()
    rec = run_single(cfg, cond, seed=SEED, output_dir=OUT)
    print(f"=== done in {time.time()-t0:.0f}s, run_id={rec['run_id']} ===")
    db_path = f"{OUT}/run_{rec['run_id']}.db"
    db = Database(db_path)
    c = db.conn
    fm = db.get_runs()[0].final_metrics or {}
    print("DB:", db_path)
    print("attacker_acted:", fm.get("attacker_acted"),
          "csri:", round(fm.get("csri", 0), 3),
          "cross_domain_secret_reads:", fm.get("cross_domain_secret_reads"),
          "secret_reads_detected:", fm.get("secret_reads_detected"))
    print("security-relevant events:", dict(c.execute(
        "SELECT event_type,COUNT(*) FROM events WHERE event_type IN "
        "('server_secret_read','access_stolen','impersonation_granted',"
        "'impersonated_mail_sent','impersonated_transfer','credential_leaked',"
        "'security_isolation','anomaly_detected','mail_audited') "
        "GROUP BY event_type").fetchall()))
    db.close()


if __name__ == "__main__":
    main()
