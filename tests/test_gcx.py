from copy import deepcopy
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from giftcard_tool.gcx import (
    CatalogRedirects,
    collect_batch,
    lookup_offers,
    parse_catalog,
    resolve_retailers,
)
from giftcard_tool.pipeline import ValidationError, build_snapshot, read_json, timestamp

ROOT = Path(__file__).resolve().parents[1]
NOW = timestamp('2026-10-24T09:00:00Z')
CAPTURE = (ROOT / 'fixtures/gcx-catalog-captured.html').read_text()


def test_sanitized_real_capture_excludes_rewards():
    products, pages = parse_catalog(CAPTURE)
    assert products == {'/buy-lowe-s-gift-cards': 4.8,
                        '/buy-domino-s-gift-cards': 17.6,
                        '/buy-starbucks-gift-cards': 5.1}
    assert pages == {1}
    # Rewards text is present in the fixture but never becomes the discount.


def test_collector_builds_real_snapshot_without_fabricated_inventory():
    config = read_json(ROOT / 'config/retailers.json')
    batch = collect_batch(config, fetch=lambda *_: CAPTURE, now=NOW)
    snapshot, observations = build_snapshot(config, batch, now=NOW)
    assert not snapshot['demo']
    assert len(observations) == 3
    for row in observations:
        assert row['observation_kind'] == 'catalog_advertised'
        assert row['card_count'] is row['average_discount_pct'] is row['total_inventory_value_cents'] is None
        assert row['discount_basis'] == 'before_fees'


@pytest.mark.parametrize('html', ['', '<html>Enable JavaScript</html>'])
def test_missing_catalog_markup_is_rejected(html):
    with pytest.raises(ValidationError):
        parse_catalog(html)


@pytest.mark.parametrize('html, missing', [
    (CAPTURE.replace('17.6% off', '17.6% cashback'), '/buy-domino-s-gift-cards'),
    (CAPTURE.replace('4.8% off', '104.8% off'), '/buy-lowe-s-gift-cards'),
    (CAPTURE.replace('</li>', '', 1), '/buy-lowe-s-gift-cards'),
    (CAPTURE.replace('href="/buy-lowe-s-gift-cards"',
                     'href="https://example.com/buy-lowe-s-gift-cards"'), '/buy-lowe-s-gift-cards'),
    (CAPTURE.replace('Lowe&#x27;s Gift Cards', ''), '/buy-lowe-s-gift-cards'),
    (CAPTURE.replace('Up to 4.8% off | 3.0% GCX Cash', ''), '/buy-lowe-s-gift-cards'),
])
def test_bad_product_is_skipped_without_losing_other_products(html, missing, caplog):
    products, _ = parse_catalog(html)
    assert missing not in products
    assert len(products) == 2
    assert 'Skipping' in caplog.text


def test_nested_spans_preserve_name_and_discount_text():
    html = CAPTURE.replace('Lowe&#x27;s Gift Cards', 'Lowe<span>&#x27;s</span> Gift Cards')
    html = html.replace('Up to 4.8% off', 'Up to <span>4.8</span>% off')
    batch = collect_batch(read_json(ROOT / 'config/retailers.json'), fetch=lambda *_: html)
    lowes = next(row for row in batch['gcx_catalog'] if 'lowe-s' in row['offer_url'])
    assert lowes['name'] == "Lowe's Gift Cards"
    assert lowes['max_discount_pct'] == 4.8
    assert batch['complete'] is True


def test_malformed_url_product_is_skipped(caplog):
    html = CAPTURE.replace('href="/buy-lowe-s-gift-cards"', 'href="https://[invalid"')
    products, _ = parse_catalog(html)
    assert products == {'/buy-domino-s-gift-cards': 17.6, '/buy-starbucks-gift-cards': 5.1}
    assert 'Skipping invalid GCX product' in caplog.text


