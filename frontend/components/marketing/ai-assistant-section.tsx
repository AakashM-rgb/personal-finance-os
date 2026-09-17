import { ChatMessageBubble } from "@/components/ai/chat-message-bubble";
import { Card } from "@/components/ui/card";
import { demoConversation } from "@/components/marketing/demo-data";

const CAPABILITIES = [
  "Monthly and category spending",
  "Transaction search",
  "Budget status",
  "Savings goal progress",
  "Recurring expenses",
  "Account balances",
  "Period comparisons",
];

export function AIAssistantSection() {
  return (
    <section id="ai-assistant" className="border-t border-zinc-100 dark:border-zinc-900">
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-12 px-6 py-20 sm:py-28 lg:grid-cols-2 lg:items-center lg:gap-16">
        <div>
          <p className="text-xs font-semibold tracking-[0.2em] text-zinc-500 uppercase dark:text-zinc-500">
            AI Assistant
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl dark:text-zinc-50">
            Ask your finances anything.
          </h2>
          <p className="mt-4 text-base text-zinc-600 dark:text-zinc-400">
            The assistant answers using a fixed set of tools that read your own real transactions,
            budgets, and goals - never a free-form database query, and never another user&apos;s
            data.
          </p>

          <ul className="mt-6 grid grid-cols-2 gap-x-4 gap-y-2">
            {CAPABILITIES.map((capability) => (
              <li key={capability} className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-emerald-600 dark:bg-emerald-500" aria-hidden="true" />
                {capability}
              </li>
            ))}
          </ul>

          <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-500">
            Not licensed financial advice - answers are grounded in your own recorded data, never
            invented.
          </p>
        </div>

        <Card className="flex flex-col gap-3 p-5 sm:p-6">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Illustrative example conversation
            </span>
          </div>
          <div className="flex flex-col gap-3">
            {demoConversation.map((turn, index) => (
              <ChatMessageBubble key={index} role={turn.role} content={turn.content} />
            ))}
          </div>
        </Card>
      </div>
    </section>
  );
}
