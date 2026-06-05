# principle.md — Design Principles & Goals for ACES

> **ACES** = *Agent Community Enterprise Simulator.* This file is the north star for
> heavy development. It states **what the repo is, what it must never become, and the
> rules every change (human- or agent-authored) is held to.** When a design choice is
> ambiguous, this document decides. When code and this document disagree, that is a
> bug in one of them — fix it, don't ignore it.

---

## 0. What this is (and is not)

ACES is **a research space, not a product.** Its job is to be a faithful, long-running
simulation of a **real-world multi-agent community** — a population of long-horizon LLM
agents (each running on a real agent runtime such as **OpenClaw**) that hold jobs, spend
and earn a token economy, talk to each other, trust or distrust each other, and persist
across a long simulated horizon. On top of that living community we **replay published
attacks** and **measure what actually happens** to the community's security.

The deliverable is not a feature; it is **trustworthy evidence** about the security
dynamics of autonomous agent communities. Everything below exists to protect the
trustworthiness of that evidence.

**"Solid, not a toy"** is the bar. A toy hardcodes outcomes, scripts the agents' minds,
mocks the infrastructure, and reports numbers that move for reasons unrelated to the
phenomenon under study. ACES does the opposite (see §6 for the acceptance bars).

Audience: every contributor, and every AI coding agent working in this repo.

---

## 1. The spine — non-negotiable principles

These override convenience, override "it passes the test," and override a tempting result.

### P1 — Community realism first; attacks are infrastructure, not the focus
The community (Layer 1) is the product. Attacks (Layer 2) and analysis (Layer 3) are
instruments pointed *at* a realistic community. Never degrade community fidelity to make
an attack land or a metric move. A result obtained on an unrealistic community is not a
result. *(Standing guidance: build the realistic simulator first.)*

### P2 — Never puppet the agent
We shape the **world**, never the **mind**. It is legitimate to sharpen an agent's
goals, tools, available resources, environment, and the *opportunities* placed in front
of it. It is **forbidden** to plant fake first-person reasoning, scripted "decisions," or
ghost-written intentions into an agent and then attribute the behavior to the LLM. The
research claim "LLM agents do X on their own" is only honest if the LLM actually decided.
This is already encoded: `attacker_policy=llm` *plants an opportunity in the attacker's
`attack_objective` memory and lets the agent's own LLM decide* whether, how, and when to
act (`aces/attacks.py::_plant_opportunity`). The scripted path exists **only** as a
labeled capability baseline, never as the headline.

### P3 — Honest framework
- **No mocks on a production path.** Real runtime, real services, real persistence. Test
  doubles live in `tests/` (e.g. `StubRuntime`) and never leak into `aces/`.
- **Every metric must track a real state delta.** A number that cannot move because the
  state it reads is never written is a lie, not a metric. Every research *factor* must
  produce an observable change in world state, and there must be a regression test that
  proves it (cf. `test_every_research_factor_has_a_real_state_delta`).
- **Validate the validator.** Any gate that decides "the framework is healthy / the
  result counts" must itself be checked against the config it runs under. A health gate
  that trusts a metric which is structurally pinned to zero is worse than no gate.
- **Never fabricate or hardcode an outcome.** No result may depend on a constant standing
  in for a computation.

### P4 — Reproducibility and the long horizon
Runs are **seeded and replayable**: matched world init so conditions are paired across
seeds. The simulation must support **very long horizons** — which is only possible if
memory is compacted across days (§2.6) and per-tick cost is bounded (§2.5). Durability
features (checkpoint/resume) must actually be wired end-to-end or be removed; a
write-only durability feature is a trap.

### P5 — Layered solidity, bottom-up
The three layers are a dependency order, not a menu. **You may not buy a Layer-3 finding
with a Layer-1 shortcut.** If Layer 1 is not faithful, Layer 2 attacks are theater and
Layer 3 conclusions are unfounded. Strengthen the lowest unsound layer first.

