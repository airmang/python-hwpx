import { FONT_FAMILIES } from "./constants";
import { useEditorStore } from "./store";

type Store = ReturnType<typeof useEditorStore.getState>;
const currentStore = () => useEditorStore.getState();

const SAMPLE_PNG_BYTES = new Uint8Array([
  137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82,
  0, 0, 0, 1, 0, 0, 0, 1, 8, 4, 0, 0, 0, 181, 28, 12, 2,
  0, 0, 0, 11, 73, 68, 65, 84, 120, 218, 99, 252, 255, 31, 0,
  3, 3, 2, 0, 238, 254, 75, 137, 0, 0, 0, 0, 73, 69, 78, 68,
  174, 66, 96, 130,
]);

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function findFirstTableParagraphIndex(store: Store): number {
  const section = currentStore().doc?.sections?.[0];
  if (!section) return -1;
  for (let i = 0; i < section.paragraphs.length; i += 1) {
    try {
      if (section.paragraphs[i]?.tables?.length > 0) return i;
    } catch {
      // ignore malformed paragraph wrappers and continue
    }
  }
  return -1;
}

function selectParagraph(store: Store, paragraphIndex = 0) {
  store.setSelection({
    sectionIndex: 0,
    paragraphIndex,
    type: "paragraph",
    textStartOffset: 0,
    textEndOffset: 0,
  });
}

function selectCell(
  store: Store,
  paragraphIndex: number,
  row = 0,
  col = 0,
  endRow?: number,
  endCol?: number,
) {
  store.setSelection({
    sectionIndex: 0,
    paragraphIndex,
    type: "cell",
    tableIndex: 0,
    row,
    col,
    endRow,
    endCol,
    objectType: "table",
  });
}

function selectTable(store: Store, paragraphIndex: number) {
  store.setSelection({
    sectionIndex: 0,
    paragraphIndex,
    type: "table",
    tableIndex: 0,
    objectType: "table",
  });
}

function selectImage(store: Store, imageIndex = 0) {
  store.setSelection({
    sectionIndex: 0,
    paragraphIndex: 0,
    type: "paragraph",
    objectType: "image",
    imageIndex,
  });
}

async function ensureFreshDocument(store: Store) {
  for (let i = 0; i < 10; i += 1) {
    await store.newDocument();
    if (currentStore().doc) {
      selectParagraph(currentStore(), 0);
      return;
    }
    await wait(250);
  }
  throw new Error("newDocument failed after retries");
}

function ensureTable(store: Store, rows = 3, cols = 3) {
  const doc = currentStore().doc;
  if (!doc) {
    throw new Error("doc is missing");
  }
  const section = doc.sections?.[0];
  if (!section) {
    throw new Error("section 0 is missing");
  }
  let paragraphIndex = findFirstTableParagraphIndex(store);
  if (paragraphIndex < 0) {
    try {
      const anchor = doc.addParagraph("feature-table-anchor");
      anchor.addTable(rows, cols);
    } catch {
      // fallback to store action below
    }
    store.rebuild();
    paragraphIndex = findFirstTableParagraphIndex(store);
  }
  if (paragraphIndex < 0) {
    store.addTable(0, 0, rows, cols);
    store.rebuild();
    paragraphIndex = findFirstTableParagraphIndex(store);
  }
  if (paragraphIndex < 0) {
    throw new Error("failed to ensure table");
  }
  selectCell(store, paragraphIndex, 0, 0, 0);
  return { paragraphIndex, tableIndex: 0 };
}

function ensureImage(store: Store) {
  const findImageParagraphIndex = () => {
    const vmIndex =
      currentStore().viewModel?.sections?.[0]?.paragraphs?.findIndex((p) => p.images.length > 0) ?? -1;
    if (vmIndex >= 0) return vmIndex;
    const section = currentStore().doc?.sections?.[0];
    if (!section) return -1;
    for (let i = 0; i < section.paragraphs.length; i += 1) {
      const para = section.paragraphs[i];
      if (!para) continue;
      if (para.pictures.length > 0) return i;
    }
    return -1;
  };

  let paragraphIndex = findImageParagraphIndex();
  if (paragraphIndex < 0) {
    for (let i = 0; i < 3 && paragraphIndex < 0; i += 1) {
      store.insertImage(SAMPLE_PNG_BYTES, "image/png", 25, 25);
      store.rebuild();
      paragraphIndex = findImageParagraphIndex();
      if (paragraphIndex >= 0) break;
    }
  }
  if (paragraphIndex < 0) {
    const sel = currentStore().selection;
    if (sel?.objectType === "image" && sel.sectionIndex === 0) {
      paragraphIndex = sel.paragraphIndex;
    }
  }
  if (paragraphIndex < 0) throw new Error("failed to ensure image paragraph");
  currentStore().setSelection({
    sectionIndex: 0,
    paragraphIndex,
    type: "paragraph",
    objectType: "image",
    imageIndex: 0,
  });
}

