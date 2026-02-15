import { Command } from "commander";
import {
  openHwpxFile,
  exportToMarkdownBundle,
  exportToText,
  exportSectionText,
  convertHwpFileToHwpxBytes,
  extractPart,
  getHwpxInfo,
  listParts,
  type MarkdownExportOptions,
  type MarkdownImageManifestItem,
  type MarkdownImageMode,
  type TextExportOptions,
} from "@ubermensch1218/hwpx-tools";
import { mkdir, writeFile } from "fs/promises";
import { basename, dirname, extname, relative, resolve } from "path";
import { handleMcpConfig, type McpConfigOptions } from "./commands/mcp-config.js";

export interface ReadOptions {
  section?: number;
}

export interface ExportOptions {
  format: "md" | "txt";
  output: string;
  imageMode?: string;
  imagesDir?: string;
  manifest?: string;
  tokenEfficient?: boolean;
}

export interface HwpxToMdOptions {
  output?: string;
  imageMode?: string;
  imagesDir?: string;
  manifest?: string;
  tokenEfficient?: boolean;
}

export interface HwpToHwpxOptions {
  output?: string;
}

function parseImageMode(value: string | undefined, fallback: MarkdownImageMode): MarkdownImageMode {
  if (!value) return fallback;
  if (value === "markdown" || value === "placeholder" || value === "omit") {
    return value;
  }
  throw new Error(`Unsupported image mode: ${value}. Use one of: markdown, placeholder, omit`);
}

function toPosixPath(value: string): string {
  return value.replace(/\\/g, "/");
}

function defaultMarkdownOutputPath(inputPath: string): string {
  const inputDir = dirname(inputPath);
  const inputBase = basename(inputPath, extname(inputPath));
  return resolve(inputDir, `${inputBase}.md`);
}

function defaultManifestOutputPath(markdownOutputPath: string): string {
  const outputDir = dirname(markdownOutputPath);
  const outputBase = basename(markdownOutputPath, extname(markdownOutputPath));
  return resolve(outputDir, `${outputBase}.images-manifest.json`);
}

