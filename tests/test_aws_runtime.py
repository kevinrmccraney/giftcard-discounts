"""Offline AWS contract tests, including races and failure preservation."""
from copy import deepcopy
from datetime import timedelta
import io
import json
from pathlib import Path
import unittest

from giftcard_tool.aws_runtime import DynamoHistory, SnapshotPublisher, publish_batch
from giftcard_tool.pipeline import ValidationError, canonical_json, timestamp

ROOT = Path(__file__).resolve().parents[1]
NOW = timestamp("2026-10-24T12:00:00Z")


class ServiceError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class MemoryDynamo:
    def __init__(self):
        self.items = {}
        self.fail = False

    def put_item(self, **request):
        if self.fail:
            raise ServiceError("ProvisionedThroughputExceededException")
        item, values = request["Item"], request["ExpressionAttributeValues"]
        key = (item["pk"]["S"], item["sk"]["S"])
        old = self.items.get(key)
        if old:
            if ":observed" in values:
                permitted = (int(old["observed_us"]["N"]) < int(values[":observed"]["N"])
                             or (old["observed_us"] == values[":observed"]
                                 and old["digest"] == values[":digest"]))
            else:
                permitted = old["digest"] == values[":digest"]
            if not permitted:
                raise ServiceError("ConditionalCheckFailedException")
        self.items[key] = deepcopy(item)
        return {"Attributes": deepcopy(old)} if old else {}


class MemoryS3:
    def __init__(self):
        self.body = None
        self.version = 0
        self.before_put = None
        self.fail = False

    def get_object(self, **request):
        if self.body is None:
            raise ServiceError("NoSuchKey")
        return {"Body": io.BytesIO(self.body), "ETag": str(self.version)}

    def put_object(self, **request):
        if self.fail:
            raise ServiceError("AccessDenied")
        if self.before_put:
            callback, self.before_put = self.before_put, None
            callback()
        if (request.get("IfMatch") not in (None, str(self.version))
                or request.get("IfNoneMatch") == "*" and self.body is not None):
            raise ServiceError("PreconditionFailed")
        self.body = request["Body"]
        self.version += 1


class CloudPipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config/retailers.json").read_text())
        self.batch = json.loads((ROOT / "fixtures/demo-batch.json").read_text())
        # Deliberately synthetic unit-test data; never sent to an AWS account.
        self.batch.update(demo=False, observed_at="2026-10-24T11:00:00Z", run_id="test-run")
        self.db, self.s3 = MemoryDynamo(), MemoryS3()
        self.history = DynamoHistory(self.db, "test-history")
        self.publisher = SnapshotPublisher(self.s3, "test-snapshots")

    def run_batch(self, batch=None, now=NOW):
        return publish_batch(self.config, batch or self.batch, self.history,
                             self.publisher, now=now)

    def test_history_snapshot_and_direct_current_state(self):
        result = self.run_batch()
        self.assertEqual(result["observations_inserted"], 3)
        snapshot = json.loads(self.s3.body)
        self.assertFalse(snapshot["demo"])
        self.assertEqual(snapshot["source_observed_at"], self.batch["observed_at"])
        self.assertEqual(len([key for key in self.db.items if key[1] == "CURRENT"]), 3)
        self.assertEqual(snapshot["retailers"]["dominos"]["offers"][0]["expires_at"],
                         "2026-10-26T11:00:00Z")

    def test_retry_is_idempotent_and_does_not_extend_expiry(self):
        self.run_batch()
        before = json.loads(self.s3.body)
        result = self.run_batch(now=NOW + timedelta(hours=1))
        after = json.loads(self.s3.body)
        self.assertEqual(result["observations_inserted"], 0)
        self.assertEqual(before["retailers"], after["retailers"])
        self.assertEqual(before["source_observed_at"], after["source_observed_at"])

    def test_demo_partial_and_stale_never_touch_history_or_snapshot(self):
        for change in ({"demo": True}, {"complete": False},
                       {"observed_at": "2026-10-20T11:00:00Z"}):
            with self.subTest(change=change):
                candidate = {**self.batch, **change}
                with self.assertRaises(ValidationError):
                    self.run_batch(candidate)
                self.assertEqual(self.db.items, {})
                self.assertIsNone(self.s3.body)

    def test_verified_empty_batch_clears_offers(self):
        self.run_batch()
        empty = {**self.batch, "run_id": "test-empty", "observed_at": "2026-10-24T11:30:00Z",
                 "offers": [{"retailer_id": row["id"], "status": "no_inventory"}
                            for row in self.config["retailers"]]}
        self.run_batch(empty)
        self.assertEqual(json.loads(self.s3.body)["retailers"], {})
        for key, row in self.db.items.items():
            if key[1] == "CURRENT":
                self.assertEqual(json.loads(row["payload"]["S"])["status"], "no_inventory")

    def test_history_failure_does_not_replace_public_snapshot(self):
        self.run_batch()
        original = self.s3.body
        self.db.fail = True
        newer = {**self.batch, "run_id": "test-later", "observed_at": "2026-10-24T11:30:00Z"}
        with self.assertRaises(ServiceError):
            self.run_batch(newer)
        self.assertEqual(self.s3.body, original)

    def test_publication_failure_preserves_snapshot_and_retry_repairs_current(self):
        self.run_batch()
        original = self.s3.body
        newer = {**self.batch, "run_id": "test-later", "observed_at": "2026-10-24T11:30:00Z"}
        self.s3.fail = True
        with self.assertRaises(ServiceError):
            self.run_batch(newer)
        self.assertEqual(self.s3.body, original)
        self.s3.fail = False
        self.assertEqual(self.run_batch(newer)["observations_inserted"], 0)
        self.assertEqual(json.loads(self.s3.body)["source_observed_at"], newer["observed_at"])

    def test_run_identity_conflict_cannot_replace_snapshot(self):
        self.run_batch()
        original = self.s3.body
        altered = {**self.batch, "observed_at": "2026-10-24T11:30:00Z"}
        with self.assertRaises(ValidationError):
            self.run_batch(altered)
        self.assertEqual(self.s3.body, original)

    def test_older_source_rejected_before_history(self):
        self.run_batch()
        original = deepcopy(self.db.items)
        older = {**self.batch, "run_id": "test-old", "observed_at": "2026-10-24T10:00:00Z"}
        with self.assertRaises(ValidationError):
            self.run_batch(older)
        self.assertEqual(self.db.items, original)

    def test_competing_initial_publish_preserves_winner(self):
        winner = {"schema_version": 1, "demo": False, "source_observed_at": "2026-10-24T11:30:00Z"}
        def race():
            self.s3.body = canonical_json(winner).encode()
            self.s3.version += 1
        self.s3.before_put = race
        with self.assertRaisesRegex(ValidationError, "Concurrent publication"):
            self.run_batch()
        self.assertEqual(json.loads(self.s3.body), winner)
        self.assertFalse(any(key[1] == "CURRENT" for key in self.db.items))

    def test_competing_update_uses_etag_and_preserves_winner(self):
        self.run_batch()
        winner = {**json.loads(self.s3.body), "source_observed_at": "2026-10-24T11:45:00Z"}
        def race():
            self.s3.body = canonical_json(winner).encode()
            self.s3.version += 1
        self.s3.before_put = race
        newer = {**self.batch, "run_id": "test-later", "observed_at": "2026-10-24T11:30:00Z"}
        with self.assertRaises(ValidationError):
            self.run_batch(newer)
        self.assertEqual(json.loads(self.s3.body), winner)

    def test_current_keys_cannot_roll_back(self):
        self.run_batch()
        before = deepcopy(self.db.items)
        older = json.loads(self.db.items[("OFFER#gcx#dominos", "CURRENT")]["payload"]["S"])
        older["observed_at"] = "2026-10-23T00:00:00Z"
        self.history.update_current([older])
        self.assertEqual(self.db.items, before)


if __name__ == "__main__":
    unittest.main()
