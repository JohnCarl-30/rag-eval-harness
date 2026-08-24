import { NavLink, Outlet } from "react-router-dom";
import { FormEvent, useEffect, useState } from "react";
import { api, getApiKey, setApiKey } from "./api";

export default function App() {
  const [authRequired, setAuthRequired] = useState(false);
  const [key, setKey] = useState(getApiKey());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .auth()
      .then((status) => setAuthRequired(status.required))
      .catch((err: Error) => setError(err.message));
  }, []);

  function saveKey(event: FormEvent) {
    event.preventDefault();
    setApiKey(key);
    setError(null);
    window.location.reload();
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-rule px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-baseline justify-between gap-6">
          <div>
            <p className="font-mono text-xs tracking-[0.2em] uppercase text-accent">rag-eval-harness</p>
            <h1 className="mt-1 text-xl font-semibold">RAGAS with a memory and a diff view</h1>
          </div>
          <nav className="flex gap-4 font-mono text-sm">
            <NavLink to="/" end className={({ isActive }) => (isActive ? "text-accent" : "hover:text-accent")}>
              Datasets
            </NavLink>
            <NavLink to="/runs" className={({ isActive }) => (isActive ? "text-accent" : "hover:text-accent")}>
              Runs
            </NavLink>
            <NavLink to="/diff" className={({ isActive }) => (isActive ? "text-accent" : "hover:text-accent")}>
              Diff
            </NavLink>
          </nav>
        </div>
      </header>
      {authRequired && (
        <form onSubmit={saveKey} className="border-b border-rule bg-white/40 px-6 py-2">
          <div className="mx-auto flex max-w-6xl items-center gap-3 text-sm">
            <span className="font-mono text-xs uppercase">API key</span>
            <input
              className="flex-1 border border-rule bg-paper px-2 py-1 font-mono text-sm"
              value={key}
              onChange={(event) => setKey(event.target.value)}
              placeholder="RAG_EVAL_API_KEY"
            />
            <button className="border border-ink px-3 py-1 text-sm" type="submit">
              Save
            </button>
          </div>
        </form>
      )}
      {error && <p className="mx-auto max-w-6xl px-6 py-3 text-sm text-bad">{error}</p>}
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
