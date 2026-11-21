"""Enumerate six optional cells and check the one-removal inequalities."""
import json
from itertools import combinations

from sensitivity_agent import flood_level, masked, solve


GRID = ((2, 7, 8, 3), (4, 5, 6, 9))
START, END = (0, 0), (0, 3)


def investigated_levels():
    optional = [(r, c) for r, row in enumerate(GRID) for c in range(len(row))
                if (r, c) not in (START, END)]
    levels = {}
    for size in range(len(optional) + 1):
        for removed in combinations(optional, size):
            grid = masked(GRID, removed)
            level = solve(grid, START, END)
            if level != flood_level(grid, START, END):
                raise ValueError(f"independent flood disagrees for {removed}")
            levels[frozenset(removed)] = level
    return optional, levels


def run():
    optional, levels = investigated_levels()
    counts = dict(equal=0, raised=0, disconnected=0, still_disconnected=0)
    for removed, before in levels.items():
        for cell in optional:
            if cell in removed:
                continue
            after = levels[removed | {cell}]
            if before is None and after is None:
                counts["still_disconnected"] += 1
            elif before is None or (after is not None and after < before):
                raise ValueError(f"monotonicity violation after masking {cell} in {removed}")
            elif after is None:
                counts["disconnected"] += 1
            elif after == before:
                counts["equal"] += 1
            else:
                counts["raised"] += 1
    bridge = ((2, 9, 3),)
    control = {name: solve(grid, (0, 0), (0, 2)) for name, grid in
               (("observed", bridge), ("excluded", ((2, None, 3),)),
                ("zero_filled", ((2, 0, 3),)))}
    return {"enumerated_masks": len(levels), "one_removal_comparisons": counts,
            "missing_data_control": control, "count_of_90_cell_masks": 2**90}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
