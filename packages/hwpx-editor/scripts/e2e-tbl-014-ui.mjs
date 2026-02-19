import { spawn } from "node:child_process";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const editorRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const outputDir = path.resolve(editorRoot, "..", "..", "..", "..", "output", "playwright");
const nextDevLockPath = path.join(editorRoot, ".next", "dev", "lock");

const port = Number(process.env.HWPX_E2E_PORT || 3110);
const baseUrl = `http://127.0.0.1:${port}`;
const screenshotPath = path.join(outputDir, "TBL-014-ui.png");

async function waitForServer(url, server, timeoutMs = 120000) {
  const started = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (server.exitCode != null) {
      throw new Error(`dev server exited early with code ${server.exitCode}`);
    }

    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404) return;
    } catch {
      // ignore until timeout
    }

    if (Date.now() - started > timeoutMs) {
      throw new Error(`dev server timeout after ${timeoutMs}ms (${url})`);
    }
    await new Promise((r) => setTimeout(r, 1000));
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

function cellSelector(ref, row, col) {
  return `td[data-hwpx-cell='1'][data-section-index='${ref.sectionIndex}'][data-paragraph-index='${ref.paragraphIndex}'][data-table-index='${ref.tableIndex}'][data-row='${row}'][data-col='${col}']`;
}

async function assertRangeSelected(page, expected) {
  const snap = await page.evaluate(() => window.__HWPX_TEST_BRIDGE?.getStateSnapshot?.());
  const sel = snap?.selection;
  if (!sel || typeof sel !== "object") return false;
  const s = sel;
  return (
    s.type === "cell" &&
    s.sectionIndex === expected.sectionIndex &&
    s.paragraphIndex === expected.paragraphIndex &&
    s.tableIndex === expected.tableIndex &&
    s.row === expected.row &&
    s.col === expected.col &&
    s.endRow === expected.endRow &&
    s.endCol === expected.endCol
  );
}

