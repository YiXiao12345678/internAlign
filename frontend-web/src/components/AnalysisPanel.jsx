import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { prettyCompany, STATUS } from "../utils";

const QUESTION_PREVIEW = 4;

function evidenceText(req) {
  if (req.status === "Supported") {
    const line = req.resume_evidence[0] || "";
    const where = req.evidence_type === "demonstrated" ? "Shown in your experience or projects" : "Listed in your skills";
    return { quote: line.length > 150 ? `${line.slice(0, 147)}…` : line, note: where };
  }
  if (req.status === "Partially supported") {
    return { note: `Your resume mentions ${req.related_skill}, a related skill, but not ${req.display_name}.` };
  }
  return { note: "No evidence found in your resume." };
}

function RequirementRow({ req }) {
  const status = STATUS[req.status];
  const { quote, note } = evidenceText(req);
  return (
    <div className="requirement">
      <div className={`requirement-icon ${status.tone}`}>{status.icon}</div>
      <div>
        <strong>{req.display_name}</strong>
        <p>{note}</p>
        {quote && <p className="evidence-quote">{quote}</p>}
      </div>
      <span className={`status-label ${status.tone}`}>{status.label}</span>
    </div>
  );
}

function EngineToggle({ engine, onChange }) {
  if (!onChange) return null;
  return (
    <div className="engine-toggle" role="group" aria-label="Analysis method">
      <button type="button" className={engine === "rules" ? "active" : ""} onClick={() => onChange("rules")}>
        Rule-based
      </button>
      <button type="button" className={engine === "rag" ? "active" : ""} onClick={() => onChange("rag")}>
        AI (RAG)
      </button>
    </div>
  );
}

export default function AnalysisPanel({ analysis, loading, error, engine = "rules", onEngineChange }) {
  const [showAllQuestions, setShowAllQuestions] = useState(false);
  const toggle = <EngineToggle engine={engine} onChange={onEngineChange} />;

  if (loading) {
    return (
      <>
        {toggle}
        <div className="panel-state">
          {engine === "rag" ? "Retrieving the posting and asking the language model… this can take a little while." : "Analyzing this posting…"}
        </div>
      </>
    );
  }
  if (error) {
    return (
      <>
        {toggle}
        <div className="banner banner-error">{error}</div>
      </>
    );
  }
  if (!analysis) return <div className="panel-state">Choose a job to see how your resume lines up.</div>;

  const { score, requirements, summary, clarification_questions: questions } = analysis;
  const required = requirements.filter((r) => r.importance === "required");
  const preferred = requirements.filter((r) => r.importance === "preferred");
  const visibleQuestions = showAllQuestions ? questions : questions.slice(0, QUESTION_PREVIEW);

  return (
    <>
      {toggle}
      <div className="section-heading">
        <div>
          <span className="section-kicker">ANALYSIS</span>
          <h2>
            {prettyCompany(analysis.company)} · {analysis.title}
          </h2>
        </div>
        {analysis.job_url && (
          <a className="text-button" href={analysis.job_url} target="_blank" rel="noopener noreferrer">
            View posting <ExternalLink size={15} />
          </a>
        )}
      </div>

      <div className="analysis-layout">
        <div className="score-panel">
          <div
            className="score-ring"
            style={{ background: `conic-gradient(#7659d8 ${score ?? 0}%, #e5e1f6 0)` }}
          >
            <div>
              <strong>{score ?? "—"}</strong>
              {score != null && <span>/ 100</span>}
            </div>
          </div>
          <h3>{analysis.score_label}</h3>
          {analysis.engine === "rag" && (
            <p className="engine-note">
              AI analysis by {analysis.model}.
              {analysis.unverified_quotes_removed > 0 &&
                ` ${analysis.unverified_quotes_removed} quote(s) not found in your resume were discarded.`}
            </p>
          )}
          {analysis.note ? (
            <p>{analysis.note}</p>
          ) : (
            <p>
              {summary.Supported} supported · {summary["Partially supported"]} partial ·{" "}
              {summary["Not found"]} missing
            </p>
          )}
        </div>

        <div className="requirements-panel">
          {required.length > 0 && (
            <>
              <h3>Required skills</h3>
              {required.map((req) => (
                <RequirementRow req={req} key={req.requirement} />
              ))}
            </>
          )}
          {preferred.length > 0 && (
            <>
              <h3 className="group-title">Nice to have</h3>
              {preferred.map((req) => (
                <RequirementRow req={req} key={req.requirement} />
              ))}
            </>
          )}
        </div>
      </div>

      {questions.length > 0 && (
        <div className="questions">
          <h3>Questions to answer before tailoring</h3>
          <p className="questions-hint">
            Nothing is added to your resume unless you confirm it. Answering these will let us suggest edits
            that are true to your experience.
          </p>
          <ul>
            {visibleQuestions.map((q) => (
              <li key={`${q.requirement}-${q.kind}`}>{q.question}</li>
            ))}
          </ul>
          {questions.length > QUESTION_PREVIEW && (
            <button className="text-button" onClick={() => setShowAllQuestions((v) => !v)}>
              {showAllQuestions ? "Show fewer" : `Show all ${questions.length}`}
            </button>
          )}
        </div>
      )}
    </>
  );
}
