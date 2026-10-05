import { useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import MyLocationOutlinedIcon from "@mui/icons-material/MyLocationOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import { TRIP_PURPOSES } from "../components/tripPurposeConfig";
import { useTravel } from "../portal/TravelContext";
import { PageIntro, SourceNote } from "../portal/UiPrimitives";

export default function PlanPage() {
  const travel = useTravel();
  const navigate = useNavigate();
  const originValue = travel.originName || "";

  async function submit(event) {
    event.preventDefault();
    const result = await travel.checkTrip();
    if (result) navigate("/result");
  }

  return <div className="portal-page">
    <PageIntro eyebrow="Lập kế hoạch" title="Đi đâu, đi như thế nào, cần lưu ý gì?" description="Chọn hành trình của bạn để xem đánh giá từ dữ liệu thời tiết, tuyến đường và tin tức hiện có." />
    <div className="portal-grid portal-grid-two">
      <Box component="form" onSubmit={submit} className="portal-section" sx={{ display: "grid", gap: 2.2, alignContent: "start" }}>
        <Typography component="h2" variant="h3">Thông tin chuyến đi</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems="stretch">
          <TextField select fullWidth label="Điểm xuất phát" value={originValue} onChange={(event) => { const p = travel.provinces.find((item) => item.province === event.target.value); if (p) travel.chooseOrigin({ label: p.province, lat: p.lat, lon: p.lon }); }} helperText={travel.originName ? `Đang dùng: ${travel.originName}` : "Chọn tỉnh hoặc dùng vị trí hiện tại"}>
            <MenuItem value="" disabled>Chọn tỉnh, thành phố</MenuItem>
            {originValue && !travel.provinces.some((p) => p.province === originValue) && <MenuItem value={originValue}>{originValue} (đang dùng)</MenuItem>}
            {travel.provinces.map((p) => <MenuItem key={p.province} value={p.province}>{p.province}</MenuItem>)}
          </TextField>
          <Button variant="outlined" startIcon={travel.gpsLoading ? <CircularProgress size={16} /> : <MyLocationOutlinedIcon />} onClick={travel.getGPS} disabled={travel.gpsLoading} sx={{ minWidth: { sm: 160 }, alignSelf: { sm: "start" }, mt: { sm: 1 } }}>{travel.gpsLoading ? "Đang lấy vị trí" : "Dùng GPS"}</Button>
        </Stack>
        <TextField label="Điểm đến" value={travel.destination} onChange={(event) => travel.updateDestination(event.target.value)} placeholder="Ví dụ: Đà Lạt, Nha Trang" fullWidth required autoComplete="off" helperText="Có thể nhập tên thành phố hoặc điểm đến cụ thể tại Việt Nam." />
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
          <TextField type="date" label="Ngày đi dự kiến" value={travel.departureDate} onChange={(event) => travel.updateDepartureDate(event.target.value)} fullWidth required slotProps={{ inputLabel: { shrink: true } }} helperText="Dự báo thời tiết chi tiết chỉ có cho những ngày dữ liệu còn hiệu lực." />
          <TextField select label="Mục đích chuyến đi" value={travel.tripPurpose || ""} onChange={(event) => travel.updatePurpose(event.target.value || null)} fullWidth helperText="Giúp điều chỉnh lưu ý thời tiết, không thay đổi cảnh báo nguy hiểm.">
            <MenuItem value="">Chuyến đi thông thường</MenuItem>
            {TRIP_PURPOSES.map((purpose) => <MenuItem key={purpose.key} value={purpose.key}>{purpose.label}</MenuItem>)}
          </TextField>
        </Stack>
        <Button size="large" variant="contained" type="submit" startIcon={travel.tripLoading ? <CircularProgress size={17} color="inherit" /> : <SearchOutlinedIcon />} disabled={!travel.canTrip || travel.tripLoading}>{travel.tripLoading ? "Đang tổng hợp dữ liệu…" : "Đánh giá chuyến đi"}</Button>
        {!travel.canTrip && <Typography variant="body2" color="text.secondary">Chọn điểm xuất phát và nhập điểm đến để tiếp tục.</Typography>}
      </Box>
      <Box className="portal-section" sx={{ display: "grid", alignContent: "start", gap: 2 }}>
        <Typography component="h2" variant="h3">Bạn sẽ nhận được gì?</Typography>
        <Divider />
        <Stack spacing={2.2}>
          <Box><Typography fontWeight={700}>01 · Nhận định ngắn gọn</Typography><Typography color="text.secondary" variant="body2">Kết luận GO, CAUTION hoặc DON'T GO kèm lý do từ các nguồn dữ liệu đang có.</Typography></Box>
          <Box><Typography fontWeight={700}>02 · Xem từng yếu tố</Typography><Typography color="text.secondary" variant="body2">Thời tiết, giao thông, tin tức và bản đồ nằm ở các trang riêng để bạn chủ động xem khi cần.</Typography></Box>
          <Box><Typography fontWeight={700}>03 · Biết giới hạn dữ liệu</Typography><Typography color="text.secondary" variant="body2">Tin đã cũ, dữ liệu thiếu hoặc thời gian di chuyển chỉ là ước tính đều được ghi rõ.</Typography></Box>
        </Stack>
        {travel.tripRes && <Alert severity="info">Bạn đã có kết quả cho chuyến đi trước. Nếu thay đổi thông tin ở đây, hãy đánh giá lại để cập nhật kết quả.</Alert>}
        <SourceNote>Ngày đi là thông tin lập kế hoạch. Đánh giá giao thông và tin tức phản ánh dữ liệu hiện có, không phải dự báo chắc chắn cho một ngày trong tương lai.</SourceNote>
      </Box>
    </div>
  </div>;
}
