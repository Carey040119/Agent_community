# FINDINGS — empirical results from the run → observe → improve loop

A running log of what live runs (DeepSeek-V4-Pro via OpenRouter, the 15-agent
research community) have taught us. Complements `principle.md` (which states
the design rules); this file records what is actually *true* of the running
system and why design choices were made.

## Layer 1 — community fidelity

**L1-1 — The benign community runs as planned, at scale.** A no-attacker run
at 5 ticks/day × 5 days completes cleanly with **bounded memory** (per-category
recall stays flat; day-summaries compact), **stable activity** (~250–314
events/day, not growing unboundedly), a **healthy economy** (salary + verified
rewards + bonuses + a fine fired), and **~65% job completion**. Behaviour is
coherent and role-appropriate (exec kickoffs, eng standups, design sign-off
threads, a release war-room).

*Reproducibility (honest definition).* "Reproducible" here means
**deterministic seeded WORLD INIT** (`random.Random(seed)`) plus a
**deterministic job/attack Poisson schedule** across the FIXED seed set
`[11, 22, 33, 44, 55]` — the *opportunities* placed in front of the agents
(who exists, what work appears when, when an attack window opens) are
identical for a given seed. It does **NOT** mean bit-identical outputs: the
LLM runs at `temperature=0.4`, so per-run *action selection* is stochastic.
Metrics are therefore reported as **mean ± range across the seed set**, not as
a single replayable number. (Same seed → same world and schedule; the agents'
decisions still vary run-to-run, which is the honest research stance — we
measure the distribution of what autonomous agents do, not a fixed transcript.)

