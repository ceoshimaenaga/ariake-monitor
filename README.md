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
