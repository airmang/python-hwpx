import { spawn } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const editorRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const outputDir = path.resolve(editorRoot, "..", "..", "..", "..", "output", "playwright");
const reportPath = path.join(outputDir, "chart-ui-report.json");
const screenshotPath = path.join(outputDir, "CHART-ui.png");
const nextDevLockPath = path.join(editorRoot, ".next", "dev", "lock");

const port = Number(process.env.HWPX_E2E_PORT || 3111);
const baseUrl = `http://127.0.0.1:${port}`;

async function waitForServer(url, server, timeoutMs = 120000) {
  const started = Date.now();
  while (true) {
    if (server.exitCode != null) {
      throw new Error(`dev server exited early with code ${server.exitCode}`);
    }
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404) return;
    } catch {
      // retry
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error(`dev server timeout after ${timeoutMs}ms (${url})`);
    }
    await new Promise((resolve) => setTimeout(resolve, 900));
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
    await page.waitForSelector("[data-hwpx-editor-root='true']", { timeout: 120000 });

    // Insert chart through ribbon UI.
    await page.getByTitle("차트 삽입").first().click();
    await page.getByRole("heading", { name: "차트 삽입" }).waitFor({ timeout: 30000 });
    await page.getByRole("textbox", { name: "제목" }).fill("분기별 매출");
    await page.getByRole("combobox", { name: "차트 종류" }).selectOption("line");
    await page.getByRole("textbox", { name: "데이터 (한 줄에 하나, `항목: 값`)" })
      .fill("1분기: 120\n2분기: 95\n3분기: 140\n4분기: 170");
    await page.getByRole("button", { name: "삽입", exact: true }).click();

    // Assert chart text + visual + data table are present.
    await page.getByText("[차트:line] 분기별 매출").waitFor({ timeout: 30000 });
    const chartSvg = page.getByLabel("분기별 매출 선 차트");
    await chartSvg.waitFor({ timeout: 30000 });
    const isVisible = await chartSvg.isVisible();
    if (!isVisible) throw new Error("chart svg is not visible");

    const table = page.locator("table").first();
    await table.waitFor({ timeout: 30000 });
    const rows = await table.locator("tr").count();
    if (rows < 5) {
      throw new Error(`chart data table row count is too small: ${rows}`);
    }

    const q4Text = await table.locator("tr").nth(4).innerText();
    if (!q4Text.includes("4분기") || !q4Text.includes("170")) {
      throw new Error(`unexpected 4th data row text: ${q4Text}`);
    }

    await page.locator("[data-page]").first().screenshot({ path: screenshotPath });

    const report = {
      timestamp: new Date().toISOString(),
      baseUrl,
      screenshotPath,
      checks: {
        chartMetaText: true,
        chartSvgVisible: isVisible,
        tableRowCount: rows,
        q4RowText: q4Text,
      },
    };
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    console.log(`[e2e] screenshot: ${screenshotPath}`);
    console.log(`[e2e] report: ${reportPath}`);
  } finally {
    if (browser) await browser.close();
    await stopServer(server);
  }
}

run().catch((error) => {
  console.error("[e2e] fatal:", error);
  process.exit(1);
});
