"""Bounded collection of public GCX advertised discounts; never purchases cards.

Catalog percentages are advertisements, not verified listing inventory or quotes.
Missing brands and changed markup abort collection instead of publishing zero stock.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from .pipeline import ValidationError, atomic_write, iso, normalize_batch, read_json, utcnow, validate_config

CATALOG_URL = 'https://gcx.app/buy-gift-cards'
MAX_BYTES = 2_000_000


class CatalogParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.products = []
        self.pages = {1}
        self.product = None
        self.capture = None
        self.pagination = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if tag == 'ul' and 'pagination' in classes:
            self.pagination = True
        if tag == 'li' and 'product-source' in classes:
            if self.product is not None:
                raise ValidationError('Unexpected nested GCX catalog product')
            self.product = {'name': '', 'info': '', 'path': None}
        if tag == 'a':
            href = attrs.get('href', '')
            parsed = urlsplit(urljoin(CATALOG_URL, href))
            if self.pagination and parsed.hostname == 'gcx.app' and parsed.path == '/buy-gift-cards':
                page = parse_qs(parsed.query).get('page', ['1'])[0]
                if page.isdigit() and len(page) <= 4 and int(page) > 0:
                    self.pages.add(int(page))
            if self.product is not None and re.fullmatch(r'/buy-[a-z0-9-]+-gift-cards', parsed.path):
                if parsed.hostname != 'gcx.app' or parsed.query:
                    raise ValidationError('Unexpected GCX offer link')
                self.product['path'] = parsed.path
        if tag == 'span' and self.product is not None:
            self.capture = 'name' if 'name' in classes else 'info' if 'info' in classes else None

    def handle_data(self, data):
        if self.product is not None and self.capture:
            self.product[self.capture] += data

    def handle_endtag(self, tag):
        if tag == 'span':
            self.capture = None
        if tag == 'ul':
            self.pagination = False
        if tag == 'li' and self.product is not None:
            self.products.append(self.product)
            self.product = None


def parse_catalog(html: str) -> tuple[dict, set[int]]:
    parser = CatalogParser()
    parser.feed(html)
    parser.close()
    if parser.product is not None or not parser.products:
        raise ValidationError('GCX catalog is empty, incomplete, or its markup changed')
    products = {}
    for product in parser.products:
        path, info = product['path'], ' '.join(product['info'].split())
        # GCX Cash is a separate promotional reward, never added to the discount.
        match = re.fullmatch(r'Up to (\d+(?:\.\d+)?)% off(?: \| \d+(?:\.\d+)?% GCX Cash)?', info)
        cash_only = re.fullmatch(r'\d+(?:\.\d+)?% GCX Cash', info)
        if not path or not product['name'].strip() or not (match or cash_only):
            raise ValidationError('Unexpected GCX catalog product or discount label')
        discount = float(match[1]) if match else None
        if discount is not None and not 0 <= discount <= 100:
            raise ValidationError('GCX advertised discount outside 0–100%')
        if path in products:
            raise ValidationError('Duplicate GCX catalog product')
        products[path] = discount
    return products, parser.pages


class CatalogRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not silently follow changed routes, login screens or unbudgeted requests.
        raise ValidationError('GCX redirected away from the requested public catalog')


def fetch_catalog(url: str, timeout: float) -> str:
    request = Request(url, headers={'User-Agent': 'GiftCardDiscounts/0.1 (public catalog estimates)',
                                    'Accept': 'text/html'})
    with build_opener(CatalogRedirects()).open(request, timeout=timeout) as response:
        if response.status != 200 or 'text/html' not in response.headers.get('Content-Type', ''):
            raise ValidationError('GCX did not return a public HTML catalog')
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValidationError('GCX page exceeds 2 MB limit')
        return raw.decode('utf-8')


def resolve_retailers(config: dict, query: str) -> list[dict]:
    """Match a retailer by id, display name, domain host, or GCX path fragment."""
    validate_config(config)
    needle = ' '.join(query.lower().split())
    if not needle:
        raise ValidationError('Lookup query is empty')
    matches = []
    for retailer in config['retailers']:
        hosts = [domain['host'] for domain in retailer['domains']]
        tokens = {retailer['id'].lower(), retailer['name'].lower(), *hosts,
                  retailer['gcx_path'].lstrip('/').lower()}
        if needle in tokens or any(needle in token for token in tokens):
            matches.append(retailer)
    if not matches:
        known = ', '.join(r['id'] for r in config['retailers'])
        raise ValidationError(f'No reviewed retailer matches {query!r}; known ids: {known}')
    return matches


def lookup_offers(config: dict, query: str, *, collect=None, **collect_kwargs) -> list[dict]:
    """Collect advertised max discount and purchase-page URL for matching retailers."""
    matches = resolve_retailers(config, query)
    subset = {**config, 'retailers': matches}
    batch = (collect or collect_batch)(subset, **collect_kwargs)
    by_id = {offer['retailer_id']: offer for offer in batch['offers']}
    rows = []
    for retailer in matches:
        offer = by_id[retailer['id']]
        rows.append({
            'retailer_id': retailer['id'],
            'name': retailer['name'],
            'max_discount_pct': offer['max_discount_pct'],
            'offer_url': offer['offer_url'],
            'discount_basis': 'before_fees',
            'observation_kind': offer.get('observation_kind', 'catalog_advertised'),
            'observed_at': batch['observed_at'],
            'demo': False,
        })
    return rows


def collect_batch(config: dict, *, max_pages: int = 20, timeout: float = 20,
                  request_budget: int = 20, delay_seconds: float = 1, retries: int = 2,
                  fetch=None, sleep=time.sleep, now: datetime | None = None) -> dict:
    validate_config(config)
    if (type(max_pages) is not int or not 1 <= max_pages <= 50
            or type(request_budget) is not int or not 1 <= request_budget <= 100
            or type(retries) is not int or not 0 <= retries <= 3
            or not 0 < timeout <= 60 or not 0 <= delay_seconds <= 60):
        raise ValidationError('Invalid GCX collection limits')
    paths = {}
    for retailer in config['retailers']:
        path = retailer.get('gcx_path')
        if not isinstance(path, str) or not re.fullmatch(r'/buy-[a-z0-9-]+-gift-cards', path):
            raise ValidationError('Each retailer needs an explicitly reviewed gcx_path')
        if path in paths:
            raise ValidationError('GCX retailer paths must be unique')
        paths[path] = retailer['id']
    observed_at = now or utcnow()  # Start time conservatively bounds source age.
    fetch = fetch or fetch_catalog
    products, pending, visited, requests = {}, {1}, set(), 0
    while pending:
        page = min(pending)
        pending.remove(page)
        if page > max_pages:
            raise ValidationError('GCX pagination exceeds configured page limit')
        url = CATALOG_URL + (f'?page={page}' if page > 1 else '')
        for attempt in range(retries + 1):
            if requests >= request_budget:
                raise ValidationError('GCX request budget exhausted')
            if requests:
                sleep(delay_seconds * (2 ** attempt))
            requests += 1
            try:
                html = fetch(url, timeout)
                break
            except HTTPError as exc:
                if exc.code in (401, 403, 429) or exc.code < 500 or attempt == retries:
                    raise ValidationError(f'GCX collection stopped: HTTP {exc.code}') from exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt == retries:
                    raise ValidationError('GCX catalog retrieval failed') from exc
        current, pages = parse_catalog(html)
        if products.keys() & current.keys():
            raise ValidationError('GCX pagination repeated a product; refusing ambiguous collection')
        products.update(current)
        visited.add(page)
        if paths.keys() <= products.keys():
            break
        # Pages are sequential, including those hidden behind an ellipsis.
        pending.update(set(range(1, min(max(pages), max_pages) + 1)) - visited)
    missing = paths.keys() - products.keys()
    if missing:
        raise ValidationError('GCX did not advertise every configured retailer; snapshot preserved')
    offers = []
    for path, rid in paths.items():
        discount = products[path]
        if discount is None:
            raise ValidationError(f'GCX has only rewards for {rid}; discounted inventory is unknown')
        offers.append({'retailer_id': rid, 'status': 'available',
                       'offer_url': 'https://gcx.app' + path,
                       'max_discount_pct': discount,
                       'observation_kind': 'catalog_advertised'})
    batch = {'schema_version': 1, 'provider_id': 'gcx', 'demo': False, 'complete': True,
             'run_id': 'gcx-' + uuid4().hex, 'observed_at': iso(observed_at), 'offers': offers}
    normalize_batch(config, batch, observed_at)
    return batch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=Path(__file__).resolve().parents[1] / 'config/retailers-live.json')
    parser.add_argument('--output', type=Path, default=Path('build/live/input.json'))
    parser.add_argument('--max-pages', type=int, default=20)
    parser.add_argument('--request-budget', type=int, default=20)
    args = parser.parse_args()
    try:
        batch = collect_batch(read_json(args.catalog), max_pages=args.max_pages, request_budget=args.request_budget)
        atomic_write(args.output, batch)
    except (ValidationError, OSError, ValueError) as exc:
        parser.exit(1, f'Collection failed: {exc}\n')
    print(json.dumps({'output': str(args.output), 'retailers': len(batch['offers']), 'demo': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
