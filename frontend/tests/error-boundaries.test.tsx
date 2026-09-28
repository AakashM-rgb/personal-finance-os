import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AppError from "@/app/(app)/error";
import RootError from "@/app/error";
import NotFound from "@/app/not-found";
import { ErrorFallback } from "@/components/ui/error-fallback";

const SENSITIVE_MESSAGE = "Cannot read properties of undefined (reading 'amount_minor')";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ErrorFallback", () => {
  it("renders an accessible alert with a retry action and a way out", () => {
    const onRetry = vi.fn();
    render(
      <ErrorFallback
        title="Oops"
        message="Please try again."
        onRetry={onRetry}
        homeHref="/dashboard"
        homeLabel="Go to dashboard"
      />
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Please try again.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Go to dashboard" })).toHaveAttribute(
      "href",
      "/dashboard"
    );
  });

  it("shows the digest reference only when one is provided", () => {
    const props = {
      title: "Oops",
      message: "Please try again.",
      onRetry: () => {},
      homeHref: "/",
      homeLabel: "Home",
    };
    const { rerender } = render(<ErrorFallback {...props} />);
    expect(screen.queryByText(/Reference:/)).not.toBeInTheDocument();

    rerender(<ErrorFallback {...props} digest="abc123" />);
    expect(screen.getByText("Reference: abc123")).toBeInTheDocument();
  });
});

describe.each([
  ["app/(app)/error.tsx", AppError, "/dashboard"],
  ["app/error.tsx", RootError, "/"],
])("%s", (_name, Boundary, homeHref) => {
  it("never shows the raw error message to the user", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<Boundary error={new Error(SENSITIVE_MESSAGE)} retry={() => {}} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(SENSITIVE_MESSAGE, "i"))).not.toBeInTheDocument();
  });

  it("calls retry when the user clicks Try again", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const retry = vi.fn();
    render(<Boundary error={new Error("boom")} retry={retry} />);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("logs the error for debugging and links back to a safe page", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const error = new Error("boom");
    render(<Boundary error={error} retry={() => {}} />);

    expect(consoleError).toHaveBeenCalledWith(error);
    expect(
      screen.getAllByRole("link").some((link) => link.getAttribute("href") === homeHref)
    ).toBe(true);
  });
});

describe("NotFound", () => {
  it("explains the page is missing and offers navigation", () => {
    render(<NotFound />);
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to dashboard" })).toHaveAttribute(
      "href",
      "/dashboard"
    );
  });
});
