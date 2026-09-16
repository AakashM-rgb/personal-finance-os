import type { MetadataRoute } from "next";

/**
 * Next.js auto-generates /manifest.webmanifest from this and links it in
 * <head> - no secrets belong here, only public branding/display metadata.
 * "standalone" (not "fullscreen") keeps the OS status bar visible, which
 * users expect from a finance app they may glance at quickly.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Finance App — Personal Financial OS",
    short_name: "Finance App",
    description: "Record, understand, and plan your money — online or offline.",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#0a0a0a",
    theme_color: "#18181b",
    orientation: "portrait-primary",
    icons: [
      {
        src: "/icons/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: "/icons/icon-maskable.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "maskable",
      },
    ],
  };
}
