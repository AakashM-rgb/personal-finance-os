import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function LandingPage() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between px-6 py-4 sm:px-12">
        <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Finance App</span>
        <nav className="flex items-center gap-3">
          <Link
            href="/login"
            className="text-sm font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
          >
            Log in
          </Link>
          <Link href="/register">
            <Button>Start Tracking Free</Button>
          </Link>
        </nav>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-zinc-900 sm:text-5xl dark:text-zinc-50">
          Know where your money goes.
        </h1>
        <p className="mt-4 max-w-xl text-lg text-zinc-600 dark:text-zinc-400">
          Track spending, plan your future, and make smarter financial decisions.
        </p>
        <Link href="/register" className="mt-8">
          <Button className="h-12 px-8 text-base">Start Tracking Free</Button>
        </Link>
      </main>
    </div>
  );
}
