import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LandingPage from "@/app/(marketing)/page";

describe("LandingPage", () => {
  it("renders the hero headline and primary/secondary CTAs", () => {
    render(<LandingPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /your finances\.[\s\S]*one intelligent system\./i
    );
    const getStartedLinks = screen.getAllByRole("link", { name: /get started/i });
    expect(getStartedLinks.some((link) => link.getAttribute("href") === "/register")).toBe(true);
  });

  it("Get started routes to the real registration page, not a fake/duplicate flow", () => {
    render(<LandingPage />);
    const links = screen.getAllByRole("link", { name: /get started/i });
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/register");
    }
  });

  it("Log in routes to the real login page", () => {
    render(<LandingPage />);
    const links = screen.getAllByRole("link", { name: /log in/i });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/login");
    }
  });

  it("renders every required section with a heading", () => {
    render(<LandingPage />);
    expect(screen.getByRole("heading", { name: /everything your money needs/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /ask your finances anything/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /see where your money actually goes/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /know your limits/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /give every goal a plan/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /your financial data should stay yours/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /questions, answered/i })).toBeInTheDocument();
  });

  it("has one and only one <h1>, preserving a correct heading hierarchy", () => {
    render(<LandingPage />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    // Every section heading is an <h2>, never skipping to h3+ at the top level.
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThanOrEqual(7);
  });

  it("anchor navigation links point at real section ids present on the page", () => {
    const { container } = render(<LandingPage />);
    const anchorLinks = screen.getAllByRole("link").filter((link) => {
      const href = link.getAttribute("href");
      return href?.startsWith("#");
    });
    expect(anchorLinks.length).toBeGreaterThan(0);
    for (const link of anchorLinks) {
      const id = link.getAttribute("href")!.slice(1);
      expect(container.querySelector(`#${id}`)).not.toBeNull();
    }
  });

  it("clearly labels the product preview and analytics preview as illustrative/example data", () => {
    render(<LandingPage />);
    expect(screen.getByLabelText(/illustrative product preview with example data/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/illustrative analytics preview with example data/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/illustrative budget preview with example data/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/illustrative savings goal preview with example data/i)).toBeInTheDocument();
    expect(screen.getByText(/illustrative example conversation/i)).toBeInTheDocument();
  });

  it("never presents illustrative content as a real testimonial, customer, or review", () => {
    render(<LandingPage />);
    const bodyText = document.body.textContent ?? "";
    for (const forbidden of [
      "customers love",
      "trusted by",
      "★★★★★",
      "5-star",
      "5 star",
      "verified customer",
      "our users say",
    ]) {
      expect(bodyText.toLowerCase()).not.toContain(forbidden.toLowerCase());
    }
  });

  it("never claims an unverified security certification", () => {
    render(<LandingPage />);
    const bodyText = (document.body.textContent ?? "").toLowerCase();
    for (const forbidden of [
      "soc 2",
      "soc2",
      "iso 27001",
      "bank-level",
      "bank level",
      "military-grade",
      "military grade",
      "zero-knowledge",
      "end-to-end encrypt",
    ]) {
      expect(bodyText).not.toContain(forbidden);
    }
  });

  it("FAQ section lists real product questions with a working disclosure widget", () => {
    render(<LandingPage />);
    const faqSection = document.getElementById("faq");
    expect(faqSection).not.toBeNull();
    const withinFaq = within(faqSection as HTMLElement);
    const sqlQuestion = withinFaq.getByText(/does the ai generate sql/i);
    const details = sqlQuestion.closest("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
  });

  it("footer contains no fabricated legal pages, address, or social links", () => {
    render(<LandingPage />);
    const footer = document.querySelector("footer");
    expect(footer).not.toBeNull();
    const footerText = (footer?.textContent ?? "").toLowerCase();
    for (const forbidden of ["privacy policy", "terms of service", "twitter", "linkedin", "instagram"]) {
      expect(footerText).not.toContain(forbidden);
    }
  });
});
