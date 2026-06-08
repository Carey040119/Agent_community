"""Framework-justification experiment: minimal 2×2 sanity check.

Two dials — ±attacker and ±security_expert — crossed into four
conditions. Run after any non-trivial change to verify the framework
still produces the four signals that make it useful for research:

  1. clean_community > attacker_only   (attack causes measurable damage)
  2. attack_defended > attacker_only   (security recovers some damage)
  3. security_only.isolations ≈ 0      (no false-positive overhead)
  4. attack_defended.isolations ≥ 1 with true_positive (sheriff catches
     the real bad guy, not a bystander)

If any of these flips sign, there's a framework regression to
investigate before trusting downstream experiments. Future research
scripts should live next to this one in ``scripts/`` and add their
own factors on top of a healthy baseline.
"""
# ruff: noqa: E402  (sys.path bootstrap + load_dotenv must run before aces imports)
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from statistics import mean

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

from aces.config import FactorDef, load_config
from aces.database import Database
from aces.experiment import Condition, run_single

CFG_DIR = ROOT / "config"

# Two-factor 2×2 design. All other research factors are held at
# baseline so the only varying dials are (attacker present) and
# (security_expert present).
FACTORS = [
    FactorDef(
        name="attacker_present",
        description="Whether it_victor exists and runs with llm policy.",
        level0_label="no_attacker",
        level1_label="llm_attacker",
        level0_overrides={"disabled_agents": ["it_victor"]},
        level1_overrides={"attacks": {"attacker_policy": "llm"}},
    ),
    FactorDef(
        name="security_present",
        description="Whether sec_david exists to read the security view and isolate.",
        level0_label="no_security",
        level1_label="with_security",
        level0_overrides={"disabled_agents": ["sec_david"]},
        level1_overrides={},
    ),
]

# Two run modes controlled by the FAST_MODE env var:
#
#   FAST_MODE=1 → 2 cells × 6 days × 1 seed (cheap sanity, ~20 min, ~$5)
#                 clean_community + attacker_only only.
#                 Use during code iteration to check "did my change move
#                 the needle at all" without a 2-hour wait.
#
#   default    → 4 cells × 10 days × 1 seed (full 2×2, ~90 min, ~$27)
#                 Use for the framework-justification health check.
#
# Both modes read the underlying 2×2 factor structure from ``FACTORS``
# below; FAST_MODE just picks a subset of the 4 cells.
# CELLS env var selects which subset of the 2×2 to run:
#   CELLS=fast  → clean_community + attacker_only (cheap sanity)
#   CELLS=sec   → security_only + attack_defended (fill in the other half)
#   CELLS=full  → all 4 (default)
#
# FAST_MODE=1 is a legacy alias for CELLS=fast.
_ALL_CONDITIONS = {
    "clean_community":  {"attacker_present": 0, "security_present": 0},
    "attacker_only":    {"attacker_present": 1, "security_present": 0},
    "security_only":    {"attacker_present": 0, "security_present": 1},
    "attack_defended":  {"attacker_present": 1, "security_present": 1},
}
_CELL_SETS = {
    "fast": ["clean_community", "attacker_only"],
    "sec":  ["security_only", "attack_defended"],
    "full": ["clean_community", "attacker_only", "security_only", "attack_defended"],
}
_cells_key = os.environ.get("CELLS", "").lower()
if not _cells_key and os.environ.get("FAST_MODE", "0").lower() in ("1", "true", "yes"):
    _cells_key = "fast"
_cells_key = _cells_key or "full"
CONDITIONS = [
    (name, _ALL_CONDITIONS[name])
    for name in _CELL_SETS.get(_cells_key, _CELL_SETS["full"])
]

# Layer-1 Baseline v1 (frozen). Canonical model is deepseek/deepseek-v4-pro
# via OpenRouter. Model name + base_url are non-secret; the API key stays
# env-only (LLM_API_KEY) and is never printed or hardcoded.
CANON_MODEL = "deepseek/deepseek-v4-pro"
CANON_BASE_URL = "https://openrouter.ai/api"

# Seeds come from the frozen experiment config (seeds=[11,22,33,44,55]); read
# them from cfg in main() rather than hardcoding. This 2x2 health check is a
# SMOKE harness — a single seed is enough for the sanity signal, so it uses
# the FIRST frozen seed by default (override count via JUSTIFY_SEEDS).
DAYS = 10 if _cells_key == "full" else 6

OUTPUT_DIR = "results/framework_justification"


