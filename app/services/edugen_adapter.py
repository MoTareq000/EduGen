from typing import Any
import json
import re


def _parse_json_any(payload: Any):
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    try:
        candidate = str(payload).strip()
    except Exception:
        return None
    if not candidate:
        return None
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _index_to_letter(index: int) -> str:
    return chr(65 + index)


def _coerce_index(value: Any, options_len: int | None = None) -> int | None:
    try:
        idx = int(value)
    except Exception:
        return None
    if options_len is None or options_len <= 0:
        return idx if 0 <= idx < 26 else None
    if 0 <= idx < options_len:
        return idx
    if 1 <= idx <= options_len:
        return idx - 1
    return None


def _is_true_value(text: str) -> bool | None:
    value = text.strip().lower()
    if value in ("true", "t", "yes", "y"):
        return True
    if value in ("false", "f", "no", "n"):
        return False
    return None


def _normalize_mcq_correct_answer(question: dict[str, Any], options: list[str]) -> str:
    answer = question.get("answer", "")
    if isinstance(answer, bool):
        return "A" if answer else "B"
    if isinstance(answer, (int, float)):
        idx = _coerce_index(answer, len(options))
        return _index_to_letter(idx) if idx is not None else str(answer)
    if isinstance(answer, str):
        value = answer.strip()
        if value:
            tf_value = _is_true_value(value)
            if tf_value is not None and options:
                return "A" if tf_value else "B"
            if len(value) == 1 and value.upper().isalpha():
                return value.upper()
            for idx, opt in enumerate(options):
                if value.lower() == str(opt).strip().lower():
                    return _index_to_letter(idx)
            idx = _coerce_index(value, len(options))
            return _index_to_letter(idx) if idx is not None else value

    idx = _coerce_index(question.get("correct_option_index"), len(options))
    if idx is not None:
        return _index_to_letter(idx)
    return ""


def _normalize_mcq_answer(raw_answer: Any, options: list[str]) -> str:
    if raw_answer is None:
        return ""
    if isinstance(raw_answer, bool):
        return "A" if raw_answer else "B"
    if isinstance(raw_answer, (int, float)):
        idx = _coerce_index(raw_answer, len(options))
        return _index_to_letter(idx) if idx is not None else str(raw_answer)
    value = str(raw_answer).strip()
    if not value:
        return ""
    tf_value = _is_true_value(value)
    if tf_value is not None and options:
        return "A" if tf_value else "B"
    if len(value) == 1 and value.upper().isalpha():
        return value.upper()
    if value.isdigit():
        idx = _coerce_index(value, len(options))
        return _index_to_letter(idx) if idx is not None else value
    for idx, opt in enumerate(options):
        if value.lower() == str(opt).strip().lower():
            return _index_to_letter(idx)
    return value


