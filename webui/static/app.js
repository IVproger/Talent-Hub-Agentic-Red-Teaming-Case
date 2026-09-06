/* MOROK web UI — навигация по шагам + привязка к реальному движку через /api. */
(function () {
  'use strict';
  const $ = (s, r) => (r || document).querySelector(s);
  const api = (p, opt) => fetch(p, opt).then((r) => (r.ok ? r : Promise.reject(r)));
  const j = (p, opt) => api(p, opt).then((r) => r.json());
  const PRED_RU = {
    tool_principal_mismatch: 'Межпринципальный вызов инструмента',
    cross_session_effect: 'Эффект в другой сессии',
    memory_write: 'Отравление памяти (cross-user)',
    response_contains: 'Утечка в тексте ответа',
  };
  const scnName = (s) => PRED_RU[(s.goal && s.goal[0]) || ''] || s.id;

  const sections = [...document.querySelectorAll('[data-screen]')];
  const steps = MK.steps($('#steps'));
  let scenarios = [];
  let poll = null;
  let openRunId = null;

  function syncSteps(n) {
    // «✓» только на шагах ДО текущего; впереди — номера (сбрасываются при возврате)
    document.querySelectorAll('#steps .mk-step').forEach((b) => {
      const i = Number(b.dataset.step);
      b.toggleAttribute('aria-current', false);
      if (i === n) b.setAttribute('aria-current', 'step');
      const done = i < n;
      b.classList.toggle('mk-step--done', done);
      const num = b.querySelector('.mk-step__n');
      if (num) num.textContent = done ? '✓' : String(i);
    });
  }
  function show(n) {
    sections.forEach((s) => { s.hidden = Number(s.dataset.screen) !== n; });
    syncSteps(n);
    if (n === 3) loadScenarios();
    if (n === 5) renderReport(openRunId);
    if (n === 6) renderBiz();
  }
  function goto(n) { steps.set(n); show(n); }
  $('#steps').addEventListener('mk:step', (e) => show(e.detail.step));
  document.querySelectorAll('[data-go]').forEach((b) =>
    b.addEventListener('click', () => goto(Number(b.dataset.go))));

  // ── Экран 1 · артефакты: архитектура (.mmd) отдельно, документы отдельно ──
  const isArch = (n) => /\.(mmd|mermaid)$/i.test(n);
  function renderTarget(t) {
    const files = t.files || [];
    const arch = files.find(isArch);
    $('#archName').textContent = arch || 'Загрузить архитектуру';
    $('#archZone').classList.toggle('mk-dropzone--filled', !!arch);
    const docs = files.filter((n) => !isArch(n));
    const box = $('#docFiles');
    if (!docs.length) { box.innerHTML = '<span class="mk-caption">Файлы не добавлены.</span>'; return; }
    box.innerHTML = '';
    docs.forEach((name) => {
      const isOp = name === t.openapi;
      const ext = (name.split('.').pop() || '').toUpperCase();
      const row = document.createElement('div');
      row.className = 'mk-file-row';
      row.innerHTML = '<span class="mk-file-row__kind">' + ext + '</span>' +
        '<span class="mk-stack" style="gap:2px"><span class="mk-file-row__name">' + name + '</span>' +
        '<span class="mk-file-row__meta">' + (isOp ? 'OpenAPI · точки входа цели' : 'документ') + '</span></span>' +
        (isOp ? '<span class="mk-text-positive" style="margin-left:auto;font-weight:600">OpenAPI ✓</span>' : '');
      box.appendChild(row);
    });
  }
  function loadTarget() { j('/api/target').then(renderTarget).catch(() => {}); }
  function upload(fileList, input) {
    const arr = [...fileList];
    if (!arr.length) return;
    const fd = new FormData();
    arr.forEach((f) => fd.append('files', f));
    $('#ctxHint').textContent = 'Загрузка…';
    j('/api/target/upload', { method: 'POST', body: fd }).then((t) => {
      renderTarget(t);
      $('#ctxHint').textContent = t.openapi ? 'OpenAPI найден: ' + t.openapi
        : 'Добавьте OpenAPI (JSON/YAML с разделом paths) в «Документацию».';
      if (input) input.value = '';
    }).catch(() => { $('#ctxHint').textContent = 'Не удалось загрузить.'; });
  }
  $('#archInput').addEventListener('change', (e) => upload(e.target.files, e.target));
  $('#docInput').addEventListener('change', (e) => upload(e.target.files, e.target));
  $('#resetTarget').addEventListener('click', () => {
    j('/api/target/reset', { method: 'POST' }).then((t) => {
      renderTarget(t);
      $('#ctxHint').textContent = 'Начато заново — загрузите артефакты цели.';
      $('#targetDot').classList.remove('mk-dot--ok');
      $('#sbConn').textContent = 'Не подключён';
      $('#sbConn').classList.remove('mk-text-positive');
      goto(1);
    });
  });

  $('#connectBtn').addEventListener('click', () => {
    j('/api/target').then((t) => {
      if (!t.openapi) { $('#ctxHint').textContent = 'Нужен OpenAPI среди файлов, чтобы подключить стенд.'; return; }
      $('#targetDot').classList.add('mk-dot--ok');
      $('#sbConn').textContent = 'Подключён';
      $('#sbConn').classList.add('mk-text-positive');
      goto(2);
    });
  });

  // ── История в сайдбаре ──
  function loadHistory() {
    j('/api/runs').then((rows) => {
      const box = $('#sbHistory');
      const done = rows.filter((r) => r.status === 'completed').slice(0, 8);
      box.innerHTML = done.length ? '' : '<span class="mk-meta" style="font-size:11px">пусто</span>';
      done.forEach((r) => {
        const b = document.createElement('button');
        b.className = 'mk-history';
        const asr = (r.asr_percent != null) ? r.asr_percent + '%' : '—';
        b.innerHTML = '<span class="mk-meta" style="font-size:11px">' + r.run_id.slice(0, 13) +
          '</span><span class="mk-between" style="font-size:12px;width:100%">Прогон' +
          '<span class="mk-mono mk-text-negative" style="font-weight:600">' + asr + '</span></span>';
        b.addEventListener('click', () => { openRunId = r.run_id; goto(5); });
        box.appendChild(b);
      });
    }).catch(() => {});
  }

  // ── Экран 3 · Сценарии ──
  function loadScenarios() {
    if (scenarios.length) return;
    j('/api/scenarios').then((list) => {
      scenarios = list;
      const box = $('#scnList');
      box.innerHTML = '';
      list.forEach((s, i) => {
        const el = document.createElement('button');
        el.className = 'mk-scenario';
        el.dataset.id = s.id;
        if (i === 0) el.setAttribute('aria-selected', 'true');
        const tag = s.goal[0] === 'memory_write' ? 'mk-tag mk-tag--memory' :
          (s.goal[0] === 'cross_session_effect' ? 'mk-tag mk-tag--mcp' : 'mk-tag');
        el.innerHTML = '<span class="mk-between"><span class="mk-scenario__title">' + scnName(s) +
          '</span><span class="mk-scenario__count mk-mono">' + s.goal.length + '</span></span>' +
          '<span class="mk-scenario__desc">' + s.attack_class + ' · ' + (s.standard_refs || []).join(', ') + '</span>' +
          '<span class="' + tag + '">' + s.goal[0] + '</span>';
        box.appendChild(el);
      });
      const ctl = MK.scenarios(box);
      box.addEventListener('mk:scenario', (e) => renderScnDetail(e.detail.id));
      renderScnDetail(list[0].id);
    }).catch(() => { $('#scnList').innerHTML = '<span class="mk-meta">не удалось загрузить</span>'; });
  }
  function renderScnDetail(id) {
    const s = scenarios.find((x) => x.id === id);
    if (!s) return;
    $('#scnDetail').innerHTML =
      '<div class="mk-card__head"><h3 class="mk-h3">' + scnName(s) + '</h3><span class="mk-meta">' + s.id + '</span></div>' +
      '<div class="mk-grid" style="grid-template-columns:repeat(2,1fr);gap:10px">' +
      param('Целевой предикат', s.goal[0]) + param('OWASP/ATLAS', (s.standard_refs || []).join(', ')) +
      param('Граница', s.boundary || '—') + param('Меню предикатов', s.goal.length) + '</div>' +
      '<p class="mk-scenario__desc" style="font-size:13px">Агент выбирает целевой предикат и действие; ядро исполняет и проверяет предикат по состоянию цели.</p>';
  }
  const param = (k, v) => '<div class="mk-param"><span class="mk-param__k">' + k + '</span><span class="mk-param__v mk-mono">' + v + '</span></div>';

  // ── Экран 4 · Прогон ──
  $('#runBtn').addEventListener('click', startRun);
  $('#cancelBtn').addEventListener('click', () => {
    if (openRunId) api('/api/run/' + openRunId + '/cancel', { method: 'POST' });
  });
  $('#toReport').addEventListener('click', () => goto(5));

  function buildRows() {
    const box = $('#rows'); box.innerHTML = '';
    scenarios.forEach((s, i) => {
      const r = document.createElement('div');
      r.className = 'mk-attack-row'; r.dataset.i = i;
      r.innerHTML = '<span class="mk-attack-row__n">' + (i + 1) + '</span>' +
        '<span class="mk-attack-row__name">' + scnName(s) + '</span>' +
        '<span class="mk-badge mk-badge--pending">PENDING</span>';
      box.appendChild(r);
    });
  }
  function setBadge(i, cls, text) {
    const row = document.querySelector('#rows .mk-attack-row[data-i="' + i + '"]');
    if (!row) return;
    const b = row.querySelector('.mk-badge');
    b.className = 'mk-badge ' + cls; b.textContent = text;
    row.className = 'mk-attack-row' + (cls === 'mk-badge--proven' ? ' mk-attack-row--proven' :
      cls === 'mk-badge--pending' ? '' : ' mk-attack-row--not-proven');
  }
  function log(lines) {
    const box = $('#log'); const cur = $('#cursor');
    box.querySelectorAll('.mk-log__line').forEach((n) => n.remove());
    lines.slice(-9).forEach((msg) => {
      const line = document.createElement('div'); line.className = 'mk-log__line';
      line.innerHTML = '<span class="mk-log__msg">' + msg + '</span>';
      box.insertBefore(line, cur);
    });
  }

  function startRun() {
    if (!scenarios.length) return;
    buildRows();
    $('#spin').style.visibility = 'visible';
    $('#runStatus').textContent = 'Запуск…';
    $('#toReport').hidden = true; $('#cancelBtn').hidden = false;
    $('#fill').style.width = '0%';
    goto(4);
    j('/api/run', { method: 'POST' }).then((r) => {
      openRunId = r.run_id;
      pollStatus();
    });
  }

  function pollStatus() {
    if (poll) clearInterval(poll);
    poll = setInterval(() => {
      j('/api/status/' + openRunId).then((st) => {
        if (st.log) log(st.log);
        const total = scenarios.length;
        const m = /Атака · (\d+)\/(\d+)/.exec(st.label || '');
        if (m) {
          const i = Number(m[1]);
          for (let k = 0; k < i - 1; k++) setBadge(k, 'mk-badge--running', 'RUNNING');
          setBadge(i - 1, 'mk-badge--running', 'RUNNING');
          $('#fill').style.width = Math.round(100 * (i - 1) / total) + '%';
          $('#counter').textContent = i + ' / ' + total + ' сценариев';
        }
        $('#runStatus').textContent = st.label || 'Идёт прогон…';
        if (st.status === 'completed' || st.status === 'interrupted' || st.status === 'failed') {
          clearInterval(poll); poll = null;
          $('#spin').style.visibility = 'hidden';
          $('#cancelBtn').hidden = true;
          $('#cursor').hidden = true;
          if (st.status === 'failed') { $('#runStatus').textContent = 'Не удался: ' + (st.error || ''); return; }
          finishRun(openRunId);
        }
      }).catch(() => {});
    }, 1500);
  }

  function finishRun(runId) {
    j('/api/runs/' + runId + '/findings').then((f) => {
      const total = f.scenarios_scored || scenarios.length;
      (f.attempts || []).forEach((a) => {
        const idx = scenarios.findIndex((s) => s.id === a.scenario_id);
        if (idx >= 0) setBadge(idx, a.verdict === 'proven' ? 'mk-badge--proven' : 'mk-badge--not-proven',
          a.verdict === 'proven' ? 'PROVEN' : 'NOT PROVEN');
      });
      $('#fill').style.width = '100%';
      $('#runStatus').textContent = 'Готово · оракул вынес вердикты';
      $('#counter').textContent = f.scenarios_proven + ' / ' + total + ' proven · ASR ' + f.asr_percent + '%';
      $('#cProven').textContent = f.scenarios_proven;
      $('#cScored').textContent = f.scenarios_scored;
      $('#toReport').hidden = false;
      loadHistory();
    }).catch(() => { $('#runStatus').textContent = 'Прогон завершён'; });
  }

  // ── Экран 5 · Отчёт ──
  MK.tabs($('#repTabs'));
  function renderReport(runId) {
    if (!runId) { $('#verdict').innerHTML = '<span class="mk-meta">Нет выбранного прогона.</span>'; return; }
    $('#repMeta').textContent = 'Шаг 5 из 6 · ' + runId;
    $('#dlReport').onclick = () => window.open('/api/runs/' + runId + '/report', '_blank');
    j('/api/runs/' + runId + '/findings').then((f) => {
      const asr = f.asr_percent || 0;
      const compromised = (f.scenarios_proven || 0) > 0;
      $('#verdict').innerHTML =
        '<div class="mk-stack" style="gap:2px"><span class="mk-label">Итог</span>' +
        '<span class="mk-mono" style="font-size:28px;font-weight:700;color:var(--mk-color-' + (compromised ? 'negative' : 'positive') + ')">' +
        (compromised ? 'COMPROMISED' : 'CLEAN') + '</span></div>' +
        '<div class="mk-metrics" style="margin-left:auto">' +
        metric('ASR', asr + '%') + metric('Proven', (f.scenarios_proven || 0) + '/' + (f.scenarios_scored || 0)) +
        metric('Попыток', f.attempts_total || 0) + metric('Время, с', (f.timings && f.timings.total_seconds) || '—') + '</div>';
      const t = $('#findTable');
      t.innerHTML = th('Сценарий') + th('Предикат') + th('Вердикт') + th('Шагов') + th('Сек');
      (f.attempts || []).forEach((a) => {
        const proven = a.verdict === 'proven';
        t.innerHTML += td(a.scenario_id, 'mk-table__td--id') +
          td(a.target || '—', 'mk-table__td--mono') +
          '<div class="mk-table__td mk-table__td--verdict"><span class="mk-badge ' +
          (proven ? 'mk-badge--proven">PROVEN' : 'mk-badge--not-proven">NOT PROVEN') + '</span></div>' +
          td((a.steps ? a.steps.length : '—'), 'mk-table__td--mono') +
          td(a.seconds != null ? a.seconds : '—', 'mk-table__td--mono');
      });
    }).catch(() => { $('#verdict').innerHTML = '<span class="mk-meta">Отчёт недоступен.</span>'; $('#findTable').innerHTML = ''; });
    fetch('/api/runs/' + runId + '/report').then((r) => r.ok ? r.text() : '—').then((t) => { $('#reportText').textContent = t; });
  }
  const metric = (k, v) => '<div class="mk-metrics__cell"><span class="mk-metric__k">' + k + '</span><span class="mk-metric mk-mono">' + v + '</span></div>';
  const th = (t) => '<div class="mk-table__th">' + t + '</div>';
  const td = (t, c) => '<div class="mk-table__td ' + (c || '') + '">' + t + '</div>';

  // ── Экран 6 · Документ для бизнеса (не повторяет техотчёт) ──
  const audiences = () => [...document.querySelectorAll('#content section[data-screen="6"] .mk-chip')]
    .filter((c) => c.getAttribute('aria-pressed') === 'true').map((c) => c.textContent.trim());
  function updateKind() { $('#bizKind').textContent = 'business-brief · ' + (audiences().join(', ') || 'без аудитории'); }
  document.querySelectorAll('#content section[data-screen="6"] .mk-chip')
    .forEach((c) => c.addEventListener('click', () => setTimeout(updateKind, 0)));
  let reqFiles = [];
  function renderReq() {
    const box = $('#reqFiles'); box.innerHTML = '';
    reqFiles.forEach((f) => {
      const ext = (f.name.split('.').pop() || '').toUpperCase();
      const row = document.createElement('div'); row.className = 'mk-file-row';
      row.innerHTML = '<span class="mk-file-row__kind">' + ext + '</span><span class="mk-stack" style="gap:2px">' +
        '<span class="mk-file-row__name">' + f.name + '</span><span class="mk-file-row__meta">' + Math.round(f.size / 1024) + ' КБ</span></span>';
      box.appendChild(row);
    });
    $('#bizS3').textContent = reqFiles.length
      ? 'Учитывает загруженные регламенты (' + reqFiles.length + ')'
      : 'Загруженные политики и регламенты';
  }
  $('#reqInput').addEventListener('change', (e) => {
    [...e.target.files].forEach((f) => reqFiles.push(f));
    e.target.value = '';
    renderReq();
  });

  function renderBiz() {
    updateKind();
    $('#bizBanner').hidden = true; $('#bizDl').hidden = true;
    if (!openRunId) { $('#bizThesis').textContent = 'Сначала выполните или откройте прогон (шаги 3–5).'; return; }
    j('/api/runs/' + openRunId + '/findings').then((f) => {
      const proven = f.scenarios_proven || 0, scored = f.scenarios_scored || 0, asr = f.asr_percent || 0;
      const compromised = proven > 0;
      $('#bizS1').textContent = 'Вердикт ' + (compromised ? 'COMPROMISED' : 'CLEAN') + ', ASR ' + asr + '%, cross-user эффект — из отчёта';
      $('#bizThesis').textContent = compromised
        ? ('Агент нарушил разграничение доступа в ' + proven + ' из ' + scored + ' сценариев (ASR ' + asr +
           '%). Это не ошибка текста ответа, а обход контроля, подтверждённый наблюдаемым состоянием — вызовом инструмента за чужого клиента. Фикс — серверная проверка владения; повторный прогон в режиме protected подтвердит закрытие (цель ASR 0%).')
        : ('По ' + scored + ' сценариям доказанных нарушений нет (ASR ' + asr + '%). Риск в проверенных границах не подтверждён; рекомендуется поддерживать regression-набор.');
    }).catch(() => { $('#bizThesis').textContent = 'Не удалось прочитать результаты прогона.'; });
  }

  $('#bizBtn').addEventListener('click', function () {
    if (!openRunId) { $('#bizThesis').textContent = 'Сначала выполните или откройте прогон.'; return; }
    const btn = this; btn.disabled = true; btn.textContent = 'LLM формирует документ…';
    const fd = new FormData();
    fd.append('audience', audiences().join(', '));
    fd.append('note', $('#bizNote').value || '');
    reqFiles.forEach((f) => fd.append('files', f));
    j('/api/runs/' + openRunId + '/business', { method: 'POST', body: fd }).then((res) => {
      $('#bizDoc').textContent = res.markdown || '';
      $('#bizDocCard').hidden = false;
      $('#bizBannerSub').textContent = 'PDF · аудитория: ' + (res.audiences.join(', ') || '—') +
        ' · регламентов учтено: ' + res.regs;
      $('#bizBanner').hidden = false;
      const dl = () => window.open('/api/runs/' + openRunId + '/business.pdf', '_blank');
      $('#bizDl').hidden = false; $('#bizDl').onclick = dl; $('#bizDl2').onclick = dl;
      btn.textContent = 'Пересобрать документ'; btn.disabled = false;
    }).catch(() => { btn.textContent = 'Сформировать документ'; btn.disabled = false; });
  });

  loadHistory();
  loadTarget();
  show(1);
})();
