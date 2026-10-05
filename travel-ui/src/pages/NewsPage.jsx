import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { apiGet } from "../api";
import { useTravel } from "../portal/TravelContext";
import { dateLabel } from "../portal/format";
import { DataState, MetricCard, PageIntro, RiskChip, SourceNote } from "../portal/UiPrimitives";

const GROUP_NAMES = { Pricing_Issue: "Giá cả", Environmental_Cleanliness: "Môi trường", Safety_Security: "An ninh", Natural_Disaster: "Thiên tai", Fire_Accident_Risk: "Tai nạn, cháy nổ" };

export default function NewsPage() {
  const travel = useTravel();
  const [place, setPlace] = useState(() => travel.tripRes?.to?.province_inferred || travel.selectedProv?.province || "");
  const [summary, setSummary] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(Boolean(place));
  const [error, setError] = useState("");

  useEffect(() => {
    if (!place) return;
    let alive = true;
    Promise.all([apiGet(`/risk?place=${encodeURIComponent(place)}`), apiGet(`/risk/events?place=${encodeURIComponent(place)}&limit=12`)]).then(([risk, articles]) => {
      if (!alive) return;
      setSummary(risk);
      setEvents(articles.events || []);
      setLoading(false);
    }).catch((reason) => { if (alive) { setError(String(reason.message || reason)); setLoading(false); } });
    return () => { alive = false; };
  }, [place]);

  function selectPlace(value) { setPlace(value); setSummary(null); setEvents([]); setError(""); setLoading(Boolean(value)); }
  return <div className="portal-page">
    <PageIntro eyebrow="Tin tức và sự kiện" title="Thông tin địa phương đã ghi nhận" description="Các bài báo trong bộ dữ liệu của dự án có tiêu đề nêu rõ rủi ro và địa danh, kèm ngày và tên miền nguồn. Tin cũ không đại diện cho tình hình hiện tại." />
    <Box className="portal-section"><TextField select fullWidth label="Chọn địa điểm" value={place} onChange={(event) => selectPlace(event.target.value)} helperText="Bạn có thể tra cứu từng tỉnh trong dữ liệu hiện có."><MenuItem value="">Chọn tỉnh, thành phố</MenuItem>{travel.provinces.map((p) => <MenuItem key={p.province} value={p.province}>{p.province}</MenuItem>)}{place && !travel.provinces.some((p) => p.province === place) && <MenuItem value={place}>{place}</MenuItem>}</TextField></Box>
    {!place && <DataState title="Chọn địa điểm để xem tin tức" action={null} />}
    {loading && <Alert severity="info" icon={<CircularProgress size={18} />}>Đang tải tin tức và đánh giá địa phương…</Alert>}
    {error && <Alert severity="error">Không tải được dữ liệu: {error}</Alert>}
    {summary && <><Alert severity={summary.is_stale ? "warning" : "info"}>{summary.num_articles === 0 ? "Chưa có bài báo được hệ thống phân loại cho địa điểm này. Không thể suy ra mức an toàn từ việc thiếu tin." : summary.is_stale ? `Bài gần nhất ngày ${dateLabel(summary.latest_article_date)}. Dữ liệu đã cũ; điểm lịch sử không phản ánh tình hình hiện tại.` : `${summary.num_articles} bài được hệ thống phân loại; bài gần nhất ngày ${dateLabel(summary.latest_article_date)}.`}</Alert><div className="portal-grid"><MetricCard title="Bài được AI phân loại" value={summary.num_articles} /><MetricCard title="Bài gần nhất" value={dateLabel(summary.latest_article_date)} /><MetricCard title="Điểm rủi ro báo chí" value={summary.is_stale || summary.num_articles === 0 ? "Không dùng hiện tại" : `${summary.overall_risk_score}/10`} helper={summary.is_stale ? "Chỉ dùng để tham khảo lịch sử" : "Tính từ các bài trong dữ liệu"} /></div></>}
    {summary && <Box className="portal-section"><Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} sx={{ mb: 2 }}><Typography component="h2" variant="h3">Bài có tiêu đề nêu rõ rủi ro</Typography>{!summary.is_stale && summary.num_articles > 0 && <RiskChip score={summary.overall_risk_score} />}</Stack>{events.length ? <div className="portal-news-list">{events.map((event) => <article className="portal-news-item" key={event.id}><Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" gap={1}><Typography component="h3" variant="subtitle1" fontWeight={700}>{event.url ? <a href={event.url} target="_blank" rel="noopener noreferrer">{event.title}</a> : event.title}</Typography>{event.risk_score != null && <RiskChip score={event.risk_score} />}</Stack><Stack direction="row" flexWrap="wrap" gap={1} sx={{ my: 1 }}><Chip size="small" variant="outlined" label={dateLabel(event.date)} /><Chip size="small" variant="outlined" label={event.source || "Nguồn chưa rõ"} />{(event.risk_groups || []).map((group) => <Chip key={group} size="small" label={GROUP_NAMES[group] || group} />)}</Stack></article>)}</div> : <DataState title="Chưa có tiêu đề nêu rõ rủi ro" description="Chưa có bài báo trong dữ liệu nêu rõ một sự cố ở tiêu đề. Điều này không có nghĩa là địa điểm an toàn." action={null} />}</Box>}
    <SourceNote>Danh sách lấy từ dữ liệu bài báo hiện có trong FastAPI. Để giảm gắn nhầm sự kiện, API chỉ đưa vào danh sách bài có tiêu đề nêu rủi ro và địa danh. Mô hình AI vẫn tự chấm điểm, gắn nhóm; việc phân loại có thể sai và chưa được biên tập xác minh. Mở nguồn gốc để tự kiểm tra. Đây không phải dòng tin thời gian thực.</SourceNote>
  </div>;
}
