# ACES Layer-2 — Novel Contagious Agent-Attack Methods (Comparison Set)

> **Status:** information deliverable — the *finer distill* of `LAYER2_ATTACK_SURVEY.md`. Not a build order, not code, nothing committed.
> Produced 2026-06-08.
> **Update 2026-06-08:** added two members after a targeted worms re-sweep — **ClawWorm** (arXiv 2603.15727, the `principle.md §3.1`-named flagship) and **Autonomous LLM Agent Worms** (arXiv 2605.02812), both missed in the first pass because the survey's dedicated "worms" sweep crashed (see `LAYER2_ATTACK_SURVEY.md §0`). The re-sweep itself was **tooling-degraded** (5/6 search angles + several screens failed to emit structured output); the two concrete gaps were closed by direct web verification. It correctly *excluded* Agent Smith, CODES, MemMorph, Zombie Agents, MedSentry (see §4). **Exhaustive coverage is not claimed** — only that the high-value space is now covered.

---

## 0. Method & provenance

This is the sharp filter the broad survey lacked. From the survey's contagion-flagged pool (16 candidates), each paper was re-screened (web-grounded) against a **strict three-part bar — all three must hold**:

- **(A) Novel attack METHOD** — the paper's *core contribution* is a new attack mechanism. Excludes measurement/field studies, SoKs/surveys, benchmarks, defense papers (even when an attack is harvested from them), and reframings of prior art.
- **(B) Paper-demonstrated agent-to-agent CONTAGION** — *the cited paper itself* shows a compromised agent making other agents compromised **and** propagating onward (self-replication / relay / cascade). Excludes one-to-many adoption fan-out of a static artifact, single-agent attacks, single-session orchestrator hijack, and contagion that only exists as ACES-side extrapolation.
- **(C) Benchmark-comparable** — realizable under `attacker_policy=llm` (planted opportunity, no scripting/puppeting), moves the CSRI **spread** channel, runnable in the shared frozen harness (`benchmark_now` or *minor* extension; major new substrate disqualifies).

**Result: 16 candidates → 3 pass; +2 worm papers added on review (ClawWorm, Autonomous LLM Agent Worms) → 5 members.** The decisive axis is **(B)** — sustained *secondary-infections-per-infected (R0 > 0)*, which most "contagion-capable" candidates fail (they fan a static artifact out, or stop at the first hop). Three of the five members ship runnable code; the two worm papers (2603.15727, 2605.02812) are pending coordinated disclosure.

---

## 1. The comparison set (INCLUDED)

Sorted by contagion strength + readiness (canonical self-replicators first, relay last).

