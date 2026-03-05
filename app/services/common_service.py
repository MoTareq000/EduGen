import json
import re


def parse_json_blob(text: str | None):
    if not text:
        return None

    candidate = str(text).strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)

    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def parse_score_from_text(text: str | None) -> int:
    try:
        score_match = re.search(r"(\d+)/100", text or "") or re.search(
            r"Score:\s*(\d+)", text or "", re.I
        )
        score = int(score_match.group(1)) if score_match else 0
    except Exception:
        score = 0
    return max(0, min(100, score))
