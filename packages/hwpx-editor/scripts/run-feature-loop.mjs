import { spawn } from "node:child_process";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const editorRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const registryPath = path.join(editorRoot, "features", "FEATURE_REGISTRY.md");
const matrixPath = path.join(editorRoot, "features", "FEATURE_TESTABILITY_MATRIX.md");
const evidenceDir = path.join(editorRoot, "features", "evidence", "playwright");
const reportPath = path.join(evidenceDir, "feature-loop-report.json");
const nextDevLockPath = path.join(editorRoot, ".next", "dev", "lock");
const port = Number(process.env.HWPX_LOOP_PORT || 3100);
const baseUrl = `http://127.0.0.1:${port}`;

function parseFeatureCodes(markdown) {
  const codes = [];
  for (const line of markdown.split("\n")) {
    const m = line.match(/^\|\s*([A-Z]{3}-\d{3})\s*\|/);
    if (!m) continue;
    codes.push(m[1]);
  }
  return [...new Set(codes)];
}

function trimError(error) {
  const text = String(error || "unknown error").replace(/\s+/g, " ").trim();
  return text.length > 72 ? `${text.slice(0, 69)}...` : text;
}

function patchMatrix(matrixMarkdown, resultsByCode) {
  let next = matrixMarkdown.replace(
    /^- Playwright 증빙:.*$/m,
    `- Playwright 증빙: \`${path.resolve(reportPath)}\``,
  );

  const lines = next.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const m = line.match(/^\|\s*([A-Z]{3}-\d{3})\s*\|/);
    if (!m) continue;

    const code = m[1];
    const result = resultsByCode.get(code);
    if (!result) continue;

    const cols = line.split("|");
    if (cols.length < 8) continue;

    const statusCell =
      result.status === "passed"
        ? "실행(자동 루프 통과)"
        : `실패(${trimError(result.error)})`;

    cols[5] = ` ${statusCell} `;
    cols[6] = ` \`${result.screenshotPath}\` `;
    lines[i] = cols.join("|");
  }

  next = lines.join("\n");
  return next;
}

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

async function run() {
  await mkdir(evidenceDir, { recursive: true });
  // Next dev occasionally leaves a stale lock file after abrupt shutdown.
  // Remove it defensively so the feature loop can restart reliably.
  await rm(nextDevLockPath, { force: true });

  const registry = await readFile(registryPath, "utf8");
  const discovered = parseFeatureCodes(registry);
  const requested = process.env.HWPX_FEATURE_CODES
    ? process.env.HWPX_FEATURE_CODES.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean)
    : [];
  const codes = requested.length > 0
    ? requested
    : discovered;

  if (codes.length === 0) {
    throw new Error("no feature codes found in FEATURE_REGISTRY.md");
  }

  console.log(`[loop] features: ${codes.length}`);
  console.log(`[loop] start dev server: ${baseUrl}`);

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
  let page;

  const results = [];

  try {
    await waitForServer(baseUrl, server);

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1680, height: 1080 } });
    page = await context.newPage();

    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForFunction(() => Boolean(window.__HWPX_TEST_BRIDGE), { timeout: 120000 });
    await page.waitForTimeout(600);

    // Warm-up: first skeleton load may race with the very first newDocument call.
    for (let attempt = 0; attempt < 3; attempt += 1) {
      // eslint-disable-next-line no-await-in-loop
      const warmed = await page.evaluate(async () => {
        const bridge = window.__HWPX_TEST_BRIDGE;
        if (!bridge) return false;
        try {
          await bridge.runFeature("DOC-002");
          return true;
        } catch {
          return false;
        }
      });
      if (warmed) break;
      // eslint-disable-next-line no-await-in-loop
      await page.waitForTimeout(350);
    }

    for (const code of codes) {
      const startedAt = Date.now();
      const screenshotPath = path.resolve(path.join(evidenceDir, `${code}.png`));

      try {
        await page.evaluate(async (currentCode) => {
          const bridge = window.__HWPX_TEST_BRIDGE;
          if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
          await bridge.runFeature(currentCode);
          return bridge.getStateSnapshot();
        }, code);

        await page.waitForTimeout(140);
        await page.screenshot({ path: screenshotPath, fullPage: true });

        const row = {
          code,
          status: "passed",
          durationMs: Date.now() - startedAt,
          screenshotPath,
          error: null,
          executedAt: new Date().toISOString(),
        };
        results.push(row);
        console.log(`[loop] PASS ${code} (${row.durationMs}ms)`);
      } catch (error) {
        try {
          await page.screenshot({ path: screenshotPath, fullPage: true });
        } catch {
          // ignore secondary capture error
        }

        const row = {
          code,
          status: "failed",
          durationMs: Date.now() - startedAt,
          screenshotPath,
          error: trimError(error),
          executedAt: new Date().toISOString(),
        };
        results.push(row);
        console.log(`[loop] FAIL ${code} (${row.durationMs}ms) :: ${row.error}`);
      }
    }
  } finally {
    if (browser) await browser.close();
    await stopServer(server);
  }

  const passCount = results.filter((r) => r.status === "passed").length;
  const failCount = results.length - passCount;

  const payload = {
    generatedAt: new Date().toISOString(),
    baseUrl,
    total: results.length,
    passCount,
    failCount,
    results,
  };

  await writeFile(reportPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

  const matrix = await readFile(matrixPath, "utf8");
  const byCode = new Map(results.map((r) => [r.code, r]));
  const patched = patchMatrix(matrix, byCode);
  await writeFile(matrixPath, patched, "utf8");

  console.log(`[loop] report: ${path.resolve(reportPath)}`);
  console.log(`[loop] matrix: ${path.resolve(matrixPath)}`);
  console.log(`[loop] summary: ${passCount}/${results.length} passed, ${failCount} failed`);

  if (failCount > 0) {
    process.exitCode = 1;
  }
}

run().catch((error) => {
  console.error("[loop] fatal:", error);
  process.exit(1);
});
