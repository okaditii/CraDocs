"""Lists every document with its time left, then runs the cleanup once.

    python3 check_expiry.py
"""
import os
import time

for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import cleanup  # noqa: E402
from store import get_store  # noqa: E402

store = get_store()
now = int(time.time())
print("mode:", os.environ.get("CRADOCS_MODE", "local"), "| bucket:", os.environ.get("CRADOCS_BUCKET"))
for d in store.list_docs():
    exp = d.get("expires_at")
    left = "forever" if d.get("permanent") or not exp else f"{exp - now} sec left"
    print(f"  {d['filename']}  ({d['doc_id']}): {left}")
print("deleted:", cleanup.run(store, now))
