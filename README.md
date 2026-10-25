# 有明 混雑マップ

有明・豊洲・お台場の **いまの混雑と3日先までの予測** を、実際の地形の地図の上に表示します。

**公開ページ → https://ceoshimaenaga.github.io/ariake-monitor/**

対象は有明の住民と、これから有明に行く人。イベント会場だけでなく、
駅・道路・商業施設・病院まで含めた31地点を見ています。

## 仕組み

毎時 GitHub Actions が各施設の公式サイトからイベント予定を集め、
来場者数を入退場カーブに分解して、地点ごとの混雑度 (0-100) を3日先まで計算します。

```
混雑度 = 平常値 × 天候係数 × 祝日係数 + イベント負荷
```

会場は「滞在人数」、駅と道路は「通過する人の流れ」、周辺施設は
「滞在人数＋イベント後の流入」として扱い、会場からの距離に応じて
影響を減衰させています。推定値なので、地点から離れるほど薄く描いています。

## データの出どころ

| 種類 | 出どころ |
|---|---|
| イベント予定 | 東京ビッグサイト / 有明アリーナ / 有明コロシアム / 東京ガーデンシアター / 有明四季劇場 / 有明ガーデン の各公式サイト |
| 地形・建物・道路・鉄道 | OpenStreetMap (ODbL) |
| 天気 | Open-Meteo |

建物のイラストは、それぞれの建物の実際の写真を参照して生成したものです。

## 構成

| パス | 役割 |
|---|---|
| `ariake/collect.py` | 収集して `ariake.json` を書き出す |
| `ariake/forecast.py` | 混雑度の予測モデル |
| `ariake/fetch_basemap.py` | OpenStreetMap から地形を取得し、海岸線から陸のポリゴンを組み立てる |
| `ariake/build_site.py` | 公開サイト `_site/` を組み立てる |
| `designs/5-atlas.html` | 地図ページの原本 (公開ページはこれをビルドしたもの) |

## 手元で動かす

```
pip install -r requirements.txt
python ariake/collect.py
python ariake/build_site.py
python -m http.server -d _site
```

## ライセンス・出典

地図データは © OpenStreetMap contributors (ODbL)。
イベント情報は各施設の公開ページから取得した公開情報です。

## 手元の PC だけで動かす

→ 引き継ぎの詳細は **[HANDOVER.md](HANDOVER.md)** にまとめてある。

収集・予測・サイトの組み立て・開発まで、すべて1台で完結する。
機械学習は使っていないので GPU は要らない (依存は requests / beautifulsoup4 /
feedparser と標準ライブラリだけ)。

### 用意

`local\setup_windows.bat` を**管理者として実行**する。
ライブラリとブラウザを入れ、毎時7分の収集をタスクに登録し、初回の収集まで走る。

### ふだん使うもの

| したいこと | すること |
|---|---|
| 手元で地図を見る | `local\serve.bat` |
| 地図を直す | `local\dev.bat` (保存 → ブラウザ再読み込みで反映) |
| いますぐ更新する | `python local\refresh.py --push` |
| この PC から公開する | `local\publish.bat` (cloudflared) |
| 様子を見る | `local\refresh.log` |

### 観測ログ

`ariake.db` はこの PC に残る。動かすほど平常値の精度が上がる。
GitHub Actions のキャッシュと違って揮発しないので、手元で動かす一番の利点。
リポジトリには入れない (`.gitignore`) ので、PC を移すときは手で持っていく。

### クラウドとの関係

定期収集は手元に移したので、`collect.yml` の `schedule` は止めてある。
両方が動くと `ariake.json` を取り合うため。
`--push` を付けて実行すると GitHub に反映され、GitHub Pages も更新される。
手元の PC を止めてクラウドに戻すときは、`collect.yml` の `schedule` の
コメントを外すだけでよい。
