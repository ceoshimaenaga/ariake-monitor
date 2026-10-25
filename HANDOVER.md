# 有明 混雑マップ — RTX機への引き継ぎ

最終更新: 2026-10-25 ／ 公開ページ: https://ceoshimaenaga.github.io/ariake-monitor/

このファイルだけ読めば、RTX機で全部動かせるようにしてある。
**なぜそうなっているか**（判断の経緯・捨てた案・踏んだ失敗）は [CONTEXT.md](CONTEXT.md) に別途ある。

---

## 1. これは何か

有明・豊洲・お台場の **31地点** の混雑を、いまと3日先まで、実際の地形の地図の上に出すサイト。
対象は有明の住民と、これから有明に行く人。

| 種別 | 数 | 例 |
|---|---|---|
| イベント会場 | 6 | 東京ビッグサイト、有明アリーナ、有明コロシアム |
| 周辺施設 | 20 | 有明ガーデン、がん研有明病院、ららぽーと豊洲 |
| 駅 | 4 | 国際展示場、有明、有明テニスの森、東京ビッグサイト |
| 道路 | 1 | 首都高有明/湾岸 |

**機械学習は使っていない。GPUは不要。** 依存は `requests` / `beautifulsoup4` / `feedparser` と
Python標準ライブラリだけ。やっているのは31地点×72時間ぶんの四則演算で、
ラズパイでも動く。RTX機を使うのは「1台で完結させたい」という理由であって、性能のためではない。

---

## 2. いまの運用体制

**収集はすべて RTX機 が担当する。クラウドの定期実行は全部止めてある。**

| やること | どこで | いつ |
|---|---|---|
| 混雑データの収集・予測 | **RTX機** | 毎時7分（タスクスケジューラ） |
| イベント表の読み取り（JS） | **RTX機** | `--render` を付けたときだけ |
| 公開ページの配信 | GitHub Pages | `--push` でGitHubに反映されると自動 |
| 観測ログの蓄積 | **RTX機** | `ariake.db`（永続） |

GitHub Actions のワークフローは5本とも **`schedule` をコメントアウト済み**。
手動実行（workflow_dispatch）だけ残してある。`pages.yml` だけは push で動くので、
RTX機が `--push` すれば公開ページが更新される。

> **なぜ止めたか**: RTX機とクラウドが両方毎時動くと `ariake.json` を取り合って衝突する。

---

## 3. RTX機でのセットアップ（初回だけ）

### 3-1. クローン

```
git clone https://github.com/ceoshimaenaga/ariake-monitor C:\dev\ariake-monitor
```

熱海モニターが `C:\dev\atami-monitor` なので、横に並べる想定。

### 3-2. 必要なもの

- **Python 3.10 以上** — インストール時に「Add python.exe to PATH」にチェック
- **Git** — クローンと push に使う
- **cloudflared**（任意）— この PC から直接公開したい場合のみ

### 3-3. セットアップ実行

`local\setup_windows.bat` を **管理者として実行**。以下が自動で走る。

1. `pip install -r requirements.txt`
2. `pip install playwright` → `playwright install chromium`（初回は数分）
3. タスクスケジューラに `AriakeMonitor_Collect` を登録（毎時7分）
4. 初回の収集を `--render` 付きで1回実行

### 3-4. GitHub への push 設定

`--push` を使うなら、Git の認証を通しておく。

```
git config --global user.name  "ceoshimaenaga"
git config --global user.email "ceoshimaenaga@gmail.com"
```

HTTPS なら初回 push でブラウザ認証が出る。通らなければ Personal Access Token を使う。

> **API キーは一切不要。** 有料APIは使っていないので、シークレットの設定は無い。

---

## 4. ふだん使うもの

| したいこと | すること |
|---|---|
| 手元で地図を見る | `local\serve.bat` → http://localhost:8787/ |
| **地図を直す** | `local\dev.bat` → 保存してブラウザ再読み込みで反映 |
| いますぐ更新して公開 | `python local\refresh.py --push` |
| イベント表も読み直す | `python local\refresh.py --push --render` |
| この PC から直接公開 | `local\publish.bat`（cloudflared） |
| 動いているか見る | `local\refresh.log` |
| タスクの状態を見る | `schtasks /Query /TN AriakeMonitor_Collect` |

### デザインを直すとき

