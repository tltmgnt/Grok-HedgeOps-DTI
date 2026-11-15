# Psychometrician × ResearchOS × TECT

## Proposed extension: Psychometric Epistemic Assurance

PEA is a proposed measurement and calibration layer for evaluating scoped
assurance decisions. It separates the quality of an assurance measurement from
the factual correctness of the claim being measured. Statistical reliability,
evaluator consensus and controller stability do not establish truth.

ResearchOS supplies claims, evidence, provenance and reproducibility records;
psychometrics supplies proposed validity, reliability, calibration and measurement
uncertainty methods; TECT controls validation, adversarial challenges and
governance. The intended decision is accepted, rejected or uncertain within a
versioned evidence scope.

| Psychometric discipline | Proposed TECT application | Required evaluation |
|---|---|---|
| Construct validity | Define what each assurance measure means and excludes | Expert rubric review, convergent/discriminant evidence and external criteria |
| Reliability | Evaluate consistency across evaluators, models and repeated trials | Aligned repeated ratings and evaluator/task effects; agreement alone is insufficient |
| Item Response Theory | Model validation task difficulty and discrimination | Adequate task bank, identified model and held-out fit; check local dependence |
| Factor analysis | Investigate latent evidence-quality dimensions | Exploratory then independent confirmatory evaluation; inspect invariance |
| Differential item functioning | Detect conditional task differences across models or domains | Compare matched latent proficiency, account for multiplicity and inspect substantive causes |
| Calibration | Compare stated probability with observed adjudicated outcomes | Disjoint fitting/evaluation sets, Brier and bin diagnostics with uncertainty |

These are candidate methods, not fitted or validated models supplied by this change.

## Mathematical research specification

Let i index a task/claim, j an evaluator or system, r a repeat, and d a domain.
Record an observable rubric vector x_ijrd, a predicted probability p_ijrd of an
externally defined binary outcome y_i=1, source dependencies and policy version.
An unresolved y_i is missing with an explicit reason; it is not a negative label.
Define the construct and its intended use before selecting a composite score.

A candidate multi-facet task-response model is
`P(X_ijrd=1 | theta_j, b_i, a_i, u_d, v_r) = logistic(a_i*(theta_j-b_i)+u_d+v_r)`.
Here X is success on a defined validation task, theta is system/evaluator
proficiency, b difficulty, a discrimination, and u/v domain and repeat effects.
This is a proposed model family, not a truth model. Identification constraints,
crossed/nested design, sufficient observations, local independence, model fit
and out-of-sample checks must be specified. Shared sources and repeated model
outputs may violate independence. DIF analyses would test group-specific item
parameters conditional on proficiency; a detected difference needs interpretation.

A candidate evidence measurement model is `x = Lambda*z + epsilon`.
The latent dimensions z and loading matrix Lambda need operational definitions,
scale identification, measurement invariance and independent confirmation.
Do not infer validated dimensions from names assigned to factors.

For adjudicated binary observations, the implemented descriptive scores are
`Brier = mean((p-y)^2)` and
`ECE = sum_b (n_b/n)*abs(mean_b(p)-mean_b(y))` for declared equal-width bins.
The implemented pairwise kappa is `(p_observed-p_expected)/(1-p_expected)`;
undefined denominators produce null. Neither a fitted calibrator nor inferential
uncertainty intervals are implemented. For study inference, preregister a
task/source-cluster-aware interval method and account for repeated ratings,
adjudication uncertainty and selection effects.

The advisory policy aggregates separately assessed obligations. A known failed
obligation rejects promotion; unresolved, errored or skipped obligations retain
uncertainty; complete passing obligations with referenced evidence permit scoped
advisory acceptance. An acceptance decision is conditional on evidence, policy,
scope and authorized review, never a universal probability of truth. Existing
TECT controllers remain authoritative and are not modified by this module.

## Testable hypotheses and pilot

The primary question is whether psychometrically calibrated evidence and
validation measures improve accuracy, reproducibility and interpretability of
TECT assurance decisions. The null is no improvement on the preregistered primary
endpoint. Compare humans, a single model, unstructured multi-agent systems and
TECT on identical blinded tasks. Include a TECT-without-PEA ablation to isolate
measurement effects from controller effects.

Primary hypothesis: PEA reduces held-out false acceptance at matched coverage.
Secondary hypotheses: improved held-out Brier score, independent reproduction
and audit reconstruction time without unacceptable review/compute cost. Test
reliability separately from correctness. Report rejected and uncertain cases,
coverage, false rejection, missing labels and every denominator. Preregister
effect sizes, sample size/power, thresholds, stopping rules, adjudication and
multiple-comparison treatment before examining held-out outcomes.

Split by task and source cluster into fitting, selection and held-out partitions.
Blind adjudicators to conditions, randomize output ordering, retain disagreements
and adjudication reasons, measure residual unblinding, and lock model/rubric/policy
versions. Use independent reproduction with a declared method. Report negative
results and calibration drift across domains; do not silently transfer thresholds.
See [machine-readable pilot plan](../../pea_assurance/pilot_protocol.json).

## Implementation and professional positioning

The [offline PEA module](../../pea_assurance/README.md) implements descriptive
binary calibration, pairwise agreement and an advisory obligation aggregator,
with synthetic software tests. It does not implement IRT/factor/DIF fitting,
authenticated evidence resolution, live controller promotion or a completed study.
Each repository's existing domain and adapter requirements remain applicable.

A psychometrician would own construct definitions, rubric development, reliability
and invariance studies, calibration design and measurement uncertainty, alongside
domain experts and independent adjudicators. This is a potential independent
research and consulting specialization for institutional evaluation teams.
JPMorgan Chase is a possible audience named by the owner, not a partner, client,
employer or endorser asserted by these repositories.

No independent empirical improvement or readiness is claimed. The next research
milestone is a reviewed construct/rubric and preregistered blinded pilot, followed
by genuine observations and independent analysis.
