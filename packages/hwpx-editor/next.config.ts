import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@hwpx/core"],
  turbopack: {
    resolveAlias: {
      fs: { browser: "./src/lib/empty-module.ts" },
      path: { browser: "./src/lib/empty-module.ts" },
      url: { browser: "./src/lib/empty-module.ts" },
    },
  },
  webpack: (config) => {
    config.resolve.fallback = {
      ...config.resolve.fallback,
      fs: false,
      path: false,
      url: false,
    };
    return config;
  },
};

export default nextConfig;