---

## 2. Layer 1 — Community design (the foundation)

A persistent micro-society of role-specialized agents. The goal is that an agent's day
*feels like a job*: it has work, costs, peers, a reputation, and incomplete information.

### 2.1 The agent
Each agent has: a **role/job**, a **workspace** (its own state dir, OpenClaw-isolated), a
set of **skills**, a scoped set of **tools and resources**, **connections** (who it knows),
a **wallet**, a **memory**, and a **status** (`HEALTHY / COMPROMISED / QUARANTINED`).
Authority is role-bound and explicit — an agent can only do what its role, tools, and
zone permit.

### 2.2 Micro-economy — token is both cost and currency
Tokens are the lifeblood. An agent **spends** tokens to think and act, and **earns** a
token budget — its *money* — as **salary paid on provable outcomes** plus task bonuses
(`SALARY`/`REWARD`/`BONUS` ledger entries, `aces/metrics.py`). "Provable" is the key
word: pay follows demonstrable completion, not claimed effort. This makes
**economic exhaustion a first-class attack surface** — token-drain and distraction are
measurable losses in the same currency the community lives on. The wallet and the ledger
must always agree; balance is mutated through one path so the audit trail can never
silently diverge from the headline economic metric.

### 2.3 Discovery and contact
An agent starts knowing **only a neighborhood** (`AgentDef.known_agents` + reporting
edges). Beyond that it must *discover* others. Two channels, like real people:
- **Email** — direct, but only if you **know the address** (the directory / a referral).
- **Web forum (Moltbook)** — public, broadcast, discoverable; how strangers find each
  other and how ideas (and poison) spread to people you never met.

Reaching beyond your neighborhood is the engine of both collaboration and contagion.

### 2.4 Trust boundaries
Because this is a **security** testbed, *whom to trust* is a decision the agent must make,
not a fact the engine grants. Trust is graded, not binary: `SocialTrustGraph` exposes
`trusted_neighbor | group_known | introduced | unknown` (`aces/network.py`). The engine's
job is to **surface the trust signal** (who is this sender to me?) and let the agent
reason about it — never to decide trust on the agent's behalf (see P2). New trust is
*earned* (introductions/vouching), never injected.

### 2.5 Time — days and ticks
- A run is a sequence of **days**; each day is a sequence of **ticks**.
- **Per day:** an agent receives/refreshes goals, works, and is paid on provable outcomes
  at end-of-day settlement.
- **Per tick:** the agent's resource consumption is **bounded** (`tick_budget_*` surfaced
  in the observation) so no single agent can run away with the world, and so token-drain
  is contained and measurable.
- **One tick of latency for every cross-agent interaction.** Email and other
  agent-to-agent effects take **a tick to deliver**. This is the **race-protection
  invariant**: within a tick all agents observe a consistent snapshot and act; effects
  land next tick. It removes intra-tick ordering races and makes propagation speed an
  observable, comparable quantity. *(Realized: mail, group mail, delegation, and forum
  posts/comments are all stamped with their send tick and gated so a recipient sees them
  only on a strictly later tick — `Database.get_unread_messages`/`get_pending_delegations`
  and `MoltbookService._delivered`. Delegation-reply visibility is the one remaining edge.)*

### 2.6 Memory — coherent within a day, compact across days
- **Within a day:** memory is consistent and accumulating (`MemoryEntry`, categorized as
  `contacts | work | knowledge | observations`, plus `attack_objective` for seeded
  opportunities).
- **Across days:** memory is **compacted** so the horizon can be very long — full history
  persists in the store, but each new observation pulls a **bounded, per-category** slice
  plus rolling **day summaries** (`day_summaries`, `DAY_SUMMARY_WRITTEN`,
  `get_agent_memory(..., limit=…)`). Long-run cost stays flat; salient state survives.
- Compaction must be **lossy-but-honest**: it may forget detail, never invent it.

---

