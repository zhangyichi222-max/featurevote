import { useEffect, useState } from "react";

import {
  createRequirement,
  fetchRequirements,
  updateRequirementStatus,
  voteRequirement,
} from "./features/requirements/api";
import { RequirementBoardPage } from "./pages/RequirementBoardPage";
import { RoadmapPage } from "./pages/RoadmapPage";
import type { Requirement, RequirementStatus } from "./types/requirement";

type ActiveView = "requests" | "roadmap";

export default function App() {
  const [activeView, setActiveView] = useState<ActiveView>("requests");
  const [items, setItems] = useState<Requirement[]>([]);
  const [message, setMessage] = useState("Loading requests...");

  async function loadRequirements() {
    const data = await fetchRequirements();
    setItems(data.items);
    setMessage(data.items.length ? "Live board synced with local SQLite." : "No requests yet. Add the first one.");
  }

  useEffect(() => {
    loadRequirements().catch((error: Error) => {
      setMessage(error.message);
    });
  }, []);

  async function handleCreate(payload: {
    title: string;
    description: string;
    creator_name: string;
    creator_open_id: string;
  }) {
    await createRequirement(payload);
    setMessage("Request submitted successfully.");
    await loadRequirements();
  }

  async function handleVote(requirementId: string) {
    await voteRequirement(requirementId, {
      voter_name: "Demo User",
      voter_open_id: "demo-user",
    });
    setMessage("Vote recorded.");
    await loadRequirements();
  }

  async function handleStatusChange(requirementId: string, status: RequirementStatus) {
    await updateRequirementStatus(requirementId, { status });
    setMessage(`Status updated to ${status.replace("_", " ")}.`);
    await loadRequirements();
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">Internal AI Tools</div>
        <nav className="topnav" aria-label="Primary">
          <button
            className={`nav-pill ${activeView === "requests" ? "nav-pill-active" : ""}`}
            type="button"
            onClick={() => setActiveView("requests")}
          >
            Feature Requests
          </button>
          <button
            className={`nav-pill ${activeView === "roadmap" ? "nav-pill-active" : ""}`}
            type="button"
            onClick={() => setActiveView("roadmap")}
          >
            Roadmap
          </button>
        </nav>
        <button className="theme-toggle" type="button" aria-label="Open settings">
          <span />
        </button>
      </header>

      {activeView === "requests" ? (
        <RequirementBoardPage
          items={items}
          message={message}
          onCreate={handleCreate}
          onVote={handleVote}
          onStatusChange={handleStatusChange}
        />
      ) : (
        <RoadmapPage items={items} onStatusChange={handleStatusChange} />
      )}
    </main>
  );
}
