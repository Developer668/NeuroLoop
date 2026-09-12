"""Real interaction checks in the user-authorized, temporary Edge test session.

Uses software WebGL to avoid adding GPU load. No API responses are mocked.
"""
import io
import json
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

expect.set_options(timeout=15000)
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verification/redesign-browser'
OUT.mkdir(exist_ok=True)
actual=json.loads((ROOT/'data/verification/redesign/report.json').read_text())
report={'browser':'temporary Edge / software WebGL','errors':[],'checks':{}}
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    context=browser.new_context(viewport={'width':1512,'height':982},device_scale_factor=1,accept_downloads=True)
    page=context.new_page()
    page.on('pageerror',lambda error:report['errors'].append(str(error)))
    page.goto('http://localhost:3010',wait_until='networkidle')
    expect(page.get_by_role('heading',level=1)).to_contain_text('Great creative.')
    page.screenshot(path=str(OUT/'hero-final.png'))
    page.locator('.landing-footer').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'footer-final.png'))
    page.goto('http://localhost:3010/workspace',wait_until='networkidle')
    page.get_by_role('button',name='Connect to this computer').click()
    expect(page.get_by_role('heading',name='Your next creative decision.')).to_be_visible()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT/'overview-final.png'))
    page.goto('http://localhost:3010/workspace?view=brain&evaluation='+actual['evaluation_id'],wait_until='networkidle')
    expect(page.get_by_text('TSAM · audiovisual readout',exact=True)).to_be_visible()
    expect(page.locator('.brain-stage-bottom')).to_contain_text('RESPONSE AT')
    for mode in ['Points','Wireframe','Surface']:
        button=page.get_by_role('button',name=mode,exact=True);button.click()
        expect(button).to_have_attribute('aria-pressed','true')
    page.get_by_role('button',name='Separate',exact=True).click()
    expect(page.get_by_role('button',name='Separate',exact=True)).to_have_attribute('aria-pressed','true')
    slider=page.get_by_label('Neural response time');slider.focus();slider.press('ArrowRight')
    expect(page.locator('.brain-stage-bottom')).not_to_contain_text('RESPONSE AT 0.0s')
    page.get_by_label('Anatomical region',exact=True).select_option(index=8)
    page.get_by_label('Filter cortical regions').fill('occipital')
    assert page.locator('.region-table tbody tr').count()>0
    page.screenshot(path=str(OUT/'brain-final.png'),full_page=True)
    report['checks']['brain_modes_timeline_regions_and_tsam']=True
    page.goto('http://localhost:3010/workspace?view=connections',wait_until='networkidle')
    page.get_by_role('button',name='Test MCP connection').click()
    expect(page.get_by_text('Connected to NeuroLoop. 12 tools discovered through a real MCP handshake.')).to_be_visible(timeout=20000)
    with page.expect_download() as download:
        page.get_by_role('link',name='Download client config').click()
    config=json.loads(Path(download.value.path()).read_text())
    assert config['mcpServers']['neuroloop']['headers']['Authorization'].startswith('Bearer ')
    report['checks']['mcp_handshake_and_configuration_download']=True
    page.screenshot(path=str(OUT/'connections-final.png'),full_page=True)
    page.goto('http://localhost:3010/workspace?view=settings',wait_until='networkidle')
    prefs=page.request.get('http://localhost:3010/api/preferences').json()
    page.get_by_label('Display name',exact=True).fill(prefs['display_name'])
    page.get_by_label('Workspace name',exact=True).fill(prefs['workspace_name'])
    page.get_by_role('button',name='Save preferences').click()
    expect(page.get_by_text('Preferences saved',exact=True)).to_be_visible()
    report['checks']['preferences_roundtrip']=True
    page.screenshot(path=str(OUT/'settings-final.png'),full_page=True)
    exported=page.request.get('http://localhost:3010/api/runs/'+actual['run_id']+'/export')
    assert exported.status==200
    with zipfile.ZipFile(io.BytesIO(exported.body())) as z:
        names=z.namelist()
        assert any(name.endswith('/prediction.npy') for name in names)
        assert 'evidence.json' in names and 'geometry-provenance.json' in names
    report['checks']['export_includes_real_arrays_and_metadata']=True
    for width in [390,768]:
        page.set_viewport_size({'width':width,'height':844})
        page.goto('http://localhost:3010',wait_until='networkidle')
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 2')
        page.screenshot(path=str(OUT/f'landing-{width}.png'),full_page=True)
    report['checks']['mobile_and_tablet_landing']=True
    page.goto('http://localhost:3010/workspace?view=library',wait_until='networkidle')
    page.get_by_label('Search creative library').fill('technical-av-check')
    assert page.locator('.asset-card').count()>=1
    page.get_by_role('button',name='Sign out',exact=True).click()
    expect(page.get_by_role('button',name='Connect to this computer')).to_be_visible()
    assert page.request.get('http://localhost:3010/api/dashboard').status==401
    report['checks']['library_search_and_sign_out']=True
    context.close();browser.close()
report['passed']=not report['errors'] and all(report['checks'].values())
(OUT/'interaction-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
assert report['passed']
