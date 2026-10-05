import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import { apiGet } from "../api";
import HeatmapLayer from "../components/HeatmapLayer";
import { useTravel } from "../portal/TravelContext";
import { PageIntro, SourceNote } from "../portal/UiPrimitives";

const VN_CENTER = [16.2, 107.8];

function MapController({ action, route }) {
  const map = useMap();
  useEffect(() => {
    const timer = setTimeout(() => map.invalidateSize(), 120);
    return () => clearTimeout(timer);
  }, [map]);
  useEffect(() => {
    if (action?.type === "flyTo" && action.center) map.flyTo(action.center, action.zoom || 9);
    else if (action?.type === "resetVN") map.flyTo(VN_CENTER, 6);
    else if (action?.type === "fitBounds" && action.bounds?.length >= 2) map.fitBounds(action.bounds, { padding: [40, 40] });
  }, [action, map]);
  useEffect(() => { if (route?.length >= 2) map.fitBounds(route, { padding: [40, 40] }); }, [map, route]);
  return null;
}

export default function MapPage() {
  const travel = useTravel();
  const [heatPoints, setHeatPoints] = useState([]);
  const [heatLoading, setHeatLoading] = useState(true);
  const [heatError, setHeatError] = useState("");
  const [showHeat, setShowHeat] = useState(false);
  const [showProvinces, setShowProvinces] = useState(false);
  useEffect(() => {
    let alive = true;
    apiGet("/map/heat").then((data) => { if (alive) { setHeatPoints(data.points || []); setHeatLoading(false); } }).catch((error) => { if (alive) { setHeatError(String(error.message || error)); setHeatLoading(false); } });
    return () => { alive = false; };
  }, []);
  const trip = travel.tripRes;
  const hasRouteGeometry = Boolean(trip?.traffic?.route_polyline);
  return <div className="portal-page">
    <PageIntro eyebrow="Bản đồ và tuyến đường" title={trip?.to?.name ? `Bản đồ đến ${travel.destination || trip.to.name}` : "Bản đồ Việt Nam"} description="Bản đồ chỉ xuất hiện tại trang này. Các lớp rủi ro phản ánh bài báo đã thu thập, không phải cảnh báo thời gian thực." />
    <Box className="portal-section" sx={{ py: 1.3 }}><Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ xs: "start", sm: "center" }} sx={{ gap: 1.5 }}><Stack direction="row" flexWrap="wrap" sx={{ gap: 1 }}><Button variant="outlined" onClick={travel.focusUser} disabled={!travel.userPos} sx={{ whiteSpace: "nowrap", px: 1 }}>Điểm xuất phát</Button><Button variant="outlined" onClick={travel.focusRoute} disabled={!travel.routeCoords.length} sx={{ whiteSpace: "nowrap", px: 1 }}>Toàn tuyến</Button><Button variant="text" onClick={travel.resetVN} sx={{ whiteSpace: "nowrap", px: 1 }}>Đặt lại</Button></Stack><Stack direction="row" flexWrap="wrap" sx={{ gap: 1 }}><FormControlLabel control={<Switch checked={showProvinces} onChange={(event) => setShowProvinces(event.target.checked)} />} label="Mốc tỉnh" /><FormControlLabel control={<Switch checked={showHeat} onChange={(event) => setShowHeat(event.target.checked)} disabled={!heatPoints.length} />} label="Lớp rủi ro" /></Stack></Stack></Box>
    {heatLoading && <Alert severity="info" icon={<CircularProgress size={18} />}>Đang tải lớp rủi ro…</Alert>}
    {heatError && <Alert severity="warning">Không tải được lớp rủi ro: {heatError}. Bản đồ và tuyến đường vẫn có thể sử dụng.</Alert>}
    {!hasRouteGeometry && travel.routeCoords.length >= 2 && <Alert severity="warning">Chưa có hình tuyến đường chi tiết. Đường nét đứt chỉ nối điểm đầu và điểm đến, không phải lộ trình lái xe.</Alert>}
    <div className="portal-map-frame">
      <MapContainer center={VN_CENTER} zoom={6} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
        <MapController action={travel.mapAction} route={travel.routeCoords} />
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {showHeat && heatPoints.length > 0 && <HeatmapLayer points={heatPoints} />}
        {showProvinces && travel.provinces.map((p) => <CircleMarker key={p.province} center={[p.lat, p.lon]} radius={6} pathOptions={{ color: "#fff", weight: 2, fillColor: "#277a64", fillOpacity: 1 }} eventHandlers={{ click: () => travel.onPickProvince(p) }}><Popup><strong>{p.province}</strong>{travel.selectedProv?.province === p.province && <p>{travel.selectedRisk ? `${travel.selectedRisk.num_articles} bài đã ghi nhận. ${travel.selectedRisk.is_stale ? "Dữ liệu đã cũ." : `Điểm báo chí: ${travel.selectedRisk.overall_risk_score}/10.`}` : "Đang tải dữ liệu…"}</p>}</Popup></CircleMarker>)}
        {travel.userPos && <CircleMarker center={[travel.userPos.lat, travel.userPos.lon]} radius={10} pathOptions={{ color: "#fff", weight: 3, fillColor: "#176b58", fillOpacity: 1 }}><Popup>Điểm xuất phát: {travel.originName || "Vị trí đã chọn"}</Popup></CircleMarker>}
        {trip?.to?.lat != null && trip?.to?.lon != null && <CircleMarker center={[trip.to.lat, trip.to.lon]} radius={10} pathOptions={{ color: "#fff", weight: 3, fillColor: "#b7702f", fillOpacity: 1 }}><Popup>Điểm đến: {trip.to.name}</Popup></CircleMarker>}
        {travel.routeCoords.length >= 2 && <Polyline positions={travel.routeCoords} pathOptions={{ color: "#176b58", weight: 5, opacity: .9, dashArray: hasRouteGeometry ? undefined : "9 8" }} />}
      </MapContainer>
    </div>
    <Box className="portal-section"><Typography component="h2" variant="h3">Chú thích bản đồ</Typography><Stack direction={{ xs: "column", sm: "row" }} sx={{ mt: 1, gap: 2 }}><Typography variant="body2">Màu xanh: điểm xuất phát và tuyến tham khảo.</Typography><Typography variant="body2">Màu cam: điểm đến.</Typography><Typography variant="body2">Lớp nhiệt: điểm báo chí lịch sử theo tỉnh.</Typography></Stack><SourceNote>Bản đồ nền © OpenStreetMap. Lớp rủi ro lấy từ API /map/heat và có thể chứa bài báo cũ; không dùng để quyết định an toàn tức thời.</SourceNote></Box>
  </div>;
}
