import type { SimilarRequirement } from "../../types/requirement";

export function SimilarRequirementPrompt({
  items,
  isChecking,
  aiEnhanced,
  onOpenExisting,
}: {
  items: SimilarRequirement[];
  isChecking: boolean;
  aiEnhanced: boolean;
  onOpenExisting: (id: string) => void;
}) {
  if (isChecking && !items.length) {
    return <div className="similar-suggestions-box muted">正在检查相似需求草稿...</div>;
  }
  if (!items.length) {
    return null;
  }

  const hasHighSimilarity = items.some((item) => item.is_high_confidence);
  return (
    <section className={`similar-suggestions-box ${hasHighSimilarity ? "strong" : ""}`}>
      <div className="similar-suggestions-header">
        <div>
          <strong>{hasHighSimilarity ? "发现相似需求草稿" : "相关需求草稿"}</strong>
          <span>{aiEnhanced ? "已结合 AI 判断" : "文本相似度匹配"}</span>
        </div>
      </div>
      <div className="similar-suggestions-list">
        {items.map((item) => (
          <button key={item.id} type="button" className="similar-suggestion-item" onClick={() => onOpenExisting(item.id)}>
            <span className="similar-score">{Math.round(item.similarity * 100)}%</span>
            <span className="similar-copy">
              <strong>POST-{item.number}: {item.title}</strong>
              <small>{item.reason || `${item.votes_count} 票`}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

