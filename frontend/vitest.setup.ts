import "@testing-library/jest-dom/vitest";
// jsdom has no IndexedDB implementation - polyfill it for the offline
// drafts/sync-queue tests (lib/offline/*).
import "fake-indexeddb/auto";

// jsdom doesn't implement scrollIntoView - stub it so components that call
// it (e.g. auto-scrolling a chat/log view) don't crash under test.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
