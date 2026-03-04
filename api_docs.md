# EduGen API Documentation

This document provides detailed information about the EduGen backend API endpoints. It is designed to help a frontend developer (human or AI) understand how to interact with the backend.

---

## Base URL
The base URL for the API is typically `http://localhost:8000` (or as configured in your environment).

---

## 1. Authentication & User Management

### Register User
*   **Path:** `/auth/register`
*   **Method:** `POST`
*   **Description:** Creates a new user account.
*   **Request Body (JSON):**
    ```json
    {
      "username": "string (min 3, max 80)",
      "password": "string (min 6, max 200)",
      "role": "student" | "instructor",
      "email": "string | null"
    }
    ```
*   **Response (200 OK):**
    ```json
    {
      "id": 123,
      "username": "johndoe",
      "role": "instructor"
    }
    ```

### Login User (Local)
*   **Path:** `/auth/login`
*   **Method:** `POST`
*   **Description:** Authenticates a user using username and password.
*   **Request Body (JSON):**
    ```json
    {
      "username": "string",
      "password": "string"
    }
    ```
*   **Response (200 OK):**
    ```json
    {
      "id": 123,
      "username": "johndoe",
      "role": "instructor"
    }
    ```

### OAuth Providers
*   **Path:** `/auth/oauth/providers`
*   **Method:** `GET`
*   **Description:** Returns a list of configured OAuth providers (e.g., Google, GitHub).
*   **Response:**
    ```json
    {
      "providers": {
        "google": { "label": "Google", "configured": true },
        "github": { "label": "GitHub", "configured": false }
      }
    }
    ```

### Start OAuth Flow
*   **Path:** `/auth/oauth/{provider}/start`
*   **Method:** `GET`
*   **Query Params:** `role` (default: "student")
*   **Description:** Returns the URL to redirect the user to for OAuth authentication.
*   **Response:**
    ```json
    { "authorize_url": "https://..." }
    ```

---

## 2. Exams Management (Instructors)

### Create Exam
*   **Path:** `/exams`
*   **Method:** `POST`
*   **Description:** Creates a new exam. Requires instructor role.
*   **Request Body (JSON):**
    ```json
    {
      "instructor_id": 1,
      "topic": "Python Basics",
      "difficulty": "Beginner" | "Intermediate" | "Advanced",
      "content": "JSON string or markdown",
      "status": "draft" | "published" | "archived",
      "rubric": "Optional grading guidelines",
      "due_at": "ISO-8601 Datetime | null",
      "source_refs": ["file1.pdf", "file2.pdf"]
    }
    ```
*   **Response:**
    ```json
    { "id": 10, "version": 1 }
    ```

### Update Exam
*   **Path:** `/exams/{exam_id}`
*   **Method:** `PUT`
*   **Description:** Updates an existing exam (status, due date, rubric). Increments version.
*   **Request Body (JSON):**
    ```json
    {
      "instructor_id": 1,
      "status": "published",
      "due_at": "ISO-8601 Datetime | null",
      "rubric": "Updated rubric"
    }
    ```
*   **Response:**
    ```json
    { "id": 10, "version": 2 }
    ```

### List Exams
*   **Path:** `/exams`
*   **Method:** `GET`
*   **Query Params:**
    *   `status`: "draft" | "published" | "archived" (optional)
    *   `created_by`: instructor_id (optional)
*   **Response:** List of exam summaries.

### Get Exam Details
*   **Path:** `/exams/{exam_id}`
*   **Method:** `GET`
*   **Description:** Returns full details of a specific exam, including `parsed_content` (AI generated structure).

### Get Exam Versions
*   **Path:** `/exams/{exam_id}/versions`
*   **Method:** `GET`
*   **Description:** Returns the history of changes for an exam.

---

## 3. RAG & Content Generation (Instructors)

### Generate Exam Content
*   **Path:** `/rag/generate`
*   **Method:** `POST`
*   **Description:** Uses AI (RAG) to generate exam questions based on a topic and uploaded PDFs.
*   **Request Body (JSON):**
    ```json
    {
      "topic": "History of Rome",
      "difficulty": "Intermediate",
      "mcq_count": 5,
      "essay_count": 2
    }
    ```
*   **Response:**
    ```json
    {
      "content": "Raw AI generated text",
      "sources": ["Rome_Overview.pdf"]
    }
    ```

### List Uploaded PDFs
*   **Path:** `/rag/pdfs`
*   **Method:** `GET`
*   **Description:** Returns a list of all PDF filenames available in the RAG system.

