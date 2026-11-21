"""Investigate the bundled synthetic fixtures and prepare a human review packet."""
import argparse
import json
import os
from urllib.request import Request, urlopen

from grid_lab import EXAMPLE, connection_threshold as solve, investigate_omissions, market_demo

FIXTURES = ("terrain", "market")


def fixture(name):
    if name == "terrain":
        return EXAMPLE, (1, 0), (1, 4), "metres"
    if name == "market":
        demo = market_demo()
        start, end = map(tuple, demo["endpoints_row_col"])
        return demo["cost_bps"], start, end, "basis points"
    raise ValueError("unknown fixture")


TOOLS = {
    "adjacency": "Repeat the baseline and strongest omissions with corner connections allowed.",
    "combined": "Mask all tied leaders together, or the leader and runner-up if unique.",
}


def flood_level(grid, start, end, diagonal=False):
    """Independently flood each observed elevation or cost until endpoints connect."""
    for level in sorted({x for row in grid for x in row if x is not None}):
        wet = {(r, c) for r, row in enumerate(grid) for c, x in enumerate(row)
               if x is not None and x <= level}
        if start not in wet:
            continue
        stack = [start]
        wet.remove(start)
        while stack:
            r, c = stack.pop()
            if (r, c) == end:
                return level
            neighbors = [(r-1, c), (r+1, c), (r, c-1), (r, c+1)]
            if diagonal:
                neighbors.extend((r+dr, c+dc) for dr in (-1, 1) for dc in (-1, 1))
            for point in neighbors:
                if point in wet:
                    wet.remove(point)
                    stack.append(point)
    return None


def masked(grid, cells):
    trial = [list(row) for row in grid]
    for r, c in cells:
        trial[r][c] = None
    return trial


def verify(grid, start, end, study):
    base = flood_level(grid, start, end)
    if base != study["baseline"]:
        raise ValueError("baseline disagrees with independent flood")
    expected = []
    if base is not None:
        for r, row in enumerate(grid):
            for c, value in enumerate(row):
                if value is None or (r, c) in (start, end):
                    continue
                level = flood_level(masked(grid, [(r, c)]), start, end)
                expected.append(dict(cell=[r, c], value=value, threshold_after=level,
                                     increase=None if level is None else level-base))
    expected.sort(key=lambda item: (item["threshold_after"] is None,
                                    item["increase"] or 0), reverse=True)
    leaders = [item["cell"] for item in expected
               if item["threshold_after"] == expected[0]["threshold_after"]
               and item["threshold_after"] != base]
    if expected != study["ranking"] or leaders != study["review_cells"]:
        raise ValueError("omission ranking disagrees with independent flood")


def model_choice(context, model):
    body = {"model": model, "store": False,
            "instructions": "Choose the most informative next experiment on this synthetic fixture. Return only its tool name.",
            "input": json.dumps({"tools": TOOLS, "verified_study": context}),
            "text": {"format": {"type": "json_schema", "name": "experiment", "strict": True,
                                "schema": {"type": "object", "additionalProperties": False,
                                           "properties": {"tool": {"type": "string", "enum": list(TOOLS)}},
                                           "required": ["tool"]}}}}
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("set OPENAI_API_KEY for model-assisted planning")
    request = Request("https://api.openai.com/v1/responses", json.dumps(body).encode(),
                      {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urlopen(request, timeout=60) as response:
        data = json.load(response)
    texts = [part["text"] for item in data.get("output", [])
             for part in item.get("content", []) if part.get("type") == "output_text"]
    if data.get("status") != "completed" or len(texts) != 1:
        raise ValueError("model did not return a completed experiment selection")
    return json.loads(texts[0])["tool"]


def investigate(name, planner=None):
    grid, start, end, unit = fixture(name)
    study = investigate_omissions(grid, start, end)
    verify(grid, start, end, study)
    cells = study["review_cells"]
    packet = {"fixture": name, "units": unit, "scope": "synthetic", "study": study,
              "independent_check": "passed", "review_status": "pending",
              "planner": "model" if planner else "offline rule"}
    if not cells:
        packet["next_question"] = study["review_question"]
        return packet
    tool = planner(packet) if planner else ("adjacency" if len(cells) > 1 else "combined")
    if tool not in TOOLS:
        raise ValueError("unknown experiment")
    if tool == "combined":
        selected = cells if len(cells) > 1 else [item["cell"] for item in study["ranking"][:2]]
        trials = [selected]
    else:
        trials = [[]] + [[cell] for cell in cells]
    observations = []
    for removed in trials:
        trial = masked(grid, removed)
        level = solve(trial, start, end, diagonals=(tool == "adjacency"))
        if level != flood_level(trial, start, end, diagonal=(tool == "adjacency")):
            raise ValueError("follow-up result disagrees with independent flood")
        observations.append({"removed": removed, "threshold": level})
    packet["follow_up"] = {"tool": tool, "description": TOOLS[tool], "observations": observations}
    packet["next_question"] = (f"Which independent observation supports {cells} in the {name} grid? "
                               + ("Can these cells share a corner connection in the real system?"
                                  if tool == "adjacency" else
                                  "Could the selected observations be missing together?"))
    return packet


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("fixture", choices=FIXTURES)
    cli.add_argument("--model", help="Opt in to one OpenAI planning call with this model ID")
    args = cli.parse_args()
    try:
        report = investigate(args.fixture, (lambda p: model_choice(p, args.model)) if args.model else None)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        cli.exit(1, f"Investigation stopped: {type(exc).__name__}: {exc}\n")
    print(json.dumps(report, indent=2))
