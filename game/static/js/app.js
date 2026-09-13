/* ==========================================================================
   AI 种田经营游戏 · 前端交互层
   原生 JS，无框架、无构建步骤。职责：拉取状态 -> 渲染面板 -> 派发行动。
   ========================================================================== */
(function () {
  'use strict';

  /* ---------------- 全局 ---------------- */
  var S = null;          // 当前游戏状态
  var META = null;       // 静态配置表
  var logFilter = 'all';
  var busy = false;
  var prev = { gold: null, assets: null, energy: null, prices: {} };

  var $ = function (id) { return document.getElementById(id); };

  /* ---------------- 工具 ---------------- */
  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function fmt(n) {
    return Number(n || 0).toLocaleString('zh-CN');
  }

  function animateNumber(el, to) {
    if (!el) return;
    var from = Number(el.dataset.value || 0);
    to = Number(to || 0);
    el.dataset.value = to;
    if (from === to || Math.abs(to - from) > 100000) { el.textContent = fmt(to); return; }
    var start = performance.now();
    var dur = 420;
    (function step(now) {
      var p = Math.min(1, (now - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(Math.round(from + (to - from) * eased));
      if (p < 1) requestAnimationFrame(step);
    })(start);
  }

  function toast(title, body, cls) {
    var box = document.createElement('div');
    box.className = 'toast' + (cls ? ' ' + cls : '');
    box.innerHTML = '<strong>' + esc(title) + '</strong>' + esc(body || '');
    $('toastStack').appendChild(box);
    setTimeout(function () {
      box.classList.add('out');
      setTimeout(function () { box.remove(); }, 320);
    }, 3600);
  }

  /* ---------------- 网络 ---------------- */
  function api(path, body) {
    var opts = { headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) {
      opts.method = 'POST';
      opts.body = JSON.stringify(body || {});
    }
    return fetch(path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok || data.ok === false) {
          var msg = (data.error && data.error.message) || ('请求失败（HTTP ' + res.status + '）');
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  function withBusy(fn) {
    if (busy) return Promise.resolve();
    busy = true;
    document.body.style.cursor = 'progress';
    return Promise.resolve()
      .then(fn)
      .catch(function (err) { toast('操作失败', err.message || '未知错误'); })
      .then(function () {
        busy = false;
        document.body.style.cursor = '';
      });
  }

  /* ---------------- 渲染：顶部 ---------------- */
  function renderHeader() {
    document.body.dataset.weather = S.weather;

    $('dayNow').textContent = S.day;
    $('dayMax').textContent = S.max_day;
    $('dayLeft').textContent = S.finished ? '本季已结束' : ('还剩 ' + (S.max_day - S.day) + ' 天');
    renderDayTicks();

    $('weatherIcon').textContent = S.weather_icon;
    $('weatherName').textContent = S.weather;
    $('weatherTip').textContent = S.weather_tip;
    $('forecastName').textContent = S.forecast_icon + ' ' + S.forecast;

    animateNumber($('goldValue'), S.gold);
    $('energyValue').textContent = S.energy;
    $('energyMax').textContent = S.max_energy;
    $('energyBar').style.width = Math.max(0, (S.energy / S.max_energy) * 100) + '%';
    animateNumber($('assetValue'), S.assets);

    var btn = $('btnNextDay');
    var blocked = !!S.pending_event || S.finished;
    btn.disabled = blocked;
    btn.classList.toggle('pulse', !blocked);
    $('nextDayHint').textContent = S.finished
      ? '本季已结束'
      : (S.pending_event ? '请先处理今日事件' : '天气 · AI 事件 · 结算');
  }

  /* 30 格刻度：已过 / 当天 / 未到，一眼看出季度进度 */
  function renderDayTicks() {
    var box = $('dayTicks');
    if (!box) return;
    if (box.childElementCount !== S.max_day) {
      box.innerHTML = new Array(S.max_day + 1).join('<i></i>');
    }
    var ticks = box.children;
    for (var i = 0; i < ticks.length; i++) {
      var cls = i < S.day - 1 ? 'done' : (i === S.day - 1 ? 'now' : '');
      if (ticks[i].className !== cls) ticks[i].className = cls;
    }
  }

  /* ---------------- 渲染：农田 ---------------- */
  function plotTags(p) {
    var tags = [];
    if (!p.crop) return '';
    if (p.ready) tags.push('<span class="tag tag-ready">可收获</span>');
    if (p.water < 30) tags.push('<span class="tag tag-thirsty">缺水</span>');
    if (p.pest) tags.push('<span class="tag tag-pest">虫害</span>');
    if (p.fertilized) tags.push('<span class="tag tag-fert">已施肥</span>');
    return tags.join('');
  }

  function renderFarm() {
    $('plotCount').textContent = S.land.length;
    $('farmGrid').innerHTML = S.land.map(function (p) {
      var cls = 'plot'
        + (p.crop ? '' : ' is-empty')
        + (p.ready ? ' ready' : '')
        + (p.crop && p.water < 30 ? ' thirsty' : '')
        + (p.pest ? ' pest' : '');

      if (!p.crop) {
        return '' +
          '<button class="' + cls + '" data-plot="' + p.id + '" aria-label="第 ' + (p.id + 1) + ' 号地，空地">' +
            '<span class="plot-inner">' +
              '<span class="plot-idx">#' + (p.id + 1) + '</span>' +
              '<span class="plot-stage-area">' +
                '<span class="plot-empty-hint"><span class="plus">＋</span><em>点击播种</em></span>' +
              '</span>' +
              '<span class="plot-name-row"><span class="plot-name">空地</span>' +
                '<span class="plot-stage-txt">未翻种</span></span>' +
            '</span>' +
          '</button>';
      }

      // 幼苗期用统一的嫩芽形象，旺长后才显示作物本体
      var face = p.stage <= 1 ? '🌱' : p.emoji;
      // 作物随生长进度由小变大（0.62 → 1.12）
      var scale = p.ready ? 1.12 : 0.62 + 0.42 * (p.progress_pct / 100);

      return '' +
        '<button class="' + cls + '" data-plot="' + p.id + '" aria-label="第 ' + (p.id + 1) + ' 号地，' + esc(p.crop) + '">' +
          '<span class="plot-inner">' +
            '<span class="plot-idx">#' + (p.id + 1) + '</span>' +
            '<span class="plot-tags">' + plotTags(p) + '</span>' +
            '<span class="plot-stage-area">' +
              '<span class="plot-crop" style="--p:' + scale.toFixed(3) + '">' + face + '</span>' +
            '</span>' +
            '<span class="plot-name-row">' +
              '<span class="plot-name">' + esc(p.crop) + '</span>' +
              '<span class="plot-stage-txt">' + esc(p.stage_name) +
                (p.ready ? ' · 可收获' : ' · 还需 ' + p.days_left + ' 天') + '</span>' +
            '</span>' +
            '<span class="plot-meters">' +
              '<span class="plot-meter"><span class="meter-label">生长</span>' +
                '<span class="meter"><i class="grow' + (p.ready ? ' ripe' : '') + '" style="width:' + p.progress_pct + '%"></i></span>' +
                '<span class="meter-val">' + Math.round(p.progress_pct) + '%</span></span>' +
              '<span class="plot-meter"><span class="meter-label">水分</span>' +
                '<span class="meter"><i class="water" style="width:' + p.water + '%"></i></span>' +
                '<span class="meter-val">' + p.water + '</span></span>' +
            '</span>' +
          '</span>' +
        '</button>';
    }).join('');
  }

  /* ---------------- 渲染：市场 ---------------- */
  function renderMarket() {
    var order = META.crop_names;
    $('marketList').innerHTML = order.map(function (crop) {
      var m = S.market[crop];
      var cfg = META.crops[crop];
      var trendCls = m.delta > 0 ? 'up' : (m.delta < 0 ? 'down' : 'flat');
      var arrow = m.delta > 0 ? '▲' : (m.delta < 0 ? '▼' : '—');
      var stock = S.harvest[crop] || 0;
      var tick = prev.prices[crop] !== undefined && prev.prices[crop] !== m.price ? ' price-tick' : '';
      prev.prices[crop] = m.price;
      // 价格在 0.6 ~ 1.7 倍区间内的相对位置，用一根细条直观表达贵贱
      var pct = Math.max(0, Math.min(1, (m.ratio - 0.6) / 1.1)) * 100;
      var cheap = m.ratio < 0.98;
      return '' +
        '<div class="market-row">' +
          '<span class="market-emoji">' + cfg.emoji + '</span>' +
          '<div class="market-info">' +
            '<div class="market-name">' + esc(crop) +
              '<span class="market-sub">基准 ' + m.base + '</span>' +
            '</div>' +
            '<div class="price-track' + (cheap ? ' down' : '') + '"><i style="width:' + pct.toFixed(1) + '%"></i></div>' +
            (stock
              ? '<button class="mini sell" data-sell="' + esc(crop) + '" data-amount="all">卖出库存 ×' + stock + '</button>'
              : '<span class="market-sub">仓库暂无存货</span>') +
          '</div>' +
          '<div class="market-price' + tick + '">' +
            '<b class="' + trendCls + '">' + m.price + '</b>' +
            '<span class="market-delta ' + trendCls + '">' + arrow + ' ' + Math.abs(m.delta) + '</span>' +
          '</div>' +
        '</div>';
    }).join('');
  }

  /* ---------------- 渲染：仓库与种子 ---------------- */
  function renderBag() {
    var seeds = META.crop_names.map(function (crop) {
      var cfg = META.crops[crop];
      var have = S.seeds[crop] || 0;
      var afford = S.gold >= cfg.seed_cost;
      return '' +
        '<div class="bag-row">' +
          '<span class="market-emoji">' + cfg.emoji + '</span>' +
          '<div class="bag-info">' +
            '<div class="bag-name">' + esc(crop) + '种子</div>' +
            '<div class="bag-sub">' + cfg.seed_cost + ' 金 / 包 · ' + cfg.grow_days + ' 天成熟</div>' +
          '</div>' +
          '<span class="bag-num">×' + have + '</span>' +
          '<div class="bag-actions">' +
            '<button class="mini" data-buy="' + esc(crop) + '" data-amount="1"' + (afford ? '' : ' disabled') + '>买 1</button>' +
            '<button class="mini" data-buy="' + esc(crop) + '" data-amount="5"' + (S.gold >= cfg.seed_cost * 5 ? '' : ' disabled') + '>买 5</button>' +
          '</div>' +
        '</div>';
    }).join('');

    var harvest = META.crop_names.map(function (crop) {
      var have = S.harvest[crop] || 0;
      var cfg = META.crops[crop];
      var price = S.market[crop].price;
      var ratio = price / S.market[crop].base;
      var cls = ratio >= 1.05 ? 'up' : (ratio <= 0.95 ? 'down' : 'flat');
      return '' +
        '<div class="bag-row">' +
          '<span class="market-emoji">' + cfg.emoji + '</span>' +
          '<div class="bag-info">' +
            '<div class="bag-name">' + esc(crop) + '</div>' +
            '<div class="bag-sub">现价 <b class="' + cls + '">' + price + '</b> / 份</div>' +
          '</div>' +
          '<span class="bag-num">×' + have + '</span>' +
          '<div class="bag-actions">' +
            '<button class="mini sell" data-sell="' + esc(crop) + '" data-amount="1"' + (have > 0 ? '' : ' disabled') + '>卖 1</button>' +
            '<button class="mini sell" data-sell="' + esc(crop) + '" data-amount="all"' + (have > 0 ? '' : ' disabled') + '>全卖</button>' +
          '</div>' +
        '</div>';
    }).join('');

    $('bagList').innerHTML =
      '<div class="bag-sec">种子</div>' + seeds +
      '<div class="bag-sec">收成</div>' + harvest;
  }

  /* ---------------- 渲染：日志 ---------------- */
  var LOG_ICON = {
    weather: '🌦️', pest: '🐛', market: '📈', social: '🤝', good: '✨',
    action: '🚜', achievement: '🏅', info: '·'
  };

  function renderLog() {
    var items = S.log.slice().reverse().filter(function (e) {
      if (logFilter === 'all') return true;
      return e.source === logFilter;
    });
    if (!items.length) {
      $('logStream').innerHTML = '<div class="log-item"><span class="log-day">--</span><div class="log-body">暂无符合条件的记录。</div></div>';
      return;
    }
    $('logStream').innerHTML = items.map(function (e) {
      var src = '';
      if (e.source === 'llm') src = '<span class="badge src-llm">AI 生成</span>';
      else if (e.source === 'fallback') src = '<span class="badge src-fallback">本地兜底</span>';
      return '' +
        '<div class="log-item" data-type="' + esc(e.type) + '">' +
          '<span class="log-day">D' + e.day + '</span>' +
          '<div class="log-body">' +
            '<div>' + (LOG_ICON[e.type] || '') + ' ' + esc(e.text) + '</div>' +
            (src ? '<div class="log-meta">' + src + '</div>' : '') +
          '</div>' +
        '</div>';
    }).join('');
  }

  /* ---------------- 渲染：成就墙 ---------------- */
  function renderAch() {
    var unlocked = S.achievements || [];
    $('achCount').textContent = unlocked.length + '/' + META.achievements.length;
    $('achGrid').innerHTML = META.achievements.map(function (a) {
      var on = unlocked.indexOf(a.id) >= 0;
      return '' +
        '<div class="ach' + (on ? ' unlocked' : '') + '">' +
          '<span class="ach-icon">' + a.icon + '</span>' +
          '<div class="ach-body">' +
            '<div class="ach-name">' + esc(a.name) + '</div>' +
            '<div class="ach-desc">' + esc(a.desc) + '</div>' +
          '</div>' +
        '</div>';
    }).join('');
  }

  /* ---------------- 渲染：AI 面板 ---------------- */
  function renderAI() {
    var st = S.stats;
    var live = !!META.llm_enabled;
    var diag = META.llm || {};
    var badge = $('aiBadge');
    badge.textContent = live ? '大模型已接入' : '本地兜底模式';
    badge.className = 'badge ' + (live ? 'live' : 'off');

    $('aiLlmCount').textContent = st.event_llm;
    $('aiFbCount').textContent = st.event_fallback;
    var total = st.event_llm + st.event_fallback;
    $('aiRate').textContent = total ? Math.round((st.event_llm / total) * 100) + '%' : '—';

    var ev = S.pending_event;
    var note;
    if (!live) {
      var miss = (diag.missing && diag.missing.length) ? diag.missing.join('；') : '接口地址与凭证';
      note = '当前未接入大模型，缺失 ' + miss + '，事件全部来自 24 条内置事件库。' +
        '容器运行请透传 -e CNB_API_ENDPOINT -e CNB_REPO_SLUG -e CNB_TOKEN，配置后自动切换为大模型实时生成。';
    } else if (ev) {
      note = '今日事件由' + (ev.source === 'llm' ? '大模型实时生成' : '内置事件库兜底') +
        '（耗时 ' + (ev.latency || 0) + 's）' + (ev.reason ? '：' + ev.reason : '');
    } else {
      note = '每日进入新的一天时，会携带当前农田状态调用大模型（' + (diag.model || '默认模型') +
        '）生成事件；超时或返回异常时自动降级，不影响游戏。';
    }
    $('aiNote').textContent = note;
    $('llmState').textContent = live
      ? 'AI 事件：' + (diag.model || '大模型') + ' 实时生成'
      : 'AI 事件：内置事件库兜底';
  }

  /* ---------------- 主渲染 ---------------- */
  function render() {
    renderHeader();
    renderFarm();
    renderMarket();
    renderBag();
    renderLog();
    renderAch();
    renderAI();
  }

  /* ---------------- 弹窗基础 ---------------- */
  var modalRoot = $('modalRoot');

  function openModal(html, onClose) {
    modalRoot.innerHTML = '<div class="modal" role="dialog" aria-modal="true">' + html + '</div>';
    modalRoot.classList.add('open');
    modalRoot.setAttribute('aria-hidden', 'false');
    modalRoot._onClose = onClose || null;
    var focusable = modalRoot.querySelector('button:not([disabled])');
    if (focusable) focusable.focus();
  }

  function closeModal() {
    var cb = modalRoot._onClose;
    modalRoot.classList.remove('open');
    modalRoot.setAttribute('aria-hidden', 'true');
    modalRoot.innerHTML = '';
    modalRoot._onClose = null;
    if (cb) cb();
  }

  modalRoot.addEventListener('click', function (e) {
    if (e.target === modalRoot) closeModal();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modalRoot.classList.contains('open')) closeModal();
  });

  /* ---------------- 地块弹窗 ---------------- */
  var currentPlotId = 0;

  function openPlotModal(plotId) {
    var p = S.land[plotId];
    if (!p) return;
    currentPlotId = plotId;

    if (!p.crop) {
      var cards = META.crop_names.map(function (crop) {
        var cfg = META.crops[crop];
        var haveSeed = (S.seeds[crop] || 0) > 0;
        var canPay = S.gold >= cfg.seed_cost;
        var ok = S.energy >= META.energy_cost.plant && (haveSeed || canPay) && !S.finished;
        var weather = Object.keys(cfg.weather).map(function (w) {
          return w + ' ' + cfg.weather[w].toFixed(2);
        }).join(' · ');
        return '' +
          '<button class="crop-card" data-plant="' + esc(crop) + '"' + (ok ? '' : ' disabled') + '>' +
            '<span class="crop-emoji">' + cfg.emoji + '</span>' +
            '<div>' +
              '<div class="crop-name">' + esc(crop) + (haveSeed ? ' <span class="badge live">种子 ×' + S.seeds[crop] + '</span>' : '') + '</div>' +
              '<div class="crop-spec">' +
                '成本 ' + (haveSeed ? '0（用库存种子）' : cfg.seed_cost + ' 金') +
                ' · ' + cfg.grow_days + ' 天<br>' +
                '单产 ' + cfg.base_yield + ' 份 × 基准 ' + cfg.base_price + ' 金<br>' +
                '天气系数 ' + weather +
              '</div>' +
            '</div>' +
          '</button>';
      }).join('');

      openModal(
        '<div class="modal-strip"></div>' +
        '<div class="modal-head">' +
          '<div class="modal-tags"><span class="badge">地块 #' + (plotId + 1) + '</span><span class="badge">体力 -' + META.energy_cost.plant + '</span></div>' +
          '<div class="modal-title">选择要播种的作物</div>' +
        '</div>' +
        '<div class="modal-desc" style="padding-bottom:0">种子会优先消耗库存，库存不足时自动花金币购买。</div>' +
        '<div class="modal-body"><div class="crop-picker">' + cards + '</div>' +
          '<button class="btn btn-ghost" data-close>取消</button></div>'
      );
      return;
    }

    var cfgP = META.crops[p.crop];
    var canWater = S.energy >= META.energy_cost.water && p.water < 100;
    var canFert = S.energy >= META.energy_cost.fertilize && !p.fertilized && S.gold >= META.fertilizer_cost;
    var canHarvest = p.ready && S.energy >= META.energy_cost.harvest;

    openModal(
      '<div class="modal-strip"></div>' +
      '<div class="modal-head">' +
        '<div class="modal-tags">' +
          '<span class="badge">地块 #' + (plotId + 1) + '</span>' +
          '<span class="badge">' + esc(p.stage_name) + '</span>' +
          (p.ready ? '<span class="badge src-llm">可收获</span>' : '') +
          (p.pest ? '<span class="badge src-fallback">虫害</span>' : '') +
        '</div>' +
        '<div class="modal-title">' + cfgP.emoji + ' ' + esc(p.crop) + '</div>' +
      '</div>' +
      '<div class="modal-body">' +
        '<div class="result-grid">' +
          '<div class="result-stat"><span>生长进度</span><b>' + Math.round(p.progress_pct) + '%</b></div>' +
          '<div class="result-stat"><span>剩余天数</span><b>' + (p.ready ? '已成熟' : p.days_left + ' 天') + '</b></div>' +
          '<div class="result-stat"><span>水分</span><b>' + p.water + ' / 100</b></div>' +
          '<div class="result-stat"><span>事件系数</span><b>×' + p.event_bonus.toFixed(2) + '</b></div>' +
        '</div>' +
        '<div class="action-grid">' +
          '<button class="action-btn" data-act="water"' + (canWater ? '' : ' disabled') + '>' +
            '<b>浇水</b><span>体力 -' + META.energy_cost.water + ' · 水分 +45</span></button>' +
          '<button class="action-btn" data-act="fertilize"' + (canFert ? '' : ' disabled') + '>' +
            '<b>施肥</b><span>体力 -' + META.energy_cost.fertilize + ' · ' + META.fertilizer_cost + ' 金 · 产量 +25%</span></button>' +
          '<button class="action-btn" data-act="harvest"' + (canHarvest ? '' : ' disabled') + '>' +
            '<b>收获</b><span>体力 -' + META.energy_cost.harvest + (p.ready ? ' · 当前预产 ' + estimateYield(p) + ' 份' : ' · 尚未成熟') + '</span></button>' +
          '<button class="action-btn" data-close><b>关闭</b><span>再想想</span></button>' +
        '</div>' +
      '</div>',
      null
    );

    modalRoot.querySelectorAll('[data-act]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var act = btn.dataset.act;
        var payload = { type: act, plot: plotId };
        if (act === 'harvest') payload.crop = p.crop;
        doAction(payload, function () { closeModal(); });
      });
    });
  }

  function estimateYield(p) {
    var cfg = META.crops[p.crop];
    var wf = cfg.weather[S.weather] || 1;
    var care = (p.water >= 60 ? 1 : (p.water >= 30 ? 0.85 : 0.6)) *
      (p.fertilized ? 1.25 : 1) * (p.pest ? 0.55 : 1);
    return Math.max(1, Math.round(cfg.base_yield * wf * care * p.event_bonus));
  }

  /* ---------------- 事件弹窗 ---------------- */
  function openEventModal(ev) {
    var type = (META.event_types[ev.type] || {});
    var effects = ev.effects || {};
    var chips = [];
    if (effects.gold) chips.push('金币 ' + (effects.gold > 0 ? '+' : '') + effects.gold);
    if (effects.energy) chips.push('体力 ' + (effects.energy > 0 ? '+' : '') + effects.energy);
    if (effects.growth_bonus) chips.push('生长系数 ' + (effects.growth_bonus > 0 ? '+' : '') + Math.round(effects.growth_bonus * 100) + '%');
    if (effects.market_modifier) {
      Object.keys(effects.market_modifier).forEach(function (c) {
        chips.push(c + ' 行情 ×' + effects.market_modifier[c]);
      });
    }
    if (!chips.length) chips.push('无即时影响');

    var choices = (ev.choices || []).map(function (c, i) {
      var cost = Number(c.cost || 0);
      var afford = cost <= S.gold;
      return '' +
        '<button class="choice" data-choice="' + i + '"' + (afford ? '' : ' disabled') + '>' +
          '<span class="choice-idx">' + (i + 1) + '</span>' +
          '<span class="choice-body">' +
            '<span class="choice-text">' + esc(c.text) + '</span>' +
            (c.hint ? '<span class="choice-hint">' + esc(c.hint) + '</span>' : '') +
          '</span>' +
          '<span class="choice-cost' + (cost ? '' : ' free') + '">' + (cost ? '-' + cost + ' 金' : '免费') + '</span>' +
        '</button>';
    }).join('');

    openModal(
      '<div class="modal-strip" style="background:linear-gradient(90deg,' +
        (type.color || '#43A047') + ',' + (type.color || '#43A047') + '33)"></div>' +
      '<div class="modal-head">' +
        '<div class="modal-tags">' +
          '<span class="badge" style="color:' + (type.color || '#fff') + '">' + (type.icon || '') + ' ' + (type.label || ev.type) + '</span>' +
          (ev.source === 'llm'
            ? '<span class="badge src-llm">AI 实时生成 · ' + (ev.latency || 0) + 's</span>'
            : '<span class="badge src-fallback">本地兜底事件</span>') +
          '<span class="badge">第 ' + S.day + ' 天</span>' +
        '</div>' +
        '<div class="modal-title">' + esc(ev.title) + '</div>' +
      '</div>' +
      '<div class="modal-desc">' + esc(ev.description) + '</div>' +
      '<div class="modal-body">' +
        '<div class="effects">' + chips.map(function (c) { return '<span class="effect">' + esc(c) + '</span>'; }).join('') + '</div>' +
        choices +
        (ev.reason ? '<div class="ai-note" style="padding:0">降级原因：' + esc(ev.reason) + '</div>' : '') +
      '</div>'
    );

    modalRoot.querySelectorAll('[data-choice]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = Number(btn.dataset.choice);
        withBusy(function () {
          return api('/api/event/choose', { index: idx }).then(function (data) {
            applyPayload(data);
            closeModal();
          });
        });
      });
    });
  }

  /* ---------------- 结算弹窗 ---------------- */
  function openResultModal(rating) {
    var st = S.stats;
    var ach = META.achievements.filter(function (a) { return (S.achievements || []).indexOf(a.id) >= 0; });
    openModal(
      '<div class="modal-strip" style="background:linear-gradient(90deg,#FFC53D,#F9A825)"></div>' +
      '<div class="result-hero">' +
        '<span class="result-icon">' + rating.icon + '</span>' +
        '<span class="result-name">' + esc(rating.name) + '</span>' +
        '<span class="result-desc">' + esc(rating.desc) + '</span>' +
        '<span class="result-assets">' + fmt(rating.assets) + ' <em>金币总资产</em></span>' +
      '</div>' +
      '<div class="modal-body">' +
        '<div class="result-grid">' +
          '<div class="result-stat"><span>累计收获</span><b>' + st.harvested_count + ' 份</b></div>' +
          '<div class="result-stat"><span>卖货收入</span><b>' + fmt(st.total_earned) + ' 金</b></div>' +
          '<div class="result-stat"><span>总支出</span><b>' + fmt(st.total_spent) + ' 金</b></div>' +
          '<div class="result-stat"><span>最高资产</span><b>' + fmt(st.max_asset) + ' 金</b></div>' +
          '<div class="result-stat"><span>AI 生成事件</span><b>' + st.event_llm + ' 次</b></div>' +
          '<div class="result-stat"><span>兜底事件</span><b>' + st.event_fallback + ' 次</b></div>' +
        '</div>' +
        '<div class="effects">' + (ach.length
          ? ach.map(function (a) { return '<span class="effect">' + a.icon + ' ' + esc(a.name) + '</span>'; }).join('')
          : '<span class="effect">本季没有解锁成就</span>') + '</div>' +
        '<button class="btn btn-primary" data-newgame style="justify-content:center">再玩一局</button>' +
      '</div>'
    );
    var btn = modalRoot.querySelector('[data-newgame]');
    if (btn) btn.addEventListener('click', function () { closeModal(); newGame(); });
  }

  /* ---------------- 行动派发 ---------------- */
  function doAction(payload, after) {
    withBusy(function () {
      return api('/api/action', payload).then(function (data) {
        applyPayload(data);
        if (after) after();
      });
    });
  }

  function applyPayload(data) {
    S = data.state;
    render();
    if (data.event) {
      setTimeout(function () { openEventModal(data.event); }, 240);
    }
    (data.new_achievements || []).forEach(function (a, i) {
      setTimeout(function () {
        toast('解锁成就 ' + a.icon, a.name + ' —— ' + a.desc, 'ach');
      }, 260 + i * 420);
    });
    if (data.finished) {
      api('/api/rating').then(function (r) {
        setTimeout(function () { openResultModal(r.rating); }, 420);
      });
    }
  }

  function nextDay() {
    withBusy(function () {
      return api('/api/next-day', {}).then(function (data) {
        applyPayload(data);
        if (!data.event && !data.finished) {
          toast('新的一天', '第 ' + data.state.day + ' 天，天气 ' + data.state.weather + '。');
        }
      });
    });
  }

  function newGame() {
    withBusy(function () {
      return api('/api/new-game', {}).then(function (data) {
        S = data.state;
        prev = { gold: null, assets: null, energy: null, prices: {} };
        render();
        toast('新的一季', '30 天农场计划开始，祝你好运。');
        if (data.state.pending_event) {
          setTimeout(function () { openEventModal(data.state.pending_event); }, 300);
        }
      });
    });
  }

  /* ---------------- 事件绑定 ---------------- */
  // 统一事件委托：地块 / 买卖 / 关闭 / 播种 / 日志筛选
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;

    var chip = e.target.closest('#logFilter .chip');
    if (chip) {
      logFilter = chip.dataset.filter;
      chip.parentElement.querySelectorAll('.chip').forEach(function (c) {
        c.classList.toggle('active', c === chip);
      });
      renderLog();
      return;
    }

    var card = e.target.closest('[data-plant]');
    if (card && modalRoot.contains(card)) {
      doAction({ type: 'plant', plot: currentPlotId, crop: card.dataset.plant }, closeModal);
      return;
    }

    var t = e.target.closest('[data-plot],[data-buy],[data-sell],[data-close]');
    if (!t) return;

    if (t.hasAttribute('data-plot')) { openPlotModal(Number(t.dataset.plot)); return; }
    if (t.hasAttribute('data-close')) { closeModal(); return; }
    if (t.hasAttribute('data-buy')) {
      doAction({ type: 'buy', crop: t.dataset.buy, amount: Number(t.dataset.amount) });
      return;
    }
    if (t.hasAttribute('data-sell')) {
      doAction({ type: 'sell', crop: t.dataset.sell, amount: t.dataset.amount });
    }
  });

  $('btnNextDay').addEventListener('click', nextDay);
  $('btnNewGame').addEventListener('click', function () {
    if (window.confirm('确定要放弃当前进度，重新开始 30 天吗？')) newGame();
  });
  $('btnRest').addEventListener('click', function () { doAction({ type: 'rest' }); });

  /* ---------------- 启动 ---------------- */
  function boot() {
    Promise.all([api('/api/meta'), api('/api/state')])
      .then(function (res) {
        META = res[0].meta;
        S = res[1].state;
        // 预置价格，避免首屏全部触发跳动动画
        Object.keys(S.market).forEach(function (c) { prev.prices[c] = S.market[c].price; });
        render();
        $('boot').classList.add('hide');
        if (S.pending_event) {
          setTimeout(function () { openEventModal(S.pending_event); }, 380);
        } else if (S.finished) {
          api('/api/rating').then(function (r) { openResultModal(r.rating); });
        }
      })
      .catch(function (err) {
        $('boot').innerHTML = '<div class="boot-inner"><span class="boot-emoji">🥀</span><p>加载失败：' + esc(err.message) + '</p></div>';
      });
  }

  boot();
})();
