import { apiRequest } from "@/lib/api-client";

export interface AssistantMessageInput {
  role: "user" | "assistant";
  content: string;
}

export interface ToolUsage {
  tool_name: string;
  ok: boolean;
}

export interface AssistantResponse {
  answer: string;
  tools_used: ToolUsage[];
  provider: string;
  disclaimer: string;
}

// Mirrors backend/app/schemas/ai.py's bounds - a client-side pre-check only;
// the backend re-validates and is the actual authority.
export const ASSISTANT_MAX_MESSAGE_LENGTH = 2000;

export const SUGGESTED_QUESTIONS = [
  "Where am I spending the most?",
  "How much did I spend this month?",
  "Compare this month with last month.",
  "What are my biggest recurring expenses?",
  "How much should I save each month?",
];

export async function askAssistant(
  accessToken: string,
  message: string,
  history: AssistantMessageInput[] = []
): Promise<AssistantResponse> {
  return apiRequest<AssistantResponse>("/api/v1/ai/assistant", {
    method: "POST",
    accessToken,
    body: { message, history },
  });
}
