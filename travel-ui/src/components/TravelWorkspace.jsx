import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Popup, Polyline, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { TRIP_PURPOSES } from "./tripPurposeConfig";
import "./TravelWorkspace.css";

const VIETNAM_CENTER = [16.2, 107.8];
const ORIGINS = [
  { label: "TP. Hồ Chí Minh", lat: 10.7769, lon: 106.7009 },
  { label: "Hà Nội", lat: 21.0278, lon: 105.8342 },
  { label: "Đà Nẵng", lat: 16.0544, lon: 108.2022 },
  { label: "Cần Thơ", lat: 10.0452, lon: 105.7469 },
];
const RISK_NAMES = {
  Pricing_Issue: "Giá cả",
  Environmental_Cleanliness: "Môi trường",
  Safety_Security: "An ninh",
  Natural_Disaster: "Thiên tai",
  Fire_Accident_Risk: "Tai nạn, cháy nổ",
};

function MapMovement({ action, route, section }) {
  const map = useMap();
  useEffect(() => {
    if (!action) return;
    if (action.type === "flyTo" && action.center) {
      map.flyTo(action.center, action.zoom || 8, { duration: 0.6 });
    } else if (action.type === "fitBounds" && action.bounds?.length >= 2) {
      map.fitBounds(action.bounds, { padding: [44, 44] });
    } else if (action.type === "resetVN") {
      map.flyTo(VIETNAM_CENTER, 6, { duration: 0.6 });
    }
  }, [action, map]);
  useEffect(() => {
    const timer = setTimeout(() => map.invalidateSize(), 120);
    return () => clearTimeout(timer);
  }, [map, section]);
  useEffect(() => {
    if (route?.length >= 2) map.fitBounds(route, { padding: [44, 44] });
  }, [map, route]);
  return null;
}

