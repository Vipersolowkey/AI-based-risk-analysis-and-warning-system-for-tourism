export function getVerdict(recommendation) {
  const value = String(recommendation || "");
  if (value.includes("KHÔNG NÊN ĐI")) return { label: "DON'T GO", vi: "Chưa nên khởi hành", tone: "error", css: "danger" };
  if (value.includes("CẨN THẬN")) return { label: "CAUTION", vi: "Cần kiểm tra thêm trước chuyến đi", tone: "warning", css: "caution" };
  if (value.includes("NÊN ĐI")) return { label: "GO", vi: "Có thể tiếp tục lên kế hoạch", tone: "success", css: "calm" };
  return { label: "CHƯA CÓ", vi: "Chưa đủ dữ liệu để kết luận", tone: "info", css: "neutral" };
}

export function dateLabel(value) {
  if (!value) return "Chưa rõ ngày";
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function numberLabel(value, digits = 0, unit = "") {
  if (value == null || !Number.isFinite(Number(value))) return "Chưa có dữ liệu";
  return `${Number(value).toLocaleString("vi-VN", { maximumFractionDigits: digits })}${unit}`;
}
