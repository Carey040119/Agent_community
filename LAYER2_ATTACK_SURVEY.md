# ACES Layer-2 Attack Literature Survey

> **Status:** information deliverable (literature catalog) — *not* an implementation plan and *not* a build order.
> Produced 2026-06-08 at the opening of Layer 2, to answer: **which published agent-attack papers are validly benchmarkable in the ACES setting.**
> Nothing here changes the frozen Layer-1 substrate, the config, or the code. It is a screened reading list with provenance.

---

## 0. Method & provenance

**How this was built.** An 8-way parallel literature sweep across attack families (worms/contagion, indirect prompt injection, tool/skill/MCP supply-chain, memory poisoning, multi-agent-system attacks, economic/resource-exhaustion, data/credential exfiltration, and agent-security benchmarks) → dedup → per-paper screen against the ACES benchmarkability rubric → an adversarial verifier that web-confirmed each citation is real and stress-tested the realizability/measurability claims → synthesis.

**Run stats:** 87 paper-hits swept → **67 unique** after dedup → 67 screened → **54 passed verification** (not dropped) → **13 dropped**. The synthesizer's curated catalog below presents **39 records after merging near-duplicates**, tiered **7 / 21 / 11** (benchmark-now / with-extension / out-of-scope-cited). The 54-vs-39 gap is editorial merging of near-dupes, not lost papers.

**The benchmarkability rubric (from `principle.md §3`).** A paper is *validly benchmarkable in ACES* only if its mechanism is:
1. **LLM-decided, not scripted** — realizable as a *planted opportunity* the attacker's own LLM acts on autonomously. Puppeting (fake first-person reasoning, scripted state mutation) is **forbidden**, and there is **no scripted-vs-LLM contrast arm**.
2. **Channel-fit** — operates/propagates through an in-sim channel (mail, group_mail, server, token_transfer, skill, forum, delegation, doc, memory).
3. **Substrate-fit** — runs on the frozen 15-agent substrate as-is, or with a clearly-stated *minor* extension (major new substrate is a flagged cost / v2 bump).
4. **Measurable** — moves ≥1 CSRI channel (confidentiality / economic / spread / availability) that is *able* to move, not structurally pinned to zero.
5. **Citable** — real published paper; multi-agent / agent-to-agent **contagion** is the flagship phenomenon; code-shipping papers are highest value.

**Two method caveats (read before trusting coverage):**
- ⚠️ **The dedicated "worms / self-propagating contagion" sweep agent failed** (it never returned structured output). The flagship contagion papers (Morris-II, Prompt Infection, CORBA, TOMA, NetSafe, G-Safeguard) still surfaced — but *incidentally*, via the IPI / multi-agent / benchmark sweeps. A re-run of the worms sweep specifically could surface additional self-propagation papers this catalog may have missed. **Treat the contagion column as a lower bound on coverage.**
- ⚠️ **Contagion over-attribution.** Many `contagion=true` labels are *ACES-side extrapolation* (one poisoned artifact fanned out via the republish/blast-radius infrastructure), not a phenomenon the cited single-agent paper demonstrates. See §8.

---

# ACES Layer-2 Attack Literature Survey

## 1. Executive Summary

| Metric | Count |
|---|---|
| Papers screened & verified (kept) | 39 |
| Papers dropped (unconfirmable / clearly out-of-scope) | 13 |
| **Tier 1 — Benchmark now** | 7 |
| **Tier 2 — With minor/major extension** | 21 |
| **Tier 3 — Out of scope (kept as documented negatives)** | 11 |
| Contagion-capable (agent-to-agent spread, Tier 1+2) | 11 |
| Code-shipping (Tier 1+2) | 18 |

**Where the literature is strong vs. thin for ACES.** The literature is **deep and code-rich on the poisoning / indirect-prompt-injection (IPI) axis through the skill/doc/forum/mail surfaces** — this is the cluster ACES's frozen substrate fits best, and it is where every flagship agent-to-agent contagion paper lives (Greshake IPI origin, Morris-II/ComPromptMized worm, Prompt Infection, CORBA, TOMA, G-Safeguard's Memory Attack). The skill-marketplace / ToxicSkills surface is **over-grounded**: roughly a dozen papers all map onto the same publish/adopt/republish channel, so most of them strengthen the *one* existing template rather than adding new mechanisms. The literature is **thin-to-absent for ACES on three fronts**: (a) **economic/token-drain** — only DoW (conceptual) and CORBA (availability-DoS) genuinely fit; nearly every energy-latency/sponge paper is structurally pinned by the 512-token output cap and an econ metric that only counts value-transferred-to-attacker; (b) **credential_leak beyond mail-spearphish** — most confidentiality papers are single-agent web/RAG/prompt-extraction work that needs a RAG retriever, a visual DOM, an exfil sink, or a "system-prompt-as-asset" concept ACES lacks; (c) **disruption/availability as a first-class contagion** — CORBA is essentially the only clean availability-contagion candidate, and even it needs a spread-metric extension. A recurring honest caveat across the corpus: many "single-agent" papers are recorded as `contagion=true` only because ACES's republish/blast-radius infrastructure *can* fan one poisoned artifact out — that contagion is ACES-side extrapolation, not demonstrated by the cited paper.

