# EduGen — Frontend Implementation Prompt

You are building the React/TypeScript frontend for **EduGen**, an AI-powered educational platform. The backend is a FastAPI server. Below is everything you need: the full API reference, the current frontend code structure, and the exact changes required.

---

## Current Frontend Stack
- **Framework:** React + TypeScript + Vite
- **UI:** shadcn/ui components (already installed)
- **State:** React Context (`AuthContext` stores the logged-in `User`)

## User Model (returned by login/register and stored in context)
```json
{ "id": 123, "username": "johndoe", "role": "instructor" | "student" }
```
> **Important:** Many endpoints require `instructor_id` or `student_id`. Always use `user.id` from the auth context.

---

## Complete API Reference

### Base URL
`http://localhost:8000` — read from `import.meta.env.VITE_API_URL` with fallback.

---

### 1. Authentication (`/auth`)

| Method | Path | Body / Params | Response |
|--------|------|--------------|----------|
| `POST` | `/auth/register` | `{ username, password, role, email? }` | `{ id, username, role }` |
| `POST` | `/auth/login` | `{ username, password }` | `{ id, username, role }` |
| `GET` | `/auth/oauth/providers` | — | `{ providers: { google: { label, configured }, github: { label, configured } } }` |
| `GET` | `/auth/oauth/{provider}/start?role=student` | — | `{ authorize_url }` |
| `GET` | `/auth/oauth/{provider}/callback?code=...&state=...&exchange=true` | — | `{ message, provider, user: { id, username, role } }` |

**Notes:**
- `register` body: `username` (3-80 chars), `password` (6-200 chars), `role` ("student" | "instructor"), `email` (optional).
- After OAuth redirect, the frontend receives `?provider=...&code=...&state=...` as query params on `/`. The frontend should then call the callback with `exchange=true` to complete login.

---

### 2. Exams (`/exams`)

| Method | Path | Body / Params | Response |
|--------|------|--------------|----------|
| `POST` | `/exams` | `{ instructor_id, topic, difficulty, content, status?, rubric?, due_at?, source_refs? }` | `{ id, version }` |
| `PUT` | `/exams/{exam_id}` | `{ instructor_id, status, due_at?, rubric? }` | `{ id, version }` |
| `GET` | `/exams` | Query: `status?`, `created_by?` | Array of exam summaries |
| `GET` | `/exams/{exam_id}` | — | Full exam object with `parsed_content` |
| `GET` | `/exams/{exam_id}/versions` | — | Array of version history objects |

**Exam summary object:**
```json
{ "id": 1, "topic": "...", "difficulty": "...", "status": "draft|published|archived", "due_at": "...", "created_by": 1, "version": 1, "rubric": "..." }
```

**Full exam object** (from `GET /exams/{id}`):
```json
{
  "id": 1, "topic": "...", "difficulty": "...",
  "content": "raw JSON string of the exam",
  "parsed_content": { "mcq": [...], "essay": [...] },
  "status": "published", "due_at": "...", "rubric": "...",
  "source_refs": ["file1.pdf"], "version": 2
}
```
> `parsed_content` is the backend-parsed JSON of `content`. Use this to render questions for students.

**`status` values:** `"draft"` → `"published"` → `"archived"`.
- Only `"published"` exams are visible to students.
- `due_at` is an ISO-8601 datetime; if set and in the past, the exam is closed for submissions.
- `source_refs` is a list of PDF filenames used during generation.

---

### 3. RAG & Content Generation (`/rag`)

| Method | Path | Body / Params | Response |
|--------|------|--------------|----------|
| `POST` | `/rag/generate` | `{ topic, difficulty?, mcq_count?, essay_count? }` | `{ content, sources }` |
| `GET` | `/rag/pdfs` | — | `{ pdfs: ["file1.pdf", ...] }` |
| `POST` | `/rag/pdfs/upload` | `multipart/form-data`: `instructor_id` (int) + `files` (PDF files) | `{ added: [...], skipped: [...], failed: [...] }` |

**Notes:**
- `difficulty` defaults to `"Beginner"`. `mcq_count` defaults to 3 (1-20). `essay_count` defaults to 2 (0-10).
- PDF upload max: 20 files, 20MB each, `.pdf` only.
- The `content` returned by `/rag/generate` should be passed as-is to `POST /exams` as the `content` field.

---

### 4. Submissions & Grading (`/submissions`)

| Method | Path | Body / Params | Response |
|--------|------|--------------|----------|
| `POST` | `/submissions` | `{ exam_id, student_id, answers }` | `{ id }` |
| `POST` | `/submissions/grade` | `{ submission_id, instructor_id }` | `{ submission_id, score, feedback, score_breakdown }` |
| `PUT` | `/submissions/{id}/override` | `{ instructor_id, score (0-100), note? }` | `{ submission_id, score, note }` |
| `GET` | `/submissions/by-exam?exam_id=...&student_id=...` | — | `{ exists: bool, ...submission }` |
| `GET` | `/submissions/students/{student_id}` | — | Array of student submissions |