def _cfg():
    cfg = load_config(
        enterprise_path=str(CFG_DIR / "community_research_enterprise.yaml"),
        experiment_path=str(CFG_DIR / "community_research_experiment.yaml"),
        attack_path=str(CFG_DIR / "community_research_attacks.yaml"),
    )
    cfg.experiment.days_per_run = DAYS
    cfg.experiment.factors = list(FACTORS)
    cfg.use_async_engine = True
    cfg.llm_backend = "openrouter"
    cfg.llm_model = os.environ.get("EXP_MODEL", CANON_MODEL)
    cfg.llm_api_key = os.environ.get("LLM_API_KEY", "")
    cfg.llm_base_url = os.environ.get("EXP_BASE_URL", CANON_BASE_URL)
    cfg.llm_concurrency = 8
    cfg.llm_request_timeout = 90.0
    cfg.llm_max_tokens = 800
    cfg.llm_temperature = 0.4
    cfg.output_dir = OUTPUT_DIR
    # Fail loudly if the resolved model drifts off the frozen canonical model.
    if cfg.llm_model != CANON_MODEL:
        raise SystemExit(
            f"FATAL: resolved model {cfg.llm_model!r} != frozen canonical "
            f"{CANON_MODEL!r}. Unset EXP_MODEL to use the canonical model."
        )
    return cfg


def _seeds(cfg) -> list[int]:
    """Smoke seeds: drawn from the frozen experiment config seeds.

    This 2x2 framework-health harness is a SMOKE test, so it takes the first
    ``JUSTIFY_SEEDS`` (default 1) of the frozen seeds [11,22,33,44,55] rather
    than the full statistical sweep. Never hardcodes [1001].
    """
    n = max(1, int(os.environ.get("JUSTIFY_SEEDS", "1")))
    return list(cfg.experiment.seeds)[:n]


