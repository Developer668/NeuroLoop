from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 page=b.new_page(viewport={'width':390,'height':844})
 page.on('pageerror',lambda e:print('JS ERROR',e))
 page.goto('http://localhost:3010/workspace',wait_until='networkidle')
 page.get_by_role('button',name='Connect to this computer').click()
 page.get_by_role('button',name='Open navigation').wait_for()
 page.get_by_role('button',name='Open navigation').click()
 page.wait_for_timeout(1000)
 print('URL',page.url)
 print(page.locator('body').inner_text()[:7000])
 print('SIDEBAR',page.locator('aside').count())
 page.screenshot(path=str(ROOT/'data/verification/browser/mobile-debug.png'),full_page=True)
 b.close()
