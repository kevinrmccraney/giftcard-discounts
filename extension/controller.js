/* Background logic isolated from browser globals so it can be tested under Node. */
(function (root) {
  'use strict';
  function createController(api, fetchImpl, Core, now = () => Date.now()) {
    let refreshPromise = null;
    let queue = Promise.resolve();
    const serialize = job => { const pending = queue.then(job); queue = pending.catch(() => {}); return pending; };
    async function preferences() {
      const { settings = {} } = await api.storage.local.get('settings');
      return { snapshotURL: '', demoMode: false, suppressed: {}, snoozed: {}, ...settings };
    }
    async function fetchBounded(response) {
      if (Number(response.headers.get('Content-Length')) > Core.MAX_BYTES) throw new Error('Snapshot too large');
      if (!response.body?.getReader) {
        const text = await response.text();
        if (new TextEncoder().encode(text).byteLength > Core.MAX_BYTES) throw new Error('Snapshot too large');
        return JSON.parse(text);
      }
      const reader = response.body.getReader();
      const chunks = []; let total = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > Core.MAX_BYTES) { await reader.cancel(); throw new Error('Snapshot too large'); }
        chunks.push(value);
      }
      const bytes = new Uint8Array(total); let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      return JSON.parse(new TextDecoder().decode(bytes));
    }
    async function refresh(force = false) {
      if (refreshPromise) return refreshPromise;
      refreshPromise = (async () => {
        const settings = await preferences();
        const source = settings.demoMode ? 'bundled-demo' : settings.snapshotURL;
        if (!source) return null;
        const { cache } = await api.storage.local.get('cache');
        const previous = cache?.source === source ? cache : null;
        const { refreshedSource } = await api.storage.session.get('refreshedSource');
        if (!force && refreshedSource === source) return previous?.snapshot ?? null;
        // Mark an attempt, including failure, so navigation cannot create a retry storm.
        await api.storage.session.set({ refreshedSource: source });
        try {
          let snapshot, etag = null;
          if (settings.demoMode) {
            const response = await fetchImpl(api.runtime.getURL('demo.json'));
            if (!response.ok) throw new Error('Bundled demo unavailable');
            snapshot = Core.rebaseDemo(await fetchBounded(response), now());
          } else {
            const url = new URL(source);
            if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Use an HTTPS snapshot URL');
            const headers = previous?.etag ? { 'If-None-Match': previous.etag } : {};
            const response = await fetchImpl(source, { headers, credentials: 'omit', redirect: 'error',
              referrerPolicy: 'no-referrer', cache: 'no-cache', signal: AbortSignal.timeout(10000) });
            if (response.status === 304 && previous) {
              // A 304 never changes observed_at or extends the offer's useful lifetime.
              await api.storage.local.set({ refreshStatus: { ok: true, checkedAt: now() } });
              return previous.snapshot;
            }
            if (!response.ok) throw new Error(`Snapshot HTTP ${response.status}`);
            snapshot = Core.validateSnapshot(await fetchBounded(response));
            if (snapshot.demo) throw new Error('Demo data rejected in live mode');
            if (previous && Date.parse(snapshot.source_observed_at) < Date.parse(previous.snapshot.source_observed_at))
              throw new Error('Snapshot rollback rejected');
            etag = response.headers.get('ETag');
          }
          await api.storage.local.set({ cache: { source, snapshot, etag }, refreshStatus: { ok: true, checkedAt: now() } });
          return snapshot;
        } catch (error) {
          await api.storage.local.set({ refreshStatus: { ok: false, checkedAt: now(), error: 'Refresh failed; fresh cached offers remain usable.' } });
          return previous?.snapshot ?? null;
        }
      })().finally(() => { refreshPromise = null; });
      return refreshPromise;
    }
    async function offerFor(host) {
      const snapshot = await refresh();
      if (!snapshot) return null;
      return serialize(async () => {
        const settings = await preferences();
        const { seen = {} } = await api.storage.session.get('seen');
        const result = Core.findOffer(snapshot, host, { ...settings, allowDemo: settings.demoMode, seen, now: now() });
        if (result) await api.storage.session.set({ seen: { ...seen, [result.retailerId]: true } });
        return result;
      });
    }
    async function hide(host, retailerId, mode) {
      return serialize(async () => {
        const settings = await preferences();
        const { cache } = await api.storage.local.get('cache');
        if (!cache || Core.matchRetailer(cache.snapshot, host) !== retailerId) throw new Error('Retailer mismatch');
        if (mode === 'forever') settings.suppressed[retailerId] = true;
        else if (mode === 'snooze') settings.snoozed[retailerId] = new Date(now() + 86400000).toISOString();
        else throw new Error('Unknown suppression mode');
        await api.storage.local.set({ settings });
      });
    }
    async function saveSettings(change) {
      return serialize(async () => {
        const settings = await preferences();
        if (typeof change.snapshotURL === 'string') {
          const value = change.snapshotURL.trim();
          if (value) {
            const url = new URL(value);
            if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Use an HTTPS snapshot URL');
          }
          settings.snapshotURL = value;
        }
        if (typeof change.demoMode === 'boolean') settings.demoMode = change.demoMode;
        if (change.restoreRetailer) {
          delete settings.suppressed[change.restoreRetailer]; delete settings.snoozed[change.restoreRetailer];
        }
        await api.storage.local.set({ settings });
        return settings;
      });
    }
    return { preferences, refresh, offerFor, hide, saveSettings };
  }
  root.createGiftCardController = createController;
  if (typeof module !== 'undefined' && module.exports) module.exports = createController;
})(globalThis);
