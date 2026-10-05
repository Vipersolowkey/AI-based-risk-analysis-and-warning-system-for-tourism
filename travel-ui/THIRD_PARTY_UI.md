# UI source and licenses

The travel portal adapts **actual source code** from the official [MUI Dashboard template](https://github.com/mui/material-ui/blob/27565bf06476f6ce2f8eb0c67393c67477968fa2/docs/data/material/getting-started/templates/dashboard/Dashboard.tsx). The upstream source was downloaded before integration to `C:\Users\ADMIN\AppData\Local\Temp\travelrisk-mui-template`, from commit `27565bf06476f6ce2f8eb0c67393c67477968fa2` of `mui/material-ui`.

| Upstream source | Adapted application code | Adaptation |
| --- | --- | --- |
| `Dashboard.tsx`, `components/SideMenu.tsx`, `components/AppNavbar.tsx`, `components/MenuContent.tsx` | `src/template/MuiDashboardShell.jsx` | Responsive permanent/mobile drawer, app bar, route navigation, account and theme controls. Demo data and demo sections removed. |
| `components/StatCard.tsx` | `src/portal/UiPrimitives.jsx` (`MetricCard`) | Card structure connected to FastAPI data; demo metrics and trend graphics removed. |

MUI template and `@mui/material` / `@mui/icons-material` are [MIT licensed](https://github.com/mui/material-ui/blob/27565bf06476f6ce2f8eb0c67393c67477968fa2/LICENSE). The copied notice is in [`src/template/LICENSE.mui.txt`](src/template/LICENSE.mui.txt) and `public/LICENSE.mui.txt` for the built site. Emotion and React Router are dependencies used under their own open-source licenses in `node_modules`.

The interface font is [Be Vietnam Pro](https://github.com/bettergui/BeVietnamPro), loaded locally from `@fontsource/be-vietnam-pro`, under the [SIL Open Font License 1.1](https://github.com/bettergui/BeVietnamPro/blob/main/OFL.txt). Its package license is copied to `public/LICENSE.be-vietnam-pro.txt` for the built site. All imported weights include its Vietnamese character subset.

The [Global Travel Risk Dashboard](https://dribbble.com/shots/25934117-Global-Travel-Risk-Dashboard-Insurtech), [Weather Administration Tracker](https://dribbble.com/shots/27080949-Weather-Administration-Tracker-Dashboard), and [Travel Dashboard case study](https://www.behance.net/gallery/222538861/Travel-Dashboard-UI-UX-Case-Study) were used **only as visual references** for hierarchy, weather grouping, and travel planning flow. No source code was taken from those design posts, and no screenshots or iframes are embedded in the application.
