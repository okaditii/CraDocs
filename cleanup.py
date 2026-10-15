"""Deletes expired, non-permanent documents.

Run locally:   python cleanup.py
On AWS Lambda: handler = cleanup.handler (triggered by an EventBridge schedule)
"""
import time

from store import get_store


def run(store, now=None):
    now = now or int(time.time())
    deleted = 0
    for doc in store.list_docs():
        if doc.get("permanent"):
            continue
        exp = doc.get("expires_at")
        if exp and exp <= now:
            store.delete_file(doc["doc_id"])
            store.delete_doc(doc["doc_id"])
            deleted += 1
    return deleted


def handler(event=None, context=None):
    return {"deleted": run(get_store())}


if __name__ == "__main__":
    print("deleted", run(get_store()), "expired document(s)")
