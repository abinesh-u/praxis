export default function HomePage() {
  return (
    <main style={{ maxWidth: "720px", margin: "0 auto", lineHeight: "1.6" }}>
      <h1>Praxis</h1>
      <p style={{ color: "#555" }}>
        Personal AI execution partner — turn commitments into completed work.
      </p>
      <section style={{ border: "1px solid #ddd", borderRadius: "8px", padding: "1.25rem", marginTop: "1.5rem" }}>
        <h2>System Status</h2>
        <p>Command center frontend initialized. API endpoint defaults to <code>http://localhost:8000</code>.</p>
      </section>
    </main>
  );
}
