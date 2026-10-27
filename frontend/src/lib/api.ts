const BASE = import.meta.env.VITE_API_BASE ?? "";

export type Asset = "SUI" | "WAL" | "CETUS";
export const ASSETS: Asset[] = ["SUI", "WAL", "CETUS"];
export const ASSET_NAMES: Record<Asset, string> = { SUI: "Sui", WAL: "Walrus", CETUS: "Cetus" };

export type Regime = { vol: string; trend: string; chain: string; session: string };

export type Credibility = { n: number; bss: number; brier: number; avg_p: number; freq_up: number };

export type Decision = {
  action: "BASELINE" | "ADJUSTED" | "NO_CALL";
  voice: string;
  p_raw: number;
  p: number;
  alpha: number;
  level: string | null;
  n_matched: number;
  credibility: Record<string, Credibility>;
  reasons: string[];
};

export type Evidence = { blob_id: string; distance: number; text: string };

export type Forecast = {
  id: number;
  asset: Asset;
  t: number;
  horizon_h: number;
  close_at_t: number;
  voices: Record<string, number>;
  regime: Regime;
  amnesiac_p: number;
  recall_p: number;
  recall_action: Decision["action"];
  status: "PENDING" | "RESOLVED" | "UNRESOLVABLE";
  label: number | null;
  close_at_resolve: number | null;
  amnesiac_brier: number | null;
  recall_brier: number | null;
  trace: {
    decision: Decision;
    explanation?: { text: string; by: "llm" | "template" };
    evidence?: { query: string; credibility?: Evidence[]; episodes?: Evidence[] };
    book_episodes?: number;
  };
};

export type Candle = { open_time: number; close: number; high: number; low: number; volume: number };
export type Onchain = { hour_ts: number; total_tx: number; epoch: number; checkpoint_seq: number; reference_gas_price: number | null };
export type Memory = {
  id: number;
  ts: string;
  namespace: string;
  kind: string;
  text: string;
  status: string;
  blob_id: string | null;
  blob_url: string | null;
  ref: Record<string, unknown>;
};
export type Lesson = { id: number; asset: Asset; rule: string; status: string; statement: string; evidence: Record<string, unknown> };
export type Stats = {
  memories_stored: number;
  memories_by_kind: Record<string, number>;
  forecasts: Record<string, number>;
  episodes_learned: number;
  users: number;
  calls: number;
  sessions: number;
};
export type RacePoint = { t: number; asset: Asset; amnesiac: number; recall: number; action: string };
export type Direction = "UP" | "DOWN";
export type Mode = "own" | "model";
export type Pick = {
  id: number;
  asset: Asset;
  slot_t: number;
  direction: Direction;
  status: "PENDING" | "WON" | "LOST" | "REFUNDED";
  mode: Mode;
  session_id: number | null;
  model_p: number | null;
  model_action: string | null;
  agrees_with_model: boolean | null;
  close_at_t: number | null;
  close_at_resolve: number | null;
};
export type CreditEntry = { id: number; ts: string; delta: number; balance: number; reason: string; ref: Record<string, unknown> };
export type Me = {
  address: string;
  credits: number;
  week: string;
  cap: number;
  weekly_floor: number;
  next_slot: number;
  ledger: CreditEntry[];
  picks: Pick[];
  memory_namespace: string;
  session_cost: number;
  call_reward: number;
  questions_per_session: number;
};
export type Record_ = {
  calls: number;
  right: number;
  agreed_calls: number;
  agreed_right: number;
  disagreed_calls: number;
  disagreed_right: number;
};
export type PersonalRecord = {
  total: Record_;
  by_volatility: Record<string, Record_>;
  by_mode: Partial<Record<Mode, Record_>>;
  memory_blobs: string[];
};
export type Driver = { feature: string; pushes: Direction; weight: number };
export type MarketContext = {
  price_at_reading?: number;
  move_1h_pct?: number | null;
  move_4h_pct?: number | null;
  move_24h_pct?: number | null;
  move_7d_pct?: number | null;
  volatility_rank_30d_pct?: number | null;
  rsi_14?: number | null;
  sui_activity_vs_week_z?: number | null;
  drivers?: Driver[];
  error?: string;
};
export type PredictSession = {
  id: number;
  asset: Asset;
  mode: Mode;
  created_at: string;
  expires_at: string;
  slot_t: number;
  forecast_id: number;
  pick_id: number | null;
  messages_used: number;
  max_messages: number;
  context: MarketContext;
};
export type ChatMessage = { id: number; ts: string; role: "user" | "assistant"; text: string; by: string | null };
export type SessionView = {
  session: PredictSession;
  forecast: Forecast | null;
  window_forecast: Forecast | null;
  pick: Pick | null;
  messages: ChatMessage[];
  questions_left: number;
  can_call: boolean;
  active: boolean;
  credits?: number;
};
export type Leaderboard = { users: { address: string; calls: number; right: number; hit_rate: number }[] };

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(BASE + path, { ...init, headers: { ...headers, ...(init.headers as object) } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown, token?: string | null) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) }, token);

export const api = {
  live: () => request<{ forecasts: Record<Asset, Forecast | null>; rules: Record<Asset, Record<string, string>> }>("/api/live"),
  stats: () => request<Stats>("/api/stats"),
  race: (asset?: Asset) => request<{ n: number; series: RacePoint[]; coin_flip: number }>(`/api/race${asset ? `?asset=${asset}` : ""}`),
  candles: (asset: Asset, limit = 72) => request<Candle[]>(`/api/candles?asset=${asset}&limit=${limit}`),
  onchain: (limit = 25) => request<Onchain[]>(`/api/onchain?limit=${limit}`),
  memories: (limit = 12) => request<Memory[]>(`/api/memories?limit=${limit}`),
  lessons: (asset?: Asset) => request<Lesson[]>(`/api/lessons${asset ? `?asset=${asset}` : ""}`),
  forecasts: (asset: Asset, limit = 24) => request<Forecast[]>(`/api/forecasts?asset=${asset}&limit=${limit}`),
  leaderboard: () => request<Leaderboard>("/api/leaderboard"),

  challenge: (address: string) => post<{ nonce: string; message: string }>("/api/auth/challenge", { address }),
  login: (address: string, nonce: string, signature: string) =>
    post<{ token: string; address: string; credits: number; expires_at: string }>("/api/auth/login", { address, nonce, signature }),
  logout: (token: string) => post<{ ok: boolean }>("/api/auth/logout", {}, token),
  me: (token: string) => request<Me>("/api/me", {}, token),
  record: (token: string, asset?: Asset) => request<PersonalRecord>(`/api/me/record${asset ? `?asset=${asset}` : ""}`, {}, token),
  sessions: (token: string) => request<{ session: PredictSession; pick: Pick | null }[]>("/api/sessions", {}, token),
  session: (token: string, id: number) => request<SessionView>(`/api/sessions/${id}`, {}, token),
  openSession: (token: string, asset: Asset, mode: Mode, direction?: Direction) =>
    post<SessionView>("/api/sessions", { asset, mode, direction }, token),
  lockCall: (token: string, id: number, direction: Direction) => post<SessionView>(`/api/sessions/${id}/call`, { direction }, token),
  ask: (token: string, id: number, text: string) =>
    post<{ answer: ChatMessage; questions_left: number }>(`/api/sessions/${id}/messages`, { text }, token),

  guide: (text: string, history: { role: "user" | "assistant"; text: string }[]) =>
    post<{ text: string; by: string; left: number }>("/api/guide", { text, history }),
};
