import json
import os
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
from langchain_core.documents import Document

# =========================
# CONFIGURATION
# =========================
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
CURRENT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("Missing GROQ_API_KEY in environment.")
GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)


class RAGPipeline:
    def __init__(self, pdf_folder="pdfs"):
        print("Initializing Knowledge Base...")
        self.pdf_folder = pdf_folder
        self.faiss_index_path = "faiss_index"
        self.embeddings = None
        self.embeddings_error = None
        self.faiss_cls = None
        self.faiss_error = None
        self.db = None
        self.chunk_store = []

        if not os.path.exists(self.pdf_folder):
            os.makedirs(self.pdf_folder)

        self.embeddings = self._load_embeddings()
        if self.embeddings is None:
            self.chunk_store = self._load_all_pdf_chunks()
            if not self.chunk_store:
                print("Warning: no PDF content found in 'pdfs' folder; RAG will run without retrieval.")
            return

        self.faiss_cls = self._load_faiss_class()
        if self.faiss_cls is None:
            self.chunk_store = self._load_all_pdf_chunks()
            if not self.chunk_store:
                print("Warning: no PDF content found in 'pdfs' folder; RAG will run without retrieval.")
            return

        if os.path.exists(self.faiss_index_path):
            try:
                self.db = self.faiss_cls.load_local(
                    self.faiss_index_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
            except Exception as exc:
                print(f"Warning: failed to load FAISS index from '{self.faiss_index_path}': {exc}")
                self._rebuild_or_fallback_chunks()
        else:
            self._rebuild_or_fallback_chunks()

    def _load_embeddings(self):
        try:
            from langchain_huggingface import HuggingFaceEmbeddings

            return HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
        except Exception as exc:
            # Windows torch installs can fail to load fbgemm.dll. Keep RAG alive
            # by falling back to lexical retrieval over PDF chunks.
            self.embeddings_error = str(exc)
            print(
                "Warning: embeddings backend unavailable; using lexical PDF retrieval fallback: "
                f"{exc}"
            )
            return None

    def _load_faiss_class(self):
        try:
            from langchain_community.vectorstores import FAISS

            return FAISS
        except Exception as exc:
            self.faiss_error = str(exc)
            print(
                "Warning: FAISS backend unavailable; using lexical PDF retrieval fallback: "
                f"{exc}"
            )
            return None

    def _split_documents(self, docs, chunk_size: int = 1000, chunk_overlap: int = 150):
        chunks = []
        step = max(chunk_size - chunk_overlap, 1)

        for doc in docs:
            content = (getattr(doc, "page_content", "") or "").strip()
            if not content:
                continue

            metadata = dict(getattr(doc, "metadata", {}) or {})
            if len(content) <= chunk_size:
                chunks.append(Document(page_content=content, metadata=metadata))
                continue

            start = 0
            while start < len(content):
                end = min(len(content), start + chunk_size)
                piece = content[start:end].strip()
                if piece:
                    chunks.append(Document(page_content=piece, metadata=dict(metadata)))
                if end >= len(content):
                    break
                start += step

        return chunks

    def _rebuild_or_fallback_chunks(self):
        chunks = self._load_all_pdf_chunks()
        if not chunks:
            print("Warning: no PDF content found in 'pdfs' folder; RAG will run without retrieval.")
            self.db = None
            self.chunk_store = []
            return

        if self.faiss_cls is None or self.embeddings is None:
            self.db = None
            self.chunk_store = chunks
            return

        try:
            self.db = self.faiss_cls.from_documents(chunks, self.embeddings)
            self.db.save_local(self.faiss_index_path)
            self.chunk_store = []
        except Exception as exc:
            print(
                "Warning: failed to build FAISS index; using lexical PDF retrieval fallback: "
                f"{exc}"
            )
            self.db = None
            self.chunk_store = chunks

    def _load_all_pdf_chunks(self):
        docs = []
        for file in os.listdir(self.pdf_folder):
            if file.lower().endswith(".pdf"):
                try:
                    docs.extend(self._load_pdf_docs(os.path.join(self.pdf_folder, file)))
                except Exception as exc:
                    print(f"Warning: failed to load PDF '{file}': {exc}")
                    continue

        if not docs:
            return []

        return self._split_documents(docs)

    @staticmethod
    def _tokenize(text: str):
        return re.findall(r"[a-z0-9]+", (text or "").lower())

    def _lexical_similarity_search(self, query: str, k: int = 5):
        if not self.chunk_store:
            return []

        query_text = (query or "").lower()
        query_tokens = self._tokenize(query_text)
        query_counts = Counter(query_tokens)
        scored = []

        for idx, doc in enumerate(self.chunk_store):
            content = getattr(doc, "page_content", "") or ""
            content_text = content.lower()
            content_tokens = self._tokenize(content_text)
            if not content_tokens:
                continue

            content_counts = Counter(content_tokens)
            overlap = sum(min(content_counts[token], freq) for token, freq in query_counts.items())
            unique_overlap = len(set(query_tokens) & set(content_tokens))
            phrase_bonus = 3 if query_text and query_text in content_text else 0
            score = overlap + (0.6 * unique_overlap) + phrase_bonus
            scored.append((score, idx, doc))

        if not scored:
            return []

        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        if scored[0][0] <= 0:
            return [doc for _, _, doc in scored[:k]]
        return [doc for score, _, doc in scored[:k] if score > 0]

    def add_uploaded_pdfs(self, uploaded_files):
        if not uploaded_files:
            return {"added": [], "skipped": [], "failed": []}

        added_files = []
        skipped_files = []
        failed_files = []
        loaded_docs = []

        for uploaded in uploaded_files:
            filename = os.path.basename(getattr(uploaded, "name", "") or "")
            if not filename or not filename.lower().endswith(".pdf"):
                failed_files.append({"name": filename or "unknown", "error": "Not a PDF file"})
                continue

            dest_path = os.path.join(self.pdf_folder, filename)
            payload = bytes(uploaded.getvalue())

            if os.path.exists(dest_path):
                try:
                    with open(dest_path, "rb") as existing:
                        if existing.read() == payload:
                            skipped_files.append(filename)
                            continue
                except Exception:
                    pass

            try:
                with open(dest_path, "wb") as out_file:
                    out_file.write(payload)
            except Exception as write_error:
                failed_files.append({"name": filename, "error": str(write_error)})
                continue

            try:
                loaded_docs.extend(self._load_pdf_docs(dest_path))
                added_files.append(filename)
            except Exception as parse_error:
                failed_files.append({"name": filename, "error": str(parse_error)})
                continue

        if loaded_docs:
            chunks = self._split_documents(loaded_docs)
            if chunks:
                if self.embeddings is None or self.faiss_cls is None:
                    self.chunk_store.extend(chunks)
                elif self.db is None:
                    try:
                        self.db = self.faiss_cls.from_documents(chunks, self.embeddings)
                    except Exception as exc:
                        print(
                            "Warning: failed to create FAISS index; using lexical PDF retrieval fallback: "
                            f"{exc}"
                        )
                        self.db = None
                        self.chunk_store.extend(chunks)
                else:
                    try:
                        self.db.add_documents(chunks)
                    except Exception as exc:
                        print(
                            "Warning: failed to append documents to FAISS index; using lexical PDF retrieval fallback: "
                            f"{exc}"
                        )
                        self.db = None
                        self.chunk_store.extend(chunks)

                if self.db is not None:
                    self.db.save_local(self.faiss_index_path)

        return {"added": added_files, "skipped": skipped_files, "failed": failed_files}

    @staticmethod
    def _extract_json_payload(text):
        candidate = (text or "").strip()
        if not candidate:
            raise ValueError("Empty response")

        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\\s*", "", candidate, flags=re.IGNORECASE)
            candidate = re.sub(r"\\s*```$", "", candidate)

        try:
            return json.loads(candidate)
        except Exception:
            pass

        decoder = json.JSONDecoder()
        for i, ch in enumerate(candidate):
            if ch == "{":
                try:
                    obj, _ = decoder.raw_decode(candidate[i:])
                    return obj
                except Exception:
                    continue

        raise ValueError("Could not parse JSON payload")

    @staticmethod
    def _load_pdf_docs(path: str):
        pypdf_error = None
        try:
            from pypdf import PdfReader

            reader = PdfReader(path)
            docs = []
            for index, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    docs.append(
                        Document(
                            page_content=text,
                            metadata={"source": path, "page": index},
                        )
                    )
            return docs
        except Exception as exc:
            pypdf_error = exc

        try:
            import fitz

            docs = []
            with fitz.open(path) as pdf_doc:
                for index, page in enumerate(pdf_doc, start=1):
                    text = (page.get_text("text") or "").strip()
                    if text:
                        docs.append(
                            Document(
                                page_content=text,
                                metadata={"source": path, "page": index},
                            )
                        )
            return docs
        except Exception as fallback_exc:
            raise ValueError(
                f"PDF parsing failed for '{os.path.basename(path)}'. "
                f"pypdf error: {pypdf_error}. PyMuPDF error: {fallback_exc}"
            ) from fallback_exc

    @staticmethod
    def _normalize_exam_payload(payload, topic, difficulty):
        mcqs_in = payload.get("mcqs", []) if isinstance(payload, dict) else []
        essays_in = payload.get("essays", []) if isinstance(payload, dict) else []

        mcqs = []
        for i, q in enumerate(mcqs_in, start=1):
            if not isinstance(q, dict):
                continue
            question = str(q.get("question", "")).strip()
            options = [str(opt).strip() for opt in q.get("options", []) if str(opt).strip()]
            if not question or len(options) < 2:
                continue

            idx = q.get("correct_option_index", 0)
            try:
                idx = int(idx)
            except Exception:
                idx = 0
            idx = max(0, min(idx, len(options) - 1))

            mcqs.append(
                {
                    "id": str(q.get("id", f"MCQ-{i}")),
                    "question": question,
                    "options": options,
                    "correct_option_index": idx,
                    "explanation": str(q.get("explanation", "")).strip(),
                }
            )

        essays = []
        for i, q in enumerate(essays_in, start=1):
            if not isinstance(q, dict):
                continue
            question = str(q.get("question", "")).strip()
            if not question:
                continue
            essays.append(
                {
                    "id": str(q.get("id", f"ESSAY-{i}")),
                    "question": question,
                    "model_answer": str(q.get("model_answer", "")).strip(),
                }
            )

        return {
            "topic": str(payload.get("topic", topic)).strip() if isinstance(payload, dict) else topic,
            "difficulty": str(payload.get("difficulty", difficulty)).strip()
            if isinstance(payload, dict)
            else difficulty,
            "mcqs": mcqs,
            "essays": essays,
        }

    def query(
        self,
        topic,
        mcq_count=3,
        essay_count=2,
        difficulty="Beginner",
        mode="General",
        pdf_name: str | None = None,
    ):
        if pdf_name:
            pdf_path = os.path.join(self.pdf_folder, pdf_name)
            if not os.path.isfile(pdf_path):
                raise FileNotFoundError(f"PDF not found: {pdf_name}")
            try:
                docs = self._load_pdf_docs(pdf_path)
            except Exception as exc:
                raise ValueError(f"Failed to read PDF '{pdf_name}': {exc}")
            if docs:
                chunks = self._split_documents(docs)
                context_text = "\n\n".join([d.page_content for d in chunks])
            else:
                context_text = ""
            sources = {pdf_name}
        else:
            if self.db is not None:
                docs = self.db.similarity_search(topic, k=5)
                context_text = "\n\n".join([d.page_content for d in docs])
                sources = {os.path.basename(d.metadata.get("source", "Unknown")) for d in docs}
            elif self.chunk_store:
                docs = self._lexical_similarity_search(topic, k=5)
                context_text = "\n\n".join([d.page_content for d in docs])
                sources = {os.path.basename(d.metadata.get("source", "Unknown")) for d in docs}
            else:
                docs = []
                context_text = ""
                sources = set()

        if mode == "Instructor Mode":
            system_msg = "You generate university exams in strict JSON only."
            user_msg = f"""
Create a {difficulty} level exam on topic: {topic}
Use this context:\n{context_text[:5000]}

Return ONLY JSON with this schema:
{{
  "topic": "{topic}",
  "difficulty": "{difficulty}",
  "mcqs": [
    {{
      "id": "MCQ-1",
      "question": "...",
      "options": ["...", "...", "...", "..."],
      "correct_option_index": 0,
      "explanation": "..."
    }}
  ],
  "essays": [
    {{
      "id": "ESSAY-1",
      "question": "...",
      "model_answer": "..."
    }}
  ]
}}

Requirements:
- Generate exactly {mcq_count} MCQs.
- Generate exactly {essay_count} essay questions.
- Each MCQ must have exactly 4 options.
- Do not include markdown, prose, or code fences.
"""
        else:
            system_msg = "You are a helpful academic assistant."
            user_msg = f"Use the context to answer: {topic}\\n\\nContext: {context_text[:3000]}"

        try:
            chat_completion = GROQ_CLIENT.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                model=CURRENT_MODEL,
                temperature=0.2 if mode == "Instructor Mode" else 0.4,
            )
            raw = chat_completion.choices[0].message.content
            if mode == "Instructor Mode":
                payload = self._extract_json_payload(raw)
                exam = self._normalize_exam_payload(payload, topic, difficulty)
                return json.dumps(exam, ensure_ascii=True), sources
            return raw, sources
        except Exception as e:
            return f"Error calling AI: {str(e)}", sources

    def grade_submission(self, exam_content, student_answer):
        system_msg = "You are a strict university grader."
        user_msg = f"""
Evaluate the student submission against the exam key.

EXAM CONTENT:
{exam_content}

STUDENT SUBMISSION:
{student_answer}

Rules:
- If JSON is provided, use correct_option_index and model_answer fields.
- Score out of 100.

STRICT OUTPUT FORMAT:
Line 1: Score: [Numerical value]/100
Following lines: concise feedback with strengths, mistakes, and improvements.
"""

        try:
            chat_completion = GROQ_CLIENT.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                model=CURRENT_MODEL,
                temperature=0.2,
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            return f"Grading Error: {str(e)}"
