import { useConnectWallet, useDisconnectWallet, useSignPersonalMessage } from "@mysten/dapp-kit";
import type { SuiWallet } from "./wallet";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, type Me } from "./api";

const STORAGE_KEY = "marketrecall.session";

type Stored = { token: string; address: string };

type Session = {
  token: string | null;
  me: Me | null;
  loading: boolean;
  signIn: (wallet: SuiWallet) => Promise<void>;
  signOut: () => void;
  refresh: () => Promise<void>;
};

const SessionContext = createContext<Session | null>(null);

function readStored(): Stored | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Stored) : null;
  } catch {
    return null;
  }
}

function writeStored(value: Stored | null) {
  try {
    if (value) localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode: session lasts for this tab only */
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readStored()?.token ?? null);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(Boolean(token));
  const { mutateAsync: connect } = useConnectWallet();
  const { mutateAsync: disconnect } = useDisconnectWallet();
  const { mutateAsync: signPersonalMessage } = useSignPersonalMessage();

  const signOut = useCallback(() => {
    const stored = readStored();
    if (stored) api.logout(stored.token).catch(() => undefined);
    writeStored(null);
    setToken(null);
    setMe(null);
    disconnect().catch(() => undefined);
  }, [disconnect]);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      setMe(await api.me(token));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) signOut();
    } finally {
      setLoading(false);
    }
  }, [token, signOut]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signIn = useCallback(
    async (wallet: SuiWallet) => {
      const { accounts } = await connect({ wallet });
      const account = accounts[0];
      if (!account) throw new Error("The wallet did not share an account.");
      const challenge = await api.challenge(account.address);
      const { signature } = await signPersonalMessage({
        message: new TextEncoder().encode(challenge.message),
        account,
      });
      const session = await api.login(account.address, challenge.nonce, signature);
      writeStored({ token: session.token, address: session.address });
      setToken(session.token);
      setMe(await api.me(session.token));
    },
    [connect, signPersonalMessage],
  );

  const value = useMemo(() => ({ token, me, loading, signIn, signOut, refresh }), [token, me, loading, signIn, signOut, refresh]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}
