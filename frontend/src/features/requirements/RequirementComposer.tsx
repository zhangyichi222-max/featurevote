import { FormEvent, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { LabelPicker } from "../../components/LabelPicker";
import { Modal } from "../../components/Modal";
import { RichContentEditor } from "../rich-content/RichContentEditor";
import type { RequirementTag, SimilarRequirement } from "../../types/requirement";
import { draftRequirementWithAi, findSimilarRequirements } from "./api";
import type { ComposerField, ComposerStep } from "./constants";
import { SimilarRequirementPrompt } from "./SimilarRequirementPrompt";

export function RequirementComposer({
  isBusy,
  tags,
  onClose,
  onOpenExisting,
  onCreateTag,
  onSubmit,
}: {
  isBusy: boolean;
  tags: RequirementTag[];
  onClose: () => void;
  onOpenExisting: (id: string) => void;
  onCreateTag: (name: string) => Promise<RequirementTag[]>;
  onSubmit: (payload: { title: string; description: string; tags: string[] }) => Promise<void>;
}) {
  const copy = {
    ideaTooShort: "\u8bf7\u81f3\u5c11\u8f93\u5165 20 \u4e2a\u5b57\uff0c\u8ba9 AI \u80fd\u7406\u89e3\u4f60\u7684\u60f3\u6cd5\u3002",
    replaceDraft: "\u91cd\u65b0\u751f\u6210\u4f1a\u8986\u76d6\u5f53\u524d\u6807\u9898\u548c\u63cf\u8ff0\uff0c\u786e\u5b9a\u7ee7\u7eed\u5417\uff1f",
    draftReady: "AI \u5df2\u6574\u7406\u597d\u8349\u7a3f\uff0c\u4f60\u53ef\u4ee5\u7ee7\u7eed\u4fee\u6539\u3002",
    draftFailed: "AI \u751f\u6210\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002",
    titleTooShort: "\u6807\u9898\u81f3\u5c11 3 \u4e2a\u5b57\u3002",
    descriptionRequired: "\u8bf7\u8865\u5145\u9700\u6c42\u8349\u7a3f\u63cf\u8ff0\u3002",
    fixFields: "\u8bf7\u5148\u4fee\u6b63\u6807\u51fa\u7684\u5185\u5bb9\u3002",
    similarFound: "\u53d1\u73b0\u7c7b\u4f3c\u9700\u6c42\u8349\u7a3f\u3002\u4f60\u53ef\u4ee5\u5148\u67e5\u770b\u5df2\u6709\u8349\u7a3f\uff0c\u6216\u518d\u6b21\u70b9\u51fb\u63d0\u4ea4\u3002",
    similarCheckFailed: "\u67e5\u91cd\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002",
    noSimilarFound: "\u672a\u53d1\u73b0\u660e\u663e\u91cd\u590d\u7684\u9700\u6c42\u8349\u7a3f\u3002",
    submitFailed: "\u9700\u6c42\u8349\u7a3f\u63d0\u4ea4\u5931\u8d25\u3002",
    newSuggestion: "\u65b0\u9700\u6c42\u8349\u7a3f",
    ideaTitle: "\u60f3\u63d0\u4ea4\u4ec0\u4e48\u9700\u6c42\u8349\u7a3f\uff1f",
    close: "\u5173\u95ed",
    ideaLabel: "\u5148\u7528\u4e00\u53e5\u8bdd\u8bf4\u6e05\u60f3\u6cd5",
    ideaPlaceholder: "\u4f8b\u5982\uff1a\u5e0c\u671b\u53ef\u4ee5\u6309\u90e8\u95e8\u7b5b\u9009\u6295\u7968\u7ed3\u679c\uff0c\u65b9\u4fbf\u5224\u65ad\u4e0d\u540c\u56e2\u961f\u6700\u5173\u5fc3\u4ec0\u4e48",
    ideaHint: "\u4e0d\u7528\u60f3\u6807\u9898\u548c\u683c\u5f0f\uff0cAI \u4f1a\u5e2e\u4f60\u6574\u7406\u6210\u53ef\u63d0\u4ea4\u7684\u9700\u6c42\u8349\u7a3f\u3002",
    manualStart: "\u76f4\u63a5\u624b\u52a8\u586b\u5199",
    aiWorking: "AI \u6b63\u5728\u6574\u7406...",
    aiDraft: "AI \u5e2e\u6211\u6574\u7406",
    confirmContent: "\u786e\u8ba4\u5185\u5bb9",
    draftTitle: "\u7f16\u8f91\u9700\u6c42\u8349\u7a3f",
    originalIdea: "\u539f\u59cb\u60f3\u6cd5",
    regenerating: "\u91cd\u65b0\u6574\u7406\u4e2d...",
    regenerate: "\u91cd\u65b0\u751f\u6210",
    title: "\u6807\u9898",
    titleHint: "\u81f3\u5c11 3 \u4e2a\u5b57\uff0c\u8ba9\u522b\u4eba\u80fd\u5feb\u901f\u7406\u89e3\u8fd9\u4e2a\u60f3\u6cd5\u3002",
    description: "\u63cf\u8ff0",
    descriptionHint: "\u8865\u5145\u573a\u666f\u3001\u95ee\u9898\u548c\u671f\u671b\u7ed3\u679c\uff0c\u65b9\u4fbf\u56e2\u961f\u8bc4\u4f30\u8fd9\u4efd\u9700\u6c42\u8349\u7a3f\u3002",
    tags: "\u6807\u7b7e",
    newTag: "\u65b0\u589e\u6807\u7b7e",
    tagPlaceholder: "\u8f93\u5165\u65b0\u6807\u7b7e",
    tagCreateFailed: "\u6807\u7b7e\u521b\u5efa\u5931\u8d25\u3002",
    back: "\u8fd4\u56de",
    submitting: "\u63d0\u4ea4\u4e2d...",
    confirmSimilar: "\u786e\u8ba4\u7c7b\u4f3c\u9700\u6c42\u8349\u7a3f",
    checkSimilar: "\u624b\u52a8\u67e5\u91cd",
    checkingSimilar: "\u67e5\u91cd\u4e2d...",
    checkAgain: "\u91cd\u65b0\u67e5\u91cd",
    submitAnyway: "\u4ecd\u7136\u63d0\u4ea4",
    submit: "\u63d0\u4ea4\u9700\u6c42\u8349\u7a3f",
  };
  const [step, setStep] = useState<ComposerStep>("idea");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  const [tagError, setTagError] = useState("");
  const [roughIdea, setRoughIdea] = useState("");
  const [similarItems, setSimilarItems] = useState<SimilarRequirement[]>([]);
  const [isCheckingSimilar, setIsCheckingSimilar] = useState(false);
  const [similarAiEnhanced, setSimilarAiEnhanced] = useState(false);
  const [submitConfirmed, setSubmitConfirmed] = useState(false);
  const [isDrafting, setIsDrafting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [draftNotice, setDraftNotice] = useState("");
  const [isDraftError, setIsDraftError] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<ComposerField, string>>>({});
  const hasHighSimilarity = similarItems.some((item) => item.is_high_confidence);
  const canRegenerate = Boolean(roughIdea.trim());

  async function handleDraft() {
    const trimmedIdea = roughIdea.trim();
    if (trimmedIdea.length < 20) {
      setDraftNotice(copy.ideaTooShort);
      setIsDraftError(true);
      return;
    }

    if (step === "draft" && (title.trim() || description.trim())) {
      const shouldReplace = window.confirm(copy.replaceDraft);
      if (!shouldReplace) {
        return;
      }
    }

    setIsDrafting(true);
    setDraftNotice("");
    setIsDraftError(false);
    try {
      const draft = await draftRequirementWithAi({ idea: trimmedIdea });
      setTitle(draft.title);
      setDescription(draft.description);
      setSubmitConfirmed(false);
      setFieldErrors({});
      setSubmitError("");
      setDraftNotice(copy.draftReady);
      setStep("draft");
    } catch (error) {
      setDraftNotice(error instanceof Error ? error.message : copy.draftFailed);
      setIsDraftError(true);
    } finally {
      setIsDrafting(false);
    }
  }

  function handleManualStart() {
    setStep("draft");
    setSubmitError("");
    setDraftNotice("");
    setIsDraftError(false);
    setFieldErrors({});
  }

  function handleBackToIdea() {
    setStep("idea");
    setSubmitError("");
    setFieldErrors({});
    setSimilarItems([]);
    setSimilarAiEnhanced(false);
    setSubmitConfirmed(false);
  }

  async function handleSimilarityCheck() {
    const trimmedTitle = title.trim();
    const trimmedDescription = description.trim();
    const nextFieldErrors: Partial<Record<ComposerField, string>> = {};

    if (trimmedTitle.length < 3) {
      nextFieldErrors.title = copy.titleTooShort;
    }
    if (!trimmedDescription) {
      nextFieldErrors.description = copy.descriptionRequired;
    }

    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) {
      setSubmitError(copy.fixFields);
      return;
    }

    setIsCheckingSimilar(true);
    setSubmitConfirmed(false);
    setSubmitError("");
    try {
      const data = await findSimilarRequirements({ title: trimmedTitle, description: trimmedDescription, limit: 3 });
      setSimilarItems(data.items);
      setSimilarAiEnhanced(data.ai_enhanced);
      setSubmitError(data.items.length ? "" : copy.noSimilarFound);
    } catch (error) {
      setSimilarItems([]);
      setSimilarAiEnhanced(false);
      setSubmitError(error instanceof Error ? error.message : copy.similarCheckFailed);
    } finally {
      setIsCheckingSimilar(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const nextFieldErrors: Partial<Record<ComposerField, string>> = {};
    const trimmedTitle = title.trim();
    const trimmedDescription = description.trim();

    if (trimmedTitle.length < 3) {
      nextFieldErrors.title = copy.titleTooShort;
    }
    if (!trimmedDescription) {
      nextFieldErrors.description = copy.descriptionRequired;
    }

    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) {
      setSubmitError(copy.fixFields);
      return;
    }

    if (hasHighSimilarity && !submitConfirmed) {
      setSubmitConfirmed(true);
      setSubmitError(copy.similarFound);
      return;
    }

    setSubmitError("");

    try {
      await onSubmit({
        title: trimmedTitle,
        description: trimmedDescription,
        tags: selectedTags,
      });
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitError(error.message);
        setFieldErrors({
          title: error.fieldErrors.title,
          description: error.fieldErrors.description,
        });
        return;
      }

      setSubmitError(error instanceof Error ? error.message : copy.submitFailed);
    }
  }

  if (step === "idea") {
    return (
      <Modal>
        <form
          className="modal-panel composer-panel idea-composer-panel"
          onSubmit={(event) => {
            event.preventDefault();
            handleDraft();
          }}
        >
          <div className="modal-header">
            <div>
              <p className="eyebrow">{copy.newSuggestion}</p>
              <h2>{copy.ideaTitle}</h2>
            </div>
            <button className="icon-button" type="button" onClick={onClose} aria-label={copy.close}>
              x
            </button>
          </div>

          <section className="idea-capture-box">
            <label>
              <span>{copy.ideaLabel}</span>
              <textarea
                value={roughIdea}
                onChange={(event) => {
                  setRoughIdea(event.target.value);
                  setDraftNotice("");
                  setIsDraftError(false);
                }}
                rows={6}
                maxLength={12000}
                placeholder={copy.ideaPlaceholder}
                autoFocus
              />
            </label>
            <small className={isDraftError ? "field-error" : "field-hint"}>
              {draftNotice || copy.ideaHint}
            </small>
          </section>

          <div className="modal-actions idea-actions">
            <button className="secondary-button" type="button" onClick={handleManualStart}>
              {copy.manualStart}
            </button>
            <button className="primary-button" type="submit" disabled={isDrafting || isBusy}>
              {isDrafting ? copy.aiWorking : copy.aiDraft}
            </button>
          </div>
        </form>
      </Modal>
    );
  }

  return (
    <Modal>
      <form className="modal-panel composer-panel" onSubmit={handleSubmit}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">{copy.confirmContent}</p>
            <h2>{copy.draftTitle}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label={copy.close}>
            x
          </button>
        </div>

        {canRegenerate ? (
          <section className="draft-source-box" aria-label={copy.originalIdea}>
            <div>
              <span>{copy.originalIdea}</span>
              <p>{roughIdea.trim()}</p>
            </div>
            <button className="secondary-button" type="button" onClick={handleDraft} disabled={isDrafting || isBusy}>
              {isDrafting ? copy.regenerating : copy.regenerate}
            </button>
          </section>
        ) : null}

        {draftNotice && !isDraftError ? <div className="draft-notice">{draftNotice}</div> : null}

        <label>
          <span>{copy.title}</span>
          <input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              setSubmitConfirmed(false);
              setSimilarItems([]);
              setSimilarAiEnhanced(false);
              setFieldErrors((current) => ({ ...current, title: undefined }));
              setSubmitError("");
            }}
            maxLength={120}
            minLength={3}
            required
            aria-invalid={Boolean(fieldErrors.title)}
            className={fieldErrors.title ? "input-error" : ""}
            autoFocus={!canRegenerate}
          />
          <small className={fieldErrors.title ? "field-error" : "field-hint"}>
            {fieldErrors.title ?? copy.titleHint}
          </small>
        </label>
        <div className="rich-field">
          <span>{copy.description}</span>
          <RichContentEditor
            value={description}
            onChange={(nextValue) => {
              setDescription(nextValue);
              setSubmitConfirmed(false);
              setSimilarItems([]);
              setSimilarAiEnhanced(false);
              setFieldErrors((current) => ({ ...current, description: undefined }));
              setSubmitError("");
            }}
            minRows={7}
          />
          <small className={fieldErrors.description ? "field-error" : "field-hint"}>
            {fieldErrors.description ?? copy.descriptionHint}
          </small>
        </div>
        <div className="composer-field">
          <span>{copy.tags}</span>
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
              placeholder={copy.tagPlaceholder}
            />
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                const name = newTag.trim();
                if (!name) return;
                onCreateTag(name)
                  .then(() => {
                    setSelectedTags((current) => [...new Set([...current, name])]);
                    setNewTag("");
                  })
                  .catch((error: Error) => setTagError(error.message || copy.tagCreateFailed));
              }}
            >
              {copy.newTag}
            </button>
          </div>
          {tagError ? <small className="field-error">{tagError}</small> : null}
        </div>
        <div className="similar-check-actions">
          <button className="secondary-button" type="button" onClick={handleSimilarityCheck} disabled={isCheckingSimilar || isBusy}>
            {isCheckingSimilar ? copy.checkingSimilar : similarItems.length ? copy.checkAgain : copy.checkSimilar}
          </button>
        </div>
        <SimilarRequirementPrompt
          items={similarItems}
          isChecking={isCheckingSimilar}
          aiEnhanced={similarAiEnhanced}
          onOpenExisting={onOpenExisting}
        />
        {submitError ? <div className="form-error">{submitError}</div> : null}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={handleBackToIdea}>
            {copy.back}
          </button>
          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? copy.submitting : hasHighSimilarity && !submitConfirmed ? copy.confirmSimilar : submitConfirmed ? copy.submitAnyway : copy.submit}
          </button>
        </div>
      </form>
    </Modal>
  );
}

