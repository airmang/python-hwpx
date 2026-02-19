import { spawn } from "node:child_process";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";
import { HwpxDocument, HwpxOxmlTable } from "@ubermensch1218/hwpxcore";

function localName(el) {
  return el?.localName ?? String(el?.nodeName ?? "").split(":").pop() ?? "";
}

function elementChildren(el) {
  return Array.from(el.childNodes).filter((n) => n && n.nodeType === 1);
}

function textNodesInRun(runEl) {
  const parts = [];
  for (const child of elementChildren(runEl)) {
    if (localName(child) !== "t") continue;
    const text = child.textContent ?? "";
    if (text) parts.push(text);
  }
  return parts.join("");
}

function extractInlineText(paragraph) {
  const parts = [];
  for (const child of elementChildren(paragraph.element)) {
    if (localName(child) !== "run") continue;
    const runText = textNodesInRun(child);
    if (runText) parts.push(runText);
  }
  return parts.join("");
}

function dumpTable(table, paragraph) {
  const anchors = [];
  for (const pos of table.iterGrid()) {
    if (pos.anchor[0] !== pos.row || pos.anchor[1] !== pos.column) continue;
    const cellEl = pos.cell.element;
    const nestedTblEls = Array.from(cellEl.getElementsByTagName("*")).filter(
      (el) => localName(el) === "tbl",
    );
    const nestedTables = nestedTblEls.map((tblEl) => dumpTable(new HwpxOxmlTable(tblEl, paragraph), paragraph));
    anchors.push({
      row: pos.anchor[0],
      col: pos.anchor[1],
      rowSpan: pos.span[0],
      colSpan: pos.span[1],
      text: pos.cell.text ?? "",
      nestedTables,
    });
  }

  return {
    rowCount: table.rowCount,
    colCount: table.columnCount,
    cells: anchors,
  };
}

function buildDump(doc) {
  return {
    sections: doc.sections.map((section) => ({
      paragraphs: section.paragraphs.map((para) => ({
        inlineText: extractInlineText(para),
        tables: para.tables.map((t) => dumpTable(t, para)),
      })),
    })),
  };
}

function blankDumpContent(dump) {
  const blankTable = (table) => ({
    rowCount: table.rowCount,
    colCount: table.colCount,
    cells: table.cells.map((cell) => ({
      row: cell.row,
      col: cell.col,
      rowSpan: cell.rowSpan,
      colSpan: cell.colSpan,
      text: "",
      nestedTables: (cell.nestedTables ?? []).map(blankTable),
    })),
  });

  return {
    sections: dump.sections.map((section) => ({
      paragraphs: section.paragraphs.map((para) => ({
        inlineText: "",
        tables: (para.tables ?? []).map(blankTable),
      })),
    })),
  };
}

function findFirstTypedCellRef(dump) {
  for (let sIdx = 0; sIdx < dump.sections.length; sIdx += 1) {
    const section = dump.sections[sIdx];
    for (let pIdx = 0; pIdx < (section?.paragraphs ?? []).length; pIdx += 1) {
      const para = section.paragraphs[pIdx];
      for (let tIdx = 0; tIdx < (para?.tables ?? []).length; tIdx += 1) {
        const table = para.tables[tIdx];
        for (const cell of table?.cells ?? []) {
          if (String(cell?.text ?? "").trim()) {
            return { sectionIndex: sIdx, paragraphIndex: pIdx, tableIndex: tIdx, row: cell.row, col: cell.col };
          }
        }
      }
    }
  }
  return null;
}

