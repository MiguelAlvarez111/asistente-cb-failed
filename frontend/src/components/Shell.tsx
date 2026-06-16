import { LogOut, ShieldCheck } from "lucide-react";

type Props = {
  children: React.ReactNode;
  onLogout: () => void;
  actions?: React.ReactNode;
};

export function Shell({ children, onLogout, actions }: Props) {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line bg-white/95 shadow-sm backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-2.5">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded bg-pine text-white">
              <ShieldCheck size={18} />
            </div>
            <div>
              <h1 className="text-base font-semibold">CB Failed Assistant</h1>
              <p className="text-xs text-ink/60">Operational validation workspace</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {actions}
            <button className="flex items-center gap-2 rounded border border-line px-3 py-2 text-sm hover:bg-field" onClick={onLogout}>
              <LogOut size={16} />
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-5 py-5">{children}</main>
    </div>
  );
}
