import type { NextConfig } from "next";

// Static export: the whole app is plain files (HTML/JS/CSS + data JSON) that any static host
// can serve. There is no server to run or pay for. Live weather is fetched by the phone.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
