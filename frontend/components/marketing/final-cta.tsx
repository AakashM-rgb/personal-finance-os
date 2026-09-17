import Link from "next/link";

import { Button } from "@/components/ui/button";

export function FinalCTA() {
  return (
    <section className="border-t border-zinc-100 dark:border-zinc-900">
      <div className="mx-auto max-w-3xl px-6 py-20 text-center sm:py-28">
        <h2 className="text-3xl font-semibold tracking-tight text-balance text-zinc-900 sm:text-4xl dark:text-zinc-50">
          Your money is already generating data.
          <br />
          Turn it into a system.
        </h2>
        <p className="mt-4 text-base text-zinc-600 dark:text-zinc-400">
          Track it. Understand it. Plan it.
        </p>

        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link href="/register" className="w-full sm:w-auto">
            <Button className="h-12 w-full px-8 text-base sm:w-auto">Get started</Button>
          </Link>
          <a href="#features" className="w-full sm:w-auto">
            <Button variant="secondary" className="h-12 w-full px-8 text-base sm:w-auto">
              Explore the product
            </Button>
          </a>
        </div>
      </div>
    </section>
  );
}
