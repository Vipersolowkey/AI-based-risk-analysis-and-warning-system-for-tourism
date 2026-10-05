import { Link } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArrowForwardOutlinedIcon from "@mui/icons-material/ArrowForwardOutlined";
import AltRouteOutlinedIcon from "@mui/icons-material/AltRouteOutlined";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import WbCloudyOutlinedIcon from "@mui/icons-material/WbCloudyOutlined";
import { useTravel } from "../portal/TravelContext";
import { dateLabel, getVerdict } from "../portal/format";
import { DataState, MetricCard, PageIntro, SourceNote } from "../portal/UiPrimitives";

export default function ResultPage() {
  const { tripRes, destination, originName, departureDate, tripCheckedAt, forecastData } = useTravel();
  if (!tripRes) return <div className="portal-page"><PageIntro eyebrow="Kết quả rủi ro" title="Nhận định chuyến đi" /><DataState title="Chưa có đánh giá chuyến đi" description="Hãy chọn hành trình và nhấn Đánh giá chuyến đi trước." /></div>;

  const verdict = getVerdict(tripRes.recommendation);
  const weather = tripRes.weather?.error ? null : tripRes.weather;
  const travelDay = forecastData.find((day) => day.date === departureDate);
  const currentWeatherScore = weather?.adjusted_risk_score ?? weather?.risk_score;
  const forecastScore = travelDay?.adjusted_risk_score ?? travelDay?.risk_score;
  const weatherScores = [currentWeatherScore, forecastScore].filter((score) => score != null).map(Number).filter(Number.isFinite);
  const weatherScore = weatherScores.length ? Math.max(...weatherScores) : null;
  const freshNewsScore = tripRes.risk?.data_status === "fresh" ? tripRes.risk?.risk_score : null;
  const scores = [weatherScore, freshNewsScore].filter((score) => score != null).map(Number).filter(Number.isFinite);
  const highestScore = scores.length ? Math.max(...scores).toFixed(1) : null;
  const reasons = [];
  if (tripRes.traffic?.route_available === false) reasons.push("Chưa lấy được tuyến đường; hãy kiểm tra chỉ đường trước khi đi.");
  else if (tripRes.traffic?.traffic_available === false) reasons.push("Chưa có dữ liệu giao thông trực tiếp; thời gian đi chỉ là ước tính.");
  if (tripRes.risk?.data_status === "stale") reasons.push("Tin tức rủi ro đã cũ.");
  if (freshNewsScore != null && freshNewsScore >= 4) reasons.push(`Điểm tin tức mới ${Number(freshNewsScore).toFixed(1)}/10.`);
  if (weather?.visibility_km != null && weather.visibility_km < 2) reasons.push(`Tầm nhìn hiện tại ${Number(weather.visibility_km).toFixed(1)} km.`);
  if (currentWeatherScore != null && currentWeatherScore >= 4) reasons.push(`Điểm thời tiết hiện tại ${Number(currentWeatherScore).toFixed(1)}/10.`);
  if (forecastScore != null && forecastScore >= 4) reasons.push(`Dự báo ngày đi ${Number(forecastScore).toFixed(1)}/10.`);

  return <div className="portal-page">
    <PageIntro eyebrow="Kết quả rủi ro" title={`Kết quả đến ${destination || tripRes.to?.name}`} description={`${originName || "Điểm xuất phát đã chọn"} → ${tripRes.to?.name || destination} · Ngày đi dự kiến ${dateLabel(departureDate)}`} action={<Button component={Link} to="/plan" variant="outlined">Chỉnh sửa chuyến đi</Button>} />
    <Box className="portal-section" sx={{ borderLeft: "5px solid", borderLeftColor: verdict.tone === "error" ? "error.main" : verdict.tone === "warning" ? "warning.main" : "success.main" }}>
      <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ xs: "start", sm: "center" }} gap={2}>
        <Box><Chip label={verdict.label} color={verdict.tone} sx={{ fontWeight: 750, mb: 1.5 }} /><Typography component="h2" variant="h2">{verdict.vi}</Typography><Typography color="text.secondary" sx={{ mt: 1 }}>{reasons.length ? reasons.join(" ") : "Đánh giá dựa trên dữ liệu đang có; hãy xem từng yếu tố trước khi quyết định."}</Typography></Box>
        <Box sx={{ minWidth: 170 }}><Typography variant="body2" color="text.secondary">Điểm rủi ro cao nhất hiện có</Typography><Typography className="portal-metric-value">{highestScore ? `${highestScore}/10` : "Chưa có"}</Typography></Box>
      </Stack>
      <SourceNote>Kết luận GO/CAUTION/DON'T GO do API chuyến đi trả về theo điều kiện lúc tra cứu. Dự báo ngày đi là thông tin bổ sung, có thể thay đổi. Lý do bên trên tóm tắt các chỉ số có thể kiểm tra. Điểm hiển thị là điểm cao nhất giữa thời tiết hiện tại, dự báo ngày đi và tin tức còn mới; không phải điểm tổng hợp hay xác suất an toàn. Kết quả tra cứu lúc {tripCheckedAt ? new Date(tripCheckedAt).toLocaleString("vi-VN") : "không rõ"}.</SourceNote>
    </Box>
    <div className="portal-grid">
      <MetricCard to="/weather" icon={<WbCloudyOutlinedIcon />} title="Thời tiết" value={weatherScore != null ? `${Number(weatherScore).toFixed(1)}/10` : "Chưa có"} helper={travelDay ? `Điểm cao hơn giữa hiện tại và dự báo ${dateLabel(departureDate)}` : "Dữ liệu hiện tại; ngày đi chưa có dự báo tương ứng"} tone={weatherScore >= 7 ? "danger" : weatherScore >= 4 ? "caution" : "default"} />
      <MetricCard to="/traffic" icon={<AltRouteOutlinedIcon />} title="Giao thông" value={tripRes.traffic?.distance_km != null ? `${tripRes.traffic.distance_km} km` : "Chưa có"} helper={tripRes.traffic?.route_available === false ? "Chưa lấy được tuyến đường" : tripRes.traffic?.traffic_available === false ? "Thời gian chỉ là ước tính" : "Mở để xem tình trạng tuyến đường"} />
      <MetricCard to="/news" icon={<ArticleOutlinedIcon />} title="Tin tức địa phương" value={tripRes.risk?.data_status === "fresh" ? `${tripRes.risk.num_articles} bài mới` : tripRes.risk?.data_status === "stale" ? "Dữ liệu đã cũ" : "Chưa có dữ liệu"} helper={tripRes.risk?.latest_article_date ? `Bài gần nhất: ${dateLabel(tripRes.risk.latest_article_date)}` : "Xem tình trạng dữ liệu tin tức"} />
    </div>
    <Alert severity={verdict.tone === "error" ? "error" : "warning"}>Nhận định này hỗ trợ chuẩn bị chuyến đi, không thay thế thông báo của cơ quan chức năng hoặc tình hình thực tế trên đường.</Alert>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}><Button component={Link} to="/weather" variant="contained" endIcon={<ArrowForwardOutlinedIcon />}>Xem thời tiết</Button><Button component={Link} to="/map" variant="outlined">Xem bản đồ hành trình</Button></Stack>
  </div>;
}
