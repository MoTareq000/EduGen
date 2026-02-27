from typing import Any

from app.services.common_service import parse_score_from_text


def grade_structured_submission(
    exam_data: dict[str, Any], student_data: dict[str, Any], essay_feedback: str
):
    mcqs = exam_data.get("mcqs", []) if isinstance(exam_data, dict) else []
    essays = exam_data.get("essays", []) if isinstance(exam_data, dict) else []
    by_id: dict[str, dict[str, Any]] = {}

    for ans in student_data.get("mcq_answers", []) if isinstance(student_data, dict) else []:
        qid = str(ans.get("id", "")).strip()
        if qid:
            by_id[qid] = ans

    mcq_total = sum(max(1, int(q.get("weight", 1))) for q in mcqs if isinstance(q, dict))
    essay_total = sum(max(1, int(q.get("weight", 1))) for q in essays if isinstance(q, dict))

    mcq_scored = 0.0
    details = []
    for q in mcqs:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id", "")).strip()
        weight = max(1, int(q.get("weight", 1)))
        expected = int(q.get("correct_option_index", 0))
        selected = -1
        if qid in by_id:
            try:
                selected = int(by_id[qid].get("selected_option_index", -1))
            except Exception:
                selected = -1
        correct = selected == expected
        if correct:
            mcq_scored += weight
        details.append(
            {
                "id": qid,
                "weight": weight,
                "selected": selected,
                "expected": expected,
                "correct": correct,
            }
        )

    essay_percent = parse_score_from_text(essay_feedback)
    essay_scored = (essay_total * essay_percent) / 100.0

    total = max(1.0, mcq_total + essay_total)
    final_score = int(round(((mcq_scored + essay_scored) / total) * 100.0))
    final_score = max(0, min(100, final_score))

    return {
        "final_score": final_score,
        "mcq": {"scored_weight": mcq_scored, "total_weight": mcq_total, "details": details},
        "essay": {
            "ai_percent": essay_percent,
            "scored_weight": essay_scored,
            "total_weight": essay_total,
        },
    }
