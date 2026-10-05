// Adapted from MUI's MIT-licensed Dashboard template at commit
// 27565bf06476f6ce2f8eb0c67393c67477968fa2 (Dashboard, SideMenu,
// AppNavbar and MenuContent). See THIRD_PARTY_UI.md for source and license.
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { styled } from "@mui/material/styles";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer, { drawerClasses } from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import AccountCircleOutlinedIcon from "@mui/icons-material/AccountCircleOutlined";
import AltRouteOutlinedIcon from "@mui/icons-material/AltRouteOutlined";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import CompareArrowsOutlinedIcon from "@mui/icons-material/CompareArrowsOutlined";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import MapOutlinedIcon from "@mui/icons-material/MapOutlined";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import RouteOutlinedIcon from "@mui/icons-material/RouteOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import WbCloudyOutlinedIcon from "@mui/icons-material/WbCloudyOutlined";

const WIDTH = 248;
const MainDrawer = styled(Drawer)({
  width: WIDTH,
  flexShrink: 0,
  [`& .${drawerClasses.paper}`]: { width: WIDTH, boxSizing: "border-box" },
});

const primaryItems = [
  { label: "Lập kế hoạch", path: "/plan", icon: <RouteOutlinedIcon /> },
  { label: "Kết quả rủi ro", path: "/result", icon: <ShieldOutlinedIcon /> },
  { label: "Thời tiết", path: "/weather", icon: <WbCloudyOutlinedIcon /> },
  { label: "Giao thông", path: "/traffic", icon: <AltRouteOutlinedIcon /> },
  { label: "Tin tức và sự kiện", path: "/news", icon: <ArticleOutlinedIcon /> },
  { label: "Bản đồ", path: "/map", icon: <MapOutlinedIcon /> },
];
const secondaryItems = [
  { label: "So sánh địa điểm", path: "/compare", icon: <CompareArrowsOutlinedIcon /> },
  { label: "Cảnh báo", path: "/alerts", icon: <NotificationsNoneOutlinedIcon /> },
  { label: "Lịch sử", path: "/history", icon: <HistoryOutlinedIcon /> },
];

function MenuContent({ onNavigate }) {
  const { pathname } = useLocation();
  return (
    <Stack sx={{ flexGrow: 1, px: 1.5, pb: 2, justifyContent: "space-between" }}>
      <Box>
        <Typography className="portal-nav-caption">CHUYẾN ĐI</Typography>
        <List disablePadding>
          {primaryItems.map((item) => (
            <ListItem key={item.path} disablePadding>
              <ListItemButton component={Link} to={item.path} onClick={onNavigate} selected={pathname === item.path} className="portal-nav-item">
                <ListItemIcon sx={{ minWidth: 38 }}>{item.icon}</ListItemIcon>
                <ListItemText primary={item.label} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
        <Divider sx={{ my: 2 }} />
        <Typography className="portal-nav-caption">TIỆN ÍCH</Typography>
        <List disablePadding>
          {secondaryItems.map((item) => (
            <ListItem key={item.path} disablePadding>
              <ListItemButton component={Link} to={item.path} onClick={onNavigate} selected={pathname === item.path} className="portal-nav-item">
                <ListItemIcon sx={{ minWidth: 38 }}>{item.icon}</ListItemIcon>
                <ListItemText primary={item.label} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </Box>
    </Stack>
  );
}

function Brand() {
  return (
    <Stack component={Link} to="/plan" className="portal-brand" direction="row" alignItems="center" spacing={1.25}>
      <span className="portal-brand-mark"><ShieldOutlinedIcon fontSize="small" /></span>
      <Box><Typography component="strong" variant="subtitle2">Vietnam Travel Risk</Typography><Typography component="span" variant="caption">Thông tin cho chuyến đi</Typography></Box>
    </Stack>
  );
}

export default function MuiDashboardShell({ children, themeMode, toggleTheme, logout, email, fullWidth = false }) {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const current = [...primaryItems, ...secondaryItems].find((item) => item.path === pathname);
  const sidebar = <><Brand /><MenuContent onNavigate={() => setOpen(false)} /><Divider /><Box className="portal-user"><AccountCircleOutlinedIcon fontSize="small" /><span title={email}>{email || "Tài khoản"}</span></Box><Stack direction="row" spacing={1} sx={{ p: 2, pt: 0 }}><Button variant="outlined" size="small" onClick={toggleTheme} startIcon={themeMode === "dark" ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />} sx={{ flex: 1, minWidth: 0, whiteSpace: "nowrap" }}>{themeMode === "dark" ? "Sáng" : "Tối"}</Button><Button variant="text" size="small" onClick={logout} sx={{ flex: 1, minWidth: 0, whiteSpace: "nowrap" }}>Đăng xuất</Button></Stack></>;

  return (
    <Box className="portal-shell">
      <a className="portal-skip" href="#portal-main">Bỏ qua điều hướng</a>
      <MainDrawer variant="permanent" className="portal-desktop-drawer" sx={{ display: { xs: "none", md: "block" }, [`& .${drawerClasses.paper}`]: { bgcolor: "background.paper", borderRightColor: "divider" } }}>{sidebar}</MainDrawer>
      <AppBar position="fixed" color="inherit" elevation={0} className="portal-mobile-bar" sx={{ display: { xs: "block", md: "none" }, borderBottom: "1px solid", borderColor: "divider" }}>
        <Toolbar><IconButton aria-label="Mở điều hướng" onClick={() => setOpen(true)} edge="start" sx={{ mr: 1 }}><MenuRoundedIcon /></IconButton><Typography variant="subtitle1" component="span" sx={{ fontWeight: 700, flexGrow: 1 }}>{current?.label || "Vietnam Travel Risk"}</Typography><IconButton aria-label={themeMode === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"} onClick={toggleTheme}>{themeMode === "dark" ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />}</IconButton></Toolbar>
      </AppBar>
      <Drawer open={open} onClose={() => setOpen(false)} sx={{ display: { xs: "block", md: "none" }, [`& .${drawerClasses.paper}`]: { width: WIDTH } }}>{sidebar}</Drawer>
      <Box component="main" id="portal-main" tabIndex={-1} className={`portal-main ${fullWidth ? "portal-main-map" : ""}`}>
        <Box className="portal-content">{children}</Box>
      </Box>
    </Box>
  );
}
