/* Pure, dependency-free snapshot validation and hostname matching. */
(function (root) {
  'use strict';
  const MAX_BYTES = 2000000;
  const ALLOWED_OFFER_HOSTS = Object.freeze({ gcx: ['gcx.app', 'gcx.raise.com'] });
  const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const pct = value => finite(value) && value >= 0 && value <= 100;
  function assert(condition, message) { if (!condition) throw new Error(message); }
  function time(value) {
    assert(typeof value === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(value), 'Timezone missing');
    const result = Date.parse(value);
    assert(Number.isFinite(result), 'Invalid timestamp');
    return result;
  }
  function normalizeHostname(value) {
    if (typeof value !== 'string') return null;
    try {
      const input = value.trim();
      if (!input.includes('://') && /[/:@?#]/.test(input)) return null;
      const url = new URL(input.includes('://') ? input : `https://${input}`);
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
      const host = url.hostname.toLowerCase().replace(/\.$/, '');
      if (/^[\d.]+$/.test(host) || host.length > 253 || !host.includes('.')) return null;
      if (!host.split('.').every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) return null;
      return host;
    } catch (_) { return null; }
  }
  function safeOfferURL(value, providerId) {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && !url.username && !url.password && !url.port &&
        own(ALLOWED_OFFER_HOSTS, providerId) && ALLOWED_OFFER_HOSTS[providerId].includes(url.hostname);
    } catch (_) { return false; }
  }
  function validateSnapshot(snapshot) {
    assert(record(snapshot) && snapshot.schema_version === 1, 'Unsupported snapshot schema');
    assert(typeof snapshot.demo === 'boolean', 'Snapshot must declare demo mode');
    assert(record(snapshot.domains) && record(snapshot.retailers) && record(snapshot.providers), 'Invalid snapshot maps');
    assert(Number.isInteger(snapshot.max_age_hours) && snapshot.max_age_hours > 0 && snapshot.max_age_hours <= 168, 'Invalid freshness limit');
    time(snapshot.generated_at); time(snapshot.source_observed_at);
    assert(new TextEncoder().encode(JSON.stringify(snapshot)).byteLength <= MAX_BYTES, 'Snapshot too large');
    for (const [host, mapping] of Object.entries(snapshot.domains)) {
      assert(normalizeHostname(host) === host && record(mapping), 'Invalid domain mapping');
      assert(typeof mapping.retailer_id === 'string' && typeof mapping.enabled === 'boolean' &&
        typeof mapping.include_subdomains === 'boolean', 'Invalid domain flags');
    }
    for (const [id, retailer] of Object.entries(snapshot.retailers)) {
      assert(/^[a-z0-9][a-z0-9_-]{0,63}$/.test(id) && record(retailer) &&
        typeof retailer.name === 'string' && retailer.name.length > 0 && retailer.name.length <= 200 &&
        Array.isArray(retailer.offers), 'Invalid retailer');
      const seen = new Set();
      for (const offer of retailer.offers) {
        assert(record(offer) && !seen.has(offer.provider_id), 'Duplicate provider offer');
        seen.add(offer.provider_id);
        assert(own(snapshot.providers, offer.provider_id), 'Unknown provider');
        assert(safeOfferURL(offer.offer_url, offer.provider_id), 'Untrusted offer URL');
        assert(pct(offer.max_discount_pct), 'Invalid maximum discount');
        assert(offer.average_discount_pct === null || (pct(offer.average_discount_pct) &&
          offer.average_discount_pct <= offer.max_discount_pct + 0.11), 'Invalid average discount');
        assert(['balance_weighted', 'provider_reported', null].includes(offer.average_method), 'Invalid average method');
        assert(offer.currency === 'USD' && offer.discount_basis === 'before_fees', 'Unsupported offer type');
        assert(offer.card_count === null || (Number.isInteger(offer.card_count) && offer.card_count > 0), 'Invalid inventory count');
        assert(offer.total_inventory_value_cents === null ||
          (Number.isInteger(offer.total_inventory_value_cents) && offer.total_inventory_value_cents > 0), 'Invalid inventory value');
        assert(time(offer.expires_at) > time(offer.observed_at), 'Invalid expiry');
      }
    }
    return snapshot;
  }
  function matchRetailer(snapshot, input) {
    const host = normalizeHostname(input);
    if (!host) return null;
    // Walk whole labels only. An explicit disabled/more-specific mapping blocks fallback.
    const labels = host.split('.');
    for (let index = 0; index < labels.length - 1; index += 1) {
      const candidate = labels.slice(index).join('.');
      if (!own(snapshot.domains, candidate)) continue;
      const mapping = snapshot.domains[candidate];
      if (!mapping.enabled || (index > 0 && !mapping.include_subdomains)) return null;
      return own(snapshot.retailers, mapping.retailer_id) ? mapping.retailer_id : null;
    }
    return null;
  }
  function findOffer(snapshot, input, options = {}) {
    if (!snapshot || (snapshot.demo && !options.allowDemo)) return null;
    const now = options.now ?? Date.now();
    const retailerId = matchRetailer(snapshot, input);
    if (!retailerId || options.suppressed?.[retailerId] || options.seen?.[retailerId]) return null;
    if (Date.parse(options.snoozed?.[retailerId] ?? '') > now) return null;
    const retailer = snapshot.retailers[retailerId];
    const offers = retailer.offers.filter(offer => {
      const observed = time(offer.observed_at);
      const expiration = Math.min(time(offer.expires_at), observed + snapshot.max_age_hours * 3600000);
      return observed <= now + 300000 && expiration > now && offer.max_discount_pct > 1 &&
        safeOfferURL(offer.offer_url, offer.provider_id);
    }).sort((a, b) => b.max_discount_pct - a.max_discount_pct || a.provider_id.localeCompare(b.provider_id));
    if (!offers.length) return null;
    return { retailerId, name: retailer.name, demo: snapshot.demo,
      providerName: snapshot.providers[offers[0].provider_id]?.name ?? offers[0].provider_id,
      offer: offers[0], offers };
  }
  function rebaseDemo(snapshot, now = Date.now()) {
    assert(snapshot.demo === true, 'Only synthetic data may be rebased');
    const copy = JSON.parse(JSON.stringify(snapshot));
    copy.generated_at = copy.source_observed_at = new Date(now).toISOString();
    for (const retailer of Object.values(copy.retailers)) {
      for (const offer of retailer.offers) {
        offer.observed_at = copy.source_observed_at;
        offer.expires_at = new Date(now + copy.max_age_hours * 3600000).toISOString();
      }
    }
    return validateSnapshot(copy);
  }
  const api = { MAX_BYTES, normalizeHostname, safeOfferURL, validateSnapshot, matchRetailer, findOffer, rebaseDemo };
  root.GiftCardCore = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
