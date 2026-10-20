import { FileText, Upload } from "lucide-react";
import { formatDate } from "../utils";

export default function ResumeView({ resume, onPickFile, uploading }) {
  if (!resume) {
    return (
      <div className="empty-state">
        <FileText size={28} />
        <h3>No resume yet</h3>
        <p>Upload a PDF, DOCX, or TXT resume. We read it to find the skills you can already show.</p>
        <button className="primary-button" onClick={onPickFile} disabled={uploading}>
          <Upload size={18} />
          {uploading ? "Uploading…" : "Upload resume"}
        </button>
      </div>
    );
  }

  return (
    <div className="resume-card">
      <div className="resume-card-head">
        <div className="stat-icon orange-icon">
          <FileText size={20} />
        </div>
        <div>
          <strong>{resume.filename}</strong>
          <span>
            Uploaded {formatDate(resume.uploaded_at)} · {resume.characters.toLocaleString()} characters read
          </span>
        </div>
        <button className="filter-button" onClick={onPickFile} disabled={uploading}>
          {uploading ? "Uploading…" : "Replace"}
        </button>
      </div>

      <h3>Skills we found ({resume.skills.length})</h3>
      {resume.skills.length ? (
        <div className="chips">
          {resume.skills.map((skill) => (
            <span className="chip" key={skill.name}>
              {skill.label}
            </span>
          ))}
        </div>
      ) : (
        <p className="muted">
          No known technical skills were detected. Make sure your resume lists the tools you use.
        </p>
      )}

      <h3>Sections detected</h3>
      {resume.sections.length ? (
        <div className="chips">
          {resume.sections.map((section) => (
            <span className="chip chip-muted" key={section}>
              {section}
            </span>
          ))}
        </div>
      ) : (
        <p className="muted">
          No section headings were detected. Headings like Skills, Experience, and Projects help us tell
          skills you list from skills you've used.
        </p>
      )}

      <p className="muted">Your original file is kept unchanged. Edits are only ever suggested, never applied automatically.</p>
    </div>
  );
}
