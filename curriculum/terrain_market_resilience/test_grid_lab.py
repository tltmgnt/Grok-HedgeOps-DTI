import itertools
import unittest

from grid_lab import EXAMPLE, connection_threshold as lowest_pass, market_demo


def flood_oracle(grid, start, end):
    # Independent definition: at each threshold, flood only submerged cells.
    for level in sorted({z for row in grid for z in row if z is not None}):
        wet = {(r, c) for r, row in enumerate(grid) for c, z in enumerate(row)
               if z is not None and z <= level}
        if start not in wet:
            continue
        seen = {start}
        stack = [start]
        while stack:
            r, c = stack.pop()
            for p in ((r-1, c), (r+1, c), (r, c-1), (r, c+1)):
                if p in wet and p not in seen:
                    seen.add(p)
                    stack.append(p)
        if end in seen:
            return level
    return None


class TerrainTests(unittest.TestCase):
    def test_known_pass_and_persistence(self):
        level = lowest_pass(EXAMPLE, (1, 0), (1, 4))
        self.assertEqual((level, level - 110), (140, 30))
        # Closing the original pass leaves a distinct, higher route.
        changed = [list(row) for row in EXAMPLE]
        changed[1][2] = None
        self.assertEqual(lowest_pass(changed, (1, 0), (1, 4)), 150)

    def test_corner_contact_depends_on_connectivity(self):
        grid = ((100, None), (None, 110))
        self.assertIsNone(lowest_pass(grid, (0, 0), (1, 1)))
        self.assertEqual(lowest_pass(grid, (0, 0), (1, 1), diagonals=True), 110)

    def test_all_small_grids_against_independent_oracle(self):
        for heights in itertools.product((None, -1, 0, 2), repeat=6):
            if heights[0] is None or heights[-1] is None:
                continue
            grid = (heights[:3], heights[3:])
            self.assertEqual(lowest_pass(grid, (0, 0), (1, 2)),
                             flood_oracle(grid, (0, 0), (1, 2)), grid)

    def test_invalid_grid_and_endpoint(self):
        for grid in ((), ((1,), (1, 2)), ((True,),), ((None,),)):
            with self.assertRaises(ValueError):
                lowest_pass(grid, (0, 0), (0, 0))


class MarketTests(unittest.TestCase):
    def test_stress_thresholds_and_missing_band(self):
        report = market_demo()
        self.assertEqual(report["threshold_bps"], 8)
        self.assertEqual(report["without_center_bps"], 14)
        self.assertIsNone(report["without_middle_band_bps"])
        grid = [row.copy() for row in report["cost_bps"]]
        for key in ("threshold_bps", "without_center_bps", "without_middle_band_bps"):
            if key == "without_center_bps":
                grid[1][1] = None
            elif key == "without_middle_band_bps":
                grid[1] = [None] * 3
            self.assertEqual(flood_oracle(grid, (0, 0), (2, 2)), report[key])
