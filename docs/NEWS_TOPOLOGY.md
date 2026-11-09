# Stock-news topology — shadow research v1

This implements bounded news-structure observations, not a proven trading signal.
It cannot direct, veto, resize or exit an order. Predictive validation is **UNPROVEN**.
No empirical performance rating is assigned by this implementation.

## Integration and evidence

The existing opportunity assessment calls `news_evidence` once for its selected
candidate. The same seven-day, top-50 provider response now supplies a separate
`news_topology_shadow` object. It is saved in `entry/decision.json` assessments,
including an assessment with no matching catalyst. The existing workflow retains
these artifacts for 90 days. No extra API request, credential, paid model, schedule,
or execution permission is added. Candidates skipped before news retrieval do not
have a news snapshot; this dataset is selection-biased and is not a market-wide scan.

The AI review evidence packet deliberately excludes the shadow object. The legacy
keyword evidence and deterministic trading decisions are unchanged. Invalid shadow
input records a visible `INVALID_INPUT` diagnostic; it never becomes a passing
trading gate. Normal provider-response failures keep their existing failure behavior.

Each snapshot records version, observation time, content hash, source labels,
canonical publisher URLs, publication/revision/availability times, exclusion counts,
and representative article IDs. Hashes support local replay integrity, not source
authentication. Raw source labels do not prove editorial or economic independence.

## Implemented observations

| Output | Method | Interpretation limit |
|---|---|---|
| Duplicate families | Same canonical URL or token Jaccard similarity >=0.9 | Syndicated paraphrases can escape detection; shared query-based URLs can overmerge |
| Event-like clusters | Connected components at token similarity >=0.5 | Lexical proximity is not verified event identity; single-linkage can chain topics |
| Window novelty | Recent 24-hour cluster with no older representative in the batch | Seven-day, truncated-window novelty, not proof that the event is new |
| Possible conflict | Opposing lexical cues within a shared topic and 24 hours | May refer to different periods or metrics; negation is not understood |
| Co-mentioned symbols | Provider symbol tags | No inferred supplier, customer, causal or directional relationship |
| H0 persistence | Complete Jaccard-distance filtration; Kruskal component merges | Formal zero-dimensional persistence of lexical data; no H1 loops, truth or returns inference |
| Snapshot change | Added/disappeared representative IDs | Provider coverage, revisions and rolling expiry also cause change |

All H0 vertices are born at distance zero. Each finite interval dies when an edge
joins two previously separate components. One essential interval remains for a
nonempty batch; `death: null` represents it. Component counts are reported at
distances 0, 0.25, 0.5, 0.75 and 1. Empty input stays `INSUFFICIENT_EVIDENCE`.
At most 50 records are processed, bounding the pairwise computation.

Timestamps must be timezone-aware. Old, future, malformed, revised-after-observation
or not-yet-available records are excluded. In live ingestion, missing `known_at`
means the current ingestion time. For historical replay, supply the archived first
availability time; publication time alone cannot establish historical availability.
The implementation cannot recover a publisher's original article before revision.

Offline replay of an archived array of provider news records:

```sh
python news_topology.py --input archived-news.json --symbol AAPL \
  --asof 2026-11-09T14:47:00Z --output news-snapshot.json
# Add --previous previous-snapshot.json for a chronological graph-change comparison.
```

The live scheduled job has no persistent cross-run graph baseline. Snapshot change
is available through the offline CLI; no previous snapshot means `NO_BASELINE`.

## Evaluation, ablations and acceptance

`news_shadow_evaluation.py` compares three nested exploratory cohorts: the existing
keyword baseline; a graph cohort; and the same graph cohort with H0 connectivity.
The graph cohort requires >=2 families, zero excluded records, a window-novel
recent cluster, and no opposing-word flag. H0 additionally requires a finite merge
at distance <=0.5. These settings are arbitrary preregistered research hypotheses,
not calibrated confidence or recommendations. Version them before any change.

Provide every eligible archived observation, not just executed or winning trades.
Each JSON row requires:

| Fields | Meaning |
|---|---|
| `symbol`, `entry_at`, `exit_at` | Matching stock and benchmark observation dates |
| `known_at`, `feature_asof`, `feature_version` | Archived availability and `news-topology-shadow-v1` |
| `snapshot` | Complete point-in-time shadow snapshot for the same symbol/asof |
| `keyword_pass` | Historical baseline result, explicit boolean |
| `entry_price`, `exit_price` | Positive finite stock prices on those dates |
| `benchmark_entry`, `benchmark_exit` | Corresponding investable benchmark prices |

Graph/H0 cohort flags are recomputed from the snapshot; caller-provided flags
cannot override them. Features must be known before entry. Duplicate symbol/entry
observations, invalid prices and inconsistent snapshots are rejected. Outcomes
crossing the development cutoff are purged. Held-out entries start no earlier than
five calendar days after cutoff. The same round-trip cost assumption is charged
to stock and benchmark observations; test realistic cost scenarios independently.

```sh
python news_shadow_evaluation.py --input archived-observations.json \
  --cutoff 2026-12-01T00:00:00Z --cost-bps 10 --output shadow-evaluation.json
```

The report contains cohort sample counts, mean net return, matched benchmark return
and excess return. Empty cohorts report null means. These are observation averages,
not portfolio returns; overlapping returns are dependent. This evaluator does not
model capital allocation, drawdown, turnover, uncertainty intervals or market impact.
It never certifies an edge, regardless of the reported mean.

Before promotion, freeze universe, event extraction, thresholds, timestamps,
benchmark, holding horizon and costs; collect representative point-in-time data;
include failures, missing evidence and delistings; evaluate independent held-out
periods and cost sensitivity; quantify uncertainty with dependence-aware methods;
and compare keyword versus graph versus graph-plus-H0 results. Reject topology if
it adds no reliable benefit over the simpler baseline. A separate reviewed change
would be required before shadow features can influence paper execution.

Current status: deterministic implementation and synthetic tests only. No historical
market dataset, independent reproduction, measured alpha or live-money validation
is included. Existing paper sizing, risk gates and fixed exits remain in force.
