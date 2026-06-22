export interface PickableLabel {
  id?: string;
  slug?: string;
  name: string;
  color: string;
}

export function LabelPicker({
  labels,
  selectedNames,
  disabled = false,
  onToggle,
  onDelete,
}: {
  labels: PickableLabel[];
  selectedNames: string[];
  disabled?: boolean;
  onToggle: (name: string) => void;
  onDelete?: (label: PickableLabel) => void;
}) {
  return (
    <div className="label-picker">
      {labels.map((label) => {
        const selected = selectedNames.includes(label.name);
        const key = label.id ?? label.slug ?? label.name;
        return (
          <div
            key={key}
            className="label-choice"
            role="checkbox"
            aria-checked={selected}
            tabIndex={disabled ? -1 : 0}
            onClick={() => {
              if (!disabled) onToggle(label.name);
            }}
            onKeyDown={(event) => {
              if (event.key !== " " && event.key !== "Enter") return;
              event.preventDefault();
              if (!disabled) onToggle(label.name);
            }}
          >
            <input type="checkbox" checked={selected} disabled={disabled} readOnly />
            <span className="label-dot" style={{ backgroundColor: label.color }} />
            <span>{label.name}</span>
            {onDelete && !disabled ? (
              <button
                className="label-delete-button"
                type="button"
                aria-label={`删除标签 ${label.name}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(label);
                }}
              >
                ?
              </button>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
