# RESEARCHOS
# Topological Epistemic Control Theory (TECT)
## DARPA-style technical white paper — draft

**An Epistemic Control and Assurance Infrastructure for AI-Generated Knowledge**

**Purpose:** Technical concept development for DARPA-style program engagement, SBIR/STTR positioning, national-laboratory research, and future formal proposal development.  
**Status:** Conceptual research draft. Not a response to a specific active solicitation. No DARPA endorsement, award, validated performance improvement, or legal certification is asserted.  
**Author-supplied draft date:** September 2026.  
**Repository editorial revision:** November 8, 2026. Version 0.1.0.  
**Editorial treatment:** Repository edition of the owner's supplied concept: all 25 topic sections and three appendices retained in edited form. Mathematical conditions clarified in §6; completed-program status and source limitations clarified in §§19 and 23. Research objectives remain distinct from demonstrated repository capabilities. See [integration status](INTEGRATION.md).

## Executive summary

AI systems generate hypotheses, analyses, plans, designs and scientific explanations quickly. In consequential environments, the central assurance question is which assertions deserve acceptance, which remain uncertain, what evidence and assumptions support them, what challenges could invalidate them, and which mission or governance constraints apply.

ResearchOS proposes infrastructure for that question. Its proposed foundation, Topological Epistemic Control Theory (TECT), represents knowledge as a changing graph of claims, evidence, reasoning relationships, provenance, confidence, adversarial tests and governance state. A generated assertion is a candidate state, not an accepted result. Validation, adversarial challenge, reproduction and governance predicates control its subsequent promotion.

**AI generation ≠ knowledge acceptance.**

The research program would compare discovery throughput, failure detection, reproducibility, robustness, auditability and review burden against human, single-model and unstructured multi-agent baselines. Program relevance is an assessment of thematic overlap with published DARPA material, not a determination of eligibility or an assurance of funding. AI Forge describes interpretability, control and robustness research; ANSR discusses heterogeneous assurance evidence; completed Assured Autonomy work supplies a precedent for continual assurance [S1–S4].

## 1. Heilmeier-style program framing

| Question | TECT / ResearchOS answer |
|---|---|
| What are you trying to do? | Control the transition from generated assertions to validated, auditable epistemic states. |
| How is it done today? | Human inspection, benchmarks, source checks, simulation, red teaming and agent workflows often lack a shared persistent state model. This characterization needs a systematic related-work review. |
| What is new? | Proposed integration of provenance, evidence independence, reasoning topology, adversarial testing, validation and governance in one transition framework. Priority and novelty have not been established. |
| Who cares, and what difference could success make? | Researchers, evaluators and operators needing traceable evidence behind consequential AI-assisted conclusions. |
| What are the risks? | Correlated evidence, incomplete attacks, false convergence, rigid formalism, metric gaming and human bottlenecks. |
| How much? | A costed work breakdown must follow the selected solicitation and measured compute and personnel needs. No award budget or funding commitment is specified. |
| How long? | A Phase I-scale effort would establish feasibility; Phase II would test scale, generalization and transition. Duration remains solicitation-dependent. |
| What are the mid-term and final exams? | Executable transition semantics and counterexamples at midpoint; matched pilot comparisons, reproducibility records and a falsifiable feasibility report at completion. |

This framing follows DARPA's eight-question catechism [S1]. Submission details must come from the actual opportunity [S5–S6].

## 2. Problem statement

Plausibility and internal coherence do not establish correctness. A consequential claim needs evidence, dependency tracking, provenance, validation history, failure modes and an explicit acceptance scope. New observations, changed assumptions or upstream contradictions must reopen affected conclusions.

The core question: given claims K, evidence E, reasoning relationships R, adversarial operators A, validation operators V and governance constraints Γ, is a proposed transition admissible, and is the resulting state sufficiently supported for the intended use?

`𝓔_(t+1) = G(𝓔_t, T, Γ, A, V)`

The epistemic-state symbol 𝓔 is distinct from its evidence component E. This is a modeling proposal, not an established physical law.

## 3. Scientific and technical novelty

