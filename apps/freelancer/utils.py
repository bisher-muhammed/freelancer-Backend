# utils.py (updated)
import os
import re
import json
import time
import logging
import fitz  # PyMuPDF
from docx import Document
from dotenv import load_dotenv
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# AI client
import google.generativeai as genai

load_dotenv()
logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API Key not found")

genai.configure(api_key=GOOGLE_API_KEY)

# -------------------------------
# Config
# -------------------------------
AI_TIMEOUT_SECONDS = 12           # time to wait for a single AI request
AI_RETRIES = 2                    # number of retries on failure (total attempts = AI_RETRIES + 1)
AI_RETRY_BACKOFF = 1.5            # multiplier for exponential backoff
MAX_BIO_LENGTH = 300
DEFAULT_SKILLS = {
    "Python": ["python"],
    "Django": ["django"],
    "React": ["react", "reactjs", "react.js"],
    "Tailwind": ["tailwind", "tailwindcss"],
    "Redux": ["redux"],
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "Docker": ["docker"],
    "JavaScript": ["javascript", "js"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Node.js": ["node", "nodejs", "node.js"],
    "MongoDB": ["mongodb", "mongo"],
    "Git": ["git"],
    "TypeScript": ["typescript", "ts"],
    "Next.js": ["next", "nextjs", "next.js"],
    "Vue": ["vue", "vuejs", "vue.js"],
    "Angular": ["angular"],
    "Express": ["express", "expressjs"],
    "Flask": ["flask"],
    "SQL": ["sql", "mysql"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "Kubernetes": ["kubernetes", "k8s"],
    "REST API": ["rest", "rest api", "restful"],
    "GraphQL": ["graphql"],
    "Photoshop": ["photoshop", "ps"],
    "Figma": ["figma"],
    "Illustrator": ["illustrator", "ai"],
}

# -------------------------------
# Helpers
# -------------------------------
def sanitize_text(text: str) -> str:
    """Remove control characters, excessive whitespace, and code fences/markdown."""
    if not text:
        return ""
    text = text.replace("\r", "\n")
    # Remove triple-backtick code blocks entirely
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove markdown bold/italic markers
    text = re.sub(r"\*\*|\*|__|~~|`", "", text)
    # Normalize whitespace
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Trim leading/trailing
    return text.strip()

def title_case_safe(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    # Keep abbreviations like "SQL", "AWS" uppercase if present in DEFAULT_SKILLS keys
    for key in DEFAULT_SKILLS:
        if s.lower() == key.lower():
            return key
    # Otherwise, use a reasonable title-casing
    return " ".join([part.capitalize() for part in re.split(r"[\s\-_/]+", s)])

# -------------------------------
# File text extraction
# -------------------------------
def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    try:
        if ext == ".pdf":
            with fitz.open(file_path) as doc:
                for page in doc:
                    # get_text("text") is best-effort; sanitize later
                    text += page.get_text("text") + "\n"
        elif ext in [".docx", ".doc"]:
            doc = Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        else:
            raise ValueError("Unsupported file type")
        return sanitize_text(text).strip()
    except Exception as e:
        logger.exception("Error extracting text from file: %s", e)
        raise ValueError(f"Error extracting text: {e}")

# -------------------------------
# AI call (threaded + timeout + retries)
# -------------------------------
def _call_ai_sync(prompt: str) -> str:
    """Synchronous call to Gemini. Kept small to run in thread."""
    model = genai.GenerativeModel("gemini-2.0-flash-exp")
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=2000,
            temperature=0.3
        )
    )
    return response.text or ""

def analyze_freelancer_profile(document_text: str) -> str:
    """
    Resilient wrapper around AI call:
    - Runs the synchronous client in a ThreadPoolExecutor
    - Enforces a per-call timeout
    - Performs retries with exponential backoff
    - Returns sanitized text (or empty string on total failure)
    """
    if not document_text:
        return ""

    prompt = _build_prompt(document_text)

    attempt = 0
    backoff = 1.0
    while attempt <= AI_RETRIES:
        attempt += 1
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_call_ai_sync, prompt)
                ai_raw = future.result(timeout=AI_TIMEOUT_SECONDS)
            ai_raw = sanitize_text(ai_raw)
            # remove any leading/trailing noise
            ai_raw = re.sub(r"^[\s\n]+", "", ai_raw)
            ai_raw = re.sub(r"[\s\n]+$", "", ai_raw)
            logger.debug("AI raw output (len=%d)", len(ai_raw))
            return ai_raw
        except Exception as e:
            logger.warning("AI attempt %s failed: %s", attempt, e, exc_info=False)
            if attempt > AI_RETRIES:
                logger.error("AI failed after %s attempts. Falling back to keyword extraction.", AI_RETRIES + 1)
                return ""
            time.sleep(backoff)
            backoff *= AI_RETRY_BACKOFF

    return ""  # should not reach here

