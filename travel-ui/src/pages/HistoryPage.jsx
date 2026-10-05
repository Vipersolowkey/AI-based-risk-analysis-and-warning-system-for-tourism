import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTravel } from "../portal/TravelContext";
import { getVerdict } from "../portal/format";
import { DataState, PageIntro, SourceNote } from "../portal/UiPrimitives";

export default function HistoryPage() {
  const travel = useTravel();
  const [toDelete, setToDelete] = useState(null);
  async function remove() { if (!toDelete) return; await travel.deleteTripHistoryEntry(toDelete.id); setToDelete(null); }
  return <div className="portal-page">
    <PageIntro eyebrow="Lịch sử chuyến đi" title="Các lần tra cứu đã lưu" description="Mỗi kết quả phản ánh dữ liệu tại thời điểm tra cứu. Hãy đánh giá lại trước khi khởi hành." action={<Button variant="outlined" onClick={travel.loadTripHistory}>Tải lại</Button>} />
    {travel.tripHistoryLoading && <Alert severity="info" icon={<CircularProgress size={18} />}>Đang tải lịch sử…</Alert>}
    {travel.tripHistoryError && <Alert severity="error">Không tải được lịch sử: {travel.tripHistoryError}</Alert>}
    {!travel.tripHistoryLoading && !travel.tripHistoryError && travel.tripHistory.length === 0 && <DataState title="Chưa có chuyến đi nào được lưu" description="Sau khi đánh giá khi đã đăng nhập, chuyến đi sẽ xuất hiện ở đây." />}
    {travel.tripHistory.length > 0 && <Box className="portal-section"><Stack spacing={0}>{travel.tripHistory.map((item) => { const verdict = getVerdict(item.recommendation); return <Box key={item.id} sx={{ py: 2, borderBottom: "1px solid", borderColor: "divider", display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 2 }}><Box><Typography component="h2" variant="h3">{item.destination}</Typography><Typography color="text.secondary" variant="body2">{new Date(item.created_at).toLocaleString("vi-VN")}</Typography><Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }}><Chip size="small" label={verdict.label} color={verdict.tone} variant="outlined" />{item.weather_risk_score != null && <Chip size="small" label={`Thời tiết ${item.weather_risk_score}/10`} variant="outlined" />}{item.risk_score != null && <Chip size="small" label={`Tin tức ${item.risk_score}/10`} variant="outlined" />}</Stack></Box><Button color="error" variant="text" onClick={() => setToDelete(item)}>Xóa</Button></Box>; })}</Stack></Box>}
    <SourceNote>Lịch sử không tự cập nhật theo tin tức hoặc thời tiết mới. Trước một chuyến đi mới, hãy lập kế hoạch và đánh giá lại.</SourceNote>
    <Dialog open={Boolean(toDelete)} onClose={() => setToDelete(null)} aria-labelledby="delete-trip-title"><DialogTitle id="delete-trip-title">Xóa chuyến đi đã lưu?</DialogTitle><DialogContent>Chuyến đi “{toDelete?.destination}” sẽ bị xóa khỏi lịch sử tài khoản.</DialogContent><DialogActions><Button onClick={() => setToDelete(null)}>Hủy</Button><Button color="error" variant="contained" onClick={remove}>Xóa</Button></DialogActions></Dialog>
  </div>;
}
