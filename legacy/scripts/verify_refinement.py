"""Temporary Edge acceptance checks against actual recorded NASA results."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verification/refinement/browser'
real=json.loads((ROOT/'data/verification/refinement/real-media-report.json').read_text(encoding='utf-8'))
expect.set_options(timeout=20000)
report={'checks':{},'errors':[],'rendering':'Temporary Edge with software WebGL; no mocked model data'}
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    context=browser.new_context(viewport={'width':1512,'height':982},accept_downloads=True)
    page=context.new_page();page.on('pageerror',lambda e:report['errors'].append(str(e)))
    page.goto('http://localhost:3010/workspace',wait_until='networkidle')
    expect(page.get_by_role('button',name='Connect to this computer')).to_be_visible()
    assert 'HTTP-only' not in page.locator('body').inner_text()
    with page.expect_response('**/api/auth') as login:
        page.get_by_role('button',name='Connect to this computer').click()
    assert login.value.status==200
    try:expect(page.get_by_role('heading',name='Your next creative decision.')).to_be_visible()
    except Exception:
        page.screenshot(path=str(OUT/'login-failure.png'))
        print(page.locator('body').inner_text()[:800],flush=True)
        raise
    assert page.locator('.connection-state i').count()==0
    assert page.locator('.sidebar-profile .avatar svg').count()==1
    assert page.locator('.nav-item.active').evaluate('(e)=>getComputedStyle(e).boxShadow')=='none'
    page.screenshot(path=str(OUT/'overview-final.png'),full_page=True)
    report['checks']['login_profile_and_navigation']=True
    page.goto('http://localhost:3010/workspace?view=compare',wait_until='networkidle')
    first=real['assets']['video']['name'];second=real['assets']['reference']['name']
    # Choose the newest result matching the current tested profile, identified by its API order.
    data=page.request.get('http://localhost:3010/api/dashboard').json()
    indices=[next(i for i,e in enumerate(data['evaluations']) if e['id']==real['evaluations'][kind]['id']) for kind in ['video','reference']]
    checks=page.locator('.record-select input[type=checkbox]')
    checks.nth(indices[0]).check();checks.nth(indices[1]).check()
    page.get_by_role('button',name='Compare selected').click()
    expect(page.get_by_role('heading',name='Cortical-pattern similarity')).to_be_visible()
    assert page.locator('.matrix tbody tr').count()==2
    assert page.locator('.check-card.incompatible input:disabled').count()>=1
    page.screenshot(path=str(OUT/'compare-final.png'),full_page=True)
    report['checks']['real_comparison_and_incompatible_selection']=True
    identity=real['evaluations']['video']['id']
    # Delay only transport of the real geometry to regress the previous five-second race.
    def delayed_geometry(route):
        response=route.fetch();page.wait_for_timeout(6200);route.fulfill(response=response)
    page.route('**/api/geometry',delayed_geometry)
    page.goto('http://localhost:3010/workspace?view=brain&evaluation='+identity,wait_until='domcontentloaded')
    expect(page.locator('.brain-stage-bottom')).to_contain_text('RESPONSE AT')
    page.unroute('**/api/geometry',delayed_geometry)
    for mode in ['Points','Wireframe','Surface']:
        button=page.get_by_role('button',name=mode,exact=True);button.click();expect(button).to_have_attribute('aria-pressed','true')
    page.get_by_label('Spread hemispheres',exact=True).check()
    slider=page.get_by_label('Neural response time');slider.focus();slider.press('ArrowRight')
    expect(page.locator('.brain-stage-bottom')).to_contain_text('RESPONSE AT 1.0s')
    page.get_by_label('Anatomical region',exact=True).select_option(index=8)
    page.get_by_label('Filter cortical regions').fill('occipital')
    expect(page.get_by_text('TSAM · audiovisual readout',exact=True)).to_be_visible()
    page.screenshot(path=str(OUT/'brain-final.png'),full_page=True)
    report['checks']['delayed_geometry_real_frame_controls_and_tsam']=True
    # Abort one real frame request and verify explicit recovery, not substitute values.
    def failed_request(route):route.abort('failed')
    page.route('**/api/evaluations/*/frame?*',failed_request,times=1)
    slider.focus();slider.press('ArrowRight')
    expect(page.get_by_role('button',name='Retry brain view')).to_be_visible()
    page.get_by_role('button',name='Retry brain view').click()
    expect(page.locator('.brain-stage-bottom')).to_contain_text('RESPONSE AT 2.0s')
    report['checks']['failed_fetch_recovery']=True
    page.goto('http://localhost:3010/workspace?view=research',wait_until='networkidle')
    expect(page.get_by_role('heading',name='Evaluation register')).to_be_visible()
    assert page.locator('.line-chart svg polyline').count()>=3
    before=page.get_by_label('Research evaluation').locator('option').count()
    page.get_by_label('Include archived history').check()
    assert page.get_by_label('Research evaluation').locator('option').count()>before
    page.get_by_label('Include archived history').uncheck()
    page.screenshot(path=str(OUT/'research-final.png'),full_page=True)
    report['checks']['recorded_charts_tables_and_archived_history']=True
    page.goto('http://localhost:3010/workspace?view=connections',wait_until='networkidle')
    page.get_by_role('button',name='Test MCP connection').click()
    expect(page.get_by_text('Connected to NeuroLoop. 15 tools discovered through a real MCP handshake.')).to_be_visible()
    page.get_by_text('Tool parameters',exact=True).first.click()
    expect(page.locator('.tool-schema').first).to_contain_text('properties')
    page.get_by_role('button',name='Check service connections').click()
    expect(page.get_by_text('Local research service returned HTTP 200.',exact=False)).to_be_visible()
    page.screenshot(path=str(OUT/'connections-final.png'),full_page=True)
    report['checks']['mcp_schema_discovery_and_service_checks']=True
    for width in [390,768]:
        page.set_viewport_size({'width':width,'height':844})
        for view in ['','workspace?view=brain&evaluation='+identity,'workspace?view=compare','workspace?view=research','workspace?view=connections']:
            page.goto('http://localhost:3010/'+view,wait_until='networkidle')
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth+2'),(width,view)
        page.goto('http://localhost:3010',wait_until='networkidle')
        page.screenshot(path=str(OUT/f'landing-{width}-final.png'),full_page=True)
    report['checks']['mobile_and_tablet_no_overflow']=True
    page.goto('http://localhost:3010/workspace',wait_until='networkidle')
    page.get_by_role('button',name='Sign out',exact=True).click()
    expect(page.get_by_role('button',name='Connect to this computer')).to_be_visible()
    assert page.request.get('http://localhost:3010/api/dashboard').status==401
    report['checks']['sign_out']=True
    context.close();browser.close()
report['passed']=not report['errors'] and all(report['checks'].values())
(OUT/'interaction-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