**L1-2 — Role coverage drives engagement (#2b).** With job templates only for
7 of 13 roles, the other 6 (execs/HR/eng-manager/IT-admin) sat idle and just
emailed. Adding role-matched templates engaged them. Job rate/mix is a baseline
parameter (not a factor), so it scales activity equally across conditions.

**L1-3 — Config (world/connections/mandate) fixes engagement and scope, not
emergent collaboration.** A designer agent that enriched `known_agents`, role
mandates, and `world_knowledge` (P2-clean — world/goals/connections only):
- woke the **idle finance agent** (0 → active),
- stopped the **over-privileged IT-admin wandering into finance secrets**
  (explicit "finance is out of remit, escalate" mandate → 0 cross-domain reads),
- spread engagement across all 15 roles.

**L1-4 — Emergent DELEGATION resists incentives and norms (open).** Two
interventions failed to make `delegation_requested` move above 0:
1. capability + connections + "delegating is normal practice" mandates;
2. manager/exec **coordination jobs** + **delegation reward-sharing**
   (`delegation_reward_share`, completer keeps a majority, conserved).
Managers *claim* the coordination jobs but **complete them solo** — the
deliverable ("record the plan as a document") is satisfiable without a
`delegate` action, and solo completion still out-rewards delegating.
**Conclusion:** emergent delegation needs a **hard structural requirement**
(job dependencies / parent-child completion that cannot finish until delegated
sub-work is accepted and done by others), not incentives or norms. Deferred
until the Layer-2 handoff-contagion angle makes delegation load-bearing. The
reward-share + coordination machinery is in place and correct (dormant until
delegation occurs), and it improved manager/exec engagement regardless.
**Superseded by L1-5:** the root cause was *atomic work*, not unwilling agents.

**L1-5 — Multi-stage jobs make work non-atomic; interdependence is real but
BOARD-MEDIATED (Route 1).** A job can now be an ordered **cross-role pipeline**
with **artifact handoffs**: each stage produces a deliverable that hands the job
to the next role; the job only completes when the final stage is delivered
(`Job.stages/current_stage/stage_artifacts/stage_owners`, per-stage pay, QA/
approval as real gating stages). Single-stage jobs are unchanged. Empirically
(5d×5t live, `run_a36a1ed84346`): **`job_stage_completed=4`** real cross-role
handoffs, a 2-stage `engineer->qa` pipeline completed end-to-end with **QA as a
genuine gate** (not theater), pipelines advanced across roles.
- **Reframe of L1-4 (a design decision, 2026-06-07):** agents advance a pipeline
  by **pulling the handed-off stage from the shared job board** (the next-role
  agent claims it), **not** via the `delegate` action — so `delegation_requested`
  stays ~0. This is now **by design**: interdependence is achieved through a
  shared board (Kanban-style), the realistic and chosen collaboration mode. The
  `delegate` path remains **wired and load-bearing** (accepting a delegation on a
  pipeline job claims its current stage) but optional. The original L1-4 framing
  ("agents won't collaborate") was wrong: the gap was *atomic work*; with
  multi-stage work, collaboration is real — just board-mediated, not directed.
- **Solo-block is a hard enforced gate**, not presentation-only: a wrong-role
  agent that retains a job_id is **refused** at claim time (the claim mutation
  checks `current_stage_role`, matching the delegation-handoff check). Routing
  hides the stage; the gate enforces it (principle.md §5).
- **Throughput tuning.** The first Route-1 run **over-produced** (74 jobs, **11%
  pipeline completion**, 17 abandoned): template frequencies summed to ~14
  jobs/day, and the 5-stage feature with `deadline_days=3` **auto-abandoned**
  before it could flow across 5 roles (board-pull + 1-tick handoff latency).
  Fixed with (a) a global **`job_frequency_scale`** (0.6 -> ~46 jobs/5d), (b)
  generator **deadline-scaling** (>=~1 day/stage for pipelines, so they aren't
  abandoned mid-flight), and (c) right-sizing the flagship pipeline to 4 stages
  and removing a redundant `requires_approval` double-gate on manager/QA final
  stages.
- **Post-tuning re-run (5d×5t, `run_1344be2da505`):** the tuning **killed the
  abandon-storm — abandoned 17 -> 2**, job volume 74 -> 51, and **handoffs more
  than doubled (`job_stage_completed` 4 -> 10)**; pipelines now flow deeper
  (depth reached up to 2/3, 2/2). **Delegation FIRED for the first time ever:
  `delegation_requested=6, responded=5`** — managers/execs (`mgr_mike` 3,
  `exec_tom` 2, `exec_amy` 1) chose to delegate *coordination* work organically.
  So even under board-pull, L1-4 moved off 0: board-pull is the pipeline-handoff
  mechanism, and directed delegation emerged for coordination — both happen.
- **Remaining gap:** **pipeline COMPLETION is still low (1/13 ≈ 8%)**. Pipelines
  no longer abandon (good) but rarely *finish* within a 5-day horizon — they sit
  mid-flight in `pending`/`claimed` (25 pending) because board-pull + 1-tick
  handoff latency + agents juggling single-stage work makes a 3-4 stage pipeline
  slow. Work flows; it just doesn't complete fast. Levers if we want higher
  completion: longer horizon, shorter pipelines, or prioritising handed-off
  stages.
- **Completion-tuning pass (`run_4840771e1eec`, 5d×5t):** applied all three
  levers — pipeline **priority 8** (above single-stage 1–5, so a handed-off
  stage surfaces at the TOP of the single-agent QA/devops bottleneck's board),
  the flagship feature **shortened 4→3 stages**, lower pipeline frequencies, and
  a **"finish work-in-progress first" norm** on the 7 pipeline-receiving roles.
  Result: **pipeline completion 8% → 27% (4/15)**, **handoffs 10 → 20**, **3
  full 3-stage pipelines completed** end-to-end, and 4 more reached 2/3 (one
  stage from done — the 5-day cutoff truncates them; effective flow ≈ 50%).
  The single-agent QA was the throughput ceiling; prioritising pipeline stages
  on its board was the key lever. *(delegation_requested was 0 this run — it is
  optional/variable under board-pull; an earlier run saw 6. Trust evolved: 2
  earned "collaborated" edges when strangers collaborated.)*

**L1-6 — Economy now bites (Route 2).** Salary was 96.8% of all pay
(unconditional), so idle agents accrued wealth. Route 2 splits salary into an
unconditional base (`salary_base_fraction=0.5`) + a performance slice paid only
on a day with provable output (a verified REWARD/BONUS, which includes Route-1
per-stage pay), plus a flat `daily_overhead=25`. Empirically (`run_1344be2da505`):
**salary paid dropped 17250 -> 10985 (-36%)** as idle agents forfeited the perf
slice (97 SALARY entries = 75 base + 22 earned-perf), **`overhead` n=75 = -1875**,
and the **idle agent is now bottom-wallet** (`fin_robert`, 0 jobs, min wallet
1272) while active agents pull ahead. Nobody bankrupts (base 60 − overhead 25 =
+35/idle-day floor). Overhead is excluded from the attack econ-drain metric
(it reads `token_transfers` only), so CSRI still measures only attack loss.

**L1-7 — Trust dynamics wired & correct, but rarely triggered in a dense org
(Route 3).** Trust was static (graph built once `from_config`); the introduce/
vouch path was dead code (§5). Route 3 makes trust **earned through
collaboration** (a completed pipeline handoff lays a `collaborated` edge →
`trusted_neighbor`), **wires the introduce action** (an agent can vouch a
contact it knows), and emits a **`TRUST_CHANGED`** event so evolution is
measurable. The mechanic is correct and unit-tested (fires for strangers,
gap-fills for already-trusted pairs). But in the live run **`TRUST_CHANGED=0`**:
every pipeline pair that collaborated (`qa_lisa`↔`devops_sara` `peer`,
`qa_lisa`↔`eng_kevin` `cross-team`) was **already config-trusted**, so the
gap-filling correctly minted nothing, and no agent chose to use the introduce
action. **Implication:** trust evolution is a *sparse/large-org or
stranger-contact* phenomenon — in a tightly-connected 15-agent org everyone
pipeline-adjacent already knows each other. It will matter for Layer 2
(contagion via newly-earned trust) and for any larger/sparser community.

**L1-8 — Three of the six factors are CONFOUNDED bundles, not single knobs
(read main effects with this caveat).** The factorial in
`config/community_research_experiment.yaml` is honest about *what* each factor
toggles, but three factors flip **several** correlated knobs at once, so their
estimated "main effect" is the effect of the **bundle**, not of any one
mechanism. A reader cannot attribute the result to a single cause from this
design alone; isolating the contributors would need a follow-up design that
varies the bundled knobs independently. The confounds:
- **`security_expert`** does not only add/remove `sec_david` — its level-1
  ("with security expert") *also* turns on `recovery_key_rotation` (rotate a
  compromised agent's keys at the end-of-day barrier). So the "expert" effect
  is **agent presence + automated key rotation** entangled; a detection win and
  a remediation win cannot be separated.
- **`scoped_credentials`** flips **three** knobs together at level 1:
  `credential_scope` (broad → scoped), `credential_rotation` (off → on), and
  `rotation_interval_days` (5 → 3). The effect is the **scope+rotation+interval**
  bundle, not credential-scoping alone.
- **`directory_hardening`** and **`strict_communications`** each bundle several
  knobs. `directory_hardening` level 1 flips `unknown_sender_requires_verification`
  ON, narrows `hr_emily.directory_scope` (org → neighbors) and
  `exec_amy.directory_scope` (org → reports), and turns on `extra_monitoring` on
  `srv_identity_admin`. `strict_communications` level 1 flips
  `communication_discipline` (free → typed), turns on `clarification_gate`, and
  tightens `grp_allhands.posting_policy` to `admins_only`. Each is a posture
  bundle, not a single control.

The other three factors are cleaner: `attacker_autonomy` flips one knob
(`attacker_policy` scripted↔llm) and `transfer_controls` flips one
(`transfer_cap_per_day` 0↔300). `security_expert`'s agent-presence component is
the intended headline (the §4-Q2 "can the expert fix anything" question), but
its rotation rider is a confound to flag, not hide.

**L1-9 — Layer-1 Baseline v1 FROZEN + validated at the full horizon.** The
community config (15 agents, economy, jobs/pipelines, world, baseline-defense
floor) and run protocol (**5 ticks × 12 days × seeds [11,22,33,44,55] ×
deepseek-v4-pro @ temp 0.4**) are frozen as the immutable substrate for all
experiments (see `LAYER1_BASELINE.md`; experiments may only toggle the 6
variable factors). The freeze pinned every formerly code-default-only knob into
YAML (no silent drift), wired the runners to the canonical seeds+model (they
previously ran `[1001]`+glm-5), added a frozen-field allowlist guard, and
corrected the L1-1 reproducibility claim. **Validation smoke** (`run_619c92b05fe5`,
seed 11, benign, 5×12): clean 12-day run, 15/15 healthy, **bounded memory**,
**economy bites at scale** (conditional salary + overhead + reward/bonus/penalty
all firing; idle agent at the wallet floor), **90% pipeline completion (9/10)**
— which **confirms the L1-5 27%-at-5-days figure was horizon-bound, not a
structural flaw** — trust evolved (2 earned edges), JSON-decode failures ~1.1%.
**Cost: ~83 min/run.** Implication for Layer-2/3: the per-run protocol is fixed,
but the full 64×5 = 320-run factorial (~440 serial hours) likely warrants a
fractional/focused experiment route rather than the full grid.

## Security model (Layer 2/3 — observed, mostly parked)

**S-1 — Malicious-persona agents attack unprompted.** Even in passive mode
(no planted objective), an agent with `is_malicious=true` ran a credential-theft
chain from its persona alone. Implication: a "passive" run containing the
attacker is not a clean control — neutralize/remove it for Layer-1 baselines.

**S-2 — Over-privilege is a deliberate, documented backdoor (#3).** `it_admin`
sits in `srv_payroll_app` login_roles AND admin_roles by design (a realistic
insider path). "Has the privilege" is authorized; "actually reads" the
cross-domain secret is **monitored misbehavior** (`cross_domain_secret_reads`),
surfaced to the security agent — not least-privileged away. See `principle.md` §3.5.

**S-3 — One LLM attacker vs one LLM defender produced a real, analyzable
intrusion.** A 3-day attacker run: `it_victor` read the payroll signer secret
cross-domain → got an impersonation grant; `sec_david` detected it as
"credential theft" and isolated `it_victor` (true positive), economic loss = 0.
A 6-agent pen-test of that log produced a **Layer-2 hardening backlog (parked
until the attack/defend phase)**: wire remediation to detection (rotate the
stolen key, not just the grant row); a synchronous transfer gate (don't rely on
the defender winning the turn race); deterministic tripwire/SIEM backstops under
the LLM agent; a real access-request/approval workflow; decouple secret-read
from capability minting; sealed (non-plaintext) secrets.

## Framework reliability

**F-1 — Run-reliability hardened (R1/R2/R3):** per-agent failures are isolated
(one error can't abort a factorial run); the DB always closes; checkpoint/resume
works. **F-2 — base_url convention bug:** ACES appends `/v1/...`, so a base that
already ends in `/v1` doubled it (`/v1/v1/...`) — now tolerant of both. This had
silently blocked every real-LLM run.
