import { useEffect, useState } from "react";
import { api, ApiError, setToken, type HistoryItem, type Profile, type RedemptionItem, type RewardItem, type ScanResult } from "./api";
import type { Screen } from "./App";
import { IconAlert, IconBack, IconCheck, IconClose, IconScan } from "./icons";
import { canScanQr, confirmAction, getLocation, haptic, inTelegram, scanQr } from "./telegram";

const fmt = (n: number) => String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
const signed = (n: number) => (n >= 0 ? "+" : "−") + fmt(n);
const date = (iso: string) => new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });

const SPECS = [
  { id: "interior", label: "Внутренние работы" },
  { id: "facade", label: "Фасады" },
  { id: "waterproofing", label: "Гидроизоляция" },
  { id: "team", label: "Бригада" },
];
const KIND_TAG: Record<string, string> = { cash: "₸", product: "ТОВАР", trip: "TRIP" };
const STATUS: Record<string, string> = { pending: "на рассмотрении", approved: "одобрено", done: "выполнено", rejected: "отклонено" };

function errorText(e: unknown) {
  if (e instanceof ApiError) return e.message;
  return "Что-то пошло не так. Попробуйте ещё раз";
}

// ---------- Приветствие ----------

export function WelcomeScreen({ onStart }: { onStart: () => void }) {
  return (
    <main className="screen dark" style={{ justifyContent: "space-between", paddingTop: 56, gap: 32 }}>
      <div className="brand">
        <img src="/logo-white.png" alt="Bekmetov" />
        <div><div className="brand-name">USTA</div><div className="brand-by">by Bekmetov</div></div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <h1>Сканируй код из банки — получай баллы</h1>
        <p className="tag">Ұста — мастер. Для тех, кто делает ремонт руками.</p>
        <p className="lead">Обменивай баллы на деньги, инструмент и путешествия. Код лежит в пакетике внутри каждой банки.</p>
      </div>
      <button type="button" className="btn btn-primary" onClick={onStart}>Войти по номеру телефона</button>
    </main>
  );
}

// ---------- Вход по SMS ----------

export function LoginScreen({ onBack, onDone }: { onBack: () => void; onDone: (isNew: boolean) => void }) {
  const [phone, setPhone] = useState("+7 ");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);

  const send = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.requestOtp(phone);
      setPhone(r.phone);
      setHint(r.debug_code ? `Тестовый режим: код ${r.debug_code}` : null);
      setStep("code");
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  const verify = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.verifyOtp(phone, code);
      setToken(r.token);
      haptic("success");
      onDone(r.is_new);
    } catch (e) { setError(errorText(e)); haptic("error"); } finally { setBusy(false); }
  };

  return (
    <main className="screen">
      {!inTelegram && <button type="button" className="icon-btn" aria-label="Назад" onClick={step === "code" ? () => setStep("phone") : onBack}><IconBack /></button>}
      {step === "phone" ? (
        <>
          <div><h2>Вход</h2><p className="sub">Отправим SMS с кодом. Документы не нужны.</p></div>
          <label className="field">Номер телефона
            <input className="input" type="tel" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          {error && <div className="notice err">{error}</div>}
          <div className="spacer" />
          <button type="button" className="btn btn-primary" disabled={busy || phone.replace(/\D/g, "").length < 11} onClick={send}>Получить SMS-код</button>
        </>
      ) : (
        <>
          <div><h2>Код из SMS</h2><p className="sub">Отправили на {phone}</p></div>
          <label className="field">Код
            <input className="input input-otp" inputMode="numeric" autoComplete="one-time-code" maxLength={4} value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 4))} />
          </label>
          {hint && <div className="notice info">{hint}</div>}
          {error && <div className="notice err">{error}</div>}
          <button type="button" className="link-btn" onClick={send} disabled={busy}>Отправить код ещё раз</button>
          <div className="spacer" />
          <button type="button" className="btn btn-primary" disabled={busy || code.length !== 4} onClick={verify}>Войти</button>
        </>
      )}
    </main>
  );
}

// ---------- Заполнение профиля ----------