async function run() {
  await mkdir(outputDir, { recursive: true });
  await rm(nextDevLockPath, { force: true });

  const server = spawn("pnpm", ["dev", "--port", String(port)], {
    cwd: editorRoot,
    env: { ...process.env, PORT: String(port) },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });

  server.stdout.on("data", (buf) => {
    const text = buf.toString();
    if (text.trim()) process.stdout.write(`[dev] ${text}`);
  });
  server.stderr.on("data", (buf) => {
    const text = buf.toString();
    if (text.trim()) process.stderr.write(`[dev-err] ${text}`);
  });

  let browser;

  try {
    await waitForServer(baseUrl, server);

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1680, height: 1080 } });
    const page = await context.newPage();

    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForFunction(() => Boolean(window.__HWPX_TEST_BRIDGE), { timeout: 120000 });

    // Create a 3x3 table.
    await page.evaluate(async () => {
      const bridge = window.__HWPX_TEST_BRIDGE;
      if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
      await bridge.runFeature("TBL-001");
    });

    const ref = await page.evaluate(() => window.__HWPX_TEST_BRIDGE?.findFirstTableRef?.());
    if (!ref) throw new Error("table not found after creation");

    // Seed some text so font changes are observable in the view model.
    await page.evaluate((tableRef) => {
      const bridge = window.__HWPX_TEST_BRIDGE;
      if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
      for (let r = 0; r <= 1; r += 1) {
        for (let c = 0; c <= 1; c += 1) {
          bridge.updateCellText({
            sectionIndex: tableRef.sectionIndex,
            paragraphIndex: tableRef.paragraphIndex,
            tableIndex: tableRef.tableIndex,
            row: r,
            col: c,
            text: `R${r}C${c}`,
          });
        }
      }
    }, ref);

    const start = page.locator(cellSelector(ref, 0, 0));
    const end = page.locator(cellSelector(ref, 1, 1));
    await start.waitFor({ state: "visible", timeout: 120000 });
    await end.waitFor({ state: "visible", timeout: 120000 });

    const expectedRange = { ...ref, row: 0, col: 0, endRow: 1, endCol: 1 };

    // Prefer Shift+click range selection.
    await start.click();
    await end.click({ modifiers: ["Shift"] });

    let selected = await assertRangeSelected(page, expectedRange);
    if (!selected) {
      // Fallback: drag-selection (mousedown on start → move to end → mouseup).
      const sBox = await start.boundingBox();
      const eBox = await end.boundingBox();
      if (!sBox || !eBox) throw new Error("unable to compute cell bounding boxes for drag selection");

      await page.mouse.move(sBox.x + sBox.width / 2, sBox.y + sBox.height / 2);
      await page.mouse.down();
      await page.mouse.move(eBox.x + eBox.width / 2, eBox.y + eBox.height / 2, { steps: 6 });
      await page.mouse.up();

      selected = await assertRangeSelected(page, expectedRange);
    }

    if (!selected) {
      const snap = await page.evaluate(() => window.__HWPX_TEST_BRIDGE?.getStateSnapshot?.());
      throw new Error(`cell range selection failed: ${JSON.stringify(snap?.selection)}`);
    }

    // Apply font family via toolbar UI (table context uses table/cell sidebar tabs).
    const targetFont = "Nanum Gothic";
    const fontDropdown = page.locator("[data-hwpx-testid='toolbar-font-family']");
    await fontDropdown.waitFor({ state: "visible", timeout: 120000 });
    await fontDropdown.locator("button").first().click();
    await fontDropdown.locator("button", { hasText: targetFont }).click();
    await page.waitForTimeout(260);

    const styles = await page.evaluate((range) => window.__HWPX_TEST_BRIDGE?.getTableRangeTextStyles?.(range) ?? [], expectedRange);
    if (!Array.isArray(styles) || styles.length < 4) {
      throw new Error(`expected at least 4 cell styles, got ${Array.isArray(styles) ? styles.length : "non-array"}`);
    }
    for (const item of styles) {
      if (item.fontFamily !== targetFont) {
        throw new Error(`font not applied to cell (${item.row},${item.col}): ${item.fontFamily} !== ${targetFont}`);
      }
    }

    // Export and reopen in-app to ensure serialization keeps the font settings.
    const bytes = await page.evaluate(async () => {
      const bridge = window.__HWPX_TEST_BRIDGE;
      if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
      const out = await bridge.exportHwpx();
      if (!out || out.length === 0) throw new Error("exported bytes are empty");
      await bridge.openHwpx(out);
      return out.length;
    });
    if (!Number.isFinite(bytes) || bytes <= 0) throw new Error("export/reopen did not return bytes length");

    const ref2 = await page.evaluate(() => window.__HWPX_TEST_BRIDGE?.findFirstTableRef?.());
    if (!ref2) throw new Error("table not found after reopen");
    const range2 = { ...ref2, row: 0, col: 0, endRow: 1, endCol: 1 };

    const styles2 = await page.evaluate((range) => window.__HWPX_TEST_BRIDGE?.getTableRangeTextStyles?.(range) ?? [], range2);
    if (!Array.isArray(styles2) || styles2.length < 4) {
      throw new Error(`expected at least 4 cell styles after reopen, got ${Array.isArray(styles2) ? styles2.length : "non-array"}`);
    }
    for (const item of styles2) {
      if (item.fontFamily !== targetFont) {
        throw new Error(`font not persisted to cell (${item.row},${item.col}): ${item.fontFamily} !== ${targetFont}`);
      }
    }

    const pageEl = page.locator("[data-page]").first();
    await pageEl.scrollIntoViewIfNeeded();
    await pageEl.screenshot({ path: screenshotPath });
    console.log(`[e2e] screenshot: ${screenshotPath}`);
  } finally {
    if (browser) await browser.close();
    await stopServer(server);
  }
}

run().catch((error) => {
  console.error("[e2e] fatal:", error);
  process.exit(1);
});