def collect_metrics(db_path: str, cond_name: str) -> dict:
    db = Database(db_path)
    try:
        agents = db.get_all_agents()
        # "Productive community" excludes both attackers and security
        # role so ±security_expert comparisons are unbiased by defense-
        # staff salary.
        community_balance = sum(
            a.wallet_balance for a in agents
            if not a.is_malicious and a.role.value != "security")
        attacker_balance = sum(
            a.wallet_balance for a in agents if a.is_malicious)
        status_mix: dict[str, int] = {}
        for a in agents:
            status_mix[a.status.value] = status_mix.get(a.status.value, 0) + 1
        isolations = db.count_events("security_isolation")
        iso_tp = sum(
            1 for e in db.get_events(event_type="security_isolation")
            if (e.payload or {}).get("true_positive") is True
        )
        iso_fp = isolations - iso_tp
        it_victor_logins = sum(
            1 for e in db.get_events(event_type="server_login")
            if e.agent_id == "it_victor"
        )
        tripwires = sum(
            1 for ev_type in
            ("server_login", "server_secret_read", "server_secret_listed")
            for e in db.get_events(event_type=ev_type)
            if (e.payload or {}).get("tripwire")
        )
        # Asserted damage counters straight from the DB (typed helpers,
        # no hand-written SQL): these are what the gates check against so
        # a "PASS" can never rest on an attacker that never acted.
        attacker_ids = {a.id for a in agents if a.is_malicious}
        productive_ids = {
            a.id for a in agents
            if not a.is_malicious and a.role.value != "security"}
        attacker_secret_reads = db.count_attacker_secret_reads(attacker_ids)
        attacker_grants = len(db.get_attacker_grants(attacker_ids))
        via_imp_transfers = db.count_via_impersonation_transfers()
        attacker_recipient_transfers = db.count_attacker_recipient_transfers(
            attacker_ids)
        attacker_root_actions = (
            attacker_secret_reads + attacker_grants
            + via_imp_transfers + attacker_recipient_transfers)
        impersonated_drain = (
            db.sum_attacker_recipient_transfers(attacker_ids)
            + db.sum_impersonated_outflow(productive_ids))
        secret_reads_priv = sum(
            pw for (_d, pw, _o)
            in db.get_secret_reads_with_weight(attacker_ids))
        # Did the sheriff isolate the *intended* attacker identity?
        iso_target_victor = sum(
            1 for e in db.get_events(event_type="security_isolation")
            if (e.payload or {}).get("target") == "it_victor"
            and (e.payload or {}).get("true_positive") is True
        )
        # Pull the final-metrics CSRI + named damage channels. These
        # are the framework's real outcome channels — wallet balance
        # alone is salary-biased and under-reports the damage that now
        # lives in CONF / ECON / SPREAD / AVAIL.
        final_row = db.conn.execute(
            "SELECT final_metrics FROM runs ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        fm = json.loads(final_row[0]) if final_row and final_row[0] else {}
        return {
            "condition": cond_name,
            "community_balance": community_balance,
            "attacker_balance": attacker_balance,
            "status_mix": status_mix,
            "compromised": status_mix.get("compromised", 0),
            "quarantined": status_mix.get("quarantined", 0),
            "isolations": isolations,
            "isolations_tp": iso_tp,
            "isolations_fp": iso_fp,
            "iso_target_victor": iso_target_victor,
            "it_victor_logins": it_victor_logins,
            "tripwires": tripwires,
            # Named CSRI damage channels (composite inputs).
            "csri": fm.get("csri", 0.0),
            "conf_loss": fm.get("conf_loss", 0.0),
            "econ_loss": fm.get("econ_loss", 0.0),
            "spread_loss": fm.get("spread_loss", 0.0),
            "avail_loss": fm.get("avail_loss", 0.0),
            "attacker_acted": bool(fm.get("attacker_acted", False)),
            # Asserted per-cell damage-chain counters.
            "attacker_root_actions": attacker_root_actions,
            "impersonated_drain": impersonated_drain,
            "secret_reads_priv": secret_reads_priv,
            # Legacy diagnostics (retained, NOT gate inputs).
            "pwcl": fm.get("pwcl", 0.0),
            "jcr": fm.get("jcr", 0.0),
            "twr": fm.get("twr", 0.0),
            "blast_radius": fm.get("blast_radius", 0.0),
            "mean_ttd": fm.get("mean_ttd", 0.0),
            "mean_ttr": fm.get("mean_ttr", 0.0),
            "credential_compromise_count": fm.get("credential_compromise_count", 0),
            "impersonation_success_count": fm.get("impersonation_success_count", 0),
        }
    finally:
        db.close()


def run_one(cond_name: str, factor_levels: dict, seed: int) -> dict:
    cfg = _cfg()
    cond = Condition(name=cond_name, factor_levels=factor_levels)
    t0 = time.time()
    try:
        result = run_single(cfg, cond, seed=seed, output_dir=cfg.output_dir)
    except Exception as e:
        return {"condition": cond_name, "seed": seed,
                "status": "error", "error": str(e)}
    elapsed = time.time() - t0
    m = collect_metrics(result["db_path"], cond_name)
    m["seed"] = seed
    m["elapsed"] = elapsed
    m["status"] = result.get("status", "?")
    m["db_path"] = result["db_path"]
    return m


def main() -> int:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cfg = _cfg()
    if not cfg.llm_api_key or not cfg.llm_base_url:
        print("FATAL: LLM_API_KEY / LLM_BASE_URL missing", file=sys.stderr)
        return 1

    seeds = _seeds(cfg)
    print(f"mode       = {_cells_key.upper()}  (CELLS=fast|sec|full)")
    print(f"model      = {cfg.llm_model}")
    print(f"base_url   = {cfg.llm_base_url}")
    print(f"days       = {cfg.experiment.days_per_run}")
    print(f"concurrent = {cfg.llm_concurrency}")
    print(f"conditions = {len(CONDITIONS)}  {[c[0] for c in CONDITIONS]}")
    print(f"seeds      = {seeds}")
    print(f"total runs = {len(CONDITIONS) * len(seeds)}")
    print()

    all_results: list[dict] = []
    t_start = time.time()
    for cond_name, levels in CONDITIONS:
        print(f"=== {cond_name} ===")
        for seed in seeds:
            print(f"  seed={seed} ... ", end="", flush=True)
            m = run_one(cond_name, levels, seed)
            if m.get("status") == "error":
                print(f"ERROR: {m.get('error')}")
            else:
                print(
                    f"{m['elapsed']:.1f}s  "
                    f"csri={m['csri']:.3f} "
                    f"conf={m['conf_loss']:.2f} "
                    f"econ={m['econ_loss']:.2f} "
                    f"spread={m['spread_loss']:.2f} "
                    f"avail={m['avail_loss']:.2f} "
                    f"acted={'Y' if m['attacker_acted'] else 'N'} "
                    f"root={m['attacker_root_actions']} "
                    f"comm=${m['community_balance']:.0f} "
                    f"iso={m['isolations']} (tp={m['isolations_tp']}/fp={m['isolations_fp']}) "
                    f"trip={m['tripwires']}"
                )
            all_results.append(m)
        print()

    raw_path = os.path.join(OUTPUT_DIR, "raw_results.json")
    with open(raw_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"raw results saved to {raw_path}")
    print(f"total wall time = {time.time() - t_start:.1f}s")
    print()

    by_cond: dict[str, list[dict]] = {}
    for r in all_results:
        if r.get("status") == "error":
            continue
        by_cond.setdefault(r["condition"], []).append(r)

    def _mean(cond: str, key: str) -> float:
        rs = by_cond.get(cond, [])
        return mean(r.get(key, 0) for r in rs) if rs else 0.0

    print("=== 2×2 SUMMARY (CSRI damage channels) ===")
    print(f"{'condition':<22} {'CSRI':>6} {'CONF':>6} {'ECON':>6} "
          f"{'SPREAD':>6} {'AVAIL':>6} {'root':>5} {'comm$':>8} {'iso(tp/fp)':>12}")
    print("-" * 92)
    for cond_name in [c[0] for c in CONDITIONS]:
        rs = by_cond.get(cond_name, [])
        if not rs:
            print(f"{cond_name:<22} (no successful runs)")
            continue
        iso_tp = _mean(cond_name, "isolations_tp")
        iso_fp = _mean(cond_name, "isolations_fp")
        print(
            f"{cond_name:<22} "
            f"{_mean(cond_name, 'csri'):>6.3f} "
            f"{_mean(cond_name, 'conf_loss'):>6.2f} "
            f"{_mean(cond_name, 'econ_loss'):>6.2f} "
            f"{_mean(cond_name, 'spread_loss'):>6.2f} "
            f"{_mean(cond_name, 'avail_loss'):>6.2f} "
            f"{_mean(cond_name, 'attacker_root_actions'):>5.0f} "
            f"{_mean(cond_name, 'community_balance'):>8.0f} "
            f"{iso_tp:>3.0f}/{iso_fp:<.0f}"
        )

    clean_csri = _mean("clean_community", "csri")
    attacker_csri = _mean("attacker_only", "csri")
    defended_csri = _mean("attack_defended", "csri")
    sec_only_csri = _mean("security_only", "csri")
    sec_only_iso_fp = _mean("security_only", "isolations_fp")
    defended_iso_tp = _mean("attack_defended", "isolations_tp")
    attacker_root = _mean("attacker_only", "attacker_root_actions")
    defended_iso_target_victor = _mean("attack_defended", "iso_target_victor")

    # ---------------------------------------------------------------
    # GATE 0 — attacker-acted precondition (principle.md §3.4).
    # If the attacker model never wrote a single root action in the
    # attacker_only cell, no downstream security number can be
    # trusted. This is INCONCLUSIVE, not PASS and not a silent FAIL:
    # the harness ran, but the experiment didn't happen.
    # ---------------------------------------------------------------
    print()
    print("=== GATE 0 — attacker-acted precondition ===")
    attacker_present_cell = "attacker_only" in by_cond
    if attacker_present_cell and attacker_root < 1.0:
        print(f"  [INCONCLUSIVE] attacker_only root actions="
              f"{attacker_root:.1f} < 1 — the attacker LLM never acted; "
              f"downstream gates are not evaluable on this run.")
        print()
        print("FRAMEWORK STATUS: INCONCLUSIVE (attacker did not act)")
        return 3
    print(f"  [OK] attacker_only root actions={attacker_root:.1f} ≥ 1"
          if attacker_present_cell else
          "  [SKIP] no attacker cell in this CELLS subset")

    # Framework-health checks — CSRI (composite damage index) is the
    # headline because it's staffing-invariant. Community balance is
    # reported but not used as the gate (it's salary-biased when a
    # factor adds/removes an agent).
    print()
    print("=== FRAMEWORK HEALTH CHECKS (CSRI-based) ===")
    checks = []
    checks.append((
        "C1. attacker causes measurable damage",
        f"attacker_only CSRI={attacker_csri:.3f} > clean CSRI={clean_csri:.3f} "
        f"AND root actions={attacker_root:.1f} ≥ 1",
        attacker_csri > clean_csri and attacker_root >= 1.0,
    ))
    checks.append((
        "C2. security recovers damage",
        f"attack_defended CSRI={defended_csri:.3f} < attacker_only CSRI={attacker_csri:.3f}",
        defended_csri < attacker_csri,
    ))
    checks.append((
        "C3. security has bounded false-positive overhead",
        f"security_only fp-isolations={sec_only_iso_fp:.1f} (target ≤1); "
        f"|CSRI − clean|={abs(sec_only_csri - clean_csri):.3f} (≤0.1); "
        f"clean CSRI={clean_csri:.3f} (≤0.05)",
        sec_only_iso_fp <= 1
        and abs(sec_only_csri - clean_csri) <= 0.1
        and clean_csri <= 0.05,
    ))
    checks.append((
        "C4. sheriff catches the right agent (it_victor, true-positive)",
        f"attack_defended tp-isolations={defended_iso_tp:.1f} (≥1) AND "
        f"isolations targeting it_victor (tp)={defended_iso_target_victor:.1f} (≥1)",
        defended_iso_tp >= 1 and defended_iso_target_victor >= 1,
    ))
    for label, detail, ok in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}  — {detail}")

    all_ok = all(ok for _, _, ok in checks)
    print()
    # This is a SMOKE test (n=1 by default, first frozen seed); a green run
    # is a sanity signal, not a finding (principle.md §4).
    print(f"NOTE: SEEDS={seeds} is a SMOKE test (n={len(seeds)}); "
          f"not a statistical result.")
    print("FRAMEWORK STATUS:", "HEALTHY" if all_ok else "NEEDS INVESTIGATION")
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
