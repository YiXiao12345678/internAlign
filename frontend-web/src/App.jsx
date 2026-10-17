import { useRef, useState } from "react";
import {
  Bell,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronRight,
  FileText,
  LayoutDashboard,
  Menu,
  Search,
  Settings,
  Upload,
  UserRound,
  X,
} from "lucide-react";
import "./index.css";

const jobs = [
  {
    company: "Marvell Technology",
    role: "Product Engineer Intern",
    location: "Santa Clara, CA",
    score: 92,
    color: "purple",
  },
  {
    company: "Applied Materials",
    role: "Software Engineering Intern",
    location: "Santa Clara, CA",
    score: 84,
    color: "blue",
  },
  {
    company: "KLA",
    role: "Test Engineering Intern",
    location: "Milpitas, CA",
    score: 78,
    color: "orange",
  },
];

const skills = [
  { name: "Python", status: "matched", text: "Found in your programming skills and UL Solutions experience." },
  { name: "SQL", status: "matched", text: "Found in your technical skills section." },
  { name: "Product testing", status: "matched", text: "Supported by your RF validation and testing experience." },
  { name: "C++", status: "partial", text: "Related programming experience found, but C++ is not listed directly." },
  { name: "Semiconductor experience", status: "missing", text: "Consider adding relevant coursework or project experience." },
];

function App() {
  const fileInput = useRef(null);
  const [resume, setResume] = useState(null);
  const [activeNav, setActiveNav] = useState("Overview");
  const [search, setSearch] = useState("");

  const handleFile = (event) => {
    const file = event.target.files?.[0];
    if (file) setResume(file);
  };

  const filteredJobs = jobs.filter((job) =>
    `${job.company} ${job.role} ${job.location}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">I</div>
          <span>InternAlign</span>
        </div>

        <nav className="nav-list">
          {[
            { label: "Overview", icon: LayoutDashboard },
            { label: "Job Matches", icon: BriefcaseBusiness },
            { label: "My Resume", icon: FileText },
          ].map(({ label, icon: Icon }) => (
            <button
              className={`nav-item ${activeNav === label ? "active" : ""}`}
              onClick={() => setActiveNav(label)}
              key={label}
            >
              <Icon size={19} />
              {label}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <button className="nav-item">
            <Settings size={19} />
            Settings
          </button>

          <div className="profile">
            <div className="avatar">YX</div>
            <div>
              <strong>Yi Xiao</strong>
              <span>Computer Science</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button className="mobile-menu">
            <Menu size={21} />
          </button>

          <div>
            <p className="eyebrow">Saturday, October 17, 2026</p>
            <h1>Good morning, Yi</h1>
          </div>

          <div className="topbar-actions">
            <button className="icon-button">
              <Bell size={19} />
              <span className="notification-dot" />
            </button>
            <button className="avatar top-avatar">YX</button>
          </div>
        </header>

        <section className="hero-card">
          <div>
            <span className="hero-label">YOUR CAREER DASHBOARD</span>
            <h2>Find internships that fit your story.</h2>
            <p>
              Upload your resume and compare your experience against real job
              requirements.
            </p>
            <button
              className="primary-button"
              onClick={() => fileInput.current?.click()}
            >
              <Upload size={18} />
              Upload resume
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.doc,.docx"
              hidden
              onChange={handleFile}
            />
          </div>

          <div className="hero-graphic">
            <div className="graphic-circle circle-one" />
            <div className="graphic-circle circle-two" />
            <div className="graphic-card">
              <CheckCircle2 size={18} />
              <span>92% match</span>
            </div>
          </div>
        </section>

        {resume && (
          <div className="upload-success">
            <CheckCircle2 size={19} />
            <span>
              <strong>{resume.name}</strong> uploaded successfully
            </span>
            <button onClick={() => setResume(null)}>
              <X size={17} />
            </button>
          </div>
        )}

        <section className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon purple-icon">
              <BriefcaseBusiness size={20} />
            </div>
            <div>
              <span>Recommended jobs</span>
              <strong>24</strong>
              <small>+8 this week</small>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon green-icon">
              <CheckCircle2 size={20} />
            </div>
            <div>
              <span>Average match score</span>
              <strong>84%</strong>
              <small>Across your matches</small>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon orange-icon">
              <FileText size={20} />
            </div>
            <div>
              <span>Resume status</span>
              <strong>{resume ? "Analyzed" : "Ready to upload"}</strong>
              <small>{resume ? "Last updated today" : "Add your resume to begin"}</small>
            </div>
          </div>
        </section>

        <section className="content-section">
          <div className="section-heading">
            <div>
              <span className="section-kicker">PERSONALIZED FOR YOU</span>
              <h2>Top job matches</h2>
            </div>
            <button className="text-button">
              View all <ChevronRight size={17} />
            </button>
          </div>

          <div className="toolbar">
            <div className="search-box">
              <Search size={18} />
              <input
                placeholder="Search jobs or companies..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <button className="filter-button">Recent matches</button>
          </div>

          <div className="job-grid">
            {filteredJobs.map((job) => (
              <article className="job-card" key={job.company}>
                <div className="job-card-top">
                  <div className={`company-logo ${job.color}`}>
                    {job.company.charAt(0)}
                  </div>
                  <button className="more-button">•••</button>
                </div>

                <span className="company-name">{job.company}</span>
                <h3>{job.role}</h3>
                <p className="location">{job.location} · Internship</p>

                <div className="match-row">
                  <div className="match-score">
                    <strong>{job.score}%</strong>
                    <span>match</span>
                  </div>
                  <div className="score-bar">
                    <div style={{ width: `${job.score}%` }} />
                  </div>
                </div>

                <button className="view-job">
                  View analysis <ChevronRight size={16} />
                </button>
              </article>
            ))}
          </div>
        </section>

        <section className="content-section analysis-section">
          <div className="section-heading">
            <div>
              <span className="section-kicker">LATEST ANALYSIS</span>
              <h2>Marvell Product Engineer Intern</h2>
            </div>
            <span className="analysis-date">Analyzed today</span>
          </div>

          <div className="analysis-layout">
            <div className="score-panel">
              <div className="score-ring">
                <div>
                  <strong>92</strong>
                  <span>/ 100</span>
                </div>
              </div>
              <h3>Excellent match</h3>
              <p>
                Your testing, Python, and wireless engineering experience align
                strongly with this role.
              </p>
            </div>

            <div className="requirements-panel">
              <h3>Requirement alignment</h3>

              {skills.map((skill) => (
                <div className="requirement" key={skill.name}>
                  <div
                    className={`requirement-icon ${skill.status}`}
                  >
                    {skill.status === "matched" ? "✓" : skill.status === "partial" ? "!" : "×"}
                  </div>
                  <div>
                    <strong>{skill.name}</strong>
                    <p>{skill.text}</p>
                  </div>
                  <span className={`status-label ${skill.status}`}>
                    {skill.status === "matched"
                      ? "Supported"
                      : skill.status === "partial"
                      ? "Partial"
                      : "Missing"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;