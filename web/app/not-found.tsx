import Link from "next/link";

export default function NotFound() {
  return (
    <main className="app">
      <div className="container app-stack">
        <section className="card">
          <h2>This page is not a model report.</h2>
          <p className="muted" style={{ marginTop: 6 }}>
            FinePrint reads model pages. Open one by replacing <span className="mono">huggingface.co</span> with this
            site&apos;s domain in a model URL, or search from the{" "}
            <Link className="link" href="/#check">
              home page
            </Link>
            .
          </p>
        </section>
      </div>
    </main>
  );
}
