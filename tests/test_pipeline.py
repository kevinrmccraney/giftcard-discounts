from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sqlite3

import pytest

from giftcard_tool.pipeline import (
    ValidationError, build_snapshot, hostname, listing_metrics, money_cents,
    normalize_batch, percent, read_json, run_pipeline, timestamp,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = timestamp('2026-10-01T13:00:00Z')

@pytest.fixture
def config(): return read_json(ROOT / 'config/retailers.json')

@pytest.fixture
def batch(): return read_json(ROOT / 'fixtures/demo-batch.json')


def test_weighted_metrics(batch):
    metrics = listing_metrics(batch['offers'][0]['listings'])
    assert metrics == {'max_discount_pct': 12.0, 'average_discount_pct': 11.2,
                       'average_method': 'balance_weighted', 'card_count': 3,
                       'total_inventory_value_cents': 12500}


def test_provider_average_is_not_mislabeled(config, batch):
    rows = normalize_batch(config, batch, NOW)
    assert rows[1]['average_method'] == 'provider_reported'
    assert rows[1]['total_inventory_value_cents'] is None


def test_unknown_average_is_null(config, batch):
    del batch['offers'][1]['average_discount_pct']
    rows = normalize_batch(config, batch, NOW)
    assert rows[1]['average_discount_pct'] is None
    assert rows[1]['average_method'] is None


def test_snapshot_omits_no_inventory(config, batch):
    snapshot, rows = build_snapshot(config, batch, NOW)
    assert set(snapshot['retailers']) == {'dominos', 'starbucks'}
    assert rows[2]['status'] == 'no_inventory'
    assert snapshot['demo'] is True
    assert snapshot['retailers']['dominos']['offers'][0]['discount_basis'] == 'before_fees'


def test_all_no_inventory_is_a_valid_empty_snapshot(config, batch):
    batch['offers'] = [{'retailer_id': row['retailer_id'], 'status': 'no_inventory'} for row in batch['offers']]
    snapshot, rows = build_snapshot(config, batch, NOW)
    assert snapshot['retailers'] == {}
    assert len(rows) == 3


def test_expiry_does_not_depend_on_generation_time(config, batch):
    snapshot, _ = build_snapshot(config, batch, NOW + timedelta(hours=49))
    assert snapshot['retailers'] == {}
    assert snapshot['source_observed_at'] == batch['observed_at']


@pytest.mark.parametrize('change', [
    lambda b: b.update(complete=False),
    lambda b: b['offers'].pop(),
    lambda b: b['offers'].append(deepcopy(b['offers'][0])),
    lambda b: b['offers'][0].update(status='unknown'),
    lambda b: b['offers'][0].update(listings_complete=False),
    lambda b: b['offers'][0].update(offer_type='cashback'),
    lambda b: b['offers'][0].update(currency='EUR'),
    lambda b: b['offers'][0].update(max_discount_pct=90),
    lambda b: b.update(demo=None),
    lambda b: b.update(observed_at='2030-01-01T00:00:00Z'),
    lambda b: b['offers'][1].update(card_count=0),
    lambda b: b['offers'][1].update(average_discount_pct=80),
    lambda b: b['offers'][2].update(max_discount_pct=12),
])
def test_bad_batch_is_rejected(config, batch, change):
    change(batch)
    with pytest.raises(ValidationError): normalize_batch(config, batch, NOW)


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'http://gcx.app/offer', 'https://gcx.app.evil.example/offer', 'https://user:pass@gcx.app/offer', 'https://gcx.app:444/offer'])
def test_bad_offer_url(config, batch, url):
    batch['offers'][0]['offer_url'] = url
    with pytest.raises(ValidationError): build_snapshot(config, batch, NOW)


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1, 101])
def test_percent_rejects_invalid(value):
    with pytest.raises(ValidationError): percent(value, 'test')


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '1.001', True])
def test_money_rejects_invalid(value):
    with pytest.raises(ValidationError): money_cents(value)


def test_sold_listings_are_excluded():
    result = listing_metrics([{'id':'a','available':False}, {'id':'b','balance':'100.00','price':'90.00'}])
    assert result['max_discount_pct'] == 10
    assert result['card_count'] == 1


