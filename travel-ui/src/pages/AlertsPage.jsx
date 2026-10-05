import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { apiGet } from "../api";
import { checkNow, getCurrentPushSubscription } from "../push";
import { useTravel } from "../portal/TravelContext";
import { DataState, PageIntro, SourceNote } from "../portal/UiPrimitives";

export default function AlertsPage() {
  const travel = useTravel();
  const token = travel.session?.user?.token;
  const destination = travel.tripRes?.to;
  const [configuration, setConfiguration] = useState("loading");
  const [subscriptions, setSubscriptions] = useState([]);
  const [subscriptionsLoading, setSubscriptionsLoading] = useState(true);
  const [subscriptionsError, setSubscriptionsError] = useState("");
  const [currentEndpoint, setCurrentEndpoint] = useState("");
  const [refreshCount, setRefreshCount] = useState(0);
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiGet("/api/notifications/vapid-public-key")
      .then((data) => { if (active) setConfiguration(data.publicKey ? "ready" : "missing"); })
      .catch(() => { if (active) setConfiguration("error"); });
    if (!token) {
      setSubscriptions([]);
      setSubscriptionsLoading(false);
      return () => { active = false; };
    }
    setSubscriptionsLoading(true);
    Promise.allSettled([
      apiGet("/api/notifications/subscriptions", token),
      getCurrentPushSubscription(),
    ]).then(([stored, browser]) => {
      if (!active) return;
      if (stored.status === "fulfilled") {
        setSubscriptions(stored.value.subscriptions || []);
        setSubscriptionsError("");
      } else {
        setSubscriptionsError("Chưa kiểm tra được trạng thái đăng ký. Hãy thử tải lại trang.");
      }
      setCurrentEndpoint(browser.status === "fulfilled" ? browser.value?.endpoint || "" : "");
      setSubscriptionsLoading(false);
    });
    return () => { active = false; };
  }, [token, travel.pushStatus, refreshCount]);

  const enabledHere = Boolean(destination && currentEndpoint && subscriptions.some((subscription) =>
    subscription.endpoint === currentEndpoint
    && Math.abs(Number(subscription.lat) - Number(destination.lat)) < 0.001
    && Math.abs(Number(subscription.lon) - Number(destination.lon)) < 0.001
  ));
  const enabled = enabledHere || (travel.pushStatus === "enabled" && subscriptionsLoading);

  async function enable() {
    await travel.enableWeatherAlerts();
    setRefreshCount((count) => count + 1);
  }

  async function disable() {
    await travel.disableWeatherAlerts();
    setRefreshCount((count) => count + 1);
  }

  async function runCheck() {
    setChecking(true);
    setError("");
    setCheckResult(null);
    try {
      setCheckResult(await checkNow(token));
    } catch (reason) {
      setError(String(reason.message || reason));
    } finally {
      setChecking(false);
    }
  }

  return <div className="portal-page">
    <PageIntro eyebrow="Cảnh báo" title="Theo dõi thời tiết điểm đến" description="Bật thông báo cho điểm đến đã chọn. Hệ thống chỉ gửi cảnh báo khi đánh giá thời tiết đạt mức nghiêm trọng." />
    {configuration === "loading" && <Alert severity="info" icon={<CircularProgress size={18} />}>Đang kiểm tra khả năng gửi thông báo…</Alert>}
    {configuration === "missing" && <Alert severity="warning">Máy chủ chưa bật tính năng thông báo. Bạn vẫn có thể xem dự báo thời tiết.</Alert>}
    {configuration === "error" && <Alert severity="error">Chưa kết nối được dịch vụ thông báo. Hãy thử tải lại trang.</Alert>}
    {!travel.canNotify && <Alert severity="warning">Tài khoản hoặc trình duyệt này chưa hỗ trợ thông báo đẩy. Bạn vẫn có thể xem dự báo thời tiết.</Alert>}
    {subscriptionsError && <Alert severity="warning">{subscriptionsError}</Alert>}

    {!destination ? <DataState title="Chưa có điểm đến để theo dõi" description="Đánh giá một chuyến đi trước khi bật cảnh báo." /> : <Box className="portal-section">
      <Typography component="h2" variant="h3">Điểm đến đang chọn</Typography>
      <Typography sx={{ mt: 1, mb: 2 }}>{destination.name}</Typography>
      {enabledHere && <Alert severity="success" sx={{ mb: 2 }}>Thiết bị này đã đăng ký theo dõi thời tiết cho điểm đến trên.</Alert>}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <Button variant="contained" onClick={enable} disabled={!travel.canNotify || configuration !== "ready" || subscriptionsLoading || travel.pushStatus === "loading" || enabled} startIcon={travel.pushStatus === "loading" ? <CircularProgress size={17} color="inherit" /> : null}>
          {enabled ? "Đã đăng ký cảnh báo" : travel.pushStatus === "loading" ? "Đang đăng ký…" : "Bật cảnh báo thời tiết"}
        </Button>
        {currentEndpoint && <Button variant="outlined" color="error" onClick={disable} disabled={travel.pushStatus === "loading"}>Tắt trên thiết bị này</Button>}
        <Button component={Link} to="/weather" variant="outlined">Xem dự báo</Button>
      </Stack>
      {travel.pushStatus === "denied" && <Alert severity="warning" sx={{ mt: 2 }}>Trình duyệt đã từ chối quyền thông báo. Hãy cho phép thông báo trong cài đặt trình duyệt rồi thử lại.</Alert>}
      {travel.pushStatus === "error" && <Alert severity="error" sx={{ mt: 2 }}>Chưa đăng ký được cảnh báo. Hãy kiểm tra kết nối và thử lại.</Alert>}
    </Box>}

    <Box className="portal-section">
      <Typography component="h2" variant="h3" sx={{ mb: 1 }}>Kiểm tra cảnh báo ngay</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Kiểm tra thời tiết tại các điểm đến đã đăng ký trên tài khoản này.</Typography>
      <Button variant="outlined" onClick={runCheck} disabled={configuration !== "ready" || !token || subscriptionsLoading || subscriptions.length === 0 || checking} startIcon={checking ? <CircularProgress size={17} /> : null}>{checking ? "Đang kiểm tra…" : "Kiểm tra ngay"}</Button>
      {!subscriptionsLoading && subscriptions.length === 0 && <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>Chưa có điểm đến nào được đăng ký.</Typography>}
      {checkResult && <Alert severity={checkResult.failed ? "warning" : "info"} sx={{ mt: 2 }}>Đã kiểm tra {checkResult.checked} điểm đến; gửi {checkResult.alerted} cảnh báo{checkResult.skipped_recent ? `; ${checkResult.skipped_recent} cảnh báo đã gửi gần đây nên không gửi lặp` : ""}{checkResult.failed ? `; ${checkResult.failed} điểm chưa kiểm tra được` : ""}.</Alert>}
      {error && <Alert severity="error" sx={{ mt: 2 }}>Chưa kiểm tra được cảnh báo: {error}</Alert>}
    </Box>
    <SourceNote>Ứng dụng tự kiểm tra khoảng 30 phút một lần khi trang web đang mở. Khi đóng trang, việc kiểm tra tự động tạm dừng. Đây không phải hệ thống cảnh báo khẩn cấp chính thức.</SourceNote>
  </div>;
}
