"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { ASSISTANT_MAX_MESSAGE_LENGTH } from "@/lib/ai";

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
}

export function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [value, setValue] = useState("");

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setValue("");
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2">
      <label htmlFor="assistant-message" className="sr-only">
        Ask the financial assistant a question
      </label>
      <textarea
        id="assistant-message"
        value={value}
        onChange={(e) => setValue(e.target.value.slice(0, ASSISTANT_MAX_MESSAGE_LENGTH))}
        onKeyDown={handleKeyDown}
        rows={2}
        placeholder="Ask about your spending, budgets, goals..."
        disabled={isLoading}
        className="h-16 w-full flex-1 resize-none rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      />
      <Button type="submit" isLoading={isLoading} disabled={!value.trim()}>
        Send
      </Button>
    </form>
  );
}