function parseArgs(argv) {
  const args = {
    input: "/Users/jskang/Downloads/[별첨2] AI솔루션 세부 설명자료.hwpx",
    output: "/Users/jskang/nomadlab/output/retype/human-typed-attachment2.hwpx",
    port: 3099,
    route: "/playwright",
  };

  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--in") args.input = argv[i + 1] ?? args.input;
    if (a === "--out") args.output = argv[i + 1] ?? args.output;
    if (a === "--port") args.port = Number(argv[i + 1] ?? String(args.port));
    if (a === "--route") args.route = argv[i + 1] ?? args.route;
  }
  return args;
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
      if (res.status > 0) return;
    } catch {
      // ignore until timeout
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error(`dev server timeout after ${timeoutMs}ms (${url})`);
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
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

function normalizeForTyping(text) {
  return String(text ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/\t/g, "    ");
}

function compareToken(text) {
  return normalizeForTyping(text).replace(/\s+/g, "").trim();
}

async function captureCheckpoint(page, imagePath, payload) {
  await page.evaluate((data) => {
    const id = "__hwpx_automation_checkpoint__";
    let badge = document.getElementById(id);
    if (!badge) {
      badge = document.createElement("div");
      badge.id = id;
      badge.style.position = "fixed";
      badge.style.right = "12px";
      badge.style.top = "12px";
      badge.style.zIndex = "2147483647";
      badge.style.padding = "8px 10px";
      badge.style.background = "rgba(17, 24, 39, 0.88)";
      badge.style.color = "#fff";
      badge.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, monospace";
      badge.style.fontSize = "12px";
      badge.style.borderRadius = "8px";
      badge.style.pointerEvents = "none";
      document.body.appendChild(badge);
    }
    badge.textContent = `${data.label} | p:${data.typedParagraphs} c:${data.typedCells}`;
  }, payload);
  await page.screenshot({ path: imagePath, fullPage: true });
}

async function clearEditable(locator) {
  await locator.evaluate((el) => {
    if (!(el instanceof HTMLElement)) return;
    el.focus();
    if (el.isContentEditable) {
      el.textContent = "";
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
}

async function typeTextLikeHuman(locator, text, opts = {}) {
  const allowEnter = opts.allowEnter !== false;
  const normalized = normalizeForTyping(text);
  if (!normalized) return;
  if (!allowEnter) {
    await locator.type(normalized.replace(/\n+/g, " "), { delay: 8 });
    return;
  }
  const lines = normalized.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    if (line.length > 0) {
      await locator.type(line, { delay: 8 });
    }
    if (i < lines.length - 1) {
      await locator.press("Enter");
      await locator.page().waitForTimeout(25);
    }
  }
}

async function fillParagraph(page, sectionIndex, paragraphIndex, text) {
  if (!text) return false;
  const normalized = normalizeForTyping(text);
  const selector =
    `[data-hwpx-paragraph='1'][data-section-index='${sectionIndex}'][data-paragraph-index='${paragraphIndex}']`;
  const target = page.locator(selector).first();
  if ((await target.count()) === 0) return false;
  await target.scrollIntoViewIfNeeded();
  try {
    await target.click({ timeout: 3000 });
  } catch {
    try {
      await target.click({ timeout: 3000, force: true });
    } catch {
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (el instanceof HTMLElement) el.focus();
      }, selector);
    }
  }
  await clearEditable(target);
  await typeTextLikeHuman(target, normalized, { allowEnter: false });
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el instanceof HTMLElement) el.blur();
  }, selector);
  await page.waitForTimeout(20);

  let actual = "";
  try {
    actual = normalizeForTyping((await target.textContent({ timeout: 1200 })) ?? "");
  } catch {
    return true;
  }
  if (!normalized.trim()) return true;
  if (compareToken(actual) === compareToken(normalized)) return true;

  await page.evaluate(({ sel, value }) => {
    const el = document.querySelector(sel);
    if (!(el instanceof HTMLElement)) return;
    el.focus();
    el.textContent = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.blur();
  }, { sel: selector, value: normalized });
  await page.waitForTimeout(20);
  try {
    const after = normalizeForTyping((await target.textContent({ timeout: 1200 })) ?? "");
    return compareToken(after) === compareToken(normalized);
  } catch {
    return true;
  }
}