原本は **`designs/5-atlas.html` の1枚だけ**。`local\dev.bat` はこれを直接配信するので、
保存 → ブラウザ再読み込みだけで反映される（ビルド不要）。
公開用の `index.html` は `ariake/build_site.py` がこれから生成するので、原本は二重に持っていない。

---

## 5. ファイルの地図

```
ariake-monitor/
├ ariake/
│  ├ collect.py        収集の入口。これを叩くと ariake.json ができる
│  ├ config.py         ★31地点の定義、イベント取得元、モデルの係数
│  ├ forecast.py       混雑予測のモデル本体
│  ├ render.py         JSで描かれるページを Playwright で読む
│  ├ build_site.py     公開用 _site/ を組み立てる
│  ├ fetch_basemap.py  OpenStreetMap から地形を取る
│  ├ locate.py         ★スポットの座標を実際の建物に合わせる
│  └ sources/          取得元ごとの処理（events / jma / odpt / routes …）
├ designs/
│  ├ 5-atlas.html      ★地図ページの原本。デザインはここだけ直せばいい
│  ├ basemap.json      OSM の地形（建物2,415 / 道路899 / 公園494 …）
│  └ icons/png/        建物イラスト11枚
├ local/               ★RTX機用。setup / refresh / serve / dev / publish
├ ariake-common.js     色・レベル・パーソナライズの共通処理
├ ariake-settings.js   「マイ設定」パネル
├ ariake.json          出力データ（これが公開される）
└ ariake.db            観測ログ（gitignore。この PC にだけ残る）
```

---

## 6. 混雑予測のモデル

```
混雑度 = 平常値 × 天候係数 × 祝日係数 + イベント負荷
```

- 来場者数を**入場カーブと退場カーブに分解**して時間ごとに割り振る
- **会場**は「滞在人数」、**駅と道路**は「通過する人の流れ」、**周辺施設**は
  「滞在人数＋イベント後の流入」として別々に扱う
- 会場から周辺への影響は**距離で減衰**させる（ガウス、推定なので上限あり）
- 巨大イベントは**軟飽和**させる（10万人でも線形には増えない）
- 同じ会場で複数の展示会が同時開催のときは、**会場の1日あたり上限**で圧縮する

係数は全部 `ariake/config.py` にある。いじるならそこ。

---

## 7. データの出どころ

| 種類 | 出どころ | 備考 |
|---|---|---|
| イベント予定 | 東京ビッグサイト / 有明コロシアム / 東京ガーデンシアター / 有明ガーデン | HTML直読み |
| 〃 | 有明アリーナ / 有明四季劇場 | **JSで描かれるので `--render` が要る** |
| 地形・建物・道路 | OpenStreetMap（ODbL） | `fetch_basemap.py`、滅多に変わらない |
| 天気 | Open-Meteo | 無料・キー不要 |

建物イラストは、それぞれの**実際の写真を参照して生成**したもの（Higgsfield）。
参照元の URL は `designs/refs/sources.json` に記録してある。

### 使っていないもの（有料なので）

- **BestTime.app** — Googleマップの「人気の時間帯」相当。実測の混雑が取れる。月数千円〜
- **Google Routes API** — 道路の実測所要時間
- **ODPT** — 運行情報。無料トークンだが未取得

`config.py` にコードは入っていて、環境変数を入れれば動く。
`BESTTIME_API_KEY` / `GOOGLE_MAPS_API_KEY` / `ODPT_TOKEN`。
**いまは全部未設定で、その分は「平常値ベースの推定」になっている。**

---

## 8. 残っている課題

### 8-1. 座標がまだ手入力の2件

| 施設 | 状況 |
|---|---|
| 有明GYM-EX | OSM に名前が無い。「GYM-EX」「有明体操」で検索して0件 |
| 有明四季劇場（春・秋） | 同上。「四季劇場」「劇団四季」で0件 |

拡大するとマーカーが数百mずれて見える。**推測で動かすより残してある。**

直す方法は2つ。

1. 正しい建物が分かるなら `ariake/config.py` の `lat` / `lng` を直接書き換える
2. OSM 自体に登録する → 次回 `locate.py --find` で自動的に拾える

他の29地点は実際の建物の輪郭に合わせ済み（最大1km ずれていたのを修正）。

### 8-2. Windows実機で未検証

`local\*.bat` は**この環境では実行できていない**（Linuxコンテナのため）。
`refresh.py` の通し実行だけは確認済み（収集→予測→サイト組み立てが成功）。
転んだら `local\refresh.log` を見る。

### 8-3. 観測ログがまだ浅い

