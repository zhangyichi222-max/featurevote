import { useMemo, useState } from "react";

import { RequirementCard } from "../features/requirements/RequirementCard";
import { RequirementSubmitForm } from "../features/requirements/RequirementSubmitForm";
import type { Requirement, RequirementStatus } from "../types/requirement";

const statusOptions: Array<{ value: "all" | RequirementStatus; label: string }> = [
  { value: "all", label: "All requests" },
  { value: "backlog", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "in_progress", label: "In Progress" },
  { value: "done", label: "Done" },
  { value: "rejected", label: "Rejected" },
];

type Props = {
  items: Requirement[];
  message: string;
  onCreate: (payload: {
    title: string;
    description: string;
    creator_name: string;
    creator_open_id: string;
  }) => Promise<void>;
  onVote: (requirementId: string) => Promise<void>;
  onStatusChange: (requirementId: string, status: RequirementStatus) => Promise<void>;
};

export function RequirementBoardPage({ items, message, onCreate, onVote, onStatusChange }: Props) {
  const [statusFilter, setStatusFilter] = useState<"all" | RequirementStatus>("all");

  const filteredItems = useMemo(() => {
    if (statusFilter === "all") {
      return items;
    }
    return items.filter((item) => item.status === statusFilter);
  }, [items, statusFilter]);

  return (
    <section className="workspace">
      <aside className="composer-column">
        <div className="intro-copy">
          <p className="eyebrow">Local SQLite Demo</p>
          <h1>Feature request board</h1>
          <p>
            Collect ideas, surface the best requests, and keep everyone aligned with a cleaner
            internal workflow.
          </p>
        </div>
        <RequirementSubmitForm onSubmit={onCreate} />
      </aside>

      <section className="board-column">
        <div className="board-panel">
          <div className="board-toolbar">
            <select
              aria-label="Filter requests by status"
              className="status-filter"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as "all" | RequirementStatus)}
            >
              {statusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <div className="board-message">{message}</div>
          </div>

          <div className="request-list">
            {filteredItems.map((item) => (
              <RequirementCard
                key={item.id}
                item={item}
                onVote={onVote}
                onStatusChange={onStatusChange}
              />
            ))}
            {!filteredItems.length ? (
              <div className="empty-state">
                <strong>No requests in this view.</strong>
                <span>Try another filter or submit a new request from the left panel.</span>
              </div>
            ) : null}
          </div>

          <footer className="board-footer">
            <span className="session-indicator">Anonymous session</span>
            <span className="powered-by">Powered by SQLite</span>
          </footer>
        </div>
      </section>
    </section>
  );
}
