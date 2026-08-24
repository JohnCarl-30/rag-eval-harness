import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DiffResponse, Run, api, fmt } from "../api";

export default function DiffPage() {
  const [params, setParams] = useSearchParams();
  const [runs, setRuns] = useState<Run[]>([]);
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [threshold, setThreshold] = useState(params.get("threshold") || "0.05");
  const [baseline, setBaseline] = useState(params.get("baseline") || "");
  const [head, setHead] = useState(params.get("head") || "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.runs().then((items) => {
      setRuns(items);
      if (!baseline) {
        const tagged = items.find((item) => item.is_baseline);
        if (tagged) setBaseline(tagged.id);
      }
    });
  }, [baseline]);

  const options = useMemo(
    () =>
      runs.map((run) => ({
        id: run.id,
        label: `${run.is_baseline ? "* " : ""}${run.label || run.id.slice(0, 8)} (${run.status})`,
      })),
    [runs],
  );

  async function onCompare(event?: FormEvent) {
    event?.preventDefault();
    if (!baseline || !head) return;
    setError(null);
    try {
      const result = await api.diff(head, baseline, Number(threshold));
      setDiff(result);
      setParams({ baseline, head, threshold });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Diff failed");
    }
  }

  useEffect(() => {
    if (baseline && head) {
      void onCompare();
    }
    // initial load only when query is present
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-8">
      <h2 className="text-lg font-semibold">Mean delta vs baseline</h2>
      <form onSubmit={onCompare} className="grid gap-4 border border-rule bg-white/50 p-4 md:grid-cols-4">
        <label className="text-sm">
          Baseline
          <select
            className="mt-1 block w-full border border-rule bg-paper px-2 py-1"
            value={baseline}
            onChange={(event) => setBaseline(event.target.value)}
          >
            <option value="">Select…</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Head
          <select
            className="mt-1 block w-full border border-rule bg-paper px-2 py-1"
            value={head}
            onChange={(event) => setHead(event.target.value)}
          >
            <option value="">Select…</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Threshold
          <input
            className="mt-1 block w-full border border-rule bg-paper px-2 py-1 font-mono"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
          />
        </label>
        <div className="flex items-end">
          <button className="w-full border border-ink bg-ink px-3 py-2 text-sm text-paper" type="submit">
            Compare
          </button>
        </div>
      </form>
      {error && <p className="text-sm text-bad">{error}</p>}
      {diff && (
        <>
          <p className={diff.passed ? "text-good" : "text-bad"}>
            {diff.passed ? "No regression vs threshold." : "Regression: a mean dropped past the threshold."}
          </p>
          <table className="w-full border-collapse text-left text-sm">
            <thead className="font-mono text-xs uppercase text-ink/60">
              <tr>
                <th className="border-b border-rule py-2">Metric</th>
                <th className="border-b border-rule py-2">Baseline</th>
                <th className="border-b border-rule py-2">Head</th>
                <th className="border-b border-rule py-2">Delta</th>
              </tr>
            </thead>
            <tbody>
              {diff.deltas.map((item) => (
                <tr key={item.metric}>
                  <td className="border-b border-rule py-2">{item.metric.replaceAll("_", " ")}</td>
                  <td className="border-b border-rule py-2 font-mono">{fmt(item.baseline)}</td>
                  <td className="border-b border-rule py-2 font-mono">{fmt(item.head)}</td>
                  <td className={`border-b border-rule py-2 font-mono ${item.dropped ? "text-bad" : "text-good"}`}>
                    {item.delta >= 0 ? "+" : ""}
                    {fmt(item.delta)}
                    {item.dropped ? " FAIL" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="w-full border-collapse text-left text-sm">
            <thead className="font-mono text-xs uppercase text-ink/60">
              <tr>
                <th className="border-b border-rule py-2">Question</th>
                <th className="border-b border-rule py-2">Baseline scores</th>
                <th className="border-b border-rule py-2">Head scores</th>
              </tr>
            </thead>
            <tbody>
              {diff.rows.map((row) => (
                <tr key={row.index}>
                  <td className="border-b border-rule py-2 align-top">{row.question}</td>
                  <td className="border-b border-rule py-2 align-top font-mono text-xs">
                    {row.baseline ? JSON.stringify(row.baseline.metrics) : "—"}
                  </td>
                  <td className="border-b border-rule py-2 align-top font-mono text-xs">
                    {row.head ? JSON.stringify(row.head.metrics) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