## 3. Layer 2 — Attack & defend

### 3.1 Paper-grounded, replayable
Attacks are not invented for convenience. We **gather published agent-community attacks
that ship with code** — e.g. **ClawWorm: Self-Propagating Attacks Across LLM Agent
Ecosystems** and the broader self-propagating / infectious-prompt literature — **replay**
them inside ACES, and **evaluate** them on the live community. Each attack template
carries its **provenance** (paper, threat class, entry point) so a result is traceable to
a real, citable mechanism.

### 3.2 Agent-to-agent infection is first-class
The central Layer-2 phenomenon is **contagion**: a compromise in one agent propagating to
others through the *normal* community channels (mail, forum, delegation, shared docs,
poisoned skills/memory). The simulator must make propagation **observable and
quantifiable** — who infected whom, how fast (in ticks), how far (blast radius).

### 3.3 Attacks and defenses are realized, not asserted (P2 again)
- An attack's damage must come from **actions actually taken** — by a scripted handler
  (labeled baseline) or, for the headline claim, by the **attacker agent's own LLM**
  acting on a planted opportunity. A "successful attack" with no corresponding action and
  no state change is not success; it is a measurement bug.
- Defenses are **architectural/policy controls** (segmentation, scoped/rotatable
  credentials, communication discipline, spend caps, quarantine, trust decay, anomaly
  detection) **and** an **agent** — a security-expert agent that reads real evidence and
  reasons (it is not handed ground truth). Whether that agent can *actually* fix things is
  a Layer-3 question (§4), so the defense must be a genuine capability, not a scripted win.

### 3.4 No confounds
A defense that "works" because the attacker model refused to attack, or because the metric
can't move, has proven nothing. Every attack run must **assert the attacker actually
acted** before its security numbers are allowed to count.

---

## 4. Layer 3 — Survey & research

The reason the first two layers must be solid. ACES exists to answer, with evidence:

1. **What is the real devastation in an agent community?**
   - Can an attacker **halt the organization** (collapse throughput, drain wallets to
     insolvency)?
   - Can an attacker **sell poisoned skills/tools** to others and have them adopted?
   - How do we **watch, categorize, and quantify** the emerging security issues — a
     taxonomy and metrics for harm (confidentiality loss, availability loss, economic
     drain, blast radius, time-to-detect, time-to-recover, propagation rate)?
2. **Can a security-expert agent in the system actually fix something?** Detection,
   isolation, recovery — measured against a matched no-expert control, with the expert
   reasoning from real evidence (P2).
3. **Homogeneous vs. heterogeneous intelligence — is the system always skewed toward the
   attacker?** Attackers gather information and find weaknesses *first*; defenders react.
   Does an intelligence advantage (or parity) for defenders close the gap, or is the
   asymmetry structural? This frames the **open question: autonomous agent communities
   need a more advanced security harness** than today's reactive controls.

### Research integrity (Layer-3 specific)
- **Metrics must move under the shipped config.** Before any comparison is reported,
  confirm each reported metric is *capable of moving* under the exact `attacker_policy`,
  weights, and defaults the run uses. A headline index that collapses to "job-completion
  noise" under the default mode is not measuring attack damage — fix the metric or change
  the default, do not report it.
- **Honest statistics.** Multiple seeds (a single-seed run is a *smoke test*, not an
  experiment), report variance / CIs, control multiple comparisons. Binary PASS/FAIL from
  n=1 is not a finding.
- **Pre-register what each metric means** and keep the docstring, the config default, and
  the computation in agreement.

---

## 5. Engineering principles for heavy development

These are how the spine (§1) is kept true as the code grows. The review that motivated
this file found each of these violated somewhere; treat violations as integrity bugs.

- **Single source of truth.** The action vocabulary (parser ⇄ prompt footer ⇄ role tools
  ⇄ engine dispatch), the wallet balance (column ⇄ ledger), and config knobs each get
  *one* authoritative definition that everything else is derived from. Hand-synced
  parallel copies drift, and drift in a research instrument is silent data corruption.
