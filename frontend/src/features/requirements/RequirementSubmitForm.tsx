import { FormEvent, useState } from "react";

type Props = {
  onSubmit: (payload: {
    title: string;
    description: string;
    creator_name: string;
    creator_open_id: string;
  }) => Promise<void>;
};

export function RequirementSubmitForm({ onSubmit }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [creatorName, setCreatorName] = useState("");
  const [creatorOpenId, setCreatorOpenId] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await onSubmit({
        title,
        description,
        creator_name: creatorName,
        creator_open_id: creatorOpenId,
      });
      setTitle("");
      setDescription("");
      setCreatorName("");
      setCreatorOpenId("");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="composer-card" onSubmit={handleSubmit}>
      <label className="field">
        <span className="field-label">Title</span>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="My awesome feature request"
          required
        />
      </label>

      <label className="field">
        <span className="field-row">
          <span className="field-label">Description</span>
          <span className="field-helper">Format</span>
        </span>
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Input description here"
          rows={6}
          required
        />
      </label>

      <label className="field">
        <span className="field-label">
          Name <em>(optional)</em>
        </span>
        <input
          value={creatorName}
          onChange={(event) => setCreatorName(event.target.value)}
          placeholder="Who is submitting this request?"
        />
      </label>

      <label className="field">
        <span className="field-label">
          User ID <em>(optional)</em>
        </span>
        <input
          value={creatorOpenId}
          onChange={(event) => setCreatorOpenId(event.target.value)}
          placeholder="A stable ID for duplicate-vote checks"
        />
      </label>

      <div className="upload-placeholder" aria-hidden="true">
        <div className="upload-icon">↑</div>
        <div>
          <strong>Attach file</strong>
          <p>Click to upload or drag and drop. Visual only for now.</p>
        </div>
      </div>

      <button className="submit-button" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Submitting..." : "Submit"}
      </button>
    </form>
  );
}
