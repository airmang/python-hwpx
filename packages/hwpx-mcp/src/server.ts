#!/usr/bin/env node

/**
 * HWPX MCP Server
 *
 * Model Context Protocol server for HWPX document manipulation.
 * Provides tools for reading, exporting, and inspecting HWPX files.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import {
  HwpxDocument,
  HwpxOxmlDocument,
  TextExtractor,
} from "@ubermensch1218/hwpxcore";
import * as fs from "fs";
import * as path from "path";

// Create MCP server instance
const server = new McpServer({
  name: "hwpx-mcp",
  version: "0.1.0",
});

// Cache for loaded documents to avoid re-parsing
const documentCache = new Map<string, HwpxDocument>();

/**
 * Load an HWPX file and return the HwpxDocument instance.
 */
async function loadHwpx(filePath: string): Promise<HwpxDocument> {
  const absolutePath = path.resolve(filePath);

  if (!fs.existsSync(absolutePath)) {
    throw new Error(`File not found: ${absolutePath}`);
  }

  // Check cache
  const cached = documentCache.get(absolutePath);
  if (cached) {
    return cached;
  }

  const buffer = fs.readFileSync(absolutePath);
  const doc = await HwpxDocument.open(buffer);

  // Cache the document
  documentCache.set(absolutePath, doc);

  return doc;
}

/**
 * Get basic information about an HWPX file.
 */
function getHwpxInfo(doc: HwpxDocument): object {
  const oxml = doc.oxml;
  const sections = oxml.sections;

  const sectionInfo = sections.map((section, index) => ({
    index,
    partName: section.partName,
    paragraphCount: section.paragraphs.length,
  }));

  const headers = oxml.headers;

  return {
    sectionCount: sections.length,
    headerCount: headers.length,
    sections: sectionInfo,
  };
}

/**
 * Extract text from an HWPX file.
 */
function extractText(doc: HwpxDocument): string {
  const extractor = new TextExtractor(doc.package);
  return extractor.extractText("\n");
}

/**
 * Convert HWPX content to Markdown format.
 */
function exportMarkdown(doc: HwpxDocument): string {
  const oxml = doc.oxml;
  const sections = oxml.sections;
  const lines: string[] = [];

  for (let i = 0; i < sections.length; i++) {
    const section = sections[i]!;

    if (i > 0) {
      lines.push("");
      lines.push("---");
      lines.push("");
    }

    for (const paragraph of section.paragraphs) {
      const text = getParagraphText(paragraph);
      if (text.trim()) {
        lines.push(text);
      }
    }
  }

  return lines.join("\n");
}

/**
 * Get text content from a paragraph.
 */
function getParagraphText(paragraph: { element: Element }): string {
  const element = paragraph.element;
  const parts: string[] = [];

  // Walk through runs and text elements
  const elements = element.getElementsByTagName("*");
  for (let i = 0; i < elements.length; i++) {
    const run = elements.item(i);
    if (run && (run.localName === "t" || run.tagName === "hp:t")) {
      const text = run.textContent ?? "";
      if (text) {
        parts.push(text);
      }
    }
  }

  return parts.join("");
}

/**
 * Extract a specific XML part from the HWPX package.
 */
function extractXmlPart(doc: HwpxDocument, partName: string): string {
  const pkg = doc.package;
  const partNames = pkg.partNames();

  // Try to find the part
  let targetPart = partName;

  // Common part mappings
  const partMappings: Record<string, string> = {
    content: "Contents/content.hpf",
    header: "Contents/header.xml",
    settings: "Contents/settings.xml",
    manifest: "META-INF/manifest.xml",
  };

  const lowerPartName = partName.toLowerCase();
  if (partMappings[lowerPartName]) {
    targetPart = partMappings[lowerPartName]!;
  }

  // Check if it's a section number (e.g., "section0", "section1")
  const sectionMatch = partName.match(/^section(\d+)$/i);
  if (sectionMatch) {
    targetPart = `Contents/section${sectionMatch[1]}.xml`;
  }

  // Find matching entry
  const matchingEntry = partNames.find((entry) => {
    return entry === targetPart || entry.endsWith("/" + targetPart);
  });

  if (!matchingEntry) {
    const availableParts = partNames.filter((e) => e.endsWith(".xml")).join(", ");
    throw new Error(
      `Part not found: ${partName}. Available XML parts: ${availableParts}`
    );
  }

  const data = pkg.getPart(matchingEntry);
  return new TextDecoder().decode(data);
}

// Register tools

// Tool 1: hwpx_read - Extract text from HWPX file
server.tool(
  "hwpx_read",
  "Extract text content from an HWPX file",
  {
    path: z.string().describe("Absolute or relative path to the HWPX file"),
  },
  async ({ path }) => {
    try {
      const doc = await loadHwpx(path);
      const text = extractText(doc);

      return {
        content: [
          {
            type: "text" as const,
            text: text || "(No text content found)",
          },
        ],
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        content: [
          {
            type: "text" as const,
            text: `Error reading HWPX file: ${message}`,
          },
        ],
        isError: true,
      };
    }
  }
);

// Tool 2: hwpx_export - Export HWPX to another format
server.tool(
  "hwpx_export",
  "Export HWPX document to another format (markdown or plain text)",
  {
    path: z.string().describe("Absolute or relative path to the HWPX file"),
    format: z.enum(["md", "txt"]).describe("Output format: 'md' for Markdown, 'txt' for plain text"),
  },
  async ({ path, format }) => {
    try {
      const doc = await loadHwpx(path);
      let output: string;

      if (format === "md") {
        output = exportMarkdown(doc);
      } else {
        output = extractText(doc);
      }

      return {
        content: [
          {
            type: "text" as const,
            text: output || "(No content to export)",
          },
        ],
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        content: [
          {
            type: "text" as const,
            text: `Error exporting HWPX file: ${message}`,
          },
        ],
        isError: true,
      };
    }
  }
);

// Tool 3: hwpx_extract_xml - Extract internal XML part
server.tool(
  "hwpx_extract_xml",
  "Extract an internal XML part from the HWPX package",
  {
    path: z.string().describe("Absolute or relative path to the HWPX file"),
    part: z.string().describe("Part name: 'header', 'manifest', 'section0', 'section1', etc., or full path like 'Contents/header.xml'"),
  },
  async ({ path, part }) => {
    try {
      const doc = await loadHwpx(path);
      const xml = extractXmlPart(doc, part);

      return {
        content: [
          {
            type: "text" as const,
            text: xml,
          },
        ],
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        content: [
          {
            type: "text" as const,
            text: `Error extracting XML part: ${message}`,
          },
        ],
        isError: true,
      };
    }
  }
);

// Tool 4: hwpx_info - Get metadata about HWPX file
server.tool(
  "hwpx_info",
  "Get metadata and structure information about an HWPX file",
  {
    path: z.string().describe("Absolute or relative path to the HWPX file"),
  },
  async ({ path }) => {
    try {
      const doc = await loadHwpx(path);
      const info = getHwpxInfo(doc);

      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(info, null, 2),
          },
        ],
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        content: [
          {
            type: "text" as const,
            text: `Error getting HWPX info: ${message}`,
          },
        ],
        isError: true,
      };
    }
  }
);

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("HWPX MCP Server started");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
