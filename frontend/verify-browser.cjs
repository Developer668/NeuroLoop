// Isolated browser verification: real API/storage, no model providers or GPU.
const { chromium, expect } = require("@playwright/test");
const { spawn, spawnSync } = require("node:child_process");
const { randomBytes } = require("node:crypto");
const fs = require("node:fs"),
  path = require("node:path"),
  net = require("node:net");
const root = path.resolve(__dirname, ".."),
  children = [];
const output = path.join(root, "data", "verification", `ui-${Date.now()}`);
fs.mkdirSync(output, { recursive: true });
const freePort = () =>
  new Promise((resolve) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
async function waitFor(url) {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  throw Error(`Server did not start: ${url}`);
}
function start(command, args, env, name, cwd = root) {
  const fd = fs.openSync(path.join(output, `${name}.log`), "w");
  const child = spawn(command, args, {
    cwd,
    env,
    windowsHide: true,
    stdio: ["ignore", fd, fd],
  });
  children.push(child);
  return child;
}
let browser, currentPage;
(async () => {
  const apiPort = await freePort(),
    webPort = await freePort();
  const env = {
    ...process.env,
    NEUROLOOP_LOCAL_BOOTSTRAP_TOKEN: randomBytes(32).toString("hex"),
    NEUROLOOP_INTERNAL_API: `http://127.0.0.1:${apiPort}`,
    NEUROLOOP_OPERATOR_TOKEN: randomBytes(32).toString("hex"),
    NEUROLOOP_WORKER_TOKEN: randomBytes(32).toString("hex"),
    NEUROLOOP_AGENT_TOKEN: randomBytes(32).toString("hex"),
    NEUROLOOP_SIGNING_KEY: randomBytes(32).toString("hex"),
    NEUROLOOP_DATA_DIR: path.join(output, "database"),
    NEUROLOOP_FRONTEND_ORIGIN: `http://127.0.0.1:${webPort}`,
    NEUROLOOP_DATABASE_URL: "",
    NEUROLOOP_ENVIRONMENT: "development",
    NEUROLOOP_WEAVE_ENABLED: "false",
    WANDB_API_KEY: "",
    TYPESAFE_API_KEY: "",
    META_ACCESS_TOKEN: "",
  };
  const executable = process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
    defaultPython = path.join(root, ".venv", executable),
    stagedPython = path.join(root, ".runtimes", "app", executable),
    python = process.env.NEUROLOOP_TEST_PYTHON || (fs.existsSync(defaultPython) ? defaultPython : stagedPython);
  start(
    python,
    [
      "-c",
      `from neuroloop_app.api import create_app; from neuroloop_app.config import Settings; import uvicorn; uvicorn.run(create_app(Settings(_env_file=None)),host='127.0.0.1',port=${apiPort})`,
    ],
    env,
    "api",
  );
  await waitFor(`http://127.0.0.1:${apiPort}/health`);
  start(
    process.execPath,
    [
      path.join(__dirname, "node_modules/next/dist/bin/next"),
      "start",
      "--hostname",
      "127.0.0.1",
      "--port",
      String(webPort),
    ],
    env,
    "web",
    __dirname,
  );
  const base = `http://127.0.0.1:${webPort}`;
  await waitFor(base);
  const brave = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser";
  browser = await chromium.launch({
    ...(fs.existsSync(brave) ? { executablePath: brave } : {}),
    headless: true,
    args: ["--enable-unsafe-swiftshader"],
  });
  const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: "reduce",
    }),
    errors = [];
  currentPage = page;
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base);
  await expect(page.locator("h1")).toBeVisible();
  await page.screenshot({
    path: path.join(output, "landing.png"),
    fullPage: true,
  });
  await page.goto(`${base}/workspace`);
  await expect(page.getByRole("heading", { name: "Open your workspace." })).toBeVisible();
  await expect(page.locator(".auth-observatory canvas")).toBeVisible();
  await page.screenshot({ path: path.join(output, "login-v1.png"), fullPage: true });
  await page.getByText("Connect with an access token", { exact: true }).click();
  await page.getByLabel("Workspace access token").fill("invalid-ui-verification-token");
  await page.getByRole("button", { name: "Connect securely" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  const crossOrigin = await page.request.post(`${base}/api/auth`, {
    headers: { Origin: "https://untrusted.example" },
    data: { mode: "local" },
  });
  expect(crossOrigin.status()).toBe(403);
  await page.getByRole("button", { name: "Open local workspace" }).click();
  await expect(
    page.getByRole("navigation", { name: "Workspace navigation" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "New campaign", exact: true })
    .first()
    .click();
  await page
    .getByLabel("Campaign name", { exact: true })
    .fill("Browser verification campaign");
  await page.getByLabel("Brand name", { exact: true }).fill("TEST ONLY");
  await page
    .getByLabel("Creative brief", { exact: true })
    .fill("CPU browser fixture; no model generation.");
  await page.getByLabel("Format", { exact: true }).selectOption("image");
  await page
    .getByRole("button", { name: "Create campaign", exact: false })
    .click();
  await expect(
    page.getByRole("heading", { name: "Campaign references" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Library", exact: true }).click();
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAI0lEQVR4nGNkYPjPQApgIkk1w6gG4gATkergYFQDMYDkUAIAPjABH26QQDYAAAAASUVORK5CYII=",
    "base64",
  );
  await page.getByLabel("Upload campaign media").setInputFiles([
    { name: "fixture.png", mimeType: "image/png", buffer: png },
    {
      name: "brief.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("TEST ONLY source document."),
    },
  ]);
  await expect(
    page.getByRole("heading", { name: "fixture.png", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "brief.txt", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(output, "library.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Publish Ads", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Send a finished creative to your ad libraries." })).toBeVisible();
  await expect(page.getByText("fixture.png", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Meta Ads", { exact: true })).toBeVisible();
  await expect(page.getByText("Google Ads", { exact: true })).toBeVisible();
  await expect(page.getByText("TikTok Ads", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Setup required" })).toHaveCount(3);
  for (const button of await page.getByRole("button", { name: "Setup required" }).all())
    await expect(button).toBeDisabled();
  await expect(page.getByRole("button", { name: "Upload to 0 destinations" })).toBeDisabled();
  await page.screenshot({
    path: path.join(output, "publish-ads.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Neuro AI", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Neuro AI", exact: true, level: 2 })).toBeVisible();
  await page.screenshot({ path: path.join(output, "neuro-v1.png"), fullPage: true });
  await page
    .getByLabel("Creative direction", { exact: true })
    .fill("Browser fixture: animate a blue square.");
  await page.getByLabel("Brand or project", { exact: true }).fill("TEST ONLY");
  await page.getByLabel("Composer references").setInputFiles([
    { name: "fixture.png", mimeType: "image/png", buffer: png },
    {
      name: "direction.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Test direction"),
    },
  ]);
  await page.getByLabel("Generation model").selectOption("image");
  await expect(
    page.getByRole("button", { name: "Start creative loop" }),
  ).toBeDisabled();
  await page.getByLabel("Generation model").selectOption("video");
  await page.getByLabel("Composer aspect ratio").selectOption("9:16");
  await page.getByRole("button", { name: "Remove direction.txt" }).click();
  await expect(page.getByRole("button", { name: "Remove direction.txt" })).toHaveCount(0);
  await page.getByRole("button", { name: "Start creative loop" }).click();
  await expect(
    page.getByRole("heading", { name: "Command Center", exact: true }),
  ).toBeVisible();
  await expect
    .poll(() => page.getByLabel("Campaign run").inputValue())
    .toMatch(/^[a-f0-9-]{36}$/);
  const runUrl = page.url();
  await page.reload();
  await expect
    .poll(() => page.getByLabel("Campaign run").inputValue())
    .toMatch(/^[a-f0-9-]{36}$/);
  if (page.url() !== runUrl)
    throw Error("Run navigation was not preserved on refresh");
  await page.getByRole("button", { name: "Dark appearance" }).click();
  await expect(page.locator(".app-shell")).toHaveAttribute(
    "data-theme",
    "dark",
  );
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Browser verification campaign/ }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(output, "overview-dark.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(page.locator(".app-shell")).toHaveAttribute(
    "data-theme",
    "dark",
  );
  await page.getByRole("button", { name: "Light appearance" }).click();
  await page.getByRole("link", { name: "Neuro AI", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Creative direction")).toBeVisible();
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2))
    throw Error("Mobile Neuro AI layout overflows");
  await page.screenshot({ path: path.join(output, "neuro-v1-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await expect
    .poll(() =>
      page
        .locator(".sidebar")
        .evaluate((el) => el.getBoundingClientRect().right),
    )
    .toBeLessThanOrEqual(1);
  await expect(
    page.getByRole("heading", { name: "Projects", exact: true }).first(),
  ).toBeVisible();
  if (
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 2,
    )
  )
    throw Error("Mobile layout overflows");
  await page.screenshot({
    path: path.join(output, "mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Publish Ads", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Send a finished creative to your ad libraries." })).toBeVisible();
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2))
    throw Error("Mobile Publish Ads layout overflows");
  await page.screenshot({ path: path.join(output, "publish-ads-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Open local workspace" }),
  ).toBeVisible();
  await page.screenshot({ path: path.join(output, "login-v1-mobile.png"), fullPage: true });
  if (errors.length) throw Error(JSON.stringify(errors));
  console.log(
    `PASS: landing, auth/CSRF, campaign creation, mixed upload, library, honest Publish Ads unconfigured state, composer/run queue, refresh recovery, navigation, theme persistence, mobile layout, logout. Screenshots: ${output}`,
  );
})()
  .catch(async (e) => {
    if (currentPage) {
      await currentPage.screenshot({
        path: path.join(output, "failure.png"),
        fullPage: true,
      });
      fs.writeFileSync(
        path.join(output, "failure.txt"),
        await currentPage.locator("body").innerText(),
      );
    }
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close();
    for (const child of children.reverse())
      if (child.exitCode === null) {
        if (process.platform === "win32")
          spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
            windowsHide: true,
            stdio: "ignore",
          });
        else child.kill("SIGTERM");
      }
  });
