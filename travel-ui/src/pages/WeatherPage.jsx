import { Link } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTravel } from "../portal/TravelContext";
import { dateLabel, numberLabel } from "../portal/format";
import { DataState, MetricCard, PageIntro, RiskChip, SourceNote } from "../portal/UiPrimitives";

export default function WeatherPage() {
  const travel = useTravel();
  const trip = travel.tripRes;
  if (!trip) return <div className="portal-page"><PageIntro eyebrow="Thời tiết" title="Thời tiết điểm đến" /><DataState title="Chưa chọn chuyến đi" description="Lập kế hoạch để lấy dữ liệu thời tiết đúng tọa độ điểm đến." /></div>;
  const current = trip.weather?.error ? null : trip.weather;
  const day = travel.forecastData[travel.selectedDateIndex] || null;
  const display = day || current;
  const score = display?.adjusted_risk_score ?? display?.risk_score;
  const currentScore = current?.adjusted_risk_score ?? current?.risk_score;
  const pm25 = current?.pm25 ?? current?.air_quality?.pm25;
  return <div className="portal-page">
    <PageIntro eyebrow="Thời tiết" title={`Thời tiết tại ${travel.destination || trip.to?.name}`} description="Xem thời tiết hiện tại và dự báo từng ngày. Chỉ các chỉ số API đã trả về mới được hiển thị." action={<Button component={Link} to="/alerts" variant="outlined">Thiết lập cảnh báo</Button>} />
    {travel.forecastLoading && <Alert severity="info" icon={<CircularProgress size={18} />}>Đang tải dự báo 7 ngày…</Alert>}
    {current ? <><Box className="portal-section"><Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ xs: "start", sm: "center" }} sx={{ gap: 1 }}><Box><Typography component="h2" variant="h3">Thời tiết hiện tại</Typography><Typography color="text.secondary" variant="body2">Số liệu và điểm rủi ro tại thời điểm đánh giá chuyến đi.</Typography></Box><RiskChip score={currentScore} /></Stack>{current.adjusted_reason && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Lưu ý từ chỉ số hiện tại: {current.adjusted_reason.replace(/(\d)(km)\b/g, "$1 km")}</Typography>}</Box><div className="portal-grid portal-grid-four"><MetricCard title="Nhiệt độ hiện tại" value={numberLabel(current.temperature, 1, "°C")} /><MetricCard title="Mưa hiện tại" value={numberLabel(current.precipitation, 1, " mm")} /><MetricCard title="Gió hiện tại" value={numberLabel(current.wind, 1, " km/h")} /><MetricCard title="Tầm nhìn hiện tại" value={numberLabel(current.visibility_km, 1, " km")} /></div></> : <Alert severity="warning">Chưa tải được thời tiết hiện tại cho điểm đến.</Alert>}
    {!travel.forecastLoading && !travel.forecastData.length && <Alert severity="warning">Chưa lấy được dự báo nhiều ngày. Các chỉ số bên dưới, nếu có, là thông tin hiện tại.</Alert>}
    {travel.forecastData.length > 0 && <Box className="portal-section"><Typography component="h2" variant="h3" sx={{ mb: 2 }}>Dự báo 7 ngày</Typography><div className="portal-day-grid">{travel.forecastData.map((item, index) => <Button key={item.date || index} variant={index === travel.selectedDateIndex ? "contained" : "outlined"} onClick={() => travel.setSelectedDateIndex(index)} sx={{ p: 1.5, display: "grid", textAlign: "left", justifyItems: "start" }}><span>{dateLabel(item.date)}</span><strong>{item.temperature != null ? `${Math.round(item.temperature)}°C` : "Chưa có"}</strong><small>Rủi ro {item.adjusted_risk_score ?? item.risk_score ?? "—"}/10</small></Button>)}</div></Box>}
    <Box className="portal-section"><Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ xs: "start", sm: "center" }} gap={1}><Box><Typography component="h2" variant="h3">{day ? `Chỉ số dự báo ngày ${dateLabel(day.date)}` : "Chỉ số thời tiết hiện tại"}</Typography><Typography color="text.secondary" variant="body2">Điểm rủi ro do mô hình thời tiết của dự án tính từ dữ liệu Open-Meteo.</Typography></Box><RiskChip score={score} /></Stack></Box>
    {display ? <div className="portal-grid portal-grid-four">
      <MetricCard title="Nhiệt độ" value={numberLabel(display.temperature, 1, "°C")} />
      <MetricCard title="Lượng mưa" value={numberLabel(display.precipitation, 1, " mm")} />
      <MetricCard title="Tốc độ gió" value={numberLabel(display.wind, 1, " km/h")} />
      <MetricCard title="Tầm nhìn" value={numberLabel(display.visibility_km, 1, " km")} />
      <MetricCard title="Chỉ số UV" value={numberLabel(display.uv_index, 1)} />
      <MetricCard title="PM2.5 hiện tại" value={numberLabel(pm25, 1, " µg/m³")} helper="Dự báo từng ngày chưa có chỉ số PM2.5 riêng." />
      <MetricCard title="Độ ẩm" value={numberLabel(display.humidity, 1, "%")} />
      <MetricCard title="Điểm rủi ro thời tiết" value={score != null ? `${Number(score).toFixed(1)}/10` : "Chưa có"} tone={score >= 7 ? "danger" : score >= 4 ? "caution" : "default"} />
    </div> : <DataState title="Không tải được dữ liệu thời tiết" description="Bạn có thể thử đánh giá lại chuyến đi khi kết nối ổn định." severity="warning" />}
    {display?.health_advice && <Alert severity="info">{display.health_advice.replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu, "").trim()}</Alert>}
    <SourceNote>Dự báo được lấy theo tọa độ điểm đến do hệ thống xác định. Dự báo có thể thay đổi; hãy kiểm tra lại gần giờ khởi hành.</SourceNote>
  </div>;
}
