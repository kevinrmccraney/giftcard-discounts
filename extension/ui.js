(function (root) {
  'use strict';
  const styles = `
    :host { all:initial; position:fixed; right:20px; bottom:20px; z-index:2147483647;
      font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color-scheme:light dark; }
    * { box-sizing:border-box; }
    .card { width:min(320px,calc(100vw - 32px)); background:Canvas; color:CanvasText;
      border:1px solid color-mix(in srgb,CanvasText 20%,transparent); border-radius:12px;
      box-shadow:0 4px 20px #0002; overflow:hidden; }
    .row { display:flex; align-items:center; }
    button,a { font:inherit; cursor:pointer; }
    button { border:0; background:transparent; color:inherit; padding:10px 12px; text-align:left; }
    button:hover { background:color-mix(in srgb,CanvasText 7%,transparent); }
    button:focus-visible,a:focus-visible { outline:2px solid Highlight; outline-offset:-3px; }
    .trigger { flex:1; font-weight:600; }
    .close { font-size:20px; padding:6px 12px; }
    .offer-link { color:inherit; padding:8px; white-space:nowrap; }
    .details { padding:0 14px 14px; }
    .details[hidden] { display:none; }
    .name { font-weight:600; margin:2px 0 8px; }
    .metric { display:flex; justify-content:space-between; gap:18px; margin:4px 0; }
    .note { font-size:11px; opacity:.75; margin:8px 0; }
    .demo { font-size:11px; font-weight:700; padding:7px 12px 0; }
    .visit { display:block; text-align:center; border:1px solid currentColor; border-radius:6px;
      padding:7px 10px; color:inherit; text-decoration:none; margin:10px 0 6px; }
    .actions { display:flex; flex-direction:column; }
    .actions button { padding:5px 0; font-size:11px; }
    @media (prefers-reduced-motion:reduce) { * { transition:none!important; } }
  `;
  function mount(result, callbacks = {}) {
    if (document.getElementById('giftcard-discounts-ui')) return null;
    const host = document.createElement('div'); host.id = 'giftcard-discounts-ui';
    const shadow = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style'); style.textContent = styles; shadow.append(style);
    const card = document.createElement('section'); card.className = 'card';
    card.setAttribute('aria-label', 'Gift card discount'); shadow.append(card);
    const node = (tag, text, cls, parent = card) => {
      const element = document.createElement(tag); if (text !== null) element.textContent = text;
      if (cls) element.className = cls; parent.append(element); return element;
    };
    const remove = () => { host.remove(); if (timer) clearTimeout(timer); callbacks.onDismiss?.(); };
    let timer = null;
    if (result.demo) node('div', 'TEST DATA - NOT A LIVE OFFER', 'demo');
    const row = node('div', null, 'row');
    const trigger = node('button', `Gift cards up to ${Number(result.offer.max_discount_pct.toFixed(2))}% off before fees`, 'trigger', row);
    trigger.type = 'button'; trigger.title = 'Advertised gift-card discount before provider fees'; trigger.setAttribute('aria-expanded', 'false'); trigger.setAttribute('aria-controls', 'giftcard-details');
    if (!result.demo) {
      const buy = node('a', result.providerName, 'offer-link', row);
      buy.setAttribute('aria-label', `Buy gift cards on ${result.providerName}`);
      buy.href = result.offer.offer_url; buy.target = '_blank'; buy.rel = 'noopener noreferrer';
    }
    const close = node('button', '\u00d7', 'close', row); close.type = 'button'; close.setAttribute('aria-label', 'Dismiss for this session');
    close.addEventListener('click', remove);
    const details = node('div', null, 'details'); details.id = 'giftcard-details'; details.hidden = true;
    node('div', `${result.name} - ${result.providerName}`, 'name', details);
    const metric = (label, value) => {
      const line = node('div', null, 'metric', details); node('span', label, '', line); node('strong', value, '', line);
    };
    metric('Up to', `${Number(result.offer.max_discount_pct.toFixed(2))}%`);
    if (result.offer.average_discount_pct !== null)
      metric(result.offer.average_method === 'balance_weighted' ? 'Weighted average' : 'Provider average', `${Number(result.offer.average_discount_pct.toFixed(2))}%`);
    if (result.offer.card_count !== null) metric('Cards observed', String(result.offer.card_count));
    node('div', '* Before provider fees. Inventory may have changed.', 'note', details);
    node('div', `Observed ${new Date(result.offer.observed_at).toLocaleString()}`, 'note', details);
    if (result.demo) node('div', 'Demo only. Purchasing is disabled.', 'note', details);
    else {
      const visit = node('a', 'View gift cards', 'visit', details);
      visit.href = result.offer.offer_url; visit.target = '_blank'; visit.rel = 'noopener noreferrer';
    }
    const actions = node('div', null, 'actions', details);
    for (const [label, mode] of [['Snooze this retailer for 24 hours', 'snooze'], ["Don't show this retailer again", 'forever']]) {
      const button = node('button', label, '', actions); button.type = 'button';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try { await callbacks.onHide?.(mode); remove(); }
        catch (_) { button.disabled = false; button.textContent = 'Could not save. Try again.'; }
      });
    }
    trigger.addEventListener('click', () => { details.hidden = !details.hidden; trigger.setAttribute('aria-expanded', String(!details.hidden)); });
    shadow.addEventListener('keydown', event => { if (event.key === 'Escape') { event.stopPropagation(); remove(); } });
    document.documentElement.append(host);
    // Do not focus or announce an unsolicited alert; the pill never steals keyboard focus.
    timer = setTimeout(remove, Math.max(1, Math.min(2147483647, Date.parse(result.offer.expires_at) - Date.now())));
    return { host, remove };
  }
  root.GiftCardUI = { mount };
})(globalThis);
