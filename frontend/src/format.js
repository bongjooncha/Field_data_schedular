export const STATUS_LABEL = {
  ok: "정상",
  partial: "확인 필요",
  empty: "미수집",
};

export const WEEKDAYS = [
  ["mon", "월요일"],
  ["tue", "화요일"],
  ["wed", "수요일"],
  ["thu", "목요일"],
  ["fri", "금요일"],
  ["sat", "토요일"],
  ["sun", "일요일"],
];

export const WEEKDAY_LABEL = Object.fromEntries(WEEKDAYS);

export const MODE_LABEL = {
  datetime: "날짜",
  epoch_ms: "밀리초 숫자",
  epoch_s: "초 숫자",
  string: "문자",
};

export const TYPE_LABEL = {
  date: "날짜",
  string: "문자",
  int: "숫자",
  double: "숫자",
  long: "숫자",
  bool: "예/아니오",
  object: "객체",
  array: "목록",
  null: "빈 값",
};

export function formatNumber(value) {
  return new Intl.NumberFormat("ko-KR").format(value || 0);
}

export function formatPercent(rate) {
  return `${((rate || 0) * 100).toFixed(1)}%`;
}

export function formatWhen(iso) {
  if (!iso) return "없음";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul",
  }).format(date);
}

export function toTimeValue(hour = 8, minute = 0) {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

export function scheduleSentence(schedule, recipients) {
  const time = toTimeValue(schedule.hour, schedule.minute);
  const target = recipients.length ? recipients.join(", ") : "받는 사람 없음";
  if (schedule.period === "weekly") {
    const day = WEEKDAY_LABEL[schedule.weekday] || "월요일";
    return `매주 ${day} ${time}에 지난 7일 수집량을 ${target} 으로 보냅니다.`;
  }
  return `매일 ${time}에 전날 00:00–24:00 수집량을 ${target} 으로 보냅니다.`;
}
