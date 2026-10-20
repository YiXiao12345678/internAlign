import { useCallback, useEffect, useState } from "react";
import Auth from "./Auth";
import Dashboard from "./Dashboard";
import { api, session, setUnauthorizedHandler } from "./api";

function App() {
  const [token, setToken] = useState(() => session.token());
  const [user, setUser] = useState(() => session.user());
  const [checking, setChecking] = useState(Boolean(session.token()));

  const logout = useCallback(() => {
    session.clear();
    setToken(null);
    setUser(null);
  }, []);

  function handleLogin(data) {
    session.save(data.access_token, data.user);
    setToken(data.access_token);
    setUser(data.user);
  }

  // Any protected request that comes back 401 logs the user out.
  useEffect(() => {
    setUnauthorizedHandler(logout);
  }, [logout]);

  // Confirm a saved token is still valid before showing the dashboard.
  useEffect(() => {
    if (!session.token()) return;
    api("/me")
      .then((freshUser) => setUser(freshUser))
      .catch(() => {}) // a 401 is already handled by logout(); network errors keep the cached user
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <div className="page-loading">Loading…</div>;
  if (!token) return <Auth onLogin={handleLogin} />;
  return <Dashboard user={user} onLogout={logout} />;
}

export default App;
