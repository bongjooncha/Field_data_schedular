import { useEffect, useState } from "react";
import { request } from "../api";
import Shell from "../components/Shell";
import { MODE_LABEL, STATUS_LABEL, formatNumber, formatPercent, formatWhen, scheduleSentence } from "../format";

export default function Dashboard({ status, onEdit, onStatus }) {
  const schedule = status.config.schedule;
  const [day, setDay] = useState(status.yesterday);
  const [span, setSpan] = useState(schedule.period === "weekly" ? "weekly" : "daily");
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let ignore = false;
    setPending(true);
    setError("");
    const params = new URLSearchParams({ date: day, span });
    request(`/api/report?${params.toString()}`)
      .then((data) => {
        if (!ignore) setReport(data);
      })
      .catch((err) => {
        if (!ignore) {
          setReport(null);
          setError(err.message);
        }
      })
      .finally(() => {
        if (!ignore) setPending(false);
      });
    return () => {
      ignore = true;
    };
  }, [day, span, reloadKey]);

  async function sendMail() {
    if (!report) return;
    const confirmed = window.confirm(`${report.window.label} 수집 결과를 메일로 보낼까요?`);
    if (!confirmed) return;
    setSending(true);
    setNotice("");
    setError("");
    try {
      const params = new URLSearchParams({ date: day, span });
      const data = await request(`/api/report/send?${params.toString()}`, { method: "POST" });
      setReport(data.report);
      onStatus(data.status);
      setNotice("메일을 보냈습니다.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  const maxCount = Math.max(...(report?.buckets || []).map((bucket) => bucket.count), 1);
  const lastRun = status.lastRun;

  return (
    <Shell
      eyebrow="수집 현황"
      title={report?.window.label || "수집량을 확인하고 있습니다"}
      description={scheduleSentence(schedule, status.config.email.to || [])}
      actions={(
        <>
          <button className="btn btn-utility" type="button" onClick={onEdit}>설정</button>
          <button className="btn btn-primary" type="button" onClick={sendMail} disabled={!report || sending}>
            {sending ? "보내는 중" : "이 기간 메일 보내기"}
          </button>
        </>
      )}
      footer={`설정 파일 ${status.configPath} · 발송은 프로그램을 켜 둔 동안 예약됩니다.`}
    >
      <section className="toolbar card">
        <label>
          마지막 날
          <input type="date" value={day} max={status.today} onChange={(event) => setDay(event.target.value)} />
        </label>
        <div className="segmented" role="group" aria-label="조회 구간">
          <button type="button" aria-pressed={span === "daily"} onClick={() => setSpan("daily")}>하루</button>
          <button type="button" aria-pressed={span === "weekly"} onClick={() => setSpan("weekly")}>7일</button>
        </div>
        <button className="btn btn-utility" type="button" onClick={() => setReloadKey((value) => value + 1)}>다시 조회</button>
        <button className="btn btn-utility" type="button" onClick={() => setDay(status.yesterday)}>어제</button>
        <button className="btn btn-utility" type="button" onClick={() => setDay(status.today)}>오늘</button>
        <p className="help">
          {span === "daily"
            ? "선택한 날 00:00부터 24:00까지, 한국 시간입니다."
            : "선택한 날을 끝으로 이전 7일입니다."}
          {status.nextRun ? ` 다음 자동 발송은 ${formatWhen(status.nextRun)} 입니다.` : ""}
        </p>
      </section>

      {error ? <p className="alert" role="alert">{error}</p> : null}
      {notice ? <p className="alert alert-ok" role="status">{notice}</p> : null}
      {report && !report.timestampIndexed ? (
        <p className="alert">시간 컬럼 {report.timestampField}에 인덱스가 없습니다. 데이터가 많으면 조회가 느려질 수 있습니다.</p>
      ) : null}

      <section className="stat-grid">
        <Stat label="수집 문서" value={report ? formatNumber(report.totalDocuments) : "–"} hint={report ? `${report.database}.${report.collection}` : "조회 중"} />
        <Stat label="평균 채움률" value={report ? formatPercent(report.averageFillRate) : "–"} hint={report ? `컬럼 ${report.columns.length}개` : ""} />
        <Stat label="상태" value={report ? STATUS_LABEL[report.status] : pending ? "조회 중" : "–"} hint={report ? `시간 컬럼 ${report.timestampField} · ${MODE_LABEL[report.timestampMode] || "시간"}` : ""} status={report?.status} />
        <Stat
          label="마지막 발송"
          value={lastRun ? (lastRun.ok ? "보냄" : "실패") : "없음"}
          hint={lastRun ? `${formatWhen(lastRun.at)}${lastRun.windowLabel ? ` · ${lastRun.windowLabel}` : ""}` : "아직 보내지 않았습니다"}
          status={lastRun ? (lastRun.ok ? "ok" : "partial") : "empty"}
        />
      </section>

      {lastRun && !lastRun.ok && lastRun.error ? <p className="alert">{lastRun.error}</p> : null}

      <section className="card">
        <div className="section-head">
          <h2>{report?.bucketKind === "day" ? "날짜별 수집" : "시간대별 수집"}</h2>
          <p>{report?.firstAt ? `${formatWhen(report.firstAt)} – ${formatWhen(report.lastAt)}` : "구간 안의 첫 문서와 마지막 문서"}</p>
        </div>
        <div className="chart" aria-hidden={!report}>
          {(report?.buckets || []).map((bucket) => (
            <div key={bucket.label} className="chart-col" title={`${bucket.label}: ${formatNumber(bucket.count)}건`}>
              <div
                className={bucket.count ? "bar" : "bar zero"}
                style={{ height: `${Math.max((bucket.count / maxCount) * 100, bucket.count ? 4 : 2)}%` }}
              />
              <span>{shortLabel(bucket.label, report?.bucketKind)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="section-head">
          <h2>컬럼별 채움</h2>
          <p>값이 비어 있지 않은 문서를 수집으로 셉니다.</p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>컬럼</th>
                <th>수집</th>
                <th>누락</th>
                <th>채움률</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {(report?.columns || []).map((column) => (
                <tr key={column.name}>
                  <td>{column.name}</td>
                  <td className="num">{formatNumber(column.present)}</td>
                  <td className="num">{formatNumber(column.missing)}</td>
                  <td>
                    <div className="meter" aria-hidden="true">
                      <span style={{ width: formatPercent(column.fillRate) }} />
                    </div>
                    <span className="num">{formatPercent(column.fillRate)}</span>
                  </td>
                  <td>
                    <span className={`status-label ${column.status}`}>
                      <i />
                      {STATUS_LABEL[column.status]}
                    </span>
                  </td>
                </tr>
              ))}
              {!report && !error ? (
                <tr>
                  <td colSpan="5">MongoDB에서 수집량을 계산하고 있습니다.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </Shell>
  );
}

function Stat({ label, value, hint, status }) {
  return (
    <article className="stat card">
      <p className="eyebrow">{label}</p>
      <p className="stat-value">
        {status ? <i className={`status-dot ${status}`} /> : null}
        {value}
      </p>
      {hint ? <p className="help">{hint}</p> : null}
    </article>
  );
}

function shortLabel(label, kind) {
  if (kind === "day") return label.slice(5);
  if (Number(label) % 3 === 0) return label;
  return "";
}