function countImages(): number {
  const vmCount =
    currentStore().viewModel?.sections?.[0]?.paragraphs?.reduce(
      (sum, para) => sum + para.images.length,
      0,
    ) ?? 0;
  if (vmCount > 0) return vmCount;

  const section = currentStore().doc?.sections?.[0];
  if (!section) return 0;
  return section.paragraphs.reduce((sum, para) => sum + (para?.pictures.length ?? 0), 0);
}

function firstImageVM() {
  const sectionVm = currentStore().viewModel?.sections?.[0];
  if (!sectionVm) return null;
  for (let i = 0; i < sectionVm.paragraphs.length; i += 1) {
    const para = sectionVm.paragraphs[i];
    if (!para || para.images.length === 0) continue;
    return { paragraphIndex: i, image: para.images[0]! };
  }
  return null;
}

function closeAllDialogs(store: Store) {
  store.closeCharFormatDialog();
  store.closeParaFormatDialog();
  store.closeBulletNumberDialog();
  store.closeCharMapDialog();
  store.closeFindReplaceDialog();
  store.closeWordCountDialog();
  store.closeTemplateDialog();
  store.closeClipboardDialog();
  store.closeHeaderFooterDialog();
  store.closePageNumberDialog();
  store.closeStyleDialog();
  store.closeCaptionDialog();
  store.closeAutoCorrectDialog();
  store.closeOutlineDialog();
  store.closeShapeDialog();
  store.closeTocDialog();
  store.closeSaveDialog();
}

