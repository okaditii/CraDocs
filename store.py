"""Storage backends. LocalStore needs nothing; AwsStore uses S3 + DynamoDB."""
import json
import os
import threading
from decimal import Decimal
from pathlib import Path


class LocalStore:
    """JSON file for metadata + a folder for documents. Free, no AWS needed."""

    def __init__(self, root="data"):
        self.root = Path(root)
        (self.root / "files").mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "db.json"
        self.lock = threading.Lock()
        if not self.db_path.exists():
            self._save({"users": {}, "docs": {}})

    def _load(self):
        return json.loads(self.db_path.read_text())

    def _save(self, data):
        self.db_path.write_text(json.dumps(data))

    # users
    def get_user(self, username):
        return self._load()["users"].get(username)

    def create_user(self, user):
        with self.lock:
            db = self._load()
            if user["username"] in db["users"]:
                return False
            db["users"][user["username"]] = user
            self._save(db)
            return True

    # docs
    def get_doc(self, doc_id):
        return self._load()["docs"].get(doc_id)

    def put_doc(self, doc):
        with self.lock:
            db = self._load()
            db["docs"][doc["doc_id"]] = doc
            self._save(db)

    def list_docs(self):
        return list(self._load()["docs"].values())

    def delete_doc(self, doc_id):
        with self.lock:
            db = self._load()
            db["docs"].pop(doc_id, None)
            self._save(db)

    def claim_download(self, doc_id):
        """Atomically count a download; False if the limit is already reached."""
        with self.lock:
            db = self._load()
            doc = db["docs"].get(doc_id)
            if not doc:
                return False
            limit = doc.get("max_downloads", 0)
            if limit and doc.get("downloads", 0) >= limit:
                return False
            doc["downloads"] = doc.get("downloads", 0) + 1
            self._save(db)
            return True

    # files
    def save_file(self, key, fileobj):
        with open(self.root / "files" / key, "wb") as f:
            f.write(fileobj.read())

    def delete_file(self, key):
        try:
            (self.root / "files" / key).unlink()
        except FileNotFoundError:
            pass

    def local_path(self, key):
        return self.root / "files" / key

    def download_url(self, key, filename, inline=False, content_type=None):
        return None  # app serves the file directly


def _clean(item):
    """DynamoDB returns Decimal; turn back into int/float."""
    if isinstance(item, Decimal):
        return int(item) if item % 1 == 0 else float(item)
    if isinstance(item, dict):
        return {k: _clean(v) for k, v in item.items()}
    if isinstance(item, list):
        return [_clean(v) for v in item]
    return item


class AwsStore:
    def __init__(self):
        import boto3

        self.bucket = os.environ["CRADOCS_BUCKET"]
        ddb = boto3.resource("dynamodb")
        self.users = ddb.Table(os.environ.get("CRADOCS_USERS_TABLE", "cradocs-users"))
        self.docs = ddb.Table(os.environ.get("CRADOCS_DOCS_TABLE", "cradocs-docs"))
        self.s3 = boto3.client("s3")

    def get_user(self, username):
        return _clean(self.users.get_item(Key={"username": username}).get("Item"))

    def create_user(self, user):
        from botocore.exceptions import ClientError

        try:
            self.users.put_item(
                Item=user, ConditionExpression="attribute_not_exists(username)"
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def get_doc(self, doc_id):
        return _clean(self.docs.get_item(Key={"doc_id": doc_id}).get("Item"))

    def put_doc(self, doc):
        self.docs.put_item(Item=doc)

    def list_docs(self):
        items, kwargs = [], {}
        while True:
            resp = self.docs.scan(**kwargs)
            items += resp["Items"]
            if "LastEvaluatedKey" not in resp:
                return _clean(items)
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def delete_doc(self, doc_id):
        self.docs.delete_item(Key={"doc_id": doc_id})

    def claim_download(self, doc_id):
        from botocore.exceptions import ClientError

        try:
            self.docs.update_item(
                Key={"doc_id": doc_id},
                UpdateExpression="ADD downloads :one",
                ConditionExpression=(
                    "attribute_exists(doc_id) AND "
                    "(max_downloads = :zero OR attribute_not_exists(downloads) "
                    "OR downloads < max_downloads)"
                ),
                ExpressionAttributeValues={":one": 1, ":zero": 0},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def save_file(self, key, fileobj):
        self.s3.upload_fileobj(
            fileobj, self.bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"}
        )

    def delete_file(self, key):
        self.s3.delete_object(Bucket=self.bucket, Key=key)

    def local_path(self, key):
        return None

    def download_url(self, key, filename, inline=False, content_type=None):
        params = {
            "Bucket": self.bucket,
            "Key": key,
            "ResponseContentDisposition": f'{"inline" if inline else "attachment"}; filename="{filename}"',
        }
        if content_type:
            params["ResponseContentType"] = content_type
        return self.s3.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=60,  # short-lived so revoked access can't be reused
        )


def get_store():
    if os.environ.get("CRADOCS_MODE", "local") == "aws":
        return AwsStore()
    return LocalStore(os.environ.get("CRADOCS_DATA", "data"))
