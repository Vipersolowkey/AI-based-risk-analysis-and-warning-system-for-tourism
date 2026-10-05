import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";
import polyline from "@mapbox/polyline";
import "./App.css";
import { API_BASE } from "./api";
import { subscribeToPush, unsubscribeFromPush, isPushSupported, getCurrentPushSubscription, checkNow } from "./push";
import { LandingPage } from "./screens/LandingPage";
import { RegisterScreen } from "./screens/RegisterScreen";
import { LoginScreen } from "./screens/LoginScreen";
import TravelPortal from "./portal/TravelPortal";

function localDate() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function readSavedContext() {
  try {
    const saved = JSON.parse(localStorage.getItem("vtra_trip_context_v2") || "null");
    if (!saved || typeof saved !== "object") return {};
    if (!saved.savedAt || Date.now() - saved.savedAt > 7 * 24 * 60 * 60 * 1000) return {};
    if (!saved.tripCheckedAt || Date.now() - saved.tripCheckedAt > 30 * 60 * 1000) {
      return { ...saved, tripRes: null, routeCoords: [], forecastData: [], tripCheckedAt: null };
    }
    return saved;
  } catch { return {}; }
}

async function apiGet(path, token) {
  let r;
  try {
    r = await fetch(`${API_BASE}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch (networkErr) {
    // Network error = server chưa chạy, CORS block, hoặc mất mạng
    throw new Error(
      "Không kết nối được server. Kiểm tra backend đang chạy tại " +
        API_BASE +
        " (lỗi: " +
        networkErr.message +
        ")"
    );
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = data?.detail || data?.error || JSON.stringify(data);
    throw new Error(msg);
  }
  return data;
}

async function apiDelete(path, token) {
  let r;
  try {
    r = await fetch(`${API_BASE}${path}`, {
      method: "DELETE",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch (networkErr) {
    throw new Error(
      "Không kết nối được server. Kiểm tra backend đang chạy tại " +
        API_BASE +
        " (lỗi: " +
        networkErr.message +
        ")"
    );
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = data?.detail || data?.error || JSON.stringify(data);
    throw new Error(msg);
  }
  return data;
}

// ===== polyline decode helper =====
function decodeRoutePolyline(enc, type) {
  // type: "polyline" or "polyline6" (from backend)
  // @mapbox/polyline supports precision param as 2nd argument.
  if (!enc || typeof enc !== "string" || enc.length < 10) return [];
  try {
    if (String(type || "").toLowerCase() === "polyline6") {
      return polyline.decode(enc, 6); // precision=6
    }
    return polyline.decode(enc); // default precision=5
  } catch {
    return [];
  }
}



export default function App() {
  const [initialContext] = useState(readSavedContext);
  // ===== LOGIN (new) =====
  const [session, setSession] = useState(() => {
    try {
      // Check if this is first page load (not a reload within same session)
      const isLoggedInSession = sessionStorage.getItem("va_logged_in_session");
      
      // If no session flag in sessionStorage, clear localStorage session (first load)
      if (!isLoggedInSession) {
        localStorage.removeItem("va_session");
        return null;
      }
      
      // Otherwise, restore from localStorage
      const s = localStorage.getItem("va_session");
      if (!s) return null;
      const parsed = JSON.parse(s);
      // Session expiration: 24 hours
      const expirationMs = 24 * 60 * 60 * 1000;
      if (parsed.ts && Date.now() - parsed.ts > expirationMs) {
        // Session expired, remove it
        localStorage.removeItem("va_session");
        sessionStorage.removeItem("va_logged_in_session");
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  });

  // Control whether we show the landing page or the login screen
  // const [showLanding, setShowLanding] = useState(true);

  // ===== Control Navigation (SỬA Ở ĐÂY) =====
  // Trạng thái màn hình: 'landing' | 'login' | 'register'
  const [currentScreen, setCurrentScreen] = useState('landing');

  // ===== Trip history (requires login) =====
  const [tripHistory, setTripHistory] = useState([]);
  const [tripHistoryLoading, setTripHistoryLoading] = useState(false);
  const [tripHistoryError, setTripHistoryError] = useState("");

  const loadTripHistory = useCallback(async () => {
    if (!session?.user?.token) return;
    setTripHistoryLoading(true);
    setTripHistoryError("");
    try {
      const data = await apiGet("/api/trip-history", session.user.token);
      setTripHistory(data.results || []);
    } catch (error) {
      setTripHistoryError(String(error.message || error));
    } finally {
      setTripHistoryLoading(false);
    }
  }, [session?.user?.token]);

  useEffect(() => {
    if (session?.user?.token) loadTripHistory();
  }, [session?.user?.token, loadTripHistory]);

  async function deleteTripHistoryEntry(id) {
    if (!session?.user?.token) return;
    try {
      await apiDelete(`/api/trip-history/${id}`, session.user.token);
      setTripHistory((prev) => prev.filter((t) => t.id !== id));
    } catch (e) {
      setErr(`Không xóa được lịch sử: ${String(e.message || e)}`);
    }
  }

  // ===== Web Push: severe weather alerts for the current trip destination =====
  const [pushStatus, setPushStatus] = useState(""); // "", "loading", "enabled", "denied", "error"

  async function enableWeatherAlerts() {
    if (!session?.user?.token || !tripRes?.to) return;
    setPushStatus("loading");
    try {
      const ok = await subscribeToPush(session.user.token, {
        destination: tripRes.to.name,
        lat: tripRes.to.lat,
        lon: tripRes.to.lon,
      });
      setPushStatus(ok ? "enabled" : "denied");
    } catch {
      setPushStatus("error");
    }
  }

  async function disableWeatherAlerts() {
    if (!session?.user?.token) return false;
    setPushStatus("loading");
    try {
      await unsubscribeFromPush(session.user.token);
      setPushStatus("");
      return true;
    } catch {
      setPushStatus("error");
      return false;
    }
  }

  useEffect(() => {
    const token = session?.user?.token;
    if (!token || !isPushSupported()) return undefined;
    let active = true;
    let inFlight = false;
    async function checkSubscribedWeather() {
      if (!active || inFlight || document.visibilityState !== "visible") return;
      inFlight = true;
      try {
        const subscription = await getCurrentPushSubscription();
        if (active && subscription) await checkNow(token);
      } catch (error) {
        console.warn("[Push] Could not check watched weather:", error);
      } finally {
        inFlight = false;
      }
    }
    checkSubscribedWeather();
    const timer = window.setInterval(checkSubscribedWeather, 30 * 60 * 1000);
    document.addEventListener("visibilitychange", checkSubscribedWeather);
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", checkSubscribedWeather);
    };
  }, [session?.user?.token, pushStatus]);

  function login(user) {
    const s = { user, ts: Date.now() };
    setSession(s);
    try {
      localStorage.setItem("va_session", JSON.stringify(s));
      // Mark this as a logged-in session in sessionStorage (persists across reload)
      sessionStorage.setItem("va_logged_in_session", "true");
    } catch {
      // The app can continue when browser storage is unavailable.
    }
    // Restore dashboard theme from localStorage or set default to light
    try {
      const savedTheme = localStorage.getItem("va_theme") || "light";
      setTheme(savedTheme);
      // Apply theme to DOM immediately
      if (savedTheme === "light") {
        document.documentElement.removeAttribute("data-theme");
      } else {
        document.documentElement.setAttribute("data-theme", savedTheme);
      }
    } catch {
      // Theme state still updates when browser storage is unavailable.
    }
  }

  function logout() {
    // Reset theme immediately on DOM
    try {
      document.documentElement.removeAttribute("data-theme");
      localStorage.removeItem("va_theme");
    } catch {
      // Clearing browser storage is best effort.
    }
    // Clear all session data
    try {
      localStorage.removeItem("va_session");
      localStorage.removeItem("vtra_trip_context_v2");
      sessionStorage.removeItem("va_logged_in_session");
    } catch {
      // React state still clears the session.
    }
    // Reset state
    setSession(null);
    setCurrentScreen('landing');
    setTheme('light');
    setUserPos(null);
    setOriginName("");
    setDestination("");
    setDepartureDate(localDate());
    setTripPurpose(null);
    setTripRes(null);
    setTripCheckedAt(null);
    setRouteCoords([]);
    setForecastData([]);
    setSelectedDateIndex(0);
    setTripHistory([]);
  }

  // ===== data =====
  const [provinces, setProvinces] = useState([]); // {province, lat, lon}
  const [selectedProv, setSelectedProv] = useState(null);
  const [selectedRisk, setSelectedRisk] = useState(null);

  // ===== user gps =====
  const [gpsLoading, setGpsLoading] = useState(false);
  const [userPos, setUserPos] = useState(initialContext.userPos || null); // {lat, lon}
  const [originName, setOriginName] = useState(initialContext.originName || "");


  // ===== trip =====
  const [destination, setDestination] = useState(initialContext.destination ?? "Đà Lạt");
  const [departureDate, setDepartureDate] = useState(initialContext.departureDate || localDate());
  const [tripLoading, setTripLoading] = useState(false);
  const [tripRes, setTripRes] = useState(initialContext.tripRes || null);
  const [tripCheckedAt, setTripCheckedAt] = useState(initialContext.tripCheckedAt || null);
  const [routeCoords, setRouteCoords] = useState(initialContext.routeCoords || []); // [[lat,lon],...]

  // ===== trip purpose =====
  const [tripPurpose, setTripPurpose] = useState(initialContext.tripPurpose || null);

  // ===== 7-day forecast =====
  const [forecastData, setForecastData] = useState(initialContext.forecastData || []);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [selectedDateIndex, setSelectedDateIndex] = useState(() => {
    const savedIndex = initialContext.selectedDateIndex;
    if (Number.isInteger(savedIndex) && savedIndex >= 0 && savedIndex < (initialContext.forecastData?.length || 0)) return savedIndex;
    return Math.max(0, initialContext.forecastData?.findIndex((day) => day.date === initialContext.departureDate) ?? 0);
  });

  // ===== ui =====
  const [err, setErr] = useState("");

  // ===== NEW: map action controller =====
  const [mapAction, setMapAction] = useState(null);

  // ===== NEW: cache risk to reduce API calls =====
  const riskCacheRef = useRef(new Map()); // key: province -> risk json
  const riskRequestRef = useRef(0);

  // ===== theme (dark / light) - default is LIGHT =====
  const [theme, setTheme] = useState("light");

  useEffect(() => {
    try {
      if (theme === "light") {
        document.documentElement.removeAttribute("data-theme");
      } else {
        document.documentElement.setAttribute("data-theme", theme);
      }
      localStorage.setItem("va_theme", theme);
    } catch {
      // Theme selection remains in React state.
    }
  }, [theme]);

  function toggleTheme() {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

  useEffect(() => {
    try {
      localStorage.setItem("vtra_trip_context_v2", JSON.stringify({
        savedAt: Date.now(), userPos, originName, destination, departureDate,
        tripPurpose, tripRes, tripCheckedAt, routeCoords, forecastData, selectedDateIndex,
      }));
    } catch {
      // Keep the current tab usable if browser storage is disabled or full.
    }
  }, [userPos, originName, destination, departureDate, tripPurpose, tripRes, tripCheckedAt, routeCoords, forecastData, selectedDateIndex]);

  function invalidateTrip() {
    setTripRes(null);
    setTripCheckedAt(null);
    setRouteCoords([]);
    setForecastData([]);
    setSelectedDateIndex(0);
    setPushStatus("");
  }

  function updateDestination(value) { setDestination(value); invalidateTrip(); }
  function updateDepartureDate(value) { setDepartureDate(value); invalidateTrip(); }
  function updatePurpose(value) { setTripPurpose(value); invalidateTrip(); }


  // Load provinces points from backend
  useEffect(() => {
    if (!session) return;
    let alive = true;
    (async () => {
      try {
        setErr("");
        const data = await apiGet("/map/points");
        if (!alive) return;
        setProvinces(data?.points || []);
      } catch (e) {
        if (!alive) return;
        setErr(`Không tải được danh sách tỉnh: ${String(e.message || e)}`);
      }
    })();
    return () => {
      alive = false;
    };
  }, [session]);

  async function getRiskCached(prov) {
    const key = String(prov || "").trim();
    if (!key) return null;

    if (riskCacheRef.current.has(key)) return riskCacheRef.current.get(key);

    const r = await apiGet(`/risk?place=${encodeURIComponent(key)}`);
    riskCacheRef.current.set(key, r);
    return r;
  }

  // When select province -> fetch risk (cached)
  async function onPickProvince(p, opts = {}) {
    const requestId = ++riskRequestRef.current;
    try {
      setErr("");
      setSelectedProv(p);
      setSelectedRisk(null);

      const r = await getRiskCached(p.province);
      if (requestId === riskRequestRef.current) setSelectedRisk(r);

      // NEW: fly to province
      if (opts.fly && requestId === riskRequestRef.current) {
        setMapAction({
          type: "flyTo",
          center: [p.lat, p.lon],
          zoom: 8,
          ts: Date.now(),
        });
      }
    } catch (e) {
      if (requestId === riskRequestRef.current) {
        setErr(`Không tải được dữ liệu tỉnh: ${String(e.message || e)}`);
      }
    }
  }

  async function getGPS() {
    setErr("");
    setGpsLoading(true);

    if (!navigator.geolocation) {
      setErr("Trình duyệt không hỗ trợ GPS.");
      setGpsLoading(false);
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (p) => {
        const lat = p.coords.latitude;
        const lon = p.coords.longitude;
        const pos = { lat, lon };

        setUserPos(pos);
        setOriginName("Vị trí hiện tại");
        invalidateTrip();
        setGpsLoading(false);

        // focus to user
        setMapAction({
          type: "flyTo",
          center: [lat, lon],
          zoom: 10,
          ts: Date.now(),
        });

      },
      (e) => {
        setErr("Không xác định được vị trí: " + e.message);
        setGpsLoading(false);
      },
      { enableHighAccuracy: true, timeout: 12000 }
    );
  }

  function chooseOrigin(origin) {
    const pos = { lat: origin.lat, lon: origin.lon };
    setUserPos(pos);
    setOriginName(origin.label);
    invalidateTrip();
    setErr("");
    setMapAction({ type: "flyTo", center: [pos.lat, pos.lon], zoom: 9, ts: Date.now() });
  }

  const canTrip = useMemo(() => {
    return Boolean(destination.trim().length > 0 && departureDate && Number.isFinite(userPos?.lat) && Number.isFinite(userPos?.lon));
  }, [destination, departureDate, userPos]);

  async function handleCheckTripClick() {
    if (!userPos) {
      setErr("Chọn điểm xuất phát hoặc dùng vị trí hiện tại trước.");
      return null;
    }
    return runTrip(tripPurpose);
  }

  async function runTrip(purposeOverride) {
    if (!userPos) {
      setErr("Chọn điểm xuất phát hoặc dùng vị trí hiện tại trước.");
      return;
    }
    const activePurpose = purposeOverride !== undefined ? purposeOverride : tripPurpose;
    setErr("");
    setTripLoading(true);
    setTripRes(null);
    setTripCheckedAt(null);
    setRouteCoords([]);
    setForecastData([]);
    setSelectedDateIndex(0);

    try {
      let url =
        `/trip?destination=${encodeURIComponent(destination)}` +
        `&lat=${encodeURIComponent(String(userPos.lat))}` +
        `&lon=${encodeURIComponent(String(userPos.lon))}`;
      if (activePurpose) {
        url += `&trip_purpose=${encodeURIComponent(activePurpose)}`;
      }

      const data = await apiGet(url, session?.user?.token);
      setTripRes(data);
      setTripCheckedAt(Date.now());
      if (session?.user?.token) loadTripHistory();

      // ===== Route polyline decode (respect polyline vs polyline6) =====
      const enc = data?.traffic?.route_polyline;
      const typ = data?.traffic?.route_polyline_type; // "polyline" | "polyline6"
      const decoded = decodeRoutePolyline(enc, typ);

      if (decoded?.length >= 2) {
        setRouteCoords(decoded);
        // focus route
        setMapAction({ type: "fitBounds", bounds: decoded, ts: Date.now() });
      } else {
        // fallback: straight line A->B
        const a = [data?.from?.lat, data?.from?.lon];
        const b = [data?.to?.lat, data?.to?.lon];
        if (a[0] && a[1] && b[0] && b[1]) {
          const straight = [a, b];
          setRouteCoords(straight);
          setMapAction({ type: "fitBounds", bounds: straight, ts: Date.now() });
        }
      }

      // ===== Fetch 7-day forecast for destination (best-effort) =====
      try {
        setForecastLoading(true);
        // Prefer short name: user input > inferred province > full resolved name
        const cityName = destination.trim()
          || data?.to?.province_inferred
          || data?.to?.name
          || "Unknown";
        const provParam = data?.to?.province_inferred
          ? `&province=${encodeURIComponent(data.to.province_inferred)}`
          : "";
        const purposeParam = activePurpose
          ? `&trip_purpose=${encodeURIComponent(activePurpose)}`
          : "";
        const coordsParam = Number.isFinite(data?.to?.lat) && Number.isFinite(data?.to?.lon)
          ? `&lat=${encodeURIComponent(String(data.to.lat))}&lon=${encodeURIComponent(String(data.to.lon))}`
          : "";
        const fcUrl = `/weather/ai/forecast?city=${encodeURIComponent(cityName)}&days=7${provParam}${purposeParam}${coordsParam}`;
        const fcData = await apiGet(fcUrl);
        if (fcData?.daily?.length) {
          setForecastData(fcData.daily);
          const dayIndex = fcData.daily.findIndex((day) => day.date === departureDate);
          setSelectedDateIndex(dayIndex >= 0 ? dayIndex : 0);
        }
      } catch (fcErr) {
        console.warn("[Forecast] Could not load 7-day forecast:", fcErr);
      } finally {
        setForecastLoading(false);
      }
      return data;
    } catch (e) {
      setErr(`Không thể đánh giá chuyến đi: ${String(e.message || e)}`);
      return null;
    } finally {
      setTripLoading(false);
    }
  }


  // ===== NEW: map quick actions =====
  function resetVN() {
    // Xóa hết các địa điểm đã chọn
    riskRequestRef.current += 1;
    setSelectedProv(null);
    setSelectedRisk(null);
    setDestination("");
    setDepartureDate(localDate());
    setTripRes(null);
    setTripCheckedAt(null);
    setRouteCoords([]);
    setForecastData([]);
    setSelectedDateIndex(0);
    setTripPurpose(null);
    setUserPos(null);
    setOriginName("");
    setErr("");
    // Reset map view
    setMapAction({ type: "resetVN", ts: Date.now() });
  }
  function focusUser() {
    if (!userPos) return;
    setMapAction({ type: "flyTo", center: [userPos.lat, userPos.lon], zoom: 10, ts: Date.now() });
  }
  function focusRoute() {
    if (!routeCoords?.length) return;
    setMapAction({ type: "fitBounds", bounds: routeCoords, ts: Date.now() });
  }

  // Open Google Maps directions using available origin/destination
  function openGoogleDirections() {
    try {
      let url = "";
      if (userPos && tripRes?.to?.lat && tripRes?.to?.lon) {
        const o = `${userPos.lat},${userPos.lon}`;
        const d = `${tripRes.to.lat},${tripRes.to.lon}`;
        url = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(o)}&destination=${encodeURIComponent(d)}&travelmode=driving`;
      } else if (userPos && destination) {
        const o = `${userPos.lat},${userPos.lon}`;
        const d = encodeURIComponent(destination);
        url = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(o)}&destination=${d}&travelmode=driving`;
      } else if (tripRes?.to?.lat && tripRes?.to?.lon) {
        const d = `${tripRes.to.lat},${tripRes.to.lon}`;
        url = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(d)}&travelmode=driving`;
      } else if (destination) {
        url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(destination)}`;
      }

      if (url) window.open(url, "_blank", "noopener,noreferrer");
      else setErr("Chọn điểm đến trước khi mở chỉ đường.");
    } catch (e) {
      setErr("Không thể mở chỉ đường: " + String(e.message || e));
    }
  }

  // Keep every Hook above this authentication branch so login/logout can
  // change screens without changing the component's Hook call order.
  if (!session) {
    if (currentScreen === "landing") {
      return <LandingPage onGoToLogin={() => setCurrentScreen("login")} />;
    }
    if (currentScreen === "register") {
      return (
        <RegisterScreen
          onRegister={login}
          onBack={() => setCurrentScreen("landing")}
          onGoToLogin={() => setCurrentScreen("login")}
        />
      );
    }
    return (
      <LoginScreen
        onLogin={login}
        onBack={() => setCurrentScreen("landing")}
        onGoToRegister={() => setCurrentScreen("register")}
      />
    );
  }

  return (
    <TravelPortal
      session={session}
      logout={logout}
      theme={theme}
      toggleTheme={toggleTheme}
      destination={destination}
      updateDestination={updateDestination}
      departureDate={departureDate}
      updateDepartureDate={updateDepartureDate}
      tripPurpose={tripPurpose}
      updatePurpose={updatePurpose}
      canTrip={canTrip}
      tripLoading={tripLoading}
      checkTrip={handleCheckTripClick}
      userPos={userPos}
      originName={originName}
      gpsLoading={gpsLoading}
      getGPS={getGPS}
      chooseOrigin={chooseOrigin}
      tripRes={tripRes}
      tripCheckedAt={tripCheckedAt}
      err={err}
      clearError={() => setErr("")}
      routeCoords={routeCoords}
      mapAction={mapAction}
      resetVN={resetVN}
      focusUser={focusUser}
      focusRoute={focusRoute}
      openGoogleDirections={openGoogleDirections}
      forecastData={forecastData}
      forecastLoading={forecastLoading}
      selectedDateIndex={selectedDateIndex}
      setSelectedDateIndex={setSelectedDateIndex}
      provinces={provinces}
      selectedProv={selectedProv}
      selectedRisk={selectedRisk}
      onPickProvince={onPickProvince}
      tripHistory={tripHistory}
      tripHistoryLoading={tripHistoryLoading}
      tripHistoryError={tripHistoryError}
      loadTripHistory={loadTripHistory}
      deleteTripHistoryEntry={deleteTripHistoryEntry}
      pushStatus={pushStatus}
      enableWeatherAlerts={enableWeatherAlerts}
      disableWeatherAlerts={disableWeatherAlerts}
      canNotify={Boolean(session?.user?.token && isPushSupported())}
    />
  );
}


