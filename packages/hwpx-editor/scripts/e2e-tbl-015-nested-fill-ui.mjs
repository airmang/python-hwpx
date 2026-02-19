import { spawn } from "node:child_process";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const editorRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const outputRoot = path.resolve(editorRoot, "..", "..", "..", "..", "output", "playwright");
const checkpointDir = path.join(outputRoot, "ux-checkpoints");
const nextDevLockPath = path.join(editorRoot, ".next", "dev", "lock");

const port = Number(process.env.HWPX_E2E_PORT || 3099);
const route = process.env.HWPX_E2E_ROUTE || "/playwright";
const baseUrl = `http://127.0.0.1:${port}`;
const screenshotPath = path.join(checkpointDir, "nested-table-multi-fill-v1.png");

const targetFillColor = "#DCE6F7";
const targetFillRgb = "rgb(220, 230, 247)";

async function waitForServer(url, server, timeoutMs = 120000) {
  const started = Date.now();
  while (Date.now() - started <= timeoutMs) {
    if (server.exitCode != null) {
      throw new Error(`dev server exited early with code ${server.exitCode}`);
    }

    try {
      const res = await fetch(url);
      if (res.status > 0) return;
    } catch {
      // ignore until timeout
    }

    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`dev server timeout after ${timeoutMs}ms (${url})`);
}

async function isServerReachable(url) {
  try {
    const res = await fetch(url);
    return res.status > 0;
  } catch {
    return false;
  }
}

async function stopServer(server) {
  if (!server || server.killed || server.exitCode != null) return;
  const pid = server.pid;
  const canKillGroup = pid && process.platform !== "win32";
  try {
    if (canKillGroup) {
      process.kill(-pid, "SIGTERM");
    } else {
      server.kill("SIGTERM");
    }
  } catch {
    // ignore
  }
  await new Promise((resolve) => setTimeout(resolve, 1200));
  if (server.exitCode == null) {
    try {
      if (canKillGroup) {
        process.kill(-pid, "SIGKILL");
      } else {
        server.kill("SIGKILL");
      }
    } catch {
      // ignore
    }
  }
}

function nestedCellTestId(nestedIndex, row, col) {
  return `nested-table-cell-${nestedIndex}-${row}-${col}`;
}

async function getComputedBg(page, testId) {
  return page.locator(`[data-hwpx-testid='${testId}']`).evaluate((el) => {
    if (!(el instanceof HTMLElement)) return "";
    return window.getComputedStyle(el).backgroundColor;
  });
}

async function run() {
  await mkdir(checkpointDir, { recursive: true });
  await rm(nextDevLockPath, { force: true });

  let server = null;
  let ownsServer = false;
  if (!(await isServerReachable(baseUrl))) {
    server = spawn("pnpm", ["dev", "--port", String(port)], {
      cwd: editorRoot,
      env: { ...process.env, PORT: String(port) },
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    });
    ownsServer = true;
    server.stdout.on("data", (buf) => {
      const text = buf.toString();
      if (text.trim()) process.stdout.write(`[dev] ${text}`);
    });
    server.stderr.on("data", (buf) => {
      const text = buf.toString();
      if (text.trim()) process.stderr.write(`[dev-err] ${text}`);
    });
  } else {
    console.log("[e2e] reusing existing server:", baseUrl);
  }

  let browser;
  try {
    if (server) {
      await waitForServer(baseUrl, server);
    } else if (!(await isServerReachable(baseUrl))) {
      throw new Error(`server is not reachable on ${baseUrl}`);
    }

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1680, height: 1080 } });
    const page = await context.newPage();

    await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForFunction(() => Boolean(window.__HWPX_TEST_BRIDGE), { timeout: 120000 });

    await page.evaluate(async () => {
      const bridge = window.__HWPX_TEST_BRIDGE;
      if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
      await bridge.runFeature("TBL-015");
    });

    const start = page.locator(`[data-hwpx-testid='${nestedCellTestId(0, 0, 0)}']`);
    const end = page.locator(`[data-hwpx-testid='${nestedCellTestId(0, 1, 1)}']`);
    await start.waitFor({ state: "visible", timeout: 120000 });
    await end.waitFor({ state: "visible", timeout: 120000 });

    await start.dispatchEvent("mousedown", { button: 0, bubbles: true });
    await start.dispatchEvent("mouseup", { button: 0, bubbles: true });
    await end.dispatchEvent("mousedown", { button: 0, shiftKey: true, bubbles: true });
    await end.dispatchEvent("mouseup", { button: 0, shiftKey: true, bubbles: true });
    await page.waitForTimeout(120);

    const fillButton = page.locator("[data-hwpx-testid='nested-table-fill-0-blue']");
    await fillButton.waitFor({ state: "visible", timeout: 120000 });
    await fillButton.dispatchEvent("mousedown");
    await page.waitForTimeout(220);

    const expectedTargets = [
      nestedCellTestId(0, 0, 0),
      nestedCellTestId(0, 0, 1),
      nestedCellTestId(0, 1, 0),
      nestedCellTestId(0, 1, 1),
    ];
    for (const testId of expectedTargets) {
      const bg = await getComputedBg(page, testId);
      if (bg !== targetFillRgb) {
        throw new Error(`nested fill mismatch on ${testId}: ${bg} !== ${targetFillRgb}`);
      }
    }

    const input = page.locator("[data-hwpx-testid='nested-table-input-0-0-0']");
    await input.click();
    await input.fill("다중셀 색칠 입력 테스트");
    await input.blur();
    await page.waitForTimeout(160);

    const exportedBytesLen = await page.evaluate(async () => {
      const bridge = window.__HWPX_TEST_BRIDGE;
      if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
      const bytes = await bridge.exportHwpx();
      if (!Array.isArray(bytes) || bytes.length === 0) throw new Error("empty exported bytes");
      await bridge.openHwpx(bytes);
      return bytes.length;
    });
    if (!Number.isFinite(exportedBytesLen) || exportedBytesLen <= 0) {
      throw new Error(`invalid export length: ${exportedBytesLen}`);
    }

    await start.waitFor({ state: "visible", timeout: 120000 });
    const reopenedBg = await getComputedBg(page, nestedCellTestId(0, 0, 0));
    if (reopenedBg !== targetFillRgb) {
      throw new Error(`reopen fill mismatch: ${reopenedBg} !== ${targetFillRgb}`);
    }

    const reopenedText = await page.locator("[data-hwpx-testid='nested-table-input-0-0-0']").inputValue();
    if (reopenedText !== "다중셀 색칠 입력 테스트") {
      throw new Error(`reopen text mismatch: ${reopenedText}`);
    }

    await page.locator("[data-page]").first().screenshot({ path: screenshotPath });
    console.log("[e2e] nested fill color:", targetFillColor);
    console.log("[e2e] screenshot:", screenshotPath);
  } finally {
    if (browser) await browser.close();
    if (ownsServer && server) {
      await stopServer(server);
    }
  }
}

run().catch((error) => {
  console.error("[e2e] fatal:", error);
  process.exit(1);
});
