/* MOROK components · поведение без фреймворка. Подключать после DOM. */
(function (global) {
  'use strict';
  const MK = {};

  /** Шаги: <nav class="mk-steps" data-mk-steps> с <button class="mk-step" data-step="N">. Событие 'mk:step' на nav. */
  MK.steps = function (nav) {
    const btns = [...nav.querySelectorAll('.mk-step')];
    let maxReached = 1;
    function set(n) {
      maxReached = Math.max(maxReached, n);
      btns.forEach((b) => {
        const i = Number(b.dataset.step);
        b.toggleAttribute('aria-current', false);
        if (i === n) b.setAttribute('aria-current', 'step');
        b.classList.toggle('mk-step--done', i < maxReached && i !== n);
        const num = b.querySelector('.mk-step__n');
        if (num) num.textContent = i < maxReached && i !== n ? '\u2713' : String(i);
      });
      nav.dispatchEvent(new CustomEvent('mk:step', { detail: { step: n } }));
    }
    btns.forEach((b) => b.addEventListener('click', () => set(Number(b.dataset.step))));
    return { set };
  };

  /** Вкладки: <div class="mk-tabs" data-mk-tabs> с <button class="mk-tab" data-tab="id">; панели [data-tab-panel="id"]. */
  MK.tabs = function (root) {
    const tabs = [...root.querySelectorAll('.mk-tab')];
    const scope = root.closest('[data-mk-tabs-scope]') || document;
    function set(id) {
      tabs.forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === id)));
      scope.querySelectorAll('[data-tab-panel]').forEach((p) => { p.hidden = p.dataset.tabPanel !== id; });
      root.dispatchEvent(new CustomEvent('mk:tab', { detail: { tab: id } }));
    }
    tabs.forEach((t) => t.addEventListener('click', () => set(t.dataset.tab)));
    const initial = tabs.find((t) => t.getAttribute('aria-selected') === 'true') || tabs[0];
    if (initial) set(initial.dataset.tab);
    return { set };
  };

  /** Чипы-переключатели: <button class="mk-chip" data-mk-chip aria-pressed="false">. */
  MK.chips = function (scope) {
    scope.querySelectorAll('[data-mk-chip]').forEach((c) => c.addEventListener('click', () => {
      c.setAttribute('aria-pressed', String(c.getAttribute('aria-pressed') !== 'true'));
    }));
  };

  /** Список сценариев: [data-mk-scenarios] с .mk-scenario[data-id]; событие 'mk:scenario'. */
  MK.scenarios = function (list) {
    const items = [...list.querySelectorAll('.mk-scenario')];
    function set(id) {
      items.forEach((i) => i.setAttribute('aria-selected', String(i.dataset.id === id)));
      list.dispatchEvent(new CustomEvent('mk:scenario', { detail: { id } }));
    }
    items.forEach((i) => i.addEventListener('click', () => set(i.dataset.id)));
    return { set };
  };

  /** Сворачивание сайдбара: кнопка [data-mk-toggle-sidebar], цель .mk-sidebar. */
  MK.sidebarToggle = function (btn, sidebar) {
    btn.addEventListener('click', () => { sidebar.hidden = !sidebar.hidden; });
  };

  /**
   * Симуляция прогона (для демо-витрины).
   * opts: { rows: NodeList .mk-attack-row (с .mk-badge внутри), verdicts: boolean[], progress: .mk-progress__fill,
   *         counter: el, log: .mk-log, cursor: el, interval=650, onDone }
   */
  MK.runSim = function (opts) {
    const rows = [...opts.rows];
    const total = rows.length;
    const t0 = Date.now();
    const stamp = () => '00:' + String(Math.floor((Date.now() - t0) / 1000)).padStart(2, '0');
    const setBadge = (row, cls, text) => {
      const b = row.querySelector('.mk-badge');
      b.className = 'mk-badge ' + cls; b.textContent = text;
      row.className = 'mk-attack-row' + (cls === 'mk-badge--proven' ? ' mk-attack-row--proven' : cls === 'mk-badge--pending' ? '' : ' mk-attack-row--not-proven');
    };
    const pushLog = (msg, cls) => {
      const line = document.createElement('div'); line.className = 'mk-log__line';
      line.innerHTML = '<span class="mk-log__t">' + stamp() + '</span><span class="mk-log__msg ' + (cls || '') + '">' + msg + '</span>';
      opts.log.insertBefore(line, opts.cursor || null);
      while (opts.log.querySelectorAll('.mk-log__line').length > 9) opts.log.querySelector('.mk-log__line').remove();
    };
    let i = 0, phase = 0;
    const tick = () => {
      if (i >= total) { clearInterval(timer); if (opts.cursor) opts.cursor.hidden = true; opts.onDone && opts.onDone(); return; }
      const row = rows[i]; const name = row.querySelector('.mk-attack-row__name').textContent;
      if (phase === 0) { setBadge(row, 'mk-badge--running', 'RUNNING'); pushLog('[' + (i + 1) + '/' + total + '] probe \u00b7 ' + name); }
      if (phase === 1) pushLog('agent \u2192 tool call \u00b7 trace ' + Math.random().toString(16).slice(2, 6) + '\u2026', 'mk-log__msg--agent');
      if (phase === 2) {
        const ok = opts.verdicts[i];
        setBadge(row, ok ? 'mk-badge--proven' : 'mk-badge--not-proven', ok ? 'PROVEN' : 'NOT PROVEN');
        pushLog(ok ? 'oracle \u00b7 state changed \u00b7 PROVEN' : 'oracle \u00b7 no cross-user effect \u00b7 NOT PROVEN', ok ? 'mk-log__msg--proven' : 'mk-log__msg--not-proven');
        i++;
        if (opts.progress) opts.progress.style.width = Math.round(100 * i / total) + '%';
        if (opts.counter) opts.counter.textContent = i + ' / ' + total + ' \u0430\u0442\u0430\u043a \u00b7 ' + Math.round(100 * i / total) + '%';
      }
      phase = (phase + 1) % 3;
    };
    const timer = setInterval(tick, opts.interval || 650);
    return { stop: () => clearInterval(timer) };
  };

  /** Автоинициализация по data-атрибутам. */
  MK.init = function (root) {
    root = root || document;
    root.querySelectorAll('[data-mk-steps]').forEach(MK.steps);
    root.querySelectorAll('[data-mk-tabs]').forEach(MK.tabs);
    root.querySelectorAll('[data-mk-scenarios]').forEach(MK.scenarios);
    MK.chips(root);
    const tg = root.querySelector('[data-mk-toggle-sidebar]'); const sb = root.querySelector('.mk-sidebar');
    if (tg && sb) MK.sidebarToggle(tg, sb);
  };

  global.MK = MK;
  if (document.readyState !== 'loading') MK.init(); else document.addEventListener('DOMContentLoaded', () => MK.init());
})(window);