**`answers` field:** Can be either a `dict` (e.g. `{ "q1": "A", "q2": "Berlin" }`) or a raw `string`. Prefer `dict` format for structured exams.

**Student submission object:**
```json
{
  "submission_id": 1, "exam_id": 1, "exam_topic": "...",
  "student_answers": "...", "ai_feedback": "...",
  "numerical_score": 85, "score_breakdown": { ... },
  "grader_note": "...", "submitted_at": "..."
}
```

**Validation rules:**
- A student can only submit once per exam (409 if duplicate).
- The exam must be `"published"` and not past `due_at`.
- Only the instructor who created the exam can grade/override its submissions.

---

### 5. Instructor Dashboard (`/instructors`)

| Method | Path | Body / Params | Response |
|--------|------|--------------|----------|
| `GET` | `/instructors/{instructor_id}/submissions` | — | All submissions for this instructor's exams |
| `GET` | `/instructors/{instructor_id}/analytics` | — | Analytics object (see below) |
| `GET` | `/instructors/instructor/students/analytics` | — | Student subject analytics (see below) |
| `POST` | `/instructors/ask` | `{ question }` | `{ sql, results, error }` |

**Analytics response** (`GET /instructors/{id}/analytics`):
```json
{
  "total_graded_submissions": 42,
  "average_score_by_topic": { "Python": 78.5, "History": 65.2 },
  "score_distribution": [85, 72, 90, ...],
  "leaderboard": [{ "username": "ali", "avg_score": 92.5 }, ...],
  "records": [{ "topic": "...", "numerical_score": 85, "username": "...", "submitted_at": "..." }, ...]
}
```

**Student Subject Analytics response** (`GET /instructors/instructor/students/analytics`):
```json
{
  "averages": { "math": 75.5, "physics": 68.2, "chemistry": 72.1, "biology": 80.0, "programming": 65.3, "english": 77.8 },
  "averages_total": 71.3,
  "min_max": { "math": { "min": 30, "max": 100 }, ... },
  "total_percent_min_max": { "min": 40.0, "max": 98.0 },
  "top_5": [{ "student_id": 1, "first_name": "Ali", "total_percent": 98.0 }, ...],
  "bottom_5": [{ "student_id": 5, "first_name": "Sara", "total_percent": 40.0 }, ...],
  "by_grade": { "10": { "count": 15, "avg_total": 72.5 }, "11": { "count": 12, "avg_total": 68.9 } }
}
```
> The 6 subjects are: **math, physics, chemistry, biology, programming, english**.

**Text-to-SQL response** (`POST /instructors/ask`):
```json
{
  "sql": "SELECT * FROM students WHERE math > 80;",
  "results": [{ "student_id": 1, "first_name": "Ali", "math": 95, ... }],
  "error": null
}
```
> If the query fails, `results` is `null` and `error` contains the message. Only SELECT queries are allowed.

---

### 6. System

| Method | Path | Response |
|--------|------|----------|
| `GET` | `/health` | `{ status, service, startup_errors, checks: { database, groq_api, google_oauth, github_oauth } }` |
| `GET` | `/audit-logs?limit=200` | Array of `{ id, user_id, event_type, meta, created_at }` |

---

## What Needs to Change in the Frontend

### `src/lib/api.ts` — Complete Rewrite
endpoint mapping:**

|----------|----------|
`POST /auth/register` |
`POST /auth/login` |
`POST /rag/generate` |
`GET /exams?status=published` |
|`GET /exams/{examId}` |
`POST /submissions` |
`GET /instructors/{instructorId}/submissions` |
 `POST /submissions/grade` |
`POST /instructors/ask` |

**New endpoints to add :**
- `POST /exams` — save generated exam
- `PUT /exams/{id}` — update/publish exam
- `GET /exams/{id}/versions` — exam version history
- `GET /rag/pdfs` — list uploaded PDFs
- `POST /rag/pdfs/upload` — upload PDFs (multipart/form-data)
- `GET /submissions/students/{id}` — student results
- `GET /submissions/by-exam?exam_id=...&student_id=...` — check if already submitted
- `PUT /submissions/{id}/override` — manual grade override
- `GET /instructors/{id}/analytics` — instructor analytics
- `GET /instructors/instructor/students/analytics` — student subject analytics
- OAuth endpoints (providers, start, callback)

**TypeScript interfaces to update:**

```typescript

interface Exam {
  id: number; topic: string; difficulty: string;
  status: "draft" | "published" | "archived";
  due_at: string | null; created_by: number;
  version: number; rubric: string | null;
  content?: string;               // raw JSON string
  parsed_content?: ParsedExam;     // only on GET /exams/{id}
  source_refs?: string[];
}

// OLD Submission has student_answers as Record, score, feedback, graded — CHANGE
// NEW:
interface Submission {
  submission_id: number; exam_id: number;
  exam_topic?: string; student_id?: number;
  student_username?: string; student_answers: string;
  ai_feedback: string | null; numerical_score: number | null;
  score_breakdown: object | null; grader_note: string | null;
  submitted_at: string; exam_content?: string; rubric?: string;
}
```

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';