async function fillTableCell(page, sectionIndex, paragraphIndex, tableIndex, row, col, text) {
  if (!text) return false;
  const normalized = normalizeForTyping(text);
  const selector =
    `td[data-hwpx-cell='1'][data-section-index='${sectionIndex}'][data-paragraph-index='${paragraphIndex}'][data-table-index='${tableIndex}'][data-row='${row}'][data-col='${col}']`;
  const cell = page.locator(selector).first();
  if ((await cell.count()) === 0) return false;
  await cell.scrollIntoViewIfNeeded();
  try {
    await cell.click({ timeout: 3000 });
  } catch {
    try {
      await cell.click({ timeout: 3000, force: true });
    } catch {
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (el instanceof HTMLElement) el.focus();
      }, selector);
    }
  }
  await clearEditable(cell);
  await typeTextLikeHuman(cell, normalized, { allowEnter: true });
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el instanceof HTMLElement) el.blur();
  }, selector);
  await page.waitForTimeout(20);
  await page.evaluate((args) => {
    const bridge = window.__HWPX_TEST_BRIDGE;
    if (!bridge?.updateCellText) return;
    bridge.updateCellText(args);
  }, {
    sectionIndex,
    paragraphIndex,
    tableIndex,
    row,
    col,
    text: normalized,
  });
  await page.waitForTimeout(20);

  let actual = "";
  try {
    actual = normalizeForTyping((await cell.textContent({ timeout: 1200 })) ?? "");
  } catch {
    return true;
  }
  if (!normalized.trim()) return true;
  if (compareToken(actual) === compareToken(normalized)) return true;

  await page.evaluate(({ sel, value }) => {
    const el = document.querySelector(sel);
    if (!(el instanceof HTMLElement)) return;
    el.focus();
    el.textContent = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.blur();
  }, { sel: selector, value: normalized });
  await page.waitForTimeout(20);
  await page.evaluate((args) => {
    const bridge = window.__HWPX_TEST_BRIDGE;
    if (!bridge?.updateCellText) return;
    bridge.updateCellText(args);
  }, {
    sectionIndex,
    paragraphIndex,
    tableIndex,
    row,
    col,
    text: normalized,
  });
  await page.waitForTimeout(20);
  try {
    const after = normalizeForTyping((await cell.textContent({ timeout: 1200 })) ?? "");
    return compareToken(after) === compareToken(normalized);
  } catch {
    return true;
  }
}

async function fillDumpViaTyping(page, dump, onCheckpoint) {
  let typedParagraphs = 0;
  let typedCells = 0;
  const paragraphMilestones = new Set([1]);
  const cellMilestones = new Set([1, 5, 10, 15, 20, 25]);

  for (let sIdx = 0; sIdx < dump.sections.length; sIdx += 1) {
    const section = dump.sections[sIdx];
    const paragraphs = section?.paragraphs ?? [];

    for (let pIdx = 0; pIdx < paragraphs.length; pIdx += 1) {
      const paragraph = paragraphs[pIdx];
      const pText = paragraph?.inlineText ?? "";
      if (await fillParagraph(page, sIdx, pIdx, pText)) {
        typedParagraphs += 1;
        if (onCheckpoint && paragraphMilestones.has(typedParagraphs)) {
          await onCheckpoint({
            label: `after-paragraph-${typedParagraphs}`,
            typedParagraphs,
            typedCells,
          });
        }
      }

      const tables = paragraph?.tables ?? [];
      for (let tIdx = 0; tIdx < tables.length; tIdx += 1) {
        const table = tables[tIdx];
        const cells = table?.cells ?? [];
        for (const cell of cells) {
          if (await fillTableCell(page, sIdx, pIdx, tIdx, cell.row, cell.col, cell.text ?? "")) {
            typedCells += 1;
            if (onCheckpoint && cellMilestones.has(typedCells)) {
              await onCheckpoint({
                label: `after-cell-${typedCells}`,
                typedParagraphs,
                typedCells,
              });
            }
          }
        }
      }
    }
  }

  return { typedParagraphs, typedCells };
}

