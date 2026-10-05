import { Link } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTravel } from "../portal/TravelContext";
import { numberLabel } from "../portal/format";
import { DataState, MetricCard, PageIntro, SourceNote } from "../portal/UiPrimitives";

function trafficName(code) {
  if (code === "heavy") return "Ùn tắc nặng";
  if (code === "moderate") return "Di chuyển chậm";
  if (code === "light" || code === "normal") return "Tương đối thông thoáng";
  return "Chưa có tình trạng trực tiếp";
}

export default function TrafficPage() {
  const travel = useTravel();
  const trip = travel.tripRes;
  if (!trip) return <div className="portal-page"><PageIntro eyebrow="Giao thông" title="Tình trạng tuyến đường" /><DataState title="Chưa có tuyến đường" description="Đánh giá một chuyến đi để xem quãng đường và thời gian di chuyển." /></div>;
  const traffic = trip.traffic || {};
  const live = traffic.traffic_available === true;
  const routeUnavailable = traffic.route_available === false;
  return <div className="portal-page">
    <PageIntro eyebrow="Giao thông" title={`Tuyến đường đến ${travel.destination || trip.to?.name}`} description={`${travel.originName || "Điểm xuất phát"} → ${trip.to?.name || travel.destination}. Thời gian có thể đổi theo tình hình đường thực tế.`} action={<Button component={Link} to="/map" variant="contained">Mở bản đồ</Button>} />
    <Alert severity={live ? "info" : "warning"}>{routeUnavailable ? "Dịch vụ định tuyến hiện chưa phản hồi. Chưa có quãng đường hoặc thời gian di chuyển đáng tin cậy; hãy mở chỉ đường và kiểm tra trước khi đi." : live ? `Tình trạng tuyến đường: ${trafficName(traffic.status_code || traffic.status)}. Thời gian có tính đến dữ liệu giao thông của nhà cung cấp.` : "Chưa có dữ liệu giao thông trực tiếp. Thời gian bên dưới là ước tính theo tuyến đường, không phản ánh kẹt xe hiện tại."}</Alert>
    <div className="portal-grid portal-grid-four">
      <MetricCard title="Quãng đường" value={numberLabel(traffic.distance_km, 1, " km")} />
      <MetricCard title="Thời gian thông thường" value={traffic.time_normal_human || "Chưa có"} />
      <MetricCard title={live ? "Thời gian theo giao thông" : "Thời gian trực tiếp"} value={live ? traffic.time_traffic_human || "Chưa có" : "Không có dữ liệu"} />
      <MetricCard title="Chậm trễ ước tính" value={live ? numberLabel(traffic.delay_min, 0, " phút") : "Không có dữ liệu"} />
    </div>
    <Box className="portal-section"><Typography component="h2" variant="h3" sx={{ mb: 1 }}>Về tuyến đường này</Typography><Typography variant="body1">{traffic.route_polyline ? "Tuyến đường đã được hiển thị trên trang Bản đồ." : "Chưa có hình tuyến đường chi tiết. Bản đồ sẽ hiển thị điểm xuất phát và điểm đến nếu có tọa độ."}</Typography><SourceNote>{routeUnavailable ? "Chưa có nguồn tuyến đường khả dụng." : `Nguồn tuyến đường: ${traffic.route_polyline_provider === "serpapi" ? "Google Maps qua SerpAPI" : traffic.route_polyline_provider === "trackasia" ? "TrackAsia" : traffic.route_polyline_provider === "osrm" ? "OSRM" : traffic.traffic_source || "chưa rõ"}.`} Hãy đối chiếu chỉ đường và biển báo thực tế trước khi đi.</SourceNote></Box>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}><Button component={Link} to="/map" variant="contained">Xem bản đồ toàn tuyến</Button><Button variant="outlined" onClick={travel.openGoogleDirections}>Mở chỉ đường ngoài ứng dụng</Button></Stack>
  </div>;
}
