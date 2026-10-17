import { useState } from "react";
import { ArrowRight, LockKeyhole, Mail, UserRound } from "lucide-react";

const API_URL = "http://127.0.0.1:8000";

function Auth({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
  });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function updateField(event) {
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    });
  }

  async function submitForm(event) {
    event.preventDefault();

    setMessage("");
    setError("");
    setLoading(true);

    const endpoint = mode === "login" ? "/login" : "/signup";

    const requestBody =
      mode === "login"
        ? {
            email: form.email,
            password: form.password,
          }
        : {
            name: form.name,
            email: form.email,
            password: form.password,
          };

    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Something went wrong.");
      }

      if (mode === "signup") {
        setMessage("Account created successfully. Please log in.");
        setMode("login");
        setForm({
          name: "",
          email: form.email,
          password: "",
        });
      } else {
        onLogin(data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-visual">
        <div className="auth-brand">
          <div className="brand-mark">I</div>
          <span>InternAlign</span>
        </div>

        <div className="auth-visual-content">
          <span className="hero-label">YOUR CAREER, ALIGNED</span>

          <h1>Turn your experience into your next opportunity.</h1>

          <p>
            InternAlign compares your resume with real internship requirements
            so you can apply with more confidence.
          </p>

          <div className="auth-preview">
            <div className="preview-score">92%</div>

            <div>
              <strong>Product Engineer Intern</strong>
              <span>Excellent match</span>
            </div>
          </div>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-box">
          <div className="auth-mobile-brand">
            <div className="brand-mark">I</div>
            <span>InternAlign</span>
          </div>

          <div className="auth-heading">
            <span className="section-kicker">
              {mode === "login" ? "WELCOME BACK" : "GET STARTED"}
            </span>

            <h2>
              {mode === "login" ? "Welcome back" : "Create your account"}
            </h2>

            <p>
              {mode === "login"
                ? "Log in to continue analyzing your job matches."
                : "Start building a more focused internship search."}
            </p>
          </div>

          <div className="auth-tabs">
            <button
              type="button"
              className={mode === "login" ? "selected" : ""}
              onClick={() => {
                setMode("login");
                setError("");
                setMessage("");
              }}
            >
              Log in
            </button>

            <button
              type="button"
              className={mode === "signup" ? "selected" : ""}
              onClick={() => {
                setMode("signup");
                setError("");
                setMessage("");
              }}
            >
              Sign up
            </button>
          </div>

          <form onSubmit={submitForm}>
            {mode === "signup" && (
              <label className="input-label">
                Full name

                <div className="auth-input">
                  <UserRound size={18} />

                  <input
                    name="name"
                    type="text"
                    placeholder="Your full name"
                    value={form.name}
                    onChange={updateField}
                    required
                  />
                </div>
              </label>
            )}

            <label className="input-label">
              Email address

              <div className="auth-input">
                <Mail size={18} />

                <input
                  name="email"
                  type="email"
                  placeholder="you@example.com"
                  value={form.email}
                  onChange={updateField}
                  required
                />
              </div>
            </label>

            <label className="input-label">
              Password

              <div className="auth-input">
                <LockKeyhole size={18} />

                <input
                  name="password"
                  type="password"
                  placeholder="At least 8 characters"
                  value={form.password}
                  onChange={updateField}
                  minLength={8}
                  required
                />
              </div>
            </label>

            {error && <div className="auth-error">{error}</div>}

            {message && <div className="auth-success">{message}</div>}

            <button className="auth-submit" type="submit" disabled={loading}>
              {loading
                ? "Please wait..."
                : mode === "login"
                ? "Log in"
                : "Create account"}

              {!loading && <ArrowRight size={18} />}
            </button>
          </form>

          <p className="auth-footer">
            Your resume and analysis results will remain private to your
            account.
          </p>
        </div>
      </section>
    </main>
  );
}

export default Auth;