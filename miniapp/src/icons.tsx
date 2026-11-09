const base = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const IconBack = () => <svg width="20" height="20" viewBox="0 0 24 24" {...base}><path d="M15 18l-6-6 6-6" /></svg>;
export const IconClose = () => <svg width="20" height="20" viewBox="0 0 24 24" {...base}><path d="M18 6L6 18" /><path d="M6 6l12 12" /></svg>;
export const IconScan = ({ size = 24 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
    <path d="M3 7V5a2 2 0 0 1 2-2h2" /><path d="M17 3h2a2 2 0 0 1 2 2v2" /><path d="M21 17v2a2 2 0 0 1-2 2h-2" /><path d="M7 21H5a2 2 0 0 1-2-2v-2" /><path d="M7 12h10" />
  </svg>
);
export const IconHome = () => <svg width="22" height="22" viewBox="0 0 24 24" {...base}><path d="M3 10l9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" /></svg>;
export const IconClock = () => <svg width="22" height="22" viewBox="0 0 24 24" {...base}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>;
export const IconGift = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" {...base}>
    <rect x="3" y="8" width="18" height="13" rx="1" /><path d="M12 8v13" /><path d="M3 12h18" /><path d="M12 8c-2-4-6-4-6-1s6 1 6 1 6 2 6-1-4-3-6 1" />
  </svg>
);
export const IconUser = () => <svg width="22" height="22" viewBox="0 0 24 24" {...base}><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></svg>;
export const IconCheck = () => <svg width="44" height="44" viewBox="0 0 24 24" {...base} strokeWidth={2.5} stroke="#1E7A45"><path d="M20 6L9 17l-5-5" /></svg>;
export const IconAlert = () => <svg width="44" height="44" viewBox="0 0 24 24" {...base} stroke="#B42318"><circle cx="12" cy="12" r="9" /><path d="M12 8v5" /><path d="M12 16h.01" /></svg>;
