import { useEffect, useMemo, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const MODEL = "gemini-2.5-flash-lite";

const defaultSubjects = [];
const defaultCategories = [];
const questionTypeOptions = ["exam", "understanding"];
const CANONICAL_CATEGORY = "GCE 'A' Levels";

const fallbackYears = Array.from({ length: 10 }, (_, index) => {
  const year = new Date().getFullYear() - index;
  return year;
});

const basePrompt = `
You are an information extraction engine. You MUST NOT generate any content that is not present verbatim in the input.

TASK
Extract ONLY the actual exam sub-questions from the given paper text (ignore instructions, headers, source lines, extracts, figures, totals, and any non-question content). Classify each extracted sub-question into:
- "exam": sub-questions that have an explicit mark allocation in square brackets, attached per rules below
- "understanding": sub-questions that do NOT have an explicit mark allocation attached per rules below

CRITICAL: NO HALLUCINATIONS
- Output ONLY questions that appear verbatim in the input text.
- DO NOT paraphrase, summarize, or invent any questions.
- DO NOT create “understanding” questions unless they are verbatim in the input.
- If there are no understanding questions, "understanding" MUST be [].

DEFINITION OF QUESTION
A “question” is a line/block that asks the candidate to do something (e.g., Explain/Discuss/Describe/Analyse/Compare/Evaluate/With reference to..., etc.), including subparts like (a), (b), (c)(i), (ii), etc.

EXCLUSIONS (NOT QUESTIONS)
Do NOT extract:
- General instructions (e.g., “Answer all questions”, “You are required to answer…”)
- Section instructions (e.g., “One or two of your three chosen questions…”)
- Totals lines like “[Total: 30]”
- Any bracketed text that is NOT a mark allocation (e.g., quotes like “free trade [but] ...”)
- Source citations and headers

MARK ASSOCIATION RULE (STRICT + MECHANICAL)
A sub-question has marks ONLY if there is a square-bracketed integer mark like [2], [4], [8], [10], [15] that is:
1) On the same line as the sub-question, OR
2) On the immediately following NON-EMPTY line (after trimming whitespace).

A square-bracketed value is NOT a mark allocation if it matches:
- [Total: ...] (case-insensitive)
- any bracketed word/phrase containing letters (e.g., [but], [Total], [Source])
Only pure integers inside brackets count as marks: [number]

If a pure-integer mark is found by rule (1) or (2), append it to the end of the question text separated by a single space, exactly as written (e.g., "... [10]").
If no such mark is attached, DO NOT add any brackets.

THEME & SUBTHEME MAPPING (STRICT)

- You MUST assign a syllabus chapter AND subchapter number (e.g. 2.2.2) to EVERY extracted question.
- Do NOT output "Unknown".
- Do NOT skip chapter assignment.
- Use the MOST SPECIFIC applicable subchapter number from the syllabus.
- The chapter value MUST exactly match one of the provided subtopics (code + title).

Theme format MUST be:
"<syllabus_number> <syllabus_chapter_title>"

Examples:
- "2.2.2 Inflation and its causes"
- "1.3.1 Price controls"
- "3.1.4 Trade protectionism"


OUTPUT FORMAT (STRICT JSON ONLY)
Return JSON ONLY in this exact structure:
{
  "exam": [
    { "chapter": "<chapter>", "question": "<verbatim question text with attached mark if present>", "marks": <number of marks allocated>}
  ],
  "understanding": [
    { "chapter": "<chapter>", "question": "<verbatim question text with NO marks>" }
  ]
}

FINAL VALIDATION (MANDATORY, DO NOT OUTPUT)
- Every "exam" question MUST end with a pure-integer bracket mark like [10].
- No "understanding" question may contain '[' or ']'.
- Do not output any item that is not verbatim from the input.

SYLLABUS + TEXT:
`;

const subtopicPrompt = `
You are a strict information extraction engine. Extract syllabus subject and subtopics from the input text.

Rules:
- A subject is the name of the subject and its subject code e.g. Economics (Syllabus 9750) and Physics (Syllabus 6091) 
- A subtopic is a dotted numeric code followed by a title. Examples: "1.1 Functions", "2.3.4 Elasticity".
- If a line is only a dotted numeric code, use the next non-empty line as its title.
- Ignore any non-subtopic content (prefaces, assessment objectives, admin sections).
- Do not invent or paraphrase.
- No duplicates by code.

Output JSON ONLY in this shape:
{
  "subject": "Economics (9750)",
  "subtopics": [
    { "code": "1.1", "title": "Functions" }
  ]
}

Syllabus text:
`;



function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, value);
    }
  });
  return search.toString();
}

