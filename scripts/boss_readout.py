"""Standalone readout for the ext-BOSS variant.

The PBS files' inline readout glob'd the wrong pattern on the first
run (``mandate_ab_on_ext_*`` instead of ``mandate_ab_on_boss_*``), so
the aggregated tables printed empty. This script reads the already-
written JSONs under ``results/mandate_boss_qwen3`` and ``results/
mandate_boss_qwen25`` and prints the correct aggregated table — no
re-sim needed.

Also prints:
  * CEO-autonomy-specific columns (ceo_accepted / ceo_propagated /
    ceo_escalated_to_security / ceo_response_text samples)
  * standard sweep columns (cov_all / depth / hops / reject / sit)
  * malicious rejection-reason samples captured from the fixed
    DELEGATION_RESPONDED event payload
"""
# ruff: noqa: E402

from __future__ import annotations

import glob
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _mean(xs, default=0.0):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else default


def _rate(xs, truthy=lambda x: bool(x)):
    xs = [x for x in xs if x is not None]
    return (sum(1 for x in xs if truthy(x)) / len(xs)) if xs else 0.0


def main() -> None:
    search_dirs = [
        # S0 (default tier, no suffix)
        "results/mandate_boss_qwen3",
        "results/mandate_boss_qwen25",
        # S1 and S2
        "results/mandate_boss_qwen3_s1",
        "results/mandate_boss_qwen25_s1",
        "results/mandate_boss_qwen3_s2",
        "results/mandate_boss_qwen25_s2",
        # Trojan BOSS variant
        "results/mandate_trojan_boss_qwen3",
        "results/mandate_trojan_boss_qwen25",
        "results/mandate_trojan_boss_qwen3_s1",
        "results/mandate_trojan_boss_qwen25_s1",
        "results/mandate_trojan_boss_qwen3_s2",
        "results/mandate_trojan_boss_qwen25_s2",
        # Trojan-B / Trojan-C generalization: BOSS × S2 only
        "results/mandate_trojan_b_boss_qwen3_s2",
        "results/mandate_trojan_b_boss_qwen25_s2",
        "results/mandate_trojan_c_boss_qwen3_s2",
        "results/mandate_trojan_c_boss_qwen25_s2",
        # Ablation: scaffold off, BOSS × S2
        "results/mandate_trojan_a_ablation_boss_qwen3_s2",
        "results/mandate_trojan_a_ablation_boss_qwen25_s2",
        "results/mandate_benign_ablation_boss_qwen3_s2",
        "results/mandate_benign_ablation_boss_qwen25_s2",
        # Trojan-A-HIJACK ablation (scaffold off, attacker-side workaround)
        # BOSS × S0/S1/S2 × 2 model
        "results/mandate_trojan_hijack_ablation_boss_qwen3",
        "results/mandate_trojan_hijack_ablation_boss_qwen25",
        "results/mandate_trojan_hijack_ablation_boss_qwen3_s1",
        "results/mandate_trojan_hijack_ablation_boss_qwen25_s1",
        "results/mandate_trojan_hijack_ablation_boss_qwen3_s2",
        "results/mandate_trojan_hijack_ablation_boss_qwen25_s2",
        # Trojan-A-HIJACK-V2 ablation (scaffold off, payload in
        # origin_description — survives CEO paraphrase)
        "results/mandate_trojan_hijack_v2_ablation_boss_qwen3",
        "results/mandate_trojan_hijack_v2_ablation_boss_qwen25",
        "results/mandate_trojan_hijack_v2_ablation_boss_qwen3_s1",
        "results/mandate_trojan_hijack_v2_ablation_boss_qwen25_s1",
        "results/mandate_trojan_hijack_v2_ablation_boss_qwen3_s2",
        "results/mandate_trojan_hijack_v2_ablation_boss_qwen25_s2",
    ]
    rows_by_key = defaultdict(list)
    for d in search_dirs:
        for p in sorted(glob.glob(f"{d}/mandate_ab_on_boss_*_s*.json")):
            r = json.load(open(p))
            model = "qwen3" if "qwen3" in d else "qwen25"
            tier = ("S2" if "_s2" in d else
                     "S1" if "_s1" in d else "S0")
            # Distinguish scaffold-off ablation rows from the main
            # BOSS × S2 baseline so comparison is one glance away.
            if "_ablation_" in d:
                tier = f"{tier}A"
            key = (model, tier, r.get("flavor", "?"),
                    r.get("channel_mode", "?"))
            rows_by_key[key].append(r)

    if not rows_by_key:
        print("No matching JSON files found under results/mandate_boss_*")
        return

    # Table.
    print(f"{'model':6s} {'tier':4s} {'flavor':10s} {'channel':10s} "
          f"{'ceo_acc':>7s} {'ceo_prop':>8s} {'ceo_esc':>7s} "
          f"{'cov_all':>7s} {'cov_leaf':>8s} {'depth':>5s} {'hops':>5s} "
          f"{'jcr':>5s} {'sit':>5s} {'reject':>6s} {'secIso':>6s}")
    for key, rs in sorted(rows_by_key.items()):
        model, tier, flavor, channel = key
        print(f"{model:6s} {tier:4s} {flavor:10s} {channel:10s} "
              f"{_rate(r['ceo_accepted'] for r in rs):>7.2f} "
              f"{_rate(r['ceo_propagated'] for r in rs):>8.2f} "
              f"{_rate(r['ceo_escalated_to_security'] for r in rs):>7.2f} "
              f"{_mean(r['skill_coverage_all'] for r in rs):>7.2f} "
              f"{_mean(r['skill_coverage_leaves'] for r in rs):>8.2f} "
              f"{_mean(r['mandate_depth_max'] for r in rs):>5.1f} "
              f"{_mean(r['mandate_hops'] for r in rs):>5.0f} "
              f"{_mean(r['jcr'] for r in rs):>5.2f} "
              f"{_mean(r['accept_and_sit_rate'] for r in rs):>5.2f} "
              f"{_mean(r['rejected_delegation_count'] for r in rs):>6.1f} "
              f"{_mean(r['security_isolation_count'] for r in rs):>6.1f}")

    # CEO response text samples per flavor.
    print()
    print("=== CEO response text samples (one per flavor, where captured) ===")
    for target_flavor in ("benign", "risky", "malicious", "trojan",
                           "trojan_b", "trojan_c", "trojan_hijack",
                           "trojan_hijack_v2"):
        print(f"\n[{target_flavor}]")
        shown = 0
        for key, rs in sorted(rows_by_key.items()):
            if key[2] != target_flavor:
                continue
            for r in rs:
                t = r.get("ceo_response_text") or ""
                if t and shown < 6:
                    accepted = r.get("ceo_accepted")
                    mark = ("ACCEPT" if accepted is True
                            else "REJECT" if accepted is False
                            else "NO-RESP")
                    print(f"  [{mark}] {key[0]}/{key[1]}/{key[2]}/{key[3]} "
                          f":: {t[:300]}")
                    shown += 1
            if shown >= 6:
                break

    # Rejection reasons collected across flavors (new, now that the
    # engine's DELEGATION_RESPONDED event carries the response text).
    print()
    print("=== Rejection reasons from malicious / risky mandate delegations ===")
    for key, rs in sorted(rows_by_key.items()):
        if key[2] not in ("risky", "malicious", "trojan",
                           "trojan_b", "trojan_c", "trojan_hijack",
                           "trojan_hijack_v2"):
            continue
        for r in rs:
            for reason in (r.get("rejection_reasons") or [])[:2]:
                print(f"  [{key[0]}/{key[1]}/{key[2]}/{key[3]}] "
                      f"{reason[:200]}")


if __name__ == "__main__":
    main()
