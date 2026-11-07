"""EFO records are immutable, traceable, falsifiable, and paper-only."""
from dataclasses import replace
import copy
import pytest
from hedgeops_team.efo import Observation, register_test, evaluate_test, verify_chain, export_chain, verify_export

T0="2026-11-01T00:00:00Z"
T1="2026-11-02T00:00:00Z"
T2="2026-11-03T00:00:00Z"
T3="2026-11-04T00:00:00Z"
T4="2026-11-05T00:00:00Z"

def chain():
    observed = Observation("observation", T0, T1, "fixture:prices", "Price was 100", {"close": 100})
    fact = Observation("fact", T1, T1, "researcher", "Observed price equals 100", {"close": 100}, (observed.digest,))
    hypothesis = Observation("hypothesis", T1, T2, "researcher", "Price will rise above 101", {"target": 101}, (fact.digest,))
    test = register_test(hypothesis, criterion="close", operator="gt", threshold=101, registered_at=T2, horizon_end=T3)
    outcome = evaluate_test(test, outcome_at=T3, recorded_at=T4, source_id="fixture:outcome", observed_value=102)
    return (observed, fact, hypothesis), (test,), (outcome,)

def test_chain_and_export_are_reproducible():
    records, tests, outcomes = chain()
    assert verify_chain(records, tests, outcomes)
    assert export_chain(records, tests, outcomes) == export_chain(*chain())
    assert verify_export(export_chain(records, tests, outcomes))

def test_falsification_not_automatically_success():
    records, tests, _ = chain()
    outcome = evaluate_test(tests[0], outcome_at=T3, recorded_at=T4, source_id="fixture", observed_value=100)
    assert outcome.verdict == "falsified"
    assert verify_chain(records, tests, (outcome,))

def test_tampered_verdict_fails():
    records, tests, outcomes = chain()
    assert not verify_chain(records, tests, (replace(outcomes[0], verdict="falsified"),))

def test_tampered_export_fails():
    document = export_chain(*chain())
    modified = copy.deepcopy(document)
    modified["payload"]["observations"][0]["claim"] = "fabricated"
    assert not verify_export(modified)

def test_recomputed_digest_does_not_bypass_lineage():
    document = export_chain(*chain())
    modified = copy.deepcopy(document)
    modified["payload"]["observations"][0]["claim"] = "fabricated"
    from hedgeops_team.audit import digest_payload
    modified["digest"] = digest_payload(modified["payload"])
    assert not verify_export(modified)

def test_missing_parent_rejected():
    records, tests, outcomes = chain()
    assert not verify_chain(records[1:], tests, outcomes)

def test_fact_requires_evidence():
    with pytest.raises(ValueError, match="linked evidence"):
        Observation("fact", T1, T1, "researcher", "claim", {})

def test_future_observation_rejected():
    with pytest.raises(ValueError):
        Observation("observation", T2, T1, "fixture", "claim", {})

def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        Observation("observation", "2026-11-01", T1, "fixture", "claim", {})

def test_test_registration_must_precede_horizon():
    records, _, _ = chain()
    with pytest.raises(ValueError):
        register_test(records[-1], criterion="close", operator="gt", threshold=101, registered_at=T3, horizon_end=T3)

def test_early_outcome_rejected():
    _, tests, _ = chain()
    with pytest.raises(ValueError, match="after horizon"):
        evaluate_test(tests[0], outcome_at=T2, recorded_at=T4, source_id="fixture", observed_value=102)

def test_nonpaper_records_rejected():
    with pytest.raises(ValueError):
        Observation("observation", T0, T1, "fixture", "claim", {}, paper_only=False)

def test_no_orphan_outcomes():
    records, tests, outcomes = chain()
    assert not verify_chain(records, (), outcomes)

def test_no_unlinked_fact_as_hypothesis():
    records, tests, outcomes = chain()
    assert not verify_chain((records[0], records[2]), tests, outcomes)

def test_nonfinite_measurement_rejected():
    with pytest.raises(ValueError):
        Observation("observation", T0, T1, "fixture", "claim", {"close": float("nan")})

def test_duplicate_links_rejected():
    records, _, _ = chain()
    with pytest.raises(ValueError):
        Observation("hypothesis", T1, T2, "researcher", "claim", {}, (records[0].digest, records[0].digest))
