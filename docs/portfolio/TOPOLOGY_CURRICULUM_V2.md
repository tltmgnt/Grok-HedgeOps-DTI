# Topology compatibility and curriculum v2 — Grok-HedgeOps-DTI

Version 2 adapts the explicit-molecular-graph teaching pattern to this repository's actual role. This is documentation and a learning/decision framework; it introduces no mathematical engine, runtime dependency or operational permission.

## Repository decision

| Question | Repository-specific answer |
| --- | --- |
| Architectural role | application |
| Minimum useful mathematics | Directed evidence/workflow graphs; bounded H0 shadow analysis where already implemented |
| Relationships to preserve | Observations, evidence, gaps, verification conditions and review dependencies |
| Concrete operation / capstone | Trace REQUIRED_FIELDS validation with a missing evidence array using offline fixtures; explain why valid JSON does not establish a true recommendation |
| Necessity and scope boundary | News-topology research must remain separate from order authority; this curriculum adds no provider calls or trading permissions |

The decision is a source-based recommendation, not measured proof that a new specialty improves this repository. Start with the existing implementation and compare any proposed abstraction against a simpler alternative.

## Six-criterion compatibility scorecard

Complete one scorecard per proposed candidate and per concrete operation. Leave unmeasured entries unknown. Scores are human judgments from 0 (no fit) to 5 (strong evidenced fit); unknown is not zero. Do not sum an incomplete card. A total out of 30 is a heuristic, not adoption approval, and feasibility or necessity can veto a high total.

| Criterion | Score | Required evidence |
| --- | --- | --- |
| Structural compatibility | Not yet scored | Map the repository objects and the relationships above without losing direction, labels, units or missingness. |
| Transformation support | Not yet scored | Demonstrate the capstone operation on accepted and rejected inputs. |
| Invariant preservation | Not yet scored | State the property preserved and supply a counterexample or perturbation. |
| Computational feasibility | Not yet scored | Measure size, time and memory on bounded fixtures; record limits. |
| Integration compatibility | Not yet scored | Verify existing schemas, APIs and neighboring contracts remain compatible. |
| Mathematical necessity | Not yet scored | Compare with directed evidence/workflow graphs and explain the additional capability, if any. |

## Curriculum

Prerequisites: basic programming, sets, functions and graph vocabulary. Work in six competency-gated sessions, approximately 60–90 minutes each; empirical evaluation is a separate research activity.

| Session | Learning objective | Exercise | Completion evidence |
| --- | --- | --- | --- |
| 1. Model | Identify observations, evidence, gaps, verification conditions and review dependencies. | Draw a minimal valid example and one excluded relationship. | Annotated object/relation inventory with explicit assumptions. |
| 2. Contract | Distinguish schema validity from substantive correctness. | Trace validation and propose malformed, missing and boundary inputs. | Input-to-rejection table grounded in current source. |
| 3. Operation | Explain directed evidence/workflow graphs; bounded h0 shadow analysis where already implemented. | Trace REQUIRED_FIELDS validation with a missing evidence array using offline fixtures; explain why valid JSON does not establish a true recommendation. | Hand trace compared with existing software, or a clearly labeled specification when no runtime exists. |
| 4. Preservation | State what a transformation must preserve. | Rename identifiers, reorder records, then alter one meaningful relation; predict each effect under the actual contract. | Separate invariant, expected change and unsupported transformation. |
| 5. Comparison | Justify mathematical necessity and cost. | Complete the six-criterion card for the existing approach and one proposed alternative; record unknowns honestly. | Evidence-backed recommendation with baseline and explicit veto conditions. |
| 6. Reproduction | Communicate the bounded result. | Reproduce the capstone using existing offline fixtures and record software version, inputs, outputs and limitations. | Reviewable notebook or report distinguishing computation, replay, independent evaluation and authorization. |

## Source-linked reading laboratory

The table is a guided selection of source lines, not an assertion that the whole repository is covered. Line numbers refer to the inspected source blob `10c110413d219313fe37e2bf3f4b1db14771196e` in [agent.py](../../agent.py). Recheck anchors after source changes.

| Line | Statement | Learning check |
| --- | --- | --- |
| [35](../../agent.py#L35) | `def validate_report(content: str) -> dict:` | State the input/output contract and trace one normal and one failing case. |
| [40](../../agent.py#L40) | `raise ValueError("Model response is not valid JSON") from exc` | Construct the triggering input and explain why rejection preserves the contract. |
| [42](../../agent.py#L42) | `raise ValueError("Model response must be a JSON object")` | Construct the triggering input and explain why rejection preserves the contract. |
| [45](../../agent.py#L45) | `raise ValueError(f"Model response missing fields: {', '.join(sorted(missing))}")` | Construct the triggering input and explain why rejection preserves the contract. |
| [48](../../agent.py#L48) | `raise ValueError(f"Model response field {field!r} must be an array")` | Construct the triggering input and explain why rejection preserves the contract. |
| [49](../../agent.py#L49) | `return report` | Predict the returned value and distinguish a computed result from authorization. |
| [52](../../agent.py#L52) | `def analyze(problem: str) -> dict:` | State the input/output contract and trace one normal and one failing case. |
| [54](../../agent.py#L54) | `raise ValueError("Problem must be non-empty text")` | Construct the triggering input and explain why rejection preserves the contract. |
| [59](../../agent.py#L59) | `raise ValueError("Set XAI_API_KEY in your .env file")` | Construct the triggering input and explain why rejection preserves the contract. |
| [61](../../agent.py#L61) | `raise ValueError("Set XAI_MODEL to a model available in your xAI Console")` | Construct the triggering input and explain why rejection preserves the contract. |
| [76](../../agent.py#L76) | `raise ValueError("Model returned an empty response")` | Construct the triggering input and explain why rejection preserves the contract. |
| [77](../../agent.py#L77) | `return validate_report(content)` | Predict the returned value and distinguish a computed result from authorization. |
## Assessment and verification

A learner must explain the model, trace the capstone, identify a counterexample and state the scope boundary. Assess these four competencies equally; a numerical score cannot compensate for an unsupported scientific or operational claim.

Relevant existing checks:

- [tests/test_agent_validation.py](../../tests/test_agent_validation.py)
- [tests/test_alpaca_purchase.py](../../tests/test_alpaca_purchase.py)
- [tests/test_assurance_register.py](../../tests/test_assurance_register.py)

Follow [README](../../README.md) for environment and installed-package instructions. Read scripts before execution; source-reading exercises do not authorize provider calls, model downloads, live orders, hardware actions or messages. Synthetic fixtures establish software behavior only. This documentation change does not report those exercises as already executed.

## Interoperability and adoption gate

Retain explicit domain contracts. Shared assurance records should refer to domain evidence and its assumptions rather than relabeling graph reachability, homology, statistical calibration and epistemic acceptance as interchangeable quantities. The canonical ResearchOs controller remains owned by ResearchOs; this curriculum does not create another controller fork.

Adopt additional mathematics only after a versioned experiment demonstrates a useful operation, the scorecard has evidence, the simpler baseline is inadequate and existing conformance checks remain satisfied. News-topology research must remain separate from order authority; this curriculum adds no provider calls or trading permissions.
