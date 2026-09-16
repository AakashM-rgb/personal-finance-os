import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement scrollIntoView - stub it so components that call
// it (e.g. auto-scrolling a chat/log view) don't crash under test.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
