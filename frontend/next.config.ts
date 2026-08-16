import type { NextConfig } from "next";

const BACKEND = process.env.NOTULA_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The floating dev badge overlaps the sidebar's provider card.
  devIndicators: false,
  // Same-origin dev loop: the FastAPI backend serves /api and /healthz on :8000.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/healthz", destination: `${BACKEND}/healthz` },
    ];
  },
};

export default nextConfig;
