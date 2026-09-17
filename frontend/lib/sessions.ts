import { apiRequest } from "@/lib/api-client";

export interface Session {
  id: string;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  expires_at: string;
}

export async function listSessions(accessToken: string): Promise<Session[]> {
  return apiRequest<Session[]>("/api/v1/auth/sessions", { accessToken });
}
