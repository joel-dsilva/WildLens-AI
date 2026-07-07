# WildLens AI — Species Detection & Ecology Platform

WildLens AI is a web application designed to identify animal species from photos and provide detailed ecological information (such as habitat, diet, food chain position, and conservation status). It integrates a custom-trained PyTorch machine learning model for fast, local classification alongside a cloud-based vision API fallback to handle multiple animals or human detection.

Live Website: [wildlens-ai.onrender.com](https://wildlens-ai.onrender.com)

---

## Tech Stack

* **Frontend**: React (Vite) and custom CSS
* **Backend**: FastAPI (Python)
* **ML Model**: PyTorch (MobileNetV3 Large trained on 10 animal classes)
* **Vision & Chat API**: Groq API (Llama 4 Scout 17B and Llama 3.3 70B)
* **Database & Authentication**: Supabase (PostgreSQL)
* **Webhook Automation**: n8n integration for scan notifications

---

## Core Features

### 1. Species Identification
* **Local CNN Model**: Photos are processed locally on the server using a fine-tuned MobileNetV3 model trained on 10 classes (dog, horse, elephant, butterfly, chicken, cat, cow, sheep, squirrel, and spider).
* **AI Fallback**: If the local model's confidence falls below 45%, the image is routed to a Llama 4 Scout vision model to identify the animal.

### 2. Multi-Subject & Human Detection
* The app identifies multiple species in a single image. The interface displays interactive tabs for each detected subject so users can toggle between their respective profiles.
* A fallback logic runs a secondary check specifically to bypass safety filters and flag human presence in uploads.

### 3. Pokedex-style Quick Summary
* Once identified, the app loads a quick summary card showing the conservation status, trophic level, range, habitat description, and key threats.
* Detailed tabs below the image break down *Habitat*, *Food Chain*, and *IUCN Status*.

### 4. Interactive AI Chat & Voice Input
* A sidebar panel lets users chat with an AI assistant about the active animal.
* Includes a microphone voice recognition option built directly using the browser's Web Speech API.

### 5. Account System & Scan History
* Handled securely via Supabase Auth.
* Includes a "Continue as Guest" option to bypass email verification and API limits during testing.
* Users can view their past scan history with thumbnails, stats, and a breakdown of frequently scanned species.

---

## Project Structure

```
.
├── app.py                  # FastAPI application server
├── animals10_model.pth     # PyTorch model weights
├── requirements.txt        # Python backend dependencies
└── frontend/
    ├── src/
    │   ├── App.jsx         # React UI code
    │   └── App.css         # Styling code
    ├── public/
    │   └── logo.svg        # Custom logo SVG
    └── dist/               # Bundled frontend production files
```

---

## Local Setup

### Backend
1. Install the backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY=your_gemini_key
   GROQ_API_KEY=your_groq_key
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_anon_key
   N8N_WEBHOOK_URL=your_n8n_webhook_url
   ```
3. Run the FastAPI application:
   ```bash
   python app.py
   ```

### Frontend
1. Navigate to the frontend directory and install packages:
   ```bash
   cd frontend
   npm install
   ```
2. Run Vite's local dev server:
   ```bash
   npm run dev
   ```
3. Build the production package (outputs to `/dist` folder for the backend to serve):
   ```bash
   npm run build
   ```
