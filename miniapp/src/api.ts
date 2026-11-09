// Клиент API платформы Usta. Токен мастера хранится на устройстве.
const BASE = import.meta.env.VITE_API_URL || "/api";
const TOKEN_KEY = "usta_token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* приватный режим */ }
}

export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any) {
    super(typeof detail === "string" ? detail : detail?.message || "Ошибка сервера");
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError(0, "Нет связи с сервером. Проверьте интернет");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) setToken(null);
    throw new ApiError(res.status, data.detail ?? "Ошибка сервера");
  }
  return data as T;
}

export type Profile = {
  id: number; phone: string; name: string | null; city: string | null; specialization: string | null;
  balance: number; available: number; pending: number; on_review: number;
  level: string; earned_12m: number; next_level: string | null; points_to_next: number; progress_pct: number;
};
export type HistoryItem = { id: number; kind: string; title: string; note: string | null; points: number; on_review: boolean; created_at: string };
export type RewardItem = { id: number; title: string; description: string | null; kind: string; cost_points: number; min_level: string | null; in_stock: boolean; can_redeem: boolean; missing_points: number };
export type ScanResult = { ok: boolean; reason: string; message: string; points: number; frozen: boolean; product: string | null; volume: string | null; calc: string | null; balance: number };
export type RedemptionItem = { id: number; reward: string; points: number; status: string; created_at: string; comment: string | null };

export const api = {
  requestOtp: (phone: string) => request<{ phone: string; sent: boolean; debug_code?: string }>("POST", "/auth/otp/request", { phone }),
  verifyOtp: (phone: string, code: string) => request<{ token: string; is_new: boolean }>("POST", "/auth/otp/verify", { phone, code }),
  me: () => request<Profile>("GET", "/me"),
  updateMe: (data: Partial<Pick<Profile, "name" | "city" | "specialization">>) => request<Profile>("PATCH", "/me", data),
  scan: (code: string, manual: boolean, lat?: number, lng?: number) => request<ScanResult>("POST", "/scan", { code, manual, lat, lng }),
  history: () => request<HistoryItem[]>("GET", "/history"),
  rewards: () => request<RewardItem[]>("GET", "/rewards"),
  redeem: (id: number) => request<{ redemption_id: number; status: string; balance: number }>("POST", `/rewards/${id}/redeem`),
  redemptions: () => request<RedemptionItem[]>("GET", "/redemptions"),
};
