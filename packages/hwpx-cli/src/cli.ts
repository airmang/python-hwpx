import { Command } from "commander";
import {
  openHwpxFile,
  exportToMarkdown,
  exportToText,
  exportSectionText,
  extractPart,
  getHwpxInfo,
  listParts,
  type MarkdownExportOptions,
  type TextExportOptions,
} from "@ubermensch1218/hwpx-tools";
import { writeFile } from "fs/promises";
import { resolve } from "path";
import { handleMcpConfig, type McpConfigOptions } from "./commands/mcp-config.js";

export interface ReadOptions {
  section?: number;
}

export interface ExportOptions {
  format: "md" | "txt";
  output: string;
}

export function createProgram(): Command {
  const program = new Command();

  program
    .name("hwpxtool")
    .description("CLI tool for HWPX file operations")
    .version("0.1.0");

  // read command
  program
    .command("read <file>")
    .description("Read HWPX file and output text content")
    .option("-s, --section <number>", "Section index to read (0-based)", parseInt)
    .action(async (file: string, options: ReadOptions) => {
      const filePath = resolve(file);
      console.error(`Reading: ${filePath}`);

      try {
        const hwpx = await openHwpxFile(filePath);

        if (options.section !== undefined) {
          const content = exportSectionText(hwpx, options.section);
          console.log(content);
        } else {
          const content = exportToText(hwpx);
          console.log(content);
        }
      } catch (error) {
        console.error(
          "Error reading file:",
          error instanceof Error ? error.message : String(error)
        );
        process.exit(1);
      }
    });

  // export command
  program
    .command("export <file>")
    .description("Export HWPX file to other formats")
    .requiredOption("-f, --format <format>", "Output format (md, txt)")
    .requiredOption("-o, --output <file>", "Output file path")
    .action(async (file: string, options: ExportOptions) => {
      const filePath = resolve(file);
      const outputPath = resolve(options.output);

      console.error(`Exporting: ${filePath}`);
      console.error(`Format: ${options.format}`);
      console.error(`Output: ${outputPath}`);

      try {
        const hwpx = await openHwpxFile(filePath);
        let content: string;

        if (options.format === "md") {
          const mdOptions: MarkdownExportOptions = {
            includeSectionSeparators: true,
            convertHeadingStyles: true,
          };
          content = exportToMarkdown(hwpx, mdOptions);
        } else if (options.format === "txt") {
          const txtOptions: TextExportOptions = {
            paragraphSeparator: "\n",
            sectionSeparator: "\n\n",
          };
          content = exportToText(hwpx, txtOptions);
        } else {
          throw new Error(`Unsupported format: ${options.format}`);
        }

        await writeFile(outputPath, content, "utf-8");
        console.error(`Successfully exported to ${outputPath}`);
      } catch (error) {
        console.error(
          "Error exporting file:",
          error instanceof Error ? error.message : String(error)
        );
        process.exit(1);
      }
    });

  // extract command
  program
    .command("extract <file> <part>")
    .description("Extract specific XML part from HWPX file")
    .action(async (file: string, part: string) => {
      const filePath = resolve(file);

      console.error(`Extracting: ${part} from ${filePath}`);

      try {
        const content = await extractPart(filePath, part);
        console.log(content);
      } catch (error) {
        console.error(
          "Error extracting part:",
          error instanceof Error ? error.message : String(error)
        );

        // List available parts on error
        try {
          const parts = await listParts(filePath);
          console.error("Available parts:");
          for (const p of parts) {
            console.error(`  - ${p}`);
          }
        } catch {
          // Ignore listing error
        }

        process.exit(1);
      }
    });

  // info command
  program
    .command("info <file>")
    .description("Display HWPX file metadata")
    .action(async (file: string) => {
      const filePath = resolve(file);

      console.error(`Getting info for: ${filePath}`);

      try {
        const info = await getHwpxInfo(filePath);
        console.log(JSON.stringify(info, null, 2));
      } catch (error) {
        console.error(
          "Error getting file info:",
          error instanceof Error ? error.message : String(error)
        );
        process.exit(1);
      }
    });

  // mcp-config command
  program
    .command("mcp-config")
    .description("Configure hwpx MCP server for Claude Code")
    .option("-g, --global", "Configure globally (default)", true)
    .option("-p, --project", "Configure for current project only")
    .option("-l, --list", "List configured MCP servers")
    .option("-r, --remove", "Remove hwpx from MCP configuration")
    .action((options: McpConfigOptions) => {
      handleMcpConfig(options);
    });

  return program;
}

// Run CLI when executed directly
const program = createProgram();
program.parse();
