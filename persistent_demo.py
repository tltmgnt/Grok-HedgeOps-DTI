"""Offline persistent event demonstration. No API credentials required."""
import json
import os
from hedgeops.store import EventStore

path = os.environ.get("HEDGEOPS_DB_PATH", "data/hedgeops.sqlite3")
with EventStore(path) as store:
    store.append("demo-case", "prediction_proposed",
                 {"metric": "latency_ms", "target": 100, "status": "pending"})
    print(json.dumps(store.snapshot("demo-case"), indent=2))
