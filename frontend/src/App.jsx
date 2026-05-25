import { useState, useEffect, useRef } from "react";

const API = "http://localhost:8765/api/v1";
const tok = () => localStorage.getItem("wo_token") || "";

async function ap(method, path, body, isFile) {
  const headers = {
    ...(isFile ? {} : { "Content-Type": "application/json" }),
    ...(tok() ? { Authorization: `Bearer ${tok()}` } : {}),
  };
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: isFile ? body : body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) { localStorage.removeItem("wo_token"); window.location.reload(); }
  if (res.status === 204) return null;
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

const fmtCr = v => {
  if (!v && v !== 0) return "—";
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  return `₹${Math.round(v).toLocaleString("en-IN")}`;
};
const pct = v => v == null ? "—" : `${Number(v).toFixed(1)}%`;
const clr = v => v >= 0 ? "#16a34a" : "#dc2626";
const scoreClr = s => s >= 70 ? "#16a34a" : s >= 50 ? "#d97706" : "#dc2626";
const CC = { equity: "#2563eb", debt: "#16a34a", hybrid: "#d97706", cash: "#6b7280", alternate: "#7c3aed" };
const SC = ["#2563eb", "#16a34a", "#d97706", "#7c3aed", "#dc2626", "#0891b2", "#65a30d", "#c026d3"];

function Ring({ score = 0, grade = "—", size = 64, label = "" }) {
  const R = size / 2 - 5, cx = size / 2, cy = size / 2, C = 2 * Math.PI * R, color = scoreClr(score);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={R} fill="none" stroke="#e5e7eb" strokeWidth={5} />
        <circle cx={cx} cy={cy} r={R} fill="none" stroke={color} strokeWidth={5}
          strokeDasharray={`${C * (score / 100)} ${C * (1 - score / 100)}`}
          strokeDashoffset={C / 4} strokeLinecap="round" />
        <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="central"
          fontSize={12} fontWeight={600} fill="#111">{grade}</text>
      </svg>
      {label && <div style={{ fontSize: 10, color: "#6b7280", textAlign: "center" }}>{label}</div>}
    </div>
  );
}

