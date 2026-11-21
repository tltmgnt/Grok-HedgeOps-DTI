# Optional final-week capstone: reasoning across an octillion masks

Allow 35 minutes. Bring paper and a pencil, or use Python 3.10+ from this folder. By the end, learners should be able to distinguish an exact count of configurations, an exhaustive small experiment, and a proof covering any number of cells.

## Predict and test (12 minutes)

Use the top-left and top-right cells as fixed endpoints. Move across shared edges; the path threshold is the largest cell value along the path, endpoints included. Choose the path with the smallest threshold.

| Row | Column 0 | Column 1 | Column 2 | Column 3 |
|---|---:|---:|---:|---:|
| 0 | 2 (start) | 7 | 8 | 3 (end) |
| 1 | 4 | 5 | 6 | 9 |

Predict the baseline and the result of masking the 8. Restore the 8, then mask the 9 instead. Treat a masked cell as impassable. Explain when a route survives with a higher threshold. Run `python omission_capstone.py` to check all 64 masks. For every mask, the program compares the grid solver with an independent threshold flood. It then checks every move from one mask to a mask with one additional cell removed.

## Scale the argument (13 minutes)

Imagine a fixed grid with 90 optional observations plus two fixed endpoints. Each observation has two states, present or excluded. Compute the number of masks. Does knowing that count tell you the threshold for a specific mask? Attempt to find a removal that lowers the threshold. Then write a proof using the set of surviving paths. State what stays fixed about endpoints, cell values, and adjacency.

## Faculty challenge and key (10 minutes)

* **Small grid.** Baseline 8, masking the 8 gives 9, and masking only the 9 gives 8. There are 192 one-removal comparisons because each of six optional cells is present in 32 starting masks. Of these, 37 preserve a finite threshold, 3 raise it, 46 disconnect the endpoints, and 106 begin and end disconnected.
* **General proof.** After removal, every surviving path was available before, with exactly the same maximum cell value. Minimizing over a subset can only preserve or raise the minimum. An empty path set means disconnected; once disconnected, further removal cannot restore a path. Repeating the argument covers any nested pair of masks. Two unrelated masks need not have comparable sets of paths.
* **What the number means.** There are exactly 2⁹⁰ = 1,237,940,039,285,380,274,899,124,224 masks (about 1.24 octillion). The program computes the count. The proof gives the direction of change; neither supplies all individual thresholds.
* **Break an assumption.** Ask what happens to the row [2, 9, 3] when the middle observation is missing. Excluding it disconnects the endpoints. Recording it as zero produces [2, 0, 3], with a false crossing threshold of 3 instead of the original 9. Ask the learner to point to the proof step that fails: the path now has a different weight.
* **Review criterion.** Collect one reproducible mask, one path-set argument, and one explicit missing-data counterexample. Ask the reviewer to distinguish a property of the finite grid model from a claim about a physical landscape or observed market.
