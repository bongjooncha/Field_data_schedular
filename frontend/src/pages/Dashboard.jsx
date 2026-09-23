import { useEffect, useState } from "react";
import { request } from "../api";
import Shell from "../components/Shell";
import { MODE_LABEL, STATUS_LABEL, formatNumber, formatPercent, formatSource, formatWhen, scheduleSentence } from "../format";

export default function Dashboard({ status, onEdit, onAdd, onStatus }) {
  const schedule = status.config.schedule;
  const mailEnabled = status.config.email.enabled !== false;
  const configured = status.config.sources || [];
  const sourceKey = configured.map((item) => item.id).join(",");
  const [sourceId, setSourceId] = useState(status.config.activeSourceId || configured[0]?.id || "");
  const [day, setDay] = useState(status.yesterday);
  const [span, setSpan] = useState(schedule.period === "weekly" ? "weekly" : "daily");
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [links, setLinks] = useState(null);
  const [checking, setChecking] = useState(true);
  const [checkKey, setCheckKey] = useState(0);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let ignore = false;
    setChecking(true);
    request("/api/connectivity")
      .then((data) => {
        if (ignore) return;
        setLinks(data);
        setError("");
      })
      .catch((err) => {
        if (!ignore) setError(err.message);
      })
      .finally(() => {
        if (!ignore) setChecking(false);
      });
    return () => {
      ignore = true;
    };
  }, [checkKey, sourceKey]);

  useEffect(() => {
    if (checking) return undefined;
    const row = (links?.sources || []).find((item) => item.id === sourceId);
    if (!row || row.online === false) {
      setReport(null);
      setOffline(Boolean(row && row.online === false));
      setPending(false);
      if (row) setError("");
      return undefined;
    }
    let ignore = false;
    setOffline(false);
    setPending(true);
    setError("");
    const params = new URLSearchParams({ date: day, span, source: sourceId });
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
  }, [checking, links, sourceId, day, span, reloadKey]);

  async function chooseSource(id) {
    if (id === sourceId) return;
    setSourceId(id);
    try {
      const data = await request("/api/sources/active", {
        method: "POST",
        body: JSON.stringify({ id }),
      });
      onStatus(data.status);
    } catch (err) {
      setError(err.message);
    }
  }

  async function sendMail() {
    if (!report) return;
    const confirmed = window.confirm(`${report.window.label} 수집 결과를 등록된 모든 주소에 대해 메일로 보낼까요? 오프라인인 주소는 연결되지 않음으로 적습니다.`);
    if (!confirmed) return;
    setSending(true);
    setNotice("");
    setError("");
    try {
      const params = new URLSearchParams({ date: day, span, source: sourceId });
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
      description={scheduleSentence(schedule, status.config.email.to || [], mailEnabled)}
      actions={(
        <>
          <button className="btn btn-utility" type="button" onClick={onAdd}>주소 추가</button>
          <button className="btn btn-utility" type="button" onClick={onEdit}>설정</button>
          {mailEnabled ? (
            <button className="btn btn-primary" type="button" onClick={sendMail} disabled={!report || sending}>
              {sending ? "보내는 중" : "이 기간 메일 보내기"}
            </button>
          ) : null}
        </>
      )}
      footer={mailEnabled
        ? `설정 파일 ${status.configPath} · 발송은 프로그램을 켜 둔 동안 예약됩니다.`
        : `설정 파일 ${status.configPath} · 메일 전송은 사용하지 않습니다.`}
    >
      <ConnectionCard
        checking={checking}
        internet={links ? links.internet : null}
        rows={links?.sources || configured.map((item) => ({
          id: item.id,
          label: formatSource(item),
          database: item.database,
          collection: item.collection,
          online: null,
          error: "",
        }))}
        sourceId={sourceId}
        onChoose={chooseSource}
        onCheck={() => setCheckKey((value) => value + 1)}
        onAdd={onAdd}
      />

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
            ? "선택한 날의 저장 시각 00:00부터 24:00까지입니다."
            : "선택한 날을 끝으로 이전 7일입니다."}
          {mailEnabled && status.nextRun ? ` 다음 자동 발송은 ${formatWhen(status.nextRun)} 입니다.` : ""}
        </p>
      </section>

      {offline ? <p className="alert" role="status">이 주소는 오프라인입니다. 연결될 때까지 집계하지 않습니다.</p> : null}
      {error ? <p className="alert" role="alert">{error}</p> : null}
      {notice ? <p className="alert alert-ok" role="status">{notice}</p> : null}
      {report?.totalDocuments === 0 && report.activeDates?.length ? (
        <section className="card date-card">
          <h2>이 날짜에는 문서가 없습니다</h2>
          <p className="help">데이터가 들어 있는 날짜입니다. 누르면 그 날의 수집량을 봅니다.</p>
          <div className="date-picks">
            {report.activeDates.map((item) => (
              <button
                key={item.date}
                className="btn btn-utility"
                type="button"
                onClick={() => {
                  setDay(item.date);
                  setSpan("daily");
                }}
              >
                {item.date} · {formatNumber(item.count)}건
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {report && !report.timestampIndexed ? (
        <p className="alert">시간 컬럼 {report.timestampField}에 인덱스가 없습니다. 데이터가 많으면 조회가 느려질 수 있습니다.</p>
      ) : null}

      <section className="stat-grid">
        <Stat label="수집 문서" value={report ? formatNumber(report.totalDocuments) : "–"} hint={report ? `${report.database}.${report.collection}` : "조회 중"} />
        <Stat label="평균 채움률" value={report ? formatPercent(report.averageFillRate) : "–"} hint={report ? `컬럼 ${report.columns.length}개` : ""} />
        <Stat label="상태" value={report ? STATUS_LABEL[report.status] : pending ? "조회 중" : "–"} hint={report ? `시간 컬럼 ${report.timestampField} · ${MODE_LABEL[report.timestampMode] || "시간"}` : ""} status={report?.status} />
        <Stat
          label="마지막 발송"
          value={mailEnabled ? (lastRun ? (lastRun.ok ? "보냄" : "실패") : "없음") : "사용 안 함"}
          hint={mailEnabled
            ? (lastRun ? `${formatWhen(lastRun.at)}${lastRun.windowLabel ? ` · ${lastRun.windowLabel}` : ""}` : "아직 보내지 않았습니다")
            : "메일 전송을 건너뛰는 설정입니다"}
          status={mailEnabled ? (lastRun ? (lastRun.ok ? "ok" : "partial") : "empty") : "empty"}
        />
      </section>

      {mailEnabled && lastRun && !lastRun.ok && lastRun.error ? <p className="alert">{lastRun.error}</p> : null}

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
          <h2>컬럼별 값</h2>
          <p>
            {mailEnabled
              ? "각 값이 그 기간에 몇 건 들어왔는지입니다. 메일에도 같은 내용이 들어갑니다."
              : "각 값이 그 기간에 몇 건 들어왔는지입니다."}
          </p>
        </div>
        {(report?.columns || []).map((column) => (
          <div className="value-block" key={column.name}>
            <div className="section-head">
              <h3>{column.name}</h3>
              <p>{column.values?.length || 0}종 · 수집 {formatNumber(column.present)}건</p>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>값</th>
                    <th>건수</th>
                    <th>비율</th>
                  </tr>
                </thead>
                <tbody>
                  {(column.values || []).map((item) => (
                    <tr key={`${column.name}-${item.value}`}>
                      <td>{item.value}</td>
                      <td className="num">{formatNumber(item.count)}</td>
                      <td className="num">{formatPercent(item.rate)}</td>
                    </tr>
                  ))}
                  {!column.values?.length ? (
                    <tr>
                      <td colSpan="3">이 기간에 값이 없습니다.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            {column.valuesTruncated ? <p className="help">건수가 많은 값 40개만 표시했습니다.</p> : null}
          </div>
        ))}
        {!report && !error && !offline ? <p className="help">MongoDB에서 값별 건수를 계산하고 있습니다.</p> : null}
      </section>
    </Shell>
  );
}

function ConnectionCard({ checking, internet, rows, sourceId, onChoose, onCheck, onAdd }) {
  const internetLabel = internet === null ? "확인 중" : internet ? "온라인" : "오프라인";
  return (
    <section className="card link-card">
      <div className="section-head">
        <h2>연결 상태</h2>
        <p>{checking ? "주소에 연결되는지 확인하고 있습니다." : "창을 열면 외부 인터넷과 각 데이터베이스 주소를 먼저 확인합니다."}</p>
      </div>
      <div className="link-row">
        <i className={`status-dot ${internet === null ? "empty" : internet ? "ok" : "partial"}`} />
        <span>
          <strong>외부 인터넷</strong>
          <small>끊기면 메일을 보내지 못할 수 있습니다. 사내 데이터베이스는 아래 주소로 따로 확인합니다.</small>
        </span>
        <em className={`pill ${internet === true ? "ok" : internet === false ? "offline" : ""}`}>{internetLabel}</em>
      </div>
      <div className="link-list">
        {rows.map((item) => {
          const stateLabel = item.online === null || item.online === undefined ? "확인 중" : item.online ? "온라인" : "오프라인";
          const target = [item.database, item.collection].filter(Boolean).join(".") || "데이터베이스 미설정";
          return (
            <button
              key={item.id}
              type="button"
              className="link-row"
              aria-pressed={item.id === sourceId}
              onClick={() => onChoose(item.id)}
            >
              <i className={`status-dot ${item.online ? "ok" : item.online === false ? "partial" : "empty"}`} />
              <span>
                <strong>{item.label}</strong>
                <small>{target}{item.online === false && item.error ? ` · ${item.error}` : ""}</small>
              </span>
              <em className={`pill ${item.online === true ? "ok" : item.online === false ? "offline" : ""}`}>{stateLabel}</em>
            </button>
          );
        })}
      </div>
      <div className="form-actions">
        <button className="btn btn-utility" type="button" onClick={onCheck} disabled={checking}>
          {checking ? "확인 중" : "다시 확인"}
        </button>
        <button className="btn btn-primary" type="button" onClick={onAdd}>주소 추가</button>
      </div>
    </section>
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
