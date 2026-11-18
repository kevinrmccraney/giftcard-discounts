"""Optional Chromium UI smoke test; no live retailer/provider traffic.

Requires playwright + Chromium. Unit tests do not require either.
Start `python3 -m giftcard_tool preview` in another terminal first.
"""
from pathlib import Path
import argparse
import json
import shutil
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8765/')
parser.add_argument('--screenshot', type=Path)
parser.add_argument('--offline', action='store_true', help='Load generated local assets with an in-memory fetch stub; no browser network access')
args = parser.parse_args()

with sync_playwright() as p:
    kwargs = {'headless': True}
    if shutil.which('chromium'):
        kwargs['executable_path'] = shutil.which('chromium')
    browser = p.chromium.launch(**kwargs)
    page = browser.new_page(viewport={'width': 1200, 'height': 850})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    if args.offline:
        # Same HTML/CSS/JS as the served preview; only the file delivery is mocked.
        public = ROOT / 'build/preview-public'
        html = (public / 'index.html').read_text()
        css = (public / 'preview.css').read_text()
        html = html.replace('<link rel="stylesheet" href="preview.css">', '<style>' + css + '</style>')
        snapshot = json.loads((public / 'snapshot.json').read_text())
        stub = '<script>window.fetch=async()=>new Response(' + json.dumps(json.dumps(snapshot)) + ');</script>'
        html = html.replace('<script src="core.js"></script>', stub + '<script>' + (public / 'core.js').read_text() + '</script>')
        for name in ('ui.js', 'preview.js'):
            html = html.replace('<script src="' + name + '"></script>', '<script>' + (public / name).read_text() + '</script>')
        # Opaque about:blank storage is unavailable; use an explicit in-memory Storage test double.
        storage_stub = '''<script>for(const key of ['localStorage','sessionStorage']) {
          const data=new Map(); Object.defineProperty(window,key,{value:{
          getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k)}});}
          </script>'''
        page.set_content(storage_stub + html)
    else:
        page.goto(args.url)
    expect(page.locator('#result')).to_contain_text('Ready.')
    page.get_by_role('button', name='Visit', exact=True).click()
    expect(page.locator('#giftcard-discounts-ui')).to_have_count(1)
    expect(page.get_by_text('TEST DATA - NOT A LIVE OFFER')).to_be_visible()
    page.get_by_role('button', name='Gift cards up to').click()
    expect(page.get_by_text('Weighted average', exact=True)).to_be_visible()
    expect(page.get_by_text('11.2%', exact=True)).to_be_visible()
    expect(page.get_by_role('link', name='View gift cards')).to_have_count(0)
    if args.screenshot:
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(args.screenshot), full_page=True)
    page.get_by_role('button', name='Dismiss for this session').click()
    page.get_by_role('button', name='Subdomain', exact=True).click()
    expect(page.locator('#giftcard-discounts-ui')).to_have_count(0)
    page.get_by_role('button', name='New simulated session', exact=True).click()
    page.get_by_role('button', name='Visit', exact=True).click()
    expect(page.locator('#giftcard-discounts-ui')).to_have_count(1)
    page.get_by_role('button', name='Gift cards up to').click()
    page.get_by_role('button', name="Don't show this retailer again").click()
    expect(page.locator('#giftcard-discounts-ui')).to_have_count(0)
    page.get_by_role('button', name='New simulated session', exact=True).click()
    page.get_by_role('button', name='Visit', exact=True).click()
    expect(page.locator('#giftcard-discounts-ui')).to_have_count(0)
    page.get_by_role('button', name='No inventory', exact=True).click()
    expect(page.locator('#giftcard-discounts-ui')).to_have_count(0)
    page.get_by_role('button', name='Unrelated domain', exact=True).click()
    expect(page.locator('#giftcard-discounts-ui')).to_have_count(0)
    page.get_by_role('button', name='Starbucks', exact=True).click()
    expect(page.locator('#giftcard-discounts-ui')).to_have_count(1)
    page.get_by_role('button', name='Gift cards up to').click()
    expect(page.get_by_text('Provider average', exact=True)).to_be_visible()
    page.emulate_media(color_scheme='dark', reduced_motion='reduce')
    expect(page.locator('#giftcard-discounts-ui')).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    box = page.locator('#giftcard-discounts-ui').bounding_box()
    assert box and box['x'] >= 0 and box['x'] + box['width'] <= 390
    page.get_by_role('button', name='Gift cards up to').focus()
    page.keyboard.press('Escape')
    expect(page.locator('#giftcard-discounts-ui')).to_have_count(0)
    # Inspect the live presentation without navigating to the external purchase page.
    page.evaluate('''() => {
      const now = Date.now();
      GiftCardUI.mount({name:"Example", retailerId:"example", providerName:"GCX", demo:false,
        offer:{max_discount_pct:1.01,average_discount_pct:null,card_count:null,
          observed_at:new Date(now).toISOString(),expires_at:new Date(now+60000).toISOString(),
          offer_url:"https://gcx.app/buy-domino-s-gift-cards"}});
    }''')
    buy = page.get_by_role('link', name='Buy gift cards on GCX', exact=True)
    expect(buy).to_be_visible()
    expect(buy).to_have_attribute('href', 'https://gcx.app/buy-domino-s-gift-cards')
    expect(buy).to_have_attribute('target', '_blank')
    expect(buy).to_have_attribute('rel', 'noopener noreferrer')
    expect(page.get_by_role('button', name='Gift cards up to')).to_contain_text('before fees')
    assert not errors, errors
    print(json.dumps({'browser': 'Chromium', 'ui_smoke': 'passed', 'page_errors': errors,
                      'checks': ['matching', 'demo-label', 'weighted-average', 'no-demo-purchase-link',
                                 'dismissal', 'session-reset', 'permanent-suppression', 'no-inventory',
                                 'unrelated-domain', 'provider-average', 'dark-mode', 'narrow-layout', 'escape',
                                 'visible-direct-provider-link', 'before-fees-label']}))
    browser.close()
