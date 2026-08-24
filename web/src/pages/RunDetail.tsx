import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { RunDetail, api, fmt } from "../api";

export default function RunDetailPage() {
  const { id } = useParams();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let timer: number | undefined;

    function tick() {
      api
        .run(id as string)
        .then((detail) => {
          if (cancelled) return;
          setRun(detail);
          if (detail.status === "queued" || detail.status === "running") {
            timer = window.setTimeout(tick, 1500);
          }
        })
        .catch((err: Error) => {
          if (!cancelled) setError(err.message);
        });
    }

    tick();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [id]);

  async function tag() {
    if (!id) return;
    await api.baseline(id);
    const detail = await api.run(id);
    setRun(detail);
  }

  if (!run) return <p className="text-sm">{error || "Loading…"}</p>;
  const means = run.means || {};
  const metricNames = Object.keys(means);

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link to="/runs" className="font-mono text-xs text-accent">
            ← runs
          </Link>
          <h2 className="mt-2 text-2xl font-semibold">{run.label || "Untitled run"}</h2>
          <p className="font-mono text-xs text-ink/50">
            {run.id} · {run.status} · {run.evaluator} · {run.adapter_type} · {run.error_count} errors
          </p>
        </div>
        <div className="flex gap-2">
          <Link className="border border-ink px-3 py-2 text-sm" to={`/diff?head=${run.id}`}>
            Diff
          </Link>
          <button className="border border-ink bg-ink px-3 py-2 text-sm text-paper" onClick={tag} type="button">
            {run.is_baseline ? "Baseline" : "Set baseline"}
          </button>
        </div>
      </div>
      {run.error_message && <p className="text-sm text-bad">{run.error_message}</p>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metricNames.map((name) => (
          <div key={name} className="border border-rule bg-white/50 p-4">
            <div className="font-mono text-[10px] uppercase tracking-wide text-ink/50">{name.replaceAll("_", " ")}</div>
            <div className="mt-1 font-mono text-3xl">{fmt(means[name])}</div>
          </div>
        ))}
      </div>
      <table className="w-full border-collapse text-left text-sm">
        <thead className="font-mono text-xs uppercase text-ink/60">
          <tr>
            <th className="border-b border-rule py-2">Question</th>
            {metricNames.map((name) => (
              <th key={name} className="border-b border-rule py-2">
                {name.replaceAll("_", " ")}
              </th>
            ))}
            <th className="border-b border-rule py-2">Error</th>
          </tr>
        </thead>
        <tbody>
          {run.rows.map((row, index) => (
            <tr key={index}>
              <td className="border-b border-rule py-2 align-top">{row.question}</td>
              {metricNames.map((name) => (
                <td key={name} className="border-b border-rule py-2 align-top font-mono">
                  {fmt(row.metrics[name])}
                </td>
              ))}
              <td className="border-b border-rule py-2 align-top text-bad">{row.error || ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
