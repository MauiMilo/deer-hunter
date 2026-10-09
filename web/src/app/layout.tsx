import type { Metadata, Viewport } from "next";
import { DataProvider } from "@/components/DataProvider";
import { ServiceWorker } from "@/components/ServiceWorker";
import { TabBar } from "@/components/ui";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Deer Scout",
  description: "Where to hunt public land in northern New Hampshire, with the evidence behind every pick.",
  applicationName: "Deer Scout",
  appleWebApp: { capable: true, title: "Deer Scout", statusBarStyle: "black-translucent" },
  icons: {
    icon: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0e1310" },
    { media: "(prefers-color-scheme: light)", color: "#f3f1ea" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <DataProvider>
          <main className="mx-auto min-h-dvh max-w-xl pb-24">{children}</main>
          <TabBar />
        </DataProvider>
        <ServiceWorker />
      </body>
    </html>
  );
}
