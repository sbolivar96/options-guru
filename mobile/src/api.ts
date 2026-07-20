import { API_URL } from "./config";

// ── Response types (mirror backend/main.py) ──────────────────────────────────
export type Flag = "c" | "p";
export type Timeframe = "5d" | "1m" | "3m";

export interface StockInfo {
  ticker: string;
  name: string;
  price: number;
  sector: string;
  sector_etf: string;
  risk_free_rate: number;
  drift: number | null;
}

export interface ChainRow {
  strike: number;
  moneyness: string | null;
  bid: number | null;
  ask: number | null;
  iv: number | null;
  volume: number | null;
  openInterest: number | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  rho: number | null;
  p_itm: number | null;
  signals: string;
}

export interface ChainResponse {
  ticker: string;
  name: string;
  sector: string | null;
  price: number;
  expiration: string;
  flag: Flag;
  timeframe: Timeframe;
  rows: ChainRow[];
}

export interface Significance {
  value: number | null;
  level: string | null;
  badge: string | null;
  color: string | null;
  headline: string | null;
  detail: string | null;
  description: string | null;
}

export interface AnalysisResponse {
  ticker: string;
  name: string;
  price: number;
  expiration: string;
  flag: Flag;
  strike: number;
  iv: number | null;
  bid: number | null;
  ask: number | null;
  greeks: Record<string, number | null>;
  significance: Record<string, Significance>;
  risk: {
    score: number;
    level: string;
    color: string;
    components: Record<string, { earned: number; max: number }>;
    drivers: string[];
    breakeven_pct: number | null;
  };
  probability: {
    risk_neutral_pct: number | null;
    real_world_pct: number | null;
    drift: number | null;
  };
}

export interface ScanRow {
  ticker: string;
  name: string;
  sector: string;
  price: number;
  avg_score: number;
  call_score: number;
  call_level: string;
  put_score: number;
  put_level: string;
  iv_pct: number;
  prob_itm_c: number | null;
  prob_itm_p: number | null;
}

export interface ScanResponse {
  count: number;
  results: ScanRow[];
  etf_scores: Record<string, number>;
}

// ── Fetch helper with timeout + clean errors ─────────────────────────────────
async function get<T>(path: string, timeoutMs = 45000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, { signal: controller.signal });
    if (!res.ok) {
      let detail = `Request failed (${res.status})`;
      try {
        const body = await res.json();
        if (body?.detail) detail = String(body.detail);
      } catch {}
      throw new Error(detail);
    }
    return (await res.json()) as T;
  } catch (e: any) {
    if (e?.name === "AbortError") throw new Error("Request timed out. Is the backend reachable?");
    if (e?.message === "Network request failed")
      throw new Error(`Can't reach the API at ${API_URL}. Check EXPO_PUBLIC_API_URL.`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  stock: (ticker: string) => get<StockInfo>(`/api/stock/${encodeURIComponent(ticker)}`),
  chain: (ticker: string, timeframe: Timeframe, flag: Flag) =>
    get<ChainResponse>(`/api/chain?ticker=${encodeURIComponent(ticker)}&timeframe=${timeframe}&flag=${flag}`),
  analysis: (ticker: string, timeframe: Timeframe, strike: number, flag: Flag) =>
    get<AnalysisResponse>(
      `/api/analysis?ticker=${encodeURIComponent(ticker)}&timeframe=${timeframe}&strike=${strike}&flag=${flag}`,
    ),
  scan: (limit = 40) => get<ScanResponse>(`/api/scan?limit=${limit}`, 120000),
};
