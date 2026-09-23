import { useEffect, useState } from "react";
import { getStatus } from "./api";
import Dashboard from "./pages/Dashboard";
import Wizard from "./pages/Wizard";

export default function App() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);

  async function refresh() {
    const next = await getStatus();
    setStatus(next);
    setError("");
    return next;
  }

  useEffect(() => {
    refresh().catch((err) => setError(err.message));
  }, []);

  if (!status) {
    return (
      <div className="boot">
        <span className="brand-mark" aria-hidden="true" />
        <p>{error || "화면을 준비하고 있습니다."}</p>
        {error ? (
          <button className="btn btn-primary" type="button" onClick={() => refresh().catch((err) => setError(err.message))}>
            다시 시도
          </button>
        ) : null}
      </div>
    );
  }

  if (!status.setupComplete || editing) {
    return (
      <Wizard
        status={status}
        onDone={async () => {
          await refresh();
          setEditing(false);
        }}
        onCancel={status.setupComplete ? () => setEditing(false) : null}
      />
    );
  }

  return (
    <Dashboard
      status={status}
      onEdit={() => setEditing(true)}
      onStatus={setStatus}
    />
  );
}
