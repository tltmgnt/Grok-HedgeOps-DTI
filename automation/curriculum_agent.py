"""Human-supervised curriculum agent: observe -> plan -> act -> verify -> report.

Permitted action: create/update GitHub tracking issues. Never place trades,
modify trading settings, merge PRs, or run generated shell commands.
"""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MODULES = [
    ("Risk taxonomy and architecture", "Map each category to evidence, severity and owner.", "Every category has a documented input and failure policy."),
    ("Market and volatility", "Validate trend, volatility and market-clock observations.", "Market restrictions always override soft sizing."),
    ("Liquidity and execution", "Measure spread, volume, slippage and partial-fill risk.", "Invalid quotes reject; marginal liquidity defers or reduces size."),
    ("Portfolio and drawdown", "Reconcile exposure, buying power, concentration and daily losses.", "Hard exposure limits cannot be overridden."),
    ("Data integrity", "Verify timestamp, source provenance and missing evidence.", "Stale or missing critical data fails closed."),
    ("Grok advisory governance", "Validate AI output, provenance and prompt-injection defenses.", "AI cannot override hard gates."),
    ("Strategy and event gaps", "Validate signal logic and earnings/event exclusions.", "Unknown event evidence never silently passes."),
    ("Risk arbitration", "Prove deterministic precedence: reject > defer > reduce > pass.", "Hard rejection always wins."),
    ("Broker reconciliation", "Verify positions, open orders and stable client order IDs.", "Repeated evaluations cannot duplicate an intended order."),
    ("Observability", "Record per-candidate evidence, reason codes and rule versions.", "Every skip has a traceable explanation."),
    ("Adversarial testing", "Inject API failures, malformed data and ambiguous responses.", "Safety invariants survive fault injection."),
    ("Supervised paper pilot", "Review CI, security checks, kill switches and operator approvals.", "Human approval is required before paper execution."),
]
MARKER = "<!-- hedgeops-curriculum-agent:v1:module-{} -->"

def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True,
                            timeout=30, check=False)
    if result.returncode:
        raise RuntimeError("GitHub CLI action failed: " + result.stderr[:300])
    return result.stdout

def observe(repo):
    raw = gh("issue", "list", "--repo", repo, "--state", "all",
             "--limit", "200", "--json", "number,title,body,state,url")
    issues = json.loads(raw)
    return {i: next((x for x in issues if MARKER.format(i) in (x.get("body") or "")), None)
            for i in range(1, len(MODULES) + 1)}

def plan(observations):
    for i, (title, task, acceptance) in enumerate(MODULES, 1):
        issue = observations[i]
        yield {"module": i, "title": title, "task": task,
               "acceptance": acceptance,
               "state": "DONE" if issue and issue["state"] == "CLOSED" else
                        "IN_PROGRESS" if issue else "TODO",
               "issue": issue}

def act(repo, steps, apply):
    for step in steps:
        if step["state"] != "TODO" or not apply:
            continue
        body = (MARKER.format(step["module"]) + "\n\n"
                + "## Objective\n" + step["task"] + "\n\n"
                + "## Acceptance criterion\n" + step["acceptance"] + "\n\n"
                + "## Human-controlled process\n"
                + "- [ ] Implement on a feature branch\n"
                + "- [ ] Add positive, negative and fail-closed tests\n"
                + "- [ ] Pass Python tests and static security checks\n"
                + "- [ ] Open PR with evidence and request review\n"
                + "- [ ] Verify safeguards and close this issue manually\n\n"
                + "**Agent scope:** planning and issue tracking only; no broker execution.\n")
        gh("issue", "create", "--repo", repo,
           "--title", f"[Risk curriculum {step['module']:02d}/12] {step['title']}",
           "--body", body)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("curriculum-agent-report.json"))
    args = parser.parse_args()
    before = list(plan(observe(args.repo)))
    act(args.repo, before, args.apply)
    after = list(plan(observe(args.repo))) if args.apply else before
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "issue_tracking" if args.apply else "dry_run",
        "scope": "GitHub issues only; no trades or PR merges",
        "modules": [{k: v for k, v in s.items() if k != "issue"} | {
            "issue_url": (s["issue"] or {}).get("url")} for s in after],
        "done": sum(s["state"] == "DONE" for s in after),
        "open": sum(s["state"] == "IN_PROGRESS" for s in after),
        "unstarted": sum(s["state"] == "TODO" for s in after),
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## Risk curriculum agent\n\n")
            out.write(f"Mode: {report['mode']} | Done: {report['done']} | Open: {report['open']} | Unstarted: {report['unstarted']}\n\n")
            out.write("| Module | State | Issue |\n|---|---|---|\n")
            for s in after:
                out.write(f"| {s['module']:02d} {s['title']} | {s['state']} | {s['issue']['url'] if s['issue'] else 'not created'} |\n")
            out.write("\n**No trading actions are performed by this agent.**\n")
    print(json.dumps({"done": report["done"], "open": report["open"],
                      "unstarted": report["unstarted"], "mode": report["mode"]}))

if __name__ == "__main__":
    main()
