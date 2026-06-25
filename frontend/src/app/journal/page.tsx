"use client";

import { useEffect, useState } from "react";
import { getJournal, type JournalEntry } from "@/lib/api";

export default function JournalPage() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await getJournal();
        setEntries(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load journal");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Trade Journal</h1>
        <p className="text-sm text-[var(--fg-muted)] mt-1">
          Trade history from the PostgreSQL <code>trade_journal</code> table.
        </p>
      </div>

      {loading && (
        <div className="bg-bg-card border border-border rounded-lg p-12 text-center text-[var(--fg-muted)]">
          Loading...
        </div>
      )}

      {error && (
        <div className="bg-bg-card border border-bear rounded-lg p-6">
          <p className="text-bear text-sm">{error}</p>
          <p className="text-[var(--fg-muted)] text-xs mt-2">
            Make sure the backend is running and the trade_journal table exists.
          </p>
        </div>
      )}

      {!loading && !error && entries.length === 0 && (
        <div className="bg-bg-card border border-border rounded-lg p-12 text-center">
          <p className="text-[var(--fg-muted)]">No journal entries yet.</p>
        </div>
      )}

      {!loading && !error && entries.length > 0 && (
        <div className="bg-bg-card border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-[var(--fg-muted)] uppercase border-b border-border bg-bg-secondary">
                  <th className="py-3 px-4">ID</th>
                  <th className="py-3 px-4">Symbol</th>
                  <th className="py-3 px-4">Entry</th>
                  <th className="py-3 px-4">Exit</th>
                  <th className="py-3 px-4">PnL</th>
                  <th className="py-3 px-4">Notes</th>
                  <th className="py-3 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-border hover:bg-bg-tertiary"
                  >
                    <td className="py-3 px-4 text-[var(--fg-muted)]">
                      {entry.id}
                    </td>
                    <td className="py-3 px-4 font-semibold">
                      {entry.symbol}
                    </td>
                    <td className="py-3 px-4 font-mono">
                      {entry.entry.toFixed(4)}
                    </td>
                    <td className="py-3 px-4 font-mono">
                      {entry.exit !== null ? entry.exit.toFixed(4) : "—"}
                    </td>
                    <td
                      className={`py-3 px-4 font-mono ${
                        entry.pnl === null
                          ? "text-[var(--fg-muted)]"
                          : entry.pnl >= 0
                          ? "text-bull"
                          : "text-bear"
                      }`}
                    >
                      {entry.pnl === null
                        ? "—"
                        : `${entry.pnl >= 0 ? "+" : ""}${entry.pnl.toFixed(2)}`}
                    </td>
                    <td className="py-3 px-4 text-[var(--fg-muted)] max-w-xs truncate">
                      {entry.notes || "—"}
                    </td>
                    <td className="py-3 px-4 text-[var(--fg-muted)] text-xs">
                      {new Date(entry.timestamp).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