async function writeImageFiles(
  hwpx: Awaited<ReturnType<typeof openHwpxFile>>,
  images: MarkdownImageManifestItem[],
  imagesDir: string
): Promise<number> {
  await mkdir(imagesDir, { recursive: true });

  const written = new Set<string>();
  let count = 0;

  for (const image of images) {
    if (!image.href || image.missingPart) continue;
    if (written.has(image.href)) continue;
    if (!hwpx.hasPart(image.href)) continue;

    const fileName = basename(image.href);
    const outPath = resolve(imagesDir, fileName);
    await writeFile(outPath, hwpx.getPart(image.href));
    written.add(image.href);
    count += 1;
  }

  return count;
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
    .option("--image-mode <mode>", "Image mode for markdown export: markdown, placeholder, omit")
    .option("--images-dir <dir>", "Extract image files into this directory")
    .option("--manifest <file>", "Write markdown image manifest JSON")
    .option("--token-efficient", "Enable token-efficient markdown normalization")
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
          const imageMode = parseImageMode(
            options.imageMode,
            options.tokenEfficient ? "placeholder" : "markdown"
          );
          const imagesDir = options.imagesDir ? resolve(options.imagesDir) : null;
          const imageBasePath = imagesDir
            ? toPosixPath(relative(dirname(outputPath), imagesDir) || ".")
            : "images";

          const mdOptions: MarkdownExportOptions = {
            includeSectionSeparators: true,
            convertHeadingStyles: true,
            tokenEfficient: !!options.tokenEfficient,
            imageMode,
            imageBasePath,
          };

          const result = exportToMarkdownBundle(hwpx, mdOptions);
          content = result.markdown;

          if (imagesDir) {
            const writtenCount = await writeImageFiles(hwpx, result.images, imagesDir);
            console.error(`Extracted ${writtenCount} image file(s) to ${imagesDir}`);
          }

          if (options.manifest) {
            const manifestPath = resolve(options.manifest);
            await mkdir(dirname(manifestPath), { recursive: true });
            await writeFile(
              manifestPath,
              JSON.stringify(
                {
                  source: filePath,
                  generatedAt: new Date().toISOString(),
                  imageMode,
                  tokenEfficient: !!options.tokenEfficient,
                  images: result.images,
                  stats: result.stats,
                },
                null,
                2
              ),
              "utf-8"
            );
            console.error(`Wrote image manifest: ${manifestPath}`);
          }
        } else if (options.format === "txt") {
          const txtOptions: TextExportOptions = {
            paragraphSeparator: "\n",
            sectionSeparator: "\n\n",
          };
          content = exportToText(hwpx, txtOptions);
        } else {
          throw new Error(`Unsupported format: ${options.format}`);
        }

        await mkdir(dirname(outputPath), { recursive: true });
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

  // hwp-to-hwpx command (best-effort conversion)
  program
    .command("hwp-to-hwpx <file>")
    .description("Convert HWP (HWP 5.x binary) file to HWPX (best-effort)")
    .option("-o, --output <file>", "HWPX output file (default: <input>.hwpx)")
    .action(async (file: string, options: HwpToHwpxOptions) => {
      const filePath = resolve(file);
      const inputBase = basename(filePath, extname(filePath));
      const outputPath = resolve(options.output ?? resolve(dirname(filePath), `${inputBase}.hwpx`));

      console.error(`Converting: ${filePath}`);
      console.error(`Output: ${outputPath}`);

      try {
        const hwpxBytes = await convertHwpFileToHwpxBytes(filePath);
        await mkdir(dirname(outputPath), { recursive: true });
        await writeFile(outputPath, hwpxBytes);
        console.error(`Wrote HWPX: ${outputPath}`);
      } catch (error) {
        console.error(
          "Error converting file:",
          error instanceof Error ? error.message : String(error)
        );
        process.exit(1);
      }
    });

  // hwpx-to-md command (token-efficient markdown export with image manifest)
  program
    .command("hwpx-to-md <file>")
    .description("Convert HWPX file to token-efficient Markdown with image manifest")
    .option("-o, --output <file>", "Markdown output file (default: <input>.md)")
    .option("--image-mode <mode>", "Image mode: markdown, placeholder, omit", "placeholder")
    .option("--images-dir <dir>", "Extract image files into this directory")
    .option("--manifest <file>", "Image manifest output path (default: <output>.images-manifest.json)")
    .option("--no-token-efficient", "Disable token-efficient markdown normalization")
    .action(async (file: string, options: HwpxToMdOptions) => {
      const filePath = resolve(file);
      const outputPath = resolve(options.output ?? defaultMarkdownOutputPath(filePath));
      const imageMode = parseImageMode(options.imageMode, "placeholder");
      const tokenEfficient = options.tokenEfficient ?? true;
      const imagesDir = options.imagesDir ? resolve(options.imagesDir) : null;
      const manifestPath = resolve(options.manifest ?? defaultManifestOutputPath(outputPath));
      const imageBasePath = imagesDir
        ? toPosixPath(relative(dirname(outputPath), imagesDir) || ".")
        : "images";

      console.error(`Converting: ${filePath}`);
      console.error(`Output: ${outputPath}`);
      console.error(`Image mode: ${imageMode}`);
      console.error(`Token efficient: ${tokenEfficient ? "yes" : "no"}`);

      try {
        const hwpx = await openHwpxFile(filePath);
        const result = exportToMarkdownBundle(hwpx, {
          includeSectionSeparators: true,
          convertHeadingStyles: true,
          tokenEfficient,
          imageMode,
          imageBasePath,
        });

        await mkdir(dirname(outputPath), { recursive: true });
        await writeFile(outputPath, result.markdown, "utf-8");
        console.error(`Wrote markdown: ${outputPath}`);

        if (imagesDir) {
          const writtenCount = await writeImageFiles(hwpx, result.images, imagesDir);
          console.error(`Extracted ${writtenCount} image file(s) to ${imagesDir}`);
        }

        await mkdir(dirname(manifestPath), { recursive: true });
        await writeFile(
          manifestPath,
          JSON.stringify(
            {
              source: filePath,
              markdown: outputPath,
              generatedAt: new Date().toISOString(),
              imageMode,
              tokenEfficient,
              imagesDir,
              images: result.images,
              stats: result.stats,
            },
            null,
            2
          ),
          "utf-8"
        );
        console.error(`Wrote image manifest: ${manifestPath}`);
      } catch (error) {
        console.error(
          "Error converting file:",
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
