export default function Shell({ eyebrow, title, description, actions, children, footer }) {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <div>
            <strong>현장 데이터 점검</strong>
            <span>전일 수집 확인</span>
          </div>
        </div>
        {actions ? <div className="topbar-actions">{actions}</div> : null}
      </header>
      <main className="page">
        <div className="page-intro">
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h1>{title}</h1>
          {description ? <p className="lede">{description}</p> : null}
        </div>
        {children}
        {footer ? <p className="config-path">{footer}</p> : null}
      </main>
    </div>
  );
}
