import io
import os
import shutil
import tempfile
import time
import unittest

_tmp = tempfile.mkdtemp()
os.environ["CRADOCS_DATA"] = _tmp
os.environ["CRADOCS_MODE"] = "local"
os.environ["GOOGLE_CLIENT_ID"] = "test-id"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

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
    data = {"file": (io.BytesIO(b"data"), "f.txt"), "amount": "1", "unit": "hours", **fields}
    post(c, "/upload", data, content_type="multipart/form-data")
    return cra.store.list_docs()[-1]  # LocalStore keeps insertion order


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

    def test_home_page_renders(self):
        owner = new_client("own7")
        upload(owner)
        r = owner.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Recent documents", r.data)
        self.assertIn(b"f.txt", r.data)

    def test_google_login_creates_account_and_signs_in(self):
        from unittest import mock
        c = cra.app.test_client()
        self.assertIn(b"Continue with Google", c.get("/login").data)
        self.assertEqual(c.get("/auth/google").status_code, 302)  # redirects to Google
        tok = {"userinfo": {"email": "Kid@Gmail.com", "email_verified": True}}
        with mock.patch.object(cra.oauth.google, "authorize_access_token", return_value=tok):
            self.assertEqual(c.get("/auth/google/callback").status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)  # signed in
        self.assertEqual(cra.store.get_user("kid@gmail.com")["provider"], "google")

    def test_google_unverified_email_rejected(self):
        from unittest import mock
        c = cra.app.test_client()
        tok = {"userinfo": {"email": "x@gmail.com", "email_verified": False}}
        with mock.patch.object(cra.oauth.google, "authorize_access_token", return_value=tok):
            c.get("/auth/google/callback")
        self.assertEqual(c.get("/").status_code, 302)  # bounced to login
        self.assertIsNone(cra.store.get_user("x@gmail.com"))

    def test_google_accounts_cannot_use_password_login_or_be_preregistered(self):
        c = cra.app.test_client()
        cra.store.create_user({"username": "g@gmail.com", "pw_hash": None, "provider": "google"})
        r = post(c, "/login", {"username": "g@gmail.com", "password": "anything"})
        self.assertIn(b"Invalid username or password", c.get("/login").data + r.data)
        post(c, "/register", {"username": "victim@gmail.com", "password": "secret1"})
        self.assertIsNone(cra.store.get_user("victim@gmail.com"))

    def test_csrf_blocks_forged_post(self):
        c = cra.app.test_client()
        c.get("/login")
        self.assertEqual(c.post("/login", data={"username": "x", "password": "y"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
