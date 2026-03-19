import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["three"],
  turbopack: {},
  webpack: (config) => {
    config.externals = [...(config.externals || [])];
    return config;
  },
  reactCompiler: true,
};

export default nextConfig;
