/* Safari 16.4+; session state survives background-worker suspension. */
importScripts('core.js', 'controller.js');
const api = globalThis.browser || globalThis.chrome;
const controller = createGiftCardController(api, fetch, GiftCardCore);
const extensionBase = api.runtime.getURL('');
api.runtime.onMessage.addListener((message, sender) => {
  const isExtensionPage = typeof sender.url === 'string' && sender.url.startsWith(extensionBase);
  const isTopPage = sender.tab && sender.frameId === 0 && /^https:\/\//.test(sender.url || '');
  if (message?.type === 'offer' && isTopPage) return controller.offerFor(sender.url).catch(() => null);
  if (message?.type === 'hide' && isTopPage)
    return controller.hide(sender.url, message.retailerId, message.mode).then(() => ({ ok: true })).catch(() => ({ ok: false }));
  if (!isExtensionPage) return undefined;
  if (message?.type === 'settings') return controller.preferences();
  if (message?.type === 'save-settings') return controller.saveSettings(message.change).then(() => ({ ok: true })).catch(() => ({ ok: false }));
  if (message?.type === 'refresh') return controller.refresh(true).then(async () => api.storage.local.get('refreshStatus'));
  return undefined;
});
// Lazy first-use refresh does not rely on startup events or on worker lifetime.
