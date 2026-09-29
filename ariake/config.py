# -*- coding: utf-8 -*-
"""有明エリアの監視対象スポット定義・影響度マトリクス・各種事前分布。

ここを編集すればスポット追加・重み調整ができる (コード変更不要)。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 監視スポット
#   kind : venue(イベント会場) / facility(商業・公園) / station(駅) / road(道路)
#   scale: 「1時間あたり何人の流入でスコア100相当か」の換算分母。
#          駅は小さく(=少人数で詰まる)、大型施設は大きく設定。
#   place_query: Google Maps / Places API で引く際の検索語 (人気時間帯の取得用)
# ---------------------------------------------------------------------------
SPOTS: dict[str, dict] = {
    # ---- イベント会場 -----------------------------------------------------
    "bigsight": {
        "name": "東京ビッグサイト", "kind": "venue", "lat": 35.629794, "lng": 139.7941,
        "capacity": 120000, "scale": 30000, "default_attendance": 15000,
        "place_query": "東京ビッグサイト 東京国際展示場",
        "place_address": "東京都江東区有明3-11-1",
    },
    "ariake_arena": {
        "name": "有明アリーナ", "kind": "venue", "lat": 35.643423, "lng": 139.794382,
        "capacity": 15000, "scale": 6000, "default_attendance": 10000,
        "place_query": "有明アリーナ",
        "place_address": "東京都江東区有明1-11-1",
    },
    "ariake_coliseum": {
        "name": "有明コロシアム", "kind": "venue", "lat": 35.636468, "lng": 139.790089,
        "capacity": 10000, "scale": 5000, "default_attendance": 4000,
        "place_query": "有明コロシアム",
        "place_address": "東京都江東区有明2-2-22",
    },
    "garden_theater": {
        "name": "東京ガーデンシアター", "kind": "venue", "lat": 35.637732, "lng": 139.792032,
        "capacity": 8000, "scale": 4000, "default_attendance": 6000,
        "place_query": "東京ガーデンシアター",
        "place_address": "東京都江東区有明1-1-10",
    },
    "shiki_ariake": {
        "name": "有明四季劇場（春・秋）", "kind": "venue", "lat": 35.6356, "lng": 139.7917,
        "capacity": 1200, "scale": 1500, "place_query": "有明四季劇場",
        "place_address": "東京都江東区有明1-1-10",
    },
    "gymex": {
        "name": "有明GYM-EX", "kind": "venue", "lat": 35.6343, "lng": 139.7963,
        "capacity": 5000, "scale": 3000, "place_query": "有明GYM-EX",
        "place_address": "東京都江東区有明1-10-1",
    },
    # ---- 周辺施設 ---------------------------------------------------------
    "ariake_garden": {
        "name": "有明ガーデン", "kind": "facility", "lat": 35.638418, "lng": 139.79307,
        "capacity": 40000, "scale": 9000, "default_attendance": 6000,
        "place_query": "有明ガーデン",
        "place_address": "東京都江東区有明2-1-8",
    },
    "ariake_tennis_forest": {
        "name": "有明テニスの森公園", "kind": "facility", "lat": 35.635318, "lng": 139.788203,
        "capacity": 8000, "scale": 4000, "baseline_scale": 0.35,
        "place_query": "有明テニスの森公園",
        "place_address": "東京都江東区有明2-2-22",
    },
    "toyosu_market": {
        "name": "豊洲市場・千客万来", "kind": "facility", "lat": 35.645458, "lng": 139.783657,
        "capacity": 30000, "scale": 7000, "baseline_scale": 0.85,
        "place_query": "豊洲市場 千客万来",
        "place_address": "東京都江東区豊洲6-5-1",
    },
    "odaiba": {
        "name": "お台場（アクアシティ／ダイバーシティ）", "kind": "facility",
        "lat": 35.6255, "lng": 139.7756, "capacity": 60000, "scale": 12000,
        "place_query": "ダイバーシティ東京プラザ",
        "place_address": "東京都江東区青海1-1-10",
    },
    # ---- 追加: 有明・東雲の生活/レジャー施設 -------------------------------
    "aeon_ariake": {
        "name": "イオンスタイル有明ガーデン", "kind": "facility",
        "lat": 35.638418, "lng": 139.79307, "capacity": 12000, "scale": 4000,
        "place_query": "イオンスタイル有明ガーデン",
        "place_address": "東京都江東区有明2-1-8",
    },
    "izumi_spa": {
        "name": "泉天空の湯 有明ガーデン", "kind": "facility",
        "lat": 35.638271, "lng": 139.791547, "capacity": 2000, "scale": 1200,
        "baseline_scale": 0.7, "spillover_scale": 0.4,
        "place_query": "泉天空の湯 有明ガーデン",
        "place_address": "東京都江東区有明2-1-7",
    },
    "ganken_ariake": {
        "name": "がん研有明病院", "kind": "facility",
        "lat": 35.634059, "lng": 139.794921, "capacity": 6000, "scale": 2500,
        "baseline_scale": 0.8, "spillover_scale": 0.15,
        "place_query": "がん研有明病院",
        "place_address": "東京都江東区有明3-8-31",
    },
    "ariake_sports": {
        "name": "有明スポーツセンター", "kind": "facility",
        "lat": 35.63317, "lng": 139.783725, "capacity": 2000, "scale": 1200,
        "baseline_scale": 0.5, "spillover_scale": 0.25,
        "place_query": "東京都 有明スポーツセンター",
        "place_address": "東京都江東区有明1-11-1",
    },
    "aeon_shinonome": {
        "name": "イオン東雲店", "kind": "facility",
        "lat": 35.648809, "lng": 139.802291, "capacity": 10000, "scale": 3500,
        "spillover_scale": 0.35,
        "place_query": "イオン東雲店", "place_address": "東京都江東区辰巳3-3-6",
    },
    # ---- 追加: 豊洲 -------------------------------------------------------
    "lalaport_toyosu": {
        "name": "ららぽーと豊洲", "kind": "facility",
        "lat": 35.655396, "lng": 139.792294, "capacity": 45000, "scale": 10000,
        "place_query": "アーバンドック ららぽーと豊洲",
        "place_address": "東京都江東区豊洲2-4-9",
    },
    "kidzania": {
        "name": "キッザニア東京", "kind": "facility",
        "lat": 35.655396, "lng": 139.792294, "capacity": 3000, "scale": 1500,
        "spillover_scale": 0.3,
        "place_query": "キッザニア東京", "place_address": "東京都江東区豊洲2-4-9",
    },
    "teamlab_planets": {
        "name": "チームラボプラネッツ TOKYO", "kind": "facility",
        "lat": 35.649274, "lng": 139.78971, "capacity": 6000, "scale": 2500,
        "place_query": "チームラボプラネッツ TOKYO",
        "place_address": "東京都江東区豊洲6-1-16",
    },
    "toyosu_gururi": {
        "name": "豊洲ぐるり公園", "kind": "facility",
        "lat": 35.64517, "lng": 139.785054, "capacity": 5000, "scale": 2500,
        "baseline_scale": 0.35, "place_query": "豊洲ぐるり公園",
        "place_address": "東京都江東区豊洲6-4",
    },
    # ---- 追加: お台場・青海 -----------------------------------------------
    "aquacity": {
        "name": "アクアシティお台場", "kind": "facility",
        "lat": 35.62778, "lng": 139.773512, "capacity": 35000, "scale": 8000,
        "place_query": "アクアシティお台場", "place_address": "東京都港区台場1-7-1",
    },
    "decks": {
        "name": "デックス東京ビーチ", "kind": "facility",
        "lat": 35.629048, "lng": 139.775901, "capacity": 25000, "scale": 6000,
        "place_query": "デックス東京ビーチ", "place_address": "東京都港区台場1-6-1",
    },
    "fujitv": {
        "name": "フジテレビ本社", "kind": "facility",
        "lat": 35.626775, "lng": 139.774433, "capacity": 8000, "scale": 3000,
        "place_query": "フジテレビ本社ビル", "place_address": "東京都港区台場2-4-8",
    },
    "miraikan": {
        "name": "日本科学未来館", "kind": "facility",
        "lat": 35.619282, "lng": 139.776707, "capacity": 6000, "scale": 2500,
        "place_query": "日本科学未来館", "place_address": "東京都江東区青海2-3-6",
    },
    "odaiba_beach": {
        "name": "お台場海浜公園", "kind": "facility",
        "lat": 35.631079, "lng": 139.773665, "capacity": 20000, "scale": 5000,
        "baseline_scale": 0.55, "place_query": "お台場海浜公園",
        "place_address": "東京都港区台場1-4",
    },
    "shiokaze": {
        "name": "潮風公園", "kind": "facility",
        "lat": 35.62266, "lng": 139.769984, "capacity": 8000, "scale": 3000,
        "baseline_scale": 0.35, "place_query": "潮風公園",
        "place_address": "東京都品川区東八潮1-2",
    },
    "cruise_terminal": {
        "name": "東京国際クルーズターミナル", "kind": "facility",
        "lat": 35.6180, "lng": 139.7720, "capacity": 5000, "scale": 2000,
        "baseline_scale": 0.3, "spillover_scale": 0.3,
        "place_query": "東京国際クルーズターミナル",
        "place_address": "東京都江東区青海2-6-3",
    },
    # ---- 駅 ---------------------------------------------------------------
    "st_tokyo_bigsight": {
        "name": "東京ビッグサイト駅（ゆりかもめ）", "kind": "station",
        "lat": 35.6300, "lng": 139.7930, "scale": 4000,
        "odpt_station": "odpt.Station:Yurikamome.Yurikamome.TokyoBigSight",
        "place_query": "東京ビッグサイト駅", "besttime": False,
    },
    "st_kokusai_tenjijo": {
        "name": "国際展示場駅（りんかい線）", "kind": "station",
        "lat": 35.6349, "lng": 139.7949, "scale": 5000,
        "odpt_station": "odpt.Station:TWR.Rinkai.KokusaiTenjijo",
        "place_query": "国際展示場駅", "besttime": False,
    },
    "st_ariake": {
        "name": "有明駅（ゆりかもめ）", "kind": "station",
        "lat": 35.6356, "lng": 139.7924, "scale": 2500,
        "odpt_station": "odpt.Station:Yurikamome.Yurikamome.Ariake",
        "place_query": "有明駅 ゆりかもめ", "besttime": False,
    },
    "st_ariake_tennis": {
        "name": "有明テニスの森駅（ゆりかもめ）", "kind": "station",
        "lat": 35.6331, "lng": 139.7959, "scale": 2500,
        "odpt_station": "odpt.Station:Yurikamome.Yurikamome.AriakeTennisNoMori",
        "place_query": "有明テニスの森駅", "besttime": False,
    },
    # ---- 道路 (Routes API の所要時間で混雑を代理観測) -----------------------
    "road_ariake": {
        "name": "有明周辺道路（首都高有明/湾岸）", "kind": "road",
        "lat": 35.6340, "lng": 139.7940, "scale": 9000,
        "route": {  # 東京駅 → 東京ビッグサイト
            "origin": "35.6812,139.7671", "destination": "35.6298,139.7950",
            "free_flow_min": 22,
        },
    },
}

# ---------------------------------------------------------------------------
# 影響度マトリクス: 会場でイベントがあると、各スポットがどれだけ影響を受けるか。
#   venue_id -> {spot_id: weight}
#   weight は「そのイベント来場者のうち、何割がそのスポットの負荷になるか」の目安。
# ---------------------------------------------------------------------------
INFLUENCE: dict[str, dict[str, float]] = {
    "bigsight": {
        "bigsight": 1.00, "st_tokyo_bigsight": 0.42, "st_kokusai_tenjijo": 0.38,
        "st_ariake": 0.06, "ariake_garden": 0.14, "road_ariake": 0.55,
        "odaiba": 0.08, "toyosu_market": 0.04, "ariake_tennis_forest": 0.03,
    },
    "ariake_arena": {
        "ariake_arena": 1.00, "st_ariake": 0.34, "st_tokyo_bigsight": 0.22,
        "st_kokusai_tenjijo": 0.20, "ariake_garden": 0.40, "road_ariake": 0.45,
        "st_ariake_tennis": 0.10,
    },
    "ariake_coliseum": {
        "ariake_coliseum": 1.00, "st_ariake_tennis": 0.45, "st_ariake": 0.18,
        "st_kokusai_tenjijo": 0.14, "ariake_garden": 0.22, "road_ariake": 0.35,
        "ariake_tennis_forest": 0.30,
    },
    "garden_theater": {
        "garden_theater": 1.00, "st_ariake": 0.30, "st_tokyo_bigsight": 0.24,
        "st_kokusai_tenjijo": 0.22, "ariake_garden": 0.38, "road_ariake": 0.35,
    },
    "shiki_ariake": {
        "shiki_ariake": 1.00, "st_ariake": 0.35, "ariake_garden": 0.45,
        "st_kokusai_tenjijo": 0.12, "road_ariake": 0.15,
    },
    "gymex": {
        "gymex": 1.00, "st_ariake": 0.22, "st_tokyo_bigsight": 0.20,
        "ariake_garden": 0.25, "road_ariake": 0.25,
    },
    "ariake_tennis_forest": {
        "ariake_tennis_forest": 1.00, "st_ariake_tennis": 0.40, "road_ariake": 0.15,
    },
}

# ---------------------------------------------------------------------------
# 事前分布 (観測データが溜まるまでの初期値)
#   BASELINE[kind][平日=0/土日祝=1] = 0時〜23時の素の混雑スコア
# ---------------------------------------------------------------------------
BASELINE: dict[str, list[list[float]]] = {
    "station": [
        [0, 0, 0, 0, 0, 2, 10, 26, 40, 30, 18, 16, 18, 16, 15, 17, 24, 34, 38, 28, 18, 12, 6, 2],
        [0, 0, 0, 0, 0, 1, 3, 7, 14, 22, 28, 30, 30, 28, 27, 28, 30, 32, 30, 24, 16, 10, 5, 1],
    ],
    "facility": [
        [0, 0, 0, 0, 0, 0, 2, 5, 8, 14, 22, 32, 38, 36, 32, 32, 34, 36, 34, 28, 18, 8, 2, 0],
        [0, 0, 0, 0, 0, 0, 1, 3, 6, 14, 28, 42, 52, 54, 50, 48, 48, 46, 40, 32, 20, 9, 2, 0],
    ],
    "venue": [
        [0] * 24,
        [0] * 24,
    ],
    "road": [
        [4, 2, 2, 2, 3, 6, 14, 26, 34, 30, 26, 26, 26, 24, 26, 30, 36, 42, 40, 32, 22, 14, 9, 6],
        [4, 3, 2, 2, 2, 3, 6, 10, 16, 24, 30, 34, 34, 32, 32, 34, 38, 38, 34, 26, 18, 12, 8, 5],
    ],
}

# ---------------------------------------------------------------------------
# イベント規模の推定
#   キーワード → (推定来場者数/日, ラベル)。上から順に最初にマッチしたものを採用。
#   数値は公表実績・報道ベースのおおよその上限値で、あくまで“見込み”。
# ---------------------------------------------------------------------------
EVENT_SCALE_KEYWORDS: list[tuple[tuple[str, ...], int, str]] = [
    # --- 小規模 (商業施設の館内催事)。上に置いて先にマッチさせる ---
    (("POP-UP", "POPUP", "ポップアップ"), 1200, "館内ポップアップ"),
    (("ライトアップ", "点灯式", "キャンペーン"), 800, "館内キャンペーン"),
    (("リリースイベント", "サイン会", "握手会", "トークショー"), 2000, "リリースイベント"),
    (("パブリックビューイング", "ビューイング"), 3000, "パブリックビューイング"),
    (("コミックマーケット", "コミケ"), 180000, "超大型同人イベント"),
    (("ジャパンモビリティショー", "東京モーターショー"), 100000, "超大型展示会"),
    (("東京ゲームショウ",), 80000, "超大型展示会"),
    (("AnimeJapan", "アニメジャパン"), 70000, "超大型展示会"),
    (("キャラクター・ブランド", "ライセンシング"), 35000, "大型展示会"),
    (("ギフト・ショー", "ギフトショー"), 60000, "大型展示会"),
    (("FOODEX", "フーデックス"), 45000, "大型展示会"),
    (("コミティア", "コミックシティ", "サンクリ", "オンリー"), 30000, "同人イベント"),
    (("フリーマーケット", "物産展", "フェス", "フェスタ"), 25000, "一般向けイベント"),
    (("博覧会", "総合展", "展示会", "EXPO", "見本市", "フェア", "ショー", "展"),
     20000, "展示会(BtoB)"),
    (("学会", "大会", "総会", "カンファレンス", "セミナー"), 6000, "学会・会議"),
    (("説明会", "就活", "採用"), 8000, "説明会"),
    (("試験", "検定"), 5000, "試験"),
    (("コンサート", "ライブ", "LIVE", "ツアー", "公演"), 0, "公演 (会場定員基準)"),
]

# 会場定員に対する平均充足率 (公演系はここから来場者を推定)
DEFAULT_FILL_RATE = 0.85

# 1会場1日あたりの来場者合計の上限 (定員に対する比率)。
# 東京ビッグサイトの「◯◯DX EXPO」群のように同時開催が何本も並ぶと
# 単純合計が非現実的になるため、この上限に収まるよう按分して圧縮する。
VENUE_DAILY_CAP_RATIO = 0.5

# ---------------------------------------------------------------------------
# 天候の効き方 (kind別の係数)
#   雨・雪は屋外/駅の滞留を増やし、商業施設は屋内需要で微増、公園は大幅減。
# ---------------------------------------------------------------------------
WEATHER_FACTOR = {
    "rain":   {"station": 1.08, "facility": 1.05, "venue": 0.97, "road": 1.18},
    "heavy":  {"station": 1.15, "facility": 0.95, "venue": 0.90, "road": 1.30},
    "snow":   {"station": 1.20, "facility": 0.85, "venue": 0.80, "road": 1.45},
    "hot":    {"station": 1.05, "facility": 1.10, "venue": 1.00, "road": 1.05},
    "clear":  {"station": 1.00, "facility": 1.00, "venue": 1.00, "road": 1.00},
}
PARK_RAIN_FACTOR = 0.45      # 屋外公園系は雨で大きく減る

# イベント負荷のソフト飽和: これを超えた分は圧縮して加算する。
# コミケ級 (10万人規模) でも 100 に張り付かせず、規模差を残すための措置。
EVENT_SOFT_KNEE = 60.0
EVENT_SOFT_RANGE = 40.0
EVENT_SOFT_TAU = 80.0

# 土日祝・連休の係数 (facility/station の baseline は曜日別なので上乗せ分のみ)
HOLIDAY_BOOST = 1.12
LONG_WEEKEND_BOOST = 1.20

# 予測を何時間先まで出すか
FORECAST_HOURS = 24 * 7


# ---------------------------------------------------------------------------
# イベントスケジュールの取得先
#   month_param: 月送りのクエリ (…?ym=202610 等)。{ym} が YYYYMM に置換される。
#   スクレイパは JSON-LD(schema.org/Event) → ヒューリスティック解析 の順に試す。
#   サイト改修で取れなくなっても collect は止まらず、warnings に記録される。
# ---------------------------------------------------------------------------
EVENT_SOURCES: list[dict] = [
    {"venue": "bigsight", "label": "東京ビッグサイト 公式イベントカレンダー",
     "urls": ["https://www.bigsight.jp/visitor/event/"],
     "month_param": "https://www.bigsight.jp/visitor/event/?ym={ym}",
     "months": 3, "default_open": "10:00", "default_end": "17:00"},

    # 有明コロシアム/有明テニスの森は東京港埠頭(海上公園なび)が一覧を出している
    {"venue": "ariake_coliseum", "label": "有明コロシアム/テニスの森 イベント情報",
     "urls": ["https://www.tptc.co.jp/park/03_08/event"],
     "months": 2, "default_open": "11:00", "default_end": "18:00"},

    # 東京ガーデンシアター・有明ガーデンはいずれも住友不動産のサイト配下。
    # (tokyo-gardentheater.com / ariake-garden.com はDNS解決できず、誤りだった)
    {"venue": "garden_theater", "label": "東京ガーデンシアター 開催予定のイベント",
     "urls": ["https://www.shopping-sumitomo-rd.com/tokyo_garden_theater/schedule/"],
     "months": 2, "default_open": "17:00", "default_end": "20:30"},

    {"venue": "ariake_garden", "label": "有明ガーデン イベント",
     "urls": ["https://www.shopping-sumitomo-rd.com/ariake/event/"],
     "months": 2, "default_open": "11:00", "default_end": "18:00"},

    # --- ここから下は JavaScript 描画が必要 (render: True) ---------------
    # 単純なHTTP取得では中身が空になるため、ariake/render.py が実ブラウザで
    # 描画して rendered_events.json に書き出す。毎時の収集はその結果を読む。
    {"venue": "ariake_arena", "label": "有明アリーナ イベント (要描画)",
     "urls": ["https://ariake-arena.tokyo/event/"], "render": True,
     "default_open": "17:00", "default_end": "20:30"},

    {"venue": "shiki_ariake", "label": "有明四季劇場 (要描画)",
     "urls": ["https://www.shiki.jp/theatres/4026/"], "render": True,
     "default_open": "12:30", "default_end": "16:00"},

    # 有明GYM-EX は単独のイベントページが存在しないため manual_events.json で補う
]

# ---------------------------------------------------------------------------
# BestTime.app (混雑実測) の呼び出し制御
#   クレジット課金なので「いつ・どれだけ叩くか」をここで完全に制御する。
#   既定: 11〜21時 / 2時間おき / 対象は施設・会場のみ (駅は精度が出ないため除外)
#   → 1日6回 × 対象数。平常カーブ(forecast)は週1回だけ取り直す。
# ---------------------------------------------------------------------------
BESTTIME = {
    "hours": (11, 21),          # JST の対象時間帯 (両端を含む)
    "interval_hours": 2,        # live を引く間隔。11,13,15,17,19,21時に実行
    "forecast_every_days": 7,   # 平常カーブの取り直し間隔 (日)
    "monthly_credit_cap": 6000, # 月間の上限リクエスト数。超えたら自動停止
    "kinds": ("facility", "venue"),
}

# ---------------------------------------------------------------------------
# 波及率の既定値 (INFLUENCE に明示されていない施設向け)
#   会場からの距離で減衰させる。「ビッグサイトで大型展示会 → ららぽーと豊洲にも
#   少し波及」のような効果を、全組み合わせを手書きせずに表現するための仕組み。
# ---------------------------------------------------------------------------
SPILLOVER_BASE = 0.18       # 距離0kmでの波及率
SPILLOVER_DECAY_KM = 1.2    # 減衰の距離定数
SPILLOVER_MAX = 0.15        # 上限
SPILLOVER_MIN = 0.01        # これ未満は無視 (計算を軽くする)
# 距離ベースの波及はあくまで推測なので、1イベントあたりの上乗せに上限を設ける。
# (INFLUENCE に明示した組み合わせにはこの上限はかからない)
SPILLOVER_MAX_POINTS = 30.0
# 個々の施設は spots["<id>"]["spillover_scale"] で更に増減できる
# (病院・クルーズターミナルなど、イベント客を吸収しにくい施設を弱める用途)

# ODPT(公共交通オープンデータ) で監視する事業者・路線
ODPT_OPERATORS = [
    {"operator": "odpt.Operator:Yurikamome", "label": "ゆりかもめ"},
    {"operator": "odpt.Operator:TWR", "label": "りんかい線"},
    {"operator": "odpt.Operator:JR-East", "label": "JR東日本", "railways":
     ["odpt.Railway:JR-East.Keiyo"]},
    {"operator": "odpt.Operator:TokyoMetro", "label": "東京メトロ", "railways":
     ["odpt.Railway:TokyoMetro.Yurakucho"]},
]

# 運行トラブルが駅の混雑スコアに与える上乗せ (points)
TRANSIT_PENALTY = {"運転見合わせ": 30, "運休": 25, "遅延": 12, "直通運転中止": 8}
