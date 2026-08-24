import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Dataset, api } from "../api";

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function reload() {
    api
      .datasets()
      .then(setDatasets)
      .catch((err: Error) => setError(err.message));
  }

  useEffect(reload, []);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await api.uploadDataset(file);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <section className="border border-rule bg-white/50 p-6">
        <h2 className="text-lg font-semibold">Upload a golden set</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink/70">
          CSV, JSONL, or JSON. <code>question</code> is required; <code>ground_truth</code>,{" "}
          <code>answer</code>, and <code>retrieved_contexts</code> are optional. Aliases like{" "}
          <code>user_input</code> / <code>reference</code> work. Cap is 100 rows.
        </p>
        <label className="mt-4 flex cursor-pointer items-center justify-center border border-dashed border-ink/40 px-4 py-10 text-sm">
          {busy ? "Uploading…" : "Drop a file or click to choose"}
          <input
            className="hidden"
            type="file"
            accept=".csv,.jsonl,.json,.ndjson"
            onChange={(event) => onFile(event.target.files?.[0])}
          />
        </label>
        {error && <p className="mt-3 text-sm text-bad">{error}</p>}
      </section>
      <section>
        <h2 className="mb-3 text-lg font-semibold">Datasets</h2>
        {datasets.length === 0 ? (
          <p className="text-sm text-ink/60">None yet. Upload golden.csv from examples/dummy-rag to start.</p>
        ) : (
          <table className="w-full border-collapse text-left text-sm">
            <thead className="font-mono text-xs uppercase text-ink/60">
              <tr>
                <th className="border-b border-rule py-2">Name</th>
                <th className="border-b border-rule py-2">Rows</th>
                <th className="border-b border-rule py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((dataset) => (
                <tr key={dataset.id} className="hover:bg-white/60">
                  <td className="border-b border-rule py-2">
                    <Link className="text-accent underline" to={`/datasets/${dataset.id}`}>
                      {dataset.name}
                    </Link>
                    <div className="font-mono text-xs text-ink/50">{dataset.id}</div>
                  </td>
                  <td className="border-b border-rule py-2">{dataset.row_count}</td>
                  <td className="border-b border-rule py-2 font-mono text-xs">{dataset.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
