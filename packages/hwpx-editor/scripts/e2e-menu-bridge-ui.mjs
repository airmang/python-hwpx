import { spawn } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const editorRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const outputDir = path.resolve(editorRoot, "..", "..", "..", "..", "output", "playwright");
const reportPath = path.join(outputDir, "menu-bridge-ui-report.json");
const screenshotPath = path.join(outputDir, "MENU-bridge-ui.png");
const nextDevLockPath = path.join(editorRoot, ".next", "dev", "lock");

const port = Number(process.env.HWPX_E2E_PORT || 3112);
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

async function clickBridgeAction(page, menuLabel, itemLabel, expectedDialogText, expectedTargetTitle) {
  const menuBar = page.locator("div[class*='min-h-[42px]']").first();
  await menuBar.getByRole("button", { name: menuLabel, exact: true }).first().click();
  const escaped = itemLabel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const item = page.getByRole("button", { name: new RegExp(`^${escaped}`) }).first();
  await item.waitFor({ timeout: 30000 });

  const isDisabled = await item.isDisabled();
  if (isDisabled) {
    throw new Error(`${itemLabel} is still disabled`);
  }

  const alertMessage = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`bridge alert timeout: ${itemLabel}`)), 30000);
    page.once("dialog", async (dialog) => {
      try {
        const msg = dialog.message();
        await dialog.accept();
        clearTimeout(timer);
        resolve(msg);
      } catch (error) {
        clearTimeout(timer);
        reject(error);
      }
    });
    item.click({ force: true }).catch((error) => {
      clearTimeout(timer);
      reject(error);
    });
  });

  if (typeof alertMessage !== "string" || !alertMessage.includes(expectedDialogText)) {
    throw new Error(`unexpected bridge alert for ${itemLabel}: ${alertMessage}`);
  }

  if (expectedTargetTitle) {
    const modal = page.locator("div[class*='fixed inset-0 z-[100]']").first();
    await modal.waitFor({ timeout: 30000 });
    await modal.getByText(expectedTargetTitle, { exact: true }).first().waitFor({ timeout: 30000 });
    await page.keyboard.press("Escape");
    await modal.waitFor({ state: "hidden", timeout: 30000 });
  }

  return { isDisabled, alertMessage };
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

    const checks = {
      dropCap: await clickBridgeAction(page, "서식", "문단 첫 글자 장식…", "문단 첫 글자 장식", "글자 모양"),
      masterPage: await clickBridgeAction(page, "쪽", "바탕쪽", "바탕쪽", "머리말/꼬리말"),
      spellCheck: await clickBridgeAction(page, "도구", "맞춤법 검사…", "맞춤법 검사", "자동 고침"),
      macro: await clickBridgeAction(page, "도구", "매크로…", "매크로", null),
      preferences: await clickBridgeAction(page, "도구", "환경 설정…", "환경 설정", null),
    };

    const sidebarCloseButton = page.getByRole("button", { name: "사이드바 닫기", exact: true });
    await sidebarCloseButton.waitFor({ timeout: 30000 });
    const pageSetupSectionVisible = await page.getByText("용지 크기", { exact: true }).isVisible();
    if (!pageSetupSectionVisible) {
      throw new Error("environment settings bridge did not open page setup sidebar");
    }

    await page.locator("[data-hwpx-editor-root='true']").screenshot({ path: screenshotPath });

    const report = {
      timestamp: new Date().toISOString(),
      baseUrl,
      screenshotPath,
      checks: {
        ...checks,
        sidebarOpened: true,
        pageSetupSectionVisible,
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