### Upload PDFs
*   **Path:** `/rag/pdfs/upload`
*   **Method:** `POST`
*   **Type:** `multipart/form-data`
*   **Form Data:**
    *   `instructor_id`: int
    *   `files`: List of PDF files
*   **Description:** Uploads PDFs to the RAG knowledge base.

---

## 4. Submissions & Grading

### Submit Exam (Student)
*   **Path:** `/submissions`
*   **Method:** `POST`
*   **Description:** Student submits answers to a published exam.
*   **Request Body (JSON):**
    ```json
    {
      "exam_id": 1,
      "student_id": 42,
      "answers": { "q1": "A", "q2": "Berlin" } | "raw text string"
    }
    ```
*   **Response:**
    ```json
    { "id": 500 }
    ```

### Grade Submission (Instructor)
*   **Path:** `/submissions/grade`
*   **Method:** `POST`
*   **Description:** Triggers AI grading for a submission.
*   **Request Body (JSON):**
    ```json
    {
      "submission_id": 500,
      "instructor_id": 1
    }
    ```
*   **Response:**
    ```json
    {
      "submission_id": 500,
      "score": 85,
      "feedback": "AI feedback text",
      "score_breakdown": { ... }
    }
    ```

### Manual Grade Override
*   **Path:** `/submissions/{submission_id}/override`
*   **Method:** `PUT`
*   **Description:** Allows instructor to manually set/overwrite a student's score.
*   **Request Body (JSON):**
    ```json
    {
      "instructor_id": 1,
      "score": 90,
      "note": "Great improvement"
    }
    ```

### Get Student Submission for Specific Exam
*   **Path:** `/submissions/by-exam`
*   **Method:** `GET`
*   **Query Params:** `exam_id`, `student_id`
*   **Description:** Returns the latest submission for a combination of exam and student. Useful for checking if already submitted.

### List All Submissions for a Student
*   **Path:** `/submissions/students/{student_id}`
*   **Method:** `GET`
*   **Response:** List of all submissions by the student with scores and feedback.

---

## 5. Analytics & Audit

### Instructor Submissions List
*   **Path:** `/instructors/{instructor_id}/submissions`
*   **Method:** `GET`
*   **Description:** Lists all submissions for all exams created by this instructor.

### Instructor Analytics
*   **Path:** `/instructors/{instructor_id}/analytics`
*   **Method:** `GET`
*   **Description:** Aggregated data like average scores by topic, leaderboard of students, and distribution.

### Student Subject Analytics (from Supabase `students` table)
*   **Path:** `/instructors/instructor/students/analytics`
*   **Method:** `GET`
*   **Description:** Returns aggregated statistics from the Supabase `students` table — averages per subject, min/max, top/bottom 5 students, and breakdown by grade level.
*   **Response (200 OK):**
    ```json
    {
      "averages": { "math": 75.5, "physics": 68.2, ... },
      "averages_total": 71.3,
      "min_max": { "math": { "min": 30, "max": 100 }, ... },
      "total_percent_min_max": { "min": 40, "max": 98 },
      "top_5": [{ "student_id": 1, "first_name": "Ali", "total_percent": 98 }, ...],
      "bottom_5": [{ "student_id": 5, "first_name": "Sara", "total_percent": 40 }, ...],
      "by_grade": { "10": { "count": 15, "avg_total": 72.5 }, ... }
    }
    ```

### Ask Question (Text-to-SQL)
*   **Path:** `/instructors/ask`
*   **Method:** `POST`
*   **Description:** Accepts a natural-language question about student data, converts it to SQL using AI, executes it, and returns results.
*   **Request Body (JSON):**
    ```json
    { "question": "Who scored above 80 in math?" }
    ```
*   **Response (200 OK):**
    ```json
    {
      "sql": "SELECT * FROM students WHERE math > 80;",
      "results": [{ "student_id": 1, "first_name": "Ali", "math": 95, ... }],
      "error": null
    }
    ```
*   **Note:** Only SELECT queries are allowed. If the AI-generated SQL is invalid, `results` will be `null` and `error` will contain the error message.

### Audit Logs
*   **Path:** `/audit-logs`
*   **Method:** `GET`
*   **Query Params:** `limit` (default 200, max 1000)
*   **Description:** Returns a system-wide log of events (logins, creates, grades).

---

## 6. System
### Health Check
*   **Path:** `/health`
*   **Method:** `GET`
*   **Description:** Returns the status of the backend and its connections (Database, Groq, OAuth).