function Bar({ data = {}, max = 8 }) {
  const entries = Object.entries(data).filter(([, v]) => v > 0).slice(0, max);
  const mx = Math.max(...entries.map(([, v]) => v), 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
      {entries.map(([label, val], i) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 120, fontSize: 11, color: "#374151", textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flexShrink: 0 }}>{label}</div>
          <div style={{ flex: 1, height: 6, background: "#f3f4f6", borderRadius: 99 }}>
            <div style={{ width: `${(val / mx) * 100}%`, height: "100%", background: SC[i % SC.length], borderRadius: 99 }} />
          </div>
          <div style={{ width: 36, fontSize: 11, color: "#6b7280", textAlign: "right" }}>{pct(val)}</div>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [authView, setAuthView] = useState("login");
  const [authError, setAuthError] = useState("");
  const [view, setView] = useState("portfolios");
  const [portfolios, setPortfolios] = useState([]);
  const [sel, setSel] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [insightLoading, setInsightLoading] = useState(false);
  const [stressDetail, setStressDetail] = useState(null);
  const [search, setSearch] = useState("");
  const fileRef = useRef();

  useEffect(() => {
    if (tok()) ap("GET", "/auth/me").then(u => setUser(u)).catch(() => {});
  }, []);

  useEffect(() => {
    if (user) ap("GET", "/portfolios/").then(setPortfolios).catch(() => {});
  }, [user]);

  const handleAuth = async e => {
    e.preventDefault();
    setAuthError("");
    const body = Object.fromEntries(new FormData(e.target));
    try {
      const r = await ap("POST", authView === "login" ? "/auth/login" : "/auth/signup", body);
      localStorage.setItem("wo_token", r.access_token);
      setUser(r.user);
      setView("portfolios");
    } catch (err) { setAuthError(err.message); }
  };

  const handleUpload = async file => {
    if (!file) return;
    setUploading(true);
    setUploadStatus("Uploading…");
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await ap("POST", "/upload/", fd, true);
      setUploadStatus("Processing…");
      const poll = async () => {
        const s = await ap("GET", `/upload/status/${r.portfolio_id}`);
        const msgs = { parsing: "Parsing document…", normalizing: "Normalizing…", analyzing: "Running analytics…" };
        setUploadStatus(msgs[s.status] || s.status);
        if (s.status === "ready") {
          ap("GET", "/portfolios/").then(setPortfolios);
          setUploading(false);
          setUploadStatus("");
          loadPortfolio(r.portfolio_id);
        } else if (s.status === "error") {
          alert("Error: " + s.error);
          setUploading(false);
          setUploadStatus("");
        } else { setTimeout(poll, 1500); }
      };
      poll();
    } catch (e) { alert(e.message); setUploading(false); setUploadStatus(""); }
  };

  const loadPortfolio = async id => {
    try {
      const [p, a, h, ins] = await Promise.allSettled([
        ap("GET", `/portfolios/${id}`),
        ap("GET", `/analytics/${id}`),
        ap("GET", `/portfolios/${id}/holdings`),
        ap("GET", `/insights/${id}`),
      ]);
      setSel({
        portfolio: p.value,
        analytics: a.value,
        holdings: h.value?.holdings || [],
        insights: ins.value?.portfolio_summary ? ins.value : null,
      });
      setView("dashboard");
      setStressDetail(null);
    } catch (e) { alert("Load failed: " + e.message); }
  };

  const generateInsights = async () => {
    if (!sel?.portfolio) return;
    setInsightLoading(true);
    try {
      const r = await ap("POST", `/insights/${sel.portfolio.id}/generate`);
      setSel(s => ({ ...s, insights: r }));
    } catch (e) { alert("AI failed: " + e.message); }
    finally { setInsightLoading(false); }
  };

  const A = sel?.analytics || {};
  const byClass = A.asset_allocation?.by_class || {};
  const scenarios = A.stress_test?.scenarios || [];
  const warnings = A.warnings || [];

  const navItems = [
    { id: "portfolios", icon: "⊞", label: "Portfolios" },
    { id: "upload", icon: "↑", label: "Upload" },
    { id: "dashboard", icon: "▦", label: "Dashboard", needsSel: true },
    { id: "holdings", icon: "≡", label: "Holdings", needsSel: true },
    { id: "analytics", icon: "◎", label: "Analytics", needsSel: true },
    { id: "stress", icon: "⚡", label: "Stress Test", needsSel: true },
    { id: "insights", icon: "✦", label: "AI Insights", needsSel: true },
  ];

  if (!user) return (
    <div style={{ fontFamily: "system-ui,sans-serif", minHeight: "100vh", background: "#f9fafb", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 380, padding: 40, background: "#fff", borderRadius: 16, border: "1px solid #e5e7eb", boxShadow: "0 4px 24px rgba(0,0,0,0.08)" }}>
        <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>WealthOS AI</div>
        <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 28 }}>Portfolio intelligence for wealth advisors</div>
        {authError && <div style={{ padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, fontSize: 12, color: "#dc2626", marginBottom: 14 }}>{authError}</div>}
        <form onSubmit={handleAuth} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {authView === "signup" && (
            <>
              <input name="full_name" placeholder="Full name" required style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #d1d5db", fontSize: 13, outline: "none" }} />
              <input name="firm_name" placeholder="Firm name (optional)" style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #d1d5db", fontSize: 13, outline: "none" }} />
            </>
          )}
          <input name="email" type="email" placeholder="Email" required style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #d1d5db", fontSize: 13, outline: "none" }} />
          <input name="password" type="password" placeholder="Password" required minLength={6} style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #d1d5db", fontSize: 13, outline: "none" }} />
          <button type="submit" style={{ padding: "11px", borderRadius: 8, border: "none", background: "#111827", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            {authView === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        <div style={{ marginTop: 18, textAlign: "center", fontSize: 12, color: "#6b7280" }}>
          {authView === "login" ? "New here? " : "Have an account? "}
          <span style={{ color: "#2563eb", cursor: "pointer" }} onClick={() => { setAuthView(v => v === "login" ? "signup" : "login"); setAuthError(""); }}>
            {authView === "login" ? "Create account" : "Sign in"}
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <div style={{ fontFamily: "system-ui,sans-serif", minHeight: "100vh", background: "#f9fafb", color: "#111827" }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } } * { box-sizing: border-box; }`}</style>

      {/* Topbar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 24px", background: "#fff", borderBottom: "1px solid #e5e7eb", position: "sticky", top: 0, zIndex: 100 }}>
        <div style={{ fontWeight: 700, fontSize: 16, cursor: "pointer" }} onClick={() => setView("portfolios")}>WealthOS AI</div>
        {sel?.portfolio && <div style={{ fontSize: 12, color: "#6b7280", padding: "4px 12px", background: "#f3f4f6", borderRadius: 20 }}>{sel.portfolio.name}</div>}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>{user.full_name}</span>
          <button onClick={() => { localStorage.removeItem("wo_token"); setUser(null); setSel(null); setView("portfolios"); }}
            style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#fff", fontSize: 12, cursor: "pointer" }}>Sign out</button>
        </div>
      </div>

      <div style={{ display: "flex", minHeight: "calc(100vh - 53px)" }}>
        {/* Sidebar */}
        <nav style={{ width: 200, background: "#fff", borderRight: "1px solid #e5e7eb", padding: "16px 8px", flexShrink: 0, display: "flex", flexDirection: "column" }}>
          {navItems.map(({ id, icon, label, needsSel }) => (
            <div key={id} onClick={() => needsSel && !sel ? null : setView(id)}
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 14px", borderRadius: 8, fontSize: 13, cursor: needsSel && !sel ? "default" : "pointer", marginBottom: 2, background: view === id ? "#eff6ff" : "transparent", color: view === id ? "#2563eb" : "#374151", fontWeight: view === id ? 600 : 400, opacity: needsSel && !sel ? 0.35 : 1 }}>
              <span style={{ width: 16, textAlign: "center" }}>{icon}</span>{label}
            </div>
          ))}
          {sel && (
            <div style={{ marginTop: "auto", paddingTop: 16, borderTop: "1px solid #e5e7eb" }}>
              <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 10, paddingLeft: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>Health</div>
              <div style={{ display: "flex", justifyContent: "space-around" }}>
                <Ring score={A.diversification?.score || 0} grade={A.diversification?.grade || "—"} size={56} label="Diversity" />
                <Ring score={A.stress_test?.summary?.resilience_score || 0} grade={A.stress_test?.summary?.resilience_grade || "—"} size={56} label="Resilience" />
              </div>
            </div>
          )}
        </nav>

        <main style={{ flex: 1, padding: 28, overflow: "auto", minWidth: 0 }}>

          {/* PORTFOLIOS */}
          {view === "portfolios" && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
                <div>
                  <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 2 }}>Portfolios</h1>
                  <div style={{ fontSize: 13, color: "#6b7280" }}>{user.firm_name || "Advisor dashboard"}</div>
                </div>
                <button onClick={() => setView("upload")} style={{ padding: "9px 18px", borderRadius: 8, border: "none", background: "#111827", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>+ Upload New</button>
              </div>
              {portfolios.length === 0
                ? <div style={{ textAlign: "center", padding: "80px 20px", color: "#6b7280" }}>
                    <div style={{ fontSize: 40, marginBottom: 16, opacity: .3 }}>◻</div>
                    <div style={{ fontSize: 15, marginBottom: 16 }}>No portfolios yet</div>
                    <button onClick={() => setView("upload")} style={{ padding: "9px 18px", borderRadius: 8, border: "none", background: "#111827", color: "#fff", fontSize: 13, cursor: "pointer" }}>Upload first portfolio</button>
                  </div>
                : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))", gap: 14 }}>
                    {portfolios.map(p => (
                      <div key={p.id} onClick={() => loadPortfolio(p.id)}
                        style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", cursor: "pointer" }}
                        onMouseEnter={e => e.currentTarget.style.borderColor = "#2563eb"}
                        onMouseLeave={e => e.currentTarget.style.borderColor = "#e5e7eb"}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                          <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 180 }}>{p.name}</div>
                          <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 600, background: p.status === "ready" ? "#dcfce7" : "#fef9c3", color: p.status === "ready" ? "#15803d" : "#854d0e" }}>{p.status}</span>
                        </div>
                        <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{fmtCr(p.total_value)}</div>
                        <div style={{ fontSize: 12, color: "#6b7280" }}>{p.holding_count} holdings · {new Date(p.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</div>
                      </div>
                    ))}
                  </div>
              }
            </div>
          )}

          {/* UPLOAD */}
          {view === "upload" && (
            <div style={{ maxWidth: 520, margin: "40px auto" }}>
              <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 6 }}>Upload Portfolio</h1>
              <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 24, lineHeight: 1.6 }}>CAS PDF (CAMS / KFin), Excel (.xlsx), or CSV. Max 50 MB.</p>
              <div onClick={() => !uploading && fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); e.currentTarget.style.borderColor = "#2563eb"; }}
                onDragLeave={e => { e.currentTarget.style.borderColor = "#d1d5db"; }}
                onDrop={e => { e.preventDefault(); e.currentTarget.style.borderColor = "#d1d5db"; handleUpload(e.dataTransfer.files[0]); }}
                style={{ padding: 48, border: "2px dashed #d1d5db", borderRadius: 16, cursor: "pointer", background: "#fff", textAlign: "center" }}>
                {uploading
                  ? <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
                      <div style={{ width: 32, height: 32, border: "3px solid #e5e7eb", borderTop: "3px solid #111827", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
                      <div style={{ fontSize: 14, fontWeight: 500 }}>{uploadStatus}</div>
                    </div>
                  : <>
                      <div style={{ fontSize: 36, marginBottom: 12, opacity: .4 }}>⬆</div>
                      <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 6 }}>Drop file here or click to browse</div>
                      <div style={{ fontSize: 13, color: "#6b7280" }}>PDF · XLSX · CSV</div>
                    </>
                }
              </div>
              <input ref={fileRef} type="file" accept=".pdf,.xlsx,.xls,.csv" style={{ display: "none" }} onChange={e => handleUpload(e.target.files[0])} />
            </div>
          )}

          {/* DASHBOARD */}
          {view === "dashboard" && sel && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
                <div>
                  <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 2 }}>{sel.portfolio.name}</h1>
                  <div style={{ fontSize: 13, color: "#6b7280" }}>{sel.holdings.length} holdings</div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => setView("stress")} style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#fff", fontSize: 13, cursor: "pointer" }}>⚡ Stress Test</button>
                  <button onClick={() => setView("insights")} style={{ padding: "8px 14px", borderRadius: 8, border: "none", background: "#111827", color: "#fff", fontSize: 13, cursor: "pointer" }}>✦ AI Insights</button>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 20 }}>
                {[
                  { l: "Total AUM", v: fmtCr(A.total_value_inr), s: `${A.holding_count} holdings` },
                  { l: "Diversification", v: `${A.diversification?.score || "—"}/100`, s: `Grade ${A.diversification?.grade || "—"}` },
                  { l: "Volatility", v: `${A.volatility?.estimated_annual_volatility_pct || "—"}%`, s: A.volatility?.volatility_band || "" },
                  { l: "Resilience", v: `${A.stress_test?.summary?.resilience_score || "—"}/100`, s: `Grade ${A.stress_test?.summary?.resilience_grade || "—"}` },
                ].map(({ l, v, s }) => (
                  <div key={l} style={{ padding: 18, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                    <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>{l}</div>
                    <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{v}</div>
                    <div style={{ fontSize: 12, color: "#6b7280" }}>{s}</div>
                  </div>
                ))}
              </div>

              {warnings.length > 0 && (
                <div style={{ marginBottom: 20, display: "flex", flexDirection: "column", gap: 8 }}>
                  {warnings.map((w, i) => (
                    <div key={i} style={{ display: "flex", gap: 8, padding: "10px 14px", background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 10, fontSize: 13, color: "#92400e" }}>
                      <span>⚠</span>{w}
                    </div>
                  ))}
                </div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
                <div style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Asset Allocation</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {Object.entries(byClass).map(([k, v]) => (
                      <div key={k} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: CC[k] || "#888", flexShrink: 0 }} />
                        <span style={{ flex: 1, fontSize: 12, textTransform: "capitalize", color: "#374151" }}>{k}</span>
                        <div style={{ width: 80, height: 5, background: "#f3f4f6", borderRadius: 99 }}>
                          <div style={{ width: `${v}%`, height: "100%", background: CC[k] || "#888", borderRadius: 99 }} />
                        </div>
                        <span style={{ fontSize: 12, fontWeight: 600, width: 40, textAlign: "right" }}>{pct(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Sector Exposure</div>
                  <Bar data={A.sector_exposure?.by_sector || {}} max={7} />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
                <div style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Concentration</div>
                  {[{ l: "Top 3", v: A.concentration?.top3_weight_pct }, { l: "Top 5", v: A.concentration?.top5_weight_pct }, { l: "Top 10", v: A.concentration?.top10_weight_pct }].map(({ l, v }) => (
                    <div key={l} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                      <span style={{ fontSize: 11, color: "#6b7280", width: 36, flexShrink: 0 }}>{l}</span>
                      <div style={{ flex: 1, height: 6, background: "#f3f4f6", borderRadius: 99 }}>
                        <div style={{ width: `${v || 0}%`, height: "100%", background: (v || 0) > 60 ? "#dc2626" : (v || 0) > 40 ? "#d97706" : "#16a34a", borderRadius: 99 }} />
                      </div>
                      <span style={{ fontSize: 11, fontWeight: 600, width: 36, textAlign: "right" }}>{pct(v)}</span>
                    </div>
                  ))}
                  <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 8 }}>HHI {A.concentration?.hhi} · {(A.concentration?.hhi_interpretation || "").replace(/_/g, " ")}</div>
                </div>
                <div style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Liquidity</div>
                  {[{ l: "Liquid", v: A.liquidity_profile?.liquid_pct, c: "#16a34a" }, { l: "Semi-liquid", v: A.liquidity_profile?.semi_liquid_pct, c: "#d97706" }, { l: "Illiquid", v: A.liquidity_profile?.illiquid_pct, c: "#dc2626" }].map(({ l, v, c }) => (
                    <div key={l} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: c, flexShrink: 0 }} />
                      <span style={{ flex: 1, fontSize: 12, color: "#374151" }}>{l}</span>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{pct(v)}</span>
                    </div>
                  ))}
                </div>
                <div style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Worst Stress</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: "#dc2626", marginBottom: 4 }}>{A.stress_test?.summary?.worst_impact_pct}%</div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 10 }}>{(A.stress_test?.summary?.worst_scenario || "").replace(/_/g, " ")}</div>
                  <button onClick={() => setView("stress")} style={{ width: "100%", padding: "7px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#fff", fontSize: 12, cursor: "pointer" }}>View all 8 →</button>
                </div>
              </div>
            </div>
          )}

          {/* HOLDINGS */}
          {view === "holdings" && sel && (
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
                <h1 style={{ fontSize: 22, fontWeight: 700 }}>Holdings — {sel.holdings.length}</h1>
                <input placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)}
                  style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 13, width: 200, outline: "none" }} />
              </div>
              <div style={{ background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", overflow: "hidden" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "#f9fafb" }}>
                      {["#", "Instrument", "Class", "Sector", "Value", "Weight", "Risk"].map(h => (
                        <th key={h} style={{ padding: "10px 14px", fontSize: 11, fontWeight: 600, color: "#6b7280", textAlign: "left", borderBottom: "1px solid #e5e7eb", textTransform: "uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...sel.holdings].filter(h => h.instrument_name.toLowerCase().includes(search.toLowerCase())).map((h, i) => (
                      <tr key={h.id} style={{ borderBottom: "1px solid #f3f4f6" }}
                        onMouseEnter={e => e.currentTarget.style.background = "#f9fafb"}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                        <td style={{ padding: "10px 14px", fontSize: 12, color: "#9ca3af" }}>{i + 1}</td>
                        <td style={{ padding: "10px 14px" }}>
                          <div style={{ fontSize: 13, fontWeight: 500 }}>{h.instrument_name}</div>
                          {h.isin && <div style={{ fontSize: 10, color: "#9ca3af", fontFamily: "monospace" }}>{h.isin}</div>}
                        </td>
                        <td style={{ padding: "10px 14px" }}>
                          <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 11, background: `${CC[h.asset_class] || "#888"}20`, color: CC[h.asset_class] || "#888", textTransform: "capitalize" }}>{h.asset_class}</span>
                        </td>
                        <td style={{ padding: "10px 14px", fontSize: 12, color: "#6b7280" }}>{h.sector || "—"}</td>
                        <td style={{ padding: "10px 14px", fontSize: 12 }}>{fmtCr(h.current_value)}</td>
                        <td style={{ padding: "10px 14px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <div style={{ width: 44, height: 4, background: "#f3f4f6", borderRadius: 99 }}>
                              <div style={{ width: `${Math.min((h.allocation_percent || 0) / 20 * 100, 100)}%`, height: "100%", background: "#2563eb", borderRadius: 99 }} />
                            </div>
                            <span style={{ fontSize: 12, fontWeight: 500 }}>{pct(h.allocation_percent)}</span>
                          </div>
                        </td>
                        <td style={{ padding: "10px 14px", fontSize: 12, fontWeight: 600, color: (h.risk_score || 0) > 7 ? "#dc2626" : (h.risk_score || 0) > 5 ? "#d97706" : "#16a34a" }}>
                          {h.risk_score ? `${h.risk_score}/10` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ANALYTICS */}
          {view === "analytics" && sel && (
            <div>
              <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 20 }}>Analytics</h1>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
                <div style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Diversification Score</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 16 }}>
                    <Ring score={A.diversification?.score || 0} grade={A.diversification?.grade || "—"} size={80} />
                    <div>
                      <div style={{ fontSize: 28, fontWeight: 700 }}>{A.diversification?.score}/100</div>
                      <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>{A.diversification?.asset_class_count} asset classes · {A.diversification?.sector_count} sectors</div>
                    </div>
                  </div>
                  <Bar data={Object.fromEntries(Object.entries(A.market_cap_exposure?.by_cap_pct_of_portfolio || {}).filter(([, v]) => v > 0).map(([k, v]) => [k.replace(/_/g, " "), v]))} max={4} />
                </div>
                <div style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Fund Overlap</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: (A.fund_overlap?.total_overlap_pct_of_portfolio || 0) > 10 ? "#d97706" : "#16a34a", marginBottom: 4 }}>
                    {A.fund_overlap?.total_overlap_pct_of_portfolio || 0}%
                  </div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>Estimated portfolio overlap</div>
                  {(A.fund_overlap?.known_pair_overlaps || []).map((p, i) => (
                    <div key={i} style={{ padding: "10px 12px", background: "#f9fafb", borderRadius: 8, marginBottom: 8 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 2 }}>{p.fund_a} ↔ {p.fund_b}</div>
                      <div style={{ fontSize: 12, color: "#d97706" }}>{p.overlap_pct}% common holdings</div>
                    </div>
                  ))}
                  {!(A.fund_overlap?.known_pair_overlaps?.length) && <div style={{ fontSize: 13, color: "#6b7280" }}>No overlaps detected</div>}
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Volatility Estimate</div>
                  <div style={{ fontSize: 36, fontWeight: 700, marginBottom: 4 }}>{A.volatility?.estimated_annual_volatility_pct}%</div>
                  <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>Annual estimate · {A.volatility?.volatility_band}</div>
                  <div style={{ display: "flex", gap: 10 }}>
                    {[{ l: "Downside 1σ", v: `-${A.volatility?.estimated_annual_volatility_pct}%`, c: "#dc2626" }, { l: "Upside 1σ", v: `+${A.volatility?.estimated_annual_volatility_pct}%`, c: "#16a34a" }].map(({ l, v, c }) => (
                      <div key={l} style={{ flex: 1, padding: "10px", background: `${c}12`, borderRadius: 8, textAlign: "center" }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: c }}>{v}</div>
                        <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>{l}</div>
                      </div>
                    ))}
                  </div>
                </div>
                <div style={{ padding: 20, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Historical Drawdowns</div>
                  {Object.entries(A.drawdown_sensitivity?.scenarios || {}).map(([sc, d]) => (
                    <div key={sc} style={{ marginBottom: 12 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontSize: 12, color: "#374151", textTransform: "capitalize" }}>{sc.replace(/_/g, " ")}</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#dc2626" }}>{d.pct}%</span>
                      </div>
                      <div style={{ height: 5, background: "#f3f4f6", borderRadius: 99 }}>
                        <div style={{ width: `${Math.abs(d.pct) / 70 * 100}%`, height: "100%", background: "#dc2626", borderRadius: 99 }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* STRESS TEST */}
          {view === "stress" && sel && (
            <div>
              <div style={{ marginBottom: 24 }}>
                <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Stress Test Engine</h1>
                <p style={{ fontSize: 13, color: "#6b7280" }}>8 macro scenarios · India market 2000–2024</p>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 24 }}>
                {[
                  { l: "Resilience", v: `${A.stress_test?.summary?.resilience_score}/100`, s: `Grade ${A.stress_test?.summary?.resilience_grade}`, c: scoreClr(A.stress_test?.summary?.resilience_score || 0) },
                  { l: "Worst Impact", v: `${A.stress_test?.summary?.worst_impact_pct}%`, s: (A.stress_test?.summary?.worst_scenario || "").replace(/_/g, " "), c: "#dc2626" },
                  { l: "Est. Loss", v: fmtCr(Math.abs(A.stress_test?.summary?.worst_impact_inr || 0)), s: "Worst case", c: "#dc2626" },
                  { l: "Best Case", v: `+${A.stress_test?.summary?.best_impact_pct}%`, s: (A.stress_test?.summary?.best_scenario || "").replace(/_/g, " "), c: "#16a34a" },
                ].map(({ l, v, s, c }) => (
                  <div key={l} style={{ padding: 18, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                    <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>{l}</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: c }}>{v}</div>
                    <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>{s}</div>
                  </div>
                ))}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {scenarios.map(s => (
                  <div key={s.scenario} onClick={() => setStressDetail(d => d?.scenario === s.scenario ? null : s)}
                    style={{ padding: 18, background: "#fff", borderRadius: 12, border: `1.5px solid ${stressDetail?.scenario === s.scenario ? "#2563eb" : "#e5e7eb"}`, cursor: "pointer" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 2 }}>{s.label}</div>
                        <div style={{ fontSize: 11, color: "#6b7280", lineHeight: 1.4 }}>{s.description}</div>
                      </div>
                      <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 12 }}>
                        <div style={{ fontSize: 20, fontWeight: 700, color: clr(s.portfolio_impact_pct) }}>{s.portfolio_impact_pct > 0 ? "+" : ""}{s.portfolio_impact_pct}%</div>
                        <div style={{ fontSize: 11, color: "#6b7280" }}>{fmtCr(Math.abs(s.portfolio_impact_inr || 0))}</div>
                      </div>
                    </div>
                    <div style={{ height: 5, background: "#f3f4f6", borderRadius: 99, marginBottom: 8 }}>
                      <div style={{ width: `${Math.min(Math.abs(s.portfolio_impact_pct) / 40 * 100, 100)}%`, height: "100%", background: clr(s.portfolio_impact_pct), borderRadius: 99 }} />
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                      <span style={{ color: "#6b7280" }}>Post-stress: <b style={{ color: "#111" }}>{fmtCr(s.post_stress_value_inr)}</b></span>
                      <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 600, background: s.severity === "positive" ? "#dcfce7" : s.severity === "high" || s.severity === "severe" ? "#fee2e2" : "#fef9c3", color: s.severity === "positive" ? "#15803d" : s.severity === "high" || s.severity === "severe" ? "#dc2626" : "#854d0e" }}>{s.severity}</span>
                    </div>
                    {stressDetail?.scenario === s.scenario && s.top_impacted_holdings?.length > 0 && (
                      <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #f3f4f6" }}>
                        <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 6 }}>Top impacted</div>
                        {s.top_impacted_holdings.map((h, i) => (
                          <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 3 }}>
                            <span style={{ color: "#6b7280", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 200 }}>{h.name}</span>
                            <span style={{ fontWeight: 600, color: clr(h.shock_pct), flexShrink: 0 }}>{h.shock_pct > 0 ? "+" : ""}{h.shock_pct}%</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AI INSIGHTS */}
          {view === "insights" && sel && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
                <div>
                  <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>AI Insights</h1>
                  <p style={{ fontSize: 13, color: "#6b7280" }}>Needs ANTHROPIC_API_KEY or OPENAI_API_KEY in backend .env</p>
                </div>
                <button onClick={generateInsights} disabled={insightLoading}
                  style={{ padding: "9px 18px", borderRadius: 8, border: "none", background: "#111827", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", opacity: insightLoading ? 0.6 : 1, display: "flex", alignItems: "center", gap: 8 }}>
                  {insightLoading
                    ? <><div style={{ width: 14, height: 14, border: "2px solid rgba(255,255,255,.3)", borderTop: "2px solid #fff", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />Generating…</>
                    : "✦ Generate Insights"}
                </button>
              </div>
              {!sel.insights
                ? <div style={{ padding: 48, textAlign: "center", color: "#6b7280", background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                    <div style={{ fontSize: 36, marginBottom: 12, opacity: .3 }}>✦</div>
                    <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 6 }}>No insights yet</div>
                    <div style={{ fontSize: 13 }}>Click Generate. Needs API key in backend .env</div>
                  </div>
                : <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {[{ t: "Portfolio Summary", c: sel.insights.portfolio_summary }, { t: "Meeting Prep Notes", c: sel.insights.meeting_prep_notes }, { t: "Risk Commentary", c: sel.insights.risk_commentary }].map(({ t, c }) => c && (
                      <div key={t} style={{ padding: 24, background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
                          <div style={{ fontSize: 14, fontWeight: 600 }}>{t}</div>
                          <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 11, background: "#f3f4f6", color: "#6b7280" }}>{sel.insights.ai_provider}</span>
                        </div>
                        <div style={{ fontSize: 14, color: "#374151", lineHeight: 1.8, whiteSpace: "pre-wrap" }}>{c}</div>
                      </div>
                    ))}
                    <div style={{ fontSize: 11, color: "#9ca3af", textAlign: "center" }}>For informational purposes only. Not investment advice.</div>
                  </div>
              }
            </div>
          )}

          {["dashboard", "holdings", "analytics", "stress", "insights"].includes(view) && !sel && (
            <div style={{ textAlign: "center", padding: "80px 20px", color: "#6b7280" }}>
              <div style={{ fontSize: 36, marginBottom: 16, opacity: .3 }}>◻</div>
              <div style={{ fontSize: 15, marginBottom: 16 }}>Select a portfolio first</div>
              <button onClick={() => setView("portfolios")} style={{ padding: "9px 18px", borderRadius: 8, border: "none", background: "#111827", color: "#fff", fontSize: 13, cursor: "pointer" }}>View portfolios</button>
            </div>
          )}

        </main>
      </div>
    </div>
  );
}
