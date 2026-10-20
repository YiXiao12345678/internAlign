import { ChevronRight } from "lucide-react";
import { logoColor, prettyCompany, scoreBand } from "../utils";

export default function JobCard({ match, selected, onSelect }) {
  const company = prettyCompany(match.company);
  const hasScore = match.score != null;

  return (
    <article className={`job-card ${selected ? "selected" : ""}`}>
      <div className="job-card-top">
        <div className={`company-logo ${logoColor(match.company)}`}>{company.charAt(0)}</div>
        <span className={`band-tag band-${scoreBand(match.score)}`}>{match.score_label}</span>
      </div>

      <span className="company-name">{company}</span>
      <h3>{match.title}</h3>
      <p className="location">{match.location || "Location not listed"}</p>

      <div className="match-row">
        <div className="match-score">
          <strong>{hasScore ? `${match.score}%` : "—"}</strong>
          <span>match</span>
        </div>
        <div className="score-bar">
          <div style={{ width: `${hasScore ? match.score : 0}%` }} />
        </div>
      </div>

      <button className="view-job" onClick={() => onSelect(match.posting_id)}>
        View analysis <ChevronRight size={16} />
      </button>
    </article>
  );
}
