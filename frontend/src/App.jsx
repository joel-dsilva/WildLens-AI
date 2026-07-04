import React, { useState, useEffect, useRef } from 'react';
import {
  Camera, UploadCloud, MessageSquare, BookOpen, BarChart2,
  Loader2, Send, ChevronRight, Zap, Globe,
  Clock, TrendingUp, X, RefreshCw, ArrowRight,
  Activity, Microscope, Shield, Plus, Search
} from 'lucide-react';
import './App.css';

const POPULAR_ANIMALS = [
  "Lion","Tiger","Elephant","Giraffe","Zebra","Cheetah","Gorilla","Panda",
  "Polar Bear","Wolf","Eagle","Dolphin","Shark","Penguin","Crocodile",
  "Kangaroo","Koala","Chimpanzee","Jaguar","Snow Leopard","Flamingo","Orangutan",
  "Bald Eagle","Komodo Dragon","Blue Whale","Axolotl","Pangolin","Platypus"
];
const EMOJI_MAP = {
  Dog:"🐕", Horse:"🐴", Elephant:"🐘", Butterfly:"🦋", Chicken:"🐔",
  Cat:"🐱", Cow:"🐄", Sheep:"🐑", Squirrel:"🐿️", Spider:"🕷️",
  Lion:"🦁", Tiger:"🐯", Giraffe:"🦒", Zebra:"🦓", Cheetah:"🐆",
  Gorilla:"🦍", Panda:"🐼", Wolf:"🐺", Eagle:"🦅", Dolphin:"🐬",
  Shark:"🦈", Penguin:"🐧", Crocodile:"🐊", Kangaroo:"🦘", Koala:"🐨",
  Jaguar:"🐆", Chimpanzee:"🐒", Flamingo:"🦩", Orangutan:"🦧",
  Platypus:"🦆", Axolotl:"🦎", Pangolin:"🐾"
};
const getEmoji = (name) => EMOJI_MAP[name] || "🐾";


const HOST = window.location.hostname === "localhost" ? "http://127.0.0.1:8000" : "";

const statusColor = (s = "") => {
  const l = s.toLowerCase();
  if (l.includes("least concern")) return "#10b981";
  if (l.includes("vulnerable"))   return "#f59e0b";
  if (l.includes("endangered"))   return "#ef4444";
  return "#6b7280";
};
const confidenceColor = (c) => c >= 80 ? "#10b981" : c >= 50 ? "#f59e0b" : "#ef4444";

