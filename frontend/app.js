const state = {
  user: null,
  currentExam: null,
};

const $ = (id) => document.getElementById(id);

function setLog(message, data) {
  const line = `[${new Date().toLocaleTimeString()}] ${message}`;
  const payload = data ? `\n${JSON.stringify(data, null, 2)}\n` : "\n";
  $("logBox").textContent = `${line}${payload}\n${$("logBox").textContent}`.trim();
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return body;
}

async function apiForm(path, formData, method = "POST") {
  const res = await fetch(path, {
    method,
    body: formData,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return body;
}

function updateSessionUI() {
  const inSession = !!state.user;
  $("authPanel").classList.toggle("hidden", inSession);
  $("appPanel").classList.toggle("hidden", !inSession);
  $("sessionBox").classList.toggle("hidden", !inSession);
  if (state.user) {
    $("sessionText").textContent = `${state.user.username} (${state.user.role})`;
  }
}

function activateTab(tabId) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
  document.querySelector(`[data-tab="${tabId}"]`).classList.add("active");
  $(tabId).classList.remove("hidden");
}

function safeDateText(value) {
  if (!value) return "none";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return dt.toLocaleString();
}

function renderMyExams(exams) {
  const wrap = $("myExamsList");
  wrap.innerHTML = "";
  if (!exams.length) {
    wrap.innerHTML = `<div class="tiny">No exams found.</div>`;
    return;
  }

  exams.forEach((e) => {
    const item = document.createElement("div");
    item.className = "list-item";
    item.innerHTML = `
      <div><strong>#${e.id}</strong> ${e.topic}</div>
      <div class="tiny">${e.difficulty || "N/A"} | v${e.version ?? 1} | due: ${safeDateText(e.due_at)}</div>
      <label>Status</label>
      <select id="status_${e.id}">
        <option value="draft" ${e.status === "draft" ? "selected" : ""}>draft</option>
        <option value="published" ${e.status === "published" ? "selected" : ""}>published</option>
        <option value="archived" ${e.status === "archived" ? "selected" : ""}>archived</option>
      </select>
      <label>Due at</label>
      <input id="due_${e.id}" type="datetime-local" value="${e.due_at ? new Date(e.due_at).toISOString().slice(0,16) : ""}" />
      <label>Rubric</label>
      <textarea id="rubric_${e.id}" rows="2">${e.rubric || ""}</textarea>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-light" data-update-exam="${e.id}">Save</button>
        <button class="btn btn-light" data-versions="${e.id}">Versions</button>
      </div>
      <pre id="versions_${e.id}" class="log hidden"></pre>
    `;
    wrap.appendChild(item);
  });

  wrap.querySelectorAll("[data-update-exam]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const examId = Number(btn.dataset.updateExam);
      try {
        const payload = {
          instructor_id: state.user.id,
          status: $(`status_${examId}`).value,
          due_at: $(`due_${examId}`).value ? new Date($(`due_${examId}`).value).toISOString() : null,
          rubric: $(`rubric_${examId}`).value.trim() || null,
        };
        const result = await api(`/exams/${examId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setLog("Exam updated", result);
        await loadMyExams();
      } catch (err) {
        setLog("Exam update failed", { error: err.message });
      }
    });
  });

  wrap.querySelectorAll("[data-versions]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const examId = Number(btn.dataset.versions);
      try {
        const versions = await api(`/exams/${examId}/versions`);
        const box = $(`versions_${examId}`);
        box.classList.remove("hidden");
        box.textContent = JSON.stringify(versions, null, 2);
      } catch (err) {
        setLog("Version load failed", { error: err.message });
      }
    });
  });
}

function renderSubmissions(list) {
  const wrap = $("submissionsList");
  wrap.innerHTML = "";
  if (!list.length) {
    wrap.innerHTML = `<div class="tiny">No submissions available.</div>`;
    return;
  }

  list.forEach((s) => {
    const item = document.createElement("div");
    item.className = "list-item";
    item.innerHTML = `
      <div><strong>Submission #${s.submission_id}</strong> | Exam #${s.exam_id} (${s.exam_topic})</div>
      <div class="tiny">Student: ${s.student_username} | Submitted: ${safeDateText(s.submitted_at)} | Score: ${s.numerical_score ?? "Not graded"}</div>
      <details>
        <summary>View details</summary>
        <label>Exam Content</label>
        <textarea rows="5" readonly>${s.exam_content || ""}</textarea>
        <label>Student Answers</label>
        <textarea rows="5" readonly>${s.student_answers || ""}</textarea>
        <label>AI Feedback</label>
        <textarea rows="4" readonly>${s.ai_feedback || "No feedback yet"}</textarea>
        <label>Score Breakdown</label>
        <pre class="log">${JSON.stringify(s.score_breakdown || {}, null, 2)}</pre>
        <label>Instructor Note</label>
        <textarea rows="2" readonly>${s.grader_note || ""}</textarea>
      </details>
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
        <button class="btn btn-light" data-grade="${s.submission_id}">Auto Grade</button>
        <input id="override_score_${s.submission_id}" type="number" min="0" max="100" value="${s.numerical_score ?? 0}" style="max-width:120px;" />
        <input id="override_note_${s.submission_id}" type="text" placeholder="Override note" value="${s.grader_note || ""}" style="max-width:260px;" />
        <button class="btn btn-light" data-override="${s.submission_id}">Save Override</button>
      </div>
    `;
    wrap.appendChild(item);
  });

  wrap.querySelectorAll("[data-grade]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const payload = {
          submission_id: Number(btn.dataset.grade),
          instructor_id: state.user.id,
        };
        const result = await api("/submissions/grade", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setLog("Graded submission", result);
        await loadSubmissionsForInstructor();
      } catch (err) {
        setLog("Grade failed", { error: err.message });
      }
    });
  });

  wrap.querySelectorAll("[data-override]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const subId = Number(btn.dataset.override);
      try {
        const payload = {
          instructor_id: state.user.id,
          score: Number($(`override_score_${subId}`).value || 0),
          note: $(`override_note_${subId}`).value.trim() || null,
        };
        const result = await api(`/submissions/${subId}/override`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setLog("Override saved", result);
        await loadSubmissionsForInstructor();
      } catch (err) {
        setLog("Override failed", { error: err.message });
      }
    });
  });
}

function renderPublishedExams(exams) {
  const wrap = $("publishedList");
  wrap.innerHTML = "";
  if (!exams.length) {
    wrap.innerHTML = `<div class="tiny">No published exams right now.</div>`;
    return;
  }

  exams.forEach((e) => {
    const item = document.createElement("div");
    item.className = "list-item";
    item.innerHTML = `
      <div><strong>#${e.id}</strong> ${e.topic}</div>
      <div class="tiny">${e.difficulty || "N/A"} | due: ${safeDateText(e.due_at)}</div>
      <button class="btn btn-light" data-open="${e.id}">Open</button>
    `;
    wrap.appendChild(item);
  });

  wrap.querySelectorAll("[data-open]").forEach((btn) => {
    btn.addEventListener("click", () => openExam(Number(btn.dataset.open)));
  });
}

function renderStudentSubmissionReadOnly(exam, existing) {
  const panel = $("examWorkArea");
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <h3>Exam #${exam.id}: ${exam.topic}</h3>
    <div class="tiny">You already submitted this exam.</div>
    <label>Your Submission</label>
    <textarea rows="6" readonly>${existing.student_answers || ""}</textarea>
    <label>Feedback</label>
    <textarea rows="4" readonly>${existing.ai_feedback || "Not graded yet"}</textarea>
    <div class="tiny">Score: ${existing.numerical_score ?? "pending"}</div>
    <pre class="log">${JSON.stringify(existing.score_breakdown || {}, null, 2)}</pre>
  `;
}

async function openExam(examId) {
  try {
    const exam = await api(`/exams/${examId}`);
    state.currentExam = exam;

    if (state.user && state.user.role === "student") {
      const existing = await api(`/submissions/by-exam?exam_id=${examId}&student_id=${state.user.id}`);
      if (existing.exists) {
        renderStudentSubmissionReadOnly(exam, existing);
        return;
      }
    }

    const panel = $("examWorkArea");
    panel.classList.remove("hidden");

    if (exam.parsed_content?.mcqs || exam.parsed_content?.essays) {
      renderStructuredExam(exam);
    } else {
      panel.innerHTML = `
        <h3>Exam #${exam.id}: ${exam.topic}</h3>
        <label>Content</label>
        <textarea rows="10" readonly>${exam.content || ""}</textarea>
        <label>Your answer</label>
        <textarea id="legacyAnswer" rows="8"></textarea>
        <button id="submitLegacyBtn" class="btn">Submit</button>
      `;
      $("submitLegacyBtn").addEventListener("click", submitLegacyAnswer);
    }
  } catch (err) {
    setLog("Open exam failed", { error: err.message });
  }
}

function renderStructuredExam(exam) {
  const data = exam.parsed_content || {};
  const mcqs = data.mcqs || [];
  const essays = data.essays || [];
  const panel = $("examWorkArea");

  let html = `<h3>Exam #${exam.id}: ${exam.topic}</h3>`;
  html += `<div class="tiny">Difficulty: ${exam.difficulty || "N/A"} | Due: ${safeDateText(exam.due_at)}</div>`;
  html += `<form id="structuredForm">`;

  mcqs.forEach((q, idx) => {
    html += `<div class="list-item"><div><strong>MCQ ${idx + 1}.</strong> ${q.question || ""}</div>`;
    (q.options || []).forEach((opt, optIdx) => {
      html += `
        <label>
          <input type="radio" name="mcq_${idx}" value="${optIdx}" ${optIdx === 0 ? "checked" : ""} />
          ${opt}
        </label>
      `;
    });
    html += `</div>`;
  });

  essays.forEach((q, idx) => {
    html += `
      <div class="list-item">
        <div><strong>Essay ${idx + 1}.</strong> ${q.question || ""}</div>
        <textarea rows="4" id="essay_${idx}" placeholder="Write your answer"></textarea>
      </div>
    `;
  });

  html += `<button type="submit" class="btn">Submit Exam</button></form>`;
  panel.innerHTML = html;

  $("structuredForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    await submitStructuredExam();
  });
}

async function submitStructuredExam() {
  const exam = state.currentExam;
  const parsed = exam.parsed_content || {};
  const mcqs = parsed.mcqs || [];
  const essays = parsed.essays || [];

  const mcq_answers = mcqs.map((q, idx) => {
    const checked = document.querySelector(`input[name="mcq_${idx}"]:checked`);
    const selectedIdx = checked ? Number(checked.value) : 0;
    const options = q.options || [];
    return {
      id: q.id || `MCQ-${idx + 1}`,
      question: q.question || "",
      selected_option_index: selectedIdx,
      selected_option: options[selectedIdx] || "",
    };
  });

  const essay_answers = essays.map((q, idx) => ({
    id: q.id || `ESSAY-${idx + 1}`,
    question: q.question || "",
    answer: ($(`essay_${idx}`)?.value || "").trim(),
  }));

  try {
    const payload = {
      exam_id: exam.id,
      student_id: state.user.id,
      answers: { mcq_answers, essay_answers },
    };
    const result = await api("/submissions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setLog("Exam submitted", result);
    await loadMySubmissions();
  } catch (err) {
    setLog("Submission failed", { error: err.message });
  }
}

async function submitLegacyAnswer() {
  const answer = $("legacyAnswer").value.trim();
  if (!answer) {
    setLog("Submission blocked", { error: "Answer is empty" });
    return;
  }
  try {
    const result = await api("/submissions", {
      method: "POST",
      body: JSON.stringify({
        exam_id: state.currentExam.id,
        student_id: state.user.id,
        answers: answer,
      }),
    });
    setLog("Exam submitted", result);
    await loadMySubmissions();
  } catch (err) {
    setLog("Submission failed", { error: err.message });
  }
}

async function loadMyExams() {
  try {
    const exams = await api(`/exams?created_by=${state.user.id}`);
    renderMyExams(exams);
  } catch (err) {
    setLog("Load exams failed", { error: err.message });
  }
}

async function loadSubmissionsForInstructor() {
  try {
    const list = await api(`/instructors/${state.user.id}/submissions`);
    renderSubmissions(list);
  } catch (err) {
    setLog("Load submissions failed", { error: err.message });
  }
}

async function loadAnalytics() {
  try {
    const data = await api(`/instructors/${state.user.id}/analytics`);
    const box = $("analyticsBox");
    const topicRows = Object.entries(data.average_score_by_topic || {})
      .map(([topic, avg]) => `<div class="list-item">${topic}: <strong>${avg}</strong></div>`)
      .join("");
    const leaderboardRows = (data.leaderboard || [])
      .map((x) => `<div class="list-item">${x.username}: <strong>${x.avg_score}</strong></div>`)
      .join("");
    box.innerHTML = `
      <div class="list-item">Total graded submissions: <strong>${data.total_graded_submissions ?? 0}</strong></div>
      <div class="tiny">Average by topic</div>
      ${topicRows || `<div class="tiny">No topic data</div>`}
      <div class="tiny">Leaderboard</div>
      ${leaderboardRows || `<div class="tiny">No leaderboard data</div>`}
      <details>
        <summary>Raw records</summary>
        <pre class="log">${JSON.stringify(data.records || [], null, 2)}</pre>
      </details>
    `;
  } catch (err) {
    setLog("Load analytics failed", { error: err.message });
  }
}

async function loadMySubmissions() {
  if (!state.user || state.user.role !== "student") return;
  try {
    const list = await api(`/submissions/students/${state.user.id}`);
    const wrap = $("mySubmissionsList");
    wrap.innerHTML = "";
    if (!list.length) {
      wrap.innerHTML = `<div class="tiny">No submissions yet.</div>`;
      return;
    }

    list.forEach((s) => {
      const item = document.createElement("div");
      item.className = "list-item";
      item.innerHTML = `
        <div><strong>Submission #${s.submission_id}</strong> - ${s.exam_topic}</div>
        <div class="tiny">Submitted: ${safeDateText(s.submitted_at)} | Score: ${s.numerical_score ?? "pending"}</div>
        <label>Feedback</label>
        <textarea rows="3" readonly>${s.ai_feedback || "Not graded yet"}</textarea>
        <details>
          <summary>Submission details</summary>
          <textarea rows="4" readonly>${s.student_answers || ""}</textarea>
          <pre class="log">${JSON.stringify(s.score_breakdown || {}, null, 2)}</pre>
        </details>
      `;
      wrap.appendChild(item);
    });
  } catch (err) {
    setLog("Load my submissions failed", { error: err.message });
  }
}

async function loadPublished() {
  try {
    const exams = await api("/exams?status=published");
    renderPublishedExams(exams);
  } catch (err) {
    setLog("Load published exams failed", { error: err.message });
  }
}

async function registerUser() {
  try {
    const payload = {
      username: $("regUsername").value.trim(),
      password: $("regPassword").value,
      role: $("regRole").value,
      email: $("regEmail").value.trim() || null,
    };
    const result = await api("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setLog("Registered", result);
  } catch (err) {
    setLog("Register failed", { error: err.message });
  }
}

async function startOAuth(provider) {
  try {
    const role = $("oauthRole").value;
    const result = await api(`/auth/oauth/${provider}/start?role=${encodeURIComponent(role)}`);
    if (!result.authorize_url) {
      throw new Error("Missing authorize URL");
    }
    window.location.href = result.authorize_url;
  } catch (err) {
    setLog("OAuth start failed", { provider, error: err.message });
  }
}

async function handleOAuthCallback() {
  const params = new URLSearchParams(window.location.search);
  const provider = params.get("provider");
  const code = params.get("code");
  const stateParam = params.get("state");
  if (!provider || !code || !stateParam) {
    return;
  }

  try {
    const result = await api(
      `/auth/oauth/${provider}/callback?exchange=true&code=${encodeURIComponent(code)}&state=${encodeURIComponent(stateParam)}`
    );
    if (result.user) {
      state.user = result.user;
      localStorage.setItem("edugen_user", JSON.stringify(result.user));
      updateSessionUI();
      activateTab(result.user.role === "instructor" ? "instructorTab" : "studentTab");
      setLog("OAuth login success", result.user);
      if (result.user.role === "instructor") {
        await Promise.all([loadMyExams(), loadSubmissionsForInstructor(), loadAnalytics(), loadPdfs()]);
      } else {
        await Promise.all([loadPublished(), loadMySubmissions()]);
      }
    }
    window.history.replaceState({}, document.title, "/");
  } catch (err) {
    setLog("OAuth callback failed", { provider, error: err.message });
  }
}

async function loginUser() {
  try {
    const payload = {
      username: $("loginUsername").value.trim(),
      password: $("loginPassword").value,
    };
    const user = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.user = user;
    localStorage.setItem("edugen_user", JSON.stringify(user));
    updateSessionUI();
    activateTab(user.role === "instructor" ? "instructorTab" : "studentTab");
    setLog("Logged in", user);
    if (user.role === "instructor") {
      await Promise.all([loadMyExams(), loadSubmissionsForInstructor(), loadAnalytics(), loadPdfs()]);
    } else {
      await Promise.all([loadPublished(), loadMySubmissions()]);
    }
  } catch (err) {
    setLog("Login failed", { error: err.message });
  }
}

async function generateExam() {
  try {
    if (!state.user || state.user.role !== "instructor") {
      setLog("Generate blocked", { error: "Instructor login required" });
      return;
    }
    const payload = {
      topic: $("genTopic").value.trim(),
      difficulty: $("genDifficulty").value,
      mcq_count: Number($("genMcqCount").value || 3),
      essay_count: Number($("genEssayCount").value || 2),
    };
    const result = await api("/rag/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("createTopic").value = payload.topic;
    $("createDifficulty").value = payload.difficulty;
    $("createContent").value = result.content || "";
    setLog("Exam generated", { sources: result.sources || [] });
  } catch (err) {
    setLog("Generate failed", { error: err.message });
  }
}

async function createExam() {
  if (!state.user || state.user.role !== "instructor") {
    setLog("Create blocked", { error: "Instructor login required" });
    return;
  }
  try {
    const dueRaw = $("createDueAt").value;
    const payload = {
      instructor_id: state.user.id,
      topic: $("createTopic").value.trim(),
      difficulty: $("createDifficulty").value.trim() || "Beginner",
      content: $("createContent").value,
      status: $("createStatus").value,
      rubric: $("createRubric").value.trim() || null,
      due_at: dueRaw ? new Date(dueRaw).toISOString() : null,
      source_refs: [],
    };
    const result = await api("/exams", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setLog("Exam created", result);
    await loadMyExams();
  } catch (err) {
    setLog("Create exam failed", { error: err.message });
  }
}

async function uploadPdfs() {
  if (!state.user || state.user.role !== "instructor") {
    setLog("Upload blocked", { error: "Instructor login required" });
    return;
  }
  const input = $("pdfUploadInput");
  const files = input.files ? Array.from(input.files) : [];
  if (!files.length) {
    setLog("Upload blocked", { error: "Select at least one PDF file" });
    return;
  }

  try {
    const formData = new FormData();
    formData.append("instructor_id", String(state.user.id));
    files.forEach((file) => formData.append("files", file));
    const result = await apiForm("/rag/pdfs/upload", formData);
    setLog("PDF upload result", result);
    await loadPdfs();
    input.value = "";
  } catch (err) {
    setLog("PDF upload failed", { error: err.message });
  }
}

async function loadPdfs() {
  try {
    const result = await api("/rag/pdfs");
    const pdfs = result.pdfs || [];
    $("pdfList").textContent = pdfs.length ? `Knowledge PDFs: ${pdfs.join(", ")}` : "Knowledge PDFs: none";
  } catch (err) {
    setLog("Load PDFs failed", { error: err.message });
  }
}

function bindEvents() {
  $("registerBtn").addEventListener("click", registerUser);
  $("loginBtn").addEventListener("click", loginUser);
  $("logoutBtn").addEventListener("click", () => {
    state.user = null;
    localStorage.removeItem("edugen_user");
    updateSessionUI();
  });

  $("generateBtn").addEventListener("click", generateExam);
  $("createExamBtn").addEventListener("click", createExam);
  $("loadMyExamsBtn").addEventListener("click", loadMyExams);
  $("loadSubmissionsBtn").addEventListener("click", loadSubmissionsForInstructor);
  $("loadPublishedBtn").addEventListener("click", loadPublished);
  $("loadMySubmissionsBtn").addEventListener("click", loadMySubmissions);
  $("loadAnalyticsBtn").addEventListener("click", loadAnalytics);
  $("uploadPdfsBtn").addEventListener("click", uploadPdfs);
  $("loadPdfsBtn").addEventListener("click", loadPdfs);
  $("googleOAuthBtn").addEventListener("click", () => startOAuth("google"));
  $("githubOAuthBtn").addEventListener("click", () => startOAuth("github"));

  document.querySelectorAll(".tab").forEach((t) => {
    t.addEventListener("click", () => activateTab(t.dataset.tab));
  });
}

async function hydrateForRole() {
  if (!state.user) return;
  if (state.user.role === "instructor") {
    await Promise.all([loadMyExams(), loadSubmissionsForInstructor(), loadAnalytics(), loadPdfs()]);
    activateTab("instructorTab");
  } else {
    await Promise.all([loadPublished(), loadMySubmissions()]);
    activateTab("studentTab");
  }
}

function bootstrap() {
  bindEvents();
  const saved = localStorage.getItem("edugen_user");
  if (saved) {
    try {
      state.user = JSON.parse(saved);
    } catch (_) {
      state.user = null;
    }
  }
  updateSessionUI();
  handleOAuthCallback();
  hydrateForRole();
  setLog("Frontend ready");
}

bootstrap();