def test_missing_brand_does_not_become_zero_inventory(caplog):
    config = read_json(ROOT / 'config/retailers.json')
    config['retailers'][0]['gcx_path'] = '/buy-missing-gift-cards'
    batch = collect_batch(config, fetch=lambda *_: CAPTURE)
    assert batch['complete'] is False
    assert len(batch['offers']) == 2
    assert config['retailers'][0]['id'] not in {offer['retailer_id'] for offer in batch['offers']}
    assert 'no valid GCX discount' in caplog.text


def test_cash_only_is_not_discounted_inventory():
    batch = collect_batch(read_json(ROOT / 'config/retailers.json'),
                          fetch=lambda *_: CAPTURE.replace('Up to 4.8% off | ', ''))
    assert batch['complete'] is False
    assert {offer['retailer_id'] for offer in batch['offers']} == {'dominos', 'starbucks'}
    lowes = next(row for row in batch['gcx_catalog'] if 'lowe-s' in row['offer_url'])
    assert lowes['max_discount_pct'] is None


def test_bounded_pagination_fetches_hidden_pages():
    config = read_json(ROOT / 'config/retailers.json')
    config['retailers'] = [config['retailers'][0]]
    first = CAPTURE[CAPTURE.index('<li'):CAPTURE.index('</li>') + 5]
    first += '<ul class="pagination"><li><a href="/buy-gift-cards?page=3">3</a></li></ul>'
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            return first
        if len(calls) == 2:
            return CAPTURE.replace('/buy-lowe-s-gift-cards', '/buy-other-gift-cards')
        return first.replace('/buy-lowe-s-gift-cards', '/buy-another-gift-cards')
    result = collect_batch(config, fetch=fetch, sleep=lambda _: None)
    assert len(result['offers']) == 1
    assert calls[-1].endswith('?page=3')
    assert len(calls) == 3


def test_collects_unconfigured_products_after_all_configured_products_found():
    pages = [CAPTURE + '<ul class="pagination"><li><a href="?page=2">2</a></li></ul>',
             CAPTURE[CAPTURE.index('<li'):CAPTURE.index('</li>') + 5]
             .replace('/buy-lowe-s-gift-cards', '/buy-other-gift-cards')]
    calls = []
    def fetch(url, _timeout):
        calls.append(url)
        return pages[len(calls) - 1]
    batch = collect_batch(read_json(ROOT / 'config/retailers.json'),
                          fetch=fetch, sleep=lambda _: None)
    assert len(calls) == 2
    assert batch['complete'] is True
    assert len(batch['offers']) == 3
    assert len(batch['gcx_catalog']) == 4
    assert any(row['offer_url'] == 'https://gcx.app/buy-other-gift-cards'
               for row in batch['gcx_catalog'])


def test_collection_continues_after_unparseable_page(caplog):
    pages = [CAPTURE + '<ul class="pagination"><li><a href="?page=3">3</a></li></ul>',
             '<html>Unexpected markup</html>',
             CAPTURE[CAPTURE.index('<li'):CAPTURE.index('</li>') + 5]
             .replace('/buy-lowe-s-gift-cards', '/buy-other-gift-cards')]
    calls = []
    def fetch(url, _timeout):
        calls.append(url)
        return pages[len(calls) - 1]
    batch = collect_batch(read_json(ROOT / 'config/retailers.json'),
                          fetch=fetch, sleep=lambda _: None)
    assert len(calls) == 3
    assert len(batch['gcx_catalog']) == 4
    assert 'Skipping GCX page 2' in caplog.text


def test_bad_configured_product_keeps_other_valid_offers(caplog):
    batch = collect_batch(read_json(ROOT / 'config/retailers.json'),
                          fetch=lambda *_: CAPTURE.replace('17.6% off', '17.6% cashback'))
    assert batch['complete'] is False
    assert {offer['retailer_id'] for offer in batch['offers']} == {'lowes', 'starbucks'}
    assert '17.6% cashback' in caplog.text


def test_no_valid_configured_discounts_preserves_snapshot():
    config = read_json(ROOT / 'config/retailers.json')
    config['retailers'] = [config['retailers'][0]]
    with pytest.raises(ValidationError, match='no valid configured discounts'):
        collect_batch(config, fetch=lambda *_: CAPTURE.replace('17.6% off', '17.6% cashback'))


