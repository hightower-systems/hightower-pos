import { type FormEvent, useState } from "react";

import {
  type CustomerLookupResponse,
  useCustomerLookup,
} from "../api/customers";
import { useCustomer } from "../store/customer";
import { Modal } from "./Modal";

interface FormState {
  name: string;
  email: string;
  phone: string;
}

const EMPTY: FormState = { name: "", email: "", phone: "" };

export function AttachCustomerModal() {
  const phase = useCustomer((s) => s.phase);
  const setAttached = useCustomer((s) => s.setAttached);
  const closeLookup = useCustomer((s) => s.closeLookup);
  const lookup = useCustomerLookup();
  const [form, setForm] = useState<FormState>(EMPTY);

  const isOpen = phase === "lookup";
  const hasAnyField = !!(form.name.trim() || form.email.trim() || form.phone.trim());
  const lookupDone = lookup.isSuccess;
  const match: CustomerLookupResponse | null = lookup.data ?? null;

  function update<K extends keyof FormState>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function reset() {
    setForm(EMPTY);
    lookup.reset();
  }

  function handleClose() {
    reset();
    closeLookup();
  }

  function handleLookup(event: FormEvent) {
    event.preventDefault();
    if (!hasAnyField) return;
    lookup.mutate({
      name: form.name.trim() || undefined,
      email: form.email.trim() || undefined,
      phone: form.phone.trim() || undefined,
    });
  }

  function handleAttachMatch() {
    if (!match) return;
    setAttached({
      customer_id: match.customer_id,
      name: match.display_name,
      email: match.email,
      phone: match.phone,
      registered: match.registered,
    });
    reset();
  }

  function handleAttachAsTyped() {
    setAttached({
      customer_id: null,
      name: form.name.trim() || null,
      email: form.email.trim() || null,
      phone: form.phone.trim() || null,
      registered: false,
    });
    reset();
  }

  if (!isOpen) return null;

  return (
    <Modal open={true} onClose={handleClose} title="Attach customer">
      <form
        onSubmit={handleLookup}
        className="flex flex-col gap-3"
        aria-label="Customer lookup"
      >
        <Field
          label="Name"
          value={form.name}
          onChange={(v) => update("name", v)}
          autoFocus
          inputProps={{ "aria-label": "Customer name" }}
        />
        <Field
          label="Email"
          value={form.email}
          onChange={(v) => update("email", v)}
          inputProps={{ type: "email", "aria-label": "Customer email" }}
        />
        <Field
          label="Phone"
          value={form.phone}
          onChange={(v) => update("phone", v)}
          inputProps={{ type: "tel", "aria-label": "Customer phone" }}
        />

        {lookup.isError && (
          <p
            role="alert"
            className="rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-status-danger"
          >
            {lookup.error?.message ?? "Could not reach the customer service."}
          </p>
        )}

        {lookupDone && match && (
          <div
            data-testid="customer-match"
            className="rounded-card border border-status-success/40 bg-status-success/10 p-3 font-mono text-sm"
          >
            <p className="text-xs uppercase tracking-wider text-status-success">
              {match.registered ? "Registered customer" : "Match found"}
            </p>
            <p className="mt-1 font-bold text-ink">
              {match.display_name ?? "(no name on file)"}
            </p>
            {match.email && <p className="text-ink-muted">{match.email}</p>}
            {match.phone && <p className="text-ink-muted">{match.phone}</p>}
          </div>
        )}

        {lookupDone && !match && (
          <div
            data-testid="customer-no-match"
            className="rounded-card border border-brand-copper/40 bg-brand-copper/10 p-3 font-mono text-xs uppercase tracking-wider text-brand-copper"
          >
            No match. Will log as a new unregistered customer.
          </div>
        )}

        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleClose}
            className="flex-1 rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted hover:bg-surface-card"
          >
            Cancel
          </button>
          {!lookupDone && (
            <button
              type="submit"
              disabled={!hasAnyField || lookup.isPending}
              className="flex-1 rounded-card bg-brand-red px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {lookup.isPending ? "Looking up..." : "Look up"}
            </button>
          )}
          {lookupDone && match && (
            <button
              type="button"
              onClick={handleAttachMatch}
              className="flex-1 rounded-card bg-brand-red px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110"
            >
              Attach
            </button>
          )}
          {lookupDone && !match && (
            <button
              type="button"
              onClick={handleAttachAsTyped}
              disabled={!hasAnyField}
              className="flex-1 rounded-card bg-brand-red px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Attach as new
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
  inputProps?: React.InputHTMLAttributes<HTMLInputElement>;
}

function Field({ label, value, onChange, autoFocus, inputProps }: FieldProps) {
  return (
    <label className="block">
      <span className="mb-1 block font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted">
        {label}
      </span>
      <input
        {...inputProps}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoFocus={autoFocus}
        className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 font-mono text-base text-ink outline-none focus:border-brand-red"
      />
    </label>
  );
}
