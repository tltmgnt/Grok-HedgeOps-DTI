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

## Reviewer questions and example answers

Ask the learner to predict the answer before opening the omission ranking. Coordinates are zero-based (row, column). Start with edge neighbours only.

**Which cost assumption should we check first?** At (1, 2), the fixture assumes a cost of 7 basis points for a 100-share order at 6 bp spread and 200 shares of available depth. Masking it raises the threshold from 8 to 15 bp.

**Why choose that cell over the centre?** Masking the centre at (1, 1) raises the threshold to 14 bp. Comparing every eligible cell gives us a reason to investigate (1, 2) first.

**Did execution costs actually rise by seven basis points?** The seven-point change occurred in the synthetic path calculation. To assess the cost assumption, ask for independently observed costs for comparable order sizes, spreads and depths.

**Why is 140 m the lowest crossing?** The middle row gives a route of 100 → 120 → 140 → 125 → 110 m. Every route crosses the middle column. Its lowest cell is 140 m, so no route opens earlier.

**Which location deserves a survey first?** The 120 m western approach at (1, 1) and the 125 m eastern approach at (1, 3) tie. Masking either raises the crossing to 160 m. Masking the 140 m saddle raises it to 150 m. Ask which approach has poorer survey coverage and record the evidence used to break the tie.

**How should we report a disconnection?** Say “No path through the remaining observed cells under the stated adjacency rule.” Ask which missing observations could bridge the gap and whether corner contact is meaningful in this setting.

**What evidence would change the conclusion?** Obtain an independent estimate for the 7 bp cost at (1, 2), replace that assumption, and rerun the full ranking. Record whether the same scenario remains the first review priority.

## Sensitivity investigation agent

From this lab folder, run `python sensitivity_agent.py terrain` or `python sensitivity_agent.py market`. The default rule-based planner runs offline. To use an AI planner, set `OPENAI_API_KEY` outside the repository and add `--model MODEL_ID` using a Responses API model with structured outputs. This sends the synthetic study to the provider and can incur one model call per investigation.

1. The agent masks each eligible cell and computes the full ranking.
2. A separate threshold flood checks the baseline, every omission, all ties and any disconnections. A disagreement stops the run before planning.
3. The planner selects one bounded experiment. The offline rule tests corner connectivity for tied leaders; for a unique leader it removes the top two observations together. The AI planner chooses between those same experiments based on the verified packet.
4. The agent executes the chosen experiment locally and checks its result by flooding again. Read the baseline and single-cell ranking under `study`, then the actual masked cells and resulting thresholds under `follow_up`. A null threshold means disconnected. Coordinates use zero-based row and column.
5. The packet ends with a question for a human reviewer. Record a source for the requested measurements or challenge the adjacency assumption before drawing conclusions about the world.
