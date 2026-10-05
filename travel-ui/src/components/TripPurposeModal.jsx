import { TRIP_PURPOSES } from "./tripPurposeConfig";

export function TripPurposeModal({ open, selected, onSelect, onConfirm, onClose }) {
  if (!open) return null;
  return (
    <>
      <style>{`
        @keyframes purpose-modal-in {
          0% { transform: scale(0.88) translateY(24px); opacity: 0 }
          100% { transform: scale(1) translateY(0); opacity: 1 }
        }
        @keyframes purpose-card-in {
          0% { transform: scale(0.90); opacity: 0 }
          100% { transform: scale(1); opacity: 1 }
        }
        .purpose-card {
          transition: transform 0.22s cubic-bezier(.22,.9,.36,1), box-shadow 0.22s ease;
          cursor: pointer;
          user-select: none;
        }
        .purpose-card:hover {
          transform: scale(1.05) translateY(-4px) !important;
        }
      `}</style>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.55)",
          backdropFilter: "blur(8px)",
          WebkitBackdropFilter: "blur(8px)",
          zIndex: 700,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            width: 520,
            maxWidth: "95vw",
            borderRadius: 20,
            border: "1px solid rgba(255,255,255,0.18)",
            background: "linear-gradient(135deg, rgba(238,245,246,0.22), rgba(238,245,246,0.06))",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            boxShadow: "0 20px 60px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.15)",
            padding: "28px 24px 22px",
            color: "#e2e8f0",
            animation: "purpose-modal-in 0.45s cubic-bezier(.22,.9,.36,1) forwards",
          }}
        >
          <div style={{ textAlign: "center", marginBottom: 20 }}>
            <div style={{ fontSize: 22, fontWeight: 900, letterSpacing: 0.3 }}>
               Mục đích chuyến đi
            </div>
            <div style={{ fontSize: 13, opacity: 0.75, marginTop: 6 }}>
              Chọn mục đích để AI điều chỉnh đánh giá rủi ro phù hợp hơn
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 14,
            }}
          >
            {TRIP_PURPOSES.map((p, i) => {
              const isActive = selected === p.key;
              return (
                <div
                  key={p.key}
                  className="purpose-card"
                  onClick={() => onSelect(p.key)}
                  style={{
                    borderRadius: 16,
                    padding: "18px 16px",
                    background: isActive ? p.gradient : p.bg,
                    border: isActive
                      ? "2px solid rgba(255,255,255,0.5)"
                      : "1px solid rgba(255,255,255,0.10)",
                    boxShadow: isActive
                      ? `0 8px 28px ${p.shadow}, inset 0 1px 0 rgba(255,255,255,0.20)`
                      : "0 2px 8px rgba(0,0,0,0.12)",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 8,
                    animation: `purpose-card-in 0.35s ${0.08 * i}s cubic-bezier(.22,.9,.36,1) both`,
                  }}
                >
                  <div style={{ fontSize: 32 }}>{p.icon}</div>
                  <div style={{ fontWeight: 800, fontSize: 15 }}>{p.label}</div>
                  <div
                    style={{
                      fontSize: 11,
                      opacity: isActive ? 0.95 : 0.7,
                      textAlign: "center",
                      lineHeight: 1.4,
                    }}
                  >
                    {p.desc}
                  </div>
                  {isActive && (
                    <div
                      style={{
                        marginTop: 4,
                        fontSize: 11,
                        fontWeight: 800,
                        background: "rgba(255,255,255,0.22)",
                        borderRadius: 999,
                        padding: "3px 12px",
                      }}
                    >
                      ✓ Đã chọn
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div
            style={{
              display: "flex",
              gap: 10,
              marginTop: 22,
              justifyContent: "center",
            }}
          >
            <button
              onClick={onClose}
              style={{
                padding: "10px 22px",
                borderRadius: 12,
                border: "1px solid rgba(255,255,255,0.15)",
                background: "rgba(255,255,255,0.06)",
                color: "#e2e8f0",
                cursor: "pointer",
                fontWeight: 700,
                fontSize: 13,
              }}
            >
              Bỏ qua
            </button>
            <button
              onClick={onConfirm}
              disabled={!selected}
              style={{
                padding: "10px 28px",
                borderRadius: 12,
                border: "none",
                background: selected
                  ? "#2563EB"
                  : "rgba(148,163,184,0.25)",
                color: selected ? "#fff" : "rgba(255,255,255,0.4)",
                cursor: selected ? "pointer" : "not-allowed",
                fontWeight: 800,
                fontSize: 14,
                boxShadow: selected
                  ? "0 4px 18px rgba(37,99,235,0.4)"
                  : "none",
                transition: "all 0.2s ease",
              }}
            >
              ✓ Xác nhận & Check Trip
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
