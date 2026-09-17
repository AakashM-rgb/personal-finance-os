"use client";

import { useEffect, useRef, useState } from "react";

import { ChatInput } from "@/components/ai/chat-input";
import { ChatMessageBubble } from "@/components/ai/chat-message-bubble";
import { SuggestedQuestions } from "@/components/ai/suggested-questions";
import { ApiError } from "@/lib/api-client";
import { askAssistant, type AssistantMessageInput } from "@/lib/ai";
import { useAuth } from "@/lib/auth-context";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

function makeId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

export default function AiAssistantPage() {
  const { accessToken } = useAuth();
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const [providerLabel, setProviderLabel] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  async function handleSend(text: string) {
    if (!accessToken) return;
    setError(null);

    const history: AssistantMessageInput[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));
    setMessages((prev) => [...prev, { id: makeId(), role: "user", content: text }]);
    setIsLoading(true);

    try {
      const response = await askAssistant(accessToken, text, history);
      setMessages((prev) => [
        ...prev,
        { id: makeId(), role: "assistant", content: response.answer },
      ]);
      setDisclaimer(response.disclaimer);
      setProviderLabel(response.provider);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "The assistant couldn't respond. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-4 sm:h-[calc(100vh-6rem)]">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          Financial Assistant
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Ask about your real spending, budgets, goals, and recurring expenses.
          {providerLabel === "mock" && " (Demo mode: no external AI provider is configured.)"}
        </p>
      </div>

      <div
        className="flex flex-1 flex-col gap-3 overflow-y-auto rounded-xl border border-zinc-200 bg-zinc-50/50 p-4 dark:border-zinc-800 dark:bg-zinc-900/30"
        aria-live="polite"
      >
        {messages.length === 0 && !isLoading && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Ask a question about your finances to get started.
            </p>
            <SuggestedQuestions onSelect={handleSend} disabled={isLoading} />
          </div>
        )}

        {messages.map((message) => (
          <ChatMessageBubble key={message.id} role={message.role} content={message.content} />
        ))}

        {isLoading && (
          <div
            className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400"
            role="status"
          >
            <span className="h-2 w-2 animate-pulse rounded-full bg-zinc-400" aria-hidden="true" />
            Analyzing your financial data…
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400"
        >
          {error}
        </div>
      )}

      {messages.length > 0 && <SuggestedQuestions onSelect={handleSend} disabled={isLoading} />}

      <ChatInput onSend={handleSend} isLoading={isLoading} />

      {disclaimer && (
        // Same text-zinc-400-on-white combination measured at 2.62:1 on the
        // categories page's "Default" label (verified with axe-core, well
        // under WCAG AA's 4.5:1) - this disclaimer only renders after the
        // first reply, so the automated scan didn't independently visit it,
        // but the color math is identical regardless of page.
        <p className="text-center text-xs text-zinc-600 dark:text-zinc-500">{disclaimer}</p>
      )}
    </div>
  );
}
