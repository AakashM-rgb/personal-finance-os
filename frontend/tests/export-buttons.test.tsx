import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ExportButtons } from "@/components/reports/export-buttons";

describe("ExportButtons", () => {
  it("renders a button for each export format", () => {
    render(<ExportButtons onExport={vi.fn().mockResolvedValue(undefined)} />);
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export Excel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export PDF" })).toBeInTheDocument();
  });

  it("calls onExport with the matching format when clicked", async () => {
    const onExport = vi.fn().mockResolvedValue(undefined);
    render(<ExportButtons onExport={onExport} />);
    fireEvent.click(screen.getByRole("button", { name: "Export Excel" }));
    await waitFor(() => expect(onExport).toHaveBeenCalledWith("xlsx"));
  });

  it("disables the other buttons while one export is in flight", async () => {
    let resolveExport: () => void = () => {};
    const onExport = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveExport = resolve;
        })
    );
    render(<ExportButtons onExport={onExport} />);
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(screen.getByRole("button", { name: "Export Excel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Export PDF" })).toBeDisabled();

    resolveExport();
    await waitFor(() => expect(screen.getByRole("button", { name: "Export Excel" })).not.toBeDisabled());
  });

  it("shows an error message when the export fails", async () => {
    const onExport = vi.fn().mockRejectedValue(new Error("boom"));
    render(<ExportButtons onExport={onExport} />);
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    await waitFor(() =>
      expect(screen.getByText("Failed to generate the export. Please try again.")).toBeInTheDocument()
    );
  });
});
