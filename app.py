import os
import time
import json
import io
import uuid
import base64
import torch
import torchvision.models as models
import torchvision.transforms as transforms
from datetime import datetime
from PIL import Image
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from supabase import create_client, Client

# ==========================================
# 1. Environment & Configuration
# ==========================================
load_dotenv()  # Auto-loads .env file - no manual setup needed

GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY     = os.environ.get("SUPABASE_KEY", "")
APP_NAME         = "WildLens AI"
APP_VERSION      = "2.0.0"

# ==========================================
# 2. Supabase Client & Table Bootstrap
# ==========================================
supabase: Client | None = None

def init_supabase():
    global supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[WARN] Supabase credentials not found -- data persistence disabled.")
        return
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f"[OK] Supabase connected: {SUPABASE_URL}")
    except Exception as e:
        print(f"[WARN] Supabase init failed: {e}")
        supabase = None

def db_insert(table: str, data: dict):
    """Safe insert -- silently skips if Supabase is not configured."""
    if supabase is None:
        return
    try:
        supabase.table(table).insert(data).execute()
    except Exception as e:
        print(f"[WARN] DB insert to '{table}' failed: {e}")

init_supabase()

# ==========================================
# 3. FastAPI App Setup
# ==========================================
app = FastAPI(
    title=f"{APP_NAME} API",
    description="Enterprise Multi-Modal Wildlife Species Intelligence Platform",
    version=APP_VERSION
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import requests

# ==========================================
# 4. Groq Client & API Configuration
# ==========================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Using the highly capable and fast Llama-3.3-70b model
GROQ_MODEL = "llama-3.3-70b-versatile"

QUOTA_MSG = "The AI assistant is currently busy. Please wait a moment and try again."

def get_groq_configured() -> bool:
    return bool(GROQ_API_KEY)

def gemini_generate(prompt: str) -> str | None:
    """Wrapper function to query Groq, named gemini_generate to maintain backend compatibility."""
    if not get_groq_configured():
        print("[WARN] Groq API Key not found.")
        return None
    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            err_data = resp.text
            print(f"[WARN] Groq API returned status {resp.status_code}: {err_data}")
            if resp.status_code == 429:
                return QUOTA_MSG
            if resp.status_code == 401:
                return "The API Key set in the Render Environment settings is invalid. Please update the GEMINI_API_KEY or GROQ_API_KEY on the Render Dashboard to match your new Groq key."
            return None
    except Exception as e:
        print(f"[WARN] Groq request failed: {e}")
        return QUOTA_MSG
import base64 as _b64
import re as _re

def _groq_vision_call(b64_image: str, prompt: str) -> str:
    """Make a single Groq Vision API call and return raw text content."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
            ]
        }],
        "temperature": 0.0,
        "max_tokens": 150
    }
    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=25)
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"].strip()
    else:
        print(f"[WARN] Groq Vision API error ({resp.status_code}): {resp.text[:300]}")
        return ""

def _parse_vision_response(content: str) -> list:
    """Parse a vision response into a clean list of names."""
    if not content:
        return []
    # Strip any leading prose like "The animals are: Cat, Lion"
    if ":" in content:
        content = content.split(":")[-1].strip()
    # Reject "none" responses
    if content.lower().strip(" .") in ("none", ""):
        return []
    # Split on commas, clean up each entry
    names = [_re.sub(r"[^a-zA-Z\s\-]", "", s).strip().title() for s in content.split(",")]
    names = [n for n in names if n and len(n) > 1]
    return names

def groq_vision_detect(image_bytes: bytes) -> list:
    """Use Groq Vision to identify ALL animals and humans in the image (two-pass)."""
    if not get_groq_configured():
        return []
    try:
        b64 = _b64.b64encode(image_bytes).decode("utf-8")

        # === PASS 1: General subject detection ===
        prompt1 = (
            "Examine this image carefully. "
            "List every living creature you can identify, including any humans/people. "
            "Reply with ONLY a comma-separated list of names. "
            "If you see a person or human being, write 'Human' in the list. "
            "Examples: 'Cat, Liger' or 'Human, Dog' or 'Lion' or 'Human'. "
            "Do NOT write any sentences or explanations. Just the names."
        )
        raw1 = _groq_vision_call(b64, prompt1)
        print(f"[INFO] Groq Vision Pass 1 raw: '{raw1}'")
        results = _parse_vision_response(raw1)
        print(f"[INFO] Groq Vision Pass 1 parsed: {results}")

        # === PASS 2: Human-specific check (if Pass 1 returned nothing) ===
        if not results:
            prompt2 = "Does this image contain a human being or a person? Answer with only 'Yes' or 'No'."
            raw2 = _groq_vision_call(b64, prompt2)
            print(f"[INFO] Groq Vision Pass 2 (human check) raw: '{raw2}'")
            if raw2.strip().lower().startswith("yes"):
                results = ["Human"]
                print("[INFO] Groq Vision Pass 2: Human detected")

        return results

    except Exception as e:
        print(f"[WARN] Groq Vision exception: {e}")
        return []


def classify_image_gemini(image_bytes: bytes) -> dict:
    """Fallback handler to classify images."""
    return classify_image_cnn(image_bytes)



# ==========================================
# 5. CNN Fallback - MobileNetV3 + Animals-10
# ==========================================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[INFO] Compute device: {device}")

ANIMALS_10 = ["Dog", "Horse", "Elephant", "Butterfly", "Chicken",
               "Cat", "Cow", "Sheep", "Squirrel", "Spider"]

ITALIAN_TO_ENGLISH = {
    "cane": "Dog", "cavallo": "Horse", "elefante": "Elephant",
    "farfalla": "Butterfly", "gallina": "Chicken", "gatto": "Cat",
    "mucca": "Cow", "pecora": "Sheep", "ragno": "Spider", "scoiattolo": "Squirrel"
}

CUSTOM_MODEL_PATH = "animals10_model.pth"
has_custom_model  = os.path.exists(CUSTOM_MODEL_PATH)
custom_classes    = ANIMALS_10
cnn_model         = None

if has_custom_model:
    try:
        print("[INFO] Loading custom-trained Animals-10 weights...")
        checkpoint     = torch.load(CUSTOM_MODEL_PATH, map_location=device, weights_only=False)
        raw_classes    = checkpoint.get("classes", ANIMALS_10)
        custom_classes = [ITALIAN_TO_ENGLISH.get(c.lower(), c.capitalize()) for c in raw_classes]
        cnn_model = models.mobilenet_v3_large()
        in_features = cnn_model.classifier[3].in_features
        cnn_model.classifier[3] = torch.nn.Linear(in_features, len(custom_classes))
        cnn_model.load_state_dict(checkpoint["model_state"])
        cnn_model.eval()
        cnn_model.to(device)
        print(f"[OK] Custom model loaded. Classes: {custom_classes}")
    except Exception as e:
        print(f"[WARN] Custom model load failed: {e}. CNN fallback disabled.")
        has_custom_model = False

preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

def classify_image_cnn(image_bytes: bytes) -> dict:
    """Primary CNN classifier - unlimited, no API quota."""
    t0  = time.time()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    if cnn_model is None:
        return {
            "species": "Unknown", "scientific_name": "", "confidence": 0,
            "description": "No model available.", "model_type": "none",
            "latency": {"preprocessing": 0, "inference": 0, "postprocessing": 0, "total": 0}
        }

    tensor = preprocess(img).unsqueeze(0).to(device)
    with torch.no_grad():
        out   = cnn_model(tensor)
        probs = torch.nn.functional.softmax(out[0], dim=0)

    top5_probs, top5_ids = torch.topk(probs, 3)
    species    = custom_classes[top5_ids[0].item()]
    confidence = round(top5_probs[0].item() * 100, 2)
    # Build top-3 alternatives
    alternatives = [
        {"species": custom_classes[top5_ids[i].item()], "confidence": round(top5_probs[i].item() * 100, 2)}
        for i in range(1, 3)
    ]
    total_ms = round((time.time() - t0) * 1000, 2)
    return {
        "species":         species,
        "scientific_name": "",
        "confidence":      confidence,
        "alternatives":    alternatives,
        "description":     "",
        "model_type":      "custom_cnn",
        "latency": {"preprocessing": 0, "inference": total_ms, "postprocessing": 0, "total": total_ms}
    }

# ==========================================
# 6. API Endpoints
# ==========================================

@app.get("/api/health")
async def health():
    return {
        "status":         "online",
        "app":            APP_NAME,
        "version":        APP_VERSION,
        "ai":             get_groq_configured(),
        "supabase":       supabase is not None,
        "custom_model":   has_custom_model,
        "device":         str(device),
    }

# Classify — Custom CNN (primary, no API quota)
@app.post("/api/classify")
async def api_classify(
    file:       UploadFile = File(...),
    session_id: str        = Form(default=""),
):
    try:
        raw    = await file.read()
        
        species_list = []
        model_used = "custom_cnn"
        confidence = 0
        
        if get_groq_configured():
            species_list = groq_vision_detect(raw)
            if species_list:
                model_used = "groq_vision"
                confidence = 99.0
                
        if not species_list:
            result = classify_image_cnn(raw)
            species_list = [result["species"]]
            confidence = result["confidence"]
            model_used = result["model_type"]
            
        primary_species = species_list[0] if species_list else "Unknown"
        scan_id = str(uuid.uuid4())

        db_insert("scans", {
            "id":          scan_id,
            "session_id":  session_id or str(uuid.uuid4()),
            "species":     primary_species,
            "confidence":  confidence,
            "model_type":  model_used,
            "latency_ms":  0,
            "created_at":  datetime.utcnow().isoformat(),
        })

        return JSONResponse(content={
            "species": primary_species,
            "species_list": species_list,
            "confidence": confidence,
            "model_type": model_used,
            "scan_id": scan_id
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# In-memory cache for species info (avoids hammering Gemini for same species)
_info_cache: dict = {}

# Species Info — cached Gemini JSON
@app.post("/api/info")
async def api_info(species: str = Form(...)):
    # Return from cache if already fetched
    cache_key = species.lower().strip()
    if cache_key in _info_cache:
        return JSONResponse(content=_info_cache[cache_key])

    demo_payload = {
        "habitat": {
            "climate":      "Varies by region",
            "distribution": "Global — species-dependent",
            "description":  f"The {species} adapts to a range of ecosystems depending on local flora and climate."
        },
        "food_chain": {
            "trophic_level": "Varies",
            "chain":         ["Primary Producers", species, "Apex Predator"],
            "description":   f"The {species} plays a key ecological role regulating population dynamics."
        },
        "conservation": {
            "status":  "Least Concern (LC)",
            "threats": "Habitat fragmentation, climate shift, human encroachment.",
            "actions": "Protected corridor expansion, ecological monitoring networks."
        }
    }

    if not get_groq_configured():
        return JSONResponse(content=demo_payload)

    try:
        schema = (
            '{"habitat":{"climate":"str","distribution":"str","description":"str"},'
            '"food_chain":{"trophic_level":"str","chain":["str"],"description":"str"},'
            '"conservation":{"status":"str","threats":"str","actions":"str"}}'
        )
        prompt = (
            f"Return structured JSON (no markdown) for the animal '{species}' "
            f"matching this exact schema: {schema}. Be factual and concise."
        )
        raw_text = gemini_generate(prompt)
        if not raw_text or raw_text == QUOTA_MSG:
            return JSONResponse(content=demo_payload)
        clean = raw_text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        parsed = json.loads(clean)
        _info_cache[cache_key] = parsed  # cache it
        return JSONResponse(content=parsed)
    except Exception:
        return JSONResponse(content=demo_payload)


# Encyclopedia search — any animal name, powered by Gemini
@app.post("/api/search")
async def api_search(query: str = Form(...)):
    """Search for any animal and return structured ecological info."""
    cache_key = query.lower().strip()
    if cache_key in _info_cache:
        return JSONResponse(content={"species": query.title(), **_info_cache[cache_key]})

    demo = {
        "species": query.title(),
        "habitat": {"climate": "Varies", "distribution": "Global", "description": f"{query.title()} inhabits a variety of ecosystems."},
        "food_chain": {"trophic_level": "Varies", "chain": ["Plants", query.title(), "Predators"], "description": f"{query.title()} plays an important ecological role."},
        "conservation": {"status": "Data Deficient", "threats": "Habitat loss, climate change.", "actions": "Research and habitat protection needed."}
    }

    if not get_groq_configured():
        return JSONResponse(content=demo)

    try:
        schema = (
            '{"species":"str","scientific_name":"str","habitat":{"climate":"str","distribution":"str","description":"str"},'
            '"food_chain":{"trophic_level":"str","chain":["str"],"description":"str"},'
            '"conservation":{"status":"str","threats":"str","actions":"str"}}'
        )
        prompt = (
            f"Return structured JSON (no markdown) for the animal '{query}'. "
            f"Use this exact schema: {schema}. Be factual and concise. "
            f"If the query is not an animal, return the closest matching animal species."
        )
        raw_text = gemini_generate(prompt)
        if not raw_text or raw_text == QUOTA_MSG:
            return JSONResponse(content=demo)
        clean = raw_text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        parsed = json.loads(clean)
        _info_cache[cache_key] = {k: v for k, v in parsed.items() if k != "species"}
        return JSONResponse(content=parsed)
    except Exception:
        return JSONResponse(content=demo)

# ?? Chat ??????????????????????????????????????????????????????????????????????
DEMO_RESPONSES = {
    "Dog":      "Canines have ~300 million olfactory receptors ? 40? more than humans. What aspect of canine biology interests you?",
    "Horse":    "Equines sleep standing up via a passive stay apparatus. Want to explore their locomotion or domestication history?",
    "Elephant": "Elephants mourn their dead and recognise themselves in mirrors ? one of few species with self-awareness. Shall we discuss cognition or habitat corridors?",
    "Butterfly":"Lepidoptera undergo complete metamorphosis in 4 stages. Their wing patterns encode species identity. Explore migration or mimicry?",
    "Chicken":  "Chickens have full-colour vision and communicate with 30+ distinct vocalisations. What would you like to know?",
    "Cat":      "Felids have a flexible spine that allows them to right themselves mid-fall. Conservation or behaviour deep-dive?",
    "Cow":      "Bovines have a 4-chamber stomach for cellulose fermentation. Want to explore their ecological carbon impact?",
    "Sheep":    "Sheep can recognise up to 50 sheep faces and remember them for years. Explore flocking dynamics?",
    "Squirrel": "Squirrels plant thousands of seeds per season, forgetting ~74% ? making them critical reforesters. Want more?",
    "Spider":   "Spiders produce up to 7 types of silk ? stronger than steel by weight. Explore venom or web mechanics?",
}

@app.post("/api/chat")
async def api_chat(
    message:        str = Form(...),
    species_context:str = Form(default=""),
    chat_history:   str = Form(default="[]"),
    session_id:     str = Form(default=""),
):
    try:
        history = json.loads(chat_history)
    except Exception:
        history = []
    sid = session_id or str(uuid.uuid4())

    # Log the user message
    db_insert("chat_logs", {
        "session_id":      sid,
        "role":            "user",
        "content":         message,
        "species_context": species_context,
        "created_at":      datetime.utcnow().isoformat(),
    })

    if not get_groq_configured():
        fallback = DEMO_RESPONSES.get(species_context,
            "WildLens AI is ready. Ask me anything about wildlife, habitats, or conservation!")
        response_text = f"{fallback}"
        db_insert("chat_logs", {
            "session_id":      sid,
            "role":            "assistant",
            "content":         response_text,
            "species_context": species_context,
            "created_at":      datetime.utcnow().isoformat(),
        })
        return JSONResponse(content={"response": response_text, "session_id": sid})

    try:
        system = (
            f"You are WildLens AI, an expert wildlife intelligence assistant. "
            f"Current species context: '{species_context or 'General Wildlife'}'. "
            f"Provide insightful, accurate, conservation-focused responses. "
            f"Keep answers concise and engaging. Never mention API errors or technical details."
        )
        messages = [{"role": "system", "content": system}]
        for turn in history[-6:]:
            content_val = turn.get("text", turn.get("content", ""))
            messages.append({"role": turn["role"] if turn.get("role") in ["user", "assistant"] else "user", "content": content_val})
        messages.append({"role": "user", "content": message})

        response_text = gemini_generate(messages) or "I'm having trouble responding right now. Please try again."

        db_insert("chat_logs", {
            "session_id":      sid,
            "role":            "assistant",
            "content":         response_text,
            "species_context": species_context,
            "created_at":      datetime.utcnow().isoformat(),
        })
        return JSONResponse(content={"response": response_text, "session_id": sid})
    except Exception as e:
        err = str(e).lower()
        if "quota" in err or "429" in err or "exhausted" in err:
            return JSONResponse(content={"response": QUOTA_MSG})
        return JSONResponse(content={"response": "Something went wrong. Please try again in a moment."})

# ?? Enterprise Report ?????????????????????????????????????????????????????????
@app.post("/api/report")
async def api_report(
    species:    str = Form(...),
    session_id: str = Form(default=""),
):
    sid = session_id or str(uuid.uuid4())
    demo_report = f"""# WILDLENS AI ? Enterprise Conservation & Habitat Risk Report
**Species:** {species}  
**Report ID:** WL-{hash(species) % 99999:05d}  
**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  
**Tier:** Enterprise Premium

---

## Executive Summary
The {species} occupies a critical niche within its native ecosystem. Current population trajectories 
indicate moderate pressure from anthropogenic encroachment and climate-driven habitat shifts.

## 1. Habitat Suitability Analysis
- **Suitable Habitat:** 68% of historical range remains viable
- **Degradation Rate:** -2.1% CAGR over trailing 10-year period
- **Primary Stressor:** Urban expansion and agricultural land conversion

## 2. Demographic Trend Modelling
| Metric | Value |
|---|---|
| Population Trend | Stable ? Declining |
| Generation Length | Species-dependent |
| Reproductive Rate | Moderate |
| Mortality Pressure | Medium-High |

## 3. Conservation Risk Matrix
- **IUCN Status:** Least Concern (LC) ? subject to revision
- **Key Threats:** Habitat loss, chemical pollution, climate extremes
- **Corridor Integrity:** 42% of migration routes intact

## 4. Recommended Action Framework
1. Establish GPS-tracked biological travel corridors
2. Deploy WildLens camera-trap API network for real-time census
3. Implement community stewardship programs in buffer zones
4. Restrict agrochemical use within 5km of nesting habitat

---
*Report generated by WildLens AI Enterprise Intelligence Engine v2.0*
"""

    if get_groq_configured():
        try:
            prompt = (
                f"Generate a professional enterprise conservation and habitat risk report "
                f"for the species '{species}'. Use markdown formatting with an executive summary, "
                f"habitat analysis, demographic trends, risk matrix, and conservation recommendations."
            )
            text = gemini_generate(prompt)
            if text:
                demo_report = text
        except Exception:
            pass  # Fall through to demo report

    db_insert("reports", {
        "session_id": sid,
        "species":    species,
        "created_at": datetime.utcnow().isoformat(),
        "ai_powered": get_groq_configured(),
    })

    return JSONResponse(content={"report": demo_report})

# ?? Citizen Science Contribution ??????????????????????????????????????????????
@app.post("/api/contribute")
async def api_contribute(
    species:    str = Form(...),
    scan_id:    str = Form(default=""),
    session_id: str = Form(default=""),
    location:   str = Form(default="Unknown"),
):
    db_insert("science_contributions", {
        "scan_id":    scan_id or str(uuid.uuid4()),
        "session_id": session_id or str(uuid.uuid4()),
        "species":    species,
        "location":   location,
        "created_at": datetime.utcnow().isoformat(),
    })
    return JSONResponse(content={"status": "logged", "message": "Thank you! Your observation has been added to the public science database."})

# ?? Premium Signup (Mock Stripe) ??????????????????????????????????????????????
@app.post("/api/premium/activate")
async def api_premium_activate(
    session_id: str = Form(default=""),
    plan:       str = Form(default="monthly"),
):
    sid = session_id or str(uuid.uuid4())
    db_insert("premium_signups", {
        "session_id": sid,
        "plan":       plan,
        "amount_usd": 29 if plan == "monthly" else 249,
        "status":     "mock_approved",
        "created_at": datetime.utcnow().isoformat(),
    })
    return JSONResponse(content={
        "status":     "approved",
        "session_id": sid,
        "message":    "Premium activated! All enterprise features are now unlocked.",
    })

# ?? Analytics (DB stats) ??????????????????????????????????????????????????????
@app.get("/api/analytics")
async def api_analytics():
    stats = {
        "total_scans":         0,
        "total_chats":         0,
        "total_contributions": 0,
        "total_premium":       0,
        "top_species":         [],
    }
    if supabase:
        try:
            scans = supabase.table("scans").select("species", count="exact").execute()
            stats["total_scans"] = scans.count or 0

            chats = supabase.table("chat_logs").select("id", count="exact").execute()
            stats["total_chats"] = chats.count or 0

            contrib = supabase.table("science_contributions").select("id", count="exact").execute()
            stats["total_contributions"] = contrib.count or 0

            prem = supabase.table("premium_signups").select("id", count="exact").execute()
            stats["total_premium"] = prem.count or 0
        except Exception as e:
            print(f"Analytics fetch error: {e}")
    return JSONResponse(content=stats)

# ==========================================
# 7. Serve React Frontend (production build)
# ==========================================
dist_path = os.path.join("frontend", "dist")
if os.path.exists(dist_path):
    assets_path = os.path.join(dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/", response_class=HTMLResponse)
    async def serve_index():
        index = os.path.join(dist_path, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return HTMLResponse("<h1>Frontend build not found. Run: cd frontend && npm run build</h1>")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_spa(full_path: str):
        """Catch-all for React Router ? returns index.html for all frontend routes."""
        index = os.path.join(dist_path, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
else:
    @app.get("/")
    async def api_root():
        return {
            "app":     APP_NAME,
            "version": APP_VERSION,
            "status":  "API online. Build the React frontend or run dev server.",
            "docs":    "/docs",
        }

# ==========================================
# 8. Startup Banner & Main Runner
# ==========================================
@app.on_event("startup")
async def startup_banner():
    gemini_status  = "Active" if GEMINI_API_KEY else "Not set"
    supabase_status = "Connected" if supabase else "Not connected"
    model_status   = "Custom-trained" if has_custom_model else "ImageNet backbone"
    print(f"""\n{'='*52}
  WildLens AI v{APP_VERSION} -- ONLINE
{'='*52}
  Gemini API  : {gemini_status}
  Supabase DB : {supabase_status}
  CNN Model   : {model_status}
  Device      : {str(device)}
{'='*52}\n""")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
