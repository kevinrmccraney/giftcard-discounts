const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Core = require('../extension/core.js');
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, '../extension/demo.json'), 'utf8'));
const NOW = Date.parse('2026-10-01T13:00:00Z');
const fresh = () => Core.rebaseDemo(fixture, NOW);
const find = (snapshot, host, options = {}) => Core.findOffer(snapshot, host, { allowDemo:true, now:NOW, ...options });

test('snapshot validates', () => assert.equal(Core.validateSnapshot(fresh()).demo, true));
test('exact match', () => assert.equal(find(fresh(), 'dominos.com').retailerId, 'dominos'));
for (const discount of [0, 1, 1.01]) {
  test(`popup requires advertised discount strictly greater than 1%: ${discount}`, () => {
    const snapshot = fresh();
    snapshot.retailers.dominos.offers[0].max_discount_pct = discount;
    assert.equal(Boolean(find(snapshot, 'dominos.com')), discount > 1);
  });
}
test('subdomain match', () => assert.equal(find(fresh(), 'order.dominos.com').retailerId, 'dominos'));
test('hostname normalization', () => assert.equal(Core.normalizeHostname('WWW.Dominos.com.'), 'www.dominos.com'));
test('label-boundary matching', () => assert.equal(find(fresh(), 'notdominos.com'), null));
test('lookalike suffix does not match', () => assert.equal(find(fresh(), 'dominos.com.attacker.example'), null));
test('no inventory does not display', () => assert.equal(find(fresh(), 'lowes.com'), null));
test('demo is opt-in', () => assert.equal(Core.findOffer(fresh(), 'dominos.com', { now:NOW }), null));
test('expired offers hidden despite new generated_at', () => { const s = fresh(); s.generated_at = new Date(NOW+49*3600000).toISOString(); assert.equal(find(s, 'dominos.com', { now:NOW+49*3600000 }), null); });
test('future observations hidden', () => assert.equal(find(fresh(), 'dominos.com', { now:NOW-3600000 }), null));
test('permanent suppression', () => assert.equal(find(fresh(), 'dominos.com', { suppressed:{dominos:true} }), null));
test('session seen is retailer-wide', () => assert.equal(find(fresh(), 'order.dominos.com', { seen:{dominos:true} }), null));
test('active snooze', () => assert.equal(find(fresh(), 'dominos.com', { snoozed:{dominos:new Date(NOW+1000).toISOString()} }), null));
test('expired snooze', () => assert.ok(find(fresh(), 'dominos.com', { snoozed:{dominos:new Date(NOW-1000).toISOString()} })));
test('disabled specific mapping blocks inherited parent', () => { const s=fresh(); s.domains['jobs.dominos.com']={retailer_id:'dominos',include_subdomains:true,enabled:false}; assert.equal(find(s,'jobs.dominos.com'),null); });
test('exact-only mapping excludes subdomains', () => { const s=fresh(); s.domains['dominos.com'].include_subdomains=false; assert.equal(find(s,'order.dominos.com'),null); assert.ok(find(s,'dominos.com')); });
test('multiple domains share identity', () => { const s=fresh(); s.domains['dominos.example']={...s.domains['dominos.com']}; assert.equal(find(s,'dominos.example').retailerId,'dominos'); });
test('untrusted link rejected', () => { const s=fresh(); s.retailers.dominos.offers[0].offer_url='https://gcx.app.evil.example/'; assert.throws(()=>Core.validateSnapshot(s)); });
test('credentials in offer URL rejected', () => assert.equal(Core.safeOfferURL('https://user:pass@gcx.app/','gcx'),false));
test('unsupported schema rejected', () => { const s=fresh(); s.schema_version=2; assert.throws(()=>Core.validateSnapshot(s)); });
test('NaN percentage rejected', () => { const s=fresh(); s.retailers.dominos.offers[0].max_discount_pct=NaN; assert.throws(()=>Core.validateSnapshot(s)); });
test('real data cannot be rebased', () => { const s=fresh(); s.demo=false; assert.throws(()=>Core.rebaseDemo(s)); });
test('expiry cannot be extended beyond declared observation age', () => { const s=fresh(); s.retailers.dominos.offers[0].expires_at=new Date(NOW+100*3600000).toISOString(); assert.equal(find(s,'dominos.com',{now:NOW+49*3600000}),null); });
