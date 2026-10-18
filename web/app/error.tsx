"use client";

export default function ErrorPage({ retry }: { error: unknown; retry: () => void }) {
  return (
    <main className="app">
      <div className="container app-stack">
        <section className="card">
          <h2>This page could not load.</h2>
          <p className="muted" style={{ marginTop: 6 }}>
            The FinePrint API may be unreachable. Try again in a moment.
          </p>
          <button className="btn btn-ink" type="button" onClick={() => retry()} style={{ marginTop: 14 }}>
            Try again
          </button>
        </section>
      </div>
    </main>
  );
}
