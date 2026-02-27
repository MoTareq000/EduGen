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
      <div class="tiny">${e.difficulty || "N/A"} | status: ${e.status || "draft"} | due: ${e.due_at || "none"}</div>
    `;
    wrap.appendChild(item);
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
      <div class="tiny">Student: ${s.student_username} | Score: ${s.numerical_score ?? "Not graded"}</div>
      <button class="btn btn-light" data-grade="${s.submission_id}">Auto Grade</button>
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
      <div class="tiny">${e.difficulty || "N/A"} | due: ${e.due_at || "none"}</div>
      <button class="btn btn-light" data-open="${e.id}">Open</button>
    `;
    wrap.appendChild(item);
  });

  wrap.querySelectorAll("[data-open]").forEach((btn) => {
    btn.addEventListener("click", () => openExam(Number(btn.dataset.open)));
  });
}

async function openExam(examId) {
  try {
    const exam = await api(`/exams/${examId}`);
    state.currentExam = exam;

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
  html += `<div class="tiny">Difficulty: ${exam.difficulty || "N/A"} | Due: ${exam.due_at || "none"}</div>`;
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
  } catch (err) {
    setLog("Submission failed", { error: err.message });
  }
}

async function loadMyExams() {
  try {
    const exams = await api("/exams");
    renderMyExams(exams.filter((x) => Number(x.created_by) === Number(state.user.id)));
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
  } catch (err) {
    setLog("Login failed", { error: err.message });
  }
}

async function generateExam() {
  try {
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

  document.querySelectorAll(".tab").forEach((t) => {
    t.addEventListener("click", () => activateTab(t.dataset.tab));
  });
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
  if (state.user) {
    activateTab(state.user.role === "instructor" ? "instructorTab" : "studentTab");
  }
  setLog("Frontend ready");
}

bootstrap();
