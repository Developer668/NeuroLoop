"""Exercise the actual production Next.js server; no network mocking."""
import json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verification/redesign-browser';OUT.mkdir(parents=True,exist_ok=True)
report={'scope':'Live browser navigation, local authentication, real backend requests; no mocked API','errors':[],'pages':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    context=browser.new_context(viewport={'width':1512,'height':982},device_scale_factor=1)
    page=context.new_page();page.on('pageerror',lambda e:report['errors'].append(str(e)))
    page.goto('http://localhost:3010',wait_until='networkidle')
    page.locator('h1').wait_for(timeout=10000)
    assert 'Great creative.' in page.locator('h1').inner_text()
    page.screenshot(path=str(OUT/'homepage.png'),full_page=True)
    page.screenshot(path=str(OUT/'hero.png'))
    page.goto('http://localhost:3010/workspace',wait_until='networkidle')
    page.get_by_role('button',name='Connect to this computer').click()
    page.get_by_role('heading',name='Your next creative decision.').wait_for(timeout=10000)
    for view in ['overview','projects','library','compare','runs','brain','research','connections','settings']:
        page.goto('http://localhost:3010/workspace?view='+view,wait_until='networkidle')
        page.wait_for_timeout(700)
        text=page.locator('main').inner_text()
        assert 'Application error' not in text and text.strip(),(view,text)
        report['pages'].append({'view':view,'rendered':True})
        if view in ['overview','brain','connections','settings']:page.screenshot(path=str(OUT/(view+'.png')),full_page=True)
    page.goto('http://localhost:3010/workspace?view=projects',wait_until='networkidle')
    page.get_by_role('button',name='New project',exact=True).click()
    page.get_by_label('Project name',exact=True).fill('Browser verification — empty brief')
    page.get_by_label('Creative brief',exact=True).fill('Integration test record. Not a production campaign or measured user study.')
    page.get_by_role('button',name='Create project',exact=True).click()
    page.get_by_role('heading',name='Browser verification — empty brief').first.wait_for(timeout=10000)
    report['created_project_through_ui']=True
    page.set_viewport_size({'width':390,'height':844})
    page.goto('http://localhost:3010/workspace?view=overview',wait_until='networkidle')
    page.get_by_role('button',name='Open navigation').click()
    page.get_by_role('link',name='Library',exact=True).click()
    page.get_by_role('heading',name='Your creative library').wait_for()
    page.wait_for_function("document.querySelector('.sidebar').getBoundingClientRect().right <= 1")
    page.screenshot(path=str(OUT/'mobile-library.png'),full_page=True)
    report['mobile_navigation']=True
    report['horizontal_overflow']=page.evaluate('document.documentElement.scrollWidth > window.innerWidth + 2')
    context.close();browser.close()
report['passed']=not report['errors'] and not report['horizontal_overflow']
(OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
if not report['passed']:sys.exit(1)
