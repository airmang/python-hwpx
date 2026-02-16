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

function extractCellTextExcludingNested(cellEl) {
  const parts = [];
  const stack = [{ el: cellEl, inTbl: false }];
  while (stack.length > 0) {
    const { el, inTbl } = stack.pop();
    const isTbl = inTbl || localName(el) === "tbl";
    for (const child of Array.from(el.childNodes)) {
      if (!child) continue;
      if (child.nodeType === 3 && !isTbl) {
        const text = child.nodeValue ?? "";
        if (text.trim()) parts.push(text);
        continue;
      }
      if (child.nodeType !== 1) continue;
      const childEl = child;
      if (!isTbl && localName(childEl) === "t") {
        const text = childEl.textContent ?? "";
        if (text) parts.push(text);
      }
      stack.push({ el: childEl, inTbl: isTbl });
    }
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
      text: extractCellTextExcludingNested(cellEl),
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
  server.kill("SIGTERM");
  await new Promise((resolve) => setTimeout(resolve, 1200));
  if (server.exitCode == null) server.kill("SIGKILL");
}

function parseArgs(argv) {
  const args = { input: "", output: "", port: 3120 };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--in") args.input = argv[i + 1] ?? "";
    if (a === "--out") args.output = argv[i + 1] ?? "";
    if (a === "--port") args.port = Number(argv[i + 1] ?? "3120");
  }
  return args;
}

async function run() {
  const { input, output, port } = parseArgs(process.argv.slice(2));
  if (!input || !output) {
    throw new Error('Usage: node retype-from-hwpx.mjs --in \"/path/file.hwpx\" --out \"/path/out.hwpx\"');
  }

  const editorRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const baseUrl = `http://127.0.0.1:${port}`;
  const evidenceDir = path.join(editorRoot, "features", "evidence", "playwright");
  const nextDevLockPath = path.join(editorRoot, ".next", "dev", "lock");
  await mkdir(evidenceDir, { recursive: true });
  await rm(nextDevLockPath, { force: true });

  const bytes = await readFile(input);
  const src = await HwpxDocument.open(bytes);
  const dump = buildDump(src);

  const server = spawn("pnpm", ["dev", "--port", String(port)], {
    cwd: editorRoot,
    env: { ...process.env, PORT: String(port) },
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

    await page.evaluate(async (d) => {
      const bridge = window.__HWPX_TEST_BRIDGE;
      if (!bridge) throw new Error("bridge missing");
      await bridge.retypeFromDump(d);
    }, dump);

    await page.waitForTimeout(500);
    const screenshotPath = path.resolve(path.join(evidenceDir, "RETYPE.png"));
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log("[retype] screenshot:", screenshotPath);

    const exported = await page.evaluate(async () => {
      const bridge = window.__HWPX_TEST_BRIDGE;
      if (!bridge) throw new Error("bridge missing");
      return await bridge.exportHwpx();
    });
    await writeFile(output, new Uint8Array(exported));
    console.log("[retype] wrote:", path.resolve(output));
  } finally {
    if (browser) await browser.close();
    await stopServer(server);
  }
}

run().catch((e) => {
  console.error("[retype] fatal:", e);
  process.exit(1);
});

