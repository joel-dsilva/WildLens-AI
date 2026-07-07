# 🌿 WildLens AI — Ecology Intelligence Platform

WildLens AI is a modern, full-stack web application designed to help users identify animals and understand their ecosystems instantly. Users can upload a photo (or capture one using a live webcam feed) to identify animals, view interactive ecological summaries, explore a comprehensive encyclopedia, chat with an AI wildlife expert, and persist their scan history across multiple devices.

Live Public App: [wildlens-ai.onrender.com](https://wildlens-ai.onrender.com)

---

## 🛠️ The Tech Stack

- **Frontend**: React.js (Vite) + Vanilla CSS (Glassmorphism theme)
- **Backend**: FastAPI (Python)
- **Primary ML Model**: PyTorch (Custom-trained MobileNetV3 Large on 10 animal classes)
- **Vision AI fallback**: Groq (Llama 4 Scout 17B)
- **Generative AI Chat & Data**: Groq (Llama 3.3 70B)
- **Database & Auth**: Supabase (PostgreSQL + JWT Auth)
- **Deployment**: Render.com + GitHub Auto-deploy
- **Third-Party Integrations**: n8n Webhook notifications on scans

---

## 🚀 Key Features

### 1. Multi-Animal & Human Detection
- If multiple animals are present in an image, the system detects all of them.
- Users can toggle between tabs of different identified species to see their individual ecological profiles.
- Backed by an automated two-pass validation system that intercepts safety filters to detect human presence.

### 2. Pokedex-style Quick Summary
- Displays a clean visual card on the dashboard summarizing the animal's IUCN status, trophic level, range distribution, habitat, and key threats.
- Accompanied by three detailed profile tabs below: *Habitat & Distribution*, *Food Chain*, and *IUCN Conservation Status*.

### 3. AI Wildlife Expert Chat
- A conversational panel loaded with the context of the active animal tab.
- Integrated voice recognition (Microphone Input) powered by the browser-native **Web Speech API** for hands-free queries.

### 4. Searchable Encyclopedia
- Search and lookup details on any animal in the world, with caching enabled to prevent repeated AI requests.

### 5. Secure Authentication & History Tracking
- User accounts managed securely by Supabase.
- Includes a **"Continue as Guest"** option to bypass registration limits instantly.
- Keeps scans and search histories isolated and stored per user account.

---

## 💻 Project Structure

```
WildLens AI/
├── app.py                  # Python backend (FastAPI server)
├── animals10_model.pth     # Trained PyTorch weights
├── requirements.txt        # Backend dependencies
├── README.md               # Project documentation
└── frontend/
    ├── src/
    │   ├── App.jsx         # Main React UI logic
    │   └── App.css         # Custom styling
    ├── public/
    │   └── logo.svg        # Official brand logo
    └── dist/               # Built static production files
```

---

## 🔧 Local Development Setup

### 1. Backend Setup
1. Clone the repository and navigate to the project directory:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.env` file in the root folder with the following variables:
   ```env
   GEMINI_API_KEY=your_api_key
   GROQ_API_KEY=your_groq_key
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_service_role_key
   N8N_WEBHOOK_URL=optional_n8n_webhook_url
   ```
3. Start the FastAPI server:
   ```bash
   python app.py
   ```

### 2. Frontend Setup
1. Navigate into the frontend directory:
   ```bash
   cd frontend
   npm install
   ```
2. Run the development environment:
   ```bash
   npm run dev
   ```
3. Build the production package (files are bundled into `dist/` and served by FastAPI):
   ```bash
   npm run build
   ```
