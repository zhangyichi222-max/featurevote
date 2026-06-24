import type { AppView } from "../features/requirements/constants";

export function ViewSwitcher({
  activeView,
  onChange,
}: {
  activeView: AppView;
  onChange: (view: AppView) => void;
}) {
  return (
    <nav className="view-switcher" aria-label="功能切换">
      <button
        className={activeView === "requirements" ? "active" : ""}
        type="button"
        onClick={() => onChange("requirements")}
      >
        需求草稿池
      </button>
      <button className={activeView === "tasks" ? "active" : ""} type="button" onClick={() => onChange("tasks")}>
        任务管理
      </button>
    </nav>
  );
}