function formatDay(value) {
  if (!value) return "—";
  const day = new Date(`${value}T12:00:00`);
  return Number.isNaN(day.getTime()) ? value : day.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

function riskTone(score) {
  if (score == null) return "neutral";
  if (score >= 7) return "danger";
  if (score >= 4) return "caution";
  return "calm";
}

export function TravelWorkspace({
  session, logout, theme, toggleTheme,
  destination, setDestination, tripPurpose, setTripPurpose, canTrip, tripLoading, onCheckTrip,
  userPos, originName, gpsLoading, getGPS, onChooseOrigin,
  tripRes, err, routeCoords, mapAction, resetVN, focusUser, focusRoute, openGoogleDirections,
  forecastData, forecastLoading, selectedDateIndex, setSelectedDateIndex,
  provinces, selectedProv, selectedRisk, onPickProvince,
  tripHistory, tripHistoryLoading, deleteTripHistoryEntry,
  pushStatus, enableWeatherAlerts, canNotify,
}) {
  const [section, setSection] = useState("overview");
  const [originChoice, setOriginChoice] = useState("");
  const [provinceQuery, setProvinceQuery] = useState("");
  const [showHelp, setShowHelp] = useState(false);
  const [showEditor, setShowEditor] = useState(false);

  const matchingProvinces = useMemo(() => {
    const q = provinceQuery.trim().toLocaleLowerCase("vi-VN");
    if (!q) return provinces;
    return provinces.filter((province) => province.province.toLocaleLowerCase("vi-VN").includes(q));
  }, [provinceQuery, provinces]);

  const weatherDay = forecastData[selectedDateIndex] || null;
  const currentWeather = tripRes?.weather?.error ? null : tripRes?.weather;
  const displayedWeather = weatherDay || currentWeather;
  const weatherRisk = displayedWeather?.adjusted_risk_score ?? displayedWeather?.risk_score;
  const recommendation = tripRes?.recommendation || "";
  const verdict = recommendation.includes("KHÔNG NÊN ĐI")
    ? { title: "Chưa nên khởi hành", tone: "danger", description: "Có điều kiện rủi ro cao trong dữ liệu hiện có. Hãy xem chi tiết trước khi quyết định." }
    : recommendation.includes("CẨN THẬN")
      ? { title: "Cần kiểm tra thêm trước chuyến đi", tone: "caution", description: "Một số nguồn dữ liệu còn thiếu hoặc có điều kiện cần lưu ý." }
      : { title: "Có thể tiếp tục lên kế hoạch", tone: "calm", description: "Đây là đánh giá tham khảo từ dữ liệu hiện có. Hãy kiểm tra thông tin thực tế trước khi đi." };

  function chooseOrigin(event) {
    const next = event.target.value;
    setOriginChoice(next);
    const origin = ORIGINS.find((item) => item.label === next);
    if (origin) onChooseOrigin(origin);
  }

  return (
    <div className={`travel-app view-${section}`}>
      <a className="travel-skip" href="#travel-main">Bỏ qua điều hướng</a>
      <header className="travel-header">
        <div className="travel-header-inner">
          <div className="travel-brand" aria-label="An tâm hành trình">
            <span className="travel-brand-mark" aria-hidden="true">A</span>
            <span><strong>An tâm hành trình</strong><small>Thông tin trước mỗi chuyến đi</small></span>
          </div>
          <div className="travel-header-actions">
            <button type="button" className="travel-text-button" onClick={() => setShowHelp((open) => !open)} aria-expanded={showHelp}>Cách sử dụng</button>
            <button type="button" className="travel-text-button" onClick={toggleTheme}>{theme === "dark" ? "Giao diện sáng" : "Giao diện tối"}</button>
            <button type="button" className="travel-outline-button" onClick={logout} title={session?.user?.email || "Đăng xuất"}>Đăng xuất</button>
          </div>
        </div>
      </header>

      <main id="travel-main" className="travel-main">
        <div className={`travel-intro ${tripRes ? "travel-intro-compact" : ""}`}>
          <div>
            <p className="travel-eyebrow">LÊN KẾ HOẠCH CÓ THÔNG TIN</p>
            <h1>{tripRes ? "Thông tin cho chuyến đi của bạn" : "Đi đâu, đi như thế nào, cần lưu ý gì?"}</h1>
            <p>{tripRes ? "Xem nhận định tổng quan, rồi mở từng mục để hiểu rõ dữ liệu." : "Chọn điểm xuất phát và điểm đến. Bạn sẽ nhận được nhận định ngắn gọn, rồi xem riêng từng yếu tố khi cần."}</p>
          </div>
          <div className="travel-intro-note">Dữ liệu hỗ trợ quyết định; điều kiện thực tế có thể thay đổi trước giờ khởi hành.</div>
        </div>

        {showHelp && (
          <div className="travel-help" role="note">
            <strong>Ba bước đơn giản:</strong> chọn điểm xuất phát, nhập điểm đến, nhấn “Xem đánh giá”. Sau đó mở từng mục Thời tiết, Tuyến đường hoặc Tin tức để xem chi tiết. Khi dữ liệu thiếu hoặc cũ, hệ thống sẽ ghi rõ.
          </div>
        )}

        <div className="travel-layout">
          <div className="travel-column">
            <section className="travel-card travel-plan" aria-labelledby="travel-plan-title">
              <div className="travel-section-heading"><span className="travel-step">01</span><div><h2 id="travel-plan-title">{tripRes && !showEditor ? "Chuyến đi của bạn" : "Chọn chuyến đi"}</h2><p>{tripRes && !showEditor ? "Bạn có thể thay đổi và tra cứu lại bất cứ lúc nào." : "Bắt đầu từ nơi bạn sẽ khởi hành."}</p></div></div>
              {tripRes && !showEditor ? (
                <div className="travel-trip-summary">
                  <div><span>Xuất phát</span><strong>{originName || "Vị trí đã chọn"}</strong></div>
                  <div><span>Điểm đến</span><strong>{tripRes.to?.name || destination}</strong></div>
                  <button type="button" className="travel-outline-button travel-wide" onClick={() => setShowEditor(true)}>Thay đổi chuyến đi</button>
                </div>
              ) : <>
              <div className="travel-field">
                <label htmlFor="travel-origin">Điểm xuất phát</label>
                <div className="travel-origin-row">
                  <select id="travel-origin" value={originChoice} onChange={chooseOrigin}>
                    <option value="">Chọn thành phố</option>
                    {ORIGINS.map((item) => <option value={item.label} key={item.label}>{item.label}</option>)}
                  </select>
                  <button type="button" className="travel-outline-button" onClick={() => { setOriginChoice(""); getGPS(); }} disabled={gpsLoading}>{gpsLoading ? "Đang xác định…" : "Dùng vị trí của tôi"}</button>
                </div>
                <p className="travel-field-hint">{userPos ? `Đang dùng: ${originName || "vị trí đã chọn"}. Bạn có thể thay đổi trước khi xem đánh giá.` : "Bạn có thể chọn thành phố; không bắt buộc cấp quyền vị trí."}</p>
              </div>
              <div className="travel-field">
                <label htmlFor="travel-destination">Điểm đến</label>
                <input id="travel-destination" value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="Ví dụ: Đà Lạt, Nha Trang" autoComplete="off" />
              </div>
              <div className="travel-field">
                <label htmlFor="travel-purpose">Bạn dự định đi cùng ai?</label>
                <select id="travel-purpose" value={tripPurpose || ""} onChange={(event) => setTripPurpose(event.target.value || null)}>
                  <option value="">Chuyến đi thông thường</option>
                  {TRIP_PURPOSES.map((purpose) => <option value={purpose.key} key={purpose.key}>{purpose.label}</option>)}
                </select>
                <p className="travel-field-hint">Tùy chọn này giúp điều chỉnh lưu ý thời tiết; không làm giảm cảnh báo nguy hiểm.</p>
              </div>
              <button className="travel-primary-button" type="button" onClick={() => { setSection("overview"); setShowEditor(false); onCheckTrip(); }} disabled={!canTrip || tripLoading}>{tripLoading ? "Đang tổng hợp dữ liệu…" : "Xem đánh giá chuyến đi"}</button>
              {!canTrip && <p className="travel-field-hint">Chọn điểm xuất phát và nhập điểm đến để tiếp tục.</p>}
              </>}
              {err && <p className="travel-error" role="alert">{err}</p>}
            </section>

            <nav className="travel-tabs" aria-label="Thông tin chuyến đi">
              {[
                ["overview", "Tổng quan"], ["weather", "Thời tiết"],
                ["route", "Tuyến đường"], ["news", "Tin tức"], ["history", "Đã lưu"],
              ].map(([key, label]) => (
                <button type="button" key={key} className={section === key ? "active" : ""} onClick={() => setSection(key)} aria-pressed={section === key}>{label}</button>
              ))}
            </nav>

            <section className="travel-card travel-detail" aria-live="polite">
              {section === "overview" && (
                <>
                  <div className="travel-section-heading"><span className="travel-step">02</span><div><h2>Nhận định cho chuyến đi</h2><p>Các yếu tố quan trọng được tóm tắt tại đây.</p></div></div>
                  {!tripRes ? <div className="travel-empty"><strong>Chưa có đánh giá</strong><p>Chọn điểm xuất phát và điểm đến ở phía trên. Kết quả sẽ xuất hiện tại đây sau khi bạn nhấn xem đánh giá.</p></div> : (
                    <>
                      <div className={`travel-verdict ${verdict.tone}`}><span className="travel-verdict-label">{tripRes.to?.name || destination}</span><h3>{verdict.title}</h3><p>{verdict.description}</p></div>
                      <div className="travel-facts">
                        <div><span>Thời tiết hiện tại</span><strong>{currentWeather?.risk_score != null ? `${currentWeather.risk_score}/10` : "Chưa có"}</strong><small>Điểm rủi ro, 10 là cao nhất</small></div>
                        <div><span>Đường đi</span><strong>{tripRes.traffic?.distance_km != null ? `${tripRes.traffic.distance_km} km` : "Chưa có"}</strong><small>{tripRes.traffic?.traffic_available === false ? "Thời gian chỉ là ước tính" : "Có dữ liệu tuyến đường"}</small></div>
                        <div><span>Tin tức</span><strong>{tripRes.risk?.data_status === "fresh" ? "Có tin mới" : "Cần kiểm tra"}</strong><small>{tripRes.risk?.data_status === "stale" ? `Bài gần nhất: ${tripRes.risk.latest_article_date || "không rõ"}` : tripRes.risk?.data_status === "no_data" ? "Chưa có dữ liệu cho điểm đến" : `${tripRes.risk?.num_articles || 0} bài trong ${tripRes.risk?.recent_window_days || 30} ngày`}</small></div>
                      </div>
                      <div className="travel-next"><strong>Xem kỹ trước khi quyết định</strong><p>Mở từng mục bên trên để xem dự báo, tuyến đường và độ mới của nguồn tin. Nhận định này không thay thế cảnh báo từ cơ quan chức năng.</p></div>
                    </>
                  )}
                </>
              )}

              {section === "weather" && (
                <>
                  <div className="travel-section-heading"><span className="travel-step">03</span><div><h2>Thời tiết điểm đến</h2><p>Xem từng ngày, một ngày tại một thời điểm.</p></div></div>
                  {!tripRes ? <div className="travel-empty">Xem đánh giá chuyến đi trước để tải dự báo cho điểm đến.</div> : (
                    <>
                      {forecastLoading && <p className="travel-field-hint" role="status">Đang tải dự báo nhiều ngày…</p>}
                      {!forecastLoading && forecastData.length === 0 && currentWeather && <p className="travel-data-note warning">Chưa tải được dự báo nhiều ngày. Thông tin bên dưới chỉ là thời tiết hiện tại tại điểm đến.</p>}
                      {forecastData.length > 0 && <div className="travel-days" aria-label="Chọn ngày dự báo">{forecastData.map((day, index) => {
                        const score = day.adjusted_risk_score ?? day.risk_score;
                        return <button type="button" key={day.date || index} className={selectedDateIndex === index ? "selected" : ""} onClick={() => setSelectedDateIndex(index)} aria-pressed={selectedDateIndex === index}><span>{formatDay(day.date)}</span><strong>{day.temperature != null ? `${Math.round(day.temperature)}°` : "—"}</strong><small className={`travel-score-dot ${riskTone(score)}`}>{score != null ? `${Number(score).toFixed(1)}/10` : "Chưa có"}</small></button>;
                      })}</div>}
                      {displayedWeather ? <div className="travel-weather-detail">
                        <div className="travel-weather-lead"><div><span>Đánh giá thời tiết {weatherDay ? `ngày ${formatDay(weatherDay.date)}` : "hiện tại"}</span><strong className={riskTone(weatherRisk)}>{weatherRisk != null ? `${Number(weatherRisk).toFixed(1)}/10` : "Chưa có"}</strong></div><p>Điểm rủi ro dự báo; số cao hơn nghĩa là cần thận trọng hơn.</p></div>
                        <dl className="travel-data-grid"><div><dt>Nhiệt độ</dt><dd>{displayedWeather.temperature != null ? `${Math.round(displayedWeather.temperature)}°C` : "—"}</dd></div><div><dt>Lượng mưa</dt><dd>{displayedWeather.precipitation != null ? `${displayedWeather.precipitation} mm` : "—"}</dd></div><div><dt>Gió</dt><dd>{displayedWeather.wind != null ? `${displayedWeather.wind} km/h` : "—"}</dd></div><div><dt>UV</dt><dd>{displayedWeather.uv_index ?? "—"}</dd></div></dl>
                        {displayedWeather.health_advice && <p className="travel-advice">{displayedWeather.health_advice.replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu, "").trim()}</p>}
                        <p className="travel-source">{weatherDay ? "Dự báo" : "Dữ liệu thời tiết hiện tại"} từ Open-Meteo; mức rủi ro do mô hình thời tiết của dự án tính. Điều kiện thực tế có thể thay đổi.</p>
                      </div> : <div className="travel-empty">Chưa tải được dữ liệu thời tiết. Hãy thử xem lại chuyến đi sau.</div>}
                      {canNotify && <button type="button" className="travel-outline-button travel-wide" onClick={enableWeatherAlerts} disabled={pushStatus === "loading" || pushStatus === "enabled"}>{pushStatus === "enabled" ? "Đã bật thông báo thời tiết" : pushStatus === "loading" ? "Đang bật thông báo…" : pushStatus === "denied" ? "Trình duyệt đã từ chối thông báo" : "Bật thông báo thời tiết"}</button>}
                    </>
                  )}
                </>
              )}

              {section === "route" && (
                <>
                  <div className="travel-section-heading"><span className="travel-step">04</span><div><h2>Tuyến đường dự kiến</h2><p>Đường đi hiển thị trên bản đồ bên cạnh.</p></div></div>
                  {!tripRes ? <div className="travel-empty">Chọn chuyến đi để xem tuyến đường và thời gian ước tính.</div> : <>
                    <div className="travel-route-endpoints"><div><span>Từ</span><strong>{originName || "Điểm xuất phát đã chọn"}</strong></div><div><span>Đến</span><strong>{tripRes.to?.name}</strong></div></div>
                    <dl className="travel-data-grid"><div><dt>Quãng đường</dt><dd>{tripRes.traffic?.distance_km ?? "—"} km</dd></div><div><dt>Thời gian dự kiến</dt><dd>{tripRes.traffic?.time_normal_human || "Chưa có"}</dd></div></dl>
                    <div className="travel-data-note">{tripRes.traffic?.traffic_available === false ? "Chưa có dữ liệu giao thông trực tiếp. Thời gian trên là ước tính theo tuyến đường và không phản ánh kẹt xe hiện tại." : `Có dữ liệu giao thông trực tiếp. Thời gian dự kiến theo tình hình hiện tại: ${tripRes.traffic?.time_traffic_human || "chưa có"}.`}</div>
                    <div className="travel-inline-actions"><button type="button" className="travel-outline-button" onClick={focusRoute}>Xem toàn tuyến</button><button type="button" className="travel-outline-button" onClick={openGoogleDirections}>Mở chỉ đường</button></div>
                    <p className="travel-source">Tuyến đường tham khảo từ {tripRes.traffic?.route_polyline_provider === "serpapi" ? "Google Maps" : "OSRM"}. Kiểm tra biển báo và điều kiện đường thực tế trước khi đi.</p>
                  </>}
                </>
              )}

              {section === "news" && (
                <>
                  <div className="travel-section-heading"><span className="travel-step">05</span><div><h2>Tin tức và dữ liệu địa phương</h2><p>Luôn xem ngày cập nhật trước khi dựa vào điểm rủi ro.</p></div></div>
                  {tripRes ? <div className={`travel-data-note ${tripRes.risk?.data_status === "fresh" ? "" : "warning"}`}>{tripRes.risk?.data_status === "fresh" ? `Có ${tripRes.risk.num_articles} bài trong ${tripRes.risk.recent_window_days} ngày gần đây về ${tripRes.to?.province_inferred || "điểm đến"}. Điểm tin tức tham khảo: ${tripRes.risk.risk_score}/10.` : tripRes.risk?.data_status === "stale" ? `Chưa có tin mới cho ${tripRes.to?.province_inferred || "điểm đến"}. Bài gần nhất: ${tripRes.risk.latest_article_date || "không rõ"}. Điểm lịch sử không đại diện cho tình hình hiện tại.` : "Chưa có dữ liệu tin tức cho điểm đến này. Không thể kết luận mức an toàn từ nguồn tin hiện có."}</div> : <div className="travel-data-note">Chọn chuyến đi hoặc tra cứu tỉnh bên dưới để xem nguồn tin đã thu thập.</div>}
                  <div className="travel-field"><label htmlFor="travel-province-search">Tra cứu một tỉnh</label><input id="travel-province-search" value={provinceQuery} onChange={(event) => setProvinceQuery(event.target.value)} placeholder="Nhập tên tỉnh" /></div>
                  <div className="travel-province-list">{matchingProvinces.slice(0, provinceQuery ? 8 : 6).map((province) => <button type="button" key={province.province} onClick={() => onPickProvince(province, { fly: true })} className={selectedProv?.province === province.province ? "selected" : ""}>{province.province}</button>)}</div>
                  {provinceQuery && !matchingProvinces.length && <p className="travel-field-hint">Không tìm thấy tỉnh phù hợp.</p>}
                  {selectedProv && <div className="travel-province-detail"><strong>{selectedProv.province}</strong>{selectedRisk ? <><p>{!selectedRisk.num_articles ? "Chưa có bài báo phù hợp trong dữ liệu đã thu thập. Không thể suy ra mức an toàn hiện tại." : selectedRisk.is_stale ? `Tin gần nhất: ${selectedRisk.latest_article_date || "không rõ"}. Dữ liệu đã cũ, không dùng điểm lịch sử để kết luận hiện tại.` : `Điểm rủi ro tin tức tham khảo: ${selectedRisk.overall_risk_score}/10 từ ${selectedRisk.num_articles} bài.`}</p>{selectedRisk.num_articles > 0 && <details><summary>Xem nhóm tin đã ghi nhận</summary><dl>{Object.entries(selectedRisk.risk_assessment || {}).map(([key, count]) => <div key={key}><dt>{RISK_NAMES[key] || key}</dt><dd>{count}</dd></div>)}</dl></details>}</> : <p>Đang tải dữ liệu tỉnh…</p>}</div>}
                  <p className="travel-source">Mô hình phân loại mức liên quan của bài báo; quy tắc xác định loại sự cố. Tin được thu thập theo đợt, không phải nguồn cảnh báo thời gian thực.</p>
                </>
              )}

              {section === "history" && (
                <>
                  <div className="travel-section-heading"><span className="travel-step">06</span><div><h2>Chuyến đi đã lưu</h2><p>Để bạn xem lại các lần tra cứu trước.</p></div></div>
                  {tripHistoryLoading ? <div className="travel-empty">Đang tải lịch sử…</div> : tripHistory.length === 0 ? <div className="travel-empty">Chưa có chuyến đi nào được lưu.</div> : <div className="travel-history">{tripHistory.map((item) => <div key={item.id}><div><strong>{item.destination}</strong><small>{new Date(item.created_at).toLocaleString("vi-VN")}</small></div><button type="button" onClick={() => deleteTripHistoryEntry(item.id)} aria-label={`Xóa chuyến đi ${item.destination}`}>Xóa</button></div>)}</div>}
                  <p className="travel-source">Kết quả cũ phản ánh dữ liệu tại thời điểm tra cứu. Hãy tra lại trước chuyến đi mới.</p>
                </>
              )}
            </section>
          </div>

          <section className="travel-map-column" aria-label="Bản đồ chuyến đi">
            <div className="travel-map-heading"><div><span>BẢN ĐỒ HÀNH TRÌNH</span><h2>{tripRes?.to?.name || "Khám phá điểm đến"}</h2></div><div className="travel-map-actions"><button type="button" onClick={focusUser} disabled={!userPos}>Điểm xuất phát</button><button type="button" onClick={focusRoute} disabled={!routeCoords?.length}>Toàn tuyến</button><button type="button" onClick={resetVN}>Đặt lại</button></div></div>
            <div className="travel-map-frame">
              <MapContainer center={VIETNAM_CENTER} zoom={6} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
                <MapMovement action={mapAction} route={routeCoords} section={section} />
                <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                {section === "news" && provinces.map((province) => <CircleMarker key={province.province} center={[province.lat, province.lon]} radius={selectedProv?.province === province.province ? 8 : 5} pathOptions={{ color: "#fff", weight: 2, fillColor: "#217a69", fillOpacity: 0.9 }} eventHandlers={{ click: () => onPickProvince(province) }}><Popup>{province.province}</Popup></CircleMarker>)}
                {userPos && <CircleMarker center={[userPos.lat, userPos.lon]} radius={9} pathOptions={{ color: "#fff", weight: 3, fillColor: "#1e5e52", fillOpacity: 1 }}><Popup>Điểm xuất phát: {originName || "vị trí đã chọn"}</Popup></CircleMarker>}
                {tripRes?.to?.lat && tripRes?.to?.lon && <CircleMarker center={[tripRes.to.lat, tripRes.to.lon]} radius={9} pathOptions={{ color: "#fff", weight: 3, fillColor: "#d89541", fillOpacity: 1 }}><Popup>Điểm đến: {tripRes.to.name}</Popup></CircleMarker>}
                {routeCoords?.length >= 2 && <Polyline positions={routeCoords} pathOptions={{ color: "#1f6b5c", weight: 5, opacity: 0.9 }} />}
              </MapContainer>
              {tripLoading && <div className="travel-map-loading" role="status">Đang kiểm tra tuyến đường và thời tiết…</div>}
            </div>
            <p className="travel-map-footnote">Bản đồ và thời gian di chuyển là thông tin tham khảo. Kiểm tra tình hình đường sá trước khi xuất phát.</p>
          </section>
        </div>
      </main>
    </div>
  );
}
