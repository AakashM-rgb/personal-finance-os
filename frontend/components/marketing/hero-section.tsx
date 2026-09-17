import Link from "next/link";

import { ProductPreview } from "@/components/marketing/product-preview";
import { Button } from "@/components/ui/button";

export function HeroSection() {
  return (
    <section className="mx-auto max-w-6xl px-6 pt-16 pb-20 sm:pt-24 sm:pb-28">
      <div className="mx-auto max-w-3xl text-center">
        <p className="text-xs font-semibold tracking-[0.2em] text-zinc-500 uppercase dark:text-zinc-500">
          Personal Finance OS
        </p>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight text-balance text-zinc-900 sm:text-5xl dark:text-zinc-50">
          Your finances.
          <br />
          One intelligent system.
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-lg text-pretty text-zinc-600 dark:text-zinc-400">
          Track spending, plan ahead, and understand your money - accounts, budgets, goals, and
          insights, all in one place.
        </p>

        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link href="/register" className="w-full sm:w-auto">
            <Button className="h-12 w-full px-8 text-base sm:w-auto">Get started</Button>
          </Link>
          <a href="#features" className="w-full sm:w-auto">
            <Button variant="secondary" className="h-12 w-full px-8 text-base sm:w-auto">
              See how it works
            </Button>
          </a>
        </div>

        <p className="mt-5 text-sm text-zinc-500 dark:text-zinc-500">
          Built around your data. Designed to keep it private.
        </p>
      </div>

      <div className="mt-16">
        <ProductPreview />
      </div>
    </section>
  );
}
