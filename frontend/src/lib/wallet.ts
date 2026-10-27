import type { useWallets } from "@mysten/dapp-kit";

export type SuiWallet = ReturnType<typeof useWallets>[number];
