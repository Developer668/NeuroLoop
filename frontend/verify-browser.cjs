const { chromium } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'data', 'verification', 'browser');
const BASE_URL = process.env.NEUROLOOP_WEB_URL || 'http://localhost:3010';
fs.mkdirSync(OUT, { recursive: true });

function browserExecutable() {
  const candidates = [
    chromium.executablePath(),
    '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ];
  return candidates.find((candidate) => candidate && fs.existsSync(candidate));
}

(async () => {
  const report = {
    scope: 'Live production browser navigation against local API; no mocked requests or model inference.',
    page_errors: [],
    failed_requests: [],
    pages: [],
  };
  const executablePath = browserExecutable();
  if (!executablePath) throw new Error('No Chromium-family browser is available for Playwright verification');
  report.browser = executablePath;

  const browser = await chromium.launch({
    executablePath,
    headless: true,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const context = await browser.newContext({ viewport: { width: 1512, height: 982 } });
    const page = await context.newPage();
    page.setDefaultTimeout(10000);
    page.setDefaultNavigationTimeout(15000);
    page.on('pageerror', (error) => report.page_errors.push(error.message));
    page.on('response', (response) => {
      if (response.status() >= 400 && !response.url().endsWith('/api/dashboard')) {
        report.failed_requests.push({ url: response.url(), status: response.status() });
      }
    });

    console.log('browser: landing');
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
    await page.locator('h1').first().waitFor();
    await page.screenshot({ path: path.join(OUT, 'landing.png'), fullPage: true });

    console.log('browser: workspace auth');
    const auth = await context.request.post(`${BASE_URL}/api/auth`, {
      data: { mode: 'local' },
      headers: { Origin: BASE_URL },
    });
    if (!auth.ok()) throw new Error(`Browser auth failed: ${auth.status()} ${await auth.text()}`);
    await page.goto(`${BASE_URL}/workspace`, { waitUntil: 'domcontentloaded' });
    await page.locator('main.main').waitFor({ timeout: 15000 });

    for (const view of ['overview', 'projects', 'library', 'compare', 'runs', 'brain', 'research', 'connections', 'settings']) {
      console.log(`browser: ${view}`);
      await page.goto(`${BASE_URL}/workspace?view=${view}`, { waitUntil: 'domcontentloaded' });
      await page.locator('main.main').waitFor();
      await page.waitForTimeout(view === 'brain' ? 700 : 150);
      const text = (await page.locator('main.main').innerText()).trim();
      if (!text || text.includes('Application error')) throw new Error(`Invalid ${view} view`);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
      report.pages.push({ view, rendered: true, horizontal_overflow: overflow });
    }

    console.log('browser: mobile navigation');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${BASE_URL}/workspace?view=overview`, { waitUntil: 'domcontentloaded' });
    const navButton = page.getByRole('button', { name: 'Open navigation' });
    if (await navButton.count()) {
      await navButton.click();
      await page.getByRole('link', { name: 'Library', exact: true }).click();
      await page.locator('main.main').waitFor();
    }
    report.mobile_horizontal_overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 2,
    );
    await page.screenshot({ path: path.join(OUT, 'mobile.png'), fullPage: true });
    await context.close();
  } finally {
    await browser.close();
  }

  report.passed =
    report.page_errors.length === 0 &&
    report.failed_requests.length === 0 &&
    !report.mobile_horizontal_overflow &&
    report.pages.every((entry) => !entry.horizontal_overflow);
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  if (!report.passed) process.exitCode = 1;
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
