import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Dataset, api } from "../api";

export default function DatasetDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [rows, setRows] = useState<Array<{ question: string; ground_truth: string | null }>>([]);
  const [adapter, setAdapter] = useState<"traces" | "http">("traces");
  const [evaluator, setEvaluator] = useState<"stub" | "ragas">("stub");
  const [sutUrl, setSutUrl] = useState("http://127.0.0.1:8080/query");
  const [sutToken, setSutToken] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!id) return;
    api.dataset(id).then(setDataset).catch((err: Error) => setError(err.message));
    api.datasetRows(id).then(setRows).catch((err: Error) => setError(err.message));
  }, [id]);

  async function onRun(event: FormEvent) {
    event.preventDefault();
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const run = await api.createRun({
        dataset_id: id,
        adapter,
        evaluator,
        sut_url: adapter === "http" ? sutUrl : undefined,
        sut_token: sutToken || undefined,
        label: label || undefined,
      });
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setBusy(false);
    }
  }

  if (!dataset) return <p className="text-sm">{error || "Loading…"}</p>;

  return (
    <div className="space-y-8">
      <div>
        <Link to="/" className="font-mono text-xs text-accent">
          ← datasets
        </Link>
        <h2 className="mt-2 text-2xl font-semibold">{dataset.name}</h2>
        <p className="font-mono text-xs text-ink/50">
          {dataset.row_count} rows · {dataset.id}
        </p>
      </div>
      <form onSubmit={onRun} className="grid gap-4 border border-rule bg-white/50 p-6 md:grid-cols-2">
        <label className="text-sm">
          Adapter
          <select
            className="mt-1 block w-full border border-rule bg-paper px-2 py-1"
            value={adapter}
            onChange={(event) => setAdapter(event.target.value as "traces" | "http")}
          >
            <option value="traces">Precomputed traces</option>
            <option value="http">HTTP SUT</option>
          </select>
        </label>
        <label className="text-sm">
          Evaluator
          <select
            className="mt-1 block w-full border border-rule bg-paper px-2 py-1"
            value={evaluator}
            onChange={(event) => setEvaluator(event.target.value as "stub" | "ragas")}
          >
            <option value="stub">stub (deterministic, no key)</option>
            <option value="ragas">ragas (OpenAI-compatible judge)</option>
          </select>
        </label>
        {adapter === "http" && (
          <>
            <label className="text-sm md:col-span-2">
              SUT URL
              <input
                className="mt-1 block w-full border border-rule bg-paper px-2 py-1 font-mono text-sm"
                value={sutUrl}
                onChange={(event) => setSutUrl(event.target.value)}
              />
            </label>
            <label className="text-sm md:col-span-2">
              Optional bearer token
              <input
                className="mt-1 block w-full border border-rule bg-paper px-2 py-1 font-mono text-sm"
                value={sutToken}
                onChange={(event) => setSutToken(event.target.value)}
              />
            </label>
          </>
        )}
        <label className="text-sm md:col-span-2">
          Label
          <input
            className="mt-1 block w-full border border-rule bg-paper px-2 py-1"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="main, pr-12, nightly…"
          />
        </label>
        <div className="md:col-span-2">
          <button className="border border-ink bg-ink px-4 py-2 text-sm text-paper" disabled={busy} type="submit">
            {busy ? "Starting…" : "Create run"}
          </button>
          {error && <p className="mt-2 text-sm text-bad">{error}</p>}
        </div>
      </form>
      <table className="w-full border-collapse text-left text-sm">
        <thead className="font-mono text-xs uppercase text-ink/60">
          <tr>
            <th className="border-b border-rule py-2">Question</th>
            <th className="border-b border-rule py-2">Ground truth</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              <td className="border-b border-rule py-2 align-top">{row.question}</td>
              <td className="border-b border-rule py-2 align-top text-ink/70">{row.ground_truth || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
