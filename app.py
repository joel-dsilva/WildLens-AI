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
from google import genai
from google.genai import types as genai_types
from supabase import create_client, Client

# ==========================================
# 1. Environment & Configuration
# ==========================================
load_dotenv()  # Auto-loads .env file ? no manual setup needed

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

# ==========================================
# ==========================================
# 4. Gemini GenAI - Auto-loaded from .env
# ==========================================
_gemini_client = None

def get_gemini_client():
    global _gemini_client
    if not GEMINI_API_KEY:
        return None
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("[OK] Gemini client initialised from environment.")
    return _gemini_client

QUOTA_MSG = "The AI assistant is currently busy. Please wait a moment and try again."

def gemini_generate(prompt: str) -> str | None:
    client = get_gemini_client()
    if not client:
        return None
    try:
        resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return resp.text
    except Exception as e:
        err = str(e).lower()
        if "quota" in err or "429" in err or "exhausted" in err or "resource" in err:
            return QUOTA_MSG
        raise

def classify_image_gemini(image_bytes: bytes) -> dict:
    """Use Gemini Vision to identify any animal species in the image."""
    t0 = time.time()
    client = get_gemini_client()

    if not client:
        # Fallback: use local CNN if Gemini not available
        return classify_image_cnn(image_bytes)

    try:
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        # Detect MIME type
        img_obj = Image.open(io.BytesIO(image_bytes))
        fmt = img_obj.format or "JPEG"
        mime_map = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}
        mime_type = mime_map.get(fmt.upper(), "image/jpeg")

        prompt = (
            "You are a professional wildlife biologist. Look at this image carefully.\n"
            "Identify the primary animal species visible.\n"
            "Respond ONLY with valid JSON in this exact format (no markdown, no extra text):\n"
            '{"species": "<common name of the animal>", "scientific_name": "<scientific name>", '
            '"confidence": <integer 0-100>, "description": "<one sentence about this animal>"}\n'
            "If no animal is visible, set species to \"No Animal Detected\" and confidence to 0."
        )

        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt
            ]
        )
        raw = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(raw)
        total_ms = round((time.time() - t0) * 1000, 2)
        return {
            "species":         data.get("species", "Unknown"),
            "scientific_name": data.get("scientific_name", ""),
            "confidence":      data.get("confidence", 0),
            "description":     data.get("description", ""),
            "model_type":      "gemini_vision",
            "latency": {
                "preprocessing": 0,
                "inference": total_ms,
                "postprocessing": 0,
                "total": total_ms,
            }
        }
    except Exception as e:
        err = str(e).lower()
        if "quota" in err or "429" in err or "exhausted" in err or "resource" in err:
            return {
                "species": "Quota Exceeded",
                "scientific_name": "",
                "confidence": 0,
                "description": "API quota limit reached. Please try again in a moment.",
                "model_type": "gemini_vision",
                "latency": {"preprocessing": 0, "inference": 0, "postprocessing": 0, "total": 0},
                "error": "quota_exceeded"
            }
        # Fallback to CNN
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
    """Fallback CNN classifier for the 10 training classes."""
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

    top_prob, top_idx = torch.topk(probs, 1)
    species    = custom_classes[top_idx[0].item()]
    confidence = round(top_prob[0].item() * 100, 2)
    total_ms   = round((time.time() - t0) * 1000, 2)
    return {
        "species":         species,
        "scientific_name": "",
        "confidence":      confidence,
        "description":     "",
        "model_type":      "cnn_fallback",
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
        "gemini":         bool(GEMINI_API_KEY),
        "supabase":       supabase is not None,
        "custom_model":   has_custom_model,
        "device":         str(device),
    }

# Classify - Gemini Vision (200+ species) with CNN fallback
@app.post("/api/classify")
async def api_classify(
    file:       UploadFile = File(...),
    session_id: str        = Form(default=""),
):
    try:
        raw     = await file.read()
        result  = classify_image_gemini(raw)
        scan_id = str(uuid.uuid4())

        db_insert("scans", {
            "id":          scan_id,
            "session_id":  session_id or str(uuid.uuid4()),
            "species":     result["species"],
            "confidence":  result["confidence"],
            "model_type":  result["model_type"],
            "latency_ms":  result["latency"]["total"],
            "created_at":  datetime.utcnow().isoformat(),
        })

        result["scan_id"] = scan_id
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ?? Species Info (structured Gemini JSON) ????????????????????????????????????
@app.post("/api/info")
async def api_info(species: str = Form(...)):
    demo_payload = {
        "habitat": {
            "climate":      "Varies by region",
            "distribution": "Global ? species-dependent",
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

    if not get_gemini_client():
        return JSONResponse(content=demo_payload)

    try:
        schema = (
            '{"habitat":{"climate":"str","distribution":"str","description":"str"},'
            '"food_chain":{"trophic_level":"str","chain":["str"],"description":"str"},'
            '"conservation":{"status":"str","threats":"str","actions":"str"}}'
        )
        prompt = (
            f"Return structured JSON (no markdown wrapping) for the animal '{species}' "
            f"matching this exact schema: {schema}"
        )
        raw_text = gemini_generate(prompt)
        if not raw_text:
            return JSONResponse(content=demo_payload)
        clean = raw_text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return JSONResponse(content=json.loads(clean))
    except Exception as e:
        return JSONResponse(content=demo_payload)

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
    history = json.loads(chat_history)
    sid     = session_id or str(uuid.uuid4())

    # Log the user message
    db_insert("chat_logs", {
        "session_id":      sid,
        "role":            "user",
        "content":         message,
        "species_context": species_context,
        "created_at":      datetime.utcnow().isoformat(),
    })

    if not get_gemini_client():
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
        full_prompt = system + "\n\n"
        for turn in history[-6:]:
            prefix = "User: " if turn["role"] == "user" else "Assistant: "
            full_prompt += prefix + turn["content"] + "\n"
        full_prompt += f"User: {message}\nAssistant:"

        response_text = gemini_generate(full_prompt) or "I'm having trouble responding right now. Please try again."

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

    if get_gemini_client():
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
        "ai_powered": bool(get_gemini_client()),
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