def test_duplicate_listing_rejected(batch):
    rows = batch['offers'][0]['listings']; rows.append(deepcopy(rows[0]))
    with pytest.raises(ValidationError): listing_metrics(rows)


@pytest.mark.parametrize('value,expected', [('WWW.Dominos.com.','www.dominos.com'), ('https://order.dominos.com/path','order.dominos.com'), ('b\u00fccher.example','xn--bcher-kva.example')])
def test_normalize_host(value, expected): assert hostname(value) == expected


@pytest.mark.parametrize('value', ['localhost','127.0.0.1','dominos.com/path','dominos.com:443','a..com','-a.com','javascript://dominos.com'])
def test_bad_host(value):
    with pytest.raises(ValidationError): hostname(value)


def test_timezone_required():
    with pytest.raises(ValidationError): timestamp('2026-10-01T13:00:00')


def write_inputs(tmp_path, config, batch):
    catalog = tmp_path / 'catalog.json'; source = tmp_path / 'batch.json'
    catalog.write_text(json.dumps(config)); source.write_text(json.dumps(batch))
    return catalog, source, tmp_path / 'snapshot.json', tmp_path / 'history.sqlite3'


def test_idempotent_import(tmp_path, config, batch):
    args = write_inputs(tmp_path, config, batch)
    assert run_pipeline(*args, now=NOW)['observations_inserted'] == 3
    assert run_pipeline(*args, now=NOW)['observations_inserted'] == 0
    with sqlite3.connect(args[3]) as db:
        assert db.execute('select count(*) from observations').fetchone()[0] == 3


def test_invalid_batch_preserves_snapshot_and_history(tmp_path, config, batch):
    args = write_inputs(tmp_path, config, batch); run_pipeline(*args, now=NOW)
    before = args[2].read_bytes(); batch['complete'] = False; args[1].write_text(json.dumps(batch))
    with pytest.raises(ValidationError): run_pipeline(*args, now=NOW)
    assert args[2].read_bytes() == before
    with sqlite3.connect(args[3]) as db:
        assert db.execute('select count(*) from observations').fetchone()[0] == 3


def test_history_accumulates(tmp_path, config, batch):
    args = write_inputs(tmp_path, config, batch); run_pipeline(*args, now=NOW)
    batch.update(run_id='second-observation', observed_at='2026-10-01T12:30:00Z')
    args[1].write_text(json.dumps(batch)); run_pipeline(*args, now=NOW)
    with sqlite3.connect(args[3]) as db:
        assert db.execute('select count(*) from observations').fetchone()[0] == 6


def test_reused_run_with_changed_payload_rejected(tmp_path, config, batch):
    args = write_inputs(tmp_path, config, batch); run_pipeline(*args, now=NOW)
    batch['offers'][1]['max_discount_pct'] = 5
    args[1].write_text(json.dumps(batch))
    with pytest.raises(ValidationError, match='run ID'): run_pipeline(*args, now=NOW)


def test_no_inventory_replaces_previous_offers(tmp_path, config, batch):
    args = write_inputs(tmp_path, config, batch); run_pipeline(*args, now=NOW)
    batch.update(run_id='all-sold', observed_at='2026-10-01T12:30:00Z')
    batch['offers'] = [{'retailer_id': row['retailer_id'], 'status':'no_inventory'} for row in batch['offers']]
    args[1].write_text(json.dumps(batch)); run_pipeline(*args, now=NOW)
    assert read_json(args[2])['retailers'] == {}


def test_snapshot_rollback_rejected(tmp_path, config, batch):
    args = write_inputs(tmp_path, config, batch); run_pipeline(*args, now=NOW)
    batch.update(run_id='older', observed_at='2026-09-30T12:00:00Z')
    args[1].write_text(json.dumps(batch))
    with pytest.raises(ValidationError, match='older'): run_pipeline(*args, now=NOW)


def test_demo_cannot_replace_production(tmp_path, config, batch):
    args = write_inputs(tmp_path, config, batch); run_pipeline(*args, now=NOW)
    batch['demo'] = False; args[1].write_text(json.dumps(batch))
    with pytest.raises(ValidationError, match='separate'): run_pipeline(*args, now=NOW)
