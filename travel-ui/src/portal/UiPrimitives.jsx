// MetricCard adapts the card title/value/content structure of MUI Dashboard
// StatCard.tsx (MIT). Demo trends and data have been removed.
import { Link } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

export function PageIntro({ eyebrow, title, description, action }) {
  return <header className="portal-page-header"><p className="portal-eyebrow">{eyebrow}</p><Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ xs: "start", sm: "center" }} flexWrap="wrap" sx={{ gap: 2 }}><Typography component="h1" variant="h1" sx={{ minWidth: 0, flex: { xs: "0 1 auto", sm: action ? "1 1 480px" : "1 1 auto" } }}>{title}</Typography>{action}</Stack>{description && <Typography component="p" variant="body1">{description}</Typography>}</header>;
}

export function MetricCard({ title, value, helper, tone = "default", icon, to }) {
  const inner = <CardContent sx={{ p: "20px !important" }}><Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ gap: 1 }}><Typography component="h2" variant="body2" color="text.secondary" fontWeight={650}>{title}</Typography>{icon && <Box aria-hidden="true" sx={{ color: tone === "danger" ? "error.main" : tone === "caution" ? "warning.main" : "primary.main" }}>{icon}</Box>}</Stack><Typography component="p" className="portal-metric-value" sx={{ mt: 1, color: tone === "danger" ? "error.main" : tone === "caution" ? "warning.dark" : "text.primary" }}>{value ?? "Chưa có dữ liệu"}</Typography>{helper && <Typography component="p" variant="body2" color="text.secondary" sx={{ mt: 1 }}>{helper}</Typography>}</CardContent>;
  return <Card component={to ? Link : "div"} to={to} variant="outlined" className={to ? "portal-card-link" : ""}>{inner}</Card>;
}

export function DataState({ title, description, action = "/plan", actionLabel = "Lập kế hoạch chuyến đi", severity = "info" }) {
  return <Alert severity={severity} variant="outlined" action={action ? <Button component={Link} to={action} size="small">{actionLabel}</Button> : null}><strong>{title}</strong>{description && <div>{description}</div>}</Alert>;
}

export function SourceNote({ children }) {
  return <Typography component="p" variant="body2" color="text.secondary" sx={{ mt: 2 }}>{children}</Typography>;
}

export function RiskChip({ score }) {
  if (score == null) return <Chip label="Chưa có điểm" size="small" variant="outlined" />;
  const n = Number(score);
  return <Chip label={`${n.toFixed(1)}/10 · ${n >= 7 ? "Cao" : n >= 4 ? "Cần lưu ý" : "Thấp"}`} size="small" color={n >= 7 ? "error" : n >= 4 ? "warning" : "success"} variant="outlined" />;
}

