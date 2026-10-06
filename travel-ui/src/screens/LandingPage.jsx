const LANDING_PINS = [
  { top: "12%", left: "8%", delay: "0s", size: 38 },
  { top: "22%", right: "12%", delay: "0.6s", size: 32 },
  { top: "68%", left: "14%", delay: "1.2s", size: 36 },
  { top: "75%", right: "9%", delay: "0.3s", size: 30 },
  { top: "40%", left: "82%", delay: "0.9s", size: 34 },
];

const LocationPinSVG = ({ size = 34, color = "#2563EB" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"
      fill={color}
      stroke="rgba(255,255,255,0.8)"
      strokeWidth="1"
    />
    <circle cx="12" cy="9" r="2.5" fill="#ffffff" />
  </svg>
);

export function LandingPage({ onGoToLogin }) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        height: "100vh",
        width: "100vw",
        overflow: "hidden",
        fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
      }}
    >
      {/* Keyframe animations */}
      <style>{`
        @keyframes landing-float {
          0%   { transform: translateY(0px) rotate(-3deg); }
          50%  { transform: translateY(-18px) rotate(3deg); }
          100% { transform: translateY(0px) rotate(-3deg); }
        }
        @keyframes landing-fade-up {
          0%   { opacity: 0; transform: translateY(30px); }
          100% { opacity: 1; transform: translateY(0); }
        }
        @keyframes landing-pulse-ring {
          0%   { transform: scale(0.9); opacity: 0.5; }
          50%  { transform: scale(1.15); opacity: 0.2; }
          100% { transform: scale(0.9); opacity: 0.5; }
        }
        @keyframes landing-shimmer {
          0%   { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        .landing-cta-primary {
          padding: 16px 40px;
          font-size: 1.15rem;
          font-weight: 800;
          border-radius: 12px;
          border: none;
          background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
          color: #ffffff;
          cursor: pointer;
          box-shadow: 0 8px 30px rgba(37,99,235,0.45), 0 2px 8px rgba(0,0,0,0.2);
          transition: all 0.25s cubic-bezier(.22,.9,.26,1);
          letter-spacing: 0.3px;
          position: relative;
          overflow: hidden;
        }
        .landing-cta-primary::after {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.15) 50%, transparent 100%);
          background-size: 200% 100%;
          animation: landing-shimmer 3s ease-in-out infinite;
        }
        .landing-cta-primary:hover {
          transform: translateY(-3px) scale(1.03);
          box-shadow: 0 12px 40px rgba(37,99,235,0.55), 0 4px 12px rgba(0,0,0,0.25);
        }
        .landing-cta-primary:active { transform: translateY(0) scale(0.98); }
        .landing-cta-secondary {
          padding: 14px 36px;
          font-size: 1.05rem;
          font-weight: 700;
          border-radius: 12px;
          border: 2px solid rgba(17,24,39,0.25);
          background: rgba(255,255,255,0.45);
          backdrop-filter: blur(8px);
          color: #111827;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(.22,.9,.26,1);
          letter-spacing: 0.3px;
        }
        .landing-cta-secondary:hover {
          background: rgba(255,255,255,0.7);
          border-color: rgba(17,24,39,0.4);
          transform: translateY(-2px);
        }
        .landing-cta-secondary:active { transform: translateY(0); }
      `}</style>

      {/* Blurred map background layer */}
      <div
        style={{
          position: "absolute",
          inset: "-20px",
          backgroundImage: `url("https://maps.googleapis.com/maps/api/staticmap?center=16.0,106.5&zoom=6&size=1600x900&scale=2&maptype=roadmap&style=feature:all|element:labels|visibility:off&key=_")`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          filter: "blur(3px) brightness(0.95) saturate(1.05)",
          zIndex: 0,
        }}
      />

      {/* Fallback: tile-based map background (since static maps API may not have key) */}
      <div
        style={{
          position: "absolute",
          inset: "-20px",
          backgroundImage: `url("https://tile.openstreetmap.org/6/51/29.png"), url("https://tile.openstreetmap.org/6/52/29.png"), url("https://tile.openstreetmap.org/6/51/30.png"), url("https://tile.openstreetmap.org/6/52/30.png")`,
          backgroundSize: "50% 50%",
          backgroundRepeat: "no-repeat",
          backgroundPosition: "top left, top right, bottom left, bottom right",
          filter: "blur(3px) brightness(0.95) saturate(1.05)",
          zIndex: 0,
        }}
      />

      {/* Light frosted overlay for readability (no color tint) */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(255, 255, 255, 0.35)",
          backdropFilter: "blur(2px)",
          WebkitBackdropFilter: "blur(2px)",
          zIndex: 1,
        }}
      />

      {/* Floating decorative location pins */}
      {LANDING_PINS.map((pin, idx) => (
        <div
          key={idx}
          style={{
            position: "absolute",
            top: pin.top,
            left: pin.left,
            right: pin.right,
            zIndex: 2,
            animation: `landing-float 4.5s ease-in-out ${pin.delay} infinite`,
            opacity: 0.7,
            filter: "drop-shadow(0 4px 12px rgba(37,99,235,0.5))",
          }}
        >
          {/* Pulse ring behind pin */}
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              width: pin.size * 2,
              height: pin.size * 2,
              borderRadius: "50%",
              border: "2px solid rgba(37,99,235,0.25)",
              animation: `landing-pulse-ring 3s ease-in-out ${pin.delay} infinite`,
            }}
          />
          <LocationPinSVG size={pin.size} color={idx % 2 === 0 ? "#2563EB" : "#3B82F6"} />
        </div>
      ))}

      {/* CTA Button - Top Right */}
      <button
        className="landing-cta-primary"
        onClick={onGoToLogin}
        style={{
          position: "fixed",
          top: 32,
          right: 40,
          zIndex: 20,
          padding: "14px 32px",
          fontSize: "1.05rem",
          fontWeight: 800,
          borderRadius: 12,
          border: "none",
          background: "linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)",
          color: "#fff",
          boxShadow: "0 8px 30px rgba(37,99,235,0.45), 0 2px 8px rgba(0,0,0,0.2)",
          letterSpacing: 0.3,
        }}
      >
        Dùng thử — Try It Now
      </button>

      {/* Main content — centered hero */}
      <div
        style={{
          position: "relative",
          zIndex: 10,
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: "20px 24px",
          boxSizing: "border-box",
          gap: 0,
          background: "rgba(255, 255, 255, 0.05)",
          backdropFilter: "blur(3px)",
          WebkitBackdropFilter: "blur(3px)",
        }}
      >
        {/* Title */}
        <h1
          style={{
            fontSize: "clamp(2.2rem, 5vw, 3.8rem)",
            fontWeight: 900,
            color: "#111827",
            margin: "0 0 8px 0",
            lineHeight: 1.15,
            letterSpacing: "-0.02em",
            animation: "landing-fade-up 0.8s ease forwards",
            opacity: 0,
            animationDelay: "0.3s",
          }}
        >
          TravelShield{" "}
          <span
            style={{
              background: "linear-gradient(135deg, #2563EB, #60A5FA)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            AI
          </span>
        </h1>

        {/* Slogan */}
        <p
          style={{
            fontSize: "clamp(1rem, 2.2vw, 1.3rem)",
            color: "#374151",
            maxWidth: 680,
            lineHeight: 1.65,
            margin: "0 0 8px 0",
            fontWeight: 400,
            animation: "landing-fade-up 0.8s ease forwards",
            opacity: 0,
            animationDelay: "0.5s",
          }}
        >
          Your safety, our priority — Personalized AI insights for every mile of your journey.
        </p>
      </div>

          {/* Features row - Top Left - No Background, Larger Font */}
<div
  style={{
    position: "fixed",
    left: 40, // Tăng lề trái một chút cho cân đối
    top: 40,  // Tăng lề trên một chút
    zIndex: 20,
    display: "flex",
    flexDirection: "row",
    gap: 32, // Tăng khoảng cách giữa các feature để không bị rối khi font to
    alignItems: "center",
    animation: "landing-fade-up 0.8s ease forwards",
    opacity: 0,
    animationDelay: "1.05s",
  }}
>
  {[
    { icon: "🗺️", label: "63 Provinces", desc: "Full coverage" },
    { icon: "⚡", label: "Real-time", desc: "Live risk data" },
    { icon: "🌦️", label: "Weather AI", desc: "7-day forecast" },
    { icon: "🛡️", label: "Safety Score", desc: "1–10 scale" },
  ].map((f, i) => (
    <div
      key={i}
      style={{
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        gap: 14, // Giãn khoảng cách giữa icon và chữ
      }}
    >
      {/* Icon - Tăng size icon */}
      <div
        style={{
          width: 48,
          height: 48,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 26, // Tăng cỡ icon emoji
        }}
      >
        {f.icon}
      </div>

      {/* Text labels - Tăng size chữ */}
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{
          color: "#111827",
          fontWeight: 800, // Làm đậm thêm một chút
          fontSize: 16,   // Tăng từ 13 lên 16
          lineHeight: 1.2,
          letterSpacing: "-0.01em"
        }}>
          {f.label}
        </div>
        <div style={{
          color: "#4B5563",
          fontSize: 13,   // Tăng từ 11 lên 13
          fontWeight: 500,
          marginTop: 2
        }}>
          {f.desc}
        </div>
      </div>
    </div>
  ))}
</div>

      {/* Bottom credit */}
      <div
        style={{
          position: "absolute",
          bottom: 24,
          left: 0,
          right: 0,
          textAlign: "center",
          color: "rgba(17,24,39,0.35)",
          fontSize: 12,
          animation: "landing-fade-up 0.8s ease forwards",
          opacity: 0,
          animationDelay: "1.3s",
        }}
      >
        © 2026 TravelShield AI
      </div>
    </div>
  );
}
