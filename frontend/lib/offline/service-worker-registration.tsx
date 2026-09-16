"use client";

import { useEffect } from "react";

/**
 * Registers the app-shell service worker (public/sw.js). Feature-detected
 * and fails silently - a browser without service worker support (or a
 * registration error) must never block the app from working online, it
 * simply won't get the offline shell.
 */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    void navigator.serviceWorker.register("/sw.js").catch(() => {
      // Offline shell is a progressive enhancement, not a requirement.
    });
  }, []);

  return null;
}
