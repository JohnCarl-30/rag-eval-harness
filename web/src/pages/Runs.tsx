import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Run, api, fmt } from "../api";

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .runs()
      .then(setRuns)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) return <p className="text-sm text-bad">{error}</p>;

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">Runs</h2>
      {runs.length === 0 ? (
        <p className="text-sm text-ink/60">No runs yet.</p>
      ) : (
        <table className="w-full border-collapse text-left text-sm">
          <thead className="font-mono text-xs uppercase text-ink/60">
            <tr>
              <th className="border-b border-rule py-2">Run</th>
              <th className="border-b border-rule py-2">Status</th>
              <th className="border-b border-rule py-2">Eval</th>
              <th className="border-b border-rule py-2">Faithfulness</th>
              <th className="border-b border-rule py-2">Relevancy</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="hover:bg-white/60">
                <td className="border-b border-rule py-2">
                  <Link className="text-accent underline" to={`/runs/${run.id}`}>
                    {run.label || run.id.slice(0, 8)}
                  </Link>
                  {run.is_baseline && (
                    <span className="ml-2 font-mono text-[10px] uppercase tracking-wide text-good">
                      baseline
                    </span>
                  )}
                  <div className="font-mono text-xs text-ink/50">{run.adapter_type}</div>
                </td>
                <td className="border-b border-rule py-2">{run.status}</td>
                <td className="border-b border-rule py-2">{run.evaluator}</td>
                <td className="border-b border-rule py-2 font-mono">{fmt(run.means?.faithfulness)}</td>
                <td className="border-b border-rule py-2 font-mono">{fmt(run.means?.answer_relevancy)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
