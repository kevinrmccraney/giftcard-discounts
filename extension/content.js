(function () {
  'use strict';
  if (window.top !== window) return;
  const api = globalThis.browser || globalThis.chrome;
  let requested = false;
  async function show() {
    if (requested || document.visibilityState !== 'visible') return;
    requested = true;
    try {
      const result = await api.runtime.sendMessage({ type: 'offer' });
      if (result) GiftCardUI.mount(result, { onHide: async mode => {
        const response = await api.runtime.sendMessage({ type: 'hide', retailerId: result.retailerId, mode });
        if (!response?.ok) throw new Error('Could not save preference');
      } });
    } catch (_) { /* Fail silently on the retailer page; status belongs in extension settings. */ }
  }
  document.addEventListener('visibilitychange', show); show();
})();