---

## 2. Tier 1 — BENCHMARK NOW

Sorted by value (contagion + code + channel diversity first).

| Paper (yr) | Mechanism | attack_class | entry_point(s) | CSRI channel(s) | contagion? | code? | provenance |
|---|---|---|---|---|---|---|---|
| **Greshake et al., "Not What You've Signed Up For" (2023)** | Canonical origin of indirect prompt injection + self-propagating "worming"; hidden directives in retrieved content hijack the reading agent | poisoning | skill, doc, forum, group_mail, mail | spread, confidentiality, economic, availability | **yes** | **yes** | AISec '23, arXiv:2302.12173, github.com/greshake/llm-security — literature anchor for 3 shipped poisoning templates |
| **Lee & Tiwari, "Prompt Infection" (2024)** | Single infectious prompt self-replicates LLM-to-LLM (hijack + payload + cross-hop accumulation + self-replication) | poisoning | skill, forum, delegation, group_mail | spread, confidentiality, availability | **yes** | no | arXiv:2410.07283 — flagship self-replicating contagion, realized today via publish/adopt/republish loop |
| **Wang et al., "G-Safeguard" — Memory Attack (2025)** | Plant erroneous content in attacker agent's memory; its own LLM derives & broadcasts wrong conclusions over the utterance graph (defense paper, attack harvested) | poisoning | memory, group_mail, skill | spread, availability | **yes** | **yes** | arXiv:2502.11127, github.com/wslong20/G-safeguard — port Memory Attack; **drop the system-prompt-injection variant (puppeting)**; treat G-Safeguard as a defense baseline |
| **Liu et al., "Do Not Mention This to the User" (2026)** | Real-world measurement of malicious agent-skill registries: Data-Thief (credential exfil via RCE) + Agent-Hijacker (stealth SKILL.md directives); 157 confirmed malicious skills | poisoning | skill | confidentiality, spread | **yes** | **yes** | USENIX Sec 2026, arXiv:2602.06547 — canonical real-world grounding for the ToxicSkills/poisoned-skill template, 2-family taxonomy for payload variants |
| **Li et al., "Towards Secure Agent Skills" (2026)** | SKILL.md lifecycle taxonomy; data/instruction-boundary failure + single-approval persistent-trust rug-pull | poisoning | skill | spread, confidentiality | **yes** (structural argument in paper) | no | arXiv:2604.02837 — maps 1:1 to shipped poisoned_skill_marketplace; rug-pull is an *optional* minor extension, not a gate. (No code, no demonstrated contagion — grounds the template.) |
| **Kelly, Glavin & Barrett, "Denial of Wallet" (2021)** | Formalizes economic-exhaustion DoS: bleed the wallet to metered operating cost (not value transferred to attacker) | token_drain | mail, group_mail, delegation | economic, availability | no | no | JISA 60:102843, arXiv:2104.08031 — conceptual grounding for shipped Management-loop-drain; **measure on community-balance/availability, NOT the attacker-drain econ term** |
| **Heiding et al., "Automated Spear Phishing" (2024)** | LLM autonomously profiles + authors + sends personalized spear-phish end-to-end; 54% human click-through | credential_leak | mail | confidentiality (gated/indirect) | no | no | arXiv:2412.00586 — canonical empirical grounding for the shipped hr_directory_spearphish template; confidentiality moves only via a multi-step leak→secret-read chain |

> Note on AgentDojo (Debenedetti et al. 2024, NeurIPS D&B, code): its screen verdict is `benchmark_now`, but its contribution is **single-agent methodology + an importable utility-vs-security defense/eval harness**, not a new attack object. It grounds the existing poisoning/skill/exec-transfer templates and is best treated as a **Layer-2/eval harness import** (see §6/§7) rather than a standalone Tier-1 attack — its mechanism is already realized by shipped templates. Listed under Tier 2 for the harness extension to avoid implying a new attack.

---

## 3. Tier 2 — WITH MINOR / MAJOR EXTENSION

