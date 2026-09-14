import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
      <Link
        href="/"
        className="mb-8 text-lg font-semibold text-zinc-900 dark:text-zinc-50"
      >
        Finance App
      </Link>
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}
