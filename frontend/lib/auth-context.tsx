"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ApiError, apiRequest, readCookie, setSessionRefresher } from "@/lib/api-client";
import { waitForBackend } from "@/lib/backend-readiness";
import { getSettings } from "@/lib/settings";
import { applyTheme, isValidThemePreference, storeTheme } from "@/lib/theme";

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

export interface ChangePasswordInput {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;
  /** True once a signed-in session was lost because it could no longer be
   * refreshed (not after an explicit logout) - lets the login page explain
   * why the user is there. Cleared by the next successful sign-in. */
  sessionExpired: boolean;
  /** Why a stored session hasn't been restored yet, when it isn't the
   * session's fault: "waking" while a slow backend is still starting up,
   * "unreachable" once it couldn't be reached at all. Never set for a session
   * the server actually rejected - that one just signs out. */
  connectionIssue: ConnectionIssue | null;
  retrySessionRestore: () => void;
  register: (input: RegisterInput) => Promise<void>;
  login: (input: LoginInput) => Promise<void>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  /** Revokes every session server-side, then adopts the fresh session the
   * backend issues for this device - the caller stays signed in. */
  changePassword: (input: ChangePasswordInput) => Promise<void>;
}

export type ConnectionIssue = "waking" | "unreachable";

const AuthContext = createContext<AuthContextValue | null>(null);

/** A warm restore takes well under a second; past this, say why it's slow. */
const SLOW_RESTORE_HINT_MS = 3_000;

let inFlightRefresh: Promise<AccessTokenResponse | null> | null = null;
let inFlightRestore: Promise<AccessTokenResponse | null> | null = null;

/**
 * Exchanges the httpOnly refresh cookie for a new access token. Single-flight
 * at module scope: refresh tokens rotate and the backend revokes EVERY session
 * when a rotated-out token is reused, so two overlapping refreshes (concurrent
 * 401s, or React Strict Mode running the mount effect twice) must share one
 * request. Resolves null only when the backend itself answers 401 - the one
 * response that proves there is no session to recover. Everything else
 * (offline, a proxy timeout while the backend wakes up, a 5xx, a 429) says
 * nothing about the session, so it rejects and the caller keeps what it has.
 */
export function refreshAccessToken(): Promise<AccessTokenResponse | null> {
  if (inFlightRefresh) return inFlightRefresh;

  const csrfToken = readCookie("csrf_token");
  if (!csrfToken) return Promise.resolve(null);

  inFlightRefresh = apiRequest<AccessTokenResponse>("/api/v1/auth/refresh", {
    method: "POST",
    csrfToken,
  })
    .catch((error: unknown) => {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    })
    .finally(() => {
      inFlightRefresh = null;
    });
  return inFlightRefresh;
}

/**
 * Restores a stored session on page load: waits until the backend answers
 * its (side-effect free) health check, then refreshes exactly once.
 *
 * The refresh is never retried automatically. If an earlier attempt's
 * response was lost in transit (e.g. a proxy timed out while a cold backend
 * was still processing it), the server already rotated the token; sending the
 * old one again would look like token theft and revoke every session. Waiting
 * on health first means the one refresh only goes to a backend that is awake.
 * Rejects when the backend can't be reached, or the refresh fails without a
 * definite answer - the caller shows that, rather than signing the user out.
 */
