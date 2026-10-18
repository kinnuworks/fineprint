import type { NextConfig } from "next";

// Reports are fetched per request from the FinePrint API with a short
// revalidate window, so the classic fetch caching model is used here.
const nextConfig: NextConfig = {
  cacheComponents: false,
};

export default nextConfig;