@pytest.mark.parametrize('code', [401, 403, 429])
def test_access_errors_never_retried(code):
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        raise HTTPError(url, code, 'blocked', {}, None)
    with pytest.raises(ValidationError, match=f'HTTP {code}'):
        collect_batch(read_json(ROOT / 'config/retailers.json'), fetch=fetch)
    assert len(calls) == 1


def test_retries_respect_global_budget():
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        raise URLError('timeout')
    with pytest.raises(ValidationError, match='budget exhausted'):
        collect_batch(read_json(ROOT / 'config/retailers.json'), fetch=fetch,
                      sleep=lambda _: None, request_budget=1)
    assert len(calls) == 1


def test_repeated_products_are_skipped_and_first_discount_preserved(caplog):
    config = read_json(ROOT / 'config/retailers.json')
    config['retailers'][0]['gcx_path'] = '/buy-missing-gift-cards'
    html = CAPTURE + '<ul class="pagination"><li><a href="/buy-gift-cards?page=2">2</a></li></ul>'
    calls = []
    def fetch(*_):
        calls.append(1)
        return html if len(calls) == 1 else html.replace('17.6% off', '99% off')
    batch = collect_batch(config, fetch=fetch, sleep=lambda _: None)
    assert batch['complete'] is False
    assert len(batch['gcx_catalog']) == 3
    assert next(row for row in batch['gcx_catalog']
                if row['offer_url'].endswith('/buy-domino-s-gift-cards'))['max_discount_pct'] == 17.6
    assert 'repeated GCX product' in caplog.text


def test_unreviewed_mapping_rejected_before_network():
    config = read_json(ROOT / 'config/retailers.json')
    del config['retailers'][0]['gcx_path']
    with pytest.raises(ValidationError, match='reviewed gcx_path'):
        collect_batch(config, fetch=lambda *_: pytest.fail('network called'))


def test_redirects_stop_before_another_request():
    with pytest.raises(ValidationError, match='redirected'):
        CatalogRedirects().redirect_request(None, None, 302, '', {}, 'https://gcx.app/login')


def test_giant_pagination_is_bounded():
    config = read_json(ROOT / 'config/retailers.json')
    config['retailers'][0]['gcx_path'] = '/buy-missing-gift-cards'
    html = CAPTURE + '<ul class="pagination"><li><a href="/buy-gift-cards?page=9999">9999</a></li></ul>'
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        return html
    result = collect_batch(config, fetch=fetch, sleep=lambda _: None, max_pages=1)
    assert result['complete'] is False
    assert len(calls) == 1


@pytest.mark.parametrize('query', ['dominos', 'Domino', 'dominos.com', 'buy-domino-s-gift-cards'])
def test_resolve_retailers_matches_id_name_domain_or_path(query):
    matches = resolve_retailers(read_json(ROOT / 'config/retailers.json'), query)
    assert [row['id'] for row in matches] == ['dominos']


def test_lookup_returns_max_discount_and_purchase_link():
    config = read_json(ROOT / 'config/retailers.json')
    rows = lookup_offers(config, 'lowes', fetch=lambda *_: CAPTURE, now=NOW)
    assert rows == [{
        'retailer_id': 'lowes',
        'name': "Lowe's",
        'max_discount_pct': 4.8,
        'offer_url': 'https://gcx.app/buy-lowe-s-gift-cards',
        'discount_basis': 'before_fees',
        'observation_kind': 'catalog_advertised',
        'observed_at': '2026-10-24T09:00:00Z',
        'demo': False,
    }]


def test_lookup_unknown_retailer_fails_before_network():
    with pytest.raises(ValidationError, match='No reviewed retailer'):
        lookup_offers(read_json(ROOT / 'config/retailers.json'), 'not-a-store',
                      collect=lambda *_args, **_kwargs: pytest.fail('network called'))
