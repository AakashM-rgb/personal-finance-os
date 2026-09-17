import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LandingNav } from "@/components/marketing/landing-nav";

afterEach(() => {
  Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
});

describe("LandingNav", () => {
  it("renders the wordmark, section links, and auth links", () => {
    render(<LandingNav />);
    expect(screen.getByRole("link", { name: "Finance App" })).toHaveAttribute("href", "/");
    expect(screen.getAllByRole("link", { name: "Features" })[0]).toHaveAttribute("href", "#features");
    expect(screen.getAllByRole("link", { name: "Log in" })[0]).toHaveAttribute("href", "/login");
    expect(screen.getAllByRole("link", { name: "Get started" })[0]).toHaveAttribute("href", "/register");
  });

  it("mobile menu is closed by default and opens on toggle, with correct aria-expanded state", () => {
    render(<LandingNav />);
    const toggle = screen.getByRole("button", { name: /open menu/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation", { name: "Section" })).toBeTruthy(); // desktop nav always in DOM

    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: /close menu/i })).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById("mobile-nav-menu")).toBeInTheDocument();
  });

  it("closing the mobile menu removes it from the DOM", () => {
    render(<LandingNav />);
    fireEvent.click(screen.getByRole("button", { name: /open menu/i }));
    expect(document.getElementById("mobile-nav-menu")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close menu/i }));
    expect(document.getElementById("mobile-nav-menu")).not.toBeInTheDocument();
  });

  it("clicking a link inside the open mobile menu closes it", () => {
    render(<LandingNav />);
    fireEvent.click(screen.getByRole("button", { name: /open menu/i }));
    const mobileMenu = document.getElementById("mobile-nav-menu") as HTMLElement;
    const featuresLink = within(mobileMenu).getByRole("link", { name: "Features" });

    fireEvent.click(featuresLink);
    expect(document.getElementById("mobile-nav-menu")).not.toBeInTheDocument();
  });

  it("applies a background/border once the page scrolls, and removes it back at the top", () => {
    render(<LandingNav />);
    const header = document.querySelector("header") as HTMLElement;
    expect(header.className).toContain("bg-transparent");

    Object.defineProperty(window, "scrollY", { value: 40, configurable: true });
    fireEvent.scroll(window);
    expect(header.className).toContain("backdrop-blur-md");

    Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
    fireEvent.scroll(window);
    expect(header.className).toContain("bg-transparent");
  });
});
