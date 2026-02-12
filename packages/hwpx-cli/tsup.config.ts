import { defineConfig } from "tsup";

export default defineConfig([
  // CLI executable
  {
    entry: {
      cli: "src/cli.ts",
    },
    format: ["esm"],
    dts: false,
    clean: true,
    shims: true,
    splitting: false,
    minify: false,
    external: ["@ubermensch1218/hwpx-tools"],
  },
  // Library
  {
    entry: {
      index: "src/index.ts",
    },
    format: ["esm"],
    dts: true,
    clean: false,
    shims: true,
    external: ["@ubermensch1218/hwpx-tools"],
  },
]);
