import { useEffect, useMemo, useRef, useState } from "react";
import {
  BriefcaseBusiness,
  CheckCircle2,
  ChevronRight,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Upload,
  X,
} from "lucide-react";
import { api, ApiError } from "./api";
import AnalysisPanel from "./components/AnalysisPanel";
import JobCard from "./components/JobCard";
import ResumeView from "./components/ResumeView";
import { greeting, initials, scoreBand, today } from "./utils";

const NAV = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "matches", label: "Job Matches", icon: BriefcaseBusiness },
  { id: "resume", label: "My Resume", icon: FileText },
];

const BAND_FILTERS = [
  { id: "all", label: "All matches" },
  { id: "strong", label: "Strong (70+)" },
  { id: "partial", label: "Partial (50–69)" },
  { id: "stretch", label: "Stretch (<50)" },
];

const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt"];
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

function scrollTo(element) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  element?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

export default function Dashboard({ user, onLogout }) {
  const fileInput = useRef(null);
  const analysisRef = useRef(null);

  const [view, setView] = useState("overview");
  const [menuOpen, setMenuOpen] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [resume, setResume] = useState(null);
  const [matches, setMatches] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);

  const [selectedId, setSelectedId] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState("");

  const [search, setSearch] = useState("");
  const [band, setBand] = useState("all");

  // Load the saved resume and its matches once.
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const savedResume = await api("/resume");
        const ranked = await api("/matches");
        if (cancelled) return;
        setResume(savedResume);
        setMatches(ranked);
        setSelectedId(ranked.matches[0]?.posting_id ?? null);
      } catch (err) {
        // 404 just means "no resume uploaded yet".
        if (!cancelled && !(err instanceof ApiError && err.status === 404)) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // Load the gap analysis whenever the selected posting (or resume) changes.
  useEffect(() => {
    if (!selectedId || !resume) return undefined;
    let cancelled = false;
    async function loadAnalysis() {
      setAnalysisLoading(true);
      setAnalysisError("");
      try {
        const result = await api(`/analysis/${encodeURIComponent(selectedId)}`);
        if (!cancelled) setAnalysis(result);
      } catch (err) {
        if (!cancelled) {
          setAnalysis(null);
          setAnalysisError(err.message);
        }
      } finally {
        if (!cancelled) setAnalysisLoading(false);
      }
    }
    loadAnalysis();
    return () => {
      cancelled = true;
    };
  }, [selectedId, resume?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function uploadFile(file) {
    if (!file) return;
    setError("");

    const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      setError("Unsupported file type. Upload a PDF, DOCX, or TXT resume.");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setError("That file is larger than 5 MB. Export a smaller version and try again.");
      return;
    }

    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const savedResume = await api("/resume", { method: "POST", form });
      const ranked = await api("/matches");
      setResume(savedResume);
      setMatches(ranked);
      setSelectedId(ranked.matches[0]?.posting_id ?? null);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  function pickFile() {
    fileInput.current?.click();
  }

  function selectPosting(id) {
    setSelectedId(id);
    requestAnimationFrame(() => scrollTo(analysisRef.current));
  }

  function go(nextView) {
    setView(nextView);
    setMenuOpen(false);
  }

  const allMatches = useMemo(() => matches?.matches ?? [], [matches]);
  const filteredMatches = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return allMatches.filter(
      (m) =>
        (band === "all" || scoreBand(m.score) === band) &&
        `${m.company} ${m.title} ${m.location}`.toLowerCase().includes(needle),
    );
  }, [allMatches, search, band]);

  const firstName = user?.name?.split(" ")[0] || "there";
  const strongCount = allMatches.filter((m) => m.score != null && m.score >= 70).length;
  const bestScore = allMatches.find((m) => m.score != null)?.score;

  const titles = {
    overview: `${greeting()}, ${firstName}`,
    matches: "Job matches",
    resume: "My resume",
  };

  const analysisSection = resume && selectedId && (
    <section className="content-section analysis-section" ref={analysisRef}>
      <AnalysisPanel analysis={analysis} loading={analysisLoading} error={analysisError} />
    </section>
  );

  const noResumePrompt = (
    <div className="empty-state">
      <BriefcaseBusiness size={28} />
      <h3>Upload your resume to see your matches</h3>
      <p>We rank every internship in the dataset by how well your experience covers what it asks for.</p>
      <button className="primary-button" onClick={pickFile} disabled={uploading}>
        <Upload size={18} />
        {uploading ? "Uploading…" : "Upload resume"}
      </button>
    </div>
  );

  return (
    <div className="app-shell">
      {menuOpen && <div className="sidebar-overlay" onClick={() => setMenuOpen(false)} />}

      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">I</div>
          <span>InternAlign</span>
        </div>

        <nav className="nav-list">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              className={`nav-item ${view === id ? "active" : ""}`}
              onClick={() => go(id)}
              aria-current={view === id ? "page" : undefined}
              key={id}
            >
              <Icon size={19} />
              {label}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <button className="nav-item" onClick={onLogout}>
            <LogOut size={19} />
            Log out
          </button>

          <div className="profile">
            <div className="avatar">{initials(user?.name)}</div>
            <div>
              <strong>{user?.name}</strong>
              <span>{user?.email}</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu size={21} />
          </button>

          <div>
            <p className="eyebrow">{today()}</p>
            <h1>{titles[view]}</h1>
          </div>

          <div className="topbar-actions">
            <div className="avatar top-avatar" title={user?.email}>
              {initials(user?.name)}
            </div>
          </div>
        </header>

        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.docx,.txt"
          hidden
          onChange={(event) => uploadFile(event.target.files?.[0])}
        />

        {error && (
          <div className="banner banner-error" role="alert">
            <span>{error}</span>
            <button onClick={() => setError("")} aria-label="Dismiss">
              <X size={17} />
            </button>
          </div>
        )}

        {loading ? (
          <div className="panel-state">Loading your dashboard…</div>
        ) : (
          <>
            {view === "overview" && (
              <>
                <section
                  className={`hero-card ${dragging ? "dragging" : ""}`}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(event) => {
                    event.preventDefault();
                    setDragging(false);
                    uploadFile(event.dataTransfer.files?.[0]);
                  }}
                >
                  <div>
                    <span className="hero-label">YOUR CAREER DASHBOARD</span>
                    <h2>{resume ? "Here's how your resume lines up." : "Find internships that fit your story."}</h2>
                    <p>
                      {resume
                        ? `Your resume is compared against ${matches?.total ?? 0} internship postings. Pick one to see what's supported and what's missing.`
                        : "Upload your resume (or drop it here) and compare your experience against real job requirements."}
                    </p>
                    <button className="primary-button" onClick={pickFile} disabled={uploading}>
                      <Upload size={18} />
                      {uploading ? "Uploading…" : resume ? "Replace resume" : "Upload resume"}
                    </button>
                  </div>

                  <div className="hero-graphic">
                    <div className="graphic-circle circle-one" />
                    <div className="graphic-circle circle-two" />
                    <div className="graphic-card">
                      <CheckCircle2 size={18} />
                      <span>{bestScore != null ? `${bestScore}% best match` : resume ? "Resume ready" : "Upload to begin"}</span>
                    </div>
                  </div>
                </section>

                <section className="stats-grid">
                  <div className="stat-card">
                    <div className="stat-icon purple-icon">
                      <BriefcaseBusiness size={20} />
                    </div>
                    <div>
                      <span>Strong matches</span>
                      <strong>{resume ? strongCount : "—"}</strong>
                      <small>{resume ? `Out of ${matches?.total ?? 0} postings` : "Upload a resume to see these"}</small>
                    </div>
                  </div>

                  <div className="stat-card">
                    <div className="stat-icon green-icon">
                      <CheckCircle2 size={20} />
                    </div>
                    <div>
                      <span>Average match score</span>
                      <strong>{matches?.average_score != null ? `${matches.average_score}%` : "—"}</strong>
                      <small>Across all scored postings</small>
                    </div>
                  </div>

                  <div className="stat-card">
                    <div className="stat-icon orange-icon">
                      <FileText size={20} />
                    </div>
                    <div>
                      <span>Resume status</span>
                      <strong>{resume ? "Analyzed" : "Ready to upload"}</strong>
                      <small>{resume ? resume.filename : "Add your resume to begin"}</small>
                    </div>
                  </div>
                </section>

                <section className="content-section">
                  <div className="section-heading">
                    <div>
                      <span className="section-kicker">PERSONALIZED FOR YOU</span>
                      <h2>Top job matches</h2>
                    </div>
                    {resume && (
                      <button className="text-button" onClick={() => go("matches")}>
                        View all <ChevronRight size={17} />
                      </button>
                    )}
                  </div>

                  {resume ? (
                    <div className="job-grid">
                      {allMatches.slice(0, 3).map((match) => (
                        <JobCard
                          key={match.posting_id}
                          match={match}
                          selected={match.posting_id === selectedId}
                          onSelect={selectPosting}
                        />
                      ))}
                    </div>
                  ) : (
                    noResumePrompt
                  )}
                </section>

                {analysisSection}
              </>
            )}

            {view === "matches" && (
              <>
                {resume ? (
                  <section className="content-section">
                    <div className="section-heading">
                      <div>
                        <span className="section-kicker">RANKED BY FIT</span>
                        <h2>All job matches</h2>
                      </div>
                      <span className="analysis-date">
                        {filteredMatches.length} of {allMatches.length} postings
                      </span>
                    </div>

                    <div className="toolbar">
                      <div className="search-box">
                        <Search size={18} />
                        <input
                          placeholder="Search jobs or companies..."
                          aria-label="Search jobs"
                          value={search}
                          onChange={(event) => setSearch(event.target.value)}
                        />
                      </div>
                      <select
                        className="filter-select"
                        aria-label="Filter by match strength"
                        value={band}
                        onChange={(event) => setBand(event.target.value)}
                      >
                        {BAND_FILTERS.map((f) => (
                          <option value={f.id} key={f.id}>
                            {f.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {filteredMatches.length ? (
                      <div className="job-grid">
                        {filteredMatches.map((match) => (
                          <JobCard
                            key={match.posting_id}
                            match={match}
                            selected={match.posting_id === selectedId}
                            onSelect={selectPosting}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="panel-state">No postings match these filters.</div>
                    )}
                  </section>
                ) : (
                  noResumePrompt
                )}
                {analysisSection}
              </>
            )}

            {view === "resume" && <ResumeView resume={resume} onPickFile={pickFile} uploading={uploading} />}
          </>
        )}
      </main>
    </div>
  );
}
