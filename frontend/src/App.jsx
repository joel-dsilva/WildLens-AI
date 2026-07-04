import React, { useState, useEffect, useRef } from 'react';
import {
  Camera, UploadCloud, MessageSquare, BookOpen, BarChart2,
  Loader2, Send, ChevronRight, Zap, Globe, Leaf,
  Clock, TrendingUp, Info, X, RefreshCw, ArrowRight,
  Star, Activity, Microscope, Shield, AlertTriangle
} from 'lucide-react';
import './App.css';

const ANIMALS = ["Dog", "Horse", "Elephant", "Butterfly", "Chicken", "Cat", "Cow", "Sheep", "Squirrel", "Spider"];
const EMOJI = { Dog:"🐕", Horse:"🐴", Elephant:"🐘", Butterfly:"🦋", Chicken:"🐔", Cat:"🐱", Cow:"🐄", Sheep:"🐑", Squirrel:"🐿️", Spider:"🕷️" };

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

  // Scanner
  const [image, setImage]           = useState(null);
  const [dragOver, setDragOver]     = useState(false);
  const [result, setResult]         = useState(null);
  const [ecoInfo, setEcoInfo]       = useState(null);
  const [funFact, setFunFact]       = useState(null);
  const [scanning, setScanning]     = useState(false);
  const [loadingEco, setLoadingEco] = useState(false);
  const [camActive, setCamActive]   = useState(false);
  const videoRef   = useRef(null);
  const canvasRef  = useRef(null);
  const fileRef    = useRef(null);

  // Encyclopedia
  const [selAnimal, setSelAnimal]       = useState(null);
  const [encData, setEncData]           = useState({});
  const [loadingEnc, setLoadingEnc]     = useState(null);

  // Chat
  const chatBottom = useRef(null);
  const [msgs, setMsgs]         = useState([{ role:"bot", text:"Hi! I'm WildLens AI. Upload an animal photo or ask me anything about wildlife.", ts: new Date() }]);
  const [input, setInput]       = useState("");
  const [chatBusy, setChatBusy] = useState(false);

  // History
  const [history, setHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem("fi_hist") || "[]"); } catch { return []; }
  });

  useEffect(() => { localStorage.setItem("fi_hist", JSON.stringify(history)); }, [history]);
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
      setImage(URL.createObjectURL(f));
      process(f); stopCam();
    }, "image/jpeg");
  };

  // ── File handlers ─────────────────────────────────────
  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f?.type.startsWith("image/")) { setImage(URL.createObjectURL(f)); process(f); }
  };
  const onFileChange = (e) => {
    const f = e.target.files?.[0];
    if (f) { setImage(URL.createObjectURL(f)); process(f); }
  };

  // ── Classify ──────────────────────────────────────────
  const process = async (file) => {
    setScanning(true); setResult(null); setEcoInfo(null); setFunFact(null);
    const fd = new FormData(); fd.append("file", file);
    try {
      const r = await fetch(`${HOST}/api/classify`, { method:"POST", body:fd });
      if (!r.ok) throw new Error();
      const d = await r.json();
      setResult(d);
      setHistory(prev => [{ id:Date.now(), species:d.species, confidence:d.confidence, ts:new Date().toISOString(), img:URL.createObjectURL(file) }, ...prev].slice(0, 60));
      setMsgs(prev => [...prev, { role:"bot", text:`Detected **${d.species}** with ${d.confidence}% confidence. Ask me anything about it!`, ts:new Date() }]);
      fetchEco(d.species);
      fetchFact(d.species);
    } catch { alert("Classification failed. Is the backend server running?"); }
    finally { setScanning(false); }
  };

  const fetchEco = async (sp) => {
    setLoadingEco(true);
    const fd = new FormData(); fd.append("species", sp);
    try {
      const r = await fetch(`${HOST}/api/info`, { method:"POST", body:fd });
      setEcoInfo(await r.json());
    } catch {} finally { setLoadingEco(false); }
  };

  const fetchFact = async (sp) => {
    const fd = new FormData();
    fd.append("message", `Share one surprising, little-known fun fact about ${sp} in 2 sentences. Make it wow the reader.`);
    fd.append("species_context", sp);
    fd.append("chat_history", "[]");
    try {
      const r = await fetch(`${HOST}/api/chat`, { method:"POST", body:fd });
      const d = await r.json();
      setFunFact(d.response);
    } catch {}
  };

  // ── Encyclopedia ──────────────────────────────────────
  const openAnimal = async (a) => {
    setSelAnimal(a);
    if (encData[a]) return;
    setLoadingEnc(a);
    const fd = new FormData(); fd.append("species", a);
    try {
      const r = await fetch(`${HOST}/api/info`, { method:"POST", body:fd });
      const json = await r.json();
      setEncData(prev => ({ ...prev, [a]: json }));
    } catch {} finally { setLoadingEnc(null); }
  };

  // ── Chat ──────────────────────────────────────────────
  const sendMsg = async () => {
    if (!input.trim() || chatBusy) return;
    const text = input; setInput(""); setChatBusy(true);
    setMsgs(prev => [...prev, { role:"user", text, ts:new Date() }]);
    const fd = new FormData();
    fd.append("message", text);
    fd.append("species_context", result?.species || "");
    fd.append("chat_history", JSON.stringify(msgs.slice(-8)));
    try {
      const r = await fetch(`${HOST}/api/chat`, { method:"POST", body:fd });
      const d = await r.json();
      setMsgs(prev => [...prev, { role:"bot", text:d.response, ts:new Date() }]);
    } catch {
      setMsgs(prev => [...prev, { role:"bot", text:"Connection error. Is the server running?", ts:new Date() }]);
    } finally { setChatBusy(false); }
  };

  // ── Stats ─────────────────────────────────────────────
  const counts = history.reduce((a, s) => { a[s.species] = (a[s.species]||0)+1; return a; }, {});
  const topSp   = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,5);
  const avgConf = history.length ? (history.reduce((a,s)=>a+s.confidence,0)/history.length).toFixed(1) : "—";

  const reset = () => { setImage(null); setResult(null); setEcoInfo(null); setFunFact(null); if(fileRef.current) fileRef.current.value=""; };

  const NAV = [
    { id:"scanner",     label:"Species Scanner",  icon:<Microscope size={17}/> },
    { id:"encyclopedia",label:"Encyclopedia",      icon:<BookOpen size={17}/> },
    { id:"chat",        label:"AI Assistant",      icon:<MessageSquare size={17}/> },
    { id:"history",     label:"Scan History",      icon:<BarChart2 size={17}/> },
  ];

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
            <span className="pill"><Star size={11}/>{avgConf}% avg</span>
          </div>
          <p className="footer-note">MobileNetV3 + Gemini 2.0 Flash</p>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="main">
        {/* Topbar */}
        <header className="topbar">
          <div>
            <h1 className="topbar-title">{NAV.find(n=>n.id===tab)?.label}</h1>
            <span className="topbar-sub">
              {tab==="scanner"      && "Upload or capture an animal photo to classify it instantly"}
              {tab==="encyclopedia" && "Explore all 10 species in our Animals-10 dataset"}
              {tab==="chat"         && "Converse with our ecology-specialized Gemini AI"}
              {tab==="history"      && `${history.length} scans recorded in this session`}
            </span>
          </div>
          <div className="status-row"><div className="dot"/><span className="status-txt">Online</span></div>
        </header>

        <div className="body">

          {/* ════ SCANNER ════ */}
          {tab==="scanner" && (
            <div className="scanner-grid">
              {/* Left */}
              <div className="scanner-left">
                {/* Drop zone */}
                {!result && !scanning && !camActive && (
                  <div
                    className={`dropzone ${dragOver?"dragover":""}`}
                    onDragOver={e=>{e.preventDefault();setDragOver(true)}}
                    onDragLeave={()=>setDragOver(false)}
                    onDrop={onDrop}
                    onClick={()=>fileRef.current?.click()}
                  >
                    {image
                      ? <img src={image} alt="preview" className="drop-preview"/>
                      : <div className="drop-inner">
                          <div className="drop-ring"><UploadCloud size={32} strokeWidth={1.5}/></div>
                          <h3>Drop an animal photo here</h3>
                          <p>or click to browse files</p>
                          <span className="drop-hint">JPG · PNG · WEBP</span>
                        </div>
                    }
                    <input ref={fileRef} type="file" accept="image/*" onChange={onFileChange} hidden/>
                  </div>
                )}

                {/* Webcam */}
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

                {/* Scanning animation */}
                {scanning && (
                  <div className="scan-card">
                    <div className="scan-rings">
                      <div className="ring"/><div className="ring r2"/><div className="ring r3"/>
                      <Microscope size={28} strokeWidth={1.5}/>
                    </div>
                    <h3>Analyzing with CNN…</h3>
                    <p>Running MobileNetV3 inference</p>
                  </div>
                )}

                {/* Result */}
                {result && !scanning && (
                  <div className="result-wrap">
                    <div className="result-img-box">
                      <img src={image} alt="scanned" className="result-img"/>
                      <button className="rescan" onClick={reset}><RefreshCw size={13}/>New Scan</button>
                    </div>
                    <div className="result-card">
                      <div className="result-top">
                        <span className="result-emoji">{EMOJI[result.species]||"🐾"}</span>
                        <div>
                          <div className="result-lbl">Detected Species</div>
                          <div className="result-name">{result.species}</div>
                        </div>
                      </div>
                      <div>
                        <div className="conf-row">
                          <span>Match Confidence</span>
                          <span style={{color:confidenceColor(result.confidence),fontWeight:700}}>{result.confidence}%</span>
                        </div>
                        <div className="conf-track">
                          <div className="conf-fill" style={{width:`${result.confidence}%`,background:confidenceColor(result.confidence)}}/>
                        </div>
                      </div>
                      <div className="latency-row">
                        {[["Prep",result.latency.preprocessing],["CNN",result.latency.inference],["Total",result.latency.total]].map(([l,v])=>(
                          <span key={l} className="latency-chip"><Clock size={10}/>{l}: {v}ms</span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Webcam trigger */}
                {!result && !scanning && !camActive && (
                  <button className="btn-ghost cam-trigger" onClick={startCam}>
                    <Camera size={15}/> Use Webcam Instead
                  </button>
                )}
              </div>

              {/* Right panel */}
              <div className="scanner-right">
                {!result && !scanning && (
                  <div className="empty-state">
                    <div className="empty-icon">🌿</div>
                    <h3>Ready to Identify</h3>
                    <p>Supports 10 animal classes. Upload any photo to get an instant classification, ecological profile, and AI-generated insights.</p>
                    <div className="chip-grid">
                      {ANIMALS.map(a=><span key={a} className="chip">{EMOJI[a]} {a}</span>)}
                    </div>
                  </div>
                )}

                {funFact && (
                  <div className="card fact-card">
                    <div className="card-head"><Star size={14}/><span>Did you know?</span></div>
                    <p>{funFact}</p>
                  </div>
                )}

                {loadingEco && (
                  <div className="card loading-row"><Loader2 size={18} className="spin"/> Loading ecological data…</div>
                )}

                {ecoInfo && !loadingEco && (
                  <>
                    <div className="card">
                      <div className="card-head"><Globe size={14}/><span>Habitat & Distribution</span></div>
                      <div className="kv"><span className="kk">Climate</span><span className="kv-val">{ecoInfo.habitat?.climate}</span></div>
                      <div className="kv"><span className="kk">Range</span><span className="kv-val">{ecoInfo.habitat?.distribution}</span></div>
                      <p className="kdesc">{ecoInfo.habitat?.description}</p>
                    </div>

                    <div className="card">
                      <div className="card-head"><ArrowRight size={14}/><span>Food Chain — {ecoInfo.food_chain?.trophic_level}</span></div>
                      <div className="chain">
                        {ecoInfo.food_chain?.chain?.map((l,i,arr)=>(
                          <React.Fragment key={i}>
                            <span className={`cnode ${l===result?.species?"cnode-active":""}`}>{l}</span>
                            {i<arr.length-1 && <span className="carrow">→</span>}
                          </React.Fragment>
                        ))}
                      </div>
                      <p className="kdesc">{ecoInfo.food_chain?.description}</p>
                    </div>

                    <div className="card">
                      <div className="card-head"><Leaf size={14}/><span>IUCN Conservation Status</span></div>
                      <span className="iucn-badge" style={{borderColor:statusColor(ecoInfo.conservation?.status),color:statusColor(ecoInfo.conservation?.status)}}>
                        {ecoInfo.conservation?.status}
                      </span>
                      <div className="kv" style={{marginTop:10}}><span className="kk">Threats</span><span className="kv-val">{ecoInfo.conservation?.threats}</span></div>
                      <div className="kv"><span className="kk">Actions</span><span className="kv-val">{ecoInfo.conservation?.actions}</span></div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* ════ ENCYCLOPEDIA ════ */}
          {tab==="encyclopedia" && (
            <div className="enc-layout">
              <div className="animal-grid">
                {ANIMALS.map(a=>(
                  <button key={a} className={`acard ${selAnimal===a?"acard-sel":""}`} onClick={()=>openAnimal(a)}>
                    <span className="acard-emoji">{EMOJI[a]}</span>
                    <span className="acard-name">{a}</span>
                    {loadingEnc===a && <Loader2 size={13} className="spin acard-loader"/>}
                  </button>
                ))}
              </div>

              {selAnimal && (
                <div className="enc-detail">
                  <div className="enc-header">
                    <span className="enc-emoji">{EMOJI[selAnimal]}</span>
                    <div>
                      <h2 className="enc-title">{selAnimal}</h2>
                      <p className="enc-sub">Ecological Profile</p>
                    </div>
                  </div>

                  {loadingEnc===selAnimal && <div className="card loading-row"><Loader2 size={18} className="spin"/>Fetching data…</div>}

                  {encData[selAnimal] && (
                    <div className="enc-body">
                      <div className="card">
                        <div className="card-head"><Globe size={14}/><span>Habitat</span></div>
                        <div className="kv"><span className="kk">Climate</span><span className="kv-val">{encData[selAnimal].habitat?.climate}</span></div>
                        <div className="kv"><span className="kk">Range</span><span className="kv-val">{encData[selAnimal].habitat?.distribution}</span></div>
                        <p className="kdesc">{encData[selAnimal].habitat?.description}</p>
                      </div>
                      <div className="card">
                        <div className="card-head"><ArrowRight size={14}/><span>Food Chain</span></div>
                        <div className="chain">
                          {encData[selAnimal].food_chain?.chain?.map((l,i,arr)=>(
                            <React.Fragment key={i}>
                              <span className={`cnode ${l===selAnimal?"cnode-active":""}`}>{l}</span>
                              {i<arr.length-1 && <span className="carrow">→</span>}
                            </React.Fragment>
                          ))}
                        </div>
                        <p className="kdesc">{encData[selAnimal].food_chain?.description}</p>
                      </div>
                      <div className="card">
                        <div className="card-head"><Shield size={14}/><span>Conservation</span></div>
                        <span className="iucn-badge" style={{borderColor:statusColor(encData[selAnimal].conservation?.status),color:statusColor(encData[selAnimal].conservation?.status)}}>
                          {encData[selAnimal].conservation?.status}
                        </span>
                        <div className="kv" style={{marginTop:10}}><span className="kk">Threats</span><span className="kv-val">{encData[selAnimal].conservation?.threats}</span></div>
                        <p className="kdesc" style={{marginTop:6}}>{encData[selAnimal].conservation?.actions}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {!selAnimal && (
                <div className="enc-prompt">
                  <div className="empty-icon">📖</div>
                  <h3>Select an animal above</h3>
                  <p>Click any species card to load its full ecological profile, food chain, and IUCN conservation status powered by Gemini AI.</p>
                </div>
              )}
            </div>
          )}

          {/* ════ CHAT ════ */}
          {tab==="chat" && (
            <div className="chat-layout">
              {result && (
                <div className="ctx-banner"><Info size={13}/>Context: <strong>{result.species}</strong> — ask anything about this animal</div>
              )}
              <div className="messages">
                {msgs.map((m,i)=>(
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
                  placeholder="Ask about behavior, habitat, diet, conservation…"
                  value={input}
                  onChange={e=>setInput(e.target.value)}
                  onKeyDown={e=>e.key==="Enter"&&sendMsg()}
                />
                <button className="send-btn" onClick={sendMsg} disabled={!input.trim()||chatBusy}>
                  <Send size={17}/>
                </button>
              </div>
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
                      [history.length,       "Total Scans"],
                      [Object.keys(counts).length, "Species Found"],
                      [`${avgConf}%`,         "Avg Confidence"],
                      [topSp[0]?.[0]||"—",    "Top Species"],
                    ].map(([v,l])=>(
                      <div key={l} className="stat-card">
                        <div className="stat-val">{v}</div>
                        <div className="stat-lbl">{l}</div>
                      </div>
                    ))}
                  </div>

                  {topSp.length>0 && (
                    <div className="card">
                      <div className="card-head"><TrendingUp size={14}/><span>Species Frequency</span></div>
                      {topSp.map(([sp,ct])=>(
                        <div key={sp} className="freq-row">
                          <span className="freq-name">{EMOJI[sp]} {sp}</span>
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
                      {history.map(s=>(
                        <div key={s.id} className="hist-item">
                          <img src={s.img} alt={s.species} className="hist-thumb"/>
                          <div className="hist-info">
                            <div className="hist-species">{EMOJI[s.species]} {s.species}</div>
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
    </div>
  );
}
