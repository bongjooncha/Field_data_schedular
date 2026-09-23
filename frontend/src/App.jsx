import { useEffect, useState } from "react";
import { getStatus } from "./api";
import Dashboard from "./pages/Dashboard";
import Wizard from "./pages/Wizard";

export default function App() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("home");

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

  if (!status.setupComplete || mode === "settings" || mode === "add") {
    const wizardMode = status.setupComplete ? mode : "setup";
    return (
      <Wizard
        key={`${wizardMode}-${status.config.activeSourceId || "new"}`}
        status={status}
        mode={wizardMode}
        onDone={async () => {
          await refresh();
          setMode("home");
        }}
        onCancel={status.setupComplete ? () => setMode("home") : null}
        onRefresh={refresh}
      />
    );
  }

  return (
    <Dashboard
      status={status}
      onEdit={() => setMode("settings")}
      onAdd={() => setMode("add")}
      onStatus={setStatus}
    />
  );
}
