import type { MetadataRoute } from "next";

export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Deer Scout",
    short_name: "Deer Scout",
    description: "Where to hunt public land in northern New Hampshire.",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0e1310",
    theme_color: "#0e1310",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