async function run() {
  const { input, output, port, route } = parseArgs(process.argv.slice(2));
  const editorRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const outputDir = path.dirname(path.resolve(output));
  const screenshotPath = path.resolve("/Users/jskang/nomadlab/output/playwright/human-typed-attachment2.png");
  const screenshotFocusPath = path.resolve("/Users/jskang/nomadlab/output/playwright/human-typed-attachment2-focus.png");
  const checkpointDir = path.resolve("/Users/jskang/nomadlab/output/playwright/human-typed-checkpoints");
  const baseUrl = `http://127.0.0.1:${port}`;
  const nextDevLockPath = path.join(editorRoot, ".next", "dev", "lock");

  await mkdir(outputDir, { recursive: true });
  await mkdir(path.dirname(screenshotPath), { recursive: true });
  await rm(checkpointDir, { recursive: true, force: true });
  await mkdir(checkpointDir, { recursive: true });
  await rm(nextDevLockPath, { force: true });

  const sourceBytes = await readFile(input);
  const sourceDoc = await HwpxDocument.open(sourceBytes);
  const sourceDump = buildDump(sourceDoc);
  const firstTypedCellRef = findFirstTypedCellRef(sourceDump);

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
    console.log("[human-type] reusing existing server:", baseUrl);
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
    await captureCheckpoint(page, path.join(checkpointDir, "00-open.png"), {
      label: "open",
      typedParagraphs: 0,
      typedCells: 0,
    });

    await page.evaluate(async (bytes) => {
      const bridge = window.__HWPX_TEST_BRIDGE;
      if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
      await bridge.openHwpx(bytes);
    }, Array.from(sourceBytes));
    await captureCheckpoint(page, path.join(checkpointDir, "01-skeleton.png"), {
      label: "source-opened",
      typedParagraphs: 0,
      typedCells: 0,
    });

    await page.waitForTimeout(400);
    const typed = await fillDumpViaTyping(page, sourceDump, async (checkpoint) => {
      const fileName = checkpoint.label.replace(/[^a-zA-Z0-9_-]/g, "_");
      await captureCheckpoint(page, path.join(checkpointDir, `${fileName}.png`), checkpoint);
      console.log(
        `[human-type] checkpoint: ${checkpoint.label} (p:${checkpoint.typedParagraphs} c:${checkpoint.typedCells})`,
      );
    });
    await page.waitForTimeout(350);

    const exported = await page.evaluate(async () => {
      const bridge = window.__HWPX_TEST_BRIDGE;
      if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
      return await bridge.exportHwpx();
    });
    await writeFile(output, new Uint8Array(exported));

    let pageScreenshotSaved = false;
    let focusScreenshotSaved = false;
    if (firstTypedCellRef) {
      const cellSelector =
        `td[data-hwpx-cell='1'][data-section-index='${firstTypedCellRef.sectionIndex}'][data-paragraph-index='${firstTypedCellRef.paragraphIndex}'][data-table-index='${firstTypedCellRef.tableIndex}'][data-row='${firstTypedCellRef.row}'][data-col='${firstTypedCellRef.col}']`;
      const cell = page.locator(cellSelector).first();
      if ((await cell.count()) > 0) {
        try {
          await cell.scrollIntoViewIfNeeded();
          const table = cell.locator("xpath=ancestor::table[1]").first();
          if ((await table.count()) > 0) {
            await table.screenshot({ path: screenshotFocusPath });
          } else {
            await cell.screenshot({ path: screenshotFocusPath });
          }
          focusScreenshotSaved = true;
        } catch {
          // fallback below
        }
      }
    }

    const pageEl = page.locator("[data-page]").first();
    if ((await pageEl.count()) > 0) {
      try {
        await pageEl.scrollIntoViewIfNeeded();
        await pageEl.screenshot({ path: screenshotPath });
        pageScreenshotSaved = true;
      } catch {
        // fallback below
      }
    }
    if (!pageScreenshotSaved) {
      await page.screenshot({ path: screenshotPath, fullPage: true });
    }

    console.log("[human-type] typed paragraphs:", typed.typedParagraphs);
    console.log("[human-type] typed cells:", typed.typedCells);
    console.log("[human-type] checkpoints:", checkpointDir);
    console.log("[human-type] screenshot:", screenshotPath);
    if (focusScreenshotSaved && firstTypedCellRef) {
      console.log("[human-type] focus screenshot:", screenshotFocusPath);
    }
    console.log("[human-type] output:", path.resolve(output));
  } finally {
    if (browser) await browser.close();
    if (ownsServer && server) {
      await stopServer(server);
    }
  }
}

run().catch((error) => {
  console.error("[human-type] fatal:", error);
  process.exit(1);
});
