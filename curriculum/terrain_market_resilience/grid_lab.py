"""Offline minimax connectivity labs for terrain and market scenarios."""
import argparse
import heapq
import json

# Heights in metres. Rows increase southward, columns eastward.
EXAMPLE = ((160, 155, 150, 155, 160),
           (100, 120, 140, 125, 110),
           (160, 150, 145, 150, 160))


def connection_threshold(grid, start, end, *, diagonals=False):
    """Return the minimum, over allowed paths, of the highest cell on each path.

    Cell values are integers in the units of the fixture. None marks excluded cells. Return None when the
    endpoints cannot connect through observed cells. Coordinates are (row, col).
    """
    if not grid or not grid[0] or any(len(row) != len(grid[0]) for row in grid):
        raise ValueError("expected a nonempty rectangular grid")
    if any(h is not None and type(h) is not int for row in grid for h in row):
        raise ValueError("expected integer cell values or None")
    rows, cols = len(grid), len(grid[0])
    for r, c in (start, end):
        if not (0 <= r < rows and 0 <= c < cols) or grid[r][c] is None:
            raise ValueError("endpoint outside observed grid")

    steps = [(-1, 0), (0, -1), (0, 1), (1, 0)]
    if diagonals:
        steps.extend([(-1, -1), (-1, 1), (1, -1), (1, 1)])
    best = {start: grid[start[0]][start[1]]}
    queue = [(best[start], start)]
    while queue:
        level, cell = heapq.heappop(queue)
        if level != best[cell]:
            continue
        if cell == end:
            return level
        for dr, dc in steps:
            r, c = cell[0] + dr, cell[1] + dc
            if not (0 <= r < rows and 0 <= c < cols) or grid[r][c] is None:
                continue
            candidate = max(level, grid[r][c])
            if (r, c) not in best or candidate < best[r, c]:
                best[r, c] = candidate
                heapq.heappush(queue, (candidate, (r, c)))
    return None


def terrain_demo():
    level = connection_threshold(EXAMPLE, (1, 0), (1, 4))
    masked = [list(row) for row in EXAMPLE]
    masked[1][2] = None
    return {"scope": "synthetic terrain", "elevations_m": EXAMPLE,
            "endpoints_row_col": [[1, 0], [1, 4]], "connectivity": 4,
            "merge_level_m": level, "younger_persistence_m": level - EXAMPLE[1][4],
            "without_saddle_m": connection_threshold(masked, (1, 0), (1, 4))}


def market_demo():
    # Authored teaching costs. Rows are spread; columns are available depth.
    costs = [[2, 3, 14], [9, 5, 7], [18, 15, 8]]
    start, end = (0, 0), (2, 2)
    missing_center = [row.copy() for row in costs]
    missing_center[1][1] = None
    missing_band = [row.copy() for row in costs]
    missing_band[1] = [None] * 3
    return {"scope": "synthetic fixed-order scenario connectivity",
            "source": "hand-authored teaching fixture", "order_shares": 100,
            "row_spread_bps": [2, 6, 12], "column_depth_shares": [1000, 500, 200],
            "cost_bps": costs, "endpoints_row_col": [start, end], "connectivity": 4,
            "threshold_bps": connection_threshold(costs, start, end),
            "without_center_bps": connection_threshold(missing_center, start, end),
            "without_middle_band_bps": connection_threshold(missing_band, start, end)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lesson", choices=("terrain", "market", "both"),
                        nargs="?", default="both")
    lesson = parser.parse_args().lesson
    demos = {"terrain": terrain_demo, "market": market_demo}
    print(json.dumps({name: demo() for name, demo in demos.items()
                      if lesson in (name, "both")}, indent=2))
