#!/usr/bin/env python3
"""Read-only verification of the E2 observed_request row written by the smoke.

Verification-of-write only: opens governor.db read-only and selects the exact
request id. No SQL write into E1/E2 databases.
"""
import json
import os
import sqlite3

db = os.path.join(os.environ["LOCALAPPDATA"], "hermes", "exec-brain", "governor.db")
con = sqlite3.connect("file:" + db.replace(os.sep, "/") + "?mode=ro", uri=True)
cur = con.execute(
    "SELECT request_id,provider,model,requested_at,input_tokens,output_tokens,"
    "total_tokens,monetary_cost,status,error_code,latency_ms "
    "FROM observed_request WHERE request_id=?",
    ("obs-20260925-39ed6ee5",),
)
cols = [d[0] for d in cur.description]
rows = cur.fetchall()
print(json.dumps([dict(zip(cols, r)) for r in rows], indent=2))
con.close()
