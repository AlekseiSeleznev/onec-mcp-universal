(function () {
  const MAX_NODES = 200;
  const DEFAULT_PATH_DEPTH = 6;
  const TYPE_COLORS = {
    catalog: '#7fd4ff',
    document: '#f7a668',
    informationRegister: '#a6e3a1',
    accumulationRegister: '#f2c94c',
    calculationRegister: '#e1acff',
    accountingRegister: '#ffb4b4',
    commonModule: '#9cc8ff',
    commonForm: '#bdbde3',
    commonCommand: '#bdbde3',
    report: '#ff9ecb',
    dataProcessor: '#ff9ecb',
    chartOfAccounts: '#d9b99b',
    chartOfCalculationTypes: '#d9b99b',
    chartOfCharacteristicTypes: '#d9b99b',
    enum: '#a2d2ff',
    constant: '#c9ced6',
    subsystem: '#c2f7a6',
    role: '#f0a5a5',
    businessProcess: '#c8a6ff',
    task: '#f9c9d9',
    exchangePlan: '#8cd9ff',
    httpService: '#a3f5d7',
    webService: '#a3f5d7',
    eventSubscription: '#ffd27f',
    scheduledJob: '#ffd27f',
    bslFile: '#6b7480',
  };
  const DB_PALETTE = ['#7fd4ff', '#f7a668', '#a6e3a1', '#f2c94c', '#e1acff', '#ff9ecb', '#a3f5d7', '#bdbde3', '#ffd27f', '#ffb4b4'];
  const TYPE_LABELS = {
    ru: {
      accumulationRegister: 'Регистр накопления',
      bslFile: 'BSL-файл',
      businessProcess: 'Бизнес-процесс',
      calculationRegister: 'Регистр расчёта',
      catalog: 'Справочник',
      chartOfAccounts: 'План счетов',
      chartOfCalculationTypes: 'План видов расчёта',
      chartOfCharacteristicTypes: 'План видов характеристик',
      commonCommand: 'Общая команда',
      commonForm: 'Общая форма',
      commonModule: 'Общий модуль',
      constant: 'Константа',
      dataProcessor: 'Обработка',
      document: 'Документ',
      documentJournal: 'Журнал документов',
      enum: 'Перечисление',
      exchangePlan: 'План обмена',
      httpService: 'HTTP-сервис',
      informationRegister: 'Регистр сведений',
      integrationService: 'Сервис интеграции',
      report: 'Отчёт',
      role: 'Роль',
      scheduledJob: 'Регламентное задание',
      settingsStorage: 'Хранилище настроек',
      subsystem: 'Подсистема',
      task: 'Задача',
      webService: 'Веб-сервис',
      wsReference: 'WS-ссылка',
      xdtoPackage: 'XDTO-пакет',
    },
    en: {
      accumulationRegister: 'Accumulation register',
      bslFile: 'BSL file',
      businessProcess: 'Business process',
      calculationRegister: 'Calculation register',
      catalog: 'Catalog',
      chartOfAccounts: 'Chart of accounts',
      chartOfCalculationTypes: 'Chart of calculation types',
      chartOfCharacteristicTypes: 'Chart of characteristic types',
      commonCommand: 'Common command',
      commonForm: 'Common form',
      commonModule: 'Common module',
      constant: 'Constant',
      dataProcessor: 'Data processor',
      document: 'Document',
      documentJournal: 'Document journal',
      enum: 'Enumeration',
      exchangePlan: 'Exchange plan',
      httpService: 'HTTP service',
      informationRegister: 'Information register',
      integrationService: 'Integration service',
      report: 'Report',
      role: 'Role',
      scheduledJob: 'Scheduled job',
      settingsStorage: 'Settings storage',
      subsystem: 'Subsystem',
      task: 'Task',
      webService: 'Web service',
      wsReference: 'WS reference',
      xdtoPackage: 'XDTO package',
    },
  };
  const EDGE_LABELS = {
    ru: {
      containsFile: 'Содержит BSL-файл',
      references: 'Использует',
    },
    en: {
      containsFile: 'Contains BSL file',
      references: 'Uses',
    },
  };

  const I18N = {
    ru: {
      search_placeholder: 'Поиск (слова через пробел)…',
      btn_clear: 'Очистить',
      btn_docs: 'Документация',
      btn_list: 'Список',
      btn_list_title: 'Показать список найденных объектов',
      btn_rebuild: 'Пересобрать',
      btn_rebuild_title: 'Пересобрать граф по рабочему каталогу',
      btn_back_title: 'Назад по графу',
      btn_fwd_title: 'Вперёд по графу',
      h_dbs: 'Базы',
      h_types: 'Типы',
      h_context: 'Контекст',
      h_node: 'Узел',
      h_analysis: 'Анализ',
      h_path: 'Путь',
      h_legend: 'Легенда',
      loading: 'загрузка…',
      no_dbs: 'нет зарегистрированных БД',
      no_types: 'нет данных',
      empty_details: 'Выберите узел на графе',
      expand_btn: 'Развернуть соседей',
      expand_hint: 'Двойной клик — развернуть соседей',
      focus_btn: 'Оставить только текущую окрестность',
      clear_unpinned_btn: 'Очистить всё кроме закреплённых',
      pin_btn: 'Закрепить узел',
      unpin_btn: 'Снять закрепление',
      set_source_btn: 'Выбрать как старт',
      set_target_btn: 'Выбрать как цель',
      nodes_word: 'узлов',
      edges_word: 'рёбер',
      legend_fill: 'Цвет заливки — тип объекта',
      legend_border: 'Цвет обводки — база данных',
      results_title: 'Результаты поиска',
      results_empty: 'Ничего не найдено',
      results_count_tpl: 'найдено: {n}',
      context_mode: 'Режим',
      context_db: 'База',
      context_filters: 'Фильтры',
      context_truncated: 'Результат усечён лимитами.',
      context_path_missing: 'Путь не найден в текущих ограничениях.',
      context_none: 'без фильтров',
      mode_overview: 'Обзор',
      mode_path: 'Путь',
      lbl_direction: 'Направление',
      direction_both: 'Обе стороны',
      direction_out: 'Исходящие',
      direction_in: 'Входящие',
      lbl_hide_bsl: 'Скрыть BSL-файлы',
      h_edge_filters: 'Типы связей',
      h_node_filters: 'Типы узлов',
      lbl_source: 'Старт:',
      lbl_target: 'Цель:',
      lbl_max_depth: 'Макс. глубина',
      btn_build_path: 'Построить путь',
      btn_clear_path: 'Очистить путь',
      path_status_ready: 'Выберите старт и цель для анализа пути.',
      path_status_wait_target: 'Выберите целевой узел.',
      path_status_wait_source: 'Выберите стартовый узел.',
      path_status_searching: 'Поиск пути…',
      path_status_found: 'Путь найден: {n} шаг.',
      path_status_found_many: 'Путь найден: {n} шагов.',
      path_status_not_found: 'Путь не найден.',
      path_status_depth_limit: 'Путь не найден в пределах maxDepth.',
      path_status_search_limit: 'Поиск пути остановлен лимитом обхода.',
      path_status_failed: 'Ошибка построения пути',
      path_steps_empty: 'Шаги пути появятся здесь.',
      query_loaded: 'Поиск применён из URL.',
      node_loaded: 'Окрестность узла загружена из URL.',
      mode_changed: 'Режим анализа переключён.',
      filter_hidden_bsl: 'BSL-файлы скрыты',
      filter_direction: 'направление: {value}',
      filter_edges: 'связи: {value}',
      filter_nodes: 'узлы: {value}',
      tag_pinned: 'закреплён',
      tag_source: 'старт',
      tag_target: 'цель',
      no_selected_node: 'Сначала выберите узел на графе.',
      no_pinned_nodes: 'Закреплённых узлов нет.',
      focus_failed: 'Не удалось загрузить окрестность узла.',
      rebuild_failed: 'Пересборка не удалась',
    },
    en: {
      search_placeholder: 'Search (space-separated words)…',
      btn_clear: 'Clear',
      btn_docs: 'Docs',
      btn_list: 'List',
      btn_list_title: 'Show list of matched objects',
      btn_rebuild: 'Rebuild',
      btn_rebuild_title: 'Rebuild graph from the workspace',
      btn_back_title: 'Back in graph history',
      btn_fwd_title: 'Forward in graph history',
      h_dbs: 'Databases',
      h_types: 'Types',
      h_context: 'Context',
      h_node: 'Node',
      h_analysis: 'Analysis',
      h_path: 'Path',
      h_legend: 'Legend',
      loading: 'loading…',
      no_dbs: 'no registered databases',
      no_types: 'no data',
      empty_details: 'Select a node on the graph',
      expand_btn: 'Expand neighbours',
      expand_hint: 'Double-click to expand neighbours',
      focus_btn: 'Keep only current neighborhood',
      clear_unpinned_btn: 'Clear all except pinned',
      pin_btn: 'Pin node',
      unpin_btn: 'Unpin node',
      set_source_btn: 'Set as source',
      set_target_btn: 'Set as target',
      nodes_word: 'nodes',
      edges_word: 'edges',
      legend_fill: 'Fill colour — object type',
      legend_border: 'Border colour — database',
      results_title: 'Search results',
      results_empty: 'Nothing found',
      results_count_tpl: '{n} found',
      context_mode: 'Mode',
      context_db: 'Database',
      context_filters: 'Filters',
      context_truncated: 'Result truncated by limits.',
      context_path_missing: 'Path was not found within current limits.',
      context_none: 'no filters',
      mode_overview: 'Overview',
      mode_path: 'Path',
      lbl_direction: 'Direction',
      direction_both: 'Both',
      direction_out: 'Outgoing',
      direction_in: 'Incoming',
      lbl_hide_bsl: 'Hide BSL files',
      h_edge_filters: 'Edge types',
      h_node_filters: 'Node types',
      lbl_source: 'Source:',
      lbl_target: 'Target:',
      lbl_max_depth: 'Max depth',
      btn_build_path: 'Build path',
      btn_clear_path: 'Clear path',
      path_status_ready: 'Pick source and target to analyze a path.',
      path_status_wait_target: 'Pick a target node.',
      path_status_wait_source: 'Pick a source node.',
      path_status_searching: 'Searching path…',
      path_status_found: 'Path found: {n} hop.',
      path_status_found_many: 'Path found: {n} hops.',
      path_status_not_found: 'Path not found.',
      path_status_depth_limit: 'Path not found within maxDepth.',
      path_status_search_limit: 'Path search stopped by traversal limit.',
      path_status_failed: 'Path lookup failed',
      path_steps_empty: 'Path steps will appear here.',
      query_loaded: 'Query loaded from URL.',
      node_loaded: 'Node neighborhood loaded from URL.',
      mode_changed: 'Analysis mode changed.',
      filter_hidden_bsl: 'BSL files hidden',
      filter_direction: 'direction: {value}',
      filter_edges: 'edges: {value}',
      filter_nodes: 'nodes: {value}',
      tag_pinned: 'pinned',
      tag_source: 'source',
      tag_target: 'target',
      no_selected_node: 'Select a node on the graph first.',
      no_pinned_nodes: 'No pinned nodes.',
      focus_failed: 'Failed to load node neighborhood.',
      rebuild_failed: 'Rebuild failed',
    },
  };

  function queryParams() {
    return new URL(window.location.href).searchParams;
  }

  function detectLang() {
    const q = (queryParams().get('lang') || '').toLowerCase();
    if (q === 'ru' || q === 'en') return q;
    const stored = localStorage.getItem('bslgraph.lang');
    if (stored === 'ru' || stored === 'en') return stored;
    return (navigator.language || '').toLowerCase().startsWith('ru') ? 'ru' : 'en';
  }

  const state = {
    stats: null,
    selectedDb: '',
    allDbs: [],
    dbColor: {},
    lang: detectLang(),
    t: null,
    navHistory: [],
    navCursor: -1,
    restoringNav: false,
    lastSnapshotKey: '',
    historyPushTimer: null,
    lastResults: [],
    mode: queryParams().get('mode') === 'path' ? 'path' : 'overview',
    selectedSourceId: '',
    selectedTargetId: '',
    pinnedNodeIds: new Set(),
    filters: {
      direction: 'both',
      hideBslFiles: false,
      edgeTypes: new Set(),
      nodeTypes: new Set(),
    },
    truncatedState: {
      related: false,
      path: false,
      reason: '',
    },
    currentPathData: null,
    currentSelectedNodeId: '',
    edgeTypes: [],
    boot: {
      db: queryParams().get('db') || '',
      q: queryParams().get('q') || '',
      nodeId: queryParams().get('nodeId') || '',
      mode: queryParams().get('mode') || '',
      appliedQuery: false,
      appliedNode: false,
    },
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
      {
        selector: 'node',
        style: {
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
          'width': 22,
          'height': 22,
        },
      },
      {
        selector: 'node:selected',
        style: {
          'border-color': '#38bdf8',
          'border-width': 4,
          'width': 28,
          'height': 28,
          'text-background-color': '#0369a1',
          'text-background-opacity': 0.9,
        },
      },
      {
        selector: 'node.pinned',
        style: {
          'border-color': '#f59e0b',
          'border-width': 5,
        },
      },
      {
        selector: 'node.path-node',
        style: {
          'background-color': '#38bdf8',
          'border-color': '#f8fafc',
          'border-width': 5,
          'opacity': 1,
        },
      },
      {
        selector: 'node.source-node',
        style: {
          'shape': 'diamond',
        },
      },
      {
        selector: 'node.target-node',
        style: {
          'shape': 'round-rectangle',
        },
      },
      {
        selector: 'node.dim',
        style: {
          'opacity': 0.18,
        },
      },
      {
        selector: 'edge',
        style: {
          'width': 1.2,
          'line-color': '#475569',
          'target-arrow-color': '#475569',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.8,
          'curve-style': 'bezier',
          'opacity': 0.7,
          'label': ele => displayEdgeType(ele.data('rawLabel') || ele.data('label')),
          'font-size': 8,
          'color': '#94a3b8',
          'text-background-color': '#0f172a',
          'text-background-opacity': 0.85,
          'text-background-padding': '2px',
          'text-rotation': 'autorotate',
        },
      },
      {
        selector: 'edge.highlight',
        style: {
          'line-color': '#38bdf8',
          'target-arrow-color': '#38bdf8',
          'opacity': 1,
          'width': 2,
        },
      },
      {
        selector: 'edge.path-edge',
        style: {
          'line-color': '#f59e0b',
          'target-arrow-color': '#f59e0b',
          'opacity': 1,
          'width': 3,
          'z-index': 999,
          'color': '#fcd34d',
        },
      },
      {
        selector: 'edge.dim',
        style: {
          'opacity': 0.12,
        },
      },
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

  function showDialog(message) {
    const modal = document.getElementById('dialog-modal');
    const messageEl = document.getElementById('dialog-message');
    if (!modal || !messageEl) return;
    messageEl.textContent = String(message || '');
    modal.hidden = false;
  }

  function hideDialog() {
    const modal = document.getElementById('dialog-modal');
    if (modal) modal.hidden = true;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function escapeAttr(s) {
    return escapeHtml(s);
  }

  function breakCamelCase(s) {
    if (!s) return '';
    if (s.length < 14) return s;
    let out = s.replace(/([а-яa-z\d])([А-ЯA-Z])/g, '$1\n$2');
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

  function rawNodeName(node) {
    const p = node?.properties || {};
    return p.name || (node?.id || '').split(':').pop() || node?.id || '';
  }

  function dbOf(node) {
    return (node.properties && node.properties.db) || '';
  }

  function displayNodeType(type) {
    return TYPE_LABELS[state.lang]?.[type] || type;
  }

  function displayEdgeType(type) {
    return EDGE_LABELS[state.lang]?.[type] || type;
  }

  function adjustPathDepth(delta) {
    const input = document.getElementById('path-depth');
    const min = Number(input.min || 1);
    const max = Number(input.max || 12);
    const current = Number(input.value || DEFAULT_PATH_DEPTH);
    const next = Math.max(min, Math.min(max, current + delta));
    input.value = String(next);
  }

  function dbsParam() {
    return state.selectedDb ? [state.selectedDb] : [];
  }

  function dbVisible(db) {
    if (!state.selectedDb) return true;
    return db === state.selectedDb;
  }

  function nodeTypeListForCurrentDb() {
    const byTypeByDb = state.stats?.byTypeByDb || {};
    const dbs = state.selectedDb ? [state.selectedDb] : state.allDbs;
    const counts = {};
    for (const db of dbs) {
      const item = byTypeByDb[db] || {};
      for (const [type, count] of Object.entries(item)) counts[type] = (counts[type] || 0) + count;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }

  function edgeTypeListForCurrentDb() {
    const byDb = state.stats?.edgeTypesByDb || {};
    const counts = {};
    const dbs = state.selectedDb ? [state.selectedDb] : state.allDbs;
    for (const db of dbs) {
      const item = byDb[db] || {};
      for (const [type, count] of Object.entries(item)) counts[type] = (counts[type] || 0) + count;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }

  function allNodeTypesSelected() {
    return Array.from(state.filters.nodeTypes);
  }

  function allEdgeTypesSelected() {
    return Array.from(state.filters.edgeTypes);
  }

  function currentAnalysisPayload() {
    const includeNodeTypes = allNodeTypesSelected();
    const excludeNodeTypes = state.filters.hideBslFiles ? ['bslFile'] : [];
    return {
      direction: state.filters.direction,
      edgeTypes: allEdgeTypesSelected(),
      includeNodeTypes,
      excludeNodeTypes,
      dbs: dbsParam(),
    };
  }

  function resetGraph(preserveState = false) {
    cy.elements().remove();
    if (!preserveState) {
      state.currentSelectedNodeId = '';
      state.currentPathData = null;
      state.truncatedState.related = false;
      state.truncatedState.path = false;
      state.truncatedState.reason = '';
    }
  }

  function ensurePinnedNodeVisibility() {
    for (const id of Array.from(state.pinnedNodeIds)) {
      if (cy.getElementById(id).empty()) state.pinnedNodeIds.delete(id);
    }
  }

  function applyNodeDecorations() {
    cy.nodes().removeClass('pinned').removeClass('path-node').removeClass('source-node').removeClass('target-node').removeClass('dim');
    cy.edges().removeClass('path-edge').removeClass('highlight').removeClass('dim');
    ensurePinnedNodeVisibility();

    state.pinnedNodeIds.forEach(id => {
      const node = cy.getElementById(id);
      if (node.nonempty()) node.addClass('pinned');
    });
    if (state.selectedSourceId) {
      const node = cy.getElementById(state.selectedSourceId);
      if (node.nonempty()) node.addClass('source-node');
    }
    if (state.selectedTargetId) {
      const node = cy.getElementById(state.selectedTargetId);
      if (node.nonempty()) node.addClass('target-node');
    }

    if (state.currentPathData?.pathFound) {
      const pathNodeIds = new Set((state.currentPathData.nodes || []).map(n => n.id));
      const pathEdgeKeys = new Set((state.currentPathData.edges || []).map(e => `${e.sourceId || e.source_id}|${e.targetId || e.target_id}|${e.type || e.edge_type}`));
      cy.nodes().forEach(node => {
        if (pathNodeIds.has(node.id())) node.addClass('path-node');
        else node.addClass('dim');
      });
      cy.edges().forEach(edge => {
        const key = `${edge.data('source')}|${edge.data('target')}|${edge.data('label')}`;
        if (pathEdgeKeys.has(key)) edge.addClass('path-edge');
        else edge.addClass('dim');
      });
    } else if (state.currentSelectedNodeId) {
      const node = cy.getElementById(state.currentSelectedNodeId);
      if (node.nonempty()) {
        const nbh = node.closedNeighborhood();
        cy.elements().not(nbh).addClass('dim');
        node.connectedEdges().addClass('highlight');
      }
    }
  }

  function addElements(nodes, edges, opts) {
    const options = opts || {};
    const positions = options.positions || {};
    const existingIds = new Set(cy.nodes().map(n => n.id()));
    const toAddNodes = [];
    for (const n of nodes || []) {
      if (existingIds.has(n.id)) continue;
      if (!dbVisible(dbOf(n))) continue;
      if (cy.nodes().length + toAddNodes.length >= MAX_NODES) break;
      const entry = { data: { id: n.id, type: n.type, label: nodeLabel(n), db: dbOf(n), raw: n } };
      if (positions[n.id]) entry.position = positions[n.id];
      toAddNodes.push(entry);
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
      toAddEdges.push({ data: { source: src, target: tgt, label, rawLabel: label } });
    }
    cy.add([...toAddNodes, ...toAddEdges]);
    applyNodeDecorations();
    cy.style().update();
    if (!options.skipLayout) cy.layout(LAYOUT_OPTS).run();
  }

  function nodeDisplayNameById(id) {
    const node = cy.getElementById(id);
    if (node.nonempty()) return rawNodeName(node.data('raw'));
    const found = state.lastResults.find(n => n.id === id);
    return rawNodeName(found || { id });
  }

  function focusCyNode(node) {
    cy.animate({
      center: { eles: node },
      zoom: Math.max(cy.zoom(), 1.15),
      duration: 400,
      easing: 'ease-out',
    });
  }

  function updatePathSummary() {
    const sourceEl = document.getElementById('path-source');
    const targetEl = document.getElementById('path-target');
    sourceEl.textContent = state.selectedSourceId ? nodeDisplayNameById(state.selectedSourceId) : '—';
    targetEl.textContent = state.selectedTargetId ? nodeDisplayNameById(state.selectedTargetId) : '—';
  }

  function translateDirection(value) {
    const t = state.t;
    if (value === 'out') return t.direction_out;
    if (value === 'in') return t.direction_in;
    return t.direction_both;
  }

  function renderContextSummary() {
    const t = state.t;
    const box = document.getElementById('context-summary');
    const filterPills = [];
    if (state.filters.direction !== 'both') {
      filterPills.push(t.filter_direction.replace('{value}', translateDirection(state.filters.direction)));
    }
    if (state.filters.hideBslFiles) filterPills.push(t.filter_hidden_bsl);
    if (state.filters.edgeTypes.size) filterPills.push(t.filter_edges.replace('{value}', Array.from(state.filters.edgeTypes).map(displayEdgeType).join(', ')));
    if (state.filters.nodeTypes.size) filterPills.push(t.filter_nodes.replace('{value}', Array.from(state.filters.nodeTypes).map(displayNodeType).join(', ')));

    const warnings = [];
    if (state.truncatedState.related || state.truncatedState.path) warnings.push(t.context_truncated);
    if (state.truncatedState.reason && state.truncatedState.reason !== 'search_limit') warnings.push(t.context_path_missing);

    const nodeCount = cy.nodes().filter(n => n.style('display') !== 'none').length;
    const edgeCount = cy.edges().filter(e => e.style('display') !== 'none').length;
    const pills = [
      `<span class="pill">${escapeHtml(t.context_mode)}: ${escapeHtml(state.mode === 'path' ? t.mode_path : t.mode_overview)}</span>`,
      `<span class="pill">${escapeHtml(t.context_db)}: ${escapeHtml(state.selectedDb || '—')}</span>`,
      `<span class="pill">${nodeCount} ${escapeHtml(t.nodes_word)}</span>`,
      `<span class="pill">${edgeCount} ${escapeHtml(t.edges_word)}</span>`,
      ...filterPills.map(item => `<span class="pill">${escapeHtml(item)}</span>`),
      ...Array.from(state.pinnedNodeIds).map(() => `<span class="pill">${escapeHtml(t.tag_pinned)}</span>`),
    ];

    box.innerHTML = `
      <div class="row">${pills.join('') || `<span class="pill">${escapeHtml(t.context_none)}</span>`}</div>
      <div class="row"><span class="k">${escapeHtml(t.context_filters)}:</span> <span class="v">${escapeHtml(filterPills.join(' · ') || t.context_none)}</span></div>
      ${warnings.map(item => `<div class="row warn">${escapeHtml(item)}</div>`).join('')}
    `;
  }

  function showDetails(node) {
    const t = state.t;
    const details = document.getElementById('details');
    if (!node) {
      state.currentSelectedNodeId = '';
      details.innerHTML = `<div class="empty">${t.empty_details}</div>`;
      applyNodeDecorations();
      renderContextSummary();
      return;
    }
    state.currentSelectedNodeId = node.id();
    const raw = node.data('raw') || {};
    const props = raw.properties || {};
    const db = node.data('db') || props.db || '';
    const isPinned = state.pinnedNodeIds.has(node.id());
    const isSource = state.selectedSourceId === node.id();
    const isTarget = state.selectedTargetId === node.id();
    const badges = [
      `<span class="badge">${escapeHtml(displayNodeType(node.data('type')))}</span>`,
      db ? `<span class="badge db">db: ${escapeHtml(db)}</span>` : '',
      isPinned ? `<span class="badge">${escapeHtml(t.tag_pinned)}</span>` : '',
      isSource ? `<span class="badge">${escapeHtml(t.tag_source)}</span>` : '',
      isTarget ? `<span class="badge">${escapeHtml(t.tag_target)}</span>` : '',
    ].filter(Boolean).join('');

    details.innerHTML = `
      <div class="row">${badges}</div>
      <div class="row"><span class="k">id:</span> <span class="v">${escapeHtml(node.id())}</span></div>
      ${props.name ? `<div class="row"><span class="k">name:</span> <span class="v">${escapeHtml(props.name)}</span></div>` : ''}
      ${props.path ? `<div class="row"><span class="k">path:</span> <span class="v">${escapeHtml(props.path)}</span></div>` : ''}
      <div class="row actions">
        <button id="expand">${escapeHtml(t.expand_btn)}</button>
        <button id="toggle-pin">${escapeHtml(isPinned ? t.unpin_btn : t.pin_btn)}</button>
      </div>
      <div class="row actions">
        <button id="set-source">${escapeHtml(t.set_source_btn)}</button>
        <button id="set-target">${escapeHtml(t.set_target_btn)}</button>
      </div>
      <div class="hint">${escapeHtml(t.expand_hint)}</div>
    `;
    document.getElementById('expand')?.addEventListener('click', () => expand(node.id()));
    document.getElementById('toggle-pin')?.addEventListener('click', () => togglePinned(node.id()));
    document.getElementById('set-source')?.addEventListener('click', () => setPathEndpoint('source', node.id()));
    document.getElementById('set-target')?.addEventListener('click', () => setPathEndpoint('target', node.id()));
    applyNodeDecorations();
    renderContextSummary();
  }

  function syncCanvasVisibility() {
    cy.nodes().forEach(node => {
      node.style('display', dbVisible(node.data('db')) ? 'element' : 'none');
    });
    cy.edges().forEach(edge => {
      const srcVis = edge.source().style('display') !== 'none';
      const tgtVis = edge.target().style('display') !== 'none';
      edge.style('display', srcVis && tgtVis ? 'element' : 'none');
    });
    applyNodeDecorations();
    renderContextSummary();
  }

  function renderResultsPanel() {
    const t = state.t;
    const body = document.getElementById('rp-body');
    const title = document.getElementById('rp-title');
    const items = state.lastResults || [];
    title.textContent = t.results_title + (items.length ? ' · ' + t.results_count_tpl.replace('{n}', items.length) : '');
    if (!items.length) {
      body.innerHTML = `<div class="rp-empty">${t.results_empty}</div>`;
      return;
    }
    body.innerHTML = items.map(n => {
      const name = rawNodeName(n);
      const db = (n.properties && n.properties.db) || '';
      const type = n.type || '';
      const color = state.dbColor[db] || '#8b95a4';
      return `<div class="rp-item" data-id="${escapeAttr(n.id)}">
        <div class="rp-dot" style="background:${TYPE_COLORS[type] || '#8b95a4'};border-color:${color}"></div>
        <div>
          <div class="rp-name">${escapeHtml(name)}</div>
          <div class="rp-meta">${escapeHtml(displayNodeType(type))}${db ? ' · ' + escapeHtml(db) : ''}</div>
        </div>
      </div>`;
    }).join('');
    body.querySelectorAll('.rp-item').forEach(el => {
      el.addEventListener('click', () => focusNode(el.dataset.id));
    });
  }

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

  function captureSnapshot() {
    return {
      query: document.getElementById('q').value || '',
      selectedDb: state.selectedDb,
      mode: state.mode,
      selectedSourceId: state.selectedSourceId,
      selectedTargetId: state.selectedTargetId,
      pinnedNodeIds: Array.from(state.pinnedNodeIds),
      filters: {
        direction: state.filters.direction,
        hideBslFiles: state.filters.hideBslFiles,
        edgeTypes: Array.from(state.filters.edgeTypes),
        nodeTypes: Array.from(state.filters.nodeTypes),
      },
      truncatedState: { ...state.truncatedState },
      currentPathData: state.currentPathData ? JSON.parse(JSON.stringify(state.currentPathData)) : null,
      currentSelectedNodeId: state.currentSelectedNodeId,
      lastResults: JSON.parse(JSON.stringify(state.lastResults || [])),
      pathDepth: Number(document.getElementById('path-depth').value || DEFAULT_PATH_DEPTH),
      zoom: cy.zoom(),
      pan: cy.pan(),
      positions: Object.fromEntries(cy.nodes().map(node => [node.id(), node.position()])),
      nodes: cy.nodes().map(node => node.data('raw')).filter(Boolean),
      edges: cy.edges().map(edge => ({
        sourceId: edge.data('source'),
        targetId: edge.data('target'),
        type: edge.data('rawLabel') || edge.data('label'),
      })),
    };
  }

  function snapshotKey(snapshot) {
    return JSON.stringify({
      q: snapshot.query,
      db: snapshot.selectedDb,
      mode: snapshot.mode,
      src: snapshot.selectedSourceId,
      tgt: snapshot.selectedTargetId,
      sel: snapshot.currentSelectedNodeId,
      pins: snapshot.pinnedNodeIds,
      dir: snapshot.filters.direction,
      hide: snapshot.filters.hideBslFiles,
      et: snapshot.filters.edgeTypes,
      nt: snapshot.filters.nodeTypes,
      zoom: snapshot.zoom,
      pan: snapshot.pan,
      path: snapshot.currentPathData ? {
        found: snapshot.currentPathData.pathFound,
        reason: snapshot.currentPathData.reason,
        nodes: (snapshot.currentPathData.nodes || []).map(n => n.id),
        edges: (snapshot.currentPathData.edges || []).map(e => `${e.sourceId || e.source_id}|${e.targetId || e.target_id}|${e.type || e.edge_type}`),
      } : null,
      graphNodes: snapshot.nodes.map(node => node.id),
      graphEdges: snapshot.edges.map(edge => `${edge.sourceId}|${edge.targetId}|${edge.type}`),
    });
  }

  function pushGraphHistory() {
    if (state.restoringNav) return;
    const snapshot = captureSnapshot();
    const key = snapshotKey(snapshot);
    if (state.lastSnapshotKey === key) return;
    state.navHistory = state.navHistory.slice(0, state.navCursor + 1);
    state.navHistory.push(snapshot);
    state.navCursor = state.navHistory.length - 1;
    state.lastSnapshotKey = key;
    updateNavButtons();
  }

  function queueGraphHistory(delay = 0) {
    if (state.historyPushTimer) window.clearTimeout(state.historyPushTimer);
    state.historyPushTimer = window.setTimeout(() => {
      state.historyPushTimer = null;
      pushGraphHistory();
    }, delay);
  }

  function updateNavButtons() {
    const back = document.getElementById('btn-back');
    const fwd = document.getElementById('btn-fwd');
    back.disabled = state.navCursor <= 0;
    fwd.disabled = state.navCursor < 0 || state.navCursor >= state.navHistory.length - 1;
  }

  function applySnapshot(snapshot) {
    state.restoringNav = true;
    state.selectedDb = snapshot.selectedDb;
    state.mode = snapshot.mode;
    state.selectedSourceId = snapshot.selectedSourceId;
    state.selectedTargetId = snapshot.selectedTargetId;
    state.pinnedNodeIds = new Set(snapshot.pinnedNodeIds || []);
    state.filters.direction = snapshot.filters?.direction || 'both';
    state.filters.hideBslFiles = !!snapshot.filters?.hideBslFiles;
    state.filters.edgeTypes = new Set(snapshot.filters?.edgeTypes || []);
    state.filters.nodeTypes = new Set(snapshot.filters?.nodeTypes || []);
    state.truncatedState = {
      related: !!snapshot.truncatedState?.related,
      path: !!snapshot.truncatedState?.path,
      reason: snapshot.truncatedState?.reason || '',
    };
    state.currentPathData = snapshot.currentPathData ? JSON.parse(JSON.stringify(snapshot.currentPathData)) : null;
    state.currentSelectedNodeId = snapshot.currentSelectedNodeId || '';
    state.lastResults = JSON.parse(JSON.stringify(snapshot.lastResults || []));

    document.getElementById('q').value = snapshot.query || '';
    document.getElementById('mode-select').value = state.mode;
    document.getElementById('direction-select').value = state.filters.direction;
    document.getElementById('hide-bsl-files').checked = state.filters.hideBslFiles;
    document.getElementById('path-depth').value = String(snapshot.pathDepth || DEFAULT_PATH_DEPTH);

    renderDbs();
    renderTypes();
    renderStats();
    renderFilters();
    renderLegend();
    resetGraph(true);
    addElements(snapshot.nodes || [], snapshot.edges || [], {
      skipLayout: true,
      positions: snapshot.positions || {},
    });
    if (typeof snapshot.zoom === 'number') cy.zoom(snapshot.zoom);
    if (snapshot.pan && typeof snapshot.pan.x === 'number' && typeof snapshot.pan.y === 'number') cy.pan(snapshot.pan);
    else if (cy.elements().length) cy.fit(cy.elements(), 60);
    renderResultsPanel();
    updatePathSummary();
    renderPathSteps();
    applyMode();

    if (state.currentSelectedNodeId) {
      const node = cy.getElementById(state.currentSelectedNodeId);
      if (node.nonempty()) showDetails(node);
      else showDetails(null);
    } else {
      showDetails(null);
    }
    state.restoringNav = false;
  }

  async function navigateHistory(delta) {
    const next = state.navCursor + delta;
    if (next < 0 || next >= state.navHistory.length) return;
    state.navCursor = next;
    const snapshot = state.navHistory[next];
    applySnapshot(snapshot);
    state.lastSnapshotKey = snapshotKey(snapshot);
    updateNavButtons();
  }

  async function runSearch(opts, recordHistory = true) {
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
      renderContextSummary();
      if (recordHistory) pushGraphHistory();
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

  async function searchByQuery(query) {
    if (!query.trim()) return;
    await runSearch({ query, types: [] });
  }

  function relatedQueryString(payload, depth, override) {
    const params = new URLSearchParams();
    params.set('depth', String(depth || 1));
    if (payload.direction) params.set('direction', payload.direction);
    const edgeTypes = override?.edgeTypes || payload.edgeTypes || [];
    const includeNodeTypes = override?.includeNodeTypes || payload.includeNodeTypes || [];
    const excludeNodeTypes = override?.excludeNodeTypes || payload.excludeNodeTypes || [];
    const dbs = override?.dbs || payload.dbs || [];
    for (const value of edgeTypes) params.append('edge_types', value);
    for (const value of includeNodeTypes) params.append('include_node_types', value);
    for (const value of excludeNodeTypes) params.append('exclude_node_types', value);
    for (const value of dbs) params.append('dbs', value);
    if (override?.limitNodes) params.set('limit_nodes', String(override.limitNodes));
    if (override?.limitEdges) params.set('limit_edges', String(override.limitEdges));
    return params.toString();
  }

  async function expand(nodeId, opts) {
    const options = opts || {};
    try {
      const payload = currentAnalysisPayload();
      const qs = relatedQueryString(payload, options.depth || 1, {
        limitNodes: options.limitNodes,
        limitEdges: options.limitEdges,
      });
      const data = await apiGet(`/api/graph/related/${encodeURIComponent(nodeId)}?${qs}`);
      state.truncatedState.related = !!data.truncated;
      if (options.replace) {
        resetGraph();
      }
      addElements(data.nodes || [], data.edges || []);
      const node = cy.getElementById(nodeId);
      if (node.nonempty()) {
        showDetails(node);
        focusCyNode(node);
      }
      renderContextSummary();
      queueGraphHistory(node.nonempty() ? 450 : 0);
      return data;
    } catch (e) {
      console.error(e);
      return null;
    }
  }

  function focusNode(id) {
    const node = cy.getElementById(id);
    if (node.nonempty()) {
      focusCyNode(node);
      showDetails(node);
      queueGraphHistory(450);
      return;
    }
    expand(id);
  }

  function pathStatusMessage(reason, hopCount) {
    const t = state.t;
    if (reason === 'searching') return t.path_status_searching;
    if (reason === 'ready') return t.path_status_ready;
    if (reason === 'wait_source') return t.path_status_wait_source;
    if (reason === 'wait_target') return t.path_status_wait_target;
    if (reason === 'depth_limit') return t.path_status_depth_limit;
    if (reason === 'search_limit') return t.path_status_search_limit;
    if (reason === 'not_found') return t.path_status_not_found;
    if (reason === 'failed') return t.path_status_failed;
    if (reason === 'found') {
      if (hopCount === 1) return t.path_status_found.replace('{n}', String(hopCount));
      return t.path_status_found_many.replace('{n}', String(hopCount));
    }
    return t.path_status_ready;
  }

  function renderPathSteps() {
    const box = document.getElementById('path-steps');
    const status = document.getElementById('path-status');
    const pathData = state.currentPathData;
    if (!pathData) {
      status.textContent = pathStatusMessage(state.selectedSourceId ? (state.selectedTargetId ? 'ready' : 'wait_target') : 'wait_source');
      box.innerHTML = `<div class="empty">${escapeHtml(state.t.path_steps_empty)}</div>`;
      renderContextSummary();
      return;
    }
    if (!pathData.pathFound) {
      status.textContent = pathStatusMessage(pathData.reason || 'not_found', 0);
      box.innerHTML = `<div class="empty">${escapeHtml(state.t.path_steps_empty)}</div>`;
      renderContextSummary();
      return;
    }
    status.textContent = pathStatusMessage('found', pathData.hopCount || 0);
    const nodes = pathData.nodes || [];
    const edges = pathData.edges || [];
    box.innerHTML = edges.map((edge, index) => {
      const from = nodes[index];
      const to = nodes[index + 1];
      return `<div class="path-step">
        <div>${escapeHtml(rawNodeName(from))}</div>
          <div class="arrow">→ ${escapeHtml(displayEdgeType(edge.type || edge.edge_type || ''))} →</div>
        <div>${escapeHtml(rawNodeName(to))}</div>
      </div>`;
    }).join('');
    renderContextSummary();
  }

  function setPathEndpoint(kind, nodeId) {
    if (kind === 'source') state.selectedSourceId = nodeId;
    else state.selectedTargetId = nodeId;
    state.currentPathData = null;
    updatePathSummary();
    renderPathSteps();
    applyNodeDecorations();
    renderContextSummary();
    pushGraphHistory();
  }

  async function buildPath() {
    const status = document.getElementById('path-status');
    if (!state.selectedSourceId) {
      status.textContent = pathStatusMessage('wait_source');
      return;
    }
    if (!state.selectedTargetId) {
      status.textContent = pathStatusMessage('wait_target');
      return;
    }
    status.textContent = pathStatusMessage('searching');
    try {
      const payload = currentAnalysisPayload();
      const maxDepth = Number(document.getElementById('path-depth').value || DEFAULT_PATH_DEPTH);
      const data = await apiPost('/api/graph/path', {
        sourceId: state.selectedSourceId,
        targetId: state.selectedTargetId,
        maxDepth,
        edgeTypes: payload.edgeTypes,
        includeNodeTypes: payload.includeNodeTypes,
        excludeNodeTypes: payload.excludeNodeTypes,
        dbs: payload.dbs,
        direction: payload.direction,
      });
      state.currentPathData = data;
      state.truncatedState.path = !!data.truncated;
      state.truncatedState.reason = data.reason || '';
      resetGraph();
      addElements(data.nodes || [], data.edges || []);
      const src = cy.getElementById(state.selectedSourceId);
      const tgt = cy.getElementById(state.selectedTargetId);
      if (src.nonempty()) showDetails(src);
      if (src.nonempty() && tgt.nonempty()) {
        cy.fit(src.union(tgt).union(cy.edges('.path-edge')), 60);
      }
      renderPathSteps();
      applyNodeDecorations();
      pushGraphHistory();
    } catch (e) {
      console.error(e);
      state.currentPathData = { pathFound: false, nodes: [], edges: [], reason: 'failed', truncated: false };
      renderPathSteps();
      pushGraphHistory();
    }
  }

  function clearPath() {
    state.currentPathData = null;
    state.truncatedState.path = false;
    state.truncatedState.reason = '';
    updatePathSummary();
    renderPathSteps();
    applyNodeDecorations();
    pushGraphHistory();
  }

  function togglePinned(nodeId) {
    if (state.pinnedNodeIds.has(nodeId)) state.pinnedNodeIds.delete(nodeId);
    else state.pinnedNodeIds.add(nodeId);
    const node = cy.getElementById(nodeId);
    if (node.nonempty()) showDetails(node);
    else {
      applyNodeDecorations();
      renderContextSummary();
    }
    pushGraphHistory();
  }

  function clearExceptPinned() {
    if (!state.pinnedNodeIds.size) {
      showDialog(state.t.no_pinned_nodes);
      return;
    }
    cy.nodes().forEach(node => {
      if (!state.pinnedNodeIds.has(node.id())) node.remove();
    });
    applyNodeDecorations();
    renderContextSummary();
    pushGraphHistory();
  }

  async function focusCurrentNeighborhood() {
    if (!state.currentSelectedNodeId) {
      showDialog(state.t.no_selected_node);
      return;
    }
    const data = await expand(state.currentSelectedNodeId, { replace: true, depth: 2, limitNodes: 120, limitEdges: 240 });
    if (!data) showDialog(state.t.focus_failed);
  }

  function computeTypeCounts() {
    const byTypeByDb = state.stats?.byTypeByDb || {};
    const dbs = state.selectedDb ? [state.selectedDb] : state.allDbs;
    const combined = {};
    for (const db of dbs) {
      const map = byTypeByDb[db] || {};
      for (const [type, count] of Object.entries(map)) combined[type] = (combined[type] || 0) + count;
    }
    return Object.entries(combined).sort((a, b) => b[1] - a[1]);
  }

  function renderTypes() {
    const t = state.t;
    const sorted = computeTypeCounts();
    const ul = document.getElementById('types');
    ul.innerHTML = sorted.length
      ? sorted.map(([type, count]) => `<li data-type="${escapeAttr(type)}"><span><span style="color:${TYPE_COLORS[type] || '#8b95a4'}">●</span> ${escapeHtml(displayNodeType(type))}</span> <span class="n">${count}</span></li>`).join('')
      : `<li class="empty">${t.no_types}</li>`;
    ul.querySelectorAll('li[data-type]').forEach(li => {
      li.addEventListener('click', () => searchByType(li.dataset.type));
    });
  }

  function renderDbs() {
    const t = state.t;
    const byTypeByDb = state.stats?.byTypeByDb || {};
    const container = document.getElementById('dbs');
    if (!state.allDbs.length) {
      container.innerHTML = `<div class="empty">${t.no_dbs}</div>`;
      return;
    }
    const singleDb = state.allDbs.length === 1;
    const rows = state.allDbs.map(db => {
      const color = state.dbColor[db] || '#8b95a4';
      const nodeCount = Object.values(byTypeByDb[db] || {}).reduce((a, b) => a + b, 0);
      return `<label><input type="radio" name="bsl-graph-db" ${db === state.selectedDb ? 'checked' : ''} ${singleDb ? 'disabled' : ''} data-db="${escapeAttr(db)}"> <span class="db-chip" style="background:${color};border-color:${color}"></span> <span class="db-name">${escapeHtml(db)}</span> <span class="db-n">${nodeCount}</span></label>`;
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
      const color = state.dbColor[db] || '#8b95a4';
      items.push(`<div class="row"><div class="sw-ring" style="border-color:${color}"></div>${escapeHtml(db)}</div>`);
    }
    items.push(`<div class="row" style="margin-top:6px;color:#8b95a4">${escapeHtml(t.legend_fill)}</div>`);
    items.push(`<div class="row" style="color:#8b95a4">${escapeHtml(t.legend_border)}</div>`);
    document.getElementById('legend').innerHTML = items.join('');
  }

  function renderFilters() {
    const edgeBox = document.getElementById('edge-filters');
    const nodeBox = document.getElementById('node-filters');
    const edgeTypes = edgeTypeListForCurrentDb();
    const nodeTypes = nodeTypeListForCurrentDb();

    edgeBox.innerHTML = edgeTypes.map(([type, count]) => `
      <label><input type="checkbox" value="${escapeAttr(type)}" ${state.filters.edgeTypes.has(type) ? 'checked' : ''}> <span>${escapeHtml(displayEdgeType(type))} (${count})</span></label>
    `).join('') || `<div class="empty">${escapeHtml(state.t.no_types)}</div>`;
    nodeBox.innerHTML = nodeTypes.map(([type, count]) => `
      <label><input type="checkbox" value="${escapeAttr(type)}" ${state.filters.nodeTypes.has(type) ? 'checked' : ''}> <span>${escapeHtml(displayNodeType(type))} (${count})</span></label>
    `).join('') || `<div class="empty">${escapeHtml(state.t.no_types)}</div>`;

    edgeBox.querySelectorAll('input[type=checkbox]').forEach(cb => {
      cb.addEventListener('change', () => {
        if (cb.checked) state.filters.edgeTypes.add(cb.value);
        else state.filters.edgeTypes.delete(cb.value);
        renderContextSummary();
      });
    });
    nodeBox.querySelectorAll('input[type=checkbox]').forEach(cb => {
      cb.addEventListener('change', () => {
        if (cb.checked) state.filters.nodeTypes.add(cb.value);
        else state.filters.nodeTypes.delete(cb.value);
        renderContextSummary();
      });
    });
  }

  function renderStats() {
    const t = state.t;
    const stats = state.stats || {};
    let nodes;
    let edges;
    if (!state.selectedDb) {
      nodes = stats.totalNodes || 0;
      edges = stats.totalEdges || 0;
    } else {
      const byTypeByDb = stats.byTypeByDb || {};
      const edgesByDb = stats.edgesByDb || {};
      nodes = Object.values(byTypeByDb[state.selectedDb] || {}).reduce((a, b) => a + b, 0);
      edges = edgesByDb[state.selectedDb] || 0;
    }
    const currentDb = document.getElementById('current-db');
    currentDb.textContent = state.selectedDb || '—';
    document.getElementById('stats').innerHTML = `<strong>${nodes}</strong> ${t.nodes_word} · <strong>${edges}</strong> ${t.edges_word}`;
  }

  function onDbSelect(e) {
    const db = e.target.dataset.db;
    if (!db || db === state.selectedDb) return;
    state.selectedDb = db;
    resetGraph();
    state.lastResults = [];
    state.currentPathData = null;
    renderDbs();
    renderTypes();
    renderStats();
    renderFilters();
    renderLegend();
    syncCanvasVisibility();
    updatePathSummary();
    renderPathSteps();
    pushGraphHistory();
  }

  function applyI18n() {
    const t = state.t;
    document.getElementById('q').placeholder = t.search_placeholder;
    document.getElementById('btn-clear').textContent = t.btn_clear;
    const btnDocs = document.getElementById('btn-docs');
    btnDocs.textContent = t.btn_docs;
    btnDocs.href = `/docs?lang=${state.lang}`;
    const btnList = document.getElementById('btn-list');
    btnList.textContent = t.btn_list;
    btnList.title = t.btn_list_title;
    const btnRebuild = document.getElementById('btn-rebuild');
    btnRebuild.textContent = t.btn_rebuild;
    btnRebuild.title = t.btn_rebuild_title;
    document.getElementById('btn-back').title = t.btn_back_title;
    document.getElementById('btn-fwd').title = t.btn_fwd_title;
    document.getElementById('mode-select').value = state.mode;
    document.querySelectorAll('#lang-sw [data-lang]').forEach(link => {
      link.classList.toggle('on', link.dataset.lang === state.lang);
    });
    document.getElementById('h-dbs').textContent = t.h_dbs;
    document.getElementById('h-types').textContent = t.h_types;
    document.getElementById('h-context').textContent = t.h_context;
    document.getElementById('h-node').textContent = t.h_node;
    document.getElementById('h-analysis').textContent = t.h_analysis;
    document.getElementById('h-path').textContent = t.h_path;
    document.getElementById('h-legend').textContent = t.h_legend;
    document.getElementById('dbs-loading').textContent = t.loading;
    document.getElementById('types-loading').textContent = t.loading;
    document.getElementById('details-empty').textContent = t.empty_details;
    document.getElementById('lbl-direction').textContent = t.lbl_direction;
    const dirSelect = document.getElementById('direction-select');
    dirSelect.querySelector('option[value=both]').textContent = t.direction_both;
    dirSelect.querySelector('option[value=out]').textContent = t.direction_out;
    dirSelect.querySelector('option[value=in]').textContent = t.direction_in;
    document.getElementById('lbl-hide-bsl').textContent = t.lbl_hide_bsl;
    document.getElementById('h-edge-filters').textContent = t.h_edge_filters;
    document.getElementById('h-node-filters').textContent = t.h_node_filters;
    document.getElementById('btn-focus-current').textContent = t.focus_btn;
    document.getElementById('btn-clear-unpinned').textContent = t.clear_unpinned_btn;
    document.getElementById('lbl-source').textContent = t.lbl_source;
    document.getElementById('lbl-target').textContent = t.lbl_target;
    document.getElementById('lbl-max-depth').textContent = t.lbl_max_depth;
    document.getElementById('btn-build-path').textContent = t.btn_build_path;
    document.getElementById('btn-clear-path').textContent = t.btn_clear_path;
    renderPathSteps();
  }

  async function loadStats() {
    const stats = await apiGet('/api/graph/stats');
    state.stats = stats;
    state.allDbs = (stats.indexedDatabases || []).slice().sort();
    state.dbColor = {};
    state.allDbs.forEach((db, index) => {
      state.dbColor[db] = DB_PALETTE[index % DB_PALETTE.length];
    });
    if (!state.selectedDb || !state.allDbs.includes(state.selectedDb)) {
      state.selectedDb = state.boot.db && state.allDbs.includes(state.boot.db) ? state.boot.db : (state.allDbs[0] || '');
    }
    renderStats();
    renderDbs();
    renderTypes();
    renderFilters();
    renderLegend();
    renderContextSummary();
    cy.style().update();
  }

  async function bootstrapFromUrl() {
    if (state.boot.q && !state.boot.appliedQuery) {
      document.getElementById('q').value = state.boot.q;
      await searchByQuery(state.boot.q);
      state.boot.appliedQuery = true;
    }
    if (state.boot.nodeId && !state.boot.appliedNode) {
      await expand(state.boot.nodeId, { replace: true, depth: 1 });
      state.boot.appliedNode = true;
    }
  }

  function applyMode() {
    const pathPanel = document.getElementById('path-panel');
    const analysisPanel = document.getElementById('analysis-panel');
    const isPath = state.mode === 'path';
    pathPanel.style.opacity = isPath ? '1' : '0.88';
    analysisPanel.style.opacity = '1';
    renderContextSummary();
  }

  cy.on('tap', 'node', evt => {
    const node = evt.target;
    if (state.mode === 'path' && !state.selectedSourceId) setPathEndpoint('source', node.id());
    else if (state.mode === 'path' && !state.selectedTargetId && state.selectedSourceId !== node.id()) setPathEndpoint('target', node.id());
    showDetails(node);
    pushGraphHistory();
  });
  cy.on('dbltap', 'node', evt => expand(evt.target.id()));
  cy.on('tap', evt => {
    if (evt.target === cy) {
      showDetails(null);
      pushGraphHistory();
    }
  });

  document.querySelectorAll('#lang-sw [data-lang]').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const newLang = link.dataset.lang;
      localStorage.setItem('bslgraph.lang', newLang);
      const url = new URL(window.location.href);
      url.searchParams.set('lang', newLang);
      window.location.href = url.toString();
    });
  });
  document.getElementById('mode-select').addEventListener('change', e => {
    state.mode = e.target.value === 'path' ? 'path' : 'overview';
    applyMode();
    pushGraphHistory();
  });
  document.getElementById('direction-select').addEventListener('change', e => {
    state.filters.direction = e.target.value;
    renderContextSummary();
    pushGraphHistory();
  });
  document.getElementById('hide-bsl-files').addEventListener('change', e => {
    state.filters.hideBslFiles = e.target.checked;
    renderContextSummary();
    pushGraphHistory();
  });
  document.getElementById('path-depth').value = String(DEFAULT_PATH_DEPTH);
  document.getElementById('path-depth-dec').addEventListener('click', () => adjustPathDepth(-1));
  document.getElementById('path-depth-inc').addEventListener('click', () => adjustPathDepth(1));
  document.getElementById('btn-build-path').addEventListener('click', buildPath);
  document.getElementById('btn-clear-path').addEventListener('click', clearPath);
  document.getElementById('btn-focus-current').addEventListener('click', focusCurrentNeighborhood);
  document.getElementById('btn-clear-unpinned').addEventListener('click', clearExceptPinned);
  document.getElementById('dialog-ok').addEventListener('click', hideDialog);
  document.getElementById('dialog-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) hideDialog();
  });
  document.getElementById('q').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchByQuery(e.target.value);
  });
  document.getElementById('btn-clear').addEventListener('click', () => {
    document.getElementById('q').value = '';
    resetGraph();
    state.lastResults = [];
    renderResultsPanel();
    showDetails(null);
    updatePathSummary();
    renderPathSteps();
    pushGraphHistory();
  });
  document.getElementById('btn-list').addEventListener('click', () => toggleResultsPanel());
  document.getElementById('rp-close').addEventListener('click', () => toggleResultsPanel(false));
  document.getElementById('btn-back').addEventListener('click', () => navigateHistory(-1));
  document.getElementById('btn-fwd').addEventListener('click', () => navigateHistory(1));
  document.getElementById('btn-rebuild').addEventListener('click', async () => {
    const btn = document.getElementById('btn-rebuild');
    const prev = btn.textContent;
    btn.textContent = '…';
    btn.disabled = true;
    try {
      await apiPost('/api/graph/rebuild', {});
      await loadStats();
    } catch (e) {
      showDialog(`${state.t.rebuild_failed}: ${e.message}`);
    } finally {
      btn.textContent = prev;
      btn.disabled = false;
    }
  });

  (async function init() {
    applyI18n();
    await loadStats();
    applyMode();
    updatePathSummary();
    renderPathSteps();
    await bootstrapFromUrl();
    pushGraphHistory();
  })();
})();
