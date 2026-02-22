# EduGen - AI University Portal

EduGen is a Streamlit-based university assessment platform that combines:

- Social/local authentication
- AI-assisted exam generation from course PDFs (RAG)
- Student exam submission
- Instructor grading and analytics

## Features

- Google and GitHub OAuth login/signup
- Local username/password fallback auth
- Role-based access (`student`, `instructor`)
- Instructor exam generation with:
  - Draft/Published/Archived status
  - Optional due date/time
  - Rubric field
  - Version history
- Student portal showing only published, open exams
- Structured submissions (MCQ + essays)
- AI grading + manual instructor score override
- Analytics dashboard + CSV export
- Runtime DB schema migration and health checks
- Audit logs for key actions (login, exam updates, grading, submissions)

## Tech Stack

- Python + Streamlit
- PostgreSQL (Supabase compatible)
- LangChain + FAISS
- HuggingFace embeddings
- Groq API for generation/grading

## Project Structure

- `app.py` - Main Streamlit app
- `setup_db.py` - Database setup/migrations script
- `rag_pipeline.py` - RAG generation/grading pipeline
- `requirements.txt` - Python dependencies
- `pdfs/` - Course documents used for retrieval
- `faiss_index/` - Local FAISS vector index

## Prerequisites

- Python 3.10+
- PostgreSQL database (or Supabase Postgres)
- Groq API key
- OAuth apps (Google + GitHub) if using social login

## Environment Variables

Create `.env` (local) or Streamlit Secrets (deployment):

```env
GROQ_API_KEY=...
GROQ_MODEL=llama-3.3-70b-versatile

DATABASE_URL=postgresql://...
# OR use SUPABASE_* values:
SUPABASE_PROJECT_REF=
SUPABASE_DB_PASSWORD=
SUPABASE_DB_USER=postgres
SUPABASE_DB_NAME=postgres
SUPABASE_DB_HOST=
SUPABASE_DB_PORT=5432

APP_BASE_URL=http://localhost:8501
OAUTH_STATE_SECRET=replace-with-a-long-random-secret

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
```

## Local Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Initialize/update database schema:

```bash
python setup_db.py
```

3. Run app:

```bash
streamlit run app.py
```

## OAuth Redirect URLs

Use exact callback URLs:

- Google: `http://localhost:8501/?provider=google`
- GitHub: `http://localhost:8501/?provider=github`

For production, replace with your deployed Streamlit URL:

- `https://<your-app>.streamlit.app/?provider=google`
- `https://<your-app>.streamlit.app/?provider=github`

## Streamlit Cloud Deployment

1. Push code to GitHub.
2. Deploy repo on Streamlit Cloud.
3. Add required keys in **App Settings -> Secrets**.
4. Ensure `APP_BASE_URL` matches deployed URL.
5. Restart/redeploy.

## Troubleshooting

- `OAuth not configured`:
  - Missing OAuth keys in `.env` (local) or Streamlit Secrets (cloud).

- `OAuth state mismatch`:
  - Ensure stable `OAUTH_STATE_SECRET` is set in deployment.
  - Ensure callback URLs exactly match provider config.

- `column oauth_provider does not exist`:
  - Run `python setup_db.py` or restart app (runtime schema migration runs on startup).

- `could not create unique index users_email_lower_uniq`:
  - DB has duplicate emails. Current migration safely skips unique index and keeps non-unique lookup index.

## Security Notes

- Do not commit real secrets to GitHub.
- Rotate any exposed keys immediately.
- Use Streamlit Secrets for production credentials.

## License

No license file is currently defined. Add one if you plan to open-source this project.