Proposed contributions are a stateful claim graph; structured reliability and evidence-independence attributes; challenges embedded within ordinary transitions; governance predicates preserved on accepted transitions; stability relative to a named metric and attack family; explicitly conditional potential-descent results; and assurance measures beyond raw confidence. These ideas require comparison against assurance cases, truth-maintenance systems, provenance graphs, belief revision, formal verification, runtime assurance and reproducible-science infrastructure before novelty can be claimed.

**Central question:** Can a formal epistemic controller improve reliability and auditability while preserving useful throughput?

Secondary questions concern scalable claim provenance, duplicate-evidence detection, marginal value of adversarial operators, unsupported-promotion prevention, unseen-perturbation prediction, and audit reconstruction time.

## 4. TECT formal model

`𝓔_t = (K_t, R_t, E_t, S_t, P_t, Γ_t)`

K contains artifacts; R contains reasoning/dependency edges; E contains validation evidence; S contains claim states; P contains provenance; Γ contains active constraints. The knowledge topology is `T=(K,R)`. Edge types include supports, contradicts, derives, depends-on, reproduces, qualifies and invalidates.

A claim state may be modeled as `s(k)=(q,p,v,a,g)`: confidence, provenance completeness, validation status, adversarial robustness and governance status. Each coordinate needs units, scope, calibration and missing-value semantics; a tuple alone does not define a calibrated assurance score.

G evaluates proposed operations against versioned predicates and returns an accepted next state or a recorded rejection. Policy updates themselves require versioned authorization and review; otherwise “preservation” could be evaded by changing the policy.

## 5. Evidence, validation and adversarial operators

Each evidence record retains source identity, method, timestamp, computational or experimental origin, dependency information, authorized access scope and an estimate of independence. A proposed diagnostic is:

`D_v(k) = (Σ_i w_i q_i r_i d_i) / (1 + deg_R(k))`

Weights, quality, reliability and independence require domain definitions. The chosen edge-degree convention must be recorded. This density is a research metric, not a probability or truth guarantee; repeated sources must not count as independent experiments.

Attack classes include contradiction injection, source poisoning, model disagreement, counterexamples, assumption violations, distribution shifts, prompt injection, corrupted evidence and strategic manipulation. Tests run in bounded research environments.

| Outcome | Meaning |
|---|---|
| PASS | Required, scoped conditions are satisfied. |
| FAIL | A required condition is violated or a material contradiction established. |
| UNCERTAIN | Available evidence establishes neither acceptance nor rejection. |

Absence of evidence must not be silently converted into PASS or FAIL. Test execution errors and skipped checks need their own recorded reason, usually yielding UNCERTAIN for the corresponding scientific obligation.

## 6. Stability, convergence and conditional results

### 6.1 Metric

Choose a domain-appropriate distance `d(𝓔1,𝓔2)`, potentially combining graph changes, confidence, evidence, provenance and governance changes. Normalization and metric axioms require specification; an arbitrary weighted score is not automatically a metric.

### 6.2 Stability

`sup_(A∈𝓐) d(A(𝓔*),𝓔*) < ε`

This is stability only with respect to the declared attack family, metric and tolerance. Finite tests establish observations for executed attacks; they do not establish the supremum over an unenumerated family. Stability is not truth.

### 6.3 Potential

`Φ(𝓔)=αU+βC+γP_def+δG_def+ηA_def`

U measures unsupported claims; C unresolved contradictions; P_def provenance deficiencies; G_def governance deficiencies; A_def unresolved vulnerabilities. Nonnegative weights, scales and a lower bound must be defined. Deficiency symbols distinguish penalties from provenance and attack operators.

### 6.4 Corrected verification-convergence proposition

**Finite case:** Assume a finite reachable state space, a fixed stable target set 𝓢, and a terminating accepted transition available at every visited non-target state that strictly decreases a real-valued potential. If transitions continue to be selected, no state can repeat before target entry, so target entry occurs within at most the number of reachable non-target states. A blocked controller, time-varying policy or missing transition violates these assumptions.

**General case with uniform progress:** If `Φ≥Φ_min` and every executed transition outside 𝓢 decreases Φ by at least a fixed `μ>0`, with transitions continuing to execute, the number of non-target transitions is at most `floor((Φ(𝓔_0)-Φ_min)/μ)`. Thus a run cannot remain outside 𝓢 indefinitely under those assumptions.

