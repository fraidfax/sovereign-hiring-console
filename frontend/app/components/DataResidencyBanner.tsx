"use client";

import { useEffect, useState } from "react";
import { fetchDataResidency, ApiError } from "../lib/api";
import type { DataResidency } from "../lib/types";
import { ErrorBanner } from "./ErrorBanner";

export function DataResidencyBanner() {
  const [data, setData] = useState<DataResidency | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchDataResidency()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err.message
              : "Could not load data residency information.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section
      aria-label="Data residency"
      className="rounded-xl border border-accent/30 bg-navy-900 p-5"
    >
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent">
        <span aria-hidden>◎</span>
        <span>Where this data lives</span>
      </div>

      {loading && (
        <p className="mt-3 text-sm text-slate-400">Checking data residency…</p>
      )}

      <ErrorBanner message={error} />

      {data && (
        <div className="mt-3 space-y-4">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-2xl font-bold text-slate-50">
              {data.location}
            </span>
            <span className="text-sm text-slate-400">
              {data.pii_external_requests_total === 0
                ? "0 requests carrying personal data have left this boundary"
                : `${data.pii_external_requests_total} PII-bearing external request(s) recorded`}
            </span>
          </div>

          {data.external_services.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {data.external_services.map((svc) => (
                <div
                  key={svc.name}
                  className="rounded-lg border border-navy-600 bg-navy-800 p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-slate-100">
                      {svc.name}
                    </span>
                    <span
                      className={
                        svc.receives_pii
                          ? "rounded-full bg-warn-dim/60 px-2 py-0.5 text-xs font-semibold text-warn"
                          : "rounded-full bg-accent-dim/30 px-2 py-0.5 text-xs font-semibold text-accent-bright"
                      }
                    >
                      {svc.receives_pii
                        ? "receives PII"
                        : "0 PII fields sent"}
                    </span>
                  </div>
                  <p className="mt-1.5 text-xs text-slate-400">{svc.note}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