---

### Page-Level Changes

#### `AuthPage.tsx`
- `authAPI.signup(...)` → `authAPI.register(...)` (function rename)
- Add optional `email` field to the registration form
- Add OAuth login buttons: call `GET /auth/oauth/providers` to check which are configured, then use `GET /auth/oauth/{provider}/start?role=...` to get the redirect URL

#### `OAuthCallback.tsx`
- Read `provider`, `code`, `state` from URL query params
- Call `GET /auth/oauth/{provider}/callback?code=...&state=...&exchange=true`
- On success, store returned `user` in auth context

#### `App.tsx`
- Add route for OAuth callback page

#### `ExamGenerator.tsx` (Instructor)
- `examAPI.generate(...)` → `ragAPI.generate({ topic, difficulty, mcq_count, essay_count })`
- Response: `{ content, sources }` — NOT `{ exam_content }`
- Add a **"Save Exam"** button that calls `POST /exams` with `{ instructor_id: user.id, topic, difficulty, content: res.content, status: "draft", source_refs: res.sources }`
- Add a **"Publish"** button that calls `PUT /exams/{id}` with `{ instructor_id: user.id, status: "published" }`
- Add a **PDF upload section**: list PDFs from `GET /rag/pdfs`, upload via `POST /rag/pdfs/upload`

#### `GradingHub.tsx` (Instructor)
- `gradingAPI.getSubmissions()` → `GET /instructors/{user.id}/submissions`
- `gradingAPI.grade(submissionId)` → `POST /submissions/grade` with `{ submission_id, instructor_id: user.id }`
- Add **manual override** UI: call `PUT /submissions/{id}/override` with `{ instructor_id, score, note }`
- Update interfaces: `submission_id` not `id`, `numerical_score` not `score`, `ai_feedback` not `feedback`

#### `Students.tsx` (Instructor)
- Call `GET /instructors/instructor/students/analytics` to get per-subject averages, min/max, top/bottom 5, and by-grade breakdown
- Also call `GET /instructors/{user.id}/analytics` for exam-based analytics (leaderboard, score distribution, avg by topic)
- Build dashboard with both data sources

#### `EduGenInsights.tsx` (Instructor)
- `insightAPI.ask(question)` → `POST /instructors/ask` with `{ question }`
- Response is `{ sql, results, error }` — handle `error` field (show error message if not null, show results table if null)
- Example questions to suggest in UI: "Who scored above 80?", "Average score in Math?", "Students who failed?", "Top 5 students?"

#### `MyExams.tsx` (Student)
- `examAPI.getStudentExams(user.id)` → `GET /exams?status=published`
- Before showing "Take Exam", check `GET /submissions/by-exam?exam_id=...&student_id=...` — if `exists: true`, show score/feedback instead
- Update `Exam` interface (no more `mcq_count`/`essay_count`/`exam_text`)

#### `ExamWindow.tsx` (Student)
- `examAPI.getExamContent(id)` → `GET /exams/{id}` — use `parsed_content` to render questions
- `examAPI.submit(...)` → `POST /submissions` with `{ exam_id, student_id: user.id, answers }` (NOT `student_answers`)
- Check `due_at` before allowing submission

#### `Results.tsx` (Student)
- Call `GET /submissions/students/{user.id}` to get all past submissions
- Display list with: `exam_topic`, `numerical_score`, `ai_feedback`, `grader_note`, `submitted_at`

---

## Error Handling

All endpoints return standard HTTP errors:
| Code | Meaning |
|------|---------|
| `400` | Bad request (validation error, exam not published, exam closed) |
| `401` | Invalid credentials |
| `403` | Not authorized (not instructor, not exam owner) |
| `404` | Resource not found |
| `409` | Conflict (username exists, already submitted) |
| `422` | Validation error (Pydantic) |
| `502` | AI/external service error |
| `500` | Internal server error |

---

## Important Implementation Notes
1. The backend has **NO JWT/token-based auth** — it uses simple user ID checking. Store the `user` object from login in context/localStorage and pass `user.id` as `instructor_id` or `student_id` in requests.
2. The `content` field in exams is a JSON string. The backend provides a `parsed_content` helper, but only on `GET /exams/{id}`.
3. For PDF uploads, use `FormData` with `Content-Type: multipart/form-data` — do NOT set `Content-Type` manually (let the browser set it with the boundary).
4. The `answers` field in submissions accepts both `dict` and `string`. Use `dict` format `{ "q1": "A", "q2": "text..." }` for structured exams.
5. Grading (`POST /submissions/grade`) triggers an AI call and may take a few seconds — show a loading spinner.
