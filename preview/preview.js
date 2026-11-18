let snapshot, mounted = null;
const read = (store, key, fallback) => { try { return JSON.parse(store.getItem(key)) || fallback; } catch (_) { return fallback; } };
const result = document.getElementById('result');
function counts() {
  const seen = read(sessionStorage, 'gcd-preview-seen', {});
  const settings = read(localStorage, 'gcd-preview-settings', { suppressed: {}, snoozed: {} });
  document.getElementById('counts').textContent = `${Object.keys(seen).length} retailer(s) seen this session; ${Object.keys(settings.suppressed).length} permanently hidden.`;
}
function visit(host) {
  if (!snapshot) return;
  mounted?.remove(); mounted = null;
  const seen = read(sessionStorage, 'gcd-preview-seen', {});
  const settings = read(localStorage, 'gcd-preview-settings', { suppressed: {}, snoozed: {} });
  const offer = GiftCardCore.findOffer(snapshot, host, { ...settings, seen, allowDemo: true });
  if (!offer) { result.textContent = `No notification for ${host}: unmatched, no fresh inventory, already seen, or hidden.`; counts(); return; }
  sessionStorage.setItem('gcd-preview-seen', JSON.stringify({ ...seen, [offer.retailerId]: true }));
  result.textContent = `Matched ${offer.name}. A demo notification is visible in the bottom-right corner.`;
  mounted = GiftCardUI.mount(offer, {
    onDismiss: () => { result.textContent = 'Notification dismissed. It will not reappear for this retailer in this simulated session.'; },
    onHide: async mode => {
      const current = read(localStorage, 'gcd-preview-settings', { suppressed: {}, snoozed: {} });
      if (mode === 'forever') current.suppressed[offer.retailerId] = true;
      if (mode === 'snooze') current.snoozed[offer.retailerId] = new Date(Date.now() + 86400000).toISOString();
      localStorage.setItem('gcd-preview-settings', JSON.stringify(current)); counts();
    },
  }); counts();
}
document.getElementById('visit-form').addEventListener('submit', event => { event.preventDefault(); visit(document.getElementById('hostname').value); });
for (const button of document.querySelectorAll('[data-host]')) button.addEventListener('click', () => { document.getElementById('hostname').value = button.dataset.host; visit(button.dataset.host); });
document.getElementById('new-session').addEventListener('click', () => { mounted?.remove(); mounted = null; sessionStorage.removeItem('gcd-preview-seen'); result.textContent = 'New simulated session. Hidden preferences are unchanged.'; counts(); });
document.getElementById('clear-preferences').addEventListener('click', () => { localStorage.removeItem('gcd-preview-settings'); result.textContent = 'Hidden retailers restored. Start a new simulated session to see previously shown retailers again.'; counts(); });
fetch('snapshot.json', { cache: 'no-store' }).then(response => { if (!response.ok) throw new Error('Snapshot unavailable'); return response.json(); }).then(value => {
  snapshot = GiftCardCore.validateSnapshot(value);
  if (!snapshot.demo) throw new Error('Preview accepts only demo data');
  result.textContent = 'Ready. Enter a retailer hostname and select Visit.'; counts();
}).catch(error => { result.textContent = `Could not load preview: ${error.message}`; });
