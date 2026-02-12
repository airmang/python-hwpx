/**
 * @ubermensch1218/hwpx-mcp
 *
 * MCP server for HWPX document manipulation.
 *
 * This package provides a Model Context Protocol (MCP) server
 * that allows AI assistants to interact with HWPX documents.
 *
 * ## Available Tools
 *
 * - `hwpx_read` - Extract text content from an HWPX file
 * - `hwpx_export` - Export HWPX to Markdown or plain text format
 * - `hwpx_extract_xml` - Extract internal XML parts from the HWPX package
 * - `hwpx_info` - Get metadata and structure information about an HWPX file
 *
 * ## Usage
 *
 * Run the MCP server:
 *
 * ```bash
 * npx @ubermensch1218/hwpx-mcp
 * ```
 *
 * Or use with Claude Desktop or other MCP clients by adding to your config:
 *
 * ```json
 * {
 *   "mcpServers": {
 *     "hwpx": {
 *       "command": "npx",
 *       "args": ["@ubermensch1218/hwpx-mcp"]
 *     }
 *   }
 * }
 * ```
 */

// Re-export types for programmatic use
export { HwpxDocument, HwpxPackage, TextExtractor } from "@ubermensch1218/hwpxcore";
