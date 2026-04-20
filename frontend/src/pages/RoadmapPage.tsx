import { useMemo, useState } from "react";

import type { Requirement, RequirementStatus } from "../types/requirement";

type Props = {
  items: Requirement[];
  onStatusChange: (requirementId: string, status: RequirementStatus) => Promise<void>;
};

type SortMode = "votes" | "recent";

const roadmapColumns: Array<{
  status: RequirementStatus;
  label: string;
  emoji: string;
}> = [
  { status: "backlog", label: "Pending", emoji: "👀" },
  { status: "approved", label: "Approved", emoji: "👍" },
  { status: "in_progress", label: "In Progress", emoji: "🛠️" },
  { status: "done", label: "Done", emoji: "✅" },
  { status: "rejected", label: "Rejected", emoji: "❌" },
];

const statusSequence: RequirementStatus[] = roadmapColumns.map((column) => column.status);

export function RoadmapPage({ items, onStatusChange }: Props) {
  const [sortMode, setSortMode] = useState<SortMode>("votes");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const groupedItems = useMemo(() => {
    return roadmapColumns.map((column) => {
      const columnItems = items
        .filter((item) => item.status === column.status)
        .sort((left, right) => {
          if (sortMode === "votes") {
            return right.vote_count - left.vote_count || right.updated_at.localeCompare(left.updated_at);
          }
          return right.updated_at.localeCompare(left.updated_at);
        });

      return { ...column, items: columnItems };
    });
  }, [items, sortMode]);

  return (
    <section className="roadmap-shell">
      <div className="roadmap-header">
        <div>
          <h1>Roadmap</h1>
        </div>
        <div className="roadmap-controls">
          <span className="session-indicator">Anonymous session</span>
          <select
            className="sort-select"
            value={sortMode}
            onChange={(event) => setSortMode(event.target.value as SortMode)}
          >
            <option value="votes">Sort by Votes</option>
            <option value="recent">Sort by Updated</option>
          </select>
        </div>
      </div>

      <div className="roadmap-grid">
        {groupedItems.map((column) => (
          <section key={column.status} className="roadmap-column">
            <header className="roadmap-column-header">
              <h2>
                {column.label} <span>{column.emoji}</span>
              </h2>
              <span className="column-count">{column.items.length}</span>
            </header>

            <div className="roadmap-card-list">
              {column.items.map((item) => {
                const currentIndex = statusSequence.indexOf(item.status);
                const previousStatus = statusSequence[currentIndex - 1];
                const nextStatus = statusSequence[currentIndex + 1];
                const isExpanded = expandedId === item.id;

                return (
                  <article key={item.id} className="roadmap-card">
                    <div className="roadmap-card-main">
                      <h3>{item.title}</h3>
                      <p className={isExpanded ? "expanded" : ""}>{item.description}</p>
                      <div className="roadmap-card-actions">
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => setExpandedId(isExpanded ? null : item.id)}
                        >
                          {isExpanded ? "Collapse" : "Expand"}
                        </button>
                        <div className="roadmap-move-actions">
                          <button
                            type="button"
                            className="move-button"
                            disabled={!previousStatus}
                            onClick={() => previousStatus && onStatusChange(item.id, previousStatus)}
                          >
                            ←
                          </button>
                          <select
                            value={item.status}
                            onChange={(event) =>
                              onStatusChange(item.id, event.target.value as RequirementStatus)
                            }
                          >
                            {roadmapColumns.map((option) => (
                              <option key={option.status} value={option.status}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="move-button"
                            disabled={!nextStatus}
                            onClick={() => nextStatus && onStatusChange(item.id, nextStatus)}
                          >
                            →
                          </button>
                        </div>
                      </div>
                    </div>
                    <aside className="roadmap-vote-rail">
                      <span className="vote-arrow">▲</span>
                      <strong>{item.vote_count}</strong>
                    </aside>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
