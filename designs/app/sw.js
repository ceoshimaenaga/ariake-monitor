/* ホーム画面に置いたときのための Service Worker。
 *
 * 考え方は2つだけ。
 *   - 地図の下地 (地形・建物・イラスト) は滅多に変わらないので、まず手元から出す
 *   - 混雑データは鮮度が命なので、まず取りに行き、繋がらないときだけ手元から出す
 *
 * 電波の無い地下や、通信が細い場所でも、直前の予測だけは開けるようにする。
 * ただし「いつ時点のものか」は画面側が必ず出すので、古いものを黙って
 * 新しいふりをして見せることはしない。
 */
var VERSION = "v4";
var SHELL = "ariake-shell-" + VERSION;
var DATA = "ariake-data-" + VERSION;

/* 下地。最初の訪問で入れておく。
 * 建物イラストは拡大したときだけ要るので、ここには入れず、使われた時に貯める。 */
var SHELL_FILES = [
  "./",
  "./index.html",
  "./ariake-common.js",
  "./ariake-settings.js",
  "./basemap.json",
  "./app/icon-192.png",
  "./app/icon-512.png",
  "./app/manifest.webmanifest"
];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(SHELL).then(function (c) {
      // 1つでも落ちると全部入らないので、個別に入れて失敗は無視する
      return Promise.all(SHELL_FILES.map(function (u) {
        return c.add(new Request(u, { cache: "reload" })).catch(function () {});
      }));
    }).then(function () {
      // 混雑データも最初の訪問で入れておく。
      // 初回はまだこの Service Worker がページを見ていないので、
      // ここで入れておかないと「一度も online で開いていない状態」に
      // なってしまい、オフラインで真っ白になる。
      return caches.open(DATA).then(function (c) {
        return c.add(new Request("./ariake.json", { cache: "reload" }))
                .catch(function () {});
      });
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        // 古い版の貯めものを消す
        if (k !== SHELL && k !== DATA) return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

function isData(url) {
  return url.pathname.endsWith("/ariake.json");
}

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // 外部の埋め込みには触らない

  // 混雑データ: まず取りに行く。繋がらなければ手元の最後のもの。
  if (isData(url)) {
    e.respondWith(
      fetch(req).then(function (res) {
        if (res && res.ok) {
          var copy = res.clone();
          caches.open(DATA).then(function (c) { c.put("./ariake.json", copy); });
        }
        return res;
      }).catch(function () {
        return caches.open(DATA).then(function (c) {
          return c.match("./ariake.json");
        });
      })
    );
    return;
  }

  // ページ本体: まず取りに行く (更新を見逃さないため)。だめなら手元。
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).catch(function () {
        return caches.match("./index.html").then(function (r) {
          return r || caches.match("./");
        });
      })
    );
    return;
  }

  // それ以外 (下地・イラスト・スクリプト): まず手元、裏で取り直す
  e.respondWith(
    caches.match(req).then(function (hit) {
      var net = fetch(req).then(function (res) {
        if (res && res.ok) {
          var copy = res.clone();
          caches.open(SHELL).then(function (c) { c.put(req, copy); });
        }
        return res;
      }).catch(function () { return hit; });
      return hit || net;
    })
  );
});