def _extract_answer_value(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    for key in (
        "answer",
        "selected_option_index",
        "selected_option",
        "response",
        "value",
        "text",
    ):
        if key in item:
            return item[key]
    return item


def _build_answer_map(student_data: Any) -> dict[str, Any]:
    answer_map: dict[str, Any] = {}
    if not isinstance(student_data, dict):
        return answer_map

    container_keys = {
        "mcq_answers",
        "essay_answers",
        "tf_answers",
        "answers",
        "responses",
        "mcqs",
        "essays",
        "tfs",
    }

    for key in ("answers", "responses"):
        payload = student_data.get(key)
        if isinstance(payload, dict):
            for k, v in payload.items():
                answer_map[str(k)] = v
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    qid = str(item.get("id") or item.get("question_id") or item.get("qid") or "").strip()
                    if qid:
                        answer_map[qid] = _extract_answer_value(item)

    for key in ("mcq_answers", "essay_answers", "tf_answers", "mcqs", "essays", "tfs"):
        payload = student_data.get(key)
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    qid = str(item.get("id") or item.get("question_id") or item.get("qid") or "").strip()
                    if qid:
                        answer_map[qid] = _extract_answer_value(item)

    for k, v in student_data.items():
        if k in container_keys:
            continue
        if isinstance(v, (dict, list)):
            continue
        answer_map[str(k)] = v

    return answer_map


def _question_id_candidates(question: dict[str, Any], index: int) -> list[str]:
    candidates = []
    for key in ("id", "question_id", "qid"):
        value = question.get(key)
        if value:
            candidates.append(str(value))
    candidates.append(str(index + 1))
    candidates.append(f"Q{index + 1}")
    return candidates


def build_edugen_questions(exam_content: Any, exam_questions: Any | None = None) -> list[dict[str, Any]] | None:
    questions_raw = None
    questions_source = _parse_json_any(exam_questions) if exam_questions is not None else None

    if isinstance(questions_source, dict) and isinstance(questions_source.get("questions"), list):
        questions_raw = questions_source.get("questions")
    elif isinstance(questions_source, list):
        questions_raw = questions_source

    if questions_raw is None:
        exam_data = _parse_json_any(exam_content)
        if isinstance(exam_data, dict) and isinstance(exam_data.get("questions"), list):
            questions_raw = exam_data.get("questions")
        elif isinstance(exam_data, dict):
            questions_raw = []
            mcq_candidates = exam_data.get("mcqs")
            if mcq_candidates is None:
                mcq_candidates = exam_data.get("mcq")
            if not isinstance(mcq_candidates, list):
                mcq_candidates = []
            for q in mcq_candidates:
                if not isinstance(q, dict):
                    continue
                options = [str(opt).strip() for opt in q.get("options", []) if str(opt).strip()]
                answer_letter = _normalize_mcq_correct_answer(q, options)
                questions_raw.append(
                    {
                        "id": q.get("id"),
                        "type": "mcq",
                        "question": q.get("question", ""),
                        "options": options,
                        "answer": answer_letter,
                    }
                )

            tf_candidates = exam_data.get("tfs")
            if tf_candidates is None:
                tf_candidates = exam_data.get("tf")
            if tf_candidates is None:
                tf_candidates = exam_data.get("true_false")
            if tf_candidates is None:
                tf_candidates = exam_data.get("true_false_questions")
            if isinstance(tf_candidates, list):
                for q in tf_candidates:
                    if not isinstance(q, dict):
                        continue
                    options = ["True", "False"]
                    answer_letter = _normalize_mcq_correct_answer(q, options)
                    questions_raw.append(
                        {
                            "id": q.get("id"),
                            "type": "mcq",
                            "original_type": "tf",
                            "question": q.get("question", ""),
                            "options": options,
                            "answer": answer_letter,
                        }
                    )

            essay_candidates = exam_data.get("essays")
            if essay_candidates is None:
                essay_candidates = exam_data.get("essay")
            if not isinstance(essay_candidates, list):
                essay_candidates = []
            for q in essay_candidates:
                if not isinstance(q, dict):
                    continue
                questions_raw.append(
                    {
                        "id": q.get("id"),
                        "type": "essay",
                        "question": q.get("question", ""),
                        "answer": q.get("model_answer") or q.get("answer") or "",
                    }
                )

    if not isinstance(questions_raw, list) or not questions_raw:
        return None

    normalized: list[dict[str, Any]] = []
    for q in questions_raw:
        if not isinstance(q, dict):
            continue
        q_type = str(q.get("type", "mcq")).strip().lower()
        question_text = q.get("question", "")
        if not question_text:
            continue

        if q_type in ("tf", "true_false", "true/false"):
            options = ["True", "False"]
            answer_letter = _normalize_mcq_correct_answer(q, options)
            normalized.append(
                {
                    "id": q.get("id"),
                    "type": "mcq",
                    "original_type": "tf",
                    "question": question_text,
                    "options": options,
                    "answer": answer_letter,
                }
            )
        elif q_type == "essay":
            normalized.append(
                {
                    "id": q.get("id"),
                    "type": "essay",
                    "question": question_text,
                    "answer": q.get("model_answer") or q.get("answer") or "",
                }
            )
        else:
            options = [str(opt).strip() for opt in q.get("options", []) if str(opt).strip()]
            answer_letter = _normalize_mcq_correct_answer(q, options)
            normalized.append(
                {
                    "id": q.get("id"),
                    "type": "mcq",
                    "question": question_text,
                    "options": options,
                    "answer": answer_letter,
                }
            )

    return normalized or None


def build_edugen_answers(student_answers: Any, questions: list[dict[str, Any]]) -> list[str]:
    student_data = _parse_json_any(student_answers)
    ordered: list[Any] | None = None
    answer_map: dict[str, Any] = {}
    section_index = {"mcq": -1, "essay": -1, "tf": -1}

    if isinstance(student_data, list):
        if all(not isinstance(item, dict) for item in student_data):
            ordered = student_data
        else:
            for item in student_data:
                if isinstance(item, dict):
                    qid = str(item.get("id") or item.get("question_id") or item.get("qid") or "").strip()
                    if qid:
                        answer_map[qid] = _extract_answer_value(item)
    elif isinstance(student_data, dict):
        answer_map = _build_answer_map(student_data)

    normalized_answers: list[str] = []
    for index, question in enumerate(questions):
        raw_answer = None
        original_type = str(question.get("original_type") or "").strip().lower()
        q_type = str(question.get("type", "")).strip().lower()
        section = "tf" if original_type == "tf" else (q_type if q_type else "mcq")
        if section not in section_index:
            section = "mcq"
        section_index[section] += 1

        if ordered is not None and index < len(ordered):
            raw_answer = ordered[index]
        if raw_answer is None:
            pref_key = f"{section}_{section_index[section]}"
            if pref_key in answer_map:
                raw_answer = answer_map[pref_key]
            else:
                for candidate in _question_id_candidates(question, index):
                    if candidate in answer_map:
                        raw_answer = answer_map[candidate]
                        break

        if question.get("type") == "essay":
            normalized_answers.append(str(raw_answer).strip() if raw_answer is not None else "")
        else:
            options = question.get("options", [])
            normalized_answers.append(_normalize_mcq_answer(raw_answer, options))

    return normalized_answers