| Paper (yr) | Novel mechanism (1 line) | contagion_type | attack_class / channel | CSRI: SPREAD + others | Realizability | Code | What makes it DISTINCT in the set |
|---|---|---|---|---|---|---|---|
| **★ Zhang, Wei et al., "ClawWorm" (2026)** — arXiv 2603.15727 | First self-replicating worm against a production-scale agent framework: a single message hijacks the victim's persistent config, executes a payload each reboot, then propagates to every newly-discovered peer with no further attacker action | self_replicating | skill-supply-chain + persistent-config / skill, mail, group_mail, memory | **SPREAD** (blast radius, hops, R0); confidentiality + availability (arbitrary payload) | **minor_extension** — maps to ACES's skill marketplace + messaging + persistent-memory/day-loop; realize the **LLM-decided slice only** (victim's LLM re-reads poisoned persistent state each "reboot" and re-decides to propagate — never a scripted self-copy) | **Pending** (responsible disclosure) | **The flagship** — named in `principle.md §3.1`; targets the *actual* OpenClaw runtime (not an analog). Strongest paper-backed contagion: sustained autonomous spread over **up to 5 hops**, 64.5% ASR / 1,800 trials. The persistence-across-reboots vector is unique to the set. |
| **Zha & Wang, "Autonomous LLM Agent Worms" (2026)** — arXiv 2605.02812 | Adversarial content written into persistent agent state re-enters the LLM's decision context via scheduled autoloading and drives high-risk actions; payload optimized (SRPO) to survive summarization/paraphrasing | self_replicating (persistence / re-entry) | file-backed persistent state + scheduled re-entry / memory, skill, mail, group_mail | **SPREAD** (3-hop cross-platform demonstrated, R0 > 1); confidentiality + privilege-escalation | **minor_extension** — maps almost 1:1 onto ACES's persistent memory + day-loop (re-entry = next-day observation); **already LLM-decision-driven** (victim reads injected state, chooses the action) — no de-scripting needed unlike ClawWorm. | **Pending** (coordinated disclosure) | The most **ACES-native** member: its "payload survives summarization" (SRPO) is a direct test of whether contagion survives ACES's §2.6 memory compaction — a question no other member poses. |
| **Lee & Tiwari, "Prompt Infection" (2024)** — arXiv 2410.07283 | Self-replicating infection prompt that copies itself LLM-to-LLM, accumulating loot in a shared `Data` field across hops | self_replicating | in-band prompt poisoning / mail, group_mail, delegation | **SPREAD** (blast radius, hops, ticks, R0); confidentiality (Data accumulator) | **benchmark_now** — plant self-replicating prompt in one attacker inbox/memory; its own LLM relays. No new substrate. | **Yes** | Purest self-replicator: payload literally rewrites and re-emits itself; logistic-growth curve shown at 10–50 agents. The canonical SPREAD baseline. |
| **Cohen, Bitton & Nassi, "Here Comes the AI Worm" / Morris-II (2024)** — arXiv 2403.02817 | Adversarial self-replicating prompt: infected GenAI app reproduces the prompt in its own output, poisoning the RAG of the next app | self_replicating | self-replicating prompt via RAG-relay / mail, group_mail; doc, memory | **SPREAD** (blast radius, hops); confidentiality (exfil), economic (spam/scam payloads) | **minor_extension** — runs on mail + doc/memory relay; add hop/generation-depth metric + surface a self-republish opportunity. | **Yes** | First zero-click GenAI worm; re-propagation rides retrieval (RAG/doc) rather than direct message text — tests the doc/memory relay vector specifically. |
| **Zhou et al., "CORBA" (2025)** — arXiv 2502.14529 | Contagious recursive **blocking** prompt that relays itself agent-to-agent while draining resources | relay_propagation | benign-looking instruction relay / mail, group_mail, delegation | **SPREAD** (P-ASR→blast radius, PTN→time-to-saturation); **availability** (recursive resource drain) | **minor_extension** — seed one blocking prompt; agents' own LLMs follow + relay. Add P-ASR-style infected-fraction + PTN-style saturation metric. | **Yes** (github.com/zhrli324/Corba) | The only **non-poisoning** / disruption-channel contagion in the set: spreads to deny availability rather than exfiltrate. 79–100% P-ASR, 1.6–1.9-turn peak across topologies. |

**Why each is a legitimately NOVEL method (not a reframing):**

- **ClawWorm (2603.15727)** — First documented *self-replicating worm against a production-scale agent framework* (OpenClaw, 40k+ instances). The novel contribution is the full autonomous infection cycle — persistent-config hijack + per-reboot payload + unattended peer-to-peer propagation — not a restatement of prompt-level worms. The companion defenses (privilege isolation, config-integrity, zero-trust execution) are secondary. **Realization caveat (P2):** only the LLM-decided propagation is legitimate in ACES; the mechanistic config-hijack/payload-self-copy must be modeled as poisoned persistent state the victim's own LLM re-encounters and re-decides on, never a scripted self-replicator.
- **Autonomous LLM Agent Worms (2605.02812)** — Novel attack-discovery/generation methodology (SSCGV source-graph analyzer + SRPO payload optimizer) for persistent, file-backed worms; demonstrates 3-hop cross-platform propagation that is explicitly **LLM-decision-driven** (the abstract's RTW-A defense is secondary). Distinct from ClawWorm: ClawWorm hijacks *config* for persistence, whereas this optimizes the *payload* to survive memory summarization/paraphrasing — i.e. it targets the memory-compaction-survival vector head-on. Because propagation is already the victim LLM's own decision, it needs **no de-scripting** to satisfy P2.
- **Prompt Infection (2410.07283)** — Invents the self-replicating infection prompt as the thesis (LLM Tagging defense is secondary). The cross-hop `Data` accumulator and population-scale logistic growth are original mechanisms, not a restatement of prior IPI.
- **Morris-II (2403.02817)** — Introduces the *adversarial self-replicating prompt*, the first zero-click worm for GenAI ecosystems; the self-reproduction-into-own-output mechanic is the novel contribution (Virtual Donkey guardrail is secondary).
- **CORBA (2502.14529)** — Fuses recursive resource-draining with contagious relay propagation in a single benign-looking blocking prompt; a genuinely new mechanism, not a survey/benchmark/defense.

---

## 2. Common comparison framework (SHARED spread metrics)

Every member is scored on the same axes so the benchmark yields method-vs-method numbers:

| Metric | Definition | Notes per member |
|---|---|---|
| **Blast radius** | Fraction / count of the 15 agents ever compromised | All five. ClawWorm 64.5% ASR; CORBA = P-ASR analogue (79–100%). |
| **Propagation depth (hops / generations)** | Max generation distance from patient-zero | All five. ClawWorm: up to **5 hops**; Autonomous Worms: **3-hop cross-platform**; Prompt Infection + Morris-II measure generation depth directly; CORBA shorter chains (topology-bounded). |
| **Time-to-first-infection (ticks)** | Ticks until 2nd agent is compromised | All five. |
| **Time-to-saturation** | Ticks until infected set stops growing | All five. CORBA = PTN analogue (1.6–1.9 turns to peak). |
| **Secondary-infections-per-infected (R0-like)** | Avg new infectees each infected agent produces | The decisive Bar-B axis: all five sustain R0 > 0 (each infectee re-emits). Excluded single-hop/single-target candidates fail here. |
| **Channel** | In-sim vector used | ClawWorm: skill-supply-chain + mail/group_mail + persistent memory. Autonomous Worms: file-backed persistent state + scheduled re-entry. Prompt Infection: mail/group_mail/delegation (message text). Morris-II: mail + doc/memory (retrieval relay). CORBA: mail/group_mail/delegation (instruction relay). |
| **Persistence** | Does the payload survive across ticks/sessions in an infectee | **The two worm papers are the persistence cases.** ClawWorm: persistence-across-reboots via config/skill hijack. Autonomous Worms: payload SRPO-optimized to **survive summarization/paraphrasing** (i.e. ACES memory compaction) and re-enter via scheduled autoload. Prompt Infection + Morris-II: payload self-carries forward in messages/docs. CORBA: stateless relay, no payload persistence. |

**Where members differ (so results stay interpretable):**

- **Mechanism class:** ClawWorm, Autonomous Worms, Prompt Infection & Morris-II are **self-replicating** (payload copies/re-emits); CORBA is **relay_propagation** (instruction is followed and re-issued, not byte-copied).
- **Channel emphasis:** ClawWorm is the **skill-supply-chain + persistent-config** member, Autonomous Worms the **file-backed-memory re-entry** member, Morris-II the **poisoning-via-retrieval** member (RAG/doc relay), Prompt Infection the **direct-message** relay — together they isolate which ACES channel carries contagion fastest.
- **Persistence axis:** the two worm papers persist across "reboots" (ACES days) by hijacking durable state — the others re-spread only while their carrier message/doc is live. **Autonomous Worms is the sharpest test** of whether contagion *survives memory compaction* (its SRPO payload is optimized for exactly that), with ClawWorm a config-hijack variant; this is a distinct question from raw spread speed.
- **CSRI target:** Prompt Infection & Morris-II are **poisoning / confidentiality-exfil** contagions, ClawWorm a poisoning contagion with an **arbitrary payload** (confidentiality + availability); CORBA is the lone **disruption / availability** contagion (recursive drain). Comparing them on the SAME spread axes shows whether availability-worms saturate faster than exfil-worms.

---

## 3. The natural baseline / anchor — Greshake

**Out of the head-to-head comparison set; in as the conceptual anchor.** Greshake et al. 2023 (*Not what you've signed up for*, arXiv 2302.12173) is the foundational indirect-prompt-injection paper and coined "worming" as a threat category — it **passes Bar A** (novel method) and **Bar C** (benchmark_now, no new substrate). It **fails Bar B**: the worming PoC is **single-hop** (a compromised agent forwards/composes a poisoned email), and recipient-agent re-infection + onward re-propagation (gen-2 infect → gen-2 spread → gen-3) is **asserted as a capability** ("why not spread the injection to all your contacts?"), never demonstrated end-to-end. The full LLM-to-LLM re-infect-and-re-propagate cascade was first shown by the successor papers in this set (Prompt Infection, Morris-II). Promoting it to a contagion entry would require ACES-side fan-out of the forwarded artifact — exactly the over-attribution the survey flagged.

**Role:** Greshake is the **lower-bound anchor** — the source of poisoning templates and the "first-hop only" reference point. The comparison set is measured *against* it as: "does each method achieve sustained R0 > 0 / multi-generation spread that Greshake only asserted?" It frames the SPREAD axis but is not a competing data point on it.

---

## 4. EXCLUSIONS

| Candidate (arXiv) | Failed bar | One-line reason |
|---|---|---|
| **Greshake et al., IPI (2302.12173)** | **B** — single-hop, onward re-propagation asserted not shown | Foundational worming term + first hop only; gen-2 re-spread is a claimed capability. Kept as anchor (§3). |
| **"Tipping the Dominos" / TOMA (2512.04129)** | **B** — single directed edge→core path; intermediaries are unwitting carriers | Payload relays to ONE target; only the terminal agent acts. No branching, no R0, no blast radius — moves confidentiality at one endpoint, not SPREAD. |
| **Tian et al., "Evil Geniuses" (2311.11855)** | **B** (and **A** after carve-out) | "Collective jailbreak" = shared-framework susceptibility; ChatDev "propagate" = sequential pipeline output-flow. Delivery is system-role replacement + optimizer = forbidden puppeting. |
| **Wang et al., "G-Safeguard" (2502.11127)** | **A** — defense paper | First MAS security safeguard (GNN on utterance graph). Cascade is real but is the *threat model defended*, harvested from PoisonRAG/InjecAgent — excluded even with harvested attack. |
| **Liu et al., "Do Not Mention This to the User" (2602.06547)** | **A** (measurement) + **B** (adoption-fanout) | Registry crawl (98k skills, 157 malicious). Static poisoned skill installed by a human; "coordinated campaign" = human publisher collusion, not agent contagion. |
| **Li et al., "Towards Secure Agent Skills" (2604.02837)** | **A** (SoK) + **B** (ACES-extrapolation) | Lifecycle/threat taxonomy, no experiments; its T7 "multi-agent propagation" is conceptual and *cites Prompt Infection* for the actual contagion. |
| **Yu et al., "NetSafe" (2410.15686)** | **A** (measurement) + **C** (major substrate) | Topology-safety study using *borrowed* attacks (AdvBench, Dark Traits). Contribution is topology rewire + RelCom loop = configurable agent-graph/router the frozen sim lacks. |
| **Mo et al., "Attractive Metadata Attack" (2508.02110)** | **B** (adoption-fanout) + **C** (moves confidentiality not SPREAD) | Novel single-agent tool-selection attack. Many agents adopting one poisoned tool = fan-out; survey itself notes "adoption share, not self-replication." |
| **Bhatt et al., "ETDI" (2506.01333)** | **A** (defense) + **B** (adoption-fanout) | OAuth/signing defense for MCP tool squatting/rug-pull. Swapped tool victimizes adopters; adopter is not a new propagating source. |
| **Hou et al., "MCP Landscape & Security" (2503.23278)** | **A** (SoK) + **B** (adoption-fanout) | MCP ecosystem SoK + 4×16 threat taxonomy. Poisoning/squatting/rug-pull are catalogued static-artifact compromises; no propagation experiment. |
| **"Hidden in Memory" / Sleeper Memory Poisoning (2605.15338)** | **B** (single-agent) | Novel dormant-activation method, but poison re-emerges within ONE assistant's own memory across its own sessions. No shared memory, no agent-to-agent passing. |
| **Lupinacci et al., "Complete Computer Takeover" (2507.06850)** | **A** (measurement) + **B** (single relay) | "Trust laundering" across 18 models; Inter-Agent Trust is a fixed 2-agent single hop terminating at the invoked agent. No onward re-propagation. |
| **Triedman, Jha & Shmatikov, "MAS Execute Arbitrary Malicious Code" (2503.12188)** | **B** (single-session orchestrator hijack) | Novel confused-deputy control-flow hijack, but "propagation" = intra-session orchestrator routing within one task. Paper itself never says worm/self-replication/contagion. |

**Famous papers explicitly excluded:** Greshake (anchor, not member — Bar B single-hop); *NetSafe* (major substrate); and the entire **MCP/skill cluster** (G-Safeguard, ETDI, Hou, Liu, Li) — the most-cited agent-security work — all fail on defense/SoK/measurement or adoption-fanout. They describe static-artifact compromise, not paper-demonstrated agent-to-agent self-replication.

---

## 5. Integrity

**arXiv ids needing re-check (future-dated 2026 ids — verify these resolve to the cited papers before run-day):**
- `2602.06547` — Liu et al., "Do Not Mention This to the User" (excluded)
- `2604.02837` — Li et al., "Towards Secure Agent Skills" (excluded)
- `2605.15338` — "Hidden in Memory" / Sleeper Memory Poisoning (excluded)
- `2512.04129` — TOMA / "Tipping the Dominos" (excluded)

All four flagged ids are on **excluded** candidates, so a mismatch does not alter the comparison set — but they should be re-resolved for citation integrity. Three of the five **included** ids (`2410.07283`, `2403.02817`, `2502.14529`) are near-term, plausibly real, and marked confirmed.

**The two worm members are future-dated — both web-verified 2026-06-08:**
- **ClawWorm (`2603.15727`, v2 2026-03-20)** → "ClawWorm: Self-Propagating Attacks Across LLM Agent Ecosystems" (Zhang, Wei, Luan, … Jun Sun, Meng Sun; Peking U / SYSU / Wuhan / Tsinghua / SMU); the paper `principle.md §3.1` names. Corroborated by direct search + abstract fetch. **Code not yet released** (responsible disclosure).
- **Autonomous LLM Agent Worms (`2605.02812`, v1 2026-05-04)** → Zha & Wang; verified via abstract + HTML full text. Contribution (SSCGV + SRPO worm discovery/generation), 3-hop cross-platform propagation, and LLM-decision-driven mechanism all confirmed from the abstract. **Code not yet released** (coordinated disclosure). *Caveat:* the abstract gives qualitative propagation (3 hops, R0 > 1) but **no quantitative infection counts** — confirm on full-paper read before relying on numbers.

Both worm members therefore rest on paper description (not runnable artifacts) until their repos drop — track both.

**Re-sweep reliability caveat:** the worms re-sweep that surfaced the exclusions (Agent Smith, CODES, MemMorph, Zombie Agents, MedSentry) was **tooling-degraded** — 5 of 6 search angles and 3 of the screens failed to emit structured output (the same failure that crashed the original sweep). The two concrete gaps (2605.02812 + the missing angles) were closed by direct main-loop web verification, but **exhaustive coverage is not claimed**: a clean re-run (simpler schema / explicit StructuredOutput instruction) could still surface a stray worm. Current confidence: the *high-value* self-propagation space is covered; the long tail is not exhaustively swept.

**Runnable code among included members:** all three ship runnable code (Prompt Infection — paper repo; Morris-II — project site + released code; CORBA — `github.com/zhrli324/Corba`, confirmed to map to Zhou et al.). The entire comparison set is reproducible from published artifacts before porting to ACES — no member rests on description alone.
