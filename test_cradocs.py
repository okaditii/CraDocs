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
    post(c, "/register", {"username": name, "password": "secret12"})
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

    def test_title_and_preview(self):
        owner, bob, eve = new_client("own10"), new_client("bob10"), new_client("eve10")
        doc = upload(owner, title="  My   Notes ", allowed="bob10", max_dl="1")
        self.assertEqual(doc["title"], "My Notes")
        self.assertIn(b"My Notes", owner.get("/").data)
        self.assertEqual(owner.get(f"/raw/{doc['doc_id']}").status_code, 404)  # not unlocked yet
        r = owner.get(f"/view/{doc['doc_id']}")
        self.assertIn(b"<title>My Notes", r.data)
        self.assertIn(b"&larr; Back", r.data)
        r = owner.get(f"/raw/{doc['doc_id']}")
        self.assertEqual(r.data, b"data")
        self.assertTrue(r.headers["Content-Type"].startswith("text/plain"))
        self.assertTrue(r.headers["Content-Disposition"].startswith("inline"))
        self.assertEqual(cra.store.get_doc(doc["doc_id"])["downloads"], 0)  # owner previews are free
        self.assertEqual(bob.get(f"/view/{doc['doc_id']}").status_code, 200)
        self.assertEqual(bob.get(f"/view/{doc['doc_id']}").status_code, 200)  # reload doesn't re-count
        self.assertEqual(cra.store.get_doc(doc["doc_id"])["downloads"], 1)
        self.assertEqual(eve.get(f"/view/{doc['doc_id']}").status_code, 302)
        self.assertEqual(eve.get(f"/raw/{doc['doc_id']}").status_code, 404)
        post(owner, f"/manage/{doc['doc_id']}", {"action": "save", "title": "Renamed", "max_dl": "1"})
        self.assertEqual(cra.store.get_doc(doc["doc_id"])["title"], "Renamed")

    def test_locked_preview_needs_password(self):
        owner = new_client("own11")
        doc = upload(owner, password="pw123", file=(io.BytesIO(b"<script>x</script>"), "a.html"))
        self.assertIn(b"Unlock and preview", owner.get(f"/view/{doc['doc_id']}").data)
        self.assertEqual(owner.get(f"/raw/{doc['doc_id']}").status_code, 404)
        post(owner, f"/view/{doc['doc_id']}", {"password": "pw123"})
        r = owner.get(f"/raw/{doc['doc_id']}")
        self.assertTrue(r.headers["Content-Type"].startswith("text/plain"))  # html never rendered
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")

    def test_register_validation(self):
        c = cra.app.test_client()
        for data in [{"username": "a,b", "password": "secret12"},     # comma breaks sharing
                     {"username": "shorty", "password": "short"},     # weak password
                     {"username": "hrs01", "password": "secret12", "default_hours": "abc"}]:
            self.assertEqual(post(c, "/register", data).status_code, 200)
            self.assertIsNone(cra.store.get_user(data["username"]))
        new_client("dupe1")
        r = post(cra.app.test_client(), "/register", {"username": "DUPE1", "password": "other123"})
        self.assertIn(b"taken", r.data)

    def test_login_lockout_and_logout(self):
        new_client("lock1")
        c = cra.app.test_client()
        for _ in range(cra.MAX_FAILS):
            post(c, "/login", {"username": "lock1", "password": "wrongpass"})
        r = post(c, "/login", {"username": "lock1", "password": "secret12"}, follow_redirects=True)
        self.assertIn(b"Too many failed attempts", r.data)  # even the right password is refused
        cra._fails.clear()
        self.assertEqual(post(c, "/login", {"username": "lock1", "password": "secret12"}).status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)
        c.get("/logout")  # a plain link can't sign you out
        self.assertEqual(c.get("/").status_code, 200)
        post(c, "/logout")
        self.assertEqual(c.get("/").status_code, 302)

    def test_doc_password_lockout(self):
        owner = new_client("own12")
        doc = upload(owner, password="pw123")
        for _ in range(cra.MAX_FAILS):
            post(owner, f"/download/{doc['doc_id']}", {"password": "bad"})
        r = post(owner, f"/download/{doc['doc_id']}", {"password": "pw123"}, follow_redirects=True)
        self.assertIn(b"Too many wrong passwords", r.data)
        cra._fails.clear()

    def test_owner_not_limited_and_unicode_names(self):
        owner, bob = new_client("own13"), new_client("bob13")
        doc = upload(owner, allowed="bob13", max_dl="1",
                     file=(io.BytesIO(b"data"), "आधार.pdf"))
        self.assertEqual(doc["filename"], "document.pdf")
        for _ in range(3):
            self.assertEqual(owner.get(f"/download/{doc['doc_id']}").status_code, 200)
        self.assertEqual(bob.get(f"/download/{doc['doc_id']}").status_code, 200)  # owner didn't use it up
        self.assertEqual(bob.get(f"/download/{doc['doc_id']}").status_code, 302)
        self.assertEqual(cra.safe_filename("my file (1).PNG"), "my_file_1.PNG")

    def test_lifetime_is_capped(self):
        owner = new_client("own14")
        doc = upload(owner, amount="9" * 40, unit="weeks")
        self.assertEqual(doc["expires_at"] - doc["starts_at"], cra.MAX_LIFETIME)

    def test_csrf_blocks_forged_post(self):
        c = cra.app.test_client()
        c.get("/login")
        self.assertEqual(c.post("/login", data={"username": "x", "password": "y"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
