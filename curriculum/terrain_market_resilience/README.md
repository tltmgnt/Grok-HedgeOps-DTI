# Which barrier connects two valleys or two market scenarios?

A standalone, 45-minute lab for learners who can read a small grid. Use Python 3.10+ from this folder. All inputs are included. The objective is to compute a connecting threshold, exhibit a path attaining it, and show why a lower threshold fails.

```sh
python grid_lab.py terrain
python grid_lab.py market
python -m unittest discover -v
```

For an automated run, `python grid_lab.py both` emits a single JSON object. A cell connects to an edge neighbour. The cost of a path is its largest cell value, including its endpoints. Among all connecting paths we seek the smallest such cost. A missing cell excludes that route. JSON `null` in a result means the endpoints cannot connect through the available cells.

## Lesson 1 · Flooding two valleys (15 minutes)

Predict when water first connects the 100 m and 110 m minima in this grid. Look for a path that establishes an upper bound and a column that establishes a matching lower bound.

```text
160  155  150  155  160
100  120  140  125  110
160  150  145  150  160
```

Check your answer with the terrain command. The middle row connects at 140 m. Every route crosses the middle column, where even the lowest cell is 140 m. The younger component therefore lives from 110 m to 140 m, a persistence of 30 m. Remove the central 140 m cell and repeat. A detour reaches 150 m. At 145 m the remaining middle-column cell at 145 m has no reachable edge neighbour on either side.

**Exercise:** Construct a two-by-two grid where corner contact alone connects the endpoints. Predict the result for four and eight neighbours, then compare with the corner-contact test. Which convention makes sense for water crossing cells in your own model, and why?

## Lesson 2 · Stress scenarios for a fixed 100-share order (20 minutes)

Each cell is a synthetic execution-cost assumption in basis points (1 bp is 0.01%). Rows represent spread widening. Columns represent decreasing available depth. The numbers are deliberately hand-authored to expose sensitivity. Adjacent cells mean a change of one scenario level on one axis. Paths are undirected and can revisit more favourable conditions.

| Spread (bp) / depth (shares) | 1,000 | 500 | 200 |
|---|---:|---:|---:|
| 2 | 2 | 3 | 14 |
| 6 | 9 | 5 | 7 |
| 12 | 18 | 15 | 8 |

Start at the top left and finish at the bottom right. Before running the market command, trace a path at threshold 8 bp. Then hide the centre observation. Finally hide the entire middle row. Record a prediction for each case.

**Answer key.** The path 2 → 3 → 5 → 7 → 8 attains 8 bp, and the endpoint alone rules out less. With the centre excluded, one route costs 14 bp via the top right and another costs 18 bp via the bottom left. The cheaper route sets the threshold at 14 bp. Removing the whole middle row leaves no observed path. The six-basis-point change measures sensitivity to the centre assumption in this fixture. It is neither a time-series forecast nor an estimate of realized slippage.

## Review and assessment (10 minutes)

1. Run the tests. The solver explores paths in order of their current worst cell. A second implementation floods every distinct threshold independently and checks reachability. They are compared on 2,304 small grids and on the market controls.
2. Change the top-right cost from 14 to 19. Predict the centre-excluded threshold, identify the new best path, and check it using the solver. Expected result: 18 bp, via 2 → 9 → 18 → 15 → 8.
3. Submit a short review containing a witness path, a lower-bound argument, one missing-data control, and one reason the interpretation might fail on real data. For a market study, identify the source of costs, justify transitions between adjacent scenarios, and state whether reversals should be allowed. For field terrain, document elevation units, spatial resolution, missing-data encoding and vertical reference.

The lab models a finite grid and produces connectivity evidence. Geographic accuracy and market performance need separate observations. Automation checks the calculation; a human reviews whether the grid models a useful question.

Terrain baseline adapted from [MathOS PR #101](https://github.com/tltmgnt/MathOS/pull/101).

## Choose the next measurement

Run the lab as above and inspect the omission study in the JSON report. It masks each observed cell except the two endpoints, restores it, and recalculates the threshold with the original adjacency. Coordinates are zero-based row and column. Loss of every observed path ranks first, followed by the largest increase in the original units. The report lists all tied leaders in row order. When all changes are zero it suggests investigating a plausible joint omission. If the baseline is already disconnected it asks which missing observations could bridge the gap.

Before viewing the ranking, predict the most influential cell. Compare your prediction with the complete ranking, choose a flagged assumption, and record what independent measurement or adjacency check would resolve it. This exhaustive single-omission exercise is intended for small synthetic grids. A high rank measures sensitivity within the fixture; field accuracy and market outcomes require independent observations.

Instructor key: on the terrain fixture, either (1, 1) or (1, 3) raises the pass from 140 m to 160 m. Both outrank the central saddle omission (150 m). In the market fixture, removing (1, 2), the 7 bp cost at 6 bp spread and 200 shares of depth, raises the threshold from 8 to 15 bp. Removing the centre raises it to 14 bp.
