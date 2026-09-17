import Link from "next/link";

const PRODUCT_LINKS = [
  { href: "#features", label: "Features" },
  { href: "#ai-assistant", label: "AI" },
  { href: "#analytics", label: "Analytics" },
  { href: "#privacy", label: "Privacy" },
  { href: "#faq", label: "FAQ" },
];

const ACCOUNT_LINKS = [
  { href: "/login", label: "Log in" },
  { href: "/register", label: "Get started" },
];

export function LandingFooter() {
  return (
    <footer className="border-t border-zinc-100 dark:border-zinc-900">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="grid grid-cols-1 gap-10 sm:grid-cols-3">
          <div>
            <Link href="/" className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
              Finance App
            </Link>
            <p className="mt-2 max-w-xs text-sm text-zinc-500 dark:text-zinc-400">
              Your personal financial operating system - accounts, budgets, goals, and insight,
              in one place.
            </p>
          </div>

          <div>
            <h3 className="text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-500">
              Product
            </h3>
            <ul className="mt-3 flex flex-col gap-2">
              {PRODUCT_LINKS.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-500">
              Account
            </h3>
            <ul className="mt-3 flex flex-col gap-2">
              {ACCOUNT_LINKS.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <p className="mt-10 border-t border-zinc-100 pt-6 text-xs text-zinc-500 dark:border-zinc-900 dark:text-zinc-500">
          © {new Date().getFullYear()} Finance App. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
