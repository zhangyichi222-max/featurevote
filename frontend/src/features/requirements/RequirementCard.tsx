import type { Requirement, RequirementStatus } from "../../types/requirement";

type Props = {
  item: Requirement;
  onVote: (requirementId: string) => Promise<void>;
  onStatusChange: (requirementId: string, status: RequirementStatus) => Promise<void>;
};

const statusLabels: Record<RequirementStatus, string> = {
  backlog: "Pending",
  approved: "Approved",
  in_progress: "In Progress",
  done: "Done",
  rejected: "Rejected",
};

export function RequirementCard({ item, onVote, onStatusChange }: Props) {
  return (
    <article className={`request-card request-${item.status}`}>
      <div className="request-main">
        <div className="request-topline">
          <h3>{item.title}</h3>
          <span className={`status-chip status-${item.status}`}>{statusLabels[item.status]}</span>
        </div>
        <p>{item.description}</p>
        <div className="request-meta">
          <span>{item.req_id}</span>
          <span>{item.creator_name || "Anonymous"}</span>
        </div>
        <div className="request-actions">
          <button className="vote-button" type="button" onClick={() => onVote(item.id)}>
            Upvote
          </button>
          <select
            value={item.status}
            onChange={(event) => onStatusChange(item.id, event.target.value as RequirementStatus)}
          >
            <option value="backlog">Pending</option>
            <option value="approved">Approved</option>
            <option value="in_progress">In Progress</option>
            <option value="done">Done</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>
      <aside className="vote-rail" aria-label={`${item.vote_count} votes`}>
        <span className="vote-arrow">▲</span>
        <strong>{item.vote_count}</strong>
      </aside>
    </article>
  );
}
