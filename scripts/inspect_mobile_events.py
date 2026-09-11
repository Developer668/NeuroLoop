from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 page=b.new_page(viewport={'width':390,'height':844})
 page.on('console',lambda m:print('LOG',m.text) if m.text.startswith('EVENT') else None)
 page.add_init_script("for(const t of ['pointerdown','pointerup','click'])document.addEventListener(t,e=>console.log('EVENT',t,e.target.outerHTML?.slice(0,300)),true)")
 page.goto('http://localhost:3010/workspace',wait_until='networkidle')
 page.get_by_role('button',name='Connect to this computer').click()
 page.get_by_role('button',name='Open navigation').wait_for()
 page.wait_for_timeout(400)
 print('BEFORE',page.url,page.get_by_role('button',name='Open navigation').bounding_box())
 page.screenshot(path=str(ROOT/'data/verification/browser/mobile-before.png'),full_page=True)
 page.get_by_role('button',name='Open navigation').click()
 page.wait_for_timeout(1000)
 print('AFTER',page.url)
 b.close()
