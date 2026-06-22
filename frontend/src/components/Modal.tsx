import type { ReactNode } from "react";

export function Modal({ children }: { children: ReactNode }) {
  return <div className="modal-backdrop" role="presentation">{children}</div>;
}

export function ModalHeader({ eyebrow, title, onClose, closeLabel = "关闭" }: { eyebrow?: string; title: ReactNode; onClose: () => void; closeLabel?: string }) {
  return (
    <div className="modal-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2>{title}</h2>
      </div>
      <button className="icon-button" type="button" onClick={onClose} aria-label={closeLabel}>
        x
      </button>
    </div>
  );
}
