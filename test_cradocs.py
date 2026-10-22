import io
import os
import shutil
import tempfile
import time
import unittest

_tmp = tempfile.mkdtemp()
os.environ["CRADOCS_DATA"] = _tmp
os.environ["CRADOCS_MODE"] = "local"
os.environ["CRADOCS_SWEEP"] = "0"  # tests drive cleanup themselves

import app as cra  # noqa: E402
from cleanup import run  # noqa: E402


def post(client, url, data=None, **kw):
    with client.session_transaction() as s:
        token = s.get("csrf")
    if token is None:
        client.get("/login")
        with client.session_transaction() as s:
            token = s["csrf"]
    return client.post(url, data={**(data or {}), "csrf": token}, **kw)


def new_client(name):
    c = cra.app.test_client()
    post(c, "/register", {"username": name, "password": "secret1"})
    return c


def upload(c, **fields):
    before = {d["doc_id"] for d in cra.store.list_docs()}
    data = {"file": (io.BytesIO(b"data"), "f.txt"), "amount": "1", "unit": "hours", **fields}
    post(c, "/upload", data, content_type="multipart/form-data")
    new = [d for d in cra.store.list_docs() if d["doc_id"] not in before]
    assert len(new) == 1, "upload should create exactly one document"
    return new[0]


class VaultTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_tmp, ignore_errors=True)

    def test_sharing_and_download_limit(self):
        owner, bob, eve = new_client("own1"), new_client("bob1"), new_client("eve1")
        doc = upload(owner, allowed="bob1", max_dl="1")
        self.assertEqual(bob.get(f"/download/{doc['doc_id']}").status_code, 200)
        self.assertEqual(bob.get(f"/download/{doc['doc_id']}").status_code, 302)  # limit hit
        self.assertEqual(eve.get(f"/download/{doc['doc_id']}").status_code, 302)  # not allowed

    def test_expiry_denies_then_cleanup_deletes(self):
        owner = new_client("own2")
        doc = upload(owner)
        doc["expires_at"] = int(time.time()) - 5
        cra.store.put_doc(doc)
        self.assertEqual(owner.get(f"/download/{doc['doc_id']}").status_code, 302)
        run(cra.store)
        self.assertIsNone(cra.store.get_doc(doc["doc_id"]))
        self.assertFalse(cra.store.local_path(doc["doc_id"]).exists())

    def test_important_doc_survives_and_needs_password(self):
        owner = new_client("own3")
        doc = upload(owner, forever="on", password="pw123")
        self.assertIsNone(doc["expires_at"])
        run(cra.store, now=int(time.time()) + 10**9)
        self.assertIsNotNone(cra.store.get_doc(doc["doc_id"]))
        r = owner.get(f"/download/{doc['doc_id']}")
        self.assertIn(b"Password required", r.data)
        self.assertEqual(post(owner, f"/download/{doc['doc_id']}", {"password": "bad"}).status_code, 200)
        self.assertEqual(post(owner, f"/download/{doc['doc_id']}", {"password": "pw123"}).status_code, 200)

    def test_delete_important_requires_password(self):
        owner = new_client("own4")
        doc = upload(owner, forever="on", password="pw123")
        post(owner, f"/manage/{doc['doc_id']}", {"action": "delete", "password": "nope"})
        self.assertIsNotNone(cra.store.get_doc(doc["doc_id"]))
        post(owner, f"/manage/{doc['doc_id']}", {"action": "delete", "password": "pw123"})
        self.assertIsNone(cra.store.get_doc(doc["doc_id"]))

    def test_revoke_access(self):
        owner, bob = new_client("own5"), new_client("bob5")
        doc = upload(owner, allowed="bob5")
        post(owner, f"/manage/{doc['doc_id']}", {"action": "save", "allowed": "", "max_dl": "0"})
        self.assertEqual(bob.get(f"/download/{doc['doc_id']}").status_code, 302)

    def test_custom_duration_per_document(self):
        owner = new_client("own6")
        now = int(time.time())
        for amount, unit, secs in [("30", "minutes", 1800), ("2", "days", 172800), ("1", "weeks", 604800)]:
            doc = upload(owner, amount=amount, unit=unit)
            self.assertAlmostEqual(doc["expires_at"] - doc["starts_at"], secs, delta=2)
        doc = upload(owner, forever="on")  # forever without a password is allowed
        self.assertIsNone(doc["expires_at"])
        self.assertIsNone(doc["pw_hash"])
        post(owner, f"/manage/{doc['doc_id']}", {"action": "save", "amount": "3", "unit": "hours", "max_dl": "0"})
        self.assertAlmostEqual(cra.store.get_doc(doc["doc_id"])["expires_at"], now + 10800, delta=5)

    def test_access_start_time_respects_browser_timezone(self):
        import calendar
        owner = new_client("own8")
        # 10:00 local in IST (getTimezoneOffset() == -330) is 04:30 UTC
        doc = upload(owner, starts="2030-01-01T10:00", tzoffset="-330")
        self.assertEqual(doc["starts_at"], calendar.timegm((2030, 1, 1, 4, 30, 0)))
        bob = new_client("bob8")
        post(owner, f"/manage/{doc['doc_id']}", {"action": "save", "allowed": "bob8", "max_dl": "0"})
        self.assertEqual(bob.get(f"/download/{doc['doc_id']}").status_code, 302)  # not started yet

    def test_oversize_upload_is_rejected_cleanly(self):
        owner = new_client("own9")
        big = io.BytesIO(b"x" * (11 * 1024 * 1024))
        r = post(owner, "/upload", {"file": (big, "big.bin"), "amount": "1", "unit": "hours"},
                 content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)

    def test_home_page_renders(self):
        owner = new_client("own7")
        upload(owner)
        r = owner.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Recent documents", r.data)
        self.assertIn(b"f.txt", r.data)

    def test_csrf_blocks_forged_post(self):
        c = cra.app.test_client()
        c.get("/login")
        self.assertEqual(c.post("/login", data={"username": "x", "password": "y"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
