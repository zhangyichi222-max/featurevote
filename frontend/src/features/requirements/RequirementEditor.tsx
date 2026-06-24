import { FormEvent, useState } from "react";

import { ApiError } from "../../api/client";
import { LabelPicker } from "../../components/LabelPicker";
import { Modal } from "../../components/Modal";
import type { Requirement, RequirementTag } from "../../types/requirement";
import { RichContentEditor } from "../rich-content/RichContentEditor";

export function RequirementEditor({
  item,
  tags,
  isBusy,
  onClose,
  onCreateTag,
  onSave,
}: {
  item: Requirement;
  tags: RequirementTag[];
  isBusy: boolean;
  onClose: () => void;
  onCreateTag: (name: string) => Promise<RequirementTag[]>;
  onSave: (payload: { title: string; description: string; tags: string[] }) => Promise<void>;
}) {
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description);
  const [selectedTags, setSelectedTags] = useState(item.tags.map((tag) => tag.name));
  const [newTag, setNewTag] = useState("");
  const [tagError, setTagError] = useState("");
  const [isCreatingTag, setIsCreatingTag] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  async function handleCreateTag() {
    const name = newTag.trim();
    if (!name || isCreatingTag) {
      return;
    }
    setIsCreatingTag(true);
    setTagError("");
    try {
      await onCreateTag(name);
      setSelectedTags((current) => [...new Set([...current, name])]);
      setNewTag("");
    } catch (createError) {
      setTagError(createError instanceof Error ? createError.message : "标签创建失败。");
    } finally {
      setIsCreatingTag(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmedTitle = title.trim();
    const trimmedDescription = description.trim();
    const nextErrors: Record<string, string> = {};
    if (trimmedTitle.length < 3) {
      nextErrors.title = "标题至少 3 个字。";
    }
    if (!trimmedDescription) {
      nextErrors.description = "请补充需求草稿描述。";
    }
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      setError("请先修正标出的内容。");
      return;
    }

    setError("");
    try {
      await onSave({
        title: trimmedTitle,
        description: trimmedDescription,
        tags: selectedTags,
      });
    } catch (saveError) {
      if (saveError instanceof ApiError) {
        setError(saveError.message);
        setFieldErrors(saveError.fieldErrors);
        return;
      }
      setError(saveError instanceof Error ? saveError.message : "需求草稿保存失败。");
    }
  }

  return (
    <Modal>
      <form className="modal-panel composer-panel requirement-editor" onSubmit={handleSubmit}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">编辑需求草稿</p>
            <h2>{item.req_id}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭">
            x
          </button>
        </div>

        <label>
          <span>标题</span>
          <input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              setFieldErrors((current) => ({ ...current, title: "" }));
              setError("");
            }}
            minLength={3}
            maxLength={120}
            required
            autoFocus
            aria-invalid={Boolean(fieldErrors.title)}
            className={fieldErrors.title ? "input-error" : ""}
          />
          <small className={fieldErrors.title ? "field-error" : "field-hint"}>
            {fieldErrors.title || "至少 3 个字，让别人能快速理解这份需求草稿。"}
          </small>
        </label>

        <div className="rich-field">
          <span>描述</span>
          <RichContentEditor
            value={description}
            onChange={(value) => {
              setDescription(value);
              setFieldErrors((current) => ({ ...current, description: "" }));
              setError("");
            }}
            minRows={7}
          />
          <small className={fieldErrors.description ? "field-error" : "field-hint"}>
            {fieldErrors.description || "补充场景、问题和期望结果。"}
          </small>
        </div>

        <div className="composer-field">
          <span>标签</span>
          <LabelPicker
            labels={tags}
            selectedNames={selectedTags}
            onToggle={(name) => {
              setSelectedTags((current) =>
                current.includes(name) ? current.filter((selectedName) => selectedName !== name) : [...current, name],
              );
            }}
          />
          <div className="new-label-row">
            <input
              value={newTag}
              onChange={(event) => {
                setNewTag(event.target.value);
                setTagError("");
              }}
              placeholder="输入新标签"
              maxLength={80}
            />
            <button
              className="secondary-button"
              type="button"
              onClick={handleCreateTag}
              disabled={!newTag.trim() || isCreatingTag || isBusy}
            >
              {isCreatingTag ? "创建中..." : "新增标签"}
            </button>
          </div>
          {tagError ? <small className="field-error">{tagError}</small> : null}
        </div>

        {error ? <div className="form-error">{error}</div> : null}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? "保存中..." : "保存需求草稿"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