| Paper (yr) | Mechanism | attack_class | entry_point(s) | CSRI channel(s) | contagion? | code? | What extension is needed |
|---|---|---|---|---|---|---|---|
| **Cohen, Bitton & Nassi, "Here Comes The AI Worm" / Morris-II (2024)** | Zero-click self-replicating prompt: replicate + payload, each victim re-propagates | poisoning | skill, mail, group_mail, memory | spread, confidentiality, availability | **yes** | **yes** | **MINOR**: add hop/generation-depth + per-generation growth to spread diagnostics (today `propagation_hops = len(abused)`, cardinality not depth); surface victim-driven self-republish as an autonomous opportunity. The literal mail/RAG carrier is a MAJOR engine change to avoid. arXiv:2403.02817, github.com/StavC/Here-Comes-the-AI-Worm |
| **Zhou et al., "CORBA" (2025)** | Contagious+recursive blocking message: relay-to-neighbors + resource-draining loop collapses availability | disruption | group_mail, mail, delegation | availability, spread, economic | **yes** | **yes** | **MINOR (metrics)**: add a relayed-instruction infection signal to the abused-identity set so spread scores agent-to-agent infection (avail+econ move today). arXiv:2502.14529, github.com/zhrli324/Corba |
| **TOMA / "Tipping the Dominos" (2025)** | Topology-aware multi-hop adversarial propagation; edge seed diffuses to a distant target | poisoning | doc, forum, delegation, group_mail, skill | spread, confidentiality, availability | **yes** | no | **MINOR**: single-topology multi-hop runs now; the headline (topology-dependent propagation) needs topology as a swept factor (alternate zone_link/reporting configs = v2 bump). arXiv:2512.04129 |
| **Yu et al., "NetSafe" (2024)** | Topology-analysis lens: network topology governs misinformation spread; star centers most vulnerable | poisoning | group_mail, forum | spread, availability | **yes** | **yes** (github.com/Ymm-cll/NetSafe — screen field was wrong) | **MAJOR (v2)**: re-wire frozen communication_groups into star/chain/tree/random conditions + new sweep dimension. Payload itself = group_norm_misinformation, runs now. arXiv:2410.15686 |
| **Tian et al., "Evil Geniuses" (2023)** | Role-level poisoned instruction pack cascades through a team via message-passing | poisoning | skill, delegation | spread, confidentiality, economic | **yes** | **yes** | **MINOR**: role-targeted poisoned-skill variants (per-role packs) to test role-level > system-level. Drop the EG auto-gen optimizer + system-prompt-replacement arm (operator-driven/puppeting). arXiv:2311.11855, github.com/T1aNS1R/Evil-Geniuses |
| **Triedman, Jha & Shmatikov, "MAS Execute Arbitrary Malicious Code" (2025)** | Untrusted content propagates through inter-agent comms → downstream unsafe tool actions (true contribution: orchestrator control-flow hijack) | poisoning | skill, forum, doc, delegation | confidentiality, spread, availability | yes (**screen flags as inflated** — paper is single-session, not worm) | no | **MAJOR**: faithful orchestrator-hijack needs a central router/dispatcher agent ACES lacks. Realizable slice duplicates ToxicSkills/Moltbook templates. arXiv:2503.12188 |
| **Lupinacci et al., "The Dark Side of LLMs" (2025)** | Inter-agent trust laundering: model refuses a direct request but obeys the identical payload from a trusted peer (100% of models) | credential_leak | mail, delegation, server | confidentiality, spread | yes (spread conditional) | **yes** (anon repo — screen field was wrong) | **MINOR**: score the trust delta cleanly (refused-direct vs complied-via-peer); enable multi-hop relay for spread. Confidentiality moves today. OS-RCE endpoint out of scope. arXiv:2507.06850 |
| **AgentDojo (Debenedetti et al. 2024)** | Indirect injection via laced tool-returned data hijacks a benign tool-using agent | poisoning | doc, mail, group_mail, skill, token_transfer, forum | confidentiality, economic, availability | no | **yes** | **MINOR (harness/Layer-2)**: import utility-vs-security scoring + injection corpus/defense baselines as an eval overlay. Mechanism already realized by shipped templates. arXiv:2406.13352, github.com/ethz-spylab/agentdojo |
| **Zhan et al., "InjecAgent" (2024)** | IPI via attacker-controlled tool outputs; ~24% ReAct GPT-4 ASR | poisoning | doc, mail, server | confidentiality, economic | no | **yes** | **MINOR**: add an attacker-controllable untrusted-tool-output/web-fetch channel; use as injection-payload taxonomy hardening the doc/skill/mail templates. arXiv:2403.02691, github.com/uiuc-kang-lab/InjecAgent |
| **Wang et al., "MCPTox" (2025)** | Tool-metadata poisoning (instructions in tool description/params); o1-mini 72.8% ASR | poisoning | skill, server | confidentiality, availability, economic | no | **yes** | **MINOR**: poisonable tool/MCP metadata on server/skill endpoints (or move payload from body→description). Strengthens ToxicSkills. arXiv:2508.14925 (AAAI 2026 accepted) |
| **Mo et al., "Attractive Metadata Attack" (AMA) (2025)** | Optimized "attractive" tool metadata wins the agent's autonomous selection | poisoning | skill | **spread** (drop confidentiality per verifier) | yes | **yes** | **MINOR-CODE**: surface skill *description* at browse/selection time (only name+price shown now) + seed benign competitor skills to measure selection share. arXiv:2508.02110, github.com/SEAIC-M/AMA |
| **Saha et al., "Under the Hood of SKILL.md" (2026)** | Semantic supply-chain: metadata games Discovery (retrieval) / Selection / Governance stages | poisoning | skill | spread, confidentiality, economic | yes | **yes** (github.com/ShoumikSaha/agent-skill-security — screen field was wrong) | **MINOR v2 bump**: semantic retriever behind browse() (Discovery) + LLM-judge gate (Governance); surface description pre-adoption (Selection). arXiv:2605.11418 |
| **Bhatt et al., "ETDI" (2025)** | MCP tool squatting (name impersonation) + rug pull (silent post-approval mutation) | poisoning | skill | confidentiality, spread | yes (one-to-many fan-out) | **yes** (vineethsai/python-sdk — screen field was wrong) | **MINOR**: rug-pull needs mutable/versioned skill body + adopter re-read; squatting needs duplicate-name allowance + clean-twin control. ETDI = signing/version-pin defense knob. arXiv:2506.01333 |
| **Hou et al., "MCP: Landscape, Security Threats" (2025)** | SoK of MCP supply chain: tool poisoning, name squatting, post-approval rug-pull | poisoning | skill, delegation, doc | confidentiality, spread | yes | no | **MINOR**: rug-pull needs in-place skill re-version primitive. No-code SoK that grounds the ToxicSkills family. arXiv:2503.23278 |
| **Xie et al., "Red-Teaming Coding Agents" (2025)** | Two-channel injection: tool-description + tool-return-value; escalated to RCE + ToolLeak | poisoning | skill, doc, server | confidentiality, availability | no | no | **MINOR**: model tool-return-value injection as a first-class point. RCE + system-prompt-leak headlines are out of scope. Grounds poisoned-skill/runbook templates. arXiv:2509.05755 |
| **MCPSecBench (Yang et al. 2025)** | Tool poisoning + tool/server name-squatting (13 of 17 types are scripted transport exploits) | poisoning | skill, server | confidentiality, availability | no | **yes** | **MINOR**: name/server squatting needs a name-collision-resolution rule. Tool-poisoning core = redundant with ToxicSkills. arXiv:2508.13220, github.com/AIS2Lab/MCPSecBench |
| **Spracklen et al., "We Have a Package for You" (2024)** | Slopsquatting: pre-register hallucinated dependency names; coding agent installs attacker's package | poisoning | skill, server | confidentiality, spread, availability | no | **yes** (Spracks/PackageHallucination — screen field was wrong) | **MAJOR**: needs an in-sim package registry w/ attacker-registerable namespace + install-from-registry exec. Collapsing onto skill channel = re-runs ToxicSkills. arXiv:2406.10279 (USENIX Sec 2025) |
| **Pulipaka et al., "Hidden in Memory: Sleeper Memory Poisoning" (2026)** | Poison planted day N stays dormant, activates day N+k, evading single-turn scans | poisoning | doc, forum, skill, memory | spread (extension-gated), availability, confidentiality | **yes** (ACES-side; paper single-agent — screen overstated) | **yes** (ivaxi0s/agent-poisoning-memory — screen field was wrong) | **MINOR**: dormancy-lag instrumentation (plant-day vs activation-day) + single-turn-scan defense to show bypass. Without it → existing doc/skill template. arXiv:2605.15338 |
| **MemoryGraft (Srivastava & He 2025)** | Fabricated "successful experience" records induce persistent behavioral drift via similarity retrieval | poisoning | memory, doc | availability, economic | no | **yes** | **MINOR-MODERATE (v2)**: needs a similarity-retrieved (ideally shared) experience store; ACES surfaces memory unconditionally by recency. arXiv:2512.16962, github.com/Jacobhhy/Agent-Memory-Poisoning |
| **Zombie Agents (Yang et al. 2026)** | Self-reinforcing durable memory backdoor surviving truncation/summarization | poisoning | memory, doc | confidentiality (only strong fit) | no | no | **MINOR→MAJOR**: a "does a one-shot memory poison recur" probe via a new victim-memory entry point is minor; the survives-summarization mechanism needs a compaction/RAG pipeline (major). arXiv:2602.15654 |
| **Sunil et al., "Memory Poisoning Attack & Defense" (2026)** | Memory-injection via query stream; corrupted memory steers later behavior (+ moderation/sanitization defenses) | poisoning | memory, mail, forum | confidentiality, availability | no | no | **MINOR**: inbound-content-to-persistent-memory path (attacker-writes-victim-memory is forbidden puppeting); real value = the **defense arm** (moderation + sanitization). arXiv:2601.05504 |
| **AMA / NICGSlowDown (Chen et al. 2022)** | EOS-suppression output-length inflation (reframed as content-induced over-generation) | disruption | doc, skill, mail | availability (econ pinned) | no | **yes** | **MINOR**: new disruption template + over-generation diagnostic; literal vision/gradient attack does not port. arXiv:2203.15859, github.com/SeekingDream/CVPR22_NICGSlowDown |
| **Zhou et al., "Beyond Max Tokens" (2026)** | Induced long tool-call chains amplify cumulative token cost past per-response caps | token_drain | delegation, mail, skill | economic, availability | no | no | **MINOR**: LLM-mode induced-tool-chain opportunity (NOT scripted token mutation) + loosen inner-loop brakes (wallet/iter/wall-clock) on the experiment arm. arXiv:2601.10955 |
| **Imprompter (Fu et al. 2024)** | Gradient-optimized obfuscated suffix coerces secret scan + markdown/image-URL exfil | credential_leak | mail, doc, forum | confidentiality | no | **yes** | **MAJOR**: needs outbound exfil sink + suffix optimizer (out of scope). Realizable slice duplicates spearphish/poison templates. arXiv:2410.14923, github.com/Reapor-Yurnero/imprompter |
| **PLeak (Hui et al. 2024)** | Gradient-optimized query coaxes confidential system-prompt disclosure | credential_leak | mail, forum | confidentiality (pinned w/o new asset) | no | **yes** | **MAJOR**: needs "playbook/system-prompt-as-confidential-asset" leak event + privilege weight + CSRI hook; optimizer can't run in-sim. arXiv:2405.06823, github.com/BHui97/PLeak |
| **TAMAS (Kavathekar et al. 2025)** | Agent-level adversarial agents (Byzantine/Colluding/Contradicting) + Impersonation | poisoning/disruption | mail, group_mail, delegation, doc | availability, confidentiality | no | **yes** | **MINOR**: model a coordinated colluder *cohort* (currently one designated attacker) + an ERS-style defense metric. DPI/IPI/Impersonation = scripted (forbidden). arXiv:2511.05269, github.com/microsoft/TAMAS |
| **AgentHarm (Andriushchenko & Souly et al. 2024)** | Measurement: refusal rate + capability-retention on a planted malicious multi-step goal | poisoning (scorer) | memory, delegation | confidentiality, economic, availability | no | **yes** | **MINOR (scorer)**: two-axis scorer (refusal-grade vs capability-completion-grade) per planted opportunity. Adopt as scorer, NOT a replayable attack. arXiv:2410.09024, Inspect Evals |