export function SetupScreen({ profile, onDone }: { profile: Profile | null; onDone: (p: Profile) => void }) {
  const [name, setName] = useState(profile?.name ?? "");
  const [city, setCity] = useState(profile?.city ?? "");
  const [spec, setSpec] = useState(profile?.specialization ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true); setError(null);
    try { onDone(await api.updateMe({ name: name.trim(), city: city.trim(), specialization: spec || null })); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <main className="screen scroll">
      <div><h2>Расскажите о себе</h2><p className="sub">Минута — и можно сканировать.</p></div>
      <label className="field">Имя<input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Как к вам обращаться" /></label>
      <label className="field">Город<input className="input" value={city} onChange={(e) => setCity(e.target.value)} placeholder="Например, Алматы" /></label>
      <div className="field">Чем занимаетесь
        <div className="chips">
          {SPECS.map((s) => (
            <button key={s.id} type="button" className={`chip ${spec === s.id ? "on" : ""}`} aria-pressed={spec === s.id} onClick={() => setSpec(s.id)}>{s.label}</button>
          ))}
        </div>
      </div>
      <div className="notice info">+100 приветственных баллов после первого скана</div>
      {error && <div className="notice err">{error}</div>}
      <div className="spacer" />
      <button type="button" className="btn btn-primary" disabled={busy || name.trim().length < 2 || city.trim().length < 2} onClick={save}>Готово</button>
    </main>
  );
}

// ---------- Главная ----------

function HistoryList({ items }: { items: HistoryItem[] }) {
  if (!items.length) return <div className="card empty">Здесь появятся ваши начисления</div>;
  return (
    <div className="card">
      {items.map((h) => (
        <div key={h.id} className="list-row">
          <div style={{ minWidth: 0 }}>
            <div className="list-title">{h.note || h.title}</div>
            <div className="list-sub">{h.title} · {date(h.created_at)}{h.on_review ? " · на проверке" : ""}</div>
          </div>
          <span className={`pts ${h.on_review ? "review" : h.points > 0 ? "plus" : ""}`}>{signed(h.points)}</span>
        </div>
      ))}
    </div>
  );
}

export function HomeScreen({ profile, go }: { profile: Profile; go: (s: Screen) => void }) {
  const [recent, setRecent] = useState<HistoryItem[] | null>(null);
  useEffect(() => { api.history().then((h) => setRecent(h.slice(0, 3))).catch(() => setRecent([])); }, []);
  return (
    <main className="screen scroll">
      <div>
        <div className="sub" style={{ fontSize: 14 }}>Сәлем,</div>
        <div style={{ fontSize: 22, fontWeight: 800 }}>{profile.name || "мастер"}</div>
      </div>
      <section className="balance" aria-label="Баланс">
        <div className="balance-row"><span className="balance-label">Ваш баланс</span><span className="level-chip">{profile.level}</span></div>
        <div><span className="balance-num">{fmt(profile.balance)}</span><span className="balance-unit">баллов</span></div>
        {profile.pending > 0 && <div className="hint">{fmt(profile.pending)} из них станут доступны к обмену через 3 дня</div>}
        {profile.on_review > 0 && <div className="hint">Ещё {fmt(profile.on_review)} на проверке</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="bar"><div style={{ width: `${profile.progress_pct}%` }} /></div>
          <span className="hint">{profile.next_level ? `До уровня «${profile.next_level}» — ${fmt(profile.points_to_next)} баллов` : "Максимальный уровень"}</span>
        </div>
      </section>
      <button type="button" className="btn btn-primary btn-big" onClick={() => go("scan")}><IconScan />Сканировать код</button>
      <div className="balance-row">
        <h3>Последние начисления</h3>
        <button type="button" className="link-btn" onClick={() => go("history")}>Все</button>
      </div>
      {recent === null ? <div className="card empty">Загрузка…</div> : <HistoryList items={recent} />}
    </main>
  );
}

// ---------- Скан ----------

async function submitScan(code: string, manual: boolean, onScanned: (r: ScanResult) => void, setError: (s: string | null) => void) {
  const loc = await getLocation();
  try {
    const r = await api.scan(code, manual, loc?.lat, loc?.lng);
    haptic("success");
    onScanned(r);
  } catch (e) {
    haptic("error");
    if (e instanceof ApiError && e.detail && typeof e.detail === "object" && "reason" in e.detail) {
      onScanned(e.detail as ScanResult);
    } else setError(errorText(e));
  }
}

export function ScanScreen({ go, onScanned }: { go: (s: Screen) => void; onScanned: (r: ScanResult) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const tgScanner = canScanQr();

  const open = async () => {
    setError(null);
    const value = await scanQr("Наведите на QR-код из пакетика в банке");
    if (!value) return;
    setBusy(true);
    await submitScan(value, false, onScanned, setError);
    setBusy(false);
  };
  useEffect(() => { if (tgScanner) open(); /* сразу открываем камеру */ }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="screen scan-bg">
      {!inTelegram && (
        <div className="balance-row">
          <button type="button" className="icon-btn" style={{ background: "#1A3542", color: "#fff" }} aria-label="Закрыть" onClick={() => go("home")}><IconClose /></button>
          <span style={{ fontWeight: 700 }}>Скан кода</span><span style={{ width: 44 }} />
        </div>
      )}
      <p className="lead" style={{ textAlign: "center" }}>Код лежит в пакетике внутри банки, под крышкой</p>
      <div className="spacer" />
      <div className="scan-frame"><IconScan size={72} /></div>
      <div className="spacer" />
      {busy && <div className="notice info">Проверяем код…</div>}
      {error && <div className="notice err">{error}</div>}
      {tgScanner ? (
        <button type="button" className="btn btn-primary" disabled={busy} onClick={open}>Открыть камеру</button>
      ) : (
        <div className="notice info">Сканер камеры работает в Telegram. Здесь введите код вручную.</div>
      )}
      <button type="button" className="btn btn-ghost" onClick={() => go("manual")}>Ввести 14 цифр вручную</button>
    </main>
  );
}

export function ManualScreen({ go, onScanned }: { go: (s: Screen) => void; onScanned: (r: ScanResult) => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ok = /^\d{14}$/.test(code);
  const submit = async () => { setBusy(true); setError(null); await submitScan(code, true, onScanned, setError); setBusy(false); };
  return (
    <main className="screen">
      {!inTelegram && <button type="button" className="icon-btn" aria-label="Назад" onClick={() => go("scan")}><IconBack /></button>}
      <div><h2>Ввести код вручную</h2><p className="sub">14 цифр под QR-кодом в пакетике</p></div>
      <label className="field">Код
        <input className="input input-code" inputMode="numeric" maxLength={14} placeholder="00000000000000" value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 14))} />
      </label>
      <span className="list-sub">{code.length} из 14 цифр</span>
      {error && <div className="notice err">{error}</div>}
      <div className="spacer" />
      <button type="button" className="btn btn-primary" disabled={!ok || busy} onClick={submit}>Подтвердить</button>
    </main>
  );
}

