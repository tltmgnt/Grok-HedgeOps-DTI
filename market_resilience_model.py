"""Offline synthetic resource-allocation model. No market or broker connections."""
import copy
import hashlib
import json
import math


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value, name, low=0, high=1000000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name + " must be a bounded integer")
    return value


def validate(study):
    if not isinstance(study, dict) or study.get("version") != 1 or type(study.get("version")) is not int:
        raise ValueError("version 1 required")
    if study.get("mode") != "synthetic":
        raise ValueError("only synthetic studies are supported")
    for key in ("name", "source", "review"):
        if not isinstance(study.get(key), str):
            raise ValueError(key + " must be text")
    if not study["name"].strip():
        raise ValueError("name required")
    integer(study.get("capacity"), "capacity")
    requests = study.get("requests")
    if not isinstance(requests, list) or len(requests) > 500:
        raise ValueError("use at most 500 requests")
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        for key in ("id", "participant"):
            if not isinstance(request.get(key), str) or not request[key].strip():
                raise ValueError(key + " required")
        integer(request.get("units"), "units", 1)
    repairs = study.get("repairs")
    if not isinstance(repairs, list) or not 1 <= len(repairs) <= 10:
        raise ValueError("use 1–10 repair candidates")
    names = set()
    for repair in repairs:
        if not isinstance(repair, dict) or set(repair) != {"name", "deduplicate", "participantCap", "allocation"}:
            raise ValueError("repair requires name, deduplicate, participantCap, allocation only")
        name = repair["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("unique repair names required")
        names.add(name)
        if type(repair["deduplicate"]) is not bool:
            raise ValueError("deduplicate must be boolean")
        if repair["participantCap"] is not None:
            integer(repair["participantCap"], "participantCap", 1)
        if repair["allocation"] not in ("fifo", "pro-rata"):
            raise ValueError("allocation must be fifo or pro-rata")
    return study


def allocate(study, policy):
    seen, admitted, requested, warnings = {}, {}, {}, []
    duplicate_count = conflicting_count = 0
    for request in study["requests"]:
        rid, actor, units = request["id"], request["participant"], request["units"]
        requested[actor] = requested.get(actor, 0) + units
        if rid in seen:
            duplicate_count += 1
            if seen[rid] != (actor, units):
                conflicting_count += 1
            if policy["deduplicate"]:
                continue
        else:
            seen[rid] = (actor, units)
        cap = policy["participantCap"]
        accepted = units if cap is None else min(units, max(0, cap - admitted.get(actor, 0)))
        admitted[actor] = admitted.get(actor, 0) + accepted
    capacity = study["capacity"]
    total = sum(admitted.values())
    grants = {actor: 0 for actor in admitted}
    if policy["allocation"] == "fifo":
        # Participants ordered by first admitted appearance; requests aggregate per participant.
        left = capacity
        for actor, units in admitted.items():
            grants[actor] = min(left, units)
            left -= grants[actor]
    elif total:
        available = min(capacity, total)
        remainders = []
        for actor, units in admitted.items():
            numerator = units * available
            grants[actor] = numerator // total
            remainders.append((numerator % total, actor))
        left = available - sum(grants.values())
        for _, actor in sorted(remainders, key=lambda pair: (-pair[0], pair[1]))[:left]:
            grants[actor] += 1
    allocated = sum(grants.values())
    concentration = sum((units / allocated) ** 2 for units in grants.values()) if allocated else None
    if duplicate_count:
        warnings.append("Repeated request IDs present")
    if conflicting_count:
        warnings.append("Conflicting duplicate IDs: first declaration retained only when deduplication enabled")
    if not study["source"].strip():
        warnings.append("Source reference missing")
    if not study["review"].strip():
        warnings.append("Human review pending")
    return {
        "policy": copy.deepcopy(policy), "requestedUnits": sum(requested.values()),
        "admittedUnits": total, "allocatedUnits": allocated,
        "unusedCapacity": capacity - allocated,
        "unservedDeclaredUnits": sum(requested.values()) - allocated,
        "duplicateRequests": duplicate_count, "conflictingDuplicates": conflicting_count,
        "servedParticipants": sum(value > 0 for value in grants.values()),
        "allocationConcentration": concentration, "allocations": grants, "warnings": warnings,
        "invariants": {"capacityRespected": allocated <= capacity,
                       "nonnegativeAllocations": all(value >= 0 for value in grants.values()),
                       "admittedDemandRespected": all(value <= admitted[key] for key, value in grants.items())},
    }


def evaluate(study):
    validate(study)
    baseline = {"name": "Baseline", "deduplicate": False, "participantCap": None, "allocation": "fifo"}
    results = [allocate(study, baseline)] + [allocate(study, repair) for repair in study["repairs"]]
    return {"schema": "researchos-market-resilience/v1", "studyDigest": digest(study),
            "mode": "synthetic", "executionAuthorized": False, "results": results,
            "limitations": [
                "Declared requests are not verified economic demand; repeated submissions may inflate totals.",
                "Concentration is descriptive, not a welfare, fairness or systemic-risk guarantee.",
                "Finite example checks do not prove resilience against arbitrary behavior.",
                "No live venue, trading, broker, LLM call, or automatic repair deployment is connected."]}


def verify_report(study, report):
    expected = evaluate(study)
    if canonical(expected) != canonical(report):
        raise ValueError("report does not match recomputed synthetic study")
    return expected