**Correction to the supplied draft:** Compactness plus strict decrease alone does not imply finite entry. On `[0,1]`, `x_(t+1)=x_t/2`, `Φ=x`, target `{0}`, a positive starting point never reaches the target in finite time. Other asymptotic convergence results need additional continuity, invariance and limit-set conditions. Bounded attacks alone do not supply uniform progress. These propositions are elementary conditional results; the research task is to test whether a useful controller satisfies their assumptions.

### 6.5 Corrected margin-resilience proposition

Let acceptance require a scalar score `f(𝓔)>τ`, with current margin `M=f(𝓔)-τ`. If f is L-Lipschitz over the declared perturbation region and `d(𝓔,A(𝓔))≤δ`, then `M>Lδ` preserves this score threshold. Vector constraints need a bound for each coordinate. The supplied `M>δ` implication is justified only with an appropriate unit-Lipschitz normalization. This does not preserve authorization or other discontinuous predicates unless separately checked.

## 7. Governance preservation

For a fixed versioned predicate Γ, admit only transitions whose destination satisfies Γ. If Γ holds initially, induction establishes Γ for accepted states. This is a property of encoded predicates and transition enforcement; it does not establish completeness of policy or correctness of the governance engine.

Examples: authorized actors for sensitive promotions; traceable provenance for critical claims; restrictions on evidence disclosure; safety boundaries; and deployment checks. Rejections retain the triggering constraint and rationale. Changes to Γ trigger re-evaluation rather than retroactively relabeling prior decisions.

## 8. Epistemic state machine

Proposed nominal stages are GENERATED → UNVERIFIED → SUPPORTED → ADVERSARIAL_TEST → REPRODUCED → VALIDATED → STABLE → ASSURED. These are policy-specific states, not synonyms for truth. Record the policy version, evidence versions and scope at every transition.

| State | Meaning | Typical next condition |
|---|---|---|
| Generated | Candidate registered | Identity and provenance captured |
| Unverified | Insufficient evidence | Support collected |
| Supported | Preliminary threshold met | Required attacks executed |
| Adversarial test | Scoped challenges evaluated | Failures resolved or uncertainty recorded |
| Reproduced | Independent method or execution confirms result | Required validations complete |
| Validated | Defined tests pass | Stability assessed |
| Stable | Robust within named perturbation scope | Governance and acceptance review |
| Assured | Mission-specific acceptance criteria met | Continuous monitoring |
| Contested | Material challenge, expiry or dependency change | Resolution, rejection or revised claim |

New evidence can reopen any promoted state. Changes must invalidate or re-evaluate dependent claims transitively, with cycles handled explicitly.

## 9. System architecture

Generation feeds claim extraction and the epistemic graph. Validation and adversarial engines attach evidence. The controller evaluates transitions under governance predicates. An assurance ledger records results for a mission interface.

| Component | Responsibility |
|---|---|
| Agent layer | Propose hypotheses, analyses, plans and designs |
| Claim extraction | Convert outputs into typed, reviewable assertions |
| Epistemic graph | Store evidence, dependencies, contradiction and provenance |
| Validation engine | Run checks, simulations, reproductions and formal methods |
| Adversarial engine | Execute bounded challenge operators |
| TECT controller | Evaluate transition predicates and diagnostics |
| Governance engine | Enforce encoded authorization, safety and data policies |
| Assurance ledger | Preserve versioned decisions and evidence references |
| Mission interface | Expose assurance scope and unresolved risks |

Claim objects need stable IDs, versions, statements, origins, evidence references, dependencies, contradictions, test history, governance state, timestamps and acceptance scope. A hash establishes content identity; an unanchored hash chain does not independently authenticate origin or prevent wholesale history replacement.

## 10. Experimental program

| Condition | Matched task treatment |
|---|---|
| A | Human researchers with conventional tools |
| B | One foundation model with standard prompting |
| C | Unstructured multi-agent workflow |
| Experimental | ResearchOS with TECT-controlled transitions |

