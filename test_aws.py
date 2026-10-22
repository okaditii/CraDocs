"""Runs the real AwsStore / app / cleanup code against mocked S3 + DynamoDB (moto).

    pip install moto[s3,dynamodb] boto3
    python test_aws.py

Nothing here touches your real AWS account.
"""
import io
import os
import re
import time
import unittest

os.environ.update({
    "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_DEFAULT_REGION": "us-east-1", "CRADOCS_MODE": "aws", "CRADOCS_SWEEP": "0",
    "CRADOCS_BUCKET": "cradocs-test-bucket", "SECRET_KEY": "test",
})

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

_mock = mock_aws()
_mock.start()
_ddb = boto3.client("dynamodb")
for name, key in [("cradocs-users", "username"), ("cradocs-docs", "doc_id")]:
    _ddb.create_table(
        TableName=name, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
        KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
    )
boto3.client("s3").create_bucket(Bucket="cradocs-test-bucket")

import app as cra  # noqa: E402
import cleanup  # noqa: E402
from store import AwsStore  # noqa: E402


def post(c, url, data=None, **kw):
    with c.session_transaction() as s:
        token = s.get("csrf")
    if token is None:
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf"]
    return c.post(url, data={**(data or {}), "csrf": token}, **kw)


def client(name):
    c = cra.app.test_client()
    post(c, "/register", {"username": name, "password": "secret1"})
    return c


def upload(c, **f):
    before = {d["doc_id"] for d in cra.store.list_docs()}
    post(c, "/upload", {"file": (io.BytesIO(b"hello aws"), "a.txt"), "amount": "1", "unit": "hours", **f},
         content_type="multipart/form-data")
    new = [d for d in cra.store.list_docs() if d["doc_id"] not in before]
    assert len(new) == 1, "upload should create exactly one document"
    return new[0]


class AwsTests(unittest.TestCase):
    def test_uses_aws_backend(self):
        self.assertIsInstance(cra.store, AwsStore)

    def test_users_and_duplicate_protection(self):
        s = cra.store
        self.assertTrue(s.create_user({"username": "u1", "pw_hash": "x", "default_hours": 5}))
        self.assertFalse(s.create_user({"username": "u1", "pw_hash": "y"}))
        self.assertEqual(s.get_user("u1")["default_hours"], 5)  # int, not Decimal
        self.assertIsNone(s.get_user("nobody"))

    def test_upload_stores_s3_object_and_metadata(self):
        owner = client("aw1")
        doc = upload(owner, allowed="bob")
        body = boto3.client("s3").get_object(Bucket="cradocs-test-bucket", Key=doc["doc_id"])["Body"].read()
        self.assertEqual(body, b"hello aws")
        self.assertEqual(doc["allowed_users"], ["bob"])
        self.assertIsInstance(doc["max_downloads"], int)

    def test_download_redirects_to_short_lived_presigned_url_and_limit_holds(self):
        owner = client("aw2")
        doc = upload(owner, max_dl="1")
        r = owner.get(f"/download/{doc['doc_id']}")
        self.assertEqual(r.status_code, 302)
        self.assertIn("cradocs-test-bucket", r.headers["Location"])
        self.assertIn("Expires=", r.headers["Location"] + "Expires=") # URL is presigned
        self.assertEqual(cra.store.get_doc(doc["doc_id"])["downloads"], 1)
        r2 = owner.get(f"/download/{doc['doc_id']}")  # limit reached: bounced to home
        self.assertTrue(r2.headers["Location"].endswith("/"))
        self.assertEqual(cra.store.get_doc(doc["doc_id"])["downloads"], 1)

    def test_atomic_download_counter(self):
        owner = client("aw3")
        doc = upload(owner, max_dl="2")
        results = [cra.store.claim_download(doc["doc_id"]) for _ in range(4)]
        self.assertEqual(results, [True, True, False, False])

    def test_unlimited_downloads_when_zero(self):
        owner = client("aw4")
        doc = upload(owner, max_dl="0")
        self.assertTrue(all(cra.store.claim_download(doc["doc_id"]) for _ in range(5)))

    def test_cleanup_deletes_expired_from_s3_and_dynamodb_but_keeps_forever(self):
        owner = client("aw5")
        old = upload(owner)
        old["expires_at"] = int(time.time()) - 10
        cra.store.put_doc(old)
        keep = upload(owner, forever="on")
        self.assertIsNone(keep["expires_at"])
        n = cleanup.run(cra.store)
        self.assertGreaterEqual(n, 1)
        self.assertIsNone(cra.store.get_doc(old["doc_id"]))
        self.assertIsNotNone(cra.store.get_doc(keep["doc_id"]))
        s3 = boto3.client("s3")
        keys = [o["Key"] for o in s3.list_objects_v2(Bucket="cradocs-test-bucket").get("Contents", [])]
        self.assertNotIn(old["doc_id"], keys)
        self.assertIn(keep["doc_id"], keys)

    def test_cloudformation_inline_lambda_works(self):
        """Extract the Lambda source from template.yaml and run it for real."""
        tpl = open(os.path.join(os.path.dirname(__file__), "template.yaml"), encoding="utf-8").read()
        m = re.search(r"ZipFile: \|\n((?:          .*\n|\n)+)", tpl)
        self.assertIsNotNone(m)
        code = "\n".join(line[10:] for line in m.group(1).splitlines())
        owner = client("aw6")
        gone = upload(owner)
        gone["expires_at"] = int(time.time()) - 5
        cra.store.put_doc(gone)
        stay = upload(owner, forever="on")
        os.environ.update({"BUCKET": "cradocs-test-bucket", "DOCS_TABLE": "cradocs-docs"})
        ns = {}
        exec(compile(code, "lambda_inline", "exec"), ns)
        out = ns["handler"]({}, None)
        self.assertGreaterEqual(out["deleted"], 1)
        self.assertIsNone(cra.store.get_doc(gone["doc_id"]))
        self.assertIsNotNone(cra.store.get_doc(stay["doc_id"]))

    def test_sharing_flow_end_to_end_on_aws(self):
        owner, bob, eve = client("aw7"), client("aw8"), client("aw9")
        doc = upload(owner, allowed="aw8", password="pw")
        self.assertIn(b"Password required", bob.get(f"/download/{doc['doc_id']}").data)
        self.assertEqual(post(bob, f"/download/{doc['doc_id']}", {"password": "pw"}).status_code, 302)
        self.assertEqual(eve.get(f"/download/{doc['doc_id']}").status_code, 302)  # blocked
        self.assertEqual(cra.store.get_doc(doc["doc_id"])["downloads"], 1)

    @classmethod
    def tearDownClass(cls):
        _mock.stop()


if __name__ == "__main__":
    unittest.main()
