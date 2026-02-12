/**
 * MCP configuration command for hwpxtool.
 * Adds hwpx-mcp server to Claude Code global settings.
 */

import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { homedir } from "os";

export interface McpConfigOptions {
  global?: boolean;
  project?: boolean;
  list?: boolean;
  remove?: boolean;
}

const CLAUDE_GLOBAL_SETTINGS_PATH = join(homedir(), ".claude", "settings.json");
const CLAUDE_PROJECT_MCP_PATH = ".mcp.json";

interface ClaudeSettings {
  mcpServers?: Record<string, McpServerConfig>;
  [key: string]: unknown;
}

interface McpServerConfig {
  command: string;
  args?: string[];
  env?: Record<string, string>;
}

/**
 * Get the path to hwpx-mcp server.
 */
function getMcpServerPath(): string {
  // Try to find the server relative to this package
  const possiblePaths = [
    join(__dirname, "..", "..", "..", "hwpx-mcp", "dist", "server.js"),
    join(__dirname, "..", "..", "hwpx-mcp", "dist", "server.js"),
    join(__dirname, "..", "hwpx-mcp", "dist", "server.js"),
  ];

  for (const p of possiblePaths) {
    if (existsSync(p)) {
      return p;
    }
  }

  // Fallback to global install path
  return "hwpx-mcp-server";
}

/**
 * Get the MCP server configuration.
 */
function getMcpServerConfig(): McpServerConfig {
  const serverPath = getMcpServerPath();

  if (serverPath === "hwpx-mcp-server") {
    // Globally installed
    return {
      command: "hwpx-mcp-server",
    };
  }

  // Local path
  return {
    command: "node",
    args: [serverPath],
  };
}

/**
 * Configure MCP for global Claude Code settings.
 */
export function configureGlobalMcp(options: McpConfigOptions = {}): void {
  const settingsPath = CLAUDE_GLOBAL_SETTINGS_PATH;
  const serverConfig = getMcpServerConfig();
  const serverName = "hwpx";

  // Ensure directory exists
  const settingsDir = dirname(settingsPath);
  if (!existsSync(settingsDir)) {
    mkdirSync(settingsDir, { recursive: true });
  }

  // Read existing settings
  let settings: ClaudeSettings = {};
  if (existsSync(settingsPath)) {
    try {
      const content = readFileSync(settingsPath, "utf-8");
      settings = JSON.parse(content);
    } catch {
      // If parsing fails, start fresh
      settings = {};
    }
  }

  // Initialize mcpServers if not exists
  if (!settings.mcpServers) {
    settings.mcpServers = {};
  }

  if (options.list) {
    // List configured servers
    console.log("Configured MCP servers:");
    for (const [name, config] of Object.entries(settings.mcpServers)) {
      console.log(`  - ${name}: ${config.command} ${(config.args || []).join(" ")}`);
    }
    return;
  }

  if (options.remove) {
    // Remove hwpx server
    if (settings.mcpServers[serverName]) {
      delete settings.mcpServers[serverName];
      writeFileSync(settingsPath, JSON.stringify(settings, null, 2), "utf-8");
      console.log(`Removed "${serverName}" from global MCP settings.`);
    } else {
      console.log(`"${serverName}" is not configured in global MCP settings.`);
    }
    return;
  }

  // Add or update hwpx server
  settings.mcpServers[serverName] = serverConfig;

  // Write settings
  writeFileSync(settingsPath, JSON.stringify(settings, null, 2), "utf-8");

  console.log(`Added "${serverName}" to global MCP settings.`);
  console.log(`\nConfiguration:`);
  console.log(JSON.stringify({ [serverName]: serverConfig }, null, 2));
  console.log(`\nSettings file: ${settingsPath}`);
  console.log(`\nRestart Claude Code to apply changes.`);
}

/**
 * Configure MCP for project-level settings.
 */
export function configureProjectMcp(options: McpConfigOptions = {}): void {
  const settingsPath = join(process.cwd(), CLAUDE_PROJECT_MCP_PATH);
  const serverConfig = getMcpServerConfig();
  const serverName = "hwpx";

  if (options.list) {
    if (existsSync(settingsPath)) {
      try {
        const content = readFileSync(settingsPath, "utf-8");
        const config = JSON.parse(content);
        console.log("Project MCP servers:");
        if (config.mcpServers) {
          for (const [name, srv] of Object.entries(config.mcpServers)) {
            const s = srv as McpServerConfig;
            console.log(`  - ${name}: ${s.command} ${(s.args || []).join(" ")}`);
          }
        }
      } catch {
        console.log("No valid project MCP configuration found.");
      }
    } else {
      console.log("No project MCP configuration found.");
    }
    return;
  }

  if (options.remove) {
    if (existsSync(settingsPath)) {
      try {
        const content = readFileSync(settingsPath, "utf-8");
        const config = JSON.parse(content) as { mcpServers?: Record<string, McpServerConfig> };
        if (config.mcpServers?.[serverName]) {
          delete config.mcpServers[serverName];
          writeFileSync(settingsPath, JSON.stringify(config, null, 2), "utf-8");
          console.log(`Removed "${serverName}" from project MCP settings.`);
        } else {
          console.log(`"${serverName}" is not configured in project MCP settings.`);
        }
      } catch {
        console.log("Failed to update project MCP settings.");
      }
    }
    return;
  }

  // Read or create project config
  let config: { mcpServers: Record<string, McpServerConfig> } = { mcpServers: {} };

  if (existsSync(settingsPath)) {
    try {
      const content = readFileSync(settingsPath, "utf-8");
      config = { ...config, ...JSON.parse(content) };
      if (!config.mcpServers) {
        config.mcpServers = {};
      }
    } catch {
      // Start fresh if parsing fails
    }
  }

  // Add or update hwpx server
  config.mcpServers[serverName] = serverConfig;

  // Write settings
  writeFileSync(settingsPath, JSON.stringify(config, null, 2), "utf-8");

  console.log(`Added "${serverName}" to project MCP settings.`);
  console.log(`\nConfiguration:`);
  console.log(JSON.stringify({ [serverName]: serverConfig }, null, 2));
  console.log(`\nSettings file: ${settingsPath}`);
}

/**
 * Main MCP config command handler.
 */
export function handleMcpConfig(options: McpConfigOptions): void {
  if (options.project) {
    configureProjectMcp(options);
  } else {
    // Default to global
    configureGlobalMcp(options);
  }
}
