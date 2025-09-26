import logging
import os
import json
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("classifier.main")

app = FastAPI(title="MediaGenerator Classifier", version="0.1.0")


@app.on_event("startup")
async def on_startup():
    try:
        logger.info("Classifier version: %s", getattr(app, "version", "unknown"))
    except Exception:
        pass
    logger.info("Classifier service started")

@app.get("/health")
async def health():
    return JSONResponse({
        "ok": True,
        "status": "ok",
        "service": "classifier",
        "use_heuristics": settings.USE_HEURISTICS,
        "keywords_count": len(settings.KEYWORDS),
        "types_count": len(settings.TYPE_LIST),
        "topics_count": len(settings.TOPIC_LIST),
        "gemini": bool(settings.GEMINI_API_KEY),
    })

# Added readiness probe to comply with service standards
@app.get("/ready")
async def ready():
    return JSONResponse({
        "ok": True,
        "ready": True,
        "service": "classifier",
    })

# --- Gemini prompt & helpers ---

def _compose_prompt(post_text: str, types: List[str], topics: List[str]) -> str:
    types_json = json.dumps(types, ensure_ascii=False)
    topics_json = json.dumps(topics, ensure_ascii=False)
    lines = [
        "You are a strict classifier of Telegram posts. Inputs:",
        "POST_TEXT — the full post text (string).",
        "TYPE_LIST — array of allowed post types (array of strings).",
        "TOPIC_LIST — array of allowed topics (array of strings).",
        "Goal: return JSON only with this exact shape:",
        "{",
        "  \"type\": \"<one_of_TYPE_LIST>\",",
        "  \"topic\": \"<one_of_TOPIC_LIST>\",",
        "  \"country\": \"<string or null>\",",
        "  \"city\": \"<string or null>\"",
        "}",
        "Classification Rules",
        "Use only values from TYPE_LIST and TOPIC_LIST. Match spelling exactly.",
        "If no value fits, return \"other\".",
        "Choose one primary type and one primary topic.",
        "Regardless of the post language, output values exactly as provided in the lists.",
        "Post Type (guidelines)",
        "advertising: explicit CTA/offers/prices/promo codes/disclaimers (#ad, sponsor).",
        "sponsored: partnership/“in collaboration with” disclosures without explicit selling.",
        "announcement: upcoming event/publication/release with date/time.",
        "sales: pricing/purchase terms/product or service offer without explicit ad tag.",
        "poll: question with options/voting/survey.",
        "digest: curated roundup of several items/links over a period.",
        "news: new event/facts with sources.",
        "event: description of a (past or ongoing) event/activity (online/offline).",
        "fact: single verifiable fact/number/statistic.",
        "results: outcomes/summary of a completed period/event.",
        "expert opinion: stance/commentary by a specialist.",
        "analysis: causes/effects/trends, often with data.",
        "story: narrative/case/first-person account/retrospective.",
        "other: anything not covered above.",
        "If multiple types apply, use this priority:",
        "advertising > sponsored > sales > announcement > digest > news > event > fact > results > analysis > expert opinion > story > other.",
        "Topic (hints)",
        "economics / finance / business and entrepreneurship: macro/markets/inflation/taxes/banking/startups/trade.",
        "politics: government/elections/laws/sanctions/public policy.",
        "Technology and Science: AI/software/hardware/research/patents/space.",
        "Culture and Arts: film/music/literature/exhibitions.",
        "Health and Sports: medicine/prevention/competitions/teams.",
        "Society and History: education/demography/social issues/historical content.",
        "Automotive and Transport: auto industry/logistics/traffic rules/public transport.",
        "Real Estate and Construction: development/mortgages/repairs/materials.",
        "If unclear — return \"other\".",
        "Geotagging (country/city)",
        "Infer country and, if possible, city from explicit mentions (text/hashtags/user tags/addresses/currency/TLD/phone codes/toponyms/language).",
        "Do not guess: if uncertain, return null.",
        "Use common Russian names for locations (e.g., \"Казахстан\", \"Алматы\") or local endonyms if clearly indicated.",
        "Output",
        "Return only a single valid JSON object, no explanations, no code, no Markdown, no extra fields.",
        "",
        f"POST_TEXT: {post_text}",
        f"TYPE_LIST: {types_json}",
        f"TOPIC_LIST: {topics_json}",
    ]
    return "\n".join(lines)


def _call_gemini(prompt: str) -> str:
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_MODEL_NAME)
        resp = model.generate_content(prompt)
        text = (getattr(resp, "text", None) or "").strip()
        return text
    except Exception:
        logger.exception("Gemini call failed")
        return ""


def _extract_text_from_post(post: Dict[str, Any]) -> str:
    text = (post.get("text") or "").strip()
    if not text:
        media = post.get("media") or {}
        text = (media.get("caption") or "").strip()
    return text


def _safe_json_parse(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None

@app.post("/api/classifier/classify")
async def classify(payload: Dict[str, Any] = Body(...)):
    # ожидаем полный пост от collector; поддерживаем старую форму {text,title,source}
    post = payload or {}
    post_text = _extract_text_from_post(post)
    source = post.get("source") or post.get("channel_title") or post.get("channel_name") or None

    if not post_text:
        return {
            "ok": True,
            "is_news": False,
            "topics": [],
            "confidence": 0.4,
            "suggested_action": "reject",
            "source": source,
            "classification": {
                "type": "other",
                "topic": "other",
                "country": None,
                "city": None,
            },
        }

    # truncate overly long text
    if len(post_text) > settings.TEXT_TRUNCATE_LIMIT:
        post_text = post_text[: settings.TEXT_TRUNCATE_LIMIT] + "…"

    result_obj: Optional[Dict[str, Any]] = None
    if settings.GEMINI_API_KEY:
        prompt = _compose_prompt(post_text, settings.TYPE_LIST, settings.TOPIC_LIST)
        raw = _call_gemini(prompt)
        result_obj = _safe_json_parse(raw)
        if not result_obj and raw:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                chunk = raw[start:end+1]
                result_obj = _safe_json_parse(chunk)

    if not result_obj:
        lower = post_text.lower()
        score = sum(1 for w in settings.KEYWORDS if w in lower)
        is_news = (score >= 1 and len(post_text.strip()) >= settings.MIN_TEXT_LEN)
        t = "news" if is_news else "other"
        result_obj = {
            "type": t,
            "topic": "other",
            "country": None,
            "city": None,
        }

    typ = str(result_obj.get("type") or "other")
    top = str(result_obj.get("topic") or "other")
    if typ not in settings.TYPE_LIST:
        typ = "other"
    if top not in settings.TOPIC_LIST:
        top = "other"
    country = result_obj.get("country")
    city = result_obj.get("city")
    country = None if country in ("", None) else country
    city = None if city in ("", None) else city

    is_news_final = (typ == "news")
    suggested_action = "approve" if is_news_final else "reject"
    confidence = 0.6 if is_news_final else 0.4

    return {
        "ok": True,
        "is_news": is_news_final,
        "topics": [top] if top != "other" else [],
        "confidence": confidence,
        "suggested_action": suggested_action,
        "source": source,
        "classification": {
            "type": typ,
            "topic": top,
            "country": country,
            "city": city,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)