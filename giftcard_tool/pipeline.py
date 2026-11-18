"""Validate explicit input, compute discounts, retain history, publish a snapshot.

Input is OUR provider-neutral interchange format, not an undocumented GCX API.
All runtime dependencies are in Python's standard library.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

UTC = timezone.utc


class ValidationError(ValueError):
    """Input is incomplete, ambiguous, unsafe, or inconsistent."""


def utcnow() -> datetime:
    return datetime.now(UTC)


def timestamp(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError("Expected an ISO 8601 timestamp") from exc
    if dt.tzinfo is None:
        raise ValidationError("Timestamp must include a timezone")
    return dt.astimezone(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="auto").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def read_json(path: Path) -> Any:
    if path.stat().st_size > 2_000_000:
        raise ValidationError("Input exceeds the prototype's 2 MB limit")
    def reject_constant(value: str) -> None:
        raise ValidationError(f"Invalid JSON number: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def hostname(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Hostname must be a string")
    value = value.strip()
    if "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            raise ValidationError("Expected a public HTTP(S) hostname")
        value = parsed.hostname or ""
    elif any(c in value for c in "/:@?#"):
        raise ValidationError("Expected a hostname, not a path or port")
    try:
        value = value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValidationError("Invalid internationalized hostname") from exc
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValidationError("IP-address retailer mappings are not supported")
    labels = value.split(".")
    if len(value) > 253 or len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    ):
        raise ValidationError("Invalid hostname")
    return value


def identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ValidationError(f"Invalid {field}")
    return value


def percent(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError(f"Invalid {field}") from exc
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise ValidationError(f"{field} must be between 0 and 100")
    return round(number, 4)


def integer(value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"{field} must be an integer >= {minimum}")
    return value


def money_cents(value: Any) -> int:
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number.as_tuple().exponent < -2:
            raise ValidationError("Money must be nonnegative with at most two decimals")
        return int(number * 100)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Invalid monetary amount") from exc


def validate_config(config: dict) -> dict:
    if config.get("schema_version") != 1:
        raise ValidationError("Unsupported catalog schema")
    providers = config.get("providers")
    retailers = config.get("retailers")
    if not isinstance(providers, dict) or not providers or not isinstance(retailers, list) or not retailers:
        raise ValidationError("Catalog needs providers and retailers")
    for pid, provider in providers.items():
        identifier(pid, "provider_id")
        if not provider.get("allowed_offer_hosts"):
            raise ValidationError("Provider needs explicit allowed offer hosts")
        for host in provider["allowed_offer_hosts"]:
            if hostname(host) != host:
                raise ValidationError("Offer hosts must be canonical")
    ids, domains = set(), set()
    for retailer in retailers:
        rid = identifier(retailer.get("id"), "retailer_id")
        if rid in ids or not isinstance(retailer.get("name"), str) or not retailer["name"].strip():
            raise ValidationError("Duplicate retailer ID or missing retailer name")
        ids.add(rid)
        if not retailer.get("domains"):
            raise ValidationError("Retailer needs a reviewed domain mapping")
        for mapping in retailer["domains"]:
            host = hostname(mapping["host"])
            if host in domains or host != mapping["host"]:
                raise ValidationError("Domain mappings must be unique and canonical")
            domains.add(host)
            for flag in ("include_subdomains", "enabled"):
                if flag in mapping and not isinstance(mapping[flag], bool):
                    raise ValidationError(f"{flag} must be boolean")
    return config


def safe_offer_url(value: str, provider: dict) -> str:
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or url.username or url.password
                or url.port not in (None, 443)
                or url.hostname not in provider["allowed_offer_hosts"]):
            raise ValidationError("Offer URL must use an approved provider HTTPS host")
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid offer URL") from exc
    return value


def listing_metrics(listings: list) -> dict:
    if not isinstance(listings, list):
        raise ValidationError("listings must be an array")
    count = total_value = total_savings = 0
    discounts, seen = [], set()
    for listing in listings:
        key = listing.get("id")
        if not isinstance(key, str) or not key or key in seen:
            raise ValidationError("Listings require unique IDs")
        seen.add(key)
        available = listing.get("available", True)
        if not isinstance(available, bool):
            raise ValidationError("Listing availability must be boolean")
        if not available:
            continue
        quantity = integer(listing.get("quantity", 1), "quantity")
        if not quantity:
            continue
        balance, price = money_cents(listing["balance"]), money_cents(listing["price"])
        if balance <= 0 or price > balance:
            raise ValidationError("Available cards need a positive balance and price <= balance")
        discounts.append(Decimal(balance - price) * 100 / balance)
        count += quantity
        total_value += balance * quantity
        total_savings += (balance - price) * quantity
    def rounded(value: Decimal) -> float:
        return float(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
    return {
        "max_discount_pct": rounded(max(discounts)) if discounts else None,
        "average_discount_pct": rounded(Decimal(total_savings) * 100 / total_value) if total_value else None,
        "average_method": "balance_weighted" if total_value else None,
        "card_count": count,
        "total_inventory_value_cents": total_value,
    }


def normalize_batch(config: dict, batch: dict, now: datetime | None = None) -> list[dict]:
    validate_config(config)
    now = now or utcnow()
    if batch.get("schema_version") != 1 or batch.get("complete") is not True:
        raise ValidationError("A complete, version-1 provider batch is required")
    if not isinstance(batch.get("demo"), bool):
        raise ValidationError("Batch must explicitly declare demo true or false")
    provider_id = batch.get("provider_id")
    if provider_id not in config["providers"]:
        raise ValidationError("Unknown provider")
    identifier(batch.get("run_id"), "run_id")
    observed_at = timestamp(batch.get("observed_at"))
    if observed_at > now + timedelta(minutes=5):
        raise ValidationError("Observation is in the future")
    offers = batch.get("offers")
    if not isinstance(offers, list):
        raise ValidationError("offers must be an array")
    expected = {r["id"] for r in config["retailers"]}
    received = [row.get("retailer_id") for row in offers]
    if len(received) != len(set(received)) or set(received) != expected:
        raise ValidationError("Batch must explicitly cover every configured retailer exactly once")
    normalized = []
    for row in offers:
        status = row.get("status")
        if status not in ("available", "no_inventory"):
            raise ValidationError("Unknown/failed retrieval is not zero inventory")
        if row.get("country", "US") != "US" or row.get("currency", "USD") != "USD":
            raise ValidationError("V1 supports US / USD gift cards only")
        if row.get("offer_type", "discounted_gift_card") != "discounted_gift_card":
            raise ValidationError("Cashback and reward offers are out of scope")
        metrics = {"max_discount_pct": None, "average_discount_pct": None,
                   "average_method": None, "card_count": None,
                   "total_inventory_value_cents": None}
        if "listings" in row:
            if row.get("listings_complete") is not True:
                raise ValidationError("Paginated/partial listings cannot produce full metrics")
            metrics = listing_metrics(row["listings"])
            if (metrics["card_count"] > 0) != (status == "available"):
                raise ValidationError("Listing inventory contradicts declared availability")
        if status == "available":
            for field in ("max_discount_pct", "average_discount_pct"):
                if row.get(field) is not None:
                    number = percent(row[field], field)
                    if field == "max_discount_pct" and metrics[field] is not None and abs(number - metrics[field]) > 0.11:
                        raise ValidationError("Reported max contradicts complete listings")
                    if field == "average_discount_pct":
                        # Do not call an undocumented provider average balance-weighted.
                        metrics["average_method"] = "provider_reported"
                    metrics[field] = number
            if metrics["max_discount_pct"] is None:
                raise ValidationError("Available inventory needs a maximum discount")
            if (metrics["average_discount_pct"] is not None
                    and metrics["average_discount_pct"] > metrics["max_discount_pct"] + 0.11):
                raise ValidationError("Average exceeds maximum discount")
            for field in ("card_count", "total_inventory_value_cents"):
                if row.get(field) is not None:
                    value = integer(row[field], field)
                    if metrics[field] is not None and metrics[field] != value:
                        raise ValidationError(f"Reported {field} contradicts complete listings")
                    metrics[field] = value
            if metrics["card_count"] == 0 or metrics["total_inventory_value_cents"] == 0:
                raise ValidationError("Available inventory cannot have a zero count or balance")
            offer_url = safe_offer_url(row.get("offer_url"), config["providers"][provider_id])
        else:
            if any(row.get(key) not in (None, 0) for key in metrics if key != "average_method"):
                raise ValidationError("No-inventory records must not advertise discounts or inventory")
            metrics.update(card_count=0, total_inventory_value_cents=0)
            offer_url = None
        observation_kind = row.get("observation_kind")
        if observation_kind not in (None, "catalog_advertised"):
            raise ValidationError("Unknown observation kind")
        normalized.append({
            **({"observation_kind": observation_kind} if observation_kind else {}),
            "retailer_id": row["retailer_id"], "provider_id": provider_id,
            "run_id": batch["run_id"], "observed_at": iso(observed_at),
            "status": status, "currency": "USD", "discount_basis": "before_fees",
            "offer_url": offer_url, "demo": batch["demo"], **metrics,
        })
    return normalized


def build_snapshot(config: dict, batch: dict, now: datetime | None = None,
                   max_age_hours: int = 48) -> tuple[dict, list[dict]]:
    now = now or utcnow()
    integer(max_age_hours, "max_age_hours", 1)
    if max_age_hours > 168:
        raise ValidationError("Prototype freshness limit cannot exceed seven days")
    observations = normalize_batch(config, batch, now)
    retailers, domains = {}, {}
    by_id = {row["retailer_id"]: row for row in observations}
    for retailer in config["retailers"]:
        rid = retailer["id"]
        for mapping in retailer["domains"]:
            domains[mapping["host"]] = {
                "retailer_id": rid,
                "include_subdomains": mapping.get("include_subdomains", True),
                "enabled": mapping.get("enabled", True),
            }
        observation = by_id[rid]
        expires_at = timestamp(observation["observed_at"]) + timedelta(hours=max_age_hours)
        if (observation["status"] != "available" or expires_at <= now
                or observation["max_discount_pct"] <= 0):
            continue
        offer = {key: value for key, value in observation.items()
                 if key not in ("retailer_id", "run_id", "demo", "status")}
        offer["expires_at"] = iso(expires_at)
        retailers[rid] = {"name": retailer["name"], "offers": [offer]}
    return {
        "schema_version": 1, "demo": batch["demo"], "generated_at": iso(now),
        "source_observed_at": iso(timestamp(batch["observed_at"])),
        "max_age_hours": max_age_hours,
        "providers": {pid: {"name": item["name"]} for pid, item in config["providers"].items()},
        "domains": domains, "retailers": retailers,
    }, observations


def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".snapshot-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(canonical_json(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def record_history(db_path: Path, batch: dict, rows: list[dict]) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(canonical_json(batch).encode()).hexdigest()
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS runs (provider TEXT, run_id TEXT, digest TEXT, PRIMARY KEY(provider, run_id))")
        db.execute("CREATE TABLE IF NOT EXISTS observations (provider TEXT, retailer TEXT, observed_at TEXT, demo INTEGER, payload TEXT, PRIMARY KEY(provider, retailer, observed_at, demo))")
        existing = db.execute("SELECT digest FROM runs WHERE provider=? AND run_id=?",
                              (batch["provider_id"], batch["run_id"])).fetchone()
        if existing and existing[0] != digest:
            raise ValidationError("A run ID cannot be reused with different input")
        db.execute("INSERT OR IGNORE INTO runs VALUES(?, ?, ?)",
                   (batch["provider_id"], batch["run_id"], digest))
        inserted = 0
        for row in rows:
            key = (row["provider_id"], row["retailer_id"], row["observed_at"], int(row["demo"]))
            payload = canonical_json(row)
            old = db.execute("SELECT payload FROM observations WHERE provider=? AND retailer=? AND observed_at=? AND demo=?", key).fetchone()
            if old and old[0] != payload:
                raise ValidationError("Refusing to rewrite an existing observation")
            cursor = db.execute("INSERT OR IGNORE INTO observations VALUES(?, ?, ?, ?, ?)", (*key, payload))
            inserted += cursor.rowcount
    return inserted


def run_pipeline(config_path: Path, batch_path: Path, output_path: Path,
                 db_path: Path, now: datetime | None = None, max_age_hours: int = 48) -> dict:
    config, batch = read_json(config_path), read_json(batch_path)
    snapshot, observations = build_snapshot(config, batch, now, max_age_hours)
    if output_path.exists():
        old = read_json(output_path)
        if old.get("demo") != snapshot["demo"]:
            raise ValidationError("Demo and production snapshots need separate output paths")
        if timestamp(old["source_observed_at"]) > timestamp(snapshot["source_observed_at"]):
            raise ValidationError("Refusing to replace a newer snapshot with older observations")
    inserted = record_history(db_path, batch, observations)
    atomic_write(output_path, snapshot)
    return {"demo": snapshot["demo"], "observations_inserted": inserted,
            "retailers_with_offers": len(snapshot["retailers"]), "snapshot": str(output_path)}
