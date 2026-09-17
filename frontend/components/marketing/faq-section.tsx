interface FaqItem {
  question: string;
  answer: string;
}

const FAQ_ITEMS: FaqItem[] = [
  {
    question: "What is Personal Finance OS?",
    answer:
      "A single system for your money - record transactions and accounts, track budgets and savings goals, and understand your spending, with an AI assistant and natural-language search built on top of your own data.",
  },
  {
    question: "Can I track transactions and accounts?",
    answer:
      "Yes. Record income, expenses, and transfers across multiple accounts - bank, cash, credit card, UPI, and wallet - with categories, tags, and fast quick-add entry.",
  },
  {
    question: "Can I create budgets and savings goals?",
    answer:
      "Yes. Set a monthly limit per category and track healthy/warning/near-limit/exceeded status with a month-end projection, and set savings goals with a target amount and date - the required monthly and weekly savings pace is calculated for you.",
  },
  {
    question: "Can I ask questions about my spending?",
    answer:
      "Yes, in two ways: natural-language search for specific requests like “food last month” or “transport expenses in August”, and an AI assistant for broader questions about your spending, budgets, and goals.",
  },
  {
    question: "Does the AI generate SQL?",
    answer:
      "No. The AI assistant and natural-language search never execute arbitrary or AI-generated SQL. Both work through a fixed set of read-only, validated tools scoped to your own account.",
  },
  {
    question: "Can I use the app offline?",
    answer:
      "Yes. You can add an expense with no connection - it's saved securely on your device and shown as pending until it syncs.",
  },
  {
    question: "How does offline expense sync work?",
    answer:
      "Once you're back online, pending expenses sync automatically. Each one carries a unique operation identifier, so a retried or repeated sync attempt can never create a duplicate transaction.",
  },
  {
    question: "Are my financial records isolated from other users?",
    answer:
      "Yes. Every request is scoped to your authenticated account at the data-access layer, so your accounts, transactions, and reports are never visible to another user.",
  },
  {
    question: "Can I manage recurring expenses and subscriptions?",
    answer:
      "Yes. Set up bills and income that repeat on a schedule, and track subscriptions separately to see what they cost you over time.",
  },
  {
    question: "Can I upload receipts?",
    answer:
      "Yes. Upload a receipt, review what was extracted from it, and confirm the details before they become a transaction - nothing is created automatically without your review.",
  },
];

export function FAQSection() {
  return (
    <section id="faq" className="mx-auto max-w-3xl px-6 py-20 sm:py-28">
      <div className="text-center">
        <p className="text-xs font-semibold tracking-[0.2em] text-zinc-500 uppercase dark:text-zinc-500">
          FAQ
        </p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl dark:text-zinc-50">
          Questions, answered.
        </h2>
      </div>

      <div className="mt-10 divide-y divide-zinc-100 dark:divide-zinc-800">
        {FAQ_ITEMS.map((item) => (
          <details key={item.question} className="group py-4">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-left font-medium text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:text-zinc-50 dark:focus-visible:ring-zinc-100 [&::-webkit-details-marker]:hidden">
              {item.question}
              <span
                className="shrink-0 text-xl text-zinc-400 transition-transform duration-200 group-open:rotate-45 dark:text-zinc-600"
                aria-hidden="true"
              >
                +
              </span>
            </summary>
            <p className="mt-3 pr-8 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
              {item.answer}
            </p>
          </details>
        ))}
      </div>
    </section>
  );
}
