(function () {
  'use strict';

  var CATEGORIES = window.CATEGORIES || [];
  var CAT_LABEL = {};
  var CAT_ORDER = {};
  CATEGORIES.forEach(function (c, i) {
    CAT_LABEL[c.id] = c.label;
    CAT_ORDER[c.id] = i;
  });

  var KEY = {
    favs: 'opscmd.favs',
    custom: 'opscmd.custom',
    history: 'opscmd.history',
    theme: 'opscmd.theme'
  };

  // {{名称}} 会被渲染成输入框；{{.Names}} 这类格式串不会误伤
  var PH_RE = /\{\{([a-zA-Z\u4e00-\u9fa5][a-zA-Z0-9\u4e00-\u9fa5_-]*)\}\}/g;
  var DANGER_RE = /(^|\s)rm\s+-[a-z]*[rf]|mkfs|dd\s+if=|>\s*\/dev\/|drop\s+(table|database)|flushall|--delete\b|prune\b|truncate\s+-s\s+0/i;

  var $ = function (sel) { return document.querySelector(sel); };
  var listEl = $('#list');
  var searchEl = $('#search');
  var chipsEl = $('#chips');
  var countEl = $('#count');
  var totalCountEl = $('#total-count');
  var toastEl = $('#toast');
  var dialog = $('#dialog');
  var fileInput = $('#file-import');

  var state = { q: '', cat: 'all', activeIndex: -1, rendered: [] };
  var phValues = new Map();
  var items = [];
  var favs = new Set();
  var searchTimer = 0;
  var toastTimer = 0;

  /* ---------------- 存储 ---------------- */

  function load(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function save(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) { /* 无痕模式 / file:// 受限时忽略 */ }
  }

  function hash(str) {
    var h = 5381;
    for (var i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0;
    return (h >>> 0).toString(36);
  }

  var ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(value) {
    return String(value).replace(/[&<>"']/g, function (ch) { return ESC[ch]; });
  }

  function isDanger(item) {
    return !!(item && (item.danger || DANGER_RE.test(item.cmd || '')));
  }

  /* ---------------- 数据 ---------------- */

  function rebuild() {
    var customs = load(KEY.custom, []);
    if (!Array.isArray(customs)) customs = [];
    customs = customs.filter(function (c) { return c && c.cmd && c.desc; });

    items = (window.COMMANDS || []).map(function (c) {
      return Object.assign({}, c, { id: 'b' + hash(c.cmd), source: 'builtin' });
    }).concat(customs.map(function (c) {
      return Object.assign({}, c, {
        id: c.id || ('u' + hash(c.cmd + c.desc)),
        source: 'custom'
      });
    }));

    var seen = new Set();
    items.forEach(function (it) {
      var id = it.id;
      var n = 1;
      while (seen.has(id)) id = it.id + '_' + n++;
      it.id = id;
      seen.add(id);
    });

    favs = new Set(load(KEY.favs, []));
    totalCountEl.textContent = String(items.length);
  }

  /* ---------------- 搜索打分 ---------------- */

  function isSubseq(needle, hay) {
    var i = 0;
    for (var j = 0; j < hay.length && i < needle.length; j++) {
      if (hay[j] === needle[i]) i++;
    }
    return i === needle.length;
  }

  function scoreOf(item, tokens) {
    var cmd = item.cmd.toLowerCase();
    var desc = item.desc.toLowerCase();
    var tagText = (item.tags || []).join(' ').toLowerCase();
    var catText = (CAT_LABEL[item.cat] || '').toLowerCase();
    var total = 0;

    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      var s = 0;
      if (cmd.indexOf(t) !== -1) s = 14 + (cmd.indexOf(t) === 0 ? 4 : 0);
      else if (desc.indexOf(t) !== -1) s = 9;
      else if (tagText.indexOf(t) !== -1 || catText.indexOf(t) !== -1) s = 6;
      else if (t.length >= 2 && isSubseq(t, cmd)) s = 4;
      else if (t.length >= 2 && isSubseq(t, desc)) s = 2;
      if (!s) return 0;
      total += s;
    }

    var phrase = tokens.join(' ');
    if (cmd.indexOf(phrase) !== -1) total += 10;
    if (desc.indexOf(phrase) !== -1) total += 6;
    if (item.hot) total += 1.5;
    if (favs.has(item.id)) total += 0.5;
    return total;
  }

  function matchesCat(item) {
    if (state.cat === 'all') return true;
    if (state.cat === 'fav') return favs.has(item.id);
    if (state.cat === 'hot') return !!item.hot;
    if (state.cat === 'custom') return item.source === 'custom';
    return item.cat === state.cat;
  }

  /* ---------------- 渲染 ---------------- */

  function renderChips() {
    var hasCustom = items.some(function (i) { return i.source === 'custom'; });
    var chips = [
      { id: 'all', label: '全部' },
      { id: 'fav', label: '★ 收藏' },
      { id: 'hot', label: '常用' }
    ];
    if (hasCustom) chips.push({ id: 'custom', label: '我加的' });
    CATEGORIES.forEach(function (c) { chips.push({ id: c.id, label: c.label }); });

    chipsEl.innerHTML = chips.map(function (c) {
      var active = state.cat === c.id;
      return '<button type="button" class="chip' + (active ? ' active' : '') +
        '" data-cat="' + c.id + '" role="tab" aria-selected="' + active + '">' +
        esc(c.label) + '</button>';
    }).join('');
  }

  function renderCmd(item) {
    var out = '';
    var last = 0;
    var idx = 0;
    var m;
    PH_RE.lastIndex = 0;
    while ((m = PH_RE.exec(item.cmd)) !== null) {
      out += esc(item.cmd.slice(last, m.index));
      var name = m[1];
      var key = item.id + '|' + idx;
      var val = phValues.get(key) || '';
      var width = Math.max(5, name.length * 2 + 1);
      out += '<input class="ph" type="text" spellcheck="false" autocomplete="off"' +
        ' data-token="' + esc(m[0]) + '" data-key="' + esc(key) + '"' +
        ' placeholder="' + esc(name) + '" value="' + esc(val) + '"' +
        ' style="width:' + width + 'ch" aria-label="参数：' + esc(name) + '">';
      last = m.index + m[0].length;
      idx++;
    }
    out += esc(item.cmd.slice(last));
    return out;
  }

  function renderCard(item) {
    var label = CAT_LABEL[item.cat] || '其他';
    var danger = isDanger(item);
    var isFav = favs.has(item.id);
    var tags = (item.tags || []).map(function (t) {
      return '<span class="tag">#' + esc(t) + '</span>';
    }).join('');

    return '<article class="card" data-id="' + esc(item.id) + '">' +
      '<div class="card-head">' +
        '<span class="cat-tag">' + esc(label) + '</span>' +
        (danger ? '<span class="danger-tag">高危</span>' : '') +
        (item.source === 'custom' ? '<span class="mine-tag">我加的</span>' : '') +
        '<h2 class="desc">' + esc(item.desc) + '</h2>' +
        '<button type="button" class="star-btn' + (isFav ? ' on' : '') + '"' +
          ' aria-pressed="' + isFav + '" title="' + (isFav ? '取消收藏' : '收藏') + '">★</button>' +
      '</div>' +
      '<div class="cmd-row">' +
        '<code class="cmd">' + renderCmd(item) + '</code>' +
        '<button type="button" class="copy-btn">复制</button>' +
      '</div>' +
      (item.note ? '<p class="note">' + esc(item.note) + '</p>' : '') +
      '<div class="card-foot">' +
        '<div class="tags">' + tags + '</div>' +
        (item.source === 'custom'
          ? '<div class="card-actions">' +
              '<button type="button" class="mini-btn" data-action="edit" data-id="' + esc(item.id) + '">编辑</button>' +
              '<button type="button" class="mini-btn" data-action="delete" data-id="' + esc(item.id) + '">删除</button>' +
            '</div>'
          : '') +
      '</div>' +
    '</article>';
  }

  function render() {
    var tokens = state.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    var scored = [];

    items.forEach(function (item) {
      if (!matchesCat(item)) return;
      var s = scoreOf(item, tokens);
      if (s > 0) scored.push({ item: item, s: s });
    });

    scored.sort(function (a, b) {
      if (b.s !== a.s) return b.s - a.s;
      var hotDiff = (b.item.hot ? 1 : 0) - (a.item.hot ? 1 : 0);
      if (hotDiff) return hotDiff;
      return (CAT_ORDER[a.item.cat] || 0) - (CAT_ORDER[b.item.cat] || 0);
    });

    state.rendered = scored.map(function (x) { return x.item; });

    if (!state.rendered.length) {
      state.activeIndex = -1;
      listEl.innerHTML = '<div class="empty">' +
        '<div class="empty-mark">$</div>' +
        '<h3>没有找到相关命令</h3>' +
        '<p>换个说法试试，比如「查端口」「磁盘满」「容器日志」；也可以点右上角「+ 添加」自己记一条。</p>' +
        '</div>';
    } else {
      if (state.activeIndex >= state.rendered.length) state.activeIndex = -1;
      listEl.innerHTML = state.rendered.map(renderCard).join('');
      if (state.activeIndex >= 0) setActive(state.activeIndex, false);
    }

    var shown = state.rendered.length;
    countEl.textContent = state.q.trim()
      ? '找到 ' + shown + ' 条命令'
      : (state.cat === 'all' ? '共 ' + shown + ' 条命令' : '该分类 ' + shown + ' 条命令');

    renderChips();
  }

  function setActive(index, scroll) {
    var cards = listEl.querySelectorAll('.card');
    if (!cards.length) return;
    state.activeIndex = index;
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.toggle('active', i === index);
    }
    if (scroll && cards[index]) cards[index].scrollIntoView({ block: 'nearest' });
  }

  function moveActive(delta) {
    var n = state.rendered.length;
    if (!n) return;
    var idx;
    if (state.activeIndex < 0) idx = delta > 0 ? 0 : n - 1;
    else idx = state.activeIndex + delta;
    idx = Math.max(0, Math.min(n - 1, idx));
    setActive(idx, true);
  }

  /* ---------------- 复制 ---------------- */

  function composeCommand(card, item) {
    var values = Array.prototype.map.call(card.querySelectorAll('input.ph'), function (inp) {
      return inp.value.trim();
    });
    var out = '';
    var last = 0;
    var idx = 0;
    var missing = 0;
    var m;
    PH_RE.lastIndex = 0;
    while ((m = PH_RE.exec(item.cmd)) !== null) {
      out += item.cmd.slice(last, m.index);
      var v = values[idx++];
      if (v) out += v;
      else { out += m[0]; missing++; }
      last = m.index + m[0].length;
    }
    out += item.cmd.slice(last);
    return { text: out, missing: missing };
  }

  function writeClipboard(text) {
    // 桌面版走 Python 的 Windows 剪贴板 API，不触发浏览器权限询问
    if (window.pywebview && window.pywebview.api && window.pywebview.api.copy_text) {
      return window.pywebview.api.copy_text(text).then(function (ok) {
        return ok !== false;
      }, function () {
        return fallbackCopy(text);
      });
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () {
        return fallbackCopy(text);
      });
    }
    return Promise.resolve(fallbackCopy(text));
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-1000px';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }

  function arm(btn) {
    if (!btn.dataset.label) btn.dataset.label = btn.textContent;
    btn.dataset.armed = '1';
    btn.classList.add('armed');
    btn.textContent = '确认复制';
    clearTimeout(btn._armTimer);
    btn._armTimer = setTimeout(function () { disarm(btn); }, 3200);
  }

  function disarm(btn) {
    clearTimeout(btn._armTimer);
    if (btn.dataset.armed === '1') {
      btn.classList.remove('armed');
      btn.textContent = btn.dataset.label || '复制';
      delete btn.dataset.armed;
      delete btn.dataset.label;
    }
  }

  function doCopy(btn, text, danger, missing) {
    if (danger && btn.dataset.armed !== '1') {
      arm(btn);
      return;
    }
    disarm(btn);
    writeClipboard(text).then(function (ok) {
      if (!ok) {
        toast('复制失败，请手动选中命令复制');
        return;
      }
      pushHistory(text);
      toast('已复制' + (missing ? '（还有 ' + missing + ' 个参数没填）' : ''));
    });
  }

  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 2400);
  }

  function pushHistory(cmd) {
    var hist = load(KEY.history, []);
    if (!Array.isArray(hist)) hist = [];
    hist = [{ cmd: cmd, at: Date.now() }].concat(hist.filter(function (h) {
      return h && h.cmd !== cmd;
    })).slice(0, 30);
    save(KEY.history, hist);
  }

  function timeAgo(ts) {
    var s = Math.max(1, Math.floor((Date.now() - ts) / 1000));
    if (s < 60) return '刚刚';
    if (s < 3600) return Math.floor(s / 60) + ' 分钟前';
    if (s < 86400) return Math.floor(s / 3600) + ' 小时前';
    return new Date(ts).toLocaleDateString('zh-CN');
  }

  /* ---------------- 弹窗 ---------------- */

  function openDialog(html, editId) {
    dialog.innerHTML = html;
    dialog.dataset.editId = editId || '';
    if (!dialog.open) dialog.showModal();
  }

  function openForm(item) {
    var isEdit = !!item;
    var cur = item || {};

    openDialog(
      '<div class="modal-head">' +
        '<h3>' + (isEdit ? '编辑命令' : '添加命令') + '</h3>' +
        '<button type="button" class="close-btn" data-close aria-label="关闭">×</button>' +
      '</div>' +
      '<form class="modal-body" id="cmd-form" novalidate>' +
        '<div class="form-row">' +
          '<label for="f-desc">用途描述（必填）</label>' +
          '<input id="f-desc" name="desc" class="input" value="' + esc(cur.desc || '') + '" placeholder="例如：查看 Nginx 最近 5xx 请求">' +
        '</div>' +
        '<div class="form-row">' +
          '<label for="f-cmd">命令（必填，参数用 {{名称}} 占位）</label>' +
          '<textarea id="f-cmd" name="cmd" spellcheck="false" placeholder="例如：tail -f /var/log/nginx/access.log | grep {{关键字}}">' + esc(cur.cmd || '') + '</textarea>' +
          '<p class="hint">占位符会渲染成输入框，复制时自动替换成你填的值，比如 {{容器}}、{{端口}}。</p>' +
        '</div>' +
        '<div class="form-grid">' +
          '<div class="form-row">' +
            '<label for="f-cat">分类</label>' +
            '<select id="f-cat" name="cat" class="input">' +
              CATEGORIES.map(function (c) {
                return '<option value="' + c.id + '"' + (cur.cat === c.id ? ' selected' : '') + '>' + esc(c.label) + '</option>';
              }).join('') +
            '</select>' +
          '</div>' +
          '<div class="form-row">' +
            '<label for="f-tags">标签（逗号分隔）</label>' +
            '<input id="f-tags" name="tags" class="input" value="' + esc((cur.tags || []).join(',')) + '" placeholder="docker,日志">' +
          '</div>' +
        '</div>' +
        '<div class="form-row">' +
          '<label for="f-note">备注（可选）</label>' +
          '<input id="f-note" name="note" class="input" value="' + esc(cur.note || '') + '" placeholder="踩坑提醒、参数说明">' +
        '</div>' +
        '<label class="check-row"><input type="checkbox" name="danger"' + (cur.danger ? ' checked' : '') + '> <span>标记为高危命令（复制时需要点两次确认）</span></label>' +
        '<div class="modal-actions">' +
          '<button type="button" class="btn" data-close>取消</button>' +
          '<button type="submit" class="btn primary">' + (isEdit ? '保存修改' : '添加') + '</button>' +
        '</div>' +
      '</form>',
      isEdit ? item.id : ''
    );

    var form = dialog.querySelector('#cmd-form');
    form.addEventListener('submit', onFormSubmit);
    setTimeout(function () { dialog.querySelector('#f-desc').focus(); }, 40);
  }

  function onFormSubmit(e) {
    e.preventDefault();
    var form = e.currentTarget;
    var desc = form.desc.value.trim();
    var cmd = form.cmd.value.trim();
    if (!desc || !cmd) {
      toast('描述和命令都要填');
      return;
    }

    var tags = form.tags.value.split(/[,，\s]+/).map(function (t) { return t.trim(); }).filter(Boolean);
    var data = {
      desc: desc,
      cmd: cmd,
      cat: form.cat.value,
      tags: tags,
      note: form.note.value.trim(),
      danger: form.danger.checked,
      hot: false
    };

    var customs = load(KEY.custom, []);
    if (!Array.isArray(customs)) customs = [];
    var editId = dialog.dataset.editId;

    if (editId) {
      var idx = -1;
      for (var i = 0; i < customs.length; i++) {
        if (customs[i].id === editId) { idx = i; break; }
      }
      if (idx >= 0) customs[idx] = Object.assign({}, customs[idx], data);
      else customs.push(Object.assign({ id: editId }, data));
      toast('已保存修改');
    } else {
      data.id = 'u' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
      customs.push(data);
      toast('已添加，可以搜索试试');
    }

    save(KEY.custom, customs);
    dialog.close();
    rebuild();
    render();
  }

  function openHistory() {
    var hist = load(KEY.history, []);
    if (!Array.isArray(hist)) hist = [];

    var body = hist.length
      ? hist.map(function (h) {
          var danger = DANGER_RE.test(h.cmd);
          return '<div class="hist-row">' +
            '<div class="hist-main">' +
              '<div class="hist-cmd">' + esc(h.cmd) + '</div>' +
              '<div class="hist-time">' + timeAgo(h.at) + '</div>' +
            '</div>' +
            '<button type="button" class="copy-btn hist-copy" data-cmd="' + esc(h.cmd) + '"' +
              ' data-danger="' + (danger ? '1' : '') + '">复制</button>' +
          '</div>';
        }).join('')
      : '<p class="muted">还没有复制记录。复制过的命令会出现在这里，方便再次使用。</p>';

    openDialog(
      '<div class="modal-head">' +
        '<h3>最近复制</h3>' +
        '<button type="button" class="close-btn" data-close aria-label="关闭">×</button>' +
      '</div>' +
      '<div class="modal-body">' +
        body +
        '<div class="modal-actions">' +
          '<button type="button" class="btn" data-clear-history>清空记录</button>' +
          '<button type="button" class="btn primary" data-close>关闭</button>' +
        '</div>' +
      '</div>'
    );
  }

  /* ---------------- 导入导出 ---------------- */

  function exportData() {
    var data = {
      app: 'opscmd',
      version: 1,
      exportedAt: new Date().toISOString(),
      custom: load(KEY.custom, []),
      favs: Array.from(favs),
      history: load(KEY.history, [])
    };
    var text = JSON.stringify(data, null, 2);

    // 桌面版：用系统「另存为」对话框
    if (window.pywebview && window.pywebview.api && window.pywebview.api.export_backup) {
      window.pywebview.api.export_backup(text).then(function (path) {
        if (typeof path === 'string' && path) toast('已导出到 ' + path);
        else toast('已取消导出');
      }, function () {
        toast('导出失败，请换个位置再试');
      });
      return;
    }

    var blob = new Blob([text], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'opscmd-backup-' + new Date().toISOString().slice(0, 10) + '.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    toast('已导出备份文件');
  }

  function importData(file) {
    var reader = new FileReader();
    reader.onload = function () { importText(String(reader.result)); };
    reader.readAsText(file);
  }

  function importText(text) {
    try {
      var data = JSON.parse(text);
      if (!data || typeof data !== 'object') throw new Error('bad file');

      var incoming = Array.isArray(data.custom) ? data.custom : [];
      var customs = load(KEY.custom, []);
      if (!Array.isArray(customs)) customs = [];
      var seen = new Set(customs.map(function (c) { return c.cmd; }));
      var added = 0;

      incoming.forEach(function (c) {
        if (!c || !c.cmd || !c.desc || seen.has(c.cmd)) return;
        customs.push({
          id: c.id || ('u' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)),
          cmd: c.cmd,
          desc: c.desc,
          cat: CAT_LABEL[c.cat] ? c.cat : 'misc',
          tags: Array.isArray(c.tags) ? c.tags : [],
          note: c.note || '',
          danger: !!c.danger
        });
        seen.add(c.cmd);
        added++;
      });

      save(KEY.custom, customs);

      if (Array.isArray(data.favs)) {
        var merged = new Set(favs);
        data.favs.forEach(function (f) { if (typeof f === 'string') merged.add(f); });
        save(KEY.favs, Array.from(merged));
      }

      rebuild();
      render();
      toast(added ? '导入完成，新增 ' + added + ' 条命令' : '没有新增命令（可能已经存在）');
    } catch (err) {
      toast('导入失败：文件格式不正确');
    }
  }

  /* ---------------- 事件 ---------------- */

  searchEl.addEventListener('input', function () {
    state.q = searchEl.value;
    state.activeIndex = state.q.trim() ? 0 : -1;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () { searchTimer = 0; render(); }, 70);
  });

  searchEl.addEventListener('search', function () {
    state.q = searchEl.value;
    state.activeIndex = state.q.trim() ? 0 : -1;
    render();
  });

  chipsEl.addEventListener('click', function (e) {
    var chip = e.target.closest('.chip');
    if (!chip) return;
    state.cat = chip.dataset.cat;
    state.activeIndex = state.q.trim() ? 0 : -1;
    render();
  });

  listEl.addEventListener('input', function (e) {
    var inp = e.target.closest('input.ph');
    if (!inp) return;
    phValues.set(inp.dataset.key, inp.value);
  });

  listEl.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || !e.target.closest('input.ph')) return;
    e.preventDefault();
    var card = e.target.closest('.card');
    var btn = card && card.querySelector('.copy-btn');
    if (btn) btn.click();
  });

  listEl.addEventListener('click', function (e) {
    var star = e.target.closest('.star-btn');
    if (star) {
      var card = star.closest('.card');
      var id = card.dataset.id;
      if (favs.has(id)) {
        favs.delete(id);
        toast('已取消收藏');
      } else {
        favs.add(id);
        toast('已收藏');
      }
      save(KEY.favs, Array.from(favs));
      var on = favs.has(id);
      star.classList.toggle('on', on);
      star.setAttribute('aria-pressed', String(on));
      star.title = on ? '取消收藏' : '收藏';
      if (state.cat === 'fav') render();
      return;
    }

    var copyBtn = e.target.closest('.copy-btn');
    if (copyBtn) {
      var cardEl = copyBtn.closest('.card');
      var item = null;
      for (var i = 0; i < items.length; i++) {
        if (items[i].id === cardEl.dataset.id) { item = items[i]; break; }
      }
      if (!item) return;
      var composed = composeCommand(cardEl, item);
      doCopy(copyBtn, composed.text, isDanger(item), composed.missing);
      return;
    }

    var actionBtn = e.target.closest('[data-action]');
    if (actionBtn) {
      var act = actionBtn.dataset.action;
      var itemId = actionBtn.dataset.id;
      var target = null;
      for (var j = 0; j < items.length; j++) {
        if (items[j].id === itemId) { target = items[j]; break; }
      }
      if (!target) return;

      if (act === 'edit') {
        openForm(target);
      } else if (act === 'delete') {
        if (actionBtn.dataset.armed !== '1') {
          actionBtn.dataset.armed = '1';
          actionBtn.textContent = '确认删除';
          setTimeout(function () {
            actionBtn.textContent = '删除';
            delete actionBtn.dataset.armed;
          }, 3000);
        } else {
          deleteCustom(target.id);
        }
      }
      return;
    }

    var bodyCard = e.target.closest('.card');
    if (bodyCard && !e.target.closest('button, input, textarea, select, a')) {
      var idx = state.rendered.findIndex(function (it) { return it.id === bodyCard.dataset.id; });
      if (idx >= 0) setActive(idx, false);
    }
  });

  function deleteCustom(id) {
    var customs = load(KEY.custom, []);
    if (!Array.isArray(customs)) customs = [];
    customs = customs.filter(function (c) {
      return (c.id || ('u' + hash(c.cmd + c.desc))) !== id;
    });
    save(KEY.custom, customs);
    rebuild();
    render();
    toast('已删除自定义命令');
  }

  dialog.addEventListener('click', function (e) {
    if (e.target === dialog) { dialog.close(); return; }

    if (e.target.closest('[data-close]')) { dialog.close(); return; }

    if (e.target.closest('[data-clear-history]')) {
      save(KEY.history, []);
      openHistory();
      return;
    }

    var hc = e.target.closest('.hist-copy');
    if (hc) {
      var text = hc.dataset.cmd;
      var danger = hc.dataset.danger === '1';
      if (danger && hc.dataset.armed !== '1') { arm(hc); return; }
      disarm(hc);
      writeClipboard(text).then(function (ok) {
        if (!ok) { toast('复制失败，请手动复制'); return; }
        pushHistory(text);
        toast('已复制');
      });
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.isComposing) return;
    var el = e.target;
    var isField = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT');

    if (e.key === '/' && !isField && !e.metaKey && !e.ctrlKey && !dialog.open) {
      e.preventDefault();
      searchEl.focus();
      searchEl.select();
      return;
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      searchEl.focus();
      searchEl.select();
      return;
    }

    if (e.key === 'Escape' && !dialog.open) {
      if (document.activeElement === searchEl) {
        if (searchEl.value) {
          searchEl.value = '';
          state.q = '';
          state.activeIndex = -1;
          render();
        } else {
          searchEl.blur();
        }
      } else if (state.activeIndex >= 0) {
        setActive(-1, false);
      }
      return;
    }

    if (document.activeElement !== searchEl || dialog.open) return;

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      moveActive(e.key === 'ArrowDown' ? 1 : -1);
      return;
    }

    if (e.key === 'Enter') {
      e.preventDefault();
      if (searchTimer) { clearTimeout(searchTimer); searchTimer = 0; render(); }
      var idx = state.activeIndex >= 0 ? state.activeIndex : 0;
      var cards = listEl.querySelectorAll('.card');
      var card = cards[idx];
      if (card) {
        var btn = card.querySelector('.copy-btn');
        if (btn) btn.click();
      }
    }
  });

  $('#btn-history').addEventListener('click', openHistory);
  $('#btn-add').addEventListener('click', function () { openForm(null); });
  $('#btn-export').addEventListener('click', exportData);
  $('#btn-import').addEventListener('click', function () {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.import_backup) {
      window.pywebview.api.import_backup().then(function (text) {
        if (typeof text === 'string' && text) importText(text);
      }, function () {
        toast('导入失败，请确认文件格式');
      });
      return;
    }
    fileInput.click();
  });
  $('#btn-theme').addEventListener('click', function () {
    var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    save(KEY.theme, next);
  });

  fileInput.addEventListener('change', function () {
    var file = fileInput.files && fileInput.files[0];
    if (file) importData(file);
    fileInput.value = '';
  });

  /* ---------------- 启动 ---------------- */

  applyTheme();
  rebuild();
  render();

  function applyTheme() {
    var saved = load(KEY.theme, null);
    var theme = saved === 'light' || saved === 'dark'
      ? saved
      : (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    document.documentElement.dataset.theme = theme;
  }
})();