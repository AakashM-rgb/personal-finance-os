import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";

import { AuthProvider } from "@/lib/auth-context";
import { ServiceWorkerRegistration } from "@/lib/offline/service-worker-registration";
import { THEME_BOOTSTRAP_SCRIPT } from "@/lib/theme";
import { ThemeSync } from "@/lib/theme-sync";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Finance App",
  description: "Your personal financial operating system.",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Finance App",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Financial forms need pinch-zoom for accessibility - never locked.
  maximumScale: 5,
  userScalable: true,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
  colorScheme: "light dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      // The bootstrap script below sets the `dark` class before hydration,
      // based on a preference React's own server render can't know (it
      // lives in localStorage/the account's saved settings) - without this,
      // React would report a hydration mismatch on that one class.
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col">
        {/* Runs before any other JS (strategy="beforeInteractive" hoists it
            into <head> and blocks hydration until it's run), so the correct
            theme is applied before first paint instead of flashing the
            wrong one. Must stay a standalone, dependency-free script - see
            lib/theme.ts. */}
        <Script id="theme-bootstrap" strategy="beforeInteractive">
          {THEME_BOOTSTRAP_SCRIPT}
        </Script>
        <ThemeSync />
        <ServiceWorkerRegistration />
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
