import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SyncStatusIndicator } from "@/components/nav/sync-status-indicator";
import type { OfflineSyncState } from "@/lib/offline/use-offline-sync";

function state(overrides: Partial<OfflineSyncState>): OfflineSyncState {
  return {
    queue: [],
    isOnline: true,
    pendingCount: 0,
    needsAttentionCount: 0,
    refresh: () => {},
    ...overrides,
  };
}

describe("SyncStatusIndicator", () => {
  it("renders nothing when everything is synced and online", () => {
    const { container } = render(<SyncStatusIndicator state={state({})} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows an offline indicator when offline, never implying data is current", () => {
    render(<SyncStatusIndicator state={state({ isOnline: false, pendingCount: 2 })} />);
    expect(screen.getByRole("status")).toHaveTextContent(/offline/i);
    expect(screen.getByRole("status")).toHaveTextContent("2");
  });

  it("shows a syncing indicator when online with pending items", () => {
    render(<SyncStatusIndicator state={state({ isOnline: true, pendingCount: 3 })} />);
    expect(screen.getByRole("status")).toHaveTextContent(/syncing/i);
  });

  it("shows a needs-attention indicator, taking priority over the offline/syncing state", () => {
    render(
      <SyncStatusIndicator
        state={state({ isOnline: false, pendingCount: 1, needsAttentionCount: 2 })}
      />
    );
    expect(screen.getByRole("status")).toHaveTextContent(/need.*attention/i);
  });
});