export function ScanResultScreen({ result, go }: { result: ScanResult; go: (s: Screen) => void }) {
  if (!result.ok) {
    return (
      <main className="screen center" style={{ paddingTop: 56 }}>
        <div className="success-icon" style={{ background: "var(--red-soft)" }}><IconAlert /></div>
        <h2>Не получилось</h2>
        <p className="sub" style={{ fontSize: 16 }}>{result.message}</p>
        <div className="spacer" />
        <button type="button" className="btn btn-primary" onClick={() => go("scan")}>Попробовать снова</button>
        <button type="button" className="btn btn-light" onClick={() => go("home")}>На главную</button>
      </main>
    );
  }
  return (
    <main className="screen center" style={{ paddingTop: 48 }}>
      <div className="success-icon"><IconCheck /></div>
      <div className="big-pts">+{fmt(result.points)}</div>
      <div style={{ fontSize: 17, fontWeight: 600 }}>{result.frozen ? "баллов начислено, проходят проверку" : "баллов начислено"}</div>
      <div className="card card-pad" style={{ width: "100%", display: "flex", flexDirection: "column", gap: 10, textAlign: "left" }}>
        <div className="kv"><span>Продукт</span><span>{result.product}</span></div>
        <div className="kv"><span>Объём</span><span>{result.volume}</span></div>
        <div className="kv"><span>Расчёт</span><span>{result.calc}</span></div>
        <div className="kv" style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}><span>Баланс</span><span>{fmt(result.balance)}</span></div>
      </div>
      <div className="spacer" />
      <button type="button" className="btn btn-primary" onClick={() => go("scan")}>Сканировать ещё</button>
      <button type="button" className="btn btn-light" onClick={() => go("home")}>На главную</button>
    </main>
  );
}

// ---------- История ----------

export function HistoryScreen() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  useEffect(() => { api.history().then(setItems).catch(() => setItems([])); }, []);
  return (
    <main className="screen scroll">
      <h2>История</h2>
      {items === null ? <div className="card empty">Загрузка…</div> : <HistoryList items={items} />}
      <p className="list-sub" style={{ textAlign: "center" }}>Баллы действуют 12 месяцев с даты начисления</p>
    </main>
  );
}