def _build_prompt(document_text: str) -> str:
    """Build the AI prompt. Kept separate for clarity and future adjustments."""
    prompt = f"""
You are an expert resume parser. Extract structured data from the resume text provided.

CRITICAL INSTRUCTIONS:
- Output MUST be plain text, not JSON, following the exact headings shown below.
- Do NOT include commentary, explanations, or extra sections.
- If a field is not present, leave it empty but keep the heading.
- Try to detect job positions/roles (e.g., Frontend Developer, Backend Engineer) as a separate line.
- For skills, output a comma-separated list. If you can provide categories for skills, list categories in the same order separated by commas.
- Keep answers concise and machine-parseable.

OUTPUT FORMAT (follow exactly):

Bio: <one or two short sentences>

Positions: <role1, role2, ...>

Skills: <skill1, skill2, skill3>

Skill Categories: <cat1, cat2, cat3>

Education:
- Degree, Institution, Year
- Degree, Institution, Year

Experience:
- Company, Role, Duration, Description
- Company, Role, Duration, Description

NOW PARSE THIS RESUME (do NOT add anything else):

{document_text}

Remember: Output MUST start with "Bio:" on the first line.
"""
    return prompt

# -------------------------------
# Fallback skill extraction (normalized schema)
# -------------------------------
def extract_skills_fallback(text: str) -> List[Dict[str, Optional[str]]]:
    """Return a list of {name, category|null} using DEFAULT_SKILLS keyword matching."""
    if not text:
        return []
    lower = text.lower()
    detected = []
    for canonical, aliases in DEFAULT_SKILLS.items():
        if any(alias in lower for alias in aliases):
            detected.append({"name": canonical, "category": None})
    # de-duplicate preserving order
    seen = set()
    unique = []
    for s in detected:
        if s["name"] not in seen:
            seen.add(s["name"])
            unique.append(s)
    return unique

