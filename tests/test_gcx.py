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


@pytest.mark.parametrize('html', ['', '<html>Enable JavaScript</html>', CAPTURE.replace('17.6% off', '17.6% cashback'),
                                  CAPTURE.replace('4.8% off', '104.8% off'), CAPTURE.replace('</li>', '', 1)])
def test_markup_changes_fail_closed(html):
    with pytest.raises(ValidationError):
        parse_catalog(html)


def test_missing_brand_does_not_become_zero_inventory():
    config = read_json(ROOT / 'config/retailers.json')
    config['retailers'][0]['gcx_path'] = '/buy-missing-gift-cards'
    with pytest.raises(ValidationError, match='did not advertise'):
        collect_batch(config, fetch=lambda *_: CAPTURE)


def test_cash_only_is_not_discounted_inventory():
    with pytest.raises(ValidationError, match='only rewards'):
        collect_batch(read_json(ROOT / 'config/retailers.json'),
                      fetch=lambda *_: CAPTURE.replace('Up to 4.8% off | ', ''))


def test_bounded_pagination_fetches_hidden_pages():
    config = read_json(ROOT / 'config/retailers.json')
    config['retailers'] = [config['retailers'][0]]
    first = CAPTURE[CAPTURE.index('<li'):CAPTURE.index('</li>') + 5]
    first += '<ul class="pagination"><li><a href="/buy-gift-cards?page=3">3</a></li></ul>'
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        return first if len(calls) == 1 else CAPTURE.replace('/buy-lowe-s-gift-cards','/buy-other-gift-cards')
    result = collect_batch(config, fetch=fetch, sleep=lambda _: None)
    assert len(result['offers']) == 1
    assert calls[-1].endswith('?page=2')


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


def test_repeated_pages_abort_instead_of_completing_partial_batch():
    config = read_json(ROOT / 'config/retailers.json')
    config['retailers'][0]['gcx_path'] = '/buy-missing-gift-cards'
    html = CAPTURE + '<ul class="pagination"><li><a href="/buy-gift-cards?page=2">2</a></li></ul>'
    with pytest.raises(ValidationError, match='repeated a product'):
        collect_batch(config, fetch=lambda *_: html, sleep=lambda _: None)


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
    with pytest.raises(ValidationError):
        collect_batch(config, fetch=fetch, sleep=lambda _: None, max_pages=1)
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
