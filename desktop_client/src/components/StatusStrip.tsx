import { useDependencies } from "../api/health";
import { usePrintAgentStatus } from "../api/printAgent";
import { formatCents } from "../api/till";

interface Props {
  cashier: { display_name: string };
  onSignOut: () => void;
  signOutPending?: boolean;
  // When the cashier has an OPEN till, surface the opening float
  // (so they know which session is in progress) and a Close Till
  // button next to Sign Out. Both omitted when the till is closed.
  till?: {
    opening_float_cents: number;
    onCloseTill: () => void;
  } | null;
  onOpenSettings?: () => void;
}

export function StatusStrip({
  cashier,
  onSignOut,
  signOutPending = false,
  till = null,
  onOpenSettings,
}: Props) {
  const deps = useDependencies();
  const printAgent = usePrintAgentStatus();

  const sentry = deps.data?.sentry;
  const windcave = deps.data?.windcave;
  const printer = printAgent.data;

  return (
    <header className="flex flex-wrap items-center gap-4 bg-brand-red px-6 py-3 text-sm text-brand-cream">
      <span className="font-mono text-base font-bold uppercase tracking-wider text-brand-cream">
        Hightower POS
      </span>
      <span className="text-brand-cream/90">{cashier.display_name}</span>
      {deps.data && (
        <span className="font-mono text-xs uppercase tracking-wider text-brand-cream/70">
          {deps.data.terminal_id}
        </span>
      )}

      <div className="ml-auto flex items-center gap-5">
        <Dot
          label="Sentry"
          ok={sentry?.reachable ?? null}
          detail={
            sentry?.reachable && sentry.latency_ms !== null
              ? `${sentry.latency_ms}ms`
              : sentry?.error ?? undefined
          }
        />
        <Dot
          label="Windcave"
          ok={windcave?.configured ?? null}
          detail={windcave?.mock ? "mock" : undefined}
        />
        <Dot
          label="Print Agent"
          ok={printer?.printer_online ?? null}
        />
        {till && (
          <>
            <span
              data-testid="till-status"
              className="font-mono text-xs uppercase tracking-wider text-brand-cream/90"
            >
              Till: {formatCents(till.opening_float_cents)} open
            </span>
            <button
              type="button"
              onClick={till.onCloseTill}
              className="rounded-card border border-brand-cream/40 bg-brand-cream/10 px-3 py-1 font-mono text-xs font-semibold uppercase tracking-wider text-brand-cream hover:bg-brand-cream/20"
            >
              Close Till
            </button>
          </>
        )}
        {onOpenSettings && (
          <button
            type="button"
            onClick={onOpenSettings}
            aria-label="Open settings"
            className="rounded-card border border-brand-cream/40 bg-brand-cream/10 px-3 py-1 font-mono text-xs font-semibold uppercase tracking-wider text-brand-cream hover:bg-brand-cream/20"
          >
            Settings
          </button>
        )}
        <button
          type="button"
          onClick={onSignOut}
          disabled={signOutPending}
          className="rounded-card border border-brand-cream/40 bg-brand-cream/10 px-3 py-1 font-mono text-xs font-semibold uppercase tracking-wider text-brand-cream hover:bg-brand-cream/20 disabled:opacity-50"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}

interface DotProps {
  label: string;
  ok: boolean | null;
  detail?: string;
}

function Dot({ label, ok, detail }: DotProps) {
  const color =
    ok === null
      ? "bg-slate-500"
      : ok
      ? "bg-status-success"
      : "bg-status-danger";
  const status =
    ok === null ? "unknown" : ok ? "online" : "offline";

  return (
    <span
      className="flex items-center gap-1.5"
      data-testid={`dot-${label.toLowerCase().replace(" ", "-")}`}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${color}`}
        aria-label={`${label}: ${status}`}
      />
      <span className="font-mono text-xs uppercase tracking-wider text-brand-cream/90">
        {label}
      </span>
      {detail && <span className="text-xs text-brand-cream/70">{detail}</span>}
    </span>
  );
}
