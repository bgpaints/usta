// Обёртка над Telegram WebApp. Вне Telegram (в обычном браузере) всё тихо работает без него.
type TG = any;
const tg: TG | undefined = (window as any).Telegram?.WebApp;

export const inTelegram = !!tg && !!tg.initData;

export function initTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  try {
    tg.setHeaderColor("#0E2631");
    tg.setBackgroundColor("#F3F4F6");
  } catch { /* старые версии Telegram */ }
}

export function canScanQr(): boolean {
  return inTelegram && typeof tg.showScanQrPopup === "function" && tg.isVersionAtLeast?.("6.4");
}

/** Открывает встроенный сканер QR Telegram. Возвращает текст кода или null, если закрыли. */
export function scanQr(text: string): Promise<string | null> {
  return new Promise((resolve) => {
    let done = false;
    const onClosed = () => {
      tg.offEvent?.("scanQrPopupClosed", onClosed);
      if (!done) resolve(null);
    };
    tg.onEvent?.("scanQrPopupClosed", onClosed);
    tg.showScanQrPopup({ text }, (value: string) => {
      done = true;
      resolve(value);
      return true; // закрыть сканер после первого кода
    });
  });
}

export function haptic(kind: "success" | "error" | "warning") {
  try { tg?.HapticFeedback?.notificationOccurred(kind); } catch { /* нет вибрации */ }
}

export function confirmAction(message: string): Promise<boolean> {
  if (inTelegram && tg.showConfirm) return new Promise((r) => tg.showConfirm(message, (ok: boolean) => r(ok)));
  return Promise.resolve(window.confirm(message));
}

/** Кнопка «Назад» в шапке Telegram. Возвращает функцию отписки. */
export function setBackButton(onBack: (() => void) | null): () => void {
  if (!inTelegram || !tg.BackButton) return () => {};
  if (!onBack) { tg.BackButton.hide(); return () => {}; }
  tg.BackButton.show();
  tg.BackButton.onClick(onBack);
  return () => { tg.BackButton.offClick(onBack); tg.BackButton.hide(); };
}

export function getLocation(): Promise<{ lat: number; lng: number } | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => resolve(null),
      { timeout: 4000, maximumAge: 300000 },
    );
  });
}