export default function App() {
  const [tab, setTab] = useState("scanner");

  // Scanner — multiple images
  const [images, setImages]         = useState([]); // [{url, file, result, ecoInfo, scanning}]
  const [activeIdx, setActiveIdx]   = useState(0);
  const [dragOver, setDragOver]     = useState(false);
  const [camActive, setCamActive]   = useState(false);
  const videoRef   = useRef(null);
  const canvasRef  = useRef(null);
  const fileRef    = useRef(null);

  // Encyclopedia — search any animal
  const [encQuery, setEncQuery]     = useState("");
  const [selAnimal, setSelAnimal]   = useState(null);
  const [encData, setEncData]       = useState({});
  const [loadingEnc, setLoadingEnc] = useState(false);

  // Chat (right sidebar)
  const chatBottom = useRef(null);
  const [msgs, setMsgs]     = useState([{ role:"bot", text:"Hi! I'm WildLens AI 🌿 Upload an animal photo or ask me anything about wildlife.", ts: new Date() }]);
  const [input, setInput]   = useState("");
  const [chatBusy, setChatBusy] = useState(false);

  // History
  const [history, setHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem("wl_hist") || "[]"); } catch { return []; }
  });

  useEffect(() => { localStorage.setItem("wl_hist", JSON.stringify(history)); }, [history]);
  useEffect(() => { chatBottom.current?.scrollIntoView({ behavior:"smooth" }); }, [msgs]);

  // ── Camera ───────────────────────────────────────────
  const startCam = async () => {
    setCamActive(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video:{ facingMode:"environment" } });
      if (videoRef.current) videoRef.current.srcObject = stream;
    } catch { setCamActive(false); alert("Camera permission denied."); }
  };
  const stopCam = () => {
    videoRef.current?.srcObject?.getTracks().forEach(t => t.stop());
    setCamActive(false);
  };
  const capture = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const v = videoRef.current, c = canvasRef.current;
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0);
    c.toBlob(blob => {
      const f = new File([blob], "snap.jpg", { type:"image/jpeg" });
      addImages([f]); stopCam();
    }, "image/jpeg");
  };

  // ── Multi-file handlers ─────────────────────────────
  const addImages = (files) => {
    const valid = Array.from(files).filter(f => f.type.startsWith("image/"));
    if (!valid.length) return;
    const newEntries = valid.map(f => ({ url: URL.createObjectURL(f), file: f, result: null, ecoInfo: null, scanning: false }));
    setImages(prev => {
      const updated = [...prev, ...newEntries];
      const startIdx = prev.length;
      setActiveIdx(startIdx);
      // Start processing each new image
      newEntries.forEach((entry, i) => processImage(startIdx + i, entry.file, updated));
      return updated;
    });
  };

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    addImages(e.dataTransfer.files);
  };
  const onFileChange = (e) => {
    if (e.target.files?.length) addImages(e.target.files);
  };

  // ── Classify ──────────────────────────────────────────
  const processImage = async (idx, file, currentImages) => {
    setImages(prev => {
      const updated = [...prev];
      if (updated[idx]) updated[idx] = { ...updated[idx], scanning: true, result: null, ecoInfo: null };
      return updated;
    });
    const fd = new FormData(); fd.append("file", file);
    try {
      const r = await fetch(`${HOST}/api/classify`, { method:"POST", body:fd });
      if (!r.ok) throw new Error("classify failed");
      const d = await r.json();
      setImages(prev => {
        const updated = [...prev];
        if (updated[idx]) updated[idx] = { ...updated[idx], scanning: false, result: d };
        return updated;
      });
      setHistory(prev => [
        { id: Date.now(), species: d.species, confidence: d.confidence, ts: new Date().toISOString(), img: URL.createObjectURL(file) },
        ...prev
      ].slice(0, 60));
      if (d.species !== "Quota Exceeded" && d.species !== "No Animal Detected" && d.confidence >= 45) {
        fetchEco(idx, d.species);
      }
    } catch {
      setImages(prev => {
        const updated = [...prev];
        if (updated[idx]) updated[idx] = { ...updated[idx], scanning: false };
        return updated;
      });
    }
  };

  const fetchEco = async (idx, sp) => {
    const fd = new FormData(); fd.append("species", sp);
    try {
      const r = await fetch(`${HOST}/api/info`, { method:"POST", body:fd });
      const data = await r.json();
      setImages(prev => {
        const updated = [...prev];
        if (updated[idx]) updated[idx] = { ...updated[idx], ecoInfo: data };
        return updated;
      });
    } catch {}
  };

  const removeImage = (idx) => {
    setImages(prev => {
      const updated = prev.filter((_, i) => i !== idx);
      setActiveIdx(ai => Math.min(ai, updated.length - 1));
      return updated;
    });
  };

  const resetAll = () => { setImages([]); setActiveIdx(0); if(fileRef.current) fileRef.current.value=""; };

  // ── Encyclopedia ──────────────────────────────────────
  const searchAnimal = async (query) => {
    if (!query.trim()) return;
    const key = query.trim().toLowerCase();
    setSelAnimal(query.trim());
    if (encData[key]) return; // already cached
    setLoadingEnc(true);
    const fd = new FormData(); fd.append("query", query.trim());
    try {
      const r = await fetch(`${HOST}/api/search`, { method:"POST", body:fd });
      const data = await r.json();
      setEncData(prev => ({ ...prev, [key]: data }));
    } catch {} finally { setLoadingEnc(false); }
  };

  const handleEncSearch = (e) => {
    e.preventDefault();
    searchAnimal(encQuery);
  };

  // ── Chat ──────────────────────────────────────────────
  const sendMsg = async () => {
    if (!input.trim() || chatBusy) return;
    const text = input; setInput(""); setChatBusy(true);
    setMsgs(prev => [...prev, { role:"user", text, ts:new Date() }]);
    const activeResult = images[activeIdx]?.result;
    const fd = new FormData();
    fd.append("message", text);
    fd.append("species_context", activeResult?.species || "");
    fd.append("chat_history", JSON.stringify(msgs.slice(-8)));
    try {
      const r = await fetch(`${HOST}/api/chat`, { method:"POST", body:fd });
      const d = await r.json();
      setMsgs(prev => [...prev, { role:"bot", text: d.response, ts:new Date() }]);
    } catch {
      setMsgs(prev => [...prev, { role:"bot", text:"Connection error. Please check if the server is running.", ts:new Date() }]);
    } finally { setChatBusy(false); }
  };

  // ── Stats ─────────────────────────────────────────────
  const counts = history.reduce((a, s) => { a[s.species] = (a[s.species]||0)+1; return a; }, {});
  const topSp   = Object.entries(counts).sort((a,b) => b[1]-a[1]).slice(0,5);
  const avgConf = history.length ? (history.reduce((a,s) => a+s.confidence,0)/history.length).toFixed(1) : "—";

  const NAV = [
    { id:"scanner",     label:"Species Scanner",  icon:<Microscope size={17}/> },
    { id:"encyclopedia",label:"Encyclopedia",      icon:<BookOpen size={17}/> },
    { id:"history",     label:"Scan History",      icon:<BarChart2 size={17}/> },
  ];

  const activeImage = images[activeIdx];

  return (
    <div className="shell">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon"><Activity size={19} strokeWidth={2.5}/></div>
          <div>
            <div className="brand-name">WildLens AI</div>
            <div className="brand-tag">Ecology Intelligence</div>
          </div>
        </div>

        <nav className="nav">
          {NAV.map(n => (
            <button key={n.id} className={`nav-item ${tab===n.id?"active":""}`} onClick={()=>setTab(n.id)}>
              {n.icon}<span>{n.label}</span>
              {tab===n.id && <ChevronRight size={13} className="nav-chevron"/>}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="pills">
            <span className="pill"><Zap size={11}/>{history.length} scans</span>
            <span className="pill"><Activity size={11}/>{avgConf}% avg</span>
          </div>
          <p className="footer-note">Custom CNN + Unlimited Scans</p>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="main">
        {/* Topbar */}
        <header className="topbar">
          <div>
            <h1 className="topbar-title">{NAV.find(n=>n.id===tab)?.label}</h1>
            <span className="topbar-sub">
              {tab==="scanner"      && "Upload multiple animal photos and get instant AI-powered identification"}
              {tab==="encyclopedia" && "Explore detailed ecological profiles powered by AI"}
              {tab==="history"      && `${history.length} scans recorded in this session`}
            </span>
          </div>
          <div className="status-row"><div className="dot"/><span className="status-txt">Online</span></div>
        </header>

        <div className="body">

          {/* ════ SCANNER ════ */}
          {tab==="scanner" && (
            <div className="scanner-page">

              {/* ── Upload Strip ── */}
              <div className="upload-strip">
                {/* Drop zone button */}
                <div
                  className={`dropzone-mini ${dragOver?"dragover":""}`}
                  onDragOver={e=>{e.preventDefault();setDragOver(true)}}
                  onDragLeave={()=>setDragOver(false)}
                  onDrop={onDrop}
                  onClick={()=>fileRef.current?.click()}
                >
                  <Plus size={20}/>
                  <span>Add Photos</span>
                  <input ref={fileRef} type="file" accept="image/*" multiple onChange={onFileChange} hidden/>
                </div>

                {/* Webcam button */}
                {!camActive && (
                  <button className="cam-mini" onClick={startCam}>
                    <Camera size={16}/><span>Webcam</span>
                  </button>
                )}

                {/* Thumbnail strip */}
                {images.map((img, i) => (
                  <div
                    key={i}
                    className={`thumb-wrap ${i===activeIdx?"thumb-active":""}`}
                    onClick={()=>setActiveIdx(i)}
                  >
                    <img src={img.url} alt="" className="thumb"/>
                    {img.scanning && <div className="thumb-overlay"><Loader2 size={14} className="spin"/></div>}
                    {img.result && !img.scanning && (
                      <div className="thumb-badge" style={{background: img.result.error ? "#ef4444" : "#10b981"}}>
                        {img.result.error ? "!" : `${img.result.confidence}%`}
                      </div>
                    )}
                    <button className="thumb-remove" onClick={e=>{e.stopPropagation();removeImage(i)}}><X size={10}/></button>
                  </div>
                ))}

                {images.length > 0 && (
                  <button className="btn-ghost" style={{marginLeft:"auto"}} onClick={resetAll}>
                    <RefreshCw size={13}/> Clear All
                  </button>
                )}
              </div>

              {/* Webcam view */}
              {camActive && (
                <div className="cam-box">
                  <video ref={videoRef} autoPlay className="cam-feed"/>
                  <canvas ref={canvasRef} hidden/>
                  <div className="cam-actions">
                    <button className="btn-accent" onClick={capture}><Camera size={15}/>Capture</button>
                    <button className="btn-ghost"  onClick={stopCam}><X size={15}/>Cancel</button>
                  </div>
                </div>
              )}

              {/* Empty state */}
              {images.length === 0 && !camActive && (
                <div
                  className={`dropzone-main ${dragOver?"dragover":""}`}
                  onDragOver={e=>{e.preventDefault();setDragOver(true)}}
                  onDragLeave={()=>setDragOver(false)}
                  onDrop={onDrop}
                  onClick={()=>fileRef.current?.click()}
                >
                  <div className="drop-ring"><UploadCloud size={36} strokeWidth={1.5}/></div>
                  <h3>Drop animal photos here</h3>
                  <p>or click to browse — supports multiple files at once</p>
                  <span className="drop-hint">JPG · PNG · WEBP · GIF</span>
                  <span className="drop-hint" style={{color:"#6366f1"}}>✨ Fast Offline Model — unlimited free scans</span>
                </div>
              )}

              {/* Active image content */}
              {activeImage && !camActive && (
                <div className="scanner-content">

                  {/* Image preview (compact) */}
                  <div className="preview-row">
                    <div className="preview-box">
                      <img src={activeImage.url} alt="preview" className="preview-img"/>
                      {activeImage.scanning && (
                        <div className="preview-scanning">
                          <Loader2 size={32} className="spin"/>
                          <p>Analyzing image structure…</p>
                        </div>
                      )}
                    </div>

                    {/* Result card */}
                    {activeImage.result && !activeImage.scanning && (
                      <div className="result-panel">
                        {activeImage.result.error === "quota_exceeded" ? (
                          <div className="quota-warn">
                            <div className="quota-icon">⚡</div>
                            <h3>API Quota Reached</h3>
                            <p>The AI has hit its rate limit. Please wait a minute and try again.</p>
                          </div>
                        ) : (
                          <>
                            {activeImage.result.confidence >= 45 ? (
                              <div className="result-top" style={{ alignItems: 'center' }}>
                                <span className="result-emoji" style={{ fontSize: '2.5rem', marginRight: '1rem' }}>{EMOJI[activeImage.result.species] || "🐾"}</span>
                                <div>
                                  <div className="result-lbl" style={{ fontSize: '1.2rem', fontWeight: 600, color: '#1f2937' }}>
                                    It is a {activeImage.result.species}
                                  </div>
                                </div>
                              </div>
                            ) : (
                              <div className="result-top" style={{ alignItems: 'center' }}>
                                <span className="result-emoji" style={{ fontSize: '2.5rem', marginRight: '1rem' }}>🤔</span>
                                <div>
                                  <div className="result-lbl" style={{ fontSize: '1.1rem', fontWeight: 500, color: '#4b5563', lineHeight: '1.5' }}>
                                    I am unsure what this is.<br/>Try asking the AI Agent for help.
                                  </div>
                                </div>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Eco info section — full width below image */}
                  {activeImage.ecoInfo && typeof activeImage.ecoInfo === 'object' && !activeImage.scanning && activeImage.result?.confidence >= 45 && (
                    <div className="eco-section">
                      <div className="eco-grid">
                        <div className="card">
                          <div className="card-head"><Globe size={14}/><span>Habitat &amp; Distribution</span></div>
                          <div className="kv"><span className="kk">Climate</span><span className="kv-val">{activeImage.ecoInfo.habitat?.climate || "Unknown"}</span></div>
                          <div className="kv"><span className="kk">Range</span><span className="kv-val">{activeImage.ecoInfo.habitat?.distribution || "Unknown"}</span></div>
                          <p className="kdesc">{activeImage.ecoInfo.habitat?.description}</p>
                        </div>

                        <div className="card">
                          <div className="card-head"><ArrowRight size={14}/><span>Food Chain — {activeImage.ecoInfo.food_chain?.trophic_level || "Unknown"}</span></div>
                          <div className="chain">
                            {(activeImage.ecoInfo.food_chain?.chain || []).map((l,i,arr) => (
                              <React.Fragment key={i}>
                                <span className={`cnode ${l===activeImage.result?.species?"cnode-active":""}`}>{l}</span>
                                {i<arr.length-1 && <span className="carrow">→</span>}
                              </React.Fragment>
                            ))}
                          </div>
                          <p className="kdesc">{activeImage.ecoInfo.food_chain?.description}</p>
                        </div>

                        <div className="card">
                          <div className="card-head"><Shield size={14}/><span>IUCN Conservation Status</span></div>
                          <span className="iucn-badge" style={{borderColor:statusColor(activeImage.ecoInfo.conservation?.status),color:statusColor(activeImage.ecoInfo.conservation?.status)}}>
                            {activeImage.ecoInfo.conservation?.status || "Unknown"}
                          </span>
                          <div className="kv" style={{marginTop:10}}><span className="kk">Threats</span><span className="kv-val">{activeImage.ecoInfo.conservation?.threats || "Unknown"}</span></div>
                          <div className="kv"><span className="kk">Actions</span><span className="kv-val">{activeImage.ecoInfo.conservation?.actions || "Unknown"}</span></div>
                        </div>
                      </div>
                    </div>
                  )}

                  {!activeImage.result && !activeImage.scanning && (
                    <div className="eco-loading"><Loader2 size={18} className="spin"/> Waiting for result…</div>
                  )}
                  {activeImage.scanning && !activeImage.ecoInfo && (
                    <div className="eco-loading"><Loader2 size={18} className="spin"/> Fetching ecological data…</div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ════ ENCYCLOPEDIA ════ */}
          {tab==="encyclopedia" && (
            <div className="enc-layout">
              {/* Search bar */}
              <form className="enc-search-bar" onSubmit={handleEncSearch}>
                <div className="enc-search-input-wrap">
                  <Search size={15} className="enc-search-icon"/>
                  <input
                    className="enc-search-input"
                    placeholder="Search any animal — Lion, Axolotl, Blue Whale, Pangolin…"
                    value={encQuery}
                    onChange={e => setEncQuery(e.target.value)}
                  />
                </div>
                <button type="submit" className="btn-accent" disabled={!encQuery.trim() || loadingEnc}>
                  {loadingEnc ? <Loader2 size={14} className="spin"/> : <Search size={14}/>}
                  Search
                </button>
              </form>

              {/* Popular quick-picks */}
              <div className="popular-label">Popular Animals</div>
              <div className="popular-grid">
                {POPULAR_ANIMALS.map(a => (
                  <button
                    key={a}
                    className={`pop-chip ${selAnimal?.toLowerCase()===a.toLowerCase()?"pop-chip-active":""}`}
                    onClick={() => { setEncQuery(a); searchAnimal(a); }}
                  >
                    {getEmoji(a)} {a}
                  </button>
                ))}
              </div>

              {/* Loading */}
              {loadingEnc && (
                <div className="card loading-row"><Loader2 size={18} className="spin"/>Looking up {selAnimal} with AI…</div>
              )}

              {/* Result */}
              {selAnimal && encData[selAnimal?.toLowerCase()] && !loadingEnc && (() => {
                const d = encData[selAnimal.toLowerCase()];
                return (
                  <div className="enc-detail">
                    <div className="enc-header">
                      <span className="enc-emoji">{getEmoji(d.species || selAnimal)}</span>
                      <div>
                        <h2 className="enc-title">{d.species || selAnimal}</h2>
                        {d.scientific_name && <p className="enc-sci">{d.scientific_name}</p>}
                        <p className="enc-sub">Ecological Profile — AI Model</p>
                      </div>
                    </div>
                    <div className="enc-body">
                      <div className="card">
                        <div className="card-head"><Globe size={14}/><span>Habitat &amp; Distribution</span></div>
                        <div className="kv"><span className="kk">Climate</span><span className="kv-val">{d.habitat?.climate}</span></div>
                        <div className="kv"><span className="kk">Range</span><span className="kv-val">{d.habitat?.distribution}</span></div>
                        <p className="kdesc">{d.habitat?.description}</p>
                      </div>
                      <div className="card">
                        <div className="card-head"><ArrowRight size={14}/><span>Food Chain — {d.food_chain?.trophic_level}</span></div>
                        <div className="chain">
                          {d.food_chain?.chain?.map((l,i,arr) => (
                            <React.Fragment key={i}>
                              <span className={`cnode ${l.toLowerCase()===selAnimal?.toLowerCase()?"cnode-active":""}`}>{l}</span>
                              {i<arr.length-1 && <span className="carrow">→</span>}
                            </React.Fragment>
                          ))}
                        </div>
                        <p className="kdesc">{d.food_chain?.description}</p>
                      </div>
                      <div className="card">
                        <div className="card-head"><Shield size={14}/><span>IUCN Conservation Status</span></div>
                        <span className="iucn-badge" style={{borderColor:statusColor(d.conservation?.status),color:statusColor(d.conservation?.status)}}>
                          {d.conservation?.status}
                        </span>
                        <div className="kv" style={{marginTop:10}}><span className="kk">Threats</span><span className="kv-val">{d.conservation?.threats}</span></div>
                        <div className="kv"><span className="kk">Actions</span><span className="kv-val">{d.conservation?.actions}</span></div>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {!selAnimal && !loadingEnc && (
                <div className="enc-prompt">
                  <div className="empty-icon">📖</div>
                  <h3>Select an animal above</h3>
                  <p>Click any species card to load its full ecological profile, food chain, and IUCN conservation status powered by AI.</p>
                </div>
              )}
            </div>
          )}

          {/* ════ HISTORY ════ */}
          {tab==="history" && (
            <div className="hist-layout">
              {history.length===0 ? (
                <div className="empty-state" style={{maxWidth:400,margin:"80px auto"}}>
                  <div className="empty-icon">📋</div>
                  <h3>No scans yet</h3>
                  <p>Scan some animals and your history will appear here with stats and frequency charts.</p>
                  <button className="btn-accent" style={{marginTop:8}} onClick={()=>setTab("scanner")}>
                    Go to Scanner <ArrowRight size={14}/>
                  </button>
                </div>
              ) : (
                <>
                  <div className="stat-row">
                    {[
                      [history.length,            "Total Scans"],
                      [Object.keys(counts).length, "Species Found"],
                      [`${avgConf}%`,              "Avg Confidence"],
                      [topSp[0]?.[0]||"—",         "Top Species"],
                    ].map(([v,l]) => (
                      <div key={l} className="stat-card">
                        <div className="stat-val">{v}</div>
                        <div className="stat-lbl">{l}</div>
                      </div>
                    ))}
                  </div>

                  {topSp.length>0 && (
                    <div className="card">
                      <div className="card-head"><TrendingUp size={14}/><span>Species Frequency</span></div>
                      {topSp.map(([sp,ct]) => (
                        <div key={sp} className="freq-row">
                          <span className="freq-name">{EMOJI[sp]||"🐾"} {sp}</span>
                          <div className="freq-track"><div className="freq-fill" style={{width:`${(ct/history.length)*100}%`}}/></div>
                          <span className="freq-ct">{ct}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="card">
                    <div className="card-head" style={{justifyContent:"space-between"}}>
                      <div style={{display:"flex",alignItems:"center",gap:8}}><Clock size={14}/><span>Recent Scans</span></div>
                      <button className="clear-btn" onClick={()=>setHistory([])}>Clear All</button>
                    </div>
                    <div className="hist-list">
                      {history.map(s => (
                        <div key={s.id} className="hist-item">
                          <img src={s.img} alt={s.species} className="hist-thumb"/>
                          <div className="hist-info">
                            <div className="hist-species">{EMOJI[s.species]||"🐾"} {s.species}</div>
                            <div className="hist-meta">
                              <span style={{color:confidenceColor(s.confidence)}}>{s.confidence}% confidence</span>
                              <span>·</span>
                              <span>{new Date(s.ts).toLocaleString()}</span>
                            </div>
                          </div>
                          <div className="hist-bar-bg">
                            <div className="hist-bar" style={{width:`${s.confidence}%`,background:confidenceColor(s.confidence)}}/>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

        </div>
      </main>

      {/* ── Chatbot Right Panel ── */}
      <aside className="chat-panel">
        <div className="chat-panel-head">
          <MessageSquare size={16}/>
          <span>WildLens AI Chat</span>
          <span className="chat-model-tag">AI Agent</span>
        </div>

        {images[activeIdx]?.result?.species && tab==="scanner" && (
          <div className="ctx-banner">
            🎯 Context: <strong>{images[activeIdx].result.species}</strong>
          </div>
        )}

        <div className="chat-messages">
          {msgs.map((m,i) => (
            <div key={i} className={`bubble-row ${m.role}`}>
              <div className="avatar">{m.role==="bot"?"🤖":"👤"}</div>
              <div className="bubble-body">
                <div className="bubble">{m.text}</div>
                <div className="bubble-ts">{new Date(m.ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}</div>
              </div>
            </div>
          ))}
          {chatBusy && (
            <div className="bubble-row bot">
              <div className="avatar">🤖</div>
              <div className="bubble-body">
                <div className="bubble typing"><span/><span/><span/></div>
              </div>
            </div>
          )}
          <div ref={chatBottom}/>
        </div>

        <div className="chat-bar">
          <input
            className="chat-input"
            placeholder="Ask about behavior, habitat, diet…"
            value={input}
            onChange={e=>setInput(e.target.value)}
            onKeyDown={e=>e.key==="Enter"&&sendMsg()}
          />
          <button className="send-btn" onClick={sendMsg} disabled={!input.trim()||chatBusy}>
            <Send size={15}/>
          </button>
        </div>
      </aside>
    </div>
  );
}
