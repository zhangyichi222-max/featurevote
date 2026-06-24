import type { CurrentUser } from "../types/requirement";

export function Header({
  currentUser,
  isAuthLoading,
  isBusy,
  onLogin,
  onLogout,
}: {
  currentUser: CurrentUser | null;
  isAuthLoading: boolean;
  isBusy: boolean;
  onLogin: () => void;
  onLogout: () => Promise<void>;
}) {
  return (
    <header className="topbar">
      <div className="brand-mark" aria-label="需求草稿池">
        <span>需</span>
        <strong>需求草稿池</strong>
      </div>
      <div className="auth-controls">
        {currentUser ? (
          <>
            <div className="user-pill">
              <strong>{currentUser.name}</strong>
              <span>成员</span>
            </div>
            <button className="secondary-button" type="button" onClick={onLogout} disabled={isBusy}>
              退出登录
            </button>
          </>
        ) : (
          <button className="primary-button" type="button" onClick={onLogin} disabled={isAuthLoading}>
            {isAuthLoading ? "检查登录中..." : "飞书登录"}
          </button>
        )}
      </div>
    </header>
  );
}

