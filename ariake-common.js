/* 有明混雑モニター 共通モジュール
 *
 * 5つのデザイン案と本体ダッシュボードで共有する:
 *   - データ読み込み
 *   - 混雑度スケール (順序尺度・単一色相。dataviz の ordinal 検証を通した値)
 *   - 住民向けパーソナライズ設定 (端末内保存 + URLで持ち運び)
 */
(function (global) {
  "use strict";

  // --- 混雑度スケール -------------------------------------------------------
  // 混雑度は「量」なので単一色相の順序尺度。色だけで意味を運ばせないため、
  // 表示側では必ずラベル(すいている…非常に混雑)を併記する。
  var LEVELS = [
    { max: 20,  label: "すいている", short: "空" },
    { max: 40,  label: "ふつう",     short: "並" },
    { max: 60,  label: "やや混雑",   short: "や" },
    { max: 80,  label: "混雑",       short: "混" },
    { max: 101, label: "非常に混雑", short: "激" }
  ];
  // 単一色相(青)の5段。「空いている→混雑」の向きは背景に合わせて反転させる。
  //   明るい背景 : 混雑ほど濃く (インクが増える)
  //   暗い背景   : 混雑ほど明るく (暗いと背景に沈んで逆効果になるため)
  // どちらも ordinal として検証済み (単一色相・明度単調・端が背景と十分なコントラスト)。
  var RAMP_LIGHT = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"];
  var RAMP_DARK  = ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"];
  // 面塗り(ヒートマップ)用は連続量のスケール。こちらは「ゼロ付近は背景に溶ける」
  // のが正しい挙動なので、端のコントラストを意図的に落としている
  // (離散マーク用の ordinal 基準とは別物。単一色相・明度単調は両方とも満たす)。
  var CELL_LIGHT = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#104281"];
  var CELL_DARK  = ["#0d366b", "#1c5cab", "#2a78d6", "#5598e7", "#9ec5f4"];
  // 状態色は「対応が要る状態」専用。系列色には絶対に使わない。
  var STATUS = { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" };

  function rankOf(score) {
    for (var i = 0; i < LEVELS.length; i++) if (score < LEVELS[i].max) return i + 1;
    return 5;
  }
  function levelOf(score) {
    var r = rankOf(score);
    return { rank: r, label: LEVELS[r - 1].label, short: LEVELS[r - 1].short };
  }
  // 実際に適用されているテーマを CSS から読む。閲覧者側のテーマ切替でも
  // CSSの見た目と色スケールがずれないようにするため、宣言ではなく実測する。
  // 各デザインは パレット内で --is-dark: 1/0 を定義しておく。
  var base = "dark";
  function setBase(mode) { base = mode === "light" ? "light" : "dark"; }
  function isDark() {
    try {
      var v = getComputedStyle(document.documentElement)
        .getPropertyValue("--is-dark").trim();
      if (v === "1") return true;
      if (v === "0") return false;
    } catch (e) { /* 取得できない環境では宣言値にフォールバック */ }
    if (personal && personal.theme && personal.theme !== "auto") return personal.theme === "dark";
    return base === "dark";
  }
  /** 離散マーク(数値・バー・点・バッジ)の色。どの段も背景から識別できる。 */
  function rampColor(score) {
    return (isDark() ? RAMP_DARK : RAMP_LIGHT)[rankOf(score) - 1];
  }
  /** ヒートマップのセル色。空いている時間帯は背景に沈ませて全体の濃淡を読ませる。 */
  function cellColor(score) {
    return (isDark() ? CELL_DARK : CELL_LIGHT)[rankOf(score) - 1];
  }
  function statusFor(score) {
    return score >= 80 ? STATUS.critical : score >= 60 ? STATUS.serious
         : score >= 40 ? STATUS.warning : STATUS.good;
  }

  // --- パーソナライズ設定 ---------------------------------------------------
  // 住民が「自分の使う駅・見たい施設」だけを固定できるようにする。
  // 端末内(localStorage)に保存し、URLにも書き出せるので機種変更や家族共有も可能。
  var KEY = "ariake.personal.v1";
  var DEFAULTS = {
    home: null,        // よく使う駅のID。先頭に固定し、案内の基準にする
    pinned: [],        // 先頭に固定するスポットID
    hidden: [],        // 非表示にするスポットID
    threshold: 60,     // これ以上を「注意」として扱う混雑度
    onlyMine: false,   // 固定したものだけ表示する
    theme: "auto",     // auto / light / dark
    design: "midnight", // 地図デザイン: midnight / paper / radar / flow
    icons: "small",    // 建物イラスト: off / small / large
    area: "all",       // 最後に見ていたエリア
    view: null         // 最後に見ていた地図の位置と縮尺 {lng, lat, mPx}
  };

  function read() {
    var v = {};
    try { v = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { v = {}; }
    var out = {};
    for (var k in DEFAULTS) out[k] = (k in v) ? v[k] : DEFAULTS[k];
    out.pinned = Array.isArray(out.pinned) ? out.pinned : [];
    out.hidden = Array.isArray(out.hidden) ? out.hidden : [];
    return out;
  }
  function write(p) {
    try { localStorage.setItem(KEY, JSON.stringify(p)); } catch (e) { /* 保存不可でも動く */ }
    applyTheme(p);
    document.dispatchEvent(new CustomEvent("ariake:personal", { detail: p }));
  }
  function applyTheme(p) {
    if (p.theme === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", p.theme);
    // 地図デザイン。デザイン側が明暗も色も全部決めるので、
    // data-theme より後に効くよう CSS の詳細度を上げてある。
    document.documentElement.setAttribute("data-design", p.design || "midnight");
  }

  // 設定の持ち出し・読み込み。公開ページではURLのハッシュに値を載せられないため、
  // 短いコード文字列をコピー＆貼り付けする方式にしている。
  function toCode(p) {
    return btoa(unescape(encodeURIComponent(JSON.stringify(p)))).replace(/=+$/, "");
  }
  function fromCode(code) {
    try {
      var pad = code.trim().replace(/\s+/g, "");
      while (pad.length % 4) pad += "=";
      var v = JSON.parse(decodeURIComponent(escape(atob(pad))));
      return (v && typeof v === "object") ? v : null;
    } catch (e) { return null; }
  }
  function toUrl(p) {
    return location.origin + location.pathname + "#p=" + toCode(p);
  }
  function fromUrl() {
    var m = (location.hash || "").match(/[#&]p=([A-Za-z0-9+/]+)/);
    if (!m) return null;
    try { return JSON.parse(decodeURIComponent(escape(atob(m[1])))); } catch (e) { return null; }
  }

  var personal = null;
  personal = read();
  var imported = fromUrl();
  if (imported) { personal = Object.assign(read(), imported); write(personal); }
  applyTheme(personal);

  function setPersonal(patch) {
    personal = Object.assign(personal, patch);
    write(personal);
    return personal;
  }
  function togglePin(id) {
    var i = personal.pinned.indexOf(id);
    if (i >= 0) personal.pinned.splice(i, 1); else personal.pinned.push(id);
    write(personal);
  }
  function toggleHide(id) {
    var i = personal.hidden.indexOf(id);
    if (i >= 0) personal.hidden.splice(i, 1); else personal.hidden.push(id);
    write(personal);
  }

  /** 設定を反映したスポット一覧。ホーム駅→ピン→残り の順に並べる。 */
  function orderedSpots(data, kind) {
    var order = data.spot_order || Object.keys(data.spots);
    var list = order.map(function (id) { return data.spots[id]; }).filter(Boolean);
    if (kind) list = list.filter(function (s) { return s.kind === kind; });
    list = list.filter(function (s) { return personal.hidden.indexOf(s.id) < 0; });
    if (personal.onlyMine) {
      list = list.filter(function (s) {
        return s.id === personal.home || personal.pinned.indexOf(s.id) >= 0;
      });
    }
    return list.sort(function (a, b) {
      return weight(a) - weight(b) || order.indexOf(a.id) - order.indexOf(b.id);
    });
  }
  function weight(s) {
    if (s.id === personal.home) return 0;
    if (personal.pinned.indexOf(s.id) >= 0) return 1;
    return 2;
  }

  /** 自分のしきい値を超える時間帯だけに絞ったアラート。 */
  function myAlerts(data) {
    return (data.alerts || []).filter(function (a) {
      if (personal.hidden.indexOf(a.spot) >= 0) return false;
      if (personal.onlyMine &&
          a.spot !== personal.home && personal.pinned.indexOf(a.spot) < 0) return false;
      return a.score >= personal.threshold;
    });
  }

  // --- 表示ヘルパー ---------------------------------------------------------
  var DOW = ["日", "月", "火", "水", "木", "金", "土"];
  function hhmm(slot) { return slot.slice(11, 16); }
  function md(slot) { return (+slot.slice(5, 7)) + "/" + (+slot.slice(8, 10)); }
  function dow(slot) { return DOW[new Date(slot).getDay()]; }
  function when(slot) { return md(slot) + "(" + dow(slot) + ") " + hhmm(slot); }
  /** 今から何時間後か (series の index と一致する) */
  function hoursFromNow(data, slot) {
    var base = new Date(data.spots[data.spot_order[0]].series[0].slot);
    return Math.round((new Date(slot) - base) / 3600000);
  }

  /** 寄与要因から「平常値」以外の主因を1つ返す (無ければ null)。 */
  function mainCause(factors) {
    var list = factors || [];
    for (var i = 0; i < list.length; i++) {
      var f = list[i];
      var isBase = f.kind ? f.kind === "baseline" : /^平常値/.test(f.label || "");
      if (!isBase) return f.label;
    }
    return null;
  }

  function load(path) {
    return fetch((path || "ariake.json") + "?" + Date.now()).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  }

  global.Ariake = {
    LEVELS: LEVELS, STATUS: STATUS,
    rankOf: rankOf, levelOf: levelOf, rampColor: rampColor, cellColor: cellColor,
    statusFor: statusFor,
    isDark: isDark, setBase: setBase,
    get personal() { return personal; },
    setPersonal: setPersonal, togglePin: togglePin, toggleHide: toggleHide,
    orderedSpots: orderedSpots, myAlerts: myAlerts,
    toUrl: toUrl, toCode: toCode, fromCode: fromCode, load: load, mainCause: mainCause,
    hhmm: hhmm, md: md, dow: dow, when: when, hoursFromNow: hoursFromNow
  };
})(window);