export async function runFeatureScenario(store: Store, code: string) {
  await ensureFreshDocument(store);
  closeAllDialogs(store);

  switch (code) {
    case "DOC-001": {
      await store.newDocument();
      break;
    }

    case "DOC-002": {
      if (!store.doc) throw new Error("doc is missing");
      const bytes = await store.doc.save();
      await store.openDocument(bytes);
      break;
    }

    case "DOC-003": {
      if (!store.doc) throw new Error("doc is missing");
      const bytes = await store.doc.save();
      if (bytes.length === 0) throw new Error("saved bytes are empty");
      break;
    }

    case "DOC-004": {
      selectParagraph(store, 0);
      store.insertTextAtCursor("undo-redo");
      store.undo();
      store.redo();
      break;
    }

    case "TXT-001": {
      store.updateParagraphText(0, 0, "TXT-001 paragraph edit");
      break;
    }

    case "TXT-002": {
      store.updateParagraphText(0, 0, "split-merge");
      store.splitParagraph(0, 0, 5);
      store.mergeParagraphWithPrevious(0, 1);
      break;
    }

    case "TXT-003": {
      store.insertBlockAt(0, 0, "new block");
      store.deleteBlock(0, 0);
      break;
    }

    case "TXT-004": {
      const tableRef = ensureTable(store);
      store.updateCellText(0, tableRef.paragraphIndex, 0, 0, 0, "cell text");
      break;
    }

    case "TXT-005": {
      selectParagraph(store, 0);
      store.insertTab();
      store.insertTextAtCursor("tabbed text");
      break;
    }

    case "FMT-001": {
      selectParagraph(store, 0);
      store.toggleBold();
      store.toggleItalic();
      store.toggleUnderline();
      store.toggleStrikethrough();
      break;
    }

    case "FMT-002": {
      selectParagraph(store, 0);
      store.setFontFamily("Noto Sans KR");
      store.setFontSize(13);
      break;
    }

    case "FMT-003": {
      selectParagraph(store, 0);
      store.setTextColor("#0055aa");
      store.setHighlightColor("#fff59d");
      break;
    }

    case "FMT-004": {
      selectParagraph(store, 0);
      store.setAlignment("CENTER");
      break;
    }

    case "FMT-005": {
      selectParagraph(store, 0);
      store.setLineSpacing(1.6);
      break;
    }

    case "FMT-006": {
      selectParagraph(store, 0);
      store.setLeftIndent(420);
      store.setFirstLineIndent(-210);
      break;
    }

    case "FMT-007": {
      selectParagraph(store, 0);
      store.applyNumbering(1);
      store.applyOutlineLevel(2);
      break;
    }

    case "TBL-001": {
      store.addTable(0, 0, 3, 3);
      break;
    }

    case "TBL-002": {
      ensureTable(store);
      store.insertTableRow("below");
      store.insertTableColumn("right");
      break;
    }

    case "TBL-003": {
      const tableRef = ensureTable(store);
      store.deleteTableRow();
      selectCell(store, tableRef.paragraphIndex, 0, 0, 0);
      store.deleteTableColumn();
      break;
    }

    case "TBL-004": {
      const tableRef = ensureTable(store);
      selectCell(store, tableRef.paragraphIndex, 0, 0, 1, 1);
      store.mergeTableCells();
      selectCell(store, tableRef.paragraphIndex, 0, 0, 0, 0);
      store.splitTableCell();
      break;
    }

    case "TBL-005": {
      ensureTable(store);
      store.deleteTable();
      break;
    }

    case "TBL-006": {
      ensureTable(store);
      store.setTableSize(120, 42);
      break;
    }

    case "TBL-007": {
      const tableRef = ensureTable(store);
      store.resizeTableColumn(0, tableRef.paragraphIndex, 0, 0, 180);
      break;
    }

    case "TBL-008": {
      ensureTable(store);
      store.setTableOutMargin({ top: 2.2, bottom: 2.2, left: 1.8, right: 1.8 });
      store.setTableInMargin({ top: 1.4, bottom: 1.4, left: 1.2, right: 1.2 });
      break;
    }

    case "TBL-009": {
      ensureTable(store);
      store.setTablePageBreak("CELL");
      store.setTableRepeatHeader(true);
      break;
    }

    case "TBL-010": {
      ensureTable(store);
      store.setCellBorder(["top", "bottom", "left", "right"], {
        type: "DASH",
        width: "0.3 mm",
        color: "#dd2255",
      });
      store.setCellBackground("#ffef99");
      store.setCellVertAlign("CENTER");
      break;
    }

    case "TBL-011": {
      const tableRef = ensureTable(store);
      selectTable(store, tableRef.paragraphIndex);
      store.setTableBorder(["top", "bottom", "left", "right"], {
        type: "NONE",
        width: "0.12 mm",
        color: "#0044aa",
      });
      store.setTableBackground("#e9f4ff");
      break;
    }

    case "TBL-012": {
      const tableRef = ensureTable(store, 4, 4);
      const table = store.doc?.sections?.[0]?.paragraphs?.[tableRef.paragraphIndex]?.tables?.[0];
      if (!table) throw new Error("table is missing");
      const before = `${table.rowCount}x${table.columnCount}`;
      selectCell(store, tableRef.paragraphIndex, 0, 0, 1, 1);
      store.mergeTableCells();
      selectCell(store, tableRef.paragraphIndex, 0, 0, 0, 0);
      store.splitTableCell();
      const afterTable = store.doc?.sections?.[0]?.paragraphs?.[tableRef.paragraphIndex]?.tables?.[0];
      if (!afterTable) throw new Error("table disappeared after merge/split");
      const after = `${afterTable.rowCount}x${afterTable.columnCount}`;
      if (before !== after) {
        throw new Error(`table shape changed: ${before} -> ${after}`);
      }
      break;
    }

    case "IMG-001": {
      store.insertImage(SAMPLE_PNG_BYTES, "image/png", 40, 20);
      break;
    }

    case "IMG-002": {
      ensureImage(store);
      store.updatePictureSize(48, 28);
      store.resizeImage(120, 80);
      break;
    }

    case "IMG-003": {
      ensureImage(store);
      store.setImageOutMargin({ top: 1.3, bottom: 1.3, left: 1.3, right: 1.3 });
      break;
    }

    case "IMG-004": {
      ensureImage(store);
      const beforeCount = countImages();
      store.deleteSelectedObject();
      const afterCount = countImages();
      if (afterCount !== Math.max(0, beforeCount - 1)) {
        throw new Error(`image delete count mismatch: ${beforeCount} -> ${afterCount}`);
      }
      break;
    }

    case "IMG-005": {
      ensureImage(store);
      const beforeCount = countImages();
      const root = document.querySelector<HTMLElement>('[data-hwpx-editor-root="true"]');
      if (!root) throw new Error("editor root is missing");
      root.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Backspace",
          bubbles: true,
          cancelable: true,
        }),
      );

      const afterCount = countImages();
      if (afterCount !== Math.max(0, beforeCount - 1)) {
        throw new Error(`keyboard image delete count mismatch: ${beforeCount} -> ${afterCount}`);
      }
      break;
    }

    case "IMG-006": {
      ensureImage(store);
      store.setImageSizeProtect(true);
      store.setImageOffsetRelTo({ horzRelTo: "PAGE", vertRelTo: "PAGE" });
      store.setImageScale(120, 120);
      store.setImageCrop({ leftMm: 0.5, rightMm: 0.5, topMm: 0.5, bottomMm: 0.5 });
      store.setImageAdjustment({ brightness: 8, contrast: -4, effect: "BLACK_WHITE", alpha: 128 });
      store.setImageRotation(15);
      store.setImageLock(true);

      const firstImage = firstImageVM();
      const imageVm = firstImage?.image;
      if (!imageVm) throw new Error("image is missing in view model");
      if (imageVm.horzRelTo !== "PAGE" || imageVm.vertRelTo !== "PAGE") {
        throw new Error("offset relTo was not applied");
      }
      if (imageVm.effect !== "BLACK_WHITE") throw new Error("effect was not applied");
      if (imageVm.alpha !== 128) throw new Error("alpha was not applied");
      break;
    }

    case "PAG-001": {
      store.updatePageSize(210, 297);
      store.updatePageMargins({ left: 20, right: 20, top: 15, bottom: 15, header: 10, footer: 10, gutter: 0 });
      store.updatePageOrientation("PORTRAIT");
      break;
    }

    case "PAG-002": {
      store.setPageNumbering({ position: "footer-center", startNumber: 3 });
      break;
    }

    case "PAG-003": {
      selectParagraph(store, 0);
      store.insertColumnBreak();
      store.insertPageBreak();
      break;
    }

    case "PAG-004": {
      selectParagraph(store, 0);
      store.insertFootnote();
      store.insertEndnote();
      break;
    }

    case "PAG-005": {
      store.setWatermarkText("CONFIDENTIAL");
      break;
    }

    case "PAG-006": {
      store.setColumnCount(2, 9);
      break;
    }

    case "DIA-001": {
      store.openCharFormatDialog();
      store.closeCharFormatDialog();
      store.openParaFormatDialog();
      store.closeParaFormatDialog();
      store.openCharMapDialog();
      store.closeCharMapDialog();
      break;
    }

    case "DIA-002": {
      store.updateParagraphText(0, 0, "alpha beta alpha");
      store.openFindReplaceDialog();
      store.findNextMatch({ search: "alpha", scope: "document" });
      store.findAndReplaceAdvanced({ search: "alpha", replacement: "ALPHA", count: 1, scope: "document" });
      store.closeFindReplaceDialog();
      break;
    }

    case "DIA-003": {
      store.openTemplateDialog();
      store.addTemplate("feature-loop-template", "/tmp/template.hwpx", "auto-test");
      const id = store.templates[store.templates.length - 1]?.id;
      if (id) store.removeTemplate(id);
      store.closeTemplateDialog();
      break;
    }

    case "DIA-004": {
      store.openHeaderFooterDialog();
      store.setHeaderFooter({ headerText: "Header", footerText: "Footer" });
      store.closeHeaderFooterDialog();
      break;
    }

    case "DIA-005": {
      store.openStyleDialog();
      store.closeStyleDialog();
      store.openOutlineDialog();
      store.applyOutlineLevel(1);
      store.closeOutlineDialog();
      store.openTocDialog();
      store.insertToc({ title: "목차", maxLevel: 2 });
      store.closeTocDialog();
      break;
    }

    case "DIA-006": {
      store.openAutoCorrectDialog();
      store.closeAutoCorrectDialog();
      break;
    }

    case "DIA-007": {
      store.openShapeDialog();
      store.insertShape("rectangle", 25, 12);
      store.closeShapeDialog();
      break;
    }

    case "DIA-008": {
      store.openWordCountDialog();
      store.closeWordCountDialog();
      break;
    }

    case "DIA-009": {
      store.openClipboardDialog();
      store.pushClipboardHistory("클립보드-테스트");
      store.addSnippet("스니펫-테스트", "스니펫 내용");
      selectParagraph(store, 0);
      store.insertTextAtCursor(" ");
      store.insertTextAtCursor("클립보드-테스트");
      store.closeClipboardDialog();
      break;
    }

    case "DIA-010": {
      selectParagraph(store, 0);
      store.insertCaption({ kind: "figure", text: "시스템 구성도" });
      store.insertCaption({ kind: "table", text: "성능 비교" });
      store.insertCaptionList({ kind: "figure" });
      store.insertCaptionList({ kind: "table" });
      break;
    }

    case "SYS-001": {
      store.setSidebarTab("table");
      if (!store.uiState.sidebarOpen) store.toggleSidebar();
      store.setSidebarTab("para");
      break;
    }

    case "SYS-002": {
      selectParagraph(store, 0);
      const tableRef = ensureTable(store);
      selectCell(store, tableRef.paragraphIndex, 0, 0, 0, 0);
      selectTable(store, tableRef.paragraphIndex);
      break;
    }

    case "SYS-003": {
      store.updateParagraphText(0, 0, "alpha beta. gamma delta?");
      selectParagraph(store, 0);
      store.setSelection({
        sectionIndex: 0,
        paragraphIndex: 0,
        type: "paragraph",
        cursorOffset: 2,
      });
      store.selectWordAtCursor();
      store.selectSentenceAtCursor();
      store.selectParagraphAll();
      break;
    }

    case "FMT-008": {
      // Create a second paragraph for painting target.
      store.updateParagraphText(0, 0, "source");
      store.addParagraph("target");
      store.setSelection({ sectionIndex: 0, paragraphIndex: 0, type: "paragraph", cursorOffset: 0 });
      store.toggleBold();
      store.setAlignment("CENTER");
      store.startFormatPainter("both");
      store.setSelection({ sectionIndex: 0, paragraphIndex: 1, type: "paragraph", cursorOffset: 0 });
      // Painter should apply on selection change via store.setSelection hook.
      break;
    }

    case "TBL-013": {
      const tableRef = ensureTable(store, 3, 3);
      selectCell(store, tableRef.paragraphIndex, 1, 1, 1, 1);
      store.distributeTableColumns();
      store.distributeTableRows();
      store.moveTableRow("up");
      store.moveTableColumn("left");
      break;
    }

    case "TBL-014": {
      const tableRef = ensureTable(store, 3, 3);
      for (let r = 0; r <= 1; r += 1) {
        for (let c = 0; c <= 1; c += 1) {
          store.updateCellText(0, tableRef.paragraphIndex, tableRef.tableIndex, r, c, `R${r}C${c}`);
        }
      }
      store.rebuild();
      // Allow post-newDocument focus/selection effects in the Editor to settle,
      // otherwise they can overwrite cell selection right after we set it.
      await wait(420);

      // Programmatic cell range selection (UI gesture is covered by a separate Playwright e2e script).
      selectCell(store, tableRef.paragraphIndex, 0, 0, 1, 1);
      await wait(60);

      const targetFont = FONT_FAMILIES.find((f) => f !== "Noto Sans KR") ?? "Nanum Gothic";
      // Defensive: selection can be overwritten by DOM selection listeners; set it right before applying style.
      selectCell(store, tableRef.paragraphIndex, 0, 0, 1, 1);
      store.setFontFamily(targetFont);
      await wait(220);

      const assertRangeFont = (paragraphIndex: number) => {
        const vm = currentStore().viewModel;
        const tableVm = vm?.sections?.[0]?.paragraphs?.[paragraphIndex]?.tables?.[0];
        if (!tableVm) throw new Error("table view model missing");
        for (let r = 0; r <= 1; r += 1) {
          for (let c = 0; c <= 1; c += 1) {
            const cell = tableVm.cells[r]?.[c];
            if (!cell?.isAnchor) throw new Error(`cell (${r},${c}) is missing or not anchor`);
            if (cell.fontFamily !== targetFont) {
              throw new Error(`font not applied to cell (${r},${c}): ${cell.fontFamily} !== ${targetFont}`);
            }
          }
        }
      };

      assertRangeFont(tableRef.paragraphIndex);

      const doc = currentStore().doc;
      if (!doc) throw new Error("doc is missing before export");
      const bytes = await doc.save();
      if (bytes.length === 0) throw new Error("exported bytes are empty");

      await store.openDocument(bytes);
      await wait(260);

      const reopenedTableParagraphIndex = findFirstTableParagraphIndex(currentStore());
      if (reopenedTableParagraphIndex < 0) throw new Error("table not found after reopen");
      assertRangeFont(reopenedTableParagraphIndex);
      break;
    }

    default:
      throw new Error(`Unsupported feature code: ${code}`);
  }

  await wait(120);
  store.rebuild();
}
