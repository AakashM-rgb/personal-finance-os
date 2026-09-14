"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, apiRequest, readCookie } from "@/lib/api-client";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  email_verified_at: string | null;
  created_at: string;
}

interface AccessTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
}

interface LoginInput {
  email: string;
  password: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;
  register: (input: RegisterInput) => Promise<void>;
  login: (input: LoginInput) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const applySession = useCallback((result: AccessTokenResponse) => {
    setUser(result.user);
    setAccessToken(result.access_token);
  }, []);

  const clearSession = useCallback(() => {
    setUser(null);
    setAccessToken(null);
  }, []);

  // On first load, try a silent refresh using the httpOnly refresh cookie
  // (if one exists from a previous visit) to restore the session without
  // asking the user to log in again.
  useEffect(() => {
    let isMounted = true;

    async function restoreSession() {
      const csrfToken = readCookie("csrf_token");
      if (!csrfToken) {
        if (isMounted) setIsLoading(false);
        return;
      }
      try {
        const result = await apiRequest<AccessTokenResponse>("/api/v1/auth/refresh", {
          method: "POST",
          csrfToken,
        });
        if (isMounted) applySession(result);
      } catch {
        // No valid session to restore - stay logged out, silently.
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    void restoreSession();
    return () => {
      isMounted = false;
    };
  }, [applySession]);

  const register = useCallback(
    async (input: RegisterInput) => {
      const result = await apiRequest<AccessTokenResponse>("/api/v1/auth/register", {
        method: "POST",
        body: input,
      });
      applySession(result);
    },
    [applySession]
  );

  const login = useCallback(
    async (input: LoginInput) => {
      const result = await apiRequest<AccessTokenResponse>("/api/v1/auth/login", {
        method: "POST",
        body: input,
      });
      applySession(result);
    },
    [applySession]
  );

  const logout = useCallback(async () => {
    const csrfToken = readCookie("csrf_token");
    try {
      await apiRequest("/api/v1/auth/logout", { method: "POST", csrfToken });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, accessToken, isLoading, register, login, logout }),
    [user, accessToken, isLoading, register, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
