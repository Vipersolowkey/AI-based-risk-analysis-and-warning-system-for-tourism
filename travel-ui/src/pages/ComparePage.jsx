import { useState } from "react";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { apiGet } from "../api";
import { useTravel } from "../portal/TravelContext";
import { dateLabel } from "../portal/format";
import { DataState, PageIntro, RiskChip, SourceNote } from "../portal/UiPrimitives";

export default function ComparePage() {
  const { provinces } = useTravel();
  const [places, setPlaces] = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function compare() {
    if (places.length < 2) return;
    setLoading(true); setError("");
    try { const data = await apiGet(`/risk/compare?places=${encodeURIComponent(places.join(","))}`); setResults(data.results || []); }
    catch (reason) { setError(String(reason.message || reason)); setResults([]); }
    finally { setLoading(false); }
  }
  return <div className="portal-page">
    <PageIntro eyebrow="So sánh địa điểm" title="Đối chiếu dữ liệu giữa các tỉnh" description="Chọn từ hai đến bốn địa điểm. Điểm báo chí là thông tin tham khảo từ những bài đã thu thập, không phải xếp hạng an toàn thời gian thực." />
    <Box className="portal-section"><Stack direction={{ xs: "column", sm: "row" }} gap={2} alignItems={{ sm: "start" }}><Autocomplete multiple options={provinces.map((p) => p.province)} value={places} onChange={(_, value) => { setPlaces(value.slice(0, 4)); setResults([]); }} renderInput={(params) => <TextField {...params} label="Địa điểm cần so sánh" helperText="Chọn 2–4 tỉnh, thành phố" />} sx={{ flex: 1, minWidth: 0 }} /><Button variant="contained" onClick={compare} disabled={places.length < 2 || loading} startIcon={loading ? <CircularProgress size={17} color="inherit" /> : null}>So sánh</Button></Stack></Box>
    {error && <Alert severity="error">Không thể so sánh: {error}</Alert>}
    {!results.length && !loading && <DataState title="Chưa có kết quả so sánh" description="Chọn ít nhất hai địa điểm rồi nhấn So sánh." action={null} />}
    {results.length > 0 && <><Alert severity="info">Số bài và ngày cập nhật có thể khác nhau giữa các tỉnh. Điểm cao hơn chỉ cho biết mức rủi ro trong dữ liệu bài báo đã ghi nhận.</Alert><div className="portal-grid">{results.map((item) => <Box key={item.resolved || item.place} className="portal-section"><Typography component="h2" variant="h3" sx={{ mb: 1 }}>{item.resolved || item.place}</Typography><RiskChip score={item.num_articles ? item.overall_risk_score : null} /><Typography sx={{ mt: 2 }} variant="body2">{item.num_articles} bài phù hợp</Typography><Typography color="text.secondary" variant="body2">Bài gần nhất: {dateLabel(item.latest_article_date)}</Typography>{item.is_stale && <Alert severity="warning" sx={{ mt: 2 }}>{item.num_articles ? "Dữ liệu đã cũ; không dùng điểm này để kết luận hiện tại." : "Chưa có dữ liệu để đánh giá."}</Alert>}</Box>)}</div></>}
    <SourceNote>So sánh dùng trực tiếp API /risk/compare. Không có số liệu giả hay xếp hạng được tính riêng ở giao diện.</SourceNote>
  </div>;
}
