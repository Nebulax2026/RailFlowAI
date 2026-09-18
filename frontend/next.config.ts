import type { NextConfig } from "next";

const apiBaseUrl = process.env.RAILFLOW_API_BASE_URL ?? "http://127.0.0.1:8000";
const staticExport = process.env.RAILFLOW_STATIC_EXPORT === "1";
const proxyConfig: NextConfig = staticExport
  ? {}
  : {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${apiBaseUrl}/api/:path*` }];
      }
    };

const nextConfig: NextConfig = {
  reactStrictMode: true,
  ...(staticExport ? { output: "export" as const, trailingSlash: true } : {}),
  allowedDevOrigins: ["127.0.0.1"],
  turbopack: { root: process.cwd() },
  ...proxyConfig
};

export default nextConfig;
