import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return {
      // fallback rewrites only fire when no App Router file matches the path.
      // This lets our SSE route handlers in app/api/v1/*/route.ts take priority
      // over the catch-all proxy — otherwise beforeFiles rewrites intercept
      // every /api/* request before route handlers are checked.
      fallback: [
        {
          source: "/api/:path*",
          destination: "http://localhost:8000/api/:path*",
        },
      ],
    };
  },
};

export default nextConfig;
