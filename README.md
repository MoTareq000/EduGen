# 🎓 AI University Portal: RAG-Powered LMS

An intelligent Learning Management System (LMS) that utilizes **Retrieval-Augmented Generation (RAG)** and **Llama 3.3-70B** to automate the creation and grading of academic assessments based on local PDF knowledge bases.

---

## 🌟 Key Features

- **PDF Knowledge Integration:** Automatically indexes and retrieves context from a library of academic PDFs using **FAISS** and **LangChain**.
- **AI Exam Generation:** Instructors can generate technical exams (MCQs and Essays) with "Model Answer Keys" tailored to specific course materials.
- **Auto-Grading Engine:** Uses **Llama 3.3-70B** to compare student submissions against answer keys, providing numerical scores and qualitative feedback.
- **Performance Analytics:** Interactive dashboards visualizing average scores, topic mastery, and student progress trends.
- **Role-Based Access Control:** Secure portals for **Instructors** (management/grading) and **Students** (testing/feedback).

---

## 🛠️ Technology Stack

| Component | Technology |
|------------|----------------|
| **Frontend** | Streamlit |
| **LLM Engine** | Llama 3.3-70B (via Groq SDK) |
| **Vector DB** | FAISS (Facebook AI Similarity Search) |
| **Embeddings** | HuggingFace (`all-MiniLM-L6-v2`) |
| **Database** | PostgreSQL 16+ (with JSONB support) |
| **Data Processing** | Pandas & PyMuPDF |

---

## 📊 Data Description (JSON Schema)

The portal handles data using four primary JSON structures to ensure flexibility and analytical depth:

### 👤 User Data

Manages student/instructor profiles and course enrollments.

```json
{
  "user_id": "USR-12345",
  "role": "student",
  "enrolled_courses": ["COURSE-CS101"],
  "preferences": {
    "language": "en",
    "notifications": true
  }
}
📝 Exam Data
Defines assessed content, including question types and difficulty levels.

{
  "exam_id": "EXAM-456",
  "questions": [
    {
      "question_id": "Q-001",
      "type": "multiple_choice",
      "text": "What is the time complexity of binary search?",
      "options": ["O(n)", "O(log n)", "O(n^2)", "O(1)"],
      "correct_answer": "O(log n)"
    }
  ]
}
🚀 Installation & Setup
1️⃣ Prerequisites
Python 3.9+

PostgreSQL 16+

Groq API Key

2️⃣ Clone & Install
git clone https://github.com/your-username/ai-university-portal.git
cd ai-university-portal
pip install -r requirements.txt
3️⃣ Database Initialization
Run the following SQL in your PostgreSQL Query Tool to set up the necessary tables:

CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    role TEXT,
    preferences JSONB
);

CREATE TABLE exams (
    exam_id TEXT PRIMARY KEY,
    topic TEXT,
    content JSONB,
    created_by TEXT REFERENCES users(user_id)
);

CREATE TABLE submissions (
    grading_id SERIAL PRIMARY KEY,
    student_id TEXT,
    exam_id TEXT,
    total_score INTEGER,
    scores JSONB
);
4️⃣ Run the Portal
streamlit run app.py
📂 Project Structure
├── app.py              # Main Streamlit application and UI logic
├── rag_pipeline.py     # PDF indexing, retrieval, and AI interaction
├── pdfs/               # Academic PDF knowledge base
├── requirements.txt    # Python dependencies
└── README.md           # Project documentation
🤝 Contribution
Contributions, feature requests, and improvements are welcome. Feel free to fork the repository and submit pull requests.

📜 License
This project is licensed under the MIT License - see the LICENSE file for details.
