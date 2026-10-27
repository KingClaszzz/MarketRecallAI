import { registerEnokiWallets } from "@mysten/enoki";
import { SuiGrpcClient } from "@mysten/sui/grpc";

const apiKey = import.meta.env.VITE_ENOKI_API_KEY;
const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

/** Google sign-in needs both keys. */
export const googleEnabled = Boolean(apiKey && googleClientId);

export function registerGoogleWallet() {
  if (!googleEnabled) return;
  registerEnokiWallets({
    apiKey: apiKey!,
    providers: { google: { clientId: googleClientId! } },
    client: new SuiGrpcClient({ network: "mainnet", baseUrl: "https://fullnode.mainnet.sui.io:443" }),
    network: "mainnet",
  });
}