// ---------- Награды ----------

export function RewardsScreen({ profile, onChanged }: { profile: Profile; onChanged: () => Promise<unknown> }) {
  const [items, setItems] = useState<RewardItem[] | null>(null);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const load = () => api.rewards().then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);

  const redeem = async (r: RewardItem) => {
    if (!(await confirmAction(`Обменять ${fmt(r.cost_points)} баллов на «${r.title}»?`))) return;
    setBusyId(r.id); setNotice(null);
    try {
      await api.redeem(r.id);
      haptic("success");
      setNotice({ ok: true, text: `Заявка принята: ${r.title}. Статус — в профиле.` });
      await Promise.all([onChanged(), load()]);
    } catch (e) { haptic("error"); setNotice({ ok: false, text: errorText(e) }); } finally { setBusyId(null); }
  };

  const label = (r: RewardItem) => {
    if (!r.in_stock) return "Нет в наличии";
    if (r.missing_points > 0) return `Не хватает ${fmt(r.missing_points)} б.`;
    if (!r.can_redeem && r.min_level) return `С уровня «${r.min_level}»`;
    return "Обменять";
  };

  return (
    <main className="screen scroll">
      <div className="balance-row"><h2>Награды</h2><span style={{ fontWeight: 700 }}>{fmt(profile.available)} б. доступно</span></div>
      {profile.pending > 0 && <div className="notice info">{fmt(profile.pending)} баллов станут доступны через 3 дня после скана</div>}
      {notice && <div className={`notice ${notice.ok ? "ok" : "err"}`}>{notice.text}</div>}
      {items === null && <div className="card empty">Загрузка…</div>}
      {items?.length === 0 && <div className="card empty">Каталог наград скоро появится</div>}
      {items?.map((r) => (
        <div key={r.id} className="card card-pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
            <div className="reward-tag">{KIND_TAG[r.kind] ?? "★"}</div>
            <div style={{ minWidth: 0 }}>
              <div className="list-title" style={{ fontWeight: 700 }}>{r.title}</div>
              <div className="list-sub">{fmt(r.cost_points)} баллов{r.min_level ? ` · уровень «${r.min_level}»` : ""}{r.description ? ` · ${r.description}` : ""}</div>
            </div>
          </div>
          <button type="button" className="btn btn-dark" disabled={!r.can_redeem || busyId !== null} onClick={() => redeem(r)}>
            {busyId === r.id ? "Отправляем…" : label(r)}
          </button>
        </div>
      ))}
    </main>
  );
}

// ---------- Профиль ----------

export function ProfileScreen({ profile, onLogout }: { profile: Profile; onLogout: () => void }) {
  const [reds, setReds] = useState<RedemptionItem[] | null>(null);
  useEffect(() => { api.redemptions().then(setReds).catch(() => setReds([])); }, []);
  const spec = SPECS.find((s) => s.id === profile.specialization)?.label;
  return (
    <main className="screen scroll">
      <h2>Профиль</h2>
      <div className="card card-pad" style={{ display: "flex", gap: 14, alignItems: "center" }}>
        <div className="avatar">{(profile.name || "М").slice(0, 1).toUpperCase()}</div>
        <div>
          <div style={{ fontSize: 17, fontWeight: 800 }}>{profile.name || "Мастер"}</div>
          <div className="list-sub">{[profile.city, spec, profile.level].filter(Boolean).join(" · ")}</div>
          <div className="list-sub">{profile.phone}</div>
        </div>
      </div>
      <h3>Мои заявки</h3>
      {reds === null ? <div className="card empty">Загрузка…</div> : reds.length === 0 ? (
        <div className="card empty">Пока нет обменов</div>
      ) : (
        <div className="card">
          {reds.map((r) => (
            <div key={r.id} className="list-row">
              <div style={{ minWidth: 0 }}>
                <div className="list-title">{r.reward}</div>
                <div className="list-sub">{fmt(r.points)} баллов · {date(r.created_at)}{r.comment ? ` · ${r.comment}` : ""}</div>
              </div>
              <span className={`status ${r.status}`}>{STATUS[r.status] ?? r.status}</span>
            </div>
          ))}
        </div>
      )}
      <button type="button" className="btn btn-light" onClick={onLogout}>Выйти</button>
    </main>
  );
}