Control task difficulty, model versions, data access, compute budgets and reviewer expertise. Preregister inclusion criteria, adjudication rules, blinded holdouts and stopping rules. Report uncertainty intervals, failures and ablations; include controller overhead and selection effects.

| Metric | Definition / purpose |
|---|---|
| Validated throughput | Accepted, externally evaluated results per unit time |
| False-claim rate | Materially incorrect evaluated claims / evaluated claims |
| Reproduction rate | Independent successful reproductions / selected attempts |
| Adversarial detection | Material failures found / known or adjudicated failures |
| Audit reconstruction time | Time to recover rationale and provenance |
| Validation coverage | Required claims validated / claims requiring validation |
| Human review burden | Reviewer hours per validated result |
| Stability | Change under a preregistered perturbation set |

Denominators, censoring and domain ground truth must be explicit. No results for this proposed four-arm evaluation are reported here.

## 11. Demonstration 1 — autonomous materials discovery

Propose candidates meeting thermal, mechanical, environmental and radiation constraints; formalize hypotheses; gather authorized literature/database evidence; run physical simulations; challenge assumptions; reproduce through independent methods; promote survivors; deliver an evidence package. Primary measure: externally validated discovery throughput. Secondary measures: false discoveries, reproducibility, compute and review cost. A toy Hamiltonian or synthetic topology result is not an autonomous materials-discovery demonstration.

## 12. Demonstration 2 — cyber threat analysis

Convert reports and authorized observations into hypotheses with source dependencies. Test contradictions, alternative explanations and simulated adversarial behavior in a controlled environment. Deliver confidence states with unresolved contradictions and explicit reassessment triggers. This concept does not authorize operational intrusion or autonomous response.

## 13. Demonstration 3 — mission planning assurance

Represent objectives, constraints, resources, assumptions and contingencies as structured claims. Evaluate candidate plans through simulation, constraint checking and failure analysis. Acceptance remains scoped to modeled conditions and operator authority; simulated success is not operational assurance.

## 14. Demonstration 4 — AI system assurance

The flagship proposed demonstration is model-agnostic: AI output → claim extraction → evidence graph → adversarial tests → independent reproduction → assurance state. Evaluate several model families and agent architectures with held-out tasks. The intended strategic role is an assurance layer above models and below consequential decisions. Published DARPA themes support relevance, not performance or endorsement [S2–S4].

## 15. Technical risks and mitigations

| Risk | Failure | Proposed mitigation |
|---|---|---|
| Evidence correlation | Repeated error counted repeatedly | Provenance clustering and independence estimates |
| Metric gaming | Assurance score replaces correctness | Holdouts, hidden challenges and independent adjudication |
| Incomplete attacks | Important failures missed | Adaptive attacks plus unseen evaluation sets |
| False convergence | Stable incorrect belief | External evidence and counterexamples |
| Graph complexity | Unmanageable dependencies | Hierarchical abstraction with auditable refinement |
| Human bottleneck | Excessive expert effort | Risk-based triage and measured review burden |
| Rigid governance | Useful work blocked | Explicit, authorized exceptions and tiered states |
| Model collusion | Shared-model error repeated | Diverse models and independent execution paths |

The principal scientific risk is stable false belief. Stability is not defined as truth. Mitigation effectiveness must itself be evaluated.

## 16. Phase I technical plan

| Milestone | Objective | Exit evidence |
|---|---|---|
| M1 | Formal specification | Definitions, assumptions, counterexamples, transition semantics |
| M2 | Graph prototype | Versioned claims, evidence, dependencies, contradictions |
| M3 | Controller | Accepted/rejected transitions logged and replayed |
| M4 | Adversarial engine | At least three scoped attack classes |
| M5 | Benchmark | Matched tasks and preregistered evaluation protocol |
| M6 | Pilot | One bounded domain demonstration |
| M7 | Feasibility report | Quantitative comparison, uncertainty and failure analysis |

Prioritize implementability and distinguishability from unstructured workflows. Repository tests are development checks; they do not by themselves satisfy M5–M7.

## 17. Phase II expansion

