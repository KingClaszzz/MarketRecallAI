import { useWallets } from "@mysten/dapp-kit";
import { isEnokiWallet, isGoogleWallet } from "@mysten/enoki";
import type { SuiWallet } from "../lib/wallet";
import { useEffect, useState } from "react";
import { googleEnabled } from "../lib/enoki";
import { useSession } from "../lib/session";

export function SignInDialog({ open, onClose, onSignedIn }: { open: boolean; onClose: () => void; onSignedIn?: () => void }) {
  const wallets = useWallets();
  const { signIn } = useSession();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const google = wallets.find((w) => isEnokiWallet(w) && isGoogleWallet(w));
  const others = wallets.filter((w) => !isEnokiWallet(w));

  const go = async (wallet: SuiWallet) => {
    setBusy(wallet.name);
    setError(null);
    try {
      await signIn(wallet);
      onSignedIn?.();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/30 backdrop-blur-[2px] sm:items-center" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="signin-title"
        className="w-full max-w-[420px] rounded-t-[28px] bg-paper p-7 shadow-[0_30px_80px_rgba(0,0,0,0.18)] sm:rounded-[28px]"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <h2 id="signin-title" className="text-[24px] font-semibold tracking-[-0.02em]">Sign in</h2>
          <button onClick={onClose} aria-label="Close" className="-mr-2 -mt-1 rounded-full p-2 text-muted hover:bg-mist">
            <svg width="14" height="14" viewBox="0 0 14 14"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          </button>
        </div>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          You get 3 free credits every week. Signing in only asks for a signature: no gas, and no funds move.
        </p>

        <div className="mt-6 space-y-2.5">
          {google ? (
            <WalletRow name="Continue with Google" icon={google.icon} busy={busy === google.name} onClick={() => go(google)} primary />
          ) : (
            googleEnabled || (
              <div className="rounded-2xl border border-dashed border-hair px-4 py-3.5 text-[14px] text-muted">
                Google sign-in will be available soon.
              </div>
            )
          )}
          {others.map((w) => (
            <WalletRow key={w.name} name={w.name} icon={w.icon} busy={busy === w.name} onClick={() => go(w)} />
          ))}
          {others.length === 0 && (
            <a href="https://slush.app" target="_blank" rel="noreferrer"
              className="block rounded-2xl bg-mist px-4 py-3.5 text-[14px] text-ink-2 hover:bg-hair/60">
              No Sui wallet detected. Install Slush, then return to this page.
            </a>
          )}
        </div>

        {error && <p className="mt-4 rounded-xl bg-down-soft px-4 py-3 text-[14px] text-down">{error}</p>}
        <p className="mt-6 text-[12px] leading-relaxed text-faint">
          Your signature is verified on Sui through Tatum. Credits have no monetary value and cannot be purchased.
        </p>
      </div>
    </div>
  );
}

function WalletRow({ name, icon, busy, onClick, primary = false }: {
  name: string; icon: string; busy: boolean; onClick: () => void; primary?: boolean;
}) {
  return (
    <button onClick={onClick} disabled={busy}
      className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3.5 text-left text-[15px] font-medium transition-colors disabled:opacity-60 ${
        primary ? "bg-ink text-white hover:bg-ink-2" : "bg-mist text-ink hover:bg-hair/70"
      }`}>
      <img src={icon} alt="" className="h-7 w-7 rounded-lg" />
      <span className="flex-1">{name}</span>
      {busy ? <span className="text-[13px] opacity-70">Confirm in your wallet…</span> : <Chevron />}
    </button>
  );
}

const Chevron = () => (
  <svg width="8" height="13" viewBox="0 0 8 13" className="opacity-50"><path d="M1.5 1.5l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
);
