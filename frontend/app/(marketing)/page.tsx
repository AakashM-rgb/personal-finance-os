import type { Metadata } from "next";

import { AIAssistantSection } from "@/components/marketing/ai-assistant-section";
import { AnalyticsSection } from "@/components/marketing/analytics-section";
import { BudgetSection } from "@/components/marketing/budget-section";
import { FAQSection } from "@/components/marketing/faq-section";
import { FeatureGrid } from "@/components/marketing/feature-grid";
import { FinalCTA } from "@/components/marketing/final-cta";
import { HeroSection } from "@/components/marketing/hero-section";
import { LandingFooter } from "@/components/marketing/landing-footer";
import { LandingNav } from "@/components/marketing/landing-nav";
import { PrivacySection } from "@/components/marketing/privacy-section";
import { SavingsGoalsSection } from "@/components/marketing/savings-goals-section";

const TITLE = "Personal Finance OS — Your finances, one intelligent system";
const DESCRIPTION =
  "Track transactions and accounts, budget by category, plan savings goals, and understand your spending - with an AI assistant and natural-language search built on your own real data.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: "/" },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    type: "website",
    url: "/",
  },
  twitter: {
    card: "summary",
    title: TITLE,
    description: DESCRIPTION,
  },
};

export default function LandingPage() {
  return (
    <div className="flex flex-1 flex-col">
      <LandingNav />
      <main>
        <HeroSection />
        <FeatureGrid />
        <AIAssistantSection />
        <AnalyticsSection />
        <BudgetSection />
        <SavingsGoalsSection />
        <PrivacySection />
        <FAQSection />
        <FinalCTA />
      </main>
      <LandingFooter />
    </div>
  );
}
