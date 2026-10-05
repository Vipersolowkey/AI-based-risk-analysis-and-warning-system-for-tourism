import { useMemo, useState } from "react";
import { Marker, Popup } from "react-leaflet";
import L from "leaflet";
import { apiGet } from "../api";

function scoreToLabel(score) {
  const s = Number(score ?? 0);
  if (s >= 7) return { text: "High", pill: "#ff3b30" };
  if (s >= 4) return { text: "Medium", pill: "#ff9f0a" };
  return { text: "Low", pill: "#34c759" };
}

const provinceIcon = L.divIcon({
  className: "",
  html: `
    <div style="
      width:14px;height:14px;border-radius:999px;
      background:#8b5cf6;
      box-shadow: 0 0 0 3px rgba(139,92,246,.25), 0 10px 18px rgba(0,0,0,.35);
      border:1px solid rgba(255,255,255,.55);
    "></div>
  `,
  iconSize: [14, 14],
  iconAnchor: [7, 7],
});

export default function ProvinceMarkers({ provinces, onSelect }) {
  const [cache, setCache] = useState({}); // name -> risk data
  const [loadingName, setLoadingName] = useState("");

  const list = useMemo(() => {
    // remove invalid coords
    return (provinces || []).filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon));
  }, [provinces]);

  async function loadRisk(placeName) {
    if (!placeName) return;
    if (cache[placeName]) return;

    try {
      setLoadingName(placeName);
      const data = await apiGet(`/risk?place=${encodeURIComponent(placeName)}&quality_only=true`);
      setCache((prev) => ({ ...prev, [placeName]: data }));
    } catch (e) {
      setCache((prev) => ({
        ...prev,
        [placeName]: { error: String(e?.message || e) },
      }));
    } finally {
      setLoadingName("");
    }
  }

  return (
    <>
      {list.map((p, idx) => {
        const key = `${p.name}-${idx}`;
        const risk = cache[p.name];
        const score = risk?.overall_risk_score ?? null;
        const label = scoreToLabel(score);

        return (
          <Marker
            key={key}
            position={[p.lat, p.lon]}
            icon={provinceIcon}
            eventHandlers={{
              click: async () => {
                onSelect?.(p);
                await loadRisk(p.name);
              },
            }}
          >
            <Popup>
              <div style={{ minWidth: 240 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                  <div style={{ fontWeight: 700 }}>{p.name}</div>
                  <div
                    style={{
                      fontSize: 12,
                      padding: "4px 8px",
                      borderRadius: 999,
                      background: label.pill,
                      color: "white",
                      fontWeight: 700,
                    }}
                  >
                    {score === null ? "—" : `Risk ${score}/10`} • {label.text}
                  </div>
                </div>

                <div style={{ marginTop: 10, fontSize: 13, color: "#333" }}>
                  {loadingName === p.name && <div>⏳ Đang tải risk…</div>}

                  {risk?.error && (
                    <div style={{ color: "#c00" }}>
                      <b>Lỗi:</b> {risk.error}
                    </div>
                  )}

                  {risk && !risk.error && (
                    <>
                      <div style={{ marginBottom: 6, color: "#666" }}>
                        Articles: <b>{risk.num_articles}</b>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                        {Object.entries(risk.risk_assessment || {}).map(([k, v]) => (
                          <div
                            key={k}
                            style={{
                              border: "1px solid rgba(0,0,0,.08)",
                              borderRadius: 10,
                              padding: "6px 8px",
                              background: "rgba(0,0,0,.02)",
                            }}
                          >
                            <div style={{ fontSize: 11, color: "#666" }}>{k}</div>
                            <div style={{ fontWeight: 800, fontSize: 14 }}>{v}</div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </Popup>
          </Marker>
        );
      })}
    </>
  );
}
