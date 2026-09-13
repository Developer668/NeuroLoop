import LoadingState from "./loading-state";

/** Isolated preview; production loading is driven by the creative request. */
export default function LoadingStateDemo() {
  return <div style={{ display: "grid", gap: 28, padding: 32 }}>
    <LoadingState label="Churning" variant="Drive" />
    <LoadingState label="Thinking" variant="Dots" />
    <LoadingState label="Searching" variant="Orbit" />
  </div>;
}
