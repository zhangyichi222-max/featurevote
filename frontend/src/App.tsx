import { useEffect, useState } from "react";

import { AUTH_EXPIRED_EVENT, ApiError, startFeishuBrowserLogin } from "./api/client";
import { Header } from "./components/Header";
import { ViewSwitcher } from "./components/ViewSwitcher";
import { RequirementPage } from "./features/requirements/RequirementPage";
import { exchangeFeishuClientCode, fetchCurrentUser, logoutCurrentUser } from "./features/requirements/api";
import type { AppView } from "./features/requirements/constants";
import { TaskPage } from "./features/tasks/TaskPage";
import type { CurrentUser } from "./types/requirement";

export default function App() {
  const [notice, setNotice] = useState("正在加载建议...");
  const [isBusy, setIsBusy] = useState(false);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [activeView, setActiveView] = useState<AppView>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("view") === "tasks" ? "tasks" : "requirements";
  });

  async function loadCurrentUser(showExpiredNotice = false) {
    try {
      setCurrentUser(await fetchCurrentUser());
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        if (showExpiredNotice) {
          setNotice("登录已过期，请重新登录。");
        }
        setCurrentUser(null);
        return;
      }
      setNotice(error instanceof Error ? error.message : "无法加载当前用户。");
    } finally {
      setIsAuthLoading(false);
    }
  }

  useEffect(() => {
    loadCurrentUser();
  }, []);

  useEffect(() => {
    if (!currentUser) {
      return;
    }

    const handleAuthExpired = () => {
      setCurrentUser(null);
      setNotice("登录已过期，请重新登录。");
    };

    const handleFocus = () => {
      loadCurrentUser(true);
    };

    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    window.addEventListener("focus", handleFocus);
    const intervalId = window.setInterval(() => loadCurrentUser(true), 5 * 60 * 1000);

    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
      window.removeEventListener("focus", handleFocus);
      window.clearInterval(intervalId);
    };
  }, [currentUser]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("feishu_client_code");
    if (!code) {
      return;
    }

    exchangeFeishuClientCode(code)
      .then(() => loadCurrentUser())
      .then(() => {
        params.delete("feishu_client_code");
        const nextSearch = params.toString();
        window.history.replaceState(null, "", `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`);
        setNotice("已通过飞书登录。");
      })
      .catch((error: Error) => setNotice(error.message));
  }, []);

  async function handleLogout() {
    setIsBusy(true);
    try {
      await logoutCurrentUser();
      setCurrentUser(null);
      setNotice("已退出登录，仍可继续浏览。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "退出登录失败。");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <Header
        currentUser={currentUser}
        isAuthLoading={isAuthLoading}
        isBusy={isBusy}
        onLogin={startFeishuBrowserLogin}
        onLogout={handleLogout}
      />
      <ViewSwitcher activeView={activeView} onChange={setActiveView} />
      {notice ? <div className="app-toast" role="status">{notice}</div> : null}
      {activeView === "tasks" ? (
        <TaskPage currentUser={currentUser} />
      ) : (
        <RequirementPage
          currentUser={currentUser}
          isBusy={isBusy}
          setIsBusy={setIsBusy}
          setNotice={setNotice}
          onOpenTasks={() => setActiveView("tasks")}
        />
      )}
    </main>
  );
}
