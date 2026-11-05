import type { NextConfig } from "next";

// The browser only ever talks to this origin; /api is proxied to the FastAPI backend.
const backend = process.env.DEALROOM_API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default config;
