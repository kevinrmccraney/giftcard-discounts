"""Lambda collection, immutable DynamoDB history, and conditional S3 publication.

AWS clients are injected in tests. boto3 is provided by the Lambda Python runtime;
the local importer and extension do not require an AWS SDK.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .pipeline import (ValidationError, build_snapshot, canonical_json, read_json,
                       timestamp, utcnow)


def _error_code(exc):
    return getattr(exc, "response", {}).get("Error", {}).get("Code")


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _epoch(value):
    return int(timestamp(value).timestamp() * 1_000_000)


class DynamoHistory:
    """Direct per-retailer current keys; history never needs a table scan."""

    def __init__(self, client, table):
        self.client, self.table = client, table

    def _immutable(self, pk, sk, value):
        # A conditional Put is atomic, including simultaneous retries of a run.
        item = {"pk": {"S": pk}, "sk": {"S": sk},
                "digest": {"S": _digest(value)},
                "payload": {"S": canonical_json(value)}}
        try:
            result = self.client.put_item(
                TableName=self.table, Item=item,
                ConditionExpression="attribute_not_exists(pk) OR digest = :digest",
                ExpressionAttributeValues={":digest": item["digest"]},
                ReturnValues="ALL_OLD")
        except Exception as exc:
            if _error_code(exc) == "ConditionalCheckFailedException":
                raise ValidationError("Conflicting run or observation identity") from exc
            raise
        return not bool(result.get("Attributes"))

    def record(self, batch, observations):
        self._immutable(f"RUN#{batch['provider_id']}#{batch['run_id']}", "META", batch)
        inserted = 0
        for row in observations:
            inserted += self._immutable(
                f"OFFER#{row['provider_id']}#{row['retailer_id']}",
                f"OBS#{_epoch(row['observed_at']):020d}", row)
        return inserted

    def update_current(self, observations):
        for row in observations:
            item = {"pk": {"S": f"OFFER#{row['provider_id']}#{row['retailer_id']}"},
                    "sk": {"S": "CURRENT"}, "digest": {"S": _digest(row)},
                    "observed_us": {"N": str(_epoch(row["observed_at"]))},
                    "payload": {"S": canonical_json(row)}}
            try:
                self.client.put_item(
                    TableName=self.table, Item=item,
                    ConditionExpression=("attribute_not_exists(pk) OR observed_us < :observed "
                                         "OR (observed_us = :observed AND digest = :digest)"),
                    ExpressionAttributeValues={":observed": item["observed_us"],
                                               ":digest": item["digest"]})
            except Exception as exc:
                # A later invocation can publish between this run's S3 write and
                # current-state updates. It must not be rolled back by this run.
                if _error_code(exc) != "ConditionalCheckFailedException":
                    raise


class SnapshotPublisher:
    def __init__(self, client, bucket, key="production/snapshot.json"):
        self.client, self.bucket, self.key = client, bucket, key

    def previous(self, snapshot):
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=self.key)
        except Exception as exc:
            if _error_code(exc) in ("NoSuchKey", "404"):
                return None
            raise
        stream = result["Body"]
        try:
            raw = stream.read(2_000_001)
        finally:
            stream.close()
        if len(raw) > 2_000_000:
            raise ValidationError("Existing snapshot exceeds size limit")
        old = json.loads(raw)
        if old.get("demo") is not False:
            raise ValidationError("Production location contains demo or invalid data")
        old_time = timestamp(old["source_observed_at"])
        new_time = timestamp(snapshot["source_observed_at"])
        if old_time > new_time:
            raise ValidationError("Refusing to replace newer observations")
        if old_time == new_time:
            old_data = {k: v for k, v in old.items() if k != "generated_at"}
            new_data = {k: v for k, v in snapshot.items() if k != "generated_at"}
            if old_data != new_data:
                raise ValidationError("Conflicting snapshots at the same observation time")
        return result["ETag"]

    def publish(self, snapshot, etag):
        condition = {"IfMatch": etag} if etag else {"IfNoneMatch": "*"}
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=self.key,
                Body=(canonical_json(snapshot) + "\n").encode("utf-8"),
                ContentType="application/json", CacheControl="public, max-age=300",
                ServerSideEncryption="AES256", **condition)
        except Exception as exc:
            if _error_code(exc) in ("PreconditionFailed", "ConditionalRequestConflict", "412", "409"):
                raise ValidationError("Concurrent publication; newer snapshot preserved") from exc
            raise


def publish_batch(config, batch, history, publisher, *, now=None, max_age_hours=48):
    """Validate everything before history; publish only after durable history.

    A failed write can leave durable immutable history, never a partial public
    snapshot. Retrying the same batch repairs publication/current keys safely.
    """
    now = now or utcnow()
    if batch.get("demo") is not False:
        raise ValidationError("AWS production runtime refuses synthetic data")
    snapshot, rows = build_snapshot(config, batch, now, max_age_hours)
    if not rows or (now - timestamp(batch["observed_at"])).total_seconds() >= max_age_hours * 3600:
        raise ValidationError("Refusing stale production input")
    if len(canonical_json(snapshot).encode("utf-8")) > 2_000_000:
        raise ValidationError("Snapshot exceeds extension input size limit")
    etag = publisher.previous(snapshot)
    inserted = history.record(batch, rows)
    publisher.publish(snapshot, etag)
    history.update_current(rows)
    return {"observations_inserted": inserted,
            "retailers_with_offers": len(snapshot["retailers"]),
            "source_observed_at": snapshot["source_observed_at"]}


def handler(event, context):
    """Scheduled collection only: invocation payload cannot inject a source URL."""
    import boto3
    from botocore.config import Config
    from .gcx import collect_batch

    config = read_json(Path(__file__).resolve().parent.parent / "config" / "retailers-live.json")
    # Budget covers all attempts, not just successful pages. SDK retries are also
    # bounded independently from provider request attempts.
    batch = collect_batch(
        config, max_pages=int(os.environ.get("GCX_MAX_PAGES", "20")),
        request_budget=int(os.environ.get("GCX_REQUEST_BUDGET", "24")),
        timeout=15, delay_seconds=1, retries=2)
    sdk_config = Config(retries={"mode": "standard", "total_max_attempts": 3},
                        connect_timeout=5, read_timeout=15)
    history = DynamoHistory(boto3.client("dynamodb", config=sdk_config), os.environ["HISTORY_TABLE"])
    publisher = SnapshotPublisher(boto3.client("s3", config=sdk_config), os.environ["SNAPSHOT_BUCKET"])
    result = publish_batch(config, batch, history, publisher,
                           max_age_hours=int(os.environ.get("MAX_AGE_HOURS", "48")))
    # No provider HTML, browsing URLs, response bodies, or credentials in logs.
    # Embedded metrics avoid separate CloudWatch credentials/SDK write calls.
    print(canonical_json({
        "_aws": {"Timestamp": int(utcnow().timestamp() * 1000),
                 "CloudWatchMetrics": [{"Namespace": "GiftCardDiscounts",
                                        "Dimensions": [["Stack"]],
                                        "Metrics": [{"Name": "Published", "Unit": "Count"}]}]},
        "Stack": os.environ["STACK_NAME"], "Published": 1,
        "retailers_with_offers": result["retailers_with_offers"]}))
    return result
