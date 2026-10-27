import { createNetworkConfig, SuiClientProvider, WalletProvider } from "@mysten/dapp-kit";
import "@mysten/dapp-kit/dist/index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { registerGoogleWallet } from "./lib/enoki";
import { SessionProvider } from "./lib/session";
import Dashboard from "./pages/Dashboard";
import Landing from "./pages/Landing";

registerGoogleWallet();

const { networkConfig } = createNetworkConfig({ mainnet: { url: "https://fullnode.mainnet.sui.io:443", network: "mainnet" } });
const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SuiClientProvider networks={networkConfig} defaultNetwork="mainnet">
        <WalletProvider autoConnect slushWallet={{ name: "MarketRecall" }}>
          <SessionProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<Landing />} />
                <Route path="/app" element={<Dashboard />} />
              </Routes>
            </BrowserRouter>
          </SessionProvider>
        </WalletProvider>
      </SuiClientProvider>
    </QueryClientProvider>
  </StrictMode>,
);