`ariake.db` は gitignore なので、RTX機で**ゼロから貯め直しになる**。
貯まるほど平常値の精度が上がるので、動かし続けるほど良くなる。
（クラウドのキャッシュは揮発していたので、どのみち長期の蓄積は無かった）

---

## 9. 困ったとき

### 収集が失敗する

```
python ariake/collect.py
```
を直接叩いてエラーを見る。よくある原因は2つ。

- **施設側のページ構造が変わった** → `ariake/sources/events.py` の抽出ロジックを直す。
  `ariake/probe.py --dump <URL>` でページの中身を見られる
- **ネットワーク** → 社内プロキシ等

イベントが0件になった会場があれば、まずそこの公式サイトを人間の目で見る。

### 地図が真っ白

`designs/basemap.json` が壊れているか無い。
`python ariake/fetch_basemap.py` で取り直す。
**Overpass（OSMのAPI）は混雑時に 502/504 を返す。** ミラー4つを3周するようにしてあるが、
それでもダメな時間帯がある。時間を置けば通る。

### マーカーと建物がずれる

```
python ariake/locate.py              # ずれを一覧（ネット不要）
python ariake/locate.py --patch      # 直す
```

名寄せには落とし穴がある。過去に踏んだもの:

- 「イオン」で引くと有明のイオンスタイルを掴み、イオン東雲店が1.4km飛ぶ
- 「会議棟」が会議棟**地下駐車場**を掴む（地下の方が広いため）
- 「潮風公園」が潮風公園**案内図**を掴む

対策として**完全一致を最優先**し、**300㎡未満の輪郭は案内板扱い**にしてある。
新しい施設を足すときは `locate.py` の `MATCH` に追記する。

### クラウドに戻したい

各ワークフローの `schedule:` のコメントを外すだけ。
そのときは RTX機 のタスクを止める（`schtasks /Delete /TN AriakeMonitor_Collect /F`）。

---

## 10. 公開まわり

### いまの公開URL

**https://ceoshimaenaga.github.io/ariake-monitor/** — ログイン不要、誰でも見られる。
RTX機が `--push` するたびに `pages.yml` が走って更新される。

### この PC から直接公開する場合

`local\publish.bat` が熱海と同じ cloudflared 方式で書いてある。
想定URL は **`ariake.shukuhakudaichou.com`**。事前に一度だけ:

```
cloudflared tunnel login
cloudflared tunnel create ariake
cloudflared tunnel route dns ariake ariake.shukuhakudaichou.com
```

`%USERPROFILE%\.cloudflared\config.yml` に転送先 `http://localhost:8787` を書く。

> **両方残すのを勧める。** PC が落ちている間も GitHub Pages は生き続ける。

---

## 11. リポジトリの関係

| リポジトリ | 公開 | 中身 |
|---|---|---|
| `ceoshimaenaga/ariake-monitor` | **public** | この有明プロジェクト一式 |
| `ceoshimaenaga/atami-monitor` | private | 熱海モニター。有明の移行元（`ariake/` `designs/` が残っているが**こちらは古い**） |

有明の作業は**必ず `ariake-monitor` 側**でやる。`atami-monitor` の有明関連ワークフローは停止済み。

---

## 12. デザインについて

地図は4種類から選べる（ページ右上「デザイン」）。選択は端末に保存される。

| | 見た目 | 向いている場面 |
|---|---|---|
| 夜のベイ | ほぼ黒の地に青の混雑 | 既定。夜間・暗所 |
| 紙の地図 | 生成り色の紙に淡いグレーの水域 | 昼間・屋外 |
| レーダー | 黒紺＋シアンの海岸線 | 混雑の面が一番くっきり |
| **人流** | 建物と道路だけが光る | **人がどこにいるかが一番わかる** |

**人流だけ描き方が違う。** 他の3つは面（ガウス補間）だが、人流は
「人がいるのは建物の中と道の上」という考え方で、OSM の建物2,415棟と道路899本に**だけ**色を置く。
空き地や水面は塗らない。値も加重平均ではなく「人を送り込んでいる地点の混雑度を距離で減衰させた最大値」を使う。

色は CSS 変数（`--map-sea` など）に持たせて canvas が読む作りなので、
**5つ目を足すときも JS は触らなくていい**。`designs/5-atlas.html` の `:root[data-design="..."]` を増やすだけ。

建物イラストは「なし / 小 / 大」から選べる。既定は小。
