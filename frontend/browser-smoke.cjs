const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
(async () => {
  const browser = await chromium.launch({headless:true,args:['--disable-gpu','--disable-webgl']});
  const report = {executed_at:new Date().toISOString(),gpu_disabled:true,external_model_calls:false,checks:[],page_errors:[]};
  const out = path.resolve(__dirname,'../data/verification');fs.mkdirSync(out,{recursive:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',e=>report.page_errors.push(e.message));
    await page.goto('http://localhost:3010/',{waitUntil:'networkidle'});
    if(!page.url().endsWith('/workspace'))throw Error('Root must redirect to the new workspace');
    report.checks.push('Root redirects to new workspace');
    await page.getByRole('button',{name:'Open local workspace'}).click();
    await page.getByRole('button',{name:'Settings',exact:true}).waitFor({state:'visible',timeout:15000});
    report.checks.push('Real local bootstrap authentication and HttpOnly session');
    const cookies = await page.context().cookies();
    if(!cookies.some(c=>c.httpOnly))throw Error('Missing HttpOnly authentication cookie');
    for(const name of ['Settings','Experiments','Learning','Lineage','Brain Lab','Command Center']){
      await page.getByRole('button',{name,exact:true}).click();
      await page.waitForTimeout(200);
      report.checks.push('Navigation: '+name);
    }
    await page.screenshot({path:path.join(out,'workspace.png'),fullPage:true});
    const capabilities = await page.evaluate(async()=>{const r=await fetch('/api/v2/capabilities');return {status:r.status,body:await r.json()};});
    if(capabilities.status!==200)throw Error('Authenticated capabilities API failed');
    report.capabilities=capabilities.body;
    const campaignResponse=await page.evaluate(async()=>{const r=await fetch('/api/v2/campaigns');return {status:r.status,body:await r.json()};});
    if(campaignResponse.status!==200)throw Error('Campaign API failed');
    report.campaign_count=campaignResponse.body.length;
    report.checks.push('Live authenticated campaign and capability APIs');
    const logout=await page.evaluate(async()=>{const r=await fetch('/api/auth',{method:'DELETE'});return r.status;});
    report.logout_status=logout;
    if(report.page_errors.length)throw Error('Browser JavaScript errors');
    report.status='PASSED';
    fs.writeFileSync(path.join(out,'browser-smoke.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } catch(e) {
    report.status='FAILED';report.error=e.message;fs.writeFileSync(path.join(out,'browser-smoke.json'),JSON.stringify(report,null,2));throw e;
  } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1);});
