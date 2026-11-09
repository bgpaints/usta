import { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken, type Profile, type ScanResult } from "./api";
import { IconClock, IconGift, IconHome, IconScan, IconUser } from "./icons";
import {
  HistoryScreen, HomeScreen, LoginScreen, ManualScreen, ProfileScreen, RewardsScreen, ScanResultScreen,
  ScanScreen, SetupScreen, WelcomeScreen,
} from "./screens";
import { setBackButton } from "./telegram";

export type Screen =
  | "welcome" | "login" | "setup" | "home" | "scan" | "manual" | "result" | "history" | "rewards" | "profile";

const TABS: Screen[] = ["home", "history", "rewards", "profile"];
const BACK: Partial<Record<Screen, Screen>> = { login: "welcome", scan: "home", manual: "scan", result: "home" };

export default function App() {
  const [screen, setScreen] = useState<Screen>(getToken() ? "home" : "welcome");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [booting, setBooting] = useState(!!getToken());

  const refresh = useCallback(async () => {
    try {
      const p = await api.me();
      setProfile(p);
      return p;
    } catch {
      setToken(null);
      setProfile(null);
      setScreen("welcome");
      return null;
    }
  }, []);

  useEffect(() => {
    if (getToken()) refresh().then((p) => { if (p && !p.name) setScreen("setup"); setBooting(false); });
  }, [refresh]);

  useEffect(() => {
    const back = BACK[screen];
    return setBackButton(back ? () => setScreen(back) : null);
  }, [screen]);

  const onLoggedIn = async (isNew: boolean) => {
    const p = await refresh();
    setScreen(isNew || !p?.name ? "setup" : "home");
  };
  const onScanned = (r: ScanResult) => {
    setResult(r);
    setScreen("result");
    refresh();
  };
  const logout = () => { setToken(null); setProfile(null); setScreen("welcome"); };

  if (booting) return <div className="app"><div className="loading">Загрузка…</div></div>;

  return (
    <div className="app">
      {screen === "welcome" && <WelcomeScreen onStart={() => setScreen("login")} />}
      {screen === "login" && <LoginScreen onBack={() => setScreen("welcome")} onDone={onLoggedIn} />}
      {screen === "setup" && <SetupScreen profile={profile} onDone={(p) => { setProfile(p); setScreen("home"); }} />}
      {screen === "home" && profile && <HomeScreen profile={profile} go={setScreen} />}
      {screen === "scan" && <ScanScreen go={setScreen} onScanned={onScanned} />}
      {screen === "manual" && <ManualScreen go={setScreen} onScanned={onScanned} />}
      {screen === "result" && result && <ScanResultScreen result={result} go={setScreen} />}
      {screen === "history" && <HistoryScreen />}
      {screen === "rewards" && profile && <RewardsScreen profile={profile} onChanged={refresh} />}
      {screen === "profile" && profile && <ProfileScreen profile={profile} onLogout={logout} />}

      {TABS.includes(screen) && (
        <nav className="nav" aria-label="Основное меню">
          <button type="button" className={`nav-item ${screen === "home" ? "on" : ""}`} onClick={() => setScreen("home")}><IconHome />Главная</button>
          <button type="button" className={`nav-item ${screen === "history" ? "on" : ""}`} onClick={() => setScreen("history")}><IconClock />История</button>
          <button type="button" className="nav-scan" aria-label="Сканировать" onClick={() => setScreen("scan")}><IconScan size={26} /></button>
          <button type="button" className={`nav-item ${screen === "rewards" ? "on" : ""}`} onClick={() => { refresh(); setScreen("rewards"); }}><IconGift />Награды</button>
          <button type="button" className={`nav-item ${screen === "profile" ? "on" : ""}`} onClick={() => setScreen("profile")}><IconUser />Профиль</button>
        </nav>
      )}
    </div>
  );
}