Scale multi-agent claim graphs; add independent model families and verifier adapters; enable change-triggered revalidation; evaluate at least three domains; expose operator dashboards and machine-readable records; test unseen attacks; pursue external assessment and transition interfaces. The goal is statistically supported improvement without unacceptable throughput loss. Staffing, duration and award structure depend on the opportunity.

## 18. Transition strategy

| Target | Potential capability |
|---|---|
| Defense research | Scientific and engineering assurance |
| Intelligence analysis | Evidence-linked hypotheses and analytic confidence |
| Mission planning | Constraint and adversarial plan evaluation |
| National laboratories | Reproducible AI-assisted research |
| AI developers | Evaluation and assurance APIs |
| Independent evaluators | Evidence and reproducibility infrastructure |
| Commercial R&D | Traceable research workflows |

ResearchOS is proposed infrastructure, with APIs and machine-readable evidence records adaptable to multiple interfaces. None of these deployments is asserted as completed by this paper.

## 19. Policy and regulatory relevance

The GPO introduced text confirms H.R. 9925, the FRONTIER Act, introduced July 23, 2026 in the 119th Congress, and describes proposed independent-verification organization licensing and frontier-model assessment mechanisms [S7]. This edition references the **introduced proposal**, not an enacted obligation. The current Congress.gov page could not be retrieved during the November 8 editorial check; the introduced text alone cannot establish the latest legislative status. Recheck the live legislative record before proposal submission or legal reliance.

Design ResearchOS around general verification needs rather than assuming enactment, future rules, eligibility as a licensed evaluator, or compliance with a particular statute. This paper is technical concept development, not legal advice or a compliance determination.

## 20. Quantitative acceptance criteria

| Category | Illustrative research objective |
|---|---|
| Discovery throughput | ≥5× selected matched baseline |
| Independent reproduction | ≥95% on reproducibility-selected results |
| Required validation | ≥95%; 100% of designated critical claims |
| Audit reconstruction | ≥50% reduction in elapsed review time |
| Failure detection | Statistically supported improvement |
| Unseen-attack robustness | Statistically supported improvement |
| Encoded governance | Zero observed violating accepted transitions in controlled tests |
| Human efficiency | Meaningful reduction in hours per externally validated result |

These are proposed targets, not achieved results. Select final thresholds after pilot characterization; report sample sizes, uncertainty and generalization limits. Zero observed violations does not prove zero possible violations.

## 21. Intellectual property and research data strategy

Maintain a versioned TECT specification; modular ResearchOS implementations; machine-readable schemas; separately versioned domain adapters and benchmarks; authorized or synthetic data; explicit experiment configurations; and defined software/data rights before teaming. Separate proprietary implementation from publishable mathematical work. Adding this paper does not change a repository's license or grant rights to third-party sources. Solicitation-specific IP, security and submission terms require separate review.

## 22. Recommended team

| Role | Capability |
|---|---|
| Principal investigator | Assurance, formal methods and systems research |
| TECT lead | Epistemic logic, mathematical modeling and dynamics |
| AI systems lead | Models, agents, orchestration and evaluation |
| Verification lead | Reproducibility, tests and experimental design |
| Adversarial lead | Threat modeling and robustness evaluation |
| Domain lead | Relevant scientific or operational expertise |
| Software lead | Graph systems, provenance, APIs and distributed execution |
| Transition lead | Government engagement, delivery and commercialization |

Phase I roles may overlap. Independent evaluation and domain expertise should become explicit work packages in Phase II. No team commitments are implied.

## 23. DARPA alignment

AI Forge's June 2026 material identifies interpretability, control and adversarial robustness themes [S2]. Its original program URL redirected to SI Forge during this editorial check; the current SI Forge page retains interpretability, control and adversarial robustness as research themes [S8]. Current opportunity names, scope and eligibility must be checked anew. ANSR describes assurance using heterogeneous evidence, robustness and predictability [S3]. Assured Autonomy is explicitly marked **completed** by DARPA and is cited as a historical research precedent, not an open funding program [S4].

The proposed positioning is continual epistemic assurance of generated knowledge and decisions. Thematic alignment is the author's assessment. It does not establish a solicitation match, DARPA endorsement, novelty, or transition commitment.

## 24. Expected impact