function normalizeCategory(value) {
  if (!value) return value;
  if (value === "A-Level" || value === 'GCE "A" Levels') {
    return CANONICAL_CATEGORY;
  }
  return value;
}

export default function App() {
  const [subjects, setSubjects] = useState([]);
  const [subject, setSubject] = useState("All");
  const [subtopics, setSubtopics] = useState([]);
  const [subtopicSearch, setSubtopicSearch] = useState("");
  const [selectedSubtopic, setSelectedSubtopic] = useState(null);

  const [categories, setCategories] = useState([]);
  const [years, setYears] = useState([]);
  const [category, setCategory] = useState("All");
  const [year, setYear] = useState("All");
  const [document_name, setDocumentName] = useState("Document Name");
  const [questionType, setQuestionType] = useState(questionTypeOptions[0]);
  const [syllabusFile, setSyllabusFile] = useState(null);

  const [questions, setQuestions] = useState([]);
  const [status, setStatus] = useState({ type: "idle", message: "" });
  const [isLoading, setIsLoading] = useState(false);

  const loadSubjects = async () => {
    try {
      const res = await fetch(`${API_URL}/subjects`);
      const data = await res.json();
      if (Array.isArray(data.subjects) && data.subjects.length > 0) {
        setSubjects(data.subjects);
        return;
      }
    } catch (err) {
      setStatus({ type: "error", message: "Could not load subjects from API." });
    }
    setSubjects(defaultSubjects);
  };

  const loadSubtopics = async (targetSubject = subject) => {
    if (!targetSubject || targetSubject === "All") {
      setSubtopics([]);
      setSelectedSubtopic(null);
      return;
    }
    try {
      const res = await fetch(`${API_URL}/subtopics?${buildQuery({ subject: targetSubject })}`);
      const data = await res.json();
      setSubtopics(Array.isArray(data.subtopics) ? data.subtopics : []);
      setSelectedSubtopic(null);
    } catch (err) {
      setStatus({ type: "error", message: "Could not load subtopics." });
    }
  };

  useEffect(() => {
    const loadFilters = async () => {
      try {
        const res = await fetch(`${API_URL}/questions/filters`);
        const data = await res.json();
        if (Array.isArray(data.categories) && data.categories.length > 0) {
          setCategories(data.categories);
        } else {
          setCategories(defaultCategories);
        }
        if (Array.isArray(data.years) && data.years.length > 0) {
          setYears(data.years);
        } else {
          setYears(fallbackYears);
        }
      } catch (err) {
        setStatus({ type: "error", message: "Could not load filters from API." });
      }
    };

    loadFilters();
    loadSubjects();
  }, []);

  useEffect(() => {
    loadSubtopics();
  }, [subject]);

  useEffect(() => {
    if (subject !== "All") {
      loadQuestions();
    }
  }, [subject, selectedSubtopic]);
  const filteredSubtopics = useMemo(() => {
    const term = subtopicSearch.trim().toLowerCase();
    if (!term) return subtopics;
    return subtopics.filter((subtopic) =>
      `${subtopic.code} ${subtopic.title}`.toLowerCase().includes(term)
    );
  }, [subtopics, subtopicSearch]);

  const syncContext = async (overrides = {}) => {
    const subjectLabel =
      overrides.subject_label ??
      overrides.subject ??
      (subject === "All" ? "Economics" : subject);
    const scraperConfig = {
      category: normalizeCategory(
        overrides.category ?? (category === "All" ? CANONICAL_CATEGORY : category)
      ),
      subject: overrides.scraper_subject ?? overrides.subject ?? (subject === "All" ? "Economics" : subject),
      year:
        overrides.year ??
        (year === "All" ? null : Number.isNaN(Number(year)) ? null : Number(year)),
      document_type: "Exam Papers",
      pages: 3,
      subject_label: subjectLabel,
    };
    await fetch(`${API_URL}/scraper/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scraperConfig),
    });
    const payload = {
      year: overrides.year ?? (Number(year) || new Date().getFullYear()),
      subject: overrides.subject ?? (subject === "All" ? "Economics" : subject),
      category: normalizeCategory(
        overrides.category ?? (category === "All" ? CANONICAL_CATEGORY : category)
      ),
      question_type: overrides.question_type ?? questionType,
      source_link: overrides.source_link ?? "",
      document_name: overrides.document_name ?? document_name,
    };
    await fetch(`${API_URL}/context`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  };

  const parseAiJson = (output) => {
    const cleaned = output.replace(/```json|```/g, "").trim();
    return JSON.parse(cleaned);
  };

  const loadQuestions = async () => {
    setIsLoading(true);
    setStatus({ type: "idle", message: "" });
    try {
      const params = {
        subject,
        year,
        category,
        subtopic: selectedSubtopic?.code,
      };
      const res = await fetch(`${API_URL}/questions?${buildQuery(params)}`);
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || "Could not fetch questions.");
      }
      const data = await res.json();
      setQuestions(Array.isArray(data.questions) ? data.questions : []);
      setStatus({ type: "success", message: `Loaded ${data.questions?.length || 0} questions.` });
    } catch (err) {
      setStatus({ type: "error", message: "Could not fetch questions." });
    } finally {
      setIsLoading(false);
    }
  };

  const extractSubtopicsFromSyllabus = async () => {
    if (!syllabusFile) {
      setStatus({ type: "error", message: "Select a syllabus PDF first." });
      return;
    }
    if (!window.puter?.ai?.chat) {
      setStatus({ type: "error", message: "Puter.js is not available." });
      return;
    }

    setIsLoading(true);
    setStatus({ type: "idle", message: "" });

    try {
      const formData = new FormData();
      formData.append("subject", subject);
      formData.append("file", syllabusFile);

      const uploadRes = await fetch(`${API_URL}/syllabus/extract`, {
        method: "POST",
        body: formData,
      });

      if (!uploadRes.ok) {
        const detail = await uploadRes.text();
        throw new Error(detail || "Syllabus extraction failed.");
      }

      const { text } = await uploadRes.json();
      const prompt = `${subtopicPrompt}${text}`;
      const aiResponse = await window.puter.ai.chat(prompt, { model: MODEL });
      const output =
        typeof aiResponse === "string"
          ? aiResponse
          : aiResponse?.message?.content || aiResponse?.content || JSON.stringify(aiResponse);

      const resultObj = parseAiJson(output);
      const extractedSubject =
        typeof resultObj.subject === "string" && resultObj.subject.trim().length > 0
          ? resultObj.subject.trim()
          : subject;
      const payload = {
        subject: extractedSubject === "All" ? "Economics" : extractedSubject,
        subtopics: resultObj.subtopics || [],
      };

      const subtopicRes = await fetch(`${API_URL}/subtopics/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const subtopicData = await subtopicRes.json();
      setStatus({
        type: "success",
        message: `Seeded ${subtopicData.created || 0} subtopics for ${payload.subject}.`,
      });
      await loadSubjects();
      setSubject(payload.subject);
      await loadSubtopics(payload.subject);
    } catch (err) {
      setStatus({ type: "error", message: err.message || "Subtopic extraction failed." });
    } finally {
      setIsLoading(false);
    }
  };

  const runAiPipeline = async () => {
    if (!window.puter?.ai?.chat) {
      setStatus({ type: "error", message: "Puter.js is not available." });
      return;
    }

    setIsLoading(true);
    setStatus({ type: "idle", message: "" });

    try {
      await syncContext();
      const dataRes = await fetch(`${API_URL}/data`);
      if (!dataRes.ok) {
        const detail = await dataRes.text();
        throw new Error(detail || "Could not load document text.");
      }
      const dataPayload = await dataRes.json();
      const contextPayload = dataPayload.context;
      if (contextPayload?.document_name) {
        setDocumentName(contextPayload.document_name);
      }
      if (contextPayload?.subject && subject === "All") {
        setSubject(contextPayload.subject);
      }
      if (contextPayload?.category && category === "All") {
        setCategory(contextPayload.category);
      }
      if (typeof contextPayload?.year === "number" && year === "All") {
        setYear(contextPayload.year > 0 ? String(contextPayload.year) : "All");
      }
      if (contextPayload) {
        await syncContext(contextPayload);
      }
      const subjectForPrompt = subject === "All" ? "" : subject;
      const subtopicRes = subjectForPrompt
        ? await fetch(`${API_URL}/subtopics?${buildQuery({ subject: subjectForPrompt })}`)
        : null;
      const subtopicData = subtopicRes ? await subtopicRes.json() : { subtopics: [] };
      const subtopicLines = (subtopicData.subtopics || [])
        .map((item) => `${item.code} ${item.title}`)
        .join("\n");

      const { text } = dataPayload;
      const prompt = `${basePrompt}\nSUBTOPICS (use exact match):\n${subtopicLines}\n\n${text}`;

      const aiResponse = await window.puter.ai.chat(prompt, { model: MODEL });
      const output =
        typeof aiResponse === "string"
          ? aiResponse
          : aiResponse?.message?.content || aiResponse?.content || JSON.stringify(aiResponse);

      const resultObj = parseAiJson(output);

      const postRes = await fetch(`${API_URL}/ai-result`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result: resultObj, context: contextPayload }),
      });
      const postData = await postRes.json();

      setStatus({ type: "success", message: `AI pipeline complete: ${postData.status || "ok"}` });
      await loadQuestions();
    } catch (err) {
      setStatus({ type: "error", message: err.message || "Pipeline failed." });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">G</div>
          <div>
            <h1>Grail Questions</h1>
            <p>Filter by syllabus chapter and year.</p>
          </div>
        </div>

        <div className="field">
          <label htmlFor="subject">Subject</label>
          <select
            id="subject"
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
          >
            <option value="All">All subjects</option>
            {subjects.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>

        <div className="subtopic-header">
          <h2>Subtopics</h2>
          <input
            placeholder="Search subtopics"
            value={subtopicSearch}
            onChange={(event) => setSubtopicSearch(event.target.value)}
          />
        </div>

        <div className="subtopic-list">
          {filteredSubtopics.map((subtopic) => {
            const isActive = selectedSubtopic?.id === subtopic.id;
            return (
              <button
                type="button"
                key={subtopic.id}
                className={`subtopic-item ${isActive ? "active" : ""}`}
                onClick={() => setSelectedSubtopic(subtopic)}
              >
                <span>{subtopic.code}</span>
                <span>{subtopic.title}</span>
              </button>
            );
          })}
          {filteredSubtopics.length === 0 && (
            <p className="empty">No subtopics yet. Add them via the API.</p>
          )}
        </div>
      </aside>

      <main className="main">
        <section className="hero">
          <div>
            <h2>Curate the question bank</h2>
            <p>
              Select a context, sync it to the backend, then run extraction or load
              matching questions.
            </p>
          </div>
          <div className="status">
            <span className={`status-pill ${status.type}`}>{status.message || "Ready"}</span>
          </div>
        </section>

        <section className="syllabus-panel">
          <div>
            <h3>Seed subtopics from syllabus</h3>
            <p>
              Upload the syllabus PDF for the selected subject and let Gemini extract the
              subtopic list.
            </p>
          </div>
          <div className="syllabus-actions">
            <input
              type="file"
              accept="application/pdf"
              onChange={(event) => setSyllabusFile(event.target.files?.[0] || null)}
            />
            <button
              className="primary"
              onClick={extractSubtopicsFromSyllabus}
              disabled={isLoading}
            >
              Extract subtopics
            </button>
          </div>
          {syllabusFile && (
            <p className="file-note">Selected: {syllabusFile.name}</p>
          )}
        </section>

        <section className="filters">
          <div className="field">
            <label htmlFor="year">Year</label>
            <select
              id="year"
              value={year}
              onChange={(event) => setYear(event.target.value)}
            >
              <option value="All">All years</option>
              {years.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="category">Category</label>
            <select
              id="category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="All">All categories</option>
              {categories.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="questionType">Question type</label>
            <select
              id="questionType"
              value={questionType}
              onChange={(event) => setQuestionType(event.target.value)}
            >
              {questionTypeOptions.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>

        </section>

        <section className="actions">
          <button type="button" className="secondary" onClick={syncContext} disabled={isLoading}>
            Sync context
          </button>
          <button type="button" className="primary" onClick={loadQuestions} disabled={isLoading}>
            {isLoading ? "Loading..." : "Load questions"}
          </button>
          <button type="button" className="accent" onClick={runAiPipeline} disabled={isLoading}>
            Run AI extraction
          </button>
        </section>

        <section className="cards">
          {questions.map((question, index) => (
            <article
              key={question.id}
              className="card"
              style={{ animationDelay: `${index * 60}ms` }}
            >
              <div className="card-meta">
                
                <span>{question.year}</span>
                <span>{question.category}</span>
                <span>{question.question_type}</span>
              </div>
              <div className="card-body">
                <h3>{question.document_name || "Untitled document"}</h3>
                <p>{question.question_text}</p>
                <div className="card-tags">
                  <span>{question.subject}</span>
                  <span>{question.source_link || "Source pending"}</span>
                </div>
              </div>
              <div className="card-score">
                <span>{question.marks ?? "-"}</span>
                <small>marks</small>
              </div>
            </article>
          ))}
          {questions.length === 0 && (
            <div className="empty-card">No questions yet. Try running extraction.</div>
          )}
        </section>
      </main>
    </div>
  );
}
