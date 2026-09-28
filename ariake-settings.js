/* マイ設定パネル (全デザイン共通)
 *
 * 住民が「自分の駅・自分の施設」だけを固定して見られるようにする。
 * 見た目は各デザインが定義する CSS 変数を継承するので、どの案に載せても馴染む。
 *   --panel / --line / --text / --muted / --accent
 */
(function (global) {
  "use strict";
  var A = global.Ariake;

  var CSS = `
  .ak-fab { position:fixed; right:16px; bottom:calc(16px + env(safe-area-inset-bottom,0px));
    z-index:60; cursor:pointer;
    background:var(--accent,#2a78d6); color:#fff; border:0; border-radius:999px;
    padding:12px 18px; font-size:13px; font-weight:700; box-shadow:0 6px 20px rgba(0,0,0,.35); }
  .ak-fab:hover { filter:brightness(1.08); }
  .ak-mask { position:fixed; inset:0; background:rgba(0,0,0,.55); z-index:70; display:none; }
  .ak-mask.on { display:block; }
  .ak-panel { position:fixed; right:0; top:0; bottom:0; width:min(400px,100%); z-index:71;
    padding-bottom:calc(40px + env(safe-area-inset-bottom,0px));
    background:var(--panel,#1a212b); color:var(--text,#e6edf3); overflow-y:auto;
    border-left:1px solid var(--line,#2a3441); padding:18px 18px 40px;
    transform:translateX(100%); transition:transform .18s ease; }
  .ak-mask.on .ak-panel { transform:none; }
  .ak-panel h2 { margin:0 0 4px; font-size:16px; }
  .ak-panel p.note { color:var(--muted,#8b97a6); font-size:11px; line-height:1.6; margin:0 0 16px; }
  .ak-sec { margin:18px 0 0; }
  .ak-sec > label { display:block; font-size:12px; font-weight:700; margin-bottom:6px; }
  .ak-panel select, .ak-panel input[type=range] { width:100%; }
  .ak-panel select { background:var(--panel,#1a212b); color:var(--text,#e6edf3);
    border:1px solid var(--line,#2a3441); border-radius:8px; padding:7px 9px; font-size:13px; }
  .ak-row { display:flex; align-items:center; gap:8px; padding:5px 0;
    border-bottom:1px solid var(--line,#2a3441); font-size:13px; }
  .ak-row .nm { flex:1; }
  .ak-row .kind { color:var(--muted,#8b97a6); font-size:10px; }
  .ak-chip { border:1px solid var(--line,#2a3441); background:transparent; cursor:pointer;
    color:var(--muted,#8b97a6); border-radius:6px; padding:3px 8px; font-size:11px; }
  .ak-chip.on { color:#fff; border-color:var(--accent,#2a78d6); background:var(--accent,#2a78d6); }
  .ak-actions { display:flex; gap:8px; margin-top:20px; flex-wrap:wrap; }
  .ak-actions button { flex:1; min-width:120px; cursor:pointer; border-radius:8px;
    padding:9px 10px; font-size:12px; border:1px solid var(--line,#2a3441);
    background:transparent; color:var(--text,#e6edf3); }
  .ak-actions button.primary { background:var(--accent,#2a78d6); border-color:transparent; color:#fff; }
  .ak-out { margin-top:10px; font-size:11px; color:var(--muted,#8b97a6); word-break:break-all; }
  .ak-code { width:100%; margin-top:8px; font-size:11px; padding:7px 9px; border-radius:8px;
    background:transparent; color:var(--text,#e6edf3); border:1px solid var(--line,#2a3441);
    font-family:ui-monospace,monospace; }
  `;

  var KINDS = { venue: "会場", facility: "施設", station: "駅", road: "道路" };

  function el(html) { var d = document.createElement("div"); d.innerHTML = html; return d.firstElementChild; }

  function mount(data) {
    var style = document.createElement("style"); style.textContent = CSS;
    document.head.appendChild(style);

    var fab = el('<button class="ak-fab" aria-haspopup="dialog">マイ設定</button>');
    var mask = el('<div class="ak-mask"><div class="ak-panel" role="dialog" aria-label="マイ設定"></div></div>');
    document.body.appendChild(fab); document.body.appendChild(mask);
    var panel = mask.querySelector(".ak-panel");

    fab.onclick = function () { render(); mask.classList.add("on"); };
    mask.onclick = function (e) { if (e.target === mask) mask.classList.remove("on"); };

    function render() {
      var p = A.personal;
      var order = data.spot_order || Object.keys(data.spots);
      var stations = order.map(function (id) { return data.spots[id]; })
        .filter(function (s) { return s && s.kind === "station"; });

      panel.innerHTML =
        '<h2>マイ設定</h2>' +
        '<p class="note">この端末にだけ保存されます。よく使う駅と見たい場所を固定しておくと、' +
        '毎回同じ並びで表示されます。</p>' +

        '<div class="ak-sec"><label>よく使う駅（最優先で表示・迂回案内の基準）</label>' +
        '<select id="ak-home"><option value="">指定しない</option>' +
        stations.map(function (s) {
          return '<option value="' + s.id + '"' + (p.home === s.id ? " selected" : "") +
                 '>' + s.name + '</option>';
        }).join("") + '</select></div>' +

        '<div class="ak-sec"><label>注意として扱う混雑度：<b id="ak-thv">' + p.threshold + '</b></label>' +
        '<input type="range" id="ak-th" min="30" max="90" step="5" value="' + p.threshold + '"></div>' +

        '<div class="ak-sec"><label>テーマ</label>' +
        '<select id="ak-theme">' +
        ["auto:端末の設定に合わせる", "light:ライト", "dark:ダーク"].map(function (o) {
          var v = o.split(":")[0];
          return '<option value="' + v + '"' + (p.theme === v ? " selected" : "") + '>' +
                 o.split(":")[1] + '</option>';
        }).join("") + '</select></div>' +

        '<div class="ak-sec"><label>' +
        '<input type="checkbox" id="ak-only"' + (p.onlyMine ? " checked" : "") + '> ' +
        '固定したものだけ表示する</label></div>' +

        '<div class="ak-sec"><label>場所ごとの設定</label>' +
        order.map(function (id) {
          var s = data.spots[id]; if (!s) return "";
          var pinned = p.pinned.indexOf(id) >= 0, hidden = p.hidden.indexOf(id) >= 0;
          return '<div class="ak-row"><span class="nm">' + s.name +
            ' <span class="kind">' + (KINDS[s.kind] || s.kind) + '</span></span>' +
            '<button class="ak-chip' + (pinned ? " on" : "") + '" data-pin="' + id + '">固定</button>' +
            '<button class="ak-chip' + (hidden ? " on" : "") + '" data-hide="' + id + '">隠す</button>' +
            '</div>';
        }).join("") + '</div>' +

        '<div class="ak-actions">' +
        '<button class="primary" id="ak-close">閉じる</button>' +
        '<button id="ak-share">設定コードをコピー</button>' +
        '<button id="ak-reset">初期状態に戻す</button>' +
        '</div>' +
        '<div class="ak-sec"><label>別の端末の設定を読み込む</label>' +
        '<input class="ak-code" id="ak-import" placeholder="設定コードを貼り付け" ' +
        'autocomplete="off" spellcheck="false">' +
        '<button class="ak-chip" id="ak-load" style="margin-top:6px">読み込む</button></div>' +
        '<div class="ak-out" id="ak-out"></div>';

      panel.querySelector("#ak-home").onchange = function (e) {
        A.setPersonal({ home: e.target.value || null });
      };
      var th = panel.querySelector("#ak-th");
      th.oninput = function (e) { panel.querySelector("#ak-thv").textContent = e.target.value; };
      th.onchange = function (e) { A.setPersonal({ threshold: +e.target.value }); };
      panel.querySelector("#ak-theme").onchange = function (e) {
        A.setPersonal({ theme: e.target.value });
      };
      panel.querySelector("#ak-only").onchange = function (e) {
        A.setPersonal({ onlyMine: e.target.checked });
      };
      panel.querySelectorAll("[data-pin]").forEach(function (b) {
        b.onclick = function () { A.togglePin(b.dataset.pin); render(); };
      });
      panel.querySelectorAll("[data-hide]").forEach(function (b) {
        b.onclick = function () { A.toggleHide(b.dataset.hide); render(); };
      });
      panel.querySelector("#ak-close").onclick = function () { mask.classList.remove("on"); };
      panel.querySelector("#ak-reset").onclick = function () {
        A.setPersonal({ home: null, pinned: [], hidden: [], threshold: 60,
                        onlyMine: false, theme: "auto" });
        render();
      };
      panel.querySelector("#ak-share").onclick = function () {
        var code = A.toCode(A.personal);
        var out = panel.querySelector("#ak-out");
        out.textContent = code;
        if (navigator.clipboard) {
          navigator.clipboard.writeText(code).then(function () {
            out.textContent = "コピーしました。別の端末で貼り付けてください。\n" + code;
          }, function () { /* コピー不可の環境では文字列を選べるように出すだけ */ });
        }
      };
      panel.querySelector("#ak-load").onclick = function () {
        var code = panel.querySelector("#ak-import").value;
        var v = A.fromCode(code);
        var out = panel.querySelector("#ak-out");
        if (!v) { out.textContent = "読み込めませんでした。コードを確認してください。"; return; }
        A.setPersonal(v);
        out.textContent = "読み込みました。";
        render();
      };
    }
  }

  global.AriakeSettings = { mount: mount };
})(window);
