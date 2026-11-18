const test = require('node:test');
const assert = require('node:assert/strict');
const Core = require('../extension/core.js');
const createController = require('../extension/controller.js');
const fixture = require('../extension/demo.json');
const NOW = Date.parse('2026-10-01T13:00:00Z');
function storage(initial = {}) {
  let data = structuredClone(initial);
  return { async get(key) { return structuredClone(key ? {[key]:data[key]} : data); },
    async set(value) { Object.assign(data, structuredClone(value)); },
    async clear() { data = {}; } };
}
function setup({demo=false, fetcher}={}) {
  const api = { storage:{ local:storage({settings:{snapshotURL:'https://snapshot.example/snapshot.json',demoMode:demo}}),session:storage() },runtime:{getURL:p=>`extension://local/${p}`} };
  const snapshot=Core.rebaseDemo(fixture,NOW); snapshot.demo=demo;
  let count=0;
  const fetchImpl=async(...args)=>{count++;return fetcher?fetcher(...args):new Response(JSON.stringify(snapshot),{headers:{ETag:'"fixture-1"'}});};
  return {api,snapshot,fetchImpl,count:()=>count,controller:createController(api,fetchImpl,Core,()=>NOW)};
}
test('no source and no demo makes no requests',async()=>{const s=setup();await s.api.storage.local.set({settings:{}});assert.equal(await s.controller.offerFor('dominos.com'),null);assert.equal(s.count(),0);});
test('one request per session despite different retailers',async()=>{const s=setup();await s.controller.offerFor('dominos.com');await s.controller.offerFor('starbucks.com');assert.equal(s.count(),1);});
test('concurrent tabs produce one notification',async()=>{const s=setup();const offers=await Promise.all([s.controller.offerFor('dominos.com'),s.controller.offerFor('order.dominos.com')]);assert.equal(offers.filter(Boolean).length,1);assert.equal(s.count(),1);});
test('worker restart preserves seen state and cache',async()=>{const s=setup();assert.ok(await s.controller.offerFor('dominos.com'));const other=createController(s.api,s.fetchImpl,Core,()=>NOW);assert.equal(await other.offerFor('dominos.com'),null);assert.equal(s.count(),1);});
test('new browser session refreshes and clears seen',async()=>{const s=setup();await s.controller.offerFor('dominos.com');await s.api.storage.session.clear();assert.ok(await s.controller.offerFor('dominos.com'));assert.equal(s.count(),2);});
test('permanent suppression survives new session',async()=>{const s=setup();await s.controller.offerFor('dominos.com');await s.controller.hide('dominos.com','dominos','forever');await s.api.storage.session.clear();assert.equal(await s.controller.offerFor('dominos.com'),null);});
test('snooze survives new session',async()=>{const s=setup();await s.controller.offerFor('dominos.com');await s.controller.hide('dominos.com','dominos','snooze');await s.api.storage.session.clear();assert.equal(await s.controller.offerFor('dominos.com'),null);});
test('retailer mismatch cannot hide unrelated retailer',async()=>{const s=setup();await s.controller.offerFor('dominos.com');await assert.rejects(s.controller.hide('dominos.com','starbucks','forever'));});
test('refresh failure retains fresh cache without per-page retry',async()=>{const s=setup();await s.controller.refresh();await s.api.storage.session.clear();let requests=0;const controller=createController(s.api,async()=>{requests++;throw new Error('offline');},Core,()=>NOW);assert.ok(await controller.offerFor('dominos.com'));assert.ok(await controller.offerFor('starbucks.com'));assert.equal(requests,1);});
test('malformed response does not replace cache',async()=>{const s=setup();await s.controller.refresh();const controller=createController(s.api,async()=>new Response('{bad'),Core,()=>NOW);const previous=(await s.api.storage.local.get('cache')).cache;await controller.refresh(true);assert.deepEqual((await s.api.storage.local.get('cache')).cache,previous);});
test('304 keeps original observation timestamp',async()=>{const s=setup();await s.controller.refresh();const before=(await s.api.storage.local.get('cache')).cache.snapshot;let headers;const controller=createController(s.api,async(_,opts)=>{headers=opts.headers;return new Response(null,{status:304});},Core,()=>NOW+3600000);await controller.refresh(true);assert.equal(headers['If-None-Match'],'"fixture-1"');assert.deepEqual((await s.api.storage.local.get('cache')).cache.snapshot,before);});
test('demo mode off rejects synthetic remote feed',async()=>{const s=setup({fetcher:async()=>new Response(JSON.stringify(Core.rebaseDemo(fixture,NOW)))});assert.equal(await s.controller.offerFor('dominos.com'),null);});
test('requests omit credentials and browsing URL',async()=>{let request;const s=setup({fetcher:async(url,opts)=>{request={url,opts};const snapshot=Core.rebaseDemo(fixture,NOW);snapshot.demo=false;return new Response(JSON.stringify(snapshot));}});await s.controller.offerFor('dominos.com');assert.equal(request.url,'https://snapshot.example/snapshot.json');assert.equal(request.opts.credentials,'omit');assert.equal(request.opts.referrerPolicy,'no-referrer');assert.ok(!JSON.stringify(request).includes('dominos'));});
test('remote snapshot rollback rejected',async()=>{const s=setup();await s.controller.refresh();const old=Core.rebaseDemo(fixture,NOW-1000);old.demo=false;const controller=createController(s.api,async()=>new Response(JSON.stringify(old)),Core,()=>NOW);await controller.refresh(true);assert.equal((await s.api.storage.local.get('cache')).cache.snapshot.source_observed_at,new Date(NOW).toISOString());});
test('demo only fetches a bundled extension resource',async()=>{let requested;const s=setup({demo:true,fetcher:async url=>{requested=url;return new Response(JSON.stringify(fixture));}});const result=await s.controller.offerFor('dominos.com');assert.equal(result.demo,true);assert.equal(requested,'extension://local/demo.json');});
