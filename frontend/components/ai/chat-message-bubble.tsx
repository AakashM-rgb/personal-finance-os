import { cn } from "@/lib/utils";

// Labels the assistant's own answers use (see backend/app/services/
// ai_assistant_service.py's system prompt and app/ai/provider/mock.py) to
// separate what the data shows from what was calculated, assumed, or
// estimated - rendered distinctly here so a decision-oriented answer never
// reads as one undifferentiated block of text. The label may carry a
// parenthetical aside before its colon (e.g. "Estimate (a general
// guideline):"), so this matches everything up to the first colon, not
// just the bare word.
const LABEL_RE = /^(Fact|Assumptions|Calculation|Estimate|Limitations|Context)\b[^:]*:/;

function renderLine(line: string, key: number) {
  const trimmed = line.trim();
  if (!trimmed) return null;

  const match = trimmed.match(LABEL_RE);
  if (match) {
    const label = match[0];
    return (
      <p key={key} className="mt-2 first:mt-0">
        <span className="font-semibold text-zinc-900 dark:text-zinc-50">{label}</span>
        {trimmed.slice(label.length)}
      </p>
    );
  }

  if (trimmed.startsWith("- ")) {
    return (
      <p key={key} className="mt-1 pl-3 first:mt-0">
        {trimmed}
      </p>
    );
  }

  return (
    <p key={key} className="mt-2 first:mt-0">
      {trimmed}
    </p>
  );
}

interface ChatMessageBubbleProps {
  role: "user" | "assistant";
  content: string;
}

export function ChatMessageBubble({ role, content }: ChatMessageBubbleProps) {
  const isUser = role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed sm:max-w-[75%]",
          isUser
            ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
            : "border border-zinc-200 bg-white text-zinc-900 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-50"
        )}
      >
        {isUser ? <p>{content}</p> : content.split("\n").map((line, i) => renderLine(line, i))}
      </div>
    </div>
  );
}