# -------------------------------
# Parse AI response to normalized JSON
# -------------------------------
def parse_ai_text_to_json(ai_text: str, original_text: str) -> dict:
    """
    Parse sanitized AI response into normalized JSON:
    - Always returns skills as list of {"name": str, "category": Optional[str]}
    - Does not modify DB; leaves category=None when unknown
    - Applies safe fallbacks
    """
    skills: List[Dict[str, Optional[str]]] = []
    education = []
    experience = []
    positions: List[str] = []
    bio = ""

    ai_text = sanitize_text(ai_text or "")

    # --- BIO ---
    bio_match = re.search(r"^Bio:\s*(.+?)(?=\nPositions:|\nSkills:|\nSkill Categories:|\nEducation:|\nExperience:|$)", ai_text, re.IGNORECASE | re.DOTALL)
    if bio_match:
        bio = " ".join(bio_match.group(1).strip().split())
    else:
        # fallback to first 200-300 chars of original text
        bio = " ".join((original_text or "").split())[:MAX_BIO_LENGTH]
    bio = bio[:MAX_BIO_LENGTH]

    # --- POSITIONS ---
    pos_match = re.search(r"Positions:\s*(.+?)(?=\nSkills:|\nSkill Categories:|\nEducation:|\nExperience:|$)", ai_text, re.IGNORECASE | re.DOTALL)
    if pos_match:
        pos_text = pos_match.group(1).strip()
        # split by commas
        positions = [p.strip() for p in re.split(r",\s*", pos_text) if p.strip()]
        positions = [title_case_safe(p) for p in positions if p]

    # --- SKILLS and CATEGORIES ---
    skills_match = re.search(r"Skills:\s*(.+?)(?=\nSkill Categories:|\nEducation:|\nExperience:|$)", ai_text, re.IGNORECASE | re.DOTALL)
    categories_match = re.search(r"Skill Categories:\s*(.+?)(?=\nEducation:|\nExperience:|$)", ai_text, re.IGNORECASE | re.DOTALL)

    raw_skills = []
    raw_categories = []

    if skills_match:
        skills_text = skills_match.group(1).strip()
        # Split by commas, semicolons or vertical bar
        raw_skills = [s.strip() for s in re.split(r"[,;|]\s*", skills_text) if s.strip()]

    if categories_match:
        cats_text = categories_match.group(1).strip()
        raw_categories = [c.strip() for c in re.split(r"[,;|]\s*", cats_text) if c.strip()]

    # Attach categories index-wise where possible. If category missing, set None.
    for i, s in enumerate(raw_skills):
        name = title_case_safe(s)
        cat = title_case_safe(raw_categories[i]) if i < len(raw_categories) else None
        skills.append({"name": name, "category": cat})

    # If AI didn't provide skills, use fallback keyword extractor (keeps schema)
    if not skills:
        logger.info("AI did not return skills -> using fallback keyword extractor")
        skills = extract_skills_fallback(original_text)

    # Deduplicate skills by name (keep first)
    seen = set()
    deduped = []
    for s in skills:
        nm = (s.get("name") or "").strip()
        if not nm:
            continue
        if nm.lower() not in seen:
            seen.add(nm.lower())
            # normalize category to None if falsy
            cat = s.get("category")
            cat = title_case_safe(cat) if cat else None
            deduped.append({"name": nm, "category": cat})
    skills = deduped

    # --- EDUCATION ---
    edu_block = re.search(r"Education:\s*\n(.*?)(?=\n\n|\nExperience:|\Z)", ai_text, re.IGNORECASE | re.DOTALL)
    if edu_block:
        for line in re.findall(r"-\s*(.+)", edu_block.group(1)):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                degree = parts[0]
                inst = parts[1]
                year = re.search(r"(\d{4})", parts[2])  # extract year if present
                year = year.group(1) if year else parts[2]
                education.append({"degree": degree, "institution": inst, "year": year})
            else:
                # best-effort parse single-line entries
                education.append({"degree": parts[0] if parts else "", "institution": parts[1] if len(parts) > 1 else "", "year": (re.search(r"(\d{4})", parts[-1]).group(1) if parts and re.search(r"(\d{4})", parts[-1]) else "")})

    # --- EXPERIENCE ---
    exp_block = re.search(r"Experience:\s*\n(.*?)(?=\n\n|\Z)", ai_text, re.IGNORECASE | re.DOTALL)
    if exp_block:
        for line in re.findall(r"-\s*(.+)", exp_block.group(1)):
            parts = [p.strip() for p in line.split(",")]
            # company, role, duration, description
            experience.append({
                "company": parts[0] if len(parts) > 0 else "",
                "role": parts[1] if len(parts) > 1 else "",
                "duration": parts[2] if len(parts) > 2 else "",
                "description": parts[3] if len(parts) > 3 else ""
            })

    # Final safety guarantees
    if not isinstance(skills, list):
        skills = []
    if not isinstance(education, list):
        education = []
    if not isinstance(experience, list):
        experience = []
    if positions and not isinstance(positions, list):
        positions = []

    return {
        "bio": bio,
        "positions": positions,
        "skills": skills,
        "education": education,
        "experience": experience
    }

# -------------------------------
# Main pipeline
# -------------------------------
def process_freelancer_document(file_path: str) -> dict:
    """
    Synchronous function used by your views:
    - Extracts text
    - Calls AI with timeout/retries
    - Parses and returns normalized JSON
    - NEVER writes to DB
    """
    text = extract_text(file_path)
    logger.debug("Extracted text length: %d", len(text))

    ai_text = analyze_freelancer_profile(text)
    if not ai_text:
        logger.info("AI returned empty response, using fallback parsing only")

    ai_data = parse_ai_text_to_json(ai_text, text)

    # Remove any extremely long fields for safety
    if "bio" in ai_data and isinstance(ai_data["bio"], str):
        ai_data["bio"] = ai_data["bio"][:MAX_BIO_LENGTH]

    return {
        "message": "Resume processed (AI assisted).",
        "bio": ai_data.get("bio", ""),
        "positions": ai_data.get("positions", []),
        "skills": ai_data.get("skills", []),
        "education": ai_data.get("education", []),
        "experience": ai_data.get("experience", []),
    }