export function restoreSession(): Promise<AccessTokenResponse | null> {
  if (inFlightRestore) return inFlightRestore;
  if (!readCookie("csrf_token")) return Promise.resolve(null);

  inFlightRestore = (async () => {
    if (!(await waitForBackend())) {
      throw new Error("The server could not be reached.");
    }
    return refreshAccessToken();
  })().finally(() => {
    inFlightRestore = null;
  });
  return inFlightRestore;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [connectionIssue, setConnectionIssue] = useState<ConnectionIssue | null>(null);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  // Read by the session refresher outside React's render cycle.
  const accessTokenRef = useRef<string | null>(null);

  const setToken = useCallback((token: string | null) => {
    accessTokenRef.current = token;
    setAccessToken(token);
  }, []);

  const applySession = useCallback(
    (result: AccessTokenResponse) => {
      setUser(result.user);
      setToken(result.access_token);
      setSessionExpired(false);
      setConnectionIssue(null);

      // Reconcile the locally-cached theme with the account's real saved
      // preference the moment we know who's signed in - e.g. logging in on a
      // new device/browser must show the user's own theme, not just whatever
      // the beforeInteractive script guessed from an empty localStorage.
      // Best-effort: a failure here must never block sign-in.
      void getSettings(result.access_token)
        .then((settings) => {
          if (isValidThemePreference(settings.theme)) {
            storeTheme(settings.theme);
            applyTheme(settings.theme);
          }
        })
        .catch(() => {});
    },
    [setToken]
  );

  const clearSession = useCallback(() => {
    setUser(null);
    setToken(null);
  }, [setToken]);

  // Lets api-client recover from a 401 mid-session: refresh once, then retry.
  useEffect(() => {
    setSessionRefresher(async (failedAccessToken) => {
      // Signed out meanwhile - never resurrect the session from a stale request.
      if (accessTokenRef.current === null) return null;
      // Another request already refreshed; just retry with the current token.
      if (accessTokenRef.current !== failedAccessToken) return accessTokenRef.current;

      const result = await refreshAccessToken();
      if (result) {
        setUser(result.user);
        setToken(result.access_token);
        return result.access_token;
      }
      if (accessTokenRef.current !== null) {
        clearSession();
        setSessionExpired(true);
      }
      return null;
    });
    return () => setSessionRefresher(null);
  }, [clearSession, setToken]);

  // On first load (and on an explicit retry), try a silent refresh using the
  // httpOnly refresh cookie (if one exists from a previous visit) to restore
  // the session without asking the user to log in again.
  useEffect(() => {
    let isMounted = true;
    const slowHint = setTimeout(() => {
      if (isMounted) setConnectionIssue("waking");
    }, SLOW_RESTORE_HINT_MS);

    restoreSession()
      .then((result) => {
        if (!isMounted) return;
        setConnectionIssue(null);
        if (result) applySession(result);
      })
      .catch(() => {
        // No definite answer about the session - never treat that as signed
        // out, which would send the user to the login page for nothing.
        if (isMounted) setConnectionIssue("unreachable");
      })
      .finally(() => {
        clearTimeout(slowHint);
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
      clearTimeout(slowHint);
    };
  }, [applySession, restoreAttempt]);

  const retrySessionRestore = useCallback(() => {
    setIsLoading(true);
    setConnectionIssue(null);
    setRestoreAttempt((attempt) => attempt + 1);
  }, []);

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

  // Revokes every session for this account, including the one making this
  // request - there is no "except this device" variant on the backend (see
  // app.services.auth_service.logout_all), so the caller is always signed
  // out here too.
  const logoutAll = useCallback(async () => {
    try {
      await apiRequest("/api/v1/auth/logout-all", { method: "POST", accessToken });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
    } finally {
      clearSession();
    }
  }, [accessToken, clearSession]);

  const changePassword = useCallback(
    async (input: ChangePasswordInput) => {
      const result = await apiRequest<AccessTokenResponse>("/api/v1/auth/change-password", {
        method: "POST",
        body: input,
        accessToken,
      });
      setUser(result.user);
      setToken(result.access_token);
    },
    [accessToken, setToken]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      accessToken,
      isLoading,
      sessionExpired,
      connectionIssue,
      retrySessionRestore,
      register,
      login,
      logout,
      logoutAll,
      changePassword,
    }),
    [
      user,
      accessToken,
      isLoading,
      sessionExpired,
      connectionIssue,
      retrySessionRestore,
      register,
      login,
      logout,
      logoutAll,
      changePassword,
    ]
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
