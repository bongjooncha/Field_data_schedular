import { useEffect, useMemo, useState } from "react";
import { request } from "../api";
import Shell from "../components/Shell";
import { TYPE_LABEL, WEEKDAYS, formatSource, toTimeValue } from "../format";

const STEPS = ["데이터베이스", "확인 컬럼", "메일과 시각"];

export default function Wizard({ status, onDone, onCancel, onRefresh, mode = "setup" }) {
  const saved = status.config;
  const steps = mode === "add" ? ["데이터베이스", "확인 컬럼"] : STEPS;
  const savedSources = saved.sources || [];
  const initial = mode === "add"
    ? null
    : savedSources.find((item) => item.id === saved.activeSourceId) || savedSources[0] || null;
  const [sources, setSources] = useState(savedSources);
  const [creating, setCreating] = useState(mode === "add");
  const [sourceId, setSourceId] = useState(initial?.id || "");
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);

  const [label, setLabel] = useState(initial?.label || "");
  const [host, setHost] = useState(initial?.host || "");
  const [port, setPort] = useState(initial?.port || 27017);
  const [username, setUsername] = useState(initial?.username || "");
  const [password, setPassword] = useState("");
  const [passwordSet, setPasswordSet] = useState(Boolean(initial?.passwordSet));
  const [authSource, setAuthSource] = useState(initial?.authSource || "admin");

  const [database, setDatabase] = useState(initial?.database || saved.mongodb.database || "");
  const [databases, setDatabases] = useState([]);
  const [collection, setCollection] = useState(initial?.collection || saved.mongodb.collection || "");
  const [collections, setCollections] = useState([]);
  const [fields, setFields] = useState([]);
  const [candidates, setCandidates] = useState(initial?.timestampField ? [initial.timestampField] : []);
  const [sampled, setSampled] = useState(0);
  const [timestampField, setTimestampField] = useState(initial?.timestampField || "");
  const [columns, setColumns] = useState(() => new Set(initial?.columns || []));
  const [query, setQuery] = useState("");
  const [customColumn, setCustomColumn] = useState("");

  const [mailEnabled, setMailEnabled] = useState(saved.email.enabled !== false);
  const [recipients, setRecipients] = useState((saved.email.to || []).join("\n"));
  const [smtpHost, setSmtpHost] = useState(saved.email.smtpHost || "");
  const [smtpPort, setSmtpPort] = useState(saved.email.smtpPort || 587);
  const [smtpUser, setSmtpUser] = useState(saved.email.smtpUser || "");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [fromName, setFromName] = useState(saved.email.fromName || "DYP_Schedular");
  const [fromAddress, setFromAddress] = useState(saved.email.fromAddress || "");
  const [useTls, setUseTls] = useState(saved.email.useTls !== false);
  const [period, setPeriod] = useState(saved.schedule.period || "daily");
  const [sendTime, setSendTime] = useState(toTimeValue(saved.schedule.hour ?? 8, saved.schedule.minute ?? 0));
  const [weekday, setWeekday] = useState(saved.schedule.weekday || "mon");

  useEffect(() => {
    if (step !== 2 || !sourceId) return undefined;
    let ignore = false;
    request(`/api/mongo/databases?sourceId=${encodeURIComponent(sourceId)}`)
      .then((data) => {
        if (ignore) return;
        const names = data.databases || [];
        setDatabases(names);
        setDatabase((current) => (names.includes(current) ? current : ""));
      })
      .catch((err) => {
        if (!ignore) setError(err.message);
      });
    return () => {
      ignore = true;
    };
  }, [step, sourceId]);

  useEffect(() => {
    if (step !== 2 || !database) return undefined;
    let ignore = false;
    request(`/api/mongo/collections?database=${encodeURIComponent(database)}&sourceId=${encodeURIComponent(sourceId)}`)
      .then((data) => {
        if (ignore) return;
        const names = data.collections || [];
        setCollections(names);
        setCollection((current) => (names.includes(current) ? current : ""));
      })
      .catch((err) => {
        if (!ignore) setError(err.message);
      });
    return () => {
      ignore = true;
    };
  }, [step, database, sourceId]);

  useEffect(() => {
    if (step !== 2 || !database || !collection) {
      if (!collection) {
        setFields([]);
        setSampled(0);
      }
      return undefined;
    }
    let ignore = false;
    request(`/api/mongo/fields?database=${encodeURIComponent(database)}&collection=${encodeURIComponent(collection)}&sourceId=${encodeURIComponent(sourceId)}`)
      .then((data) => {
        if (ignore) return;
        setFields(data.fields || []);
        setCandidates(data.timestampCandidates || []);
        setSampled(data.sampled || 0);
        setTimestampField((current) => current || data.timestampCandidates?.[0] || "");
      })
      .catch((err) => {
        if (!ignore) setError(err.message);
      });
    return () => {
      ignore = true;
    };
  }, [step, database, collection, sourceId]);

  const visibleFields = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return fields.filter((field) => {
      if (field.name === timestampField) return false;
      if (!keyword) return true;
      return field.name.toLowerCase().includes(keyword);
    });
  }, [fields, query, timestampField]);

  const extraColumns = [...columns].filter((name) => name !== timestampField && !fields.some((field) => field.name === name));

  async function submitConnection(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setPending(true);
    try {
      const data = await request("/api/setup/connection", {
        method: "POST",
        body: JSON.stringify({
          id: creating ? "" : sourceId,
          label,
          host,
          port: Number(port),
          username,
          password,
          authSource,
        }),
      });
      const nextSources = data.status?.config?.sources || [];
      const savedSource = nextSources.find((item) => item.id === data.sourceId);
      setSources(nextSources);
      setSourceId(data.sourceId);
      setCreating(false);
      setPasswordSet(Boolean(savedSource?.passwordSet));
      setPassword("");
      setStep(2);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  }

  function selectSource(source) {
    setCreating(false);
    setSourceId(source.id);
    setLabel(source.label || "");
    setHost(source.host || "");
    setPort(source.port || 27017);
    setUsername(source.username || "");
    setPassword("");
    setPasswordSet(Boolean(source.passwordSet));
    setAuthSource(source.authSource || "admin");
    setDatabase(source.database || "");
    setCollection(source.collection || "");
    setTimestampField(source.timestampField || "");
    setColumns(new Set(source.columns || []));
    setFields([]);
    setError("");
    setNotice("");
    setStep(1);
  }

  function startNewAddress() {
    setCreating(true);
    setSourceId("");
    setLabel("");
    setHost("");
    setPort(27017);
    setUsername("");
    setPassword("");
    setPasswordSet(false);
    setAuthSource("admin");
    setDatabase("");
    setCollection("");
    setTimestampField("");
    setColumns(new Set());
    setFields([]);
    setCandidates([]);
    setError("");
    setNotice("");
    setStep(1);
  }

  async function removeSource(id) {
    if (!window.confirm("이 주소를 목록에서 뺄까요? 그 주소의 컬럼 설정도 함께 지워집니다.")) return;
    setError("");
    setPending(true);
    try {
      const data = await request(`/api/sources/${encodeURIComponent(id)}`, { method: "DELETE" });
      const nextSources = data.status?.config?.sources || [];
      setSources(nextSources);
      if (onRefresh) await onRefresh();
      const active = nextSources.find((item) => item.id === data.status?.config?.activeSourceId) || nextSources[0];
      if (active) selectSource(active);
      else startNewAddress();
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  }

  function changeDatabase(value) {
    setDatabase(value);
    setCollection("");
    setFields([]);
    setTimestampField("");
    setColumns(new Set());
    setError("");
  }

  function toggleColumn(name) {
    setColumns((current) => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function addCustomColumn() {
    const name = customColumn.trim();
    if (!name || name === timestampField) return;
    setColumns((current) => new Set(current).add(name));
    setCustomColumn("");
  }

  async function submitWatch(event) {
    event.preventDefault();
    setError("");
    const chosen = [...columns].filter((name) => name && name !== timestampField);
    setPending(true);
    try {
      await request("/api/setup/watch", {
        method: "POST",
        body: JSON.stringify({
          sourceId,
          database,
          collection,
          timestampField,
          columns: chosen,
        }),
      });
      if (mode === "add") await onDone();
      else setStep(3);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  }

  function deliveryPayload() {
    const [hourText, minuteText] = (sendTime || "08:00").split(":");
    return {
      enabled: mailEnabled,
      to: recipients.split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean),
      smtpHost,
      smtpPort: Number(smtpPort),
      smtpUser,
      smtpPassword,
      fromName,
      fromAddress,
      useTls,
      period,
      hour: Number(hourText),
      minute: Number(minuteText),
      weekday,
    };
  }

  async function submitDelivery(event) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      await request("/api/setup/delivery", {
        method: "POST",
        body: JSON.stringify(deliveryPayload()),
      });
      await onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  }

  async function sendTest() {
    setError("");
    setNotice("");
    setPending(true);
    try {
      await request("/api/mail/test", {
        method: "POST",
        body: JSON.stringify(deliveryPayload()),
      });
      setNotice("테스트 메일을 보냈습니다. 받은편지함을 확인해 주세요.");
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  }

  const actions = onCancel ? (
    <button className="btn btn-utility" type="button" onClick={onCancel}>
      점검 화면
    </button>
  ) : null;

  return (
    <Shell
      eyebrow={mode === "add" ? `주소 추가 ${step} / ${steps.length}` : `설정 ${step} / ${steps.length}`}
      title={steps[step - 1]}
      description={mode === "add"
        ? "다른 MongoDB 주소를 추가합니다. 주소마다 데이터베이스와 확인 컬럼을 따로 고릅니다."
        : "메일 주소, 발송 시각, 데이터베이스와 확인 컬럼은 데이터베이스가 아닌 config.json에 저장됩니다."}
      actions={actions}
      footer={`설정 파일 ${status.configPath}`}
    >
      <ol className="steps">
        {steps.map((label, index) => {
          const number = index + 1;
          const state = number === step ? "active" : number < step ? "done" : "";
          const canOpen = (status.setupComplete || number <= step) && (number === 1 || sourceId);
          return (
            <li key={label}>
              <button
                type="button"
                className={`step-pill ${state}`}
                onClick={() => {
                  if (canOpen) {
                    setError("");
                    setStep(number);
                  }
                }}
                disabled={!canOpen}
              >
                <span>{number}</span>
                {label}
              </button>
            </li>
          );
        })}
      </ol>

      {error ? <p className="alert" role="alert">{error}</p> : null}
      {notice ? <p className="alert alert-ok" role="status">{notice}</p> : null}

      {step === 1 ? (
        <form className="card form-grid" onSubmit={submitConnection}>
          <p className="help">
            현장 데이터가 쌓이는 MongoDB에 읽기 전용으로 연결합니다. 주소는 여러 개 둘 수 있고, 이 프로그램은 현장 데이터를 수정하지 않습니다.
          </p>
          {sources.length ? (
            <div className="source-picks">
              {sources.map((source) => (
                <div className="source-pick" key={source.id}>
                  <button
                    type="button"
                    className="btn btn-utility"
                    aria-pressed={!creating && source.id === sourceId}
                    onClick={() => selectSource(source)}
                  >
                    {formatSource(source)}
                  </button>
                  {sources.length > 1 ? (
                    <button className="btn btn-utility" type="button" onClick={() => removeSource(source.id)} disabled={pending}>
                      빼기
                    </button>
                  ) : null}
                </div>
              ))}
              <button className="btn btn-utility" type="button" onClick={startNewAddress}>주소 추가</button>
            </div>
          ) : null}
          <label>
            이름
            <input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="현장 A. 비워 두면 주소로 표시" />
          </label>
          <label>
            주소
            <input value={host} onChange={(event) => setHost(event.target.value)} placeholder="192.168.0.10 또는 mongodb://..." required />
          </label>
          <div className="split">
            <label>
              포트
              <input type="number" min="1" max="65535" value={port} onChange={(event) => setPort(event.target.value)} required />
            </label>
            <label>
              인증 데이터베이스
              <input value={authSource} onChange={(event) => setAuthSource(event.target.value)} placeholder="admin" />
            </label>
          </div>
          <label>
            사용자 ID
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" placeholder="계정이 없으면 비워 두세요" />
          </label>
          <label>
            비밀번호
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" placeholder={passwordSet ? "저장됨. 바꿀 때만 입력" : ""} />
          </label>
          <div className="form-actions">
            <button className="btn btn-primary" type="submit" disabled={pending}>
              {pending ? "연결 확인 중" : "연결하고 다음"}
            </button>
          </div>
        </form>
      ) : null}

      {step === 2 ? (
        <form className="card form-grid" onSubmit={submitWatch}>
          <p className="help">시간 기준 컬럼으로 전날 또는 7일 구간을 자르고, 고른 컬럼에 값이 얼마나 들어왔는지 셉니다.</p>
          <div className="split">
            <label>
              데이터베이스
              <select value={database} onChange={(event) => changeDatabase(event.target.value)} required>
                <option value="">선택</option>
                {databases.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>
            <label>
              컬렉션
              <select
                value={collection}
                onChange={(event) => {
                  setCollection(event.target.value);
                  setTimestampField("");
                  setColumns(new Set());
                  setError("");
                }}
                required
                disabled={!database}
              >
                <option value="">선택</option>
                {collections.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>
          </div>

          <label>
            시간 기준 컬럼
            <select value={timestampField} onChange={(event) => setTimestampField(event.target.value)} required>
              <option value="">선택</option>
              {timestampOptions(fields, candidates, timestampField).map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>
          {candidates.length ? <p className="help">날짜로 보이는 컬럼: {candidates.join(", ")}</p> : null}

          <div className="column-tools">
            <label className="grow">
              컬럼 검색
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="컬럼 이름" />
            </label>
            <button
              className="btn btn-utility"
              type="button"
              onClick={() => setColumns((current) => {
                const next = new Set(current);
                visibleFields.forEach((field) => next.add(field.name));
                return next;
              })}
            >
              보이는 컬럼 모두 선택
            </button>
            <button className="btn btn-utility" type="button" onClick={() => setColumns(new Set())}>
              선택 해제
            </button>
          </div>

          <div className="column-list">
            {visibleFields.length === 0 ? (
              <p className="help">{sampled ? "검색 결과가 없습니다." : "컬렉션을 고르면 최근 문서의 컬럼이 나타납니다."}</p>
            ) : (
              visibleFields.map((field) => (
                <label key={field.name} className="check-row">
                  <input
                    type="checkbox"
                    checked={columns.has(field.name)}
                    onChange={() => toggleColumn(field.name)}
                  />
                  <span>
                    <strong>{field.name}</strong>
                    <small>
                      {(field.types || []).map((type) => TYPE_LABEL[type] || type).join(", ") || "값 없음"}
                      {" · "}
                      최근 {sampled}건 중 {field.present}건
                    </small>
                  </span>
                </label>
              ))
            )}
          </div>

          {extraColumns.length ? (
            <p className="help">직접 추가한 컬럼: {extraColumns.join(", ")}</p>
          ) : null}

          <div className="column-tools">
            <label className="grow">
              목록에 없는 컬럼
              <input value={customColumn} onChange={(event) => setCustomColumn(event.target.value)} placeholder="sensor.temperature" />
            </label>
            <button className="btn btn-utility" type="button" onClick={addCustomColumn}>
              추가
            </button>
          </div>

          <div className="form-actions">
            <button className="btn btn-utility" type="button" onClick={() => setStep(1)}>이전</button>
            <button className="btn btn-primary" type="submit" disabled={pending}>
              {pending ? "저장 중" : mode === "add" ? "이 주소 저장" : "컬럼 저장하고 다음"}
            </button>
          </div>
        </form>
      ) : null}

      {step === 3 ? (
        <form className="card form-grid" onSubmit={submitDelivery}>
          <label className="check-inline">
            <input
              type="checkbox"
              checked={!mailEnabled}
              onChange={(event) => setMailEnabled(!event.target.checked)}
            />
            메일 전송 건너뛰기. 내부망처럼 메일을 보낼 수 없으면 수집 결과는 화면에서만 확인합니다.
          </label>
          {mailEnabled ? (
            <>
              <p className="help">
                발송은 이 프로그램이 켜져 있는 동안 동작합니다. 꺼 둘 경우에는 실행 파일에 --send-now 를 붙여 Windows 작업 스케줄러에 등록할 수 있습니다.
              </p>
              <label>
                받을 메일
                <textarea value={recipients} onChange={(event) => setRecipients(event.target.value)} placeholder={"ops@example.com\nteam@example.com"} rows={3} required />
              </label>
              <div className="split">
                <label>
                  SMTP 서버
                  <input value={smtpHost} onChange={(event) => setSmtpHost(event.target.value)} placeholder="smtp.example.com" required />
                </label>
                <label>
                  SMTP 포트
                  <input type="number" min="1" max="65535" value={smtpPort} onChange={(event) => setSmtpPort(event.target.value)} required />
                </label>
              </div>
              <div className="split">
                <label>
                  SMTP 계정
                  <input value={smtpUser} onChange={(event) => setSmtpUser(event.target.value)} autoComplete="username" />
                </label>
                <label>
                  SMTP 비밀번호
                  <input
                    type="password"
                    value={smtpPassword}
                    onChange={(event) => setSmtpPassword(event.target.value)}
                    autoComplete="current-password"
                    placeholder={saved.email.smtpPasswordSet ? "저장됨. 바꿀 때만 입력" : ""}
                  />
                </label>
              </div>
              <div className="split">
                <label>
                  보내는 이름
                  <input value={fromName} onChange={(event) => setFromName(event.target.value)} placeholder="DYP_Schedular" />
                </label>
                <label>
                  보내는 메일
                  <input type="email" value={fromAddress} onChange={(event) => setFromAddress(event.target.value)} required />
                </label>
              </div>
              <p className="help">받은 편지함에는 {fromName.trim() || "DYP_Schedular"} 이름으로 표시됩니다. 메일 주소 자체는 로그인한 계정 주소입니다.</p>
              <label className="check-inline">
                <input type="checkbox" checked={useTls} onChange={(event) => setUseTls(event.target.checked)} />
                TLS 사용 (포트 587). 포트 465는 SSL로 연결합니다.
              </label>

              <fieldset className="period-fieldset">
                <legend>집계 주기</legend>
                <div className="segmented">
                  <button type="button" aria-pressed={period === "daily"} onClick={() => setPeriod("daily")}>매일, 전날</button>
                  <button type="button" aria-pressed={period === "weekly"} onClick={() => setPeriod("weekly")}>매주, 지난 7일</button>
                </div>
              </fieldset>

              <div className="split">
                <label>
                  발송 시각
                  <input type="time" value={sendTime} onChange={(event) => setSendTime(event.target.value)} required />
                </label>
                {period === "weekly" ? (
                  <label>
                    발송 요일
                    <select value={weekday} onChange={(event) => setWeekday(event.target.value)}>
                      {WEEKDAYS.map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <p className="help time-note">기준 시간대는 한국(서울)입니다. 기본값은 매일 아침 8시입니다.</p>
                )}
              </div>
            </>
          ) : (
            <p className="help">예약 발송과 수동 발송을 하지 않습니다. 나중에 설정에서 다시 켤 수 있습니다.</p>
          )}

          <div className="form-actions">
            <button className="btn btn-utility" type="button" onClick={() => setStep(2)}>이전</button>
            {mailEnabled ? (
              <button className="btn btn-utility" type="button" onClick={sendTest} disabled={pending}>테스트 메일</button>
            ) : null}
            <button className="btn btn-primary" type="submit" disabled={pending}>
              {pending ? "저장 중" : "저장하고 점검 시작"}
            </button>
          </div>
        </form>
      ) : null}
    </Shell>
  );
}

function timestampOptions(fields, candidates, current) {
  const names = new Set([...(candidates || []), ...fields.map((field) => field.name)]);
  if (current) names.add(current);
  return [...names];
}
