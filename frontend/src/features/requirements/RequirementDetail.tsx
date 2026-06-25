import { useEffect, useState } from "react";

import { RichContentPreview } from "../rich-content/RichContentEditor";
import type { Requirement, RequirementSourceGroup } from "../../types/requirement";
import { fetchRequirementSources } from "./api";

export function RequirementDetail({
  item,
  isBusy,
  onVote,
  onConvert,
  onArchive,
  onEdit,
  canEdit,
  canManage,
  canViewSources,
}: {
  item: Requirement | null;
  isBusy: boolean;
  onVote: (id: string) => Promise<void>;
  onConvert: (item: Requirement) => void;
  onArchive: (id: string) => Promise<void>;
  onEdit: (item: Requirement) => void;
  canEdit: boolean;
  canManage: boolean;
  canViewSources: boolean;
}) {
  const [sourceGroups, setSourceGroups] = useState<RequirementSourceGroup[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState("");

  useEffect(() => {
    let active = true;
    setSourceGroups([]);
    setSourcesError("");
    if (!item || !canViewSources) {
      return () => {
        active = false;
      };
    }
    setSourcesLoading(true);
    fetchRequirementSources(item.id)
      .then((response) => {
        if (active) setSourceGroups(response.groups);
      })
      .catch(() => {
        if (active) setSourcesError("飞书来源加载失败，请稍后重试。");
      })
      .finally(() => {
        if (active) setSourcesLoading(false);
      });
    return () => {
      active = false;
    };
  }, [item?.id, canViewSources]);

  if (!item) {
    return (
      <aside className="requirement-detail requirement-detail-empty">
        <h3>草稿详情</h3>
        <p>选择一份需求草稿查看详情。</p>
      </aside>
    );
  }

  return (
    <aside className="requirement-detail" aria-label="需求草稿详情">
      <div className="requirement-detail-header">
        <div>
          <span className="requirement-detail-key">{item.req_id}</span>
          <h3>{item.title}</h3>
        </div>
        {canEdit ? (
          <button className="secondary-button" type="button" onClick={() => onEdit(item)} disabled={isBusy}>
            编辑
          </button>
        ) : null}
      </div>
      <div className="requirement-detail-actions">
        <button
          className={`requirement-detail-vote ${item.has_voted ? "voted" : ""}`}
          type="button"
          onClick={() => onVote(item.id)}
          disabled={isBusy}
        >
          <span>^</span>
          {item.has_voted ? "已投票" : "投票"} · {item.vote_count}
        </button>
        {canManage ? (
          <>
            <button className="primary-button" type="button" onClick={() => onConvert(item)} disabled={isBusy}>
              采纳并创建任务
            </button>
            <button className="danger-button" type="button" onClick={() => onArchive(item.id)} disabled={isBusy}>
              删除
            </button>
          </>
        ) : null}
      </div>
      <div className="requirement-properties">
        <div className="requirement-property-row">
          <span>提交人</span>
          <strong>{item.creator_name}</strong>
        </div>
        <div className="requirement-property-row requirement-property-labels">
          <span>标签</span>
          <div className="requirement-labels detail-labels">
            {item.tags.length ? item.tags.map((tag) => (
              <small key={tag.id} style={{ borderColor: tag.color }}>
                <span className="label-dot" style={{ backgroundColor: tag.color }} />
                {tag.name}
              </small>
            )) : <em>无</em>}
          </div>
        </div>
      </div>
      <section className="requirement-description-panel">
        <h4>描述</h4>
        <RichContentPreview markdown={item.description || "暂无描述。"} />
      </section>
      {canViewSources && (sourcesLoading || sourcesError || sourceGroups.length > 0) ? (
        <details className="requirement-sources" open={sourceGroups.length > 0}>
          <summary>
            飞书来源
            {sourceGroups.length ? <span>{sourceGroups.reduce((sum, group) => sum + group.messages.length, 0)} 条消息</span> : null}
          </summary>
          {sourcesLoading ? <p className="requirement-source-state">正在加载来源...</p> : null}
          {sourcesError ? <p className="requirement-source-state error">{sourcesError}</p> : null}
          {!sourcesLoading ? sourceGroups.map((group) => (
            <section className="requirement-source-group" key={`${group.chat_id}:${group.key}`}>
              <header>
                <strong>{group.chat_name}</strong>
                <span>{group.kind === "thread" ? "回复线程" : "时间窗口"}</span>
              </header>
              <div className="requirement-source-messages">
                {group.messages.map((message) => (
                  <article
                    className={`requirement-source-message ${message.is_direct_source ? "direct" : ""}`}
                    key={message.message_id}
                  >
                    <div>
                      <strong>{message.sender_name || formatSenderId(message.sender_open_id)}</strong>
                      <time>{formatSourceTime(message.sent_at)}</time>
                      {message.is_direct_source ? <em>直接来源</em> : null}
                    </div>
                    <p>{message.raw_text}</p>
                  </article>
                ))}
              </div>
            </section>
          )) : null}
        </details>
      ) : null}
    </aside>
  );
}

function formatSourceTime(value?: string | null) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatSenderId(value?: string | null) {
  if (!value) return "未知成员";
  if (value.length <= 18) return value;
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

