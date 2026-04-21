(function () {
  const MAX_NODES = 200;
  const TYPE_COLORS = {
    catalog:              '#7fd4ff',
    document:             '#f7a668',
    informationRegister:  '#a6e3a1',
    accumulationRegister: '#f2c94c',
    calculationRegister:  '#e1acff',
    accountingRegister:   '#ffb4b4',
    commonModule:         '#9cc8ff',
    commonForm:           '#bdbde3',
    commonCommand:        '#bdbde3',
    report:               '#ff9ecb',
    dataProcessor:        '#ff9ecb',
    chartOfAccounts:      '#d9b99b',
    chartOfCalculationTypes: '#d9b99b',
    chartOfCharacteristicTypes: '#d9b99b',
    enum:                 '#a2d2ff',
    constant:             '#c9ced6',
    subsystem:            '#c2f7a6',
    role:                 '#f0a5a5',
    businessProcess:      '#c8a6ff',
    task:                 '#f9c9d9',
    exchangePlan:         '#8cd9ff',
    httpService:          '#a3f5d7',
    webService:           '#a3f5d7',
    eventSubscription:    '#ffd27f',
    scheduledJob:         '#ffd27f',
    bslFile:              '#6b7480',
  };
  const DB_PALETTE = ['#7fd4ff', '#f7a668', '#a6e3a1', '#f2c94c', '#e1acff', '#ff9ecb', '#a3f5d7', '#bdbde3', '#ffd27f', '#ffb4b4'];

  const I18N = {
    ru: {
      search_placeholder: 'Поиск (слова через пробел)…',
      btn_clear: 'Очистить',
      btn_list: 'Список',
      btn_list_title: 'Показать список найденных объектов',
      btn_rebuild: 'Пересобрать',
      btn_rebuild_title: 'Пересобрать граф по рабочему каталогу',
      btn_back_title: 'Предыдущий поиск',
      btn_fwd_title: 'Следующий поиск',
      h_dbs: 'Базы',
      h_types: 'Типы',
      h_node: 'Узел',
      h_legend: 'Легенда',
      loading: 'загрузка…',
      no_dbs: 'нет зарегистрированных БД',
      no_types: 'нет данных',
      empty_details: 'Выберите узел на графе',
      all_dbs: 'Все базы',
      expand_btn: 'Развернуть соседей',
      expand_hint: 'Двойной клик — развернуть соседей',
      nodes_word: 'узлов',
      edges_word: 'рёбер',
      dbs_word: 'БД',
      legend_fill: 'Цвет заливки — тип объекта',
      legend_border: 'Цвет обводки — база данных',
      results_title: 'Результаты поиска',
      results_empty: 'Ничего не найдено',
      results_count_tpl: 'найдено: {n}',
    },
    en: {
      search_placeholder: 'Search (space-separated words)…',
      btn_clear: 'Clear',
      btn_list: 'List',
      btn_list_title: 'Show list of matched objects',
      btn_rebuild: 'Rebuild',
      btn_rebuild_title: 'Rebuild graph from the workspace',
      btn_back_title: 'Previous search',
      btn_fwd_title: 'Next search',
      h_dbs: 'Databases',
      h_types: 'Types',
      h_node: 'Node',
      h_legend: 'Legend',
      loading: 'loading…',
      no_dbs: 'no registered databases',
      no_types: 'no data',
      empty_details: 'Select a node on the graph',
      all_dbs: 'All databases',
      expand_btn: 'Expand neighbours',
      expand_hint: 'Double-click to expand neighbours',
      nodes_word: 'nodes',
      edges_word: 'edges',
      dbs_word: 'DBs',
      legend_fill: 'Fill colour — object type',
      legend_border: 'Border colour — database',
      results_title: 'Search results',
      results_empty: 'Nothing found',
      results_count_tpl: '{n} found',
    },
  };

  function detectLang() {
    const u = new URL(window.location.href);
    const q = (u.searchParams.get('lang') || '').toLowerCase();
    if (q === 'ru' || q === 'en') return q;
    const stored = localStorage.getItem('bslgraph.lang');
    if (stored === 'ru' || stored === 'en') return stored;
    return (navigator.language || '').toLowerCase().startsWith('ru') ? 'ru' : 'en';
  }

  const state = {
    stats: null,
    selectedDb: '',         // exactly one DB; empty only when no DBs at all
    allDbs: [],
    dbColor: {},
    lang: detectLang(),
    t: null,
    history: [],            // list of { query, types, results: [nodeRaw] }
    hCursor: -1,            // index into history; -1 means no entries
    lastResults: [],        // last search results (raw node objects)
  };
  state.t = I18N[state.lang];
  document.documentElement.lang = state.lang;

  const cy = cytoscape({
    container: document.getElementById('cy'),
    elements: [],
    wheelSensitivity: 0.2,
    minZoom: 0.1,
    maxZoom: 4,
    style: [
      { selector: 'node', style: {
        'background-color': ele => TYPE_COLORS[ele.data('type')] || '#94a3b8',
        'border-color': ele => state.dbColor[ele.data('db')] || '#334155',
        'border-width': 3,
        'label': 'data(label)',
        'font-size': 10,
        'color': '#e2e8f0',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 6,
        'text-wrap': 'wrap',
        'text-max-width': '200px',
        'line-height': 1.15,
        'text-background-color': '#1e293b',
        'text-background-opacity': 0.9,
        'text-background-padding': '4px',
        'text-background-shape': 'round-rectangle',
        'min-zoomed-font-size': 7,
        'width': 22, 'height': 22,
      }},
      { selector: 'node:selected', style: {
        'border-color': '#38bdf8', 'border-width': 4,
        'width': 28, 'height': 28,
        'text-background-color': '#0369a1',
        'text-background-opacity': 0.9,
      }},
      { selector: 'node.dim', style: {
        'opacity': 0.2,
      }},
      { selector: 'edge', style: {
        'width': 1.2,
        'line-color': '#475569',
        'target-arrow-color': '#475569',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
        'curve-style': 'bezier',
        'opacity': 0.7,
      }},
      { selector: 'edge.highlight', style: {
        'line-color': '#38bdf8',
        'target-arrow-color': '#38bdf8',
        'opacity': 1,
        'width': 2,
      }},
    ],
    layout: { name: 'preset' },
  });

  const LAYOUT_OPTS = {
    name: 'cose',
    animate: true,
    animationDuration: 700,
    animationEasing: 'ease-out',
    fit: true,
    padding: 40,
    nodeRepulsion: 40000,
    nodeOverlap: 30,
    idealEdgeLength: 220,
    edgeElasticity: 100,
    gravity: 0.12,
    nestingFactor: 1.2,
    numIter: 2000,
    initialTemp: 300,
    coolingFactor: 0.95,
    minTemp: 1.0,
    nodeDimensionsIncludeLabels: true,
  };

  async function api(path, opts) {
    const r = await fetch(path, opts);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }
  const apiGet = (p) => api(p);
  const apiPost = (p, body) => api(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });

  function breakCamelCase(s) {
    if (!s) return '';
    if (s.length < 14) return s;
    // Insert soft-break at lower→UPPER or digit→UPPER transitions (ASCII + Cyrillic)
    let out = s.replace(/([а-яa-z\d])([А-ЯA-Z])/g, '$1\n$2');
    // Any remaining line longer than 18 chars — hard-break every 16 chars
    return out
      .split('\n')
      .map(line => (line.length > 18 ? line.match(/.{1,16}/g).join('\n') : line))
      .join('\n');
  }

  function nodeLabel(node) {
    const p = node.properties || {};
    const raw = p.name || (node.id || '').split(':').pop() || node.id;
    return breakCamelCase(raw);
  }
  function dbOf(node) { return (node.properties && node.properties.db) || ''; }

  function dbsParam() {
    return state.selectedDb ? [state.selectedDb] : [];
  }
  function dbVisible(db) {
    if (!state.selectedDb) return true;
    return db === state.selectedDb;
  }

  function addElements(nodes, edges) {
    const existingIds = new Set(cy.nodes().map(n => n.id()));
    const toAddNodes = [];
    for (const n of nodes || []) {
      if (existingIds.has(n.id)) continue;
      if (!dbVisible(dbOf(n))) continue;
      if (cy.nodes().length + toAddNodes.length >= MAX_NODES) break;
      toAddNodes.push({ data: { id: n.id, type: n.type, label: nodeLabel(n), db: dbOf(n), raw: n } });
    }
    const existingEdges = new Set(cy.edges().map(e => `${e.data('source')}|${e.data('target')}|${e.data('label')}`));
    const toAddEdges = [];
    const allNodeIds = new Set([...existingIds, ...toAddNodes.map(x => x.data.id)]);
    for (const e of edges || []) {
      const src = e.source_id || e.sourceId;
      const tgt = e.target_id || e.targetId;
      const label = e.edge_type || e.type;
      if (!allNodeIds.has(src) || !allNodeIds.has(tgt)) continue;
      const key = `${src}|${tgt}|${label}`;
      if (existingEdges.has(key)) continue;
      toAddEdges.push({ data: { source: src, target: tgt, label } });
    }
    cy.add([...toAddNodes, ...toAddEdges]);
    cy.style().update();
    cy.layout(LAYOUT_OPTS).run();
  }

  function resetGraph() {
    cy.elements().remove();
  }

  function highlightNeighborhood(node) {
    cy.elements().removeClass('highlight').removeClass('dim');
    if (!node) return;
    const nbh = node.closedNeighborhood();
    cy.elements().not(nbh).addClass('dim');
    node.connectedEdges().addClass('highlight');
  }

  function showDetails(node) {
    const t = state.t;
    const d = document.getElementById('details');
    if (!node) {
      d.innerHTML = `<div class="empty">${t.empty_details}</div>`;
      highlightNeighborhood(null);
      return;
    }
    const p = node.data('raw')?.properties || {};
    const db = node.data('db') || p.db || '';
    d.innerHTML = `
      <div class="row"><span class="badge">${node.data('type')}</span>${db ? `<span class="badge db">db: ${db}</span>` : ''}</div>
      <div class="row"><span class="k">id:</span> <span class="v">${node.id()}</span></div>
      ${p.name ? `<div class="row"><span class="k">name:</span> <span class="v">${p.name}</span></div>` : ''}
      ${p.path ? `<div class="row"><span class="k">path:</span> <span class="v">${p.path}</span></div>` : ''}
      <div class="row"><button id="expand">${t.expand_btn}</button> <span class="hint">${t.expand_hint}</span></div>`;
    document.getElementById('expand')?.addEventListener('click', () => expand(node.id()));
    highlightNeighborhood(node);
  }

  async function expand(nodeId) {
    try {
      const data = await apiGet(`/api/graph/related/${encodeURIComponent(nodeId)}?depth=1`);
      addElements(data.nodes || [], data.edges || []);
    } catch (e) { console.error(e); }
  }

  cy.on('tap', 'node', (evt) => showDetails(evt.target));
  cy.on('dbltap', 'node', (evt) => expand(evt.target.id()));
  cy.on('tap', (evt) => { if (evt.target === cy) showDetails(null); });

  function computeTypeCounts() {
    const byTypeByDb = state.stats?.byTypeByDb || {};
    const dbs = state.selectedDb ? [state.selectedDb] : state.allDbs;
    const combined = {};
    for (const db of dbs) {
      const m = byTypeByDb[db] || {};
      for (const [t, n] of Object.entries(m)) combined[t] = (combined[t] || 0) + n;
    }
    return Object.entries(combined).sort((a, b) => b[1] - a[1]);
  }

  function renderStats() {
    const t = state.t;
    const s = state.stats || {};
    let nodes, edges;
    if (!state.selectedDb) {
      nodes = s.totalNodes || 0;
      edges = s.totalEdges || 0;
    } else {
      const byTypeByDb = s.byTypeByDb || {};
      const edgesByDb = s.edgesByDb || {};
      nodes = Object.values(byTypeByDb[state.selectedDb] || {}).reduce((a, b) => a + b, 0);
      edges = edgesByDb[state.selectedDb] || 0;
    }
    const suffix = state.selectedDb && state.allDbs.length > 1
      ? ` · ${state.selectedDb}`
      : '';
    document.getElementById('stats').innerHTML =
      `<strong>${nodes}</strong> ${t.nodes_word} · <strong>${edges}</strong> ${t.edges_word}` + suffix;
  }

  function renderTypes() {
    const t = state.t;
    const sorted = computeTypeCounts();
    const ul = document.getElementById('types');
    ul.innerHTML = sorted.length
      ? sorted.map(([ty, n]) => `<li data-type="${ty}"><span><span style="color:${TYPE_COLORS[ty] || '#8b95a4'}">●</span> ${ty}</span> <span class="n">${n}</span></li>`).join('')
      : `<li class="empty">${t.no_types}</li>`;
    ul.querySelectorAll('li[data-type]').forEach(li => {
      li.addEventListener('click', () => searchByType(li.dataset.type));
    });
  }

  function renderDbs() {
    const t = state.t;
    const byTypeByDb = state.stats?.byTypeByDb || {};
    const container = document.getElementById('dbs');
    const header = document.getElementById('h-dbs');
    header.style.display = '';
    container.style.display = '';
    if (!state.allDbs.length) {
      container.innerHTML = `<div class="empty">${t.no_dbs}</div>`;
      return;
    }
    const singleDb = state.allDbs.length === 1;
    const rows = state.allDbs.map(db => {
      const color = state.dbColor[db] || '#8b95a4';
      const n = Object.values(byTypeByDb[db] || {}).reduce((a, b) => a + b, 0);
      const checked = db === state.selectedDb;
      const disabledAttr = singleDb ? 'disabled' : '';
      return `<label><input type="radio" name="bsl-graph-db" ${checked ? 'checked' : ''} ${disabledAttr} data-db="${db}"> <span class="db-chip" style="background:${color};border-color:${color}"></span> <span class="db-name">${db}</span> <span class="db-n">${n}</span></label>`;
    });
    container.innerHTML = rows.join('');
    container.querySelectorAll('input[type=radio]').forEach(rb => {
      rb.addEventListener('change', onDbSelect);
    });
  }

  function renderLegend() {
    const t = state.t;
    const items = [];
    for (const db of state.allDbs) {
      const c = state.dbColor[db] || '#8b95a4';
      items.push(`<div class="row"><div class="sw-ring" style="border-color:${c}"></div>${db}</div>`);
    }
    items.push(`<div class="row" style="margin-top:6px;color:#8b95a4">${t.legend_fill}</div>`);
    items.push(`<div class="row" style="color:#8b95a4">${t.legend_border}</div>`);
    document.getElementById('legend').innerHTML = items.join('');
  }

  function syncCanvasVisibility() {
    cy.nodes().forEach(n => {
      n.style('display', dbVisible(n.data('db')) ? 'element' : 'none');
    });
    cy.edges().forEach(ed => {
      const srcVis = ed.source().style('display') !== 'none';
      const tgtVis = ed.target().style('display') !== 'none';
      ed.style('display', srcVis && tgtVis ? 'element' : 'none');
    });
  }

  function onDbSelect(e) {
    const db = e.target.dataset.db;
    if (!db || db === state.selectedDb) return;
    state.selectedDb = db;
    renderDbs();
    renderTypes();
    renderStats();
    syncCanvasVisibility();
  }

  function pushHistory(entry) {
    // Drop forward stack when a new search happens mid-history.
    state.history = state.history.slice(0, state.hCursor + 1);
    state.history.push(entry);
    state.hCursor = state.history.length - 1;
    updateNavButtons();
  }

  function updateNavButtons() {
    const back = document.getElementById('btn-back');
    const fwd = document.getElementById('btn-fwd');
    back.disabled = state.hCursor <= 0;
    fwd.disabled = state.hCursor < 0 || state.hCursor >= state.history.length - 1;
  }

  async function runSearch(opts, opts_recordHistory = true) {
    try {
      const payload = {
        query: opts.query || '',
        types: opts.types || [],
        limit: opts.limit || 30,
        dbs: dbsParam(),
      };
      const data = await apiPost('/api/graph/search', payload);
      resetGraph();
      addElements(data.nodes || [], data.edges || []);
      state.lastResults = data.nodes || [];
      renderResultsPanel();
      if (opts_recordHistory) {
        pushHistory({
          query: payload.query,
          types: payload.types.slice(),
          results: state.lastResults.slice(),
        });
      }
      return data;
    } catch (e) {
      console.error(e);
      return null;
    }
  }

  async function searchByType(type) {
    document.getElementById('q').value = '';
    await runSearch({ query: '', types: [type] });
  }

  async function searchByQuery(q) {
    if (!q.trim()) return;
    await runSearch({ query: q, types: [] });
  }

  async function navigateHistory(delta) {
    const next = state.hCursor + delta;
    if (next < 0 || next >= state.history.length) return;
    state.hCursor = next;
    const h = state.history[next];
    document.getElementById('q').value = h.query || '';
    await runSearch({ query: h.query, types: h.types || [] }, /* record */ false);
    updateNavButtons();
  }

  function focusNode(id) {
    const n = cy.getElementById(id);
    if (n && n.nonempty()) {
      cy.animate({
        center: { eles: n },
        zoom: Math.max(cy.zoom(), 1.2),
        duration: 400,
        easing: 'ease-out',
      });
      showDetails(n);
      return;
    }
    // Node not on the canvas yet — fetch its neighbourhood and show it.
    expand(id);
  }

  function renderResultsPanel() {
    const t = state.t;
    const body = document.getElementById('rp-body');
    const title = document.getElementById('rp-title');
    const items = state.lastResults || [];
    title.textContent =
      t.results_title + (items.length ? ' · ' + t.results_count_tpl.replace('{n}', items.length) : '');
    if (!items.length) {
      body.innerHTML = `<div class="rp-empty">${t.results_empty}</div>`;
      return;
    }
    body.innerHTML = items.map((n, i) => {
      const name = (n.properties && n.properties.name) || (n.id || '').split(':').pop();
      const db = (n.properties && n.properties.db) || '';
      const type = n.type || '';
      const color = state.dbColor[db] || '#8b95a4';
      return `<div class="rp-item" data-id="${escapeAttr(n.id)}">
        <div class="rp-dot" style="background:${TYPE_COLORS[type] || '#8b95a4'};border-color:${color}"></div>
        <div>
          <div class="rp-name">${escapeHtml(name)}</div>
          <div class="rp-meta">${type}${db ? ' · ' + db : ''}</div>
        </div>
      </div>`;
    }).join('');
    body.querySelectorAll('.rp-item').forEach(el => {
      el.addEventListener('click', () => focusNode(el.dataset.id));
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function escapeAttr(s) { return escapeHtml(s); }

  function toggleResultsPanel(force) {
    const panel = document.getElementById('results-panel');
    const shouldShow = force !== undefined ? force : panel.hasAttribute('hidden');
    if (shouldShow) {
      panel.removeAttribute('hidden');
      renderResultsPanel();
    } else {
      panel.setAttribute('hidden', '');
    }
  }

  async function loadStats() {
    const s = await apiGet('/api/graph/stats');
    state.stats = s;
    state.allDbs = (s.indexedDatabases || []).slice().sort();
    state.dbColor = {};
    state.allDbs.forEach((db, i) => { state.dbColor[db] = DB_PALETTE[i % DB_PALETTE.length]; });
    // Default: first DB selected. Empty only when no DBs are registered.
    if (!state.selectedDb || !state.allDbs.includes(state.selectedDb)) {
      state.selectedDb = state.allDbs[0] || '';
    }
    renderStats();
    renderDbs();
    renderTypes();
    renderLegend();
    cy.style().update();
  }

  function applyI18n() {
    const t = state.t;
    document.getElementById('q').placeholder = t.search_placeholder;
    document.getElementById('btn-clear').textContent = t.btn_clear;
    const btnList = document.getElementById('btn-list');
    btnList.textContent = t.btn_list;
    btnList.title = t.btn_list_title;
    const rebuild = document.getElementById('btn-rebuild');
    rebuild.textContent = t.btn_rebuild;
    rebuild.title = t.btn_rebuild_title;
    document.getElementById('btn-back').title = t.btn_back_title;
    document.getElementById('btn-fwd').title = t.btn_fwd_title;
    document.getElementById('h-dbs').textContent = t.h_dbs;
    document.getElementById('h-types').textContent = t.h_types;
    document.getElementById('h-node').textContent = t.h_node;
    document.getElementById('h-legend').textContent = t.h_legend;
    document.getElementById('dbs-loading').textContent = t.loading;
    document.getElementById('types-loading').textContent = t.loading;
    document.getElementById('details-empty').textContent = t.empty_details;
    document.getElementById('lang-select').value = state.lang;
  }

  document.getElementById('lang-select').addEventListener('change', (e) => {
    const newLang = e.target.value;
    localStorage.setItem('bslgraph.lang', newLang);
    const u = new URL(window.location.href);
    u.searchParams.set('lang', newLang);
    window.location.href = u.toString();
  });

  document.getElementById('q').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') searchByQuery(e.target.value);
  });
  document.getElementById('btn-clear').addEventListener('click', () => {
    document.getElementById('q').value = '';
    resetGraph();
    showDetails(null);
    state.lastResults = [];
    renderResultsPanel();
  });
  document.getElementById('btn-list').addEventListener('click', () => toggleResultsPanel());
  document.getElementById('rp-close').addEventListener('click', () => toggleResultsPanel(false));
  document.getElementById('btn-back').addEventListener('click', () => navigateHistory(-1));
  document.getElementById('btn-fwd').addEventListener('click', () => navigateHistory(+1));
  document.getElementById('btn-rebuild').addEventListener('click', async () => {
    const btn = document.getElementById('btn-rebuild');
    const prev = btn.textContent;
    btn.textContent = '…';
    btn.disabled = true;
    try {
      await apiPost('/api/graph/rebuild', {});
      await loadStats();
    } catch (e) { alert((state.t.btn_rebuild || 'Rebuild') + ' failed: ' + e.message); }
    finally { btn.textContent = prev; btn.disabled = false; }
  });

  applyI18n();
  loadStats();
})();