If the experimental program succeeds, organizations could accelerate research while retaining hypothesis/knowledge distinctions; expose competing explanations earlier; test assumptions explicitly; emit machine-readable assurance records; support independent evaluators; and reconstruct why conclusions were accepted, challenged or revised. These are conditional expected benefits requiring empirical validation.

## 25. Conclusion

ResearchOS proposes an epistemic control layer above heterogeneous models and below consequential decisions. Its intended process is Generate → Represent → Validate → Attack → Reproduce → Govern → Stabilize → Assure. The ordering can vary by policy, but promotion must remain explicit and revisable.

TECT does not claim that mathematical stability proves truth. It provides a proposed language for stating evidence, tested attacks, remaining assumptions and acceptance conditions. Falsifiable comparisons must determine whether it improves on existing assurance methods. Every consequential conclusion should expose its claim, support, potential defeaters and current permission scope.

## Appendix A — notation

| Symbol | Meaning |
|---|---|
| 𝓔 | Complete epistemic state |
| K | Artifacts / claims |
| R | Reasoning and dependency relationships |
| E | Evidence records |
| S | Claim state map |
| P | Provenance |
| T | Claim topology (K,R) |
| G | Transition operator |
| V | Validation operators |
| A, 𝓐 | An adversarial operator; declared attack family |
| Γ | Versioned governance predicate / constraints |
| d | Specified state distance |
| Φ | Epistemic potential |
| D_v | Proposed validation density |
| S_e | Proposed stability score; domain definition pending |
| ORI | Proposed operational-readiness index; definition and calibration pending |

## Appendix B — initial research questions

1. Which distances predict consequential epistemic instability?
2. How can evidence independence be estimated across heterogeneous sources?
3. Which adversarial operators yield the most marginal value per unit cost?
4. Does observed stability generalize to unseen attacks?
5. How should correlated evidence affect calibration?
6. Can governance predicates compose without excessive rigidity?
7. Which abstractions support million-claim graphs while retaining auditability?
8. How should risk determine expert review placement?

## Appendix C — proposal preparation notes and source register

This is a concept paper, not a solicitation-compliant proposal. Determine actual scope, format, page limits, award type, milestones, cost rules, IP/data rights and security requirements from the selected notice. Do not infer an active opportunity from a program-description page. No proposal or external message is submitted by this repository update.

Sources checked November 8, 2026. References support the specific factual descriptions above; they do not validate TECT, its novelty or performance. No long source quotations are reproduced.

- **S1:** DARPA, [Heilmeier Catechism](https://www.darpa.mil/about/heilmeier-catechism).
- **S2:** DARPA, [AI Forge announcement](https://www.darpa.mil/news/2026/ai-forge-accelerating-ai-breakthroughs-national-security) and [June 2026 critical challenges report](https://www.darpa.mil/sites/default/files/attachment/2026-06/ai-forge-report.pdf). Original [AI Forge URL](https://www.darpa.mil/research/programs/ai-forge) redirects to [SI Forge](https://www.darpa.mil/research/programs/si-forge); recheck current opportunities.
- **S3:** DARPA, [Assured Neuro Symbolic Learning and Reasoning](https://www.darpa.mil/research/programs/assured-neuro-symbolic-learning-and-reasoning).
- **S4:** DARPA, [Assured Autonomy](https://www.darpa.mil/research/programs/assured-autonomy), completed-program reference.
- **S5:** DARPA, [research opportunities](https://www.darpa.mil/work-with-us/opportunities). Specific solicitation requirements not evaluated in this draft.
- **S6:** DARPA, [Small Business Programs](https://www.darpa.mil/work-with-us/for-small-businesses). Availability and eligibility need an opportunity-specific check.
- **S7:** U.S. GPO, [H.R. 9925 introduced text](https://www.govinfo.gov/content/pkg/BILLS-119hr9925ih/html/BILLS-119hr9925ih.htm), July 23, 2026. [Congress.gov live record](https://www.congress.gov/bill/119th-congress/house-bill/9925) was inaccessible to the editorial reader; latest status not independently confirmed.

- **S8:** DARPA, [SI Forge current program page](https://www.darpa.mil/research/programs/si-forge), checked November 8, 2026.
