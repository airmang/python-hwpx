import { defineConfig } from "tsup";
import path from "path";
import fs from "fs";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm", "cjs"],
  tsconfig: "tsconfig.build.json",
  dts: true,
  sourcemap: true,
  clean: true,
  splitting: false,
  banner: {
    js: '"use client";',
  },
  external: [
    "react",
    "react-dom",
    "react/jsx-runtime",
  ],
  esbuildPlugins: [
    {
      name: "resolve-path-alias",
      setup(build) {
        build.onResolve({ filter: /^@\// }, (args) => {
          const basePath = path.join(process.cwd(), "src", args.path.slice(2));
          // Try extensions: .ts, .tsx, /index.ts, /index.tsx
          const candidates = [
            basePath + ".ts",
            basePath + ".tsx",
            path.join(basePath, "index.ts"),
            path.join(basePath, "index.tsx"),
            basePath,
          ];
          for (const candidate of candidates) {
            if (fs.existsSync(candidate)) {
              return { path: candidate };
            }
          }
          return { path: basePath };
        });
      },
    },
  ],
});