- **No misleading surface.** In a security simulator, code that *looks* load-bearing but
  enforces nothing (e.g. a defined-but-unwired authorization layer) actively misleads
  anyone auditing "who can do what." Dead/unenforced code is a research-integrity bug, not
  mere clutter: **wire it or delete it.** Distinguish *intentional staging* (a coherent,
  documented, half-wired feature) from *cruft* (orphaned duplicates) — stage explicitly,
  remove the rest.
- **Respect the persistence boundary.** The database layer owns schema knowledge. Engine
  and metrics call typed methods; they do not hand-write SQL against physical column
  names. Cleanup/reset is total, owned, and never swallows errors.
- **Validate config at the edge.** Bad enum/role/zone values fail at load with the
  offending entity named — never deep inside `init_world` with a context-free stack trace.
  Unknown keys warn consistently.
- **Concurrency safety is explicit.** Serialize mutations, never block the event loop
  inside the apply lock, reap subprocesses, and ensure one agent's failure cannot abort an
  entire multi-day run (`gather(..., return_exceptions=True)`; resources closed in
  `finally`).
- **Backends must be comparable.** If two runtimes (direct-LLM vs. OpenClaw) can be
  compared, they must expose the *same* capabilities and prompts; a silent asymmetry
  between backends confounds every cross-backend result.
- **Test honesty.** Every research factor has a real-state-delta regression test; tests
  use the stub runtime and never reach a live API; docs point at the *actual* edit points.

---

## 6. "Solid, not a toy" — acceptance bars

A change is ready when:

1. **No puppeting** — no first-person reasoning or decisions were planted into any agent.
2. **No mock on a production path** — doubles confined to `tests/`.
3. **Every new metric/factor moves a real, asserted state delta** — proven by a test.
4. **Every new metric can move under the default shipped config** — verified, not assumed.
5. **One source of truth** — no new hand-synced parallel copy of the action schema, the
   balance, or a config knob.
6. **No new misleading surface** — new code is wired and enforced, or it isn't merged.
7. **Reproducible** — seeded; long-horizon-safe (bounded per-tick cost, compacted memory).
8. **Attacks are citable** — every attack template carries its paper/threat-class
   provenance.
9. **Statistics are honest** — multi-seed with variance for anything reported as a result.

---

## 7. Where the principles live in the code (pointers)

| Concern | Module(s) |
|---|---|
| Day/tick loop, barrier, per-tick budget | `aces/engine.py` (`run_async`), `tick_budget_*` |
| Agent / memory / action model | `aces/models.py` (`AgentState`, `MemoryEntry`, `Action` subclasses) |
| Trust graph & zones | `aces/network.py` (`SocialTrustGraph`, `AccessControl`) |
| Services: mail, forum, vault, tokens | `aces/services.py`, `aces/moltbook.py`, `aces/webhost.py` |
| Key-gated authorization (request→grant / steal / revoke) | `aces/services.py` (`KeyService`), `AccessGrant` |
| Skills marketplace (publish / adopt / poison / propagate) | `aces/services.py` (`SkillService`), `Skill`, `<workspace>/skills/SKILL.md` |
| Attack injector & policies (`llm`/`scripted`/`passive`) | `aces/attacks.py` |
| Defenses & detection | `aces/defenses.py` |
| Role behavior (goals/priorities, no puppeting) | `aces/playbooks.py`, `aces/prompting.py` |
| Runtimes (strategy: LLM / OpenClaw / Stub) | `aces/runtime.py`, `aces/openclaw_runtime.py` |
| Metrics & CSRI | `aces/metrics.py` |
| Persistence (sole boundary) | `aces/database.py` |
| Experiment / factorial design | `aces/experiment.py`, `config/*.yaml`, `scripts/` |

When you extend ACES, start here, and keep this file true.
