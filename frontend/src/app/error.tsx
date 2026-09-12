"use client";
export default function ErrorBoundary({
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <main className="error-page">
      <span className="eyebrow">WORKSPACE ERROR</span>
      <h1>This view could not load.</h1>
      <p>Your stored assets and completed experiments have not been changed.</p>
      <button className="button primary" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
