const api = globalThis.browser || globalThis.chrome;
const status = document.getElementById('status');
async function load() {
  const settings = await api.runtime.sendMessage({ type: 'settings' });
  document.getElementById('feed-status').textContent = settings.demoMode ? 'Synthetic demo mode is enabled.' : (settings.snapshotURL ? 'A snapshot source is configured.' : 'No live provider feed is configured.');
  document.getElementById('snapshot-url').value = settings.snapshotURL;
  document.getElementById('demo-mode').checked = settings.demoMode;
  const list = document.getElementById('hidden-list'); list.replaceChildren();
  const ids = new Set([...Object.keys(settings.suppressed), ...Object.keys(settings.snoozed)]);
  if (!ids.size) list.textContent = 'None';
  for (const id of ids) {
    const row = document.createElement('div'); row.className = 'hidden-row';
    const label = document.createElement('span'); label.textContent = id;
    const button = document.createElement('button'); button.textContent = 'Restore'; button.type = 'button';
    button.addEventListener('click', async () => { await api.runtime.sendMessage({ type: 'save-settings', change: { restoreRetailer: id } }); await load(); });
    row.append(label, button); list.append(row);
  }
}
document.getElementById('settings-form').addEventListener('submit', async event => {
  event.preventDefault();
  const response = await api.runtime.sendMessage({ type: 'save-settings', change: {
    snapshotURL: document.getElementById('snapshot-url').value,
    demoMode: document.getElementById('demo-mode').checked,
  } });
  status.textContent = response.ok ? 'Saved. Reload a retailer page to try it.' : 'Could not save. Use an HTTPS URL.';
  if (response.ok) await load();
});
document.getElementById('refresh').addEventListener('click', async () => {
  status.textContent = 'Refreshing...';
  const response = await api.runtime.sendMessage({ type: 'refresh' });
  status.textContent = response.refreshStatus?.ok ? 'Dataset refreshed.' : (response.refreshStatus?.error || 'Set a snapshot URL or enable demo mode first.');
});
load().catch(() => { status.textContent = 'Extension unavailable.'; });
