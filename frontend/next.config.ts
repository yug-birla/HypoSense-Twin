import type { NextConfig } from "next";

// Static export served by FastAPI (ADR-007): one offline process at demo time.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
};

export default config;