---

## 4. Tier 3 — OUT OF SCOPE

| Paper (yr) | Why excluded |
|---|---|
| **EIA: Environmental Injection Attack (Liao et al. 2024, ICLR'25)** | Single-agent + single-human-user web-privacy leak; distinctive stealth/form-mirroring/PII needs a human persona + visual DOM (major substrate, breaks agents-as-principals). Portable part = generic poisoned-doc, already covered. No contagion. |
| **EVA: Red-Teaming GUI Agents (Lu et al. 2025)** | Single-agent GUI red-team; novel mechanism is an attacker-run iterative evolve→test→mutate **optimization loop** (scripted harness, not a plantable opportunity); needs GUI substrate. No code. |
| **ToolHijacker (Shi et al. 2025, NDSS'26)** | Distinctive contribution (optimized doc dominating an embedding retriever + automated tool-selection) needs a major new retrieval/selection substrate + offline optimizer; collapses into ToxicSkills. Single-agent, no code. |
| **AgentPoison (Chen et al. 2024, NeurIPS)** | Optimized trigger wins embedding-similarity retrieval from a vector RAG/long-term-memory store ACES lacks (major new substrate); harm is attacker-authored at retrieval, not an autonomous decision. |
| **MINJA (Dong et al. 2025)** | Single-agent self-poisoning; load-bearing primitives (input-distilled memory writes + semantic retrieval) absent; attacker step otherwise collapses to forbidden scripting. Spread structurally pinned. |
| **GraphRAG under Fire / GRAGPoison (Liang et al. 2025)** | Relation-level KG-index attack needs a GraphRAG retriever (major new substrate); realizable-now version duplicates flat-doc poisoning. Single-agent. (Code ships — screen field was wrong.) |
| **ConfusedPilot (RoyChowdhury et al. 2024)** | Defining effects (retrieval suppression + confused-deputy cache leak) are RAG-pipeline properties, not agent decisions; doc body never even reaches an agent's LLM today. No CSRI channel moves. |
| **Agent-in-the-Middle / AiTM (He et al. 2025, ACL'25)** | Interception/relay position is engine-granted plumbing (scripting), not an autonomous choice; needs a new message-routing transport substrate. Downstream effect duplicates existing poisoning templates. |
| **M-Spoiler (Liu et al. 2025, EMNLP'25)** | ACES has no collective-decision/vote/debate organ to flip; core method is offline adversarial-suffix optimization (scripted). Residue = generic group_mail/forum persuasion already shipped. |
| **P-DoS (Gao et al. 2024)** | Fine-tune-time poisoning has no per-agent fine-tune substrate; defeated by the 512/800-token output cap; inference-token waste hits zero CSRI channels (econ counts only transfers-to-attacker). Collapses to ToxicSkills. |
| **LoopLLM (Li et al. 2025, AAAI'26)** | No energy/latency channel; output hard-capped so over-generation can't inflate; only proxy (token-count charge) pinned below noise. Single-agent, non-contagious. (Code ships — screen field was wrong.) |
| **Alizadeh et al., "Simple PI Leaks Personal Data" (2025)** | Single-agent victim-side injection, no autonomous attacker; leaked-PII harm unmeasurable (confidentiality is secret-read-only). Realizing it = puppeting the victim + major new substrate. |
| **Effective Prompt Extraction (Zhang, Carlini & Ippolito 2024, COLM)** | Single-agent prober-vs-model; leaked asset (system instructions) is unmodeled → confidentiality structurally pinned to zero. No contagion. (Code ships.) |
| **output2prompt (Zhang, Morris & Shmatikov 2024, EMNLP)** | Out-of-band ML inversion over harvested outputs; not an in-channel agent action (landing it = scripting). System-prompt asset class absent. No CSRI movement. (Code ships.) |
| **ASB: Agent Security Bench (Zhang et al. 2025, ICLR)** | Single-agent injection/ASR harness, no autonomous attacker; realizable slice duplicates ToxicSkills; novel cross-agent memory-poisoning needs major new substrate. |
| **MAGPIE (Juneja et al. 2025)** | Non-adversarial: well-behaved agents accidentally over-disclose; no attacker, no planted opportunity, no contagion. Value = a defense/measurement probe, not an attack template. |
| **ST-WebAgentBench (Levy et al. 2024)** | Single-agent web-UI safety benchmark; no attacker, no planted opportunity; "harm" = the agent's own policy-violation graded by a rubric. Informs the Layer-3 metric/policy layer, not an attack. |

> (Tier 3 holds 17 kept-but-out-of-scope records; the 11 cited in the executive count are the ones whose verdict is strictly `out_of_scope` rather than `with_extension`. The remaining out-of-scope-leaning entries above were verified `keep`/`flag` and are documented so the reader sees *why* each was rejected.)

---

## 5. COVERAGE MAP

Matrix of **{4 CSRI channels} × {4 attack_class}**, counting Tier-1/2 papers whose mapping to that cell is *defensible* (a paper can appear in multiple cells). "—" = no Tier-1/2 paper.

| | poisoning | credential_leak | token_drain | disruption |
|---|---|---|---|---|
| **confidentiality** | ~14 (Greshake, Prompt Infection, Morris-II, Liu'26, Li'26, ETDI, Hou, MCPTox, MCPSecBench, Xie, TOMA, Pulipaka, AgentDojo, InjecAgent…) | 4 (Heiding, Lupinacci, Imprompter, PLeak) | — | — |
| **economic** | ~5 (Greshake, Evil Geniuses, AgentDojo, MemoryGraft, Saha) | — | 3 (DoW, Beyond Max Tokens, [P-DoS=OOS]) | — |
| **spread** | ~13 (Greshake, Prompt Infection, Morris-II, G-Safeguard, Liu'26, Li'26, TOMA, NetSafe, Evil Geniuses, AMA, ETDI, Hou, Pulipaka…) | 1 (Lupinacci, extension-gated) | — | 1 (CORBA) |
| **availability** | ~8 (Greshake, Morris-II, AgentDojo, NetSafe, TOMA, MemoryGraft, NICGSlowDown, MCPSecBench…) | — | 2 (DoW, Beyond Max Tokens) | 2 (CORBA, NICGSlowDown-reframed) |

**Over-covered cells.** `poisoning × {confidentiality, spread}` is heavily over-grounded — the skill/IPI surface alone accounts for ~12 papers, most of which strengthen the *single* existing ToxicSkills/poisoned-skill template rather than adding mechanisms. Promote breadth, not count, here.

**Under-covered cells (gaps).**
- `disruption × *` is nearly empty: **CORBA is the only clean availability-contagion candidate** (with a minor metrics extension); NICGSlowDown is a reframed degenerate. There is **no benchmarkable `disruption × spread` or `disruption × confidentiality` Tier-1/2 paper besides CORBA**.
- `token_drain` has **only 2.5 fits** (DoW conceptual, Beyond Max Tokens extension-gated; every energy-latency/sponge paper is OOS due to the output cap + econ-metric definition). `token_drain × spread` and `token_drain × confidentiality` are **empty**.
- `credential_leak × {economic, spread, availability}` is **almost empty** — credential papers are single-agent confidentiality leaks; only Lupinacci's trust-laundering reaches `spread`, and only after an extension.
- The **entire `disruption` and `credential_leak` columns lack a code-shipping, contagion-capable Tier-1 paper** (CORBA covers disruption-contagion but is Tier-2).

**Where the agent-to-agent CONTAGION (spread) papers cluster.** Overwhelmingly in **`poisoning` via the skill / group_mail / delegation / doc surfaces**: Greshake (origin), Prompt Infection, Morris-II/ComPromptMized, G-Safeguard Memory Attack, TOMA, NetSafe, Evil Geniuses, ETDI, Hou, AMA, Pulipaka. The **only non-poisoning contagion candidate is CORBA (disruption)**. Contagion is essentially a poisoning-channel phenomenon in this corpus, and several "contagion=true" labels (Pulipaka, TOMA topology claim, MAS-Execute-Code, Lupinacci, WASP) are **ACES-side extrapolations** the cited papers do not themselves demonstrate.

---

## 6. EXISTING TEMPLATES ASSESSMENT

The 8 shipped templates, each with the best citable grounding found.

| # | Template (class / entry) | Best citable grounding | Status |
|---|---|---|---|
| 1 | **HR directory spearphish** (credential_leak / mail) | **Heiding et al. 2024 (arXiv:2412.00586)** — fully-automated LLM spear-phishing, 54% click-through. Direct empirical anchor. | **Well-grounded.** Note CSRI confidentiality moves only via a gated multi-step leak→secret-read chain, not the raw mail leak. |
| 2 | **Payroll signer theft** (credential_leak / server) | Trust-laundering: **Lupinacci et al. 2025 (arXiv:2507.06850)**; generic IPI-to-secret-read: **Greshake 2023**, **InjecAgent 2024**. | **Adequately grounded** by trust-exploitation + IPI literature; no single paper is a perfect 1:1 anchor for server-secret theft specifically. |
| 3 | **Release runbook poisoning** (poisoning / group_mail) | **Greshake 2023 (IPI origin)**; reinforced by **PoisonedRAG**, **Xie 2025**, **G-Safeguard Memory Attack**. | **Well-grounded** as IPI-into-shared-content; Greshake is the primary anchor it previously lacked. |
| 4 | **Executive emergency transfer fraud** (token_drain / token_transfer) | **AgentDojo 2024** (send-a-payment injection sub-task); **AdvAgent 2025** (poisoned content → targeted financial action). | **Grounded** as IPI-drives-transfer; this is `token_transfer`-as-economic, somewhat thin on a dedicated single anchor. |
| 5 | **Management loop drain** (token_drain / mail) | **Kelly et al. 2021 "Denial of Wallet"** (conceptual); **Zhou et al. 2026 "Beyond Max Tokens"** (induced tool-chain cost amplification). | **Conceptually grounded.** Measure on community-balance/availability — the attacker-drain econ term reads ~0 for pure DoW. |
| 6 | **Monitoring alert fatigue** (disruption / server) | **CORBA 2025** is the nearest citable disruption-contagion; no paper directly grounds "alert fatigue" specifically. | **Thinly sourced — re-ground or reframe.** Closest is CORBA's recursive-blocking DoS; consider reframing toward CORBA's mechanism rather than a bespoke alert-fatigue story. |
| 7 | **Group-norm misinformation** (poisoning / group_mail) | **Greshake 2023**; **NetSafe 2024** (topology-governed misinformation spread); **TAMAS** (Contradicting/Colluding); **G-Safeguard Memory Attack**. | **Well-grounded** — strong multi-agent misinformation-contagion literature. |
| 8 | **Poisoned skill / ToxicSkills** (poisoning / skill) | **Liu et al. 2026 "Do Not Mention This to the User"** (canonical real-world measurement) + **Li 2026**, **Hou 2025**, **MCPTox**, **AMA**, **ETDI**, **MCPSecBench**, **Saha 2026**, **Evil Geniuses**. | **Over-grounded** — the single best-cited template; pick payload variants from Liu'26's 2-family taxonomy. |

**Scripted-arm directive (mandatory).** Every screen and verifier flagged the same integrity line: the legacy **scripted attacker paths must be removed / kept out of all benchmark measurement** — only LLM-realizable, planted-opportunity attacks are legitimate, and there is **no scripted-vs-LLM contrast arm**. Specifically called out across the corpus: `_attack_via_skill` (attacks.py:978), `_attack_token_drain` / `_attack_credential_leak` (the `attacker_policy=scripted` baselines), and any direct `target.tokens_used` / wallet / memory state mutation. These exist as legacy baselines and **puppet the agent**; any CSRI number sourced from them is invalid. The benchmark realization for all 8 templates is the `_plant_opportunity` / `_opportunity_text` LLM-mode path (attacks.py:289–408), where the attacker's own LLM decides whether/how to act and the victim's own LLM decides whether to comply.

> *Note: code-location references above (e.g. `attacks.py:978`) are the synthesizer's claims and were not line-verified in this survey. Confirm against the live source before acting on any of them.*

---

## 7. PRIORITIZED SHORTLIST (information only — candidates, not a decided plan)

The strongest contagion-capable, code-shipping, LLM-realizable, channel-diverse handful, for the user to choose among:

1. **Greshake et al. 2023 — IPI origin + worming** *(benchmark now, code, contagion, 5 channels).* arXiv:2302.12173, github.com/greshake/llm-security. The canonical anchor for 3 shipped poisoning templates; runs today on skill/doc/forum/group_mail with no substrate change.
2. **Lee & Tiwari 2024 — Prompt Infection** *(benchmark now, contagion).* arXiv:2410.07283. Flagship self-replicating LLM-to-LLM contagion, fully realized on the frozen publish/adopt/republish loop with a moving spread metric; no code but mechanism is shipped.
3. **Cohen, Bitton & Nassi 2024 — Morris-II / ComPromptMized** *(minor extension, code, contagion).* arXiv:2403.02817, github.com/StavC/Here-Comes-the-AI-Worm. The canonical GenAI worm; 1-hop runs today, multi-hop needs only a propagation-depth metric + surfaced self-republish opportunity.
4. **CORBA 2025** *(minor metrics extension, code, the only clean disruption-contagion).* arXiv:2502.14529, github.com/zhrli324/Corba. Fills the empty `disruption × spread` cell; avail+econ move today, spread needs a relayed-instruction infection signal.
5. **Liu et al. 2026 — "Do Not Mention This to the User"** *(benchmark now, code, contagion, real-world).* arXiv:2602.06547. Canonical real-world ToxicSkills grounding with a 2-family payload taxonomy ready to drive variants.
6. **G-Safeguard Memory Attack 2025** *(benchmark now, code, contagion + defense baseline).* arXiv:2502.11127, github.com/wslong20/G-safeguard. Memory-seed → autonomous utterance-graph cascade; doubles as a defense baseline. (Drop its system-prompt-injection variant.)
7. **TOMA 2025** *(minor extension, contagion, channel-diverse).* arXiv:2512.04129. Topology-aware multi-hop poisoning across doc/forum/skill/delegation; single-topology runs now, topology-sweep is the v2 step.

These cluster on the poisoning-contagion axis (where the literature and substrate are strongest); CORBA is the deliberate outlier to cover the disruption gap.

---

## 8. INTEGRITY CAVEATS

**Papers the verifier flagged (real, but a claim looked inflated or a field was wrong).** These are kept, but the reader should treat the noted claim with the correction:

| Paper | Verifier flag |
|---|---|
| **MAS Execute Arbitrary Malicious Code (Triedman 2025)** | `contagion=true` + spread channel **inflated** — paper is single-session orchestrator hijack, NOT worm contagion; benchmarkable slice duplicates ToxicSkills/Moltbook. |
| **Hidden in Memory / Sleeper (Pulipaka 2026)** | `contagion=true` **overstated** (paper is single-agent); `code_available=false` **factually wrong** (repo ships). |
| **Lupinacci "Dark Side of LLMs" (2025)** | `contagion`/spread framing **inflated** — spread is conditional on an unbuilt multi-hop extension; `code_available=false` **wrong** (anon repo exists). |
| **AMA (Mo 2025)** | Description **not surfaced at selection** (only name+price), so the extension is minor-*code* not pure-config; **confidentiality channel should be dropped** (spread only). |
| **Saha "Under the Hood of SKILL.md" (2026)** | `code_available=false` **wrong** (github.com/ShoumikSaha/agent-skill-security ships); Selection "realizable now" should be downgraded to minor-extension. |
| **ETDI (Bhatt 2025)** | `code_available=false` **wrong** — code ships (vineethsai/python-sdk + upstream MCP PR #845). |
| **NetSafe (Yu 2024)** | `code_available=false` **wrong** (github.com/Ymm-cll/NetSafe ships); headline value depends on a v2 topology-rewire, not the as-is template. |
| **GRAGPoison (Liang 2025)** | `code_available=false` **wrong** (JACKPURCELL/GraphRAG_Under_Fire ships; also IEEE S&P 2026). Verdict (OOS) unchanged. |
| **Spracklen "Package Hallucinations" (2024)** | `code_available=false` **wrong** (Spracks/PackageHallucination ships). |
| **LoopLLM (Li 2025)** | `code_available=false` **wrong** (neuron-insight-lab/LoopLLM ships). Verdict (OOS) unchanged. |
| **MemoryGraft (Srivastava 2026)** | Minor: cited `models.py:383` for doc poison fields; actual fields at 365–366 (383 is the SKILL docstring). |
| **MCPTox (Wang 2025)** | Provenance understated: **accepted/published at AAAI 2026**, not merely a submission. |
| **MCP SoK (Hou 2025)** | Two cosmetic slips: lifecycle is 4 phases (not 3); "SkillState.version" does not exist (version field is on Document). |
| **Heiding spear-phishing (2024)** | CSRI `confidentiality` downgraded from clean `yes` to **partial** — mail-leak does not move conf_loss directly; needs a leak→secret-read/impersonation chain. |
| **M-Spoiler / MAGPIE / ST-WebAgentBench / TAMAS** | Headline `csri_channels` / `llm_realizable` mappings are **wishful in the metadata header** but correctly retracted in the body; AiTM is prior-art cited by TAMAS, not a TAMAS contribution. |

**Dropped as unconfirmable / clearly out-of-scope (13 papers).** All 13 were verified **real** (none hallucinated); they were dropped for substrate/realizability reasons — almost all are single-agent vision/DNN/sponge attacks needing a visual DOM, gradient access, or a model-weights/fine-tune substrate ACES does not have, with no agent-to-agent contagion: *Attacking VLM Agents via Pop-ups; WebInject; VPI-Bench; BadSkill; Agent Smith; Sponge Examples; Sponge Poisoning; DeepSloth; NMTSloth; Engorgio; Overload; Exfiltration-from-ChatGPT; R-Judge.* Several of these also had `code_available` correctable to **true** (Pop-ups, VPI-Bench, Exfiltration-from-ChatGPT) but the correction does not change their out-of-scope status.

**Confidence read.** No paper in the kept set was found to be fabricated; every "keep" was code- or venue-verified. The dominant honest caveat across the corpus is **contagion over-attribution** — `contagion=true` is frequently an ACES-side extrapolation (one poisoned artifact fanned out via republish/blast-radius) rather than a phenomenon the cited single-agent paper demonstrates. The second recurring caveat is **metric pinning** — for token_drain/energy-latency and prompt-extraction papers the relevant CSRI channel is structurally near-zero on the frozen substrate. Treat the contagion claims for Pulipaka, TOMA's topology result, MAS-Execute-Code, Lupinacci, and WASP as **inferred, not paper-backed**, and any `code_available=false` field in the flagged rows above as **suspect** (multiple were wrong in the conservative direction).

---

## Appendix — arXiv IDs flagged for verification

Several arXiv IDs above fall in **future-dated ranges** (2026 papers: 2602.06547, 2604.02837, 2605.11418, 2601.05504, 2602.15654, 2605.15338, 2512.16962, 2601.10955, 2512.04129) relative to a Jan-2026 knowledge cutoff. The verifier marked these `confirmed_exists=true`, but the **exact arXiv identifiers should be re-checked against arxiv.org before they are written into any attack template's provenance string** — an inflated/auto-generated ID is the most likely residual error in a lit-review-by-LLM, even when the paper itself is real.
