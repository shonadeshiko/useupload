"""
SSP人口メッシュ統合パイプライン (4/4) — 多摩川流域メッシュにSSP別人口トレンドを結合する

【背景・方針(重要・要開示)】
SSP別に完全差別化された人口メッシュデータ(国立環境研究所「SSP別1kmメッシュ別将来推計人口」)は
A-PLATの利用申請フォーム経由でのみ入手可能で、承認までのリードタイムが不明(2026-08-04時点、
[[projects/流域スケール自然資本評価/00-研究構想]] 参照)。ハッカソンの期限(8/30)には
申請から入手までを組み込めないため、本スクリプトでは以下の**代替・近似手法**を用いる。

【代替手法(一次資料に基づく、捏造ではない)】
1. ベースライン人口トレンドには、**申請不要で即入手可能な**
   国土数値情報「500mメッシュ別将来推計人口データ(H30国政局推計)」を用いる。
   これは国立社会保障・人口問題研究所(社人研)の地域別将来推計人口に基づく中位推計であり、
   日本版SSPマニュアル(第2版)が「SSP2の推計用出生率として社人研地域推計で用いられている
   出生率を用い」と明記している通り、**SSP2にほぼ相当する基準シナリオ**として扱える。
2. SSP1-2.6 / SSP5-8.5 相当の傾向は、日本版SSPマニュアル(第2版)の**表-7(地域区分ごとのSSP2比、
   2050年)** に示された、地域区分(大都市圏市街地/大都市圏非市街地/地方圏市街地/地方圏非市街地)
   ごとの全国集計値の変化率を、該当する市区町村に**一律で適用**する近似を用いる。
   出典: 国立環境研究所 日本版SSP開発チーム(2021)「日本版SSP市区町村別人口推計について(第2版)」
   https://adaptation-platform.nies.go.jp/data/socioeconomic/pdf/population_manual_v2.pdf
   表-6(地域区分ごとの総人口)・表-7(地域区分ごとのSSP2比)を出典として2026-08-05に一次確認
   （表-6の絶対値からTable-7のパーセンテージを逆算し、一致することをクロスチェック済み）。
3. 🔴 **これは全国集計値を局所メッシュへ適用する近似であり、多摩川流域固有のSSP別人口推計ではない。**
   本物のSSP別1kmメッシュデータが入手できた場合は本スクリプトの§2を差し替えること。

【市区町村の地域区分分類(一次資料に基づく)】
日本版SSPマニュアル(第2版) 表-4「自治体の4地域区分への分類結果」より、多摩川流域に関連する
市区町村を抽出・転記(2026-08-05)。JISコードは総務省「全国地方公共団体コード」
(https://nlftp.mlit.go.jp/ksj/gml/codelist/AdminiBoundary_CD.xlsx)と突合して付与。

【入力】
- tama_mesh_final.geojson (03の出力)
- 500m_mesh_2018_13.dbf (国土数値情報500mメッシュ別将来推計人口, 東京都, H30国政局推計)
  ダウンロードURL: https://nlftp.mlit.go.jp/ksj/gml/data/m500h30/m500h30-18/500m_mesh_suikei_2018_shape_13.zip

【出力】
- tama_compact_v2.json: 人口トレンド(基準/SSP1-2.6近似/SSP5-8.5近似)を追加したダッシュボード用JSON
"""
import geopandas as gpd
import pyogrio
import json
import os

# データ配置: このスクリプトから見て ../data/ 以下に配置しておくこと。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')

MESH_FINAL_PATH = os.path.join(DATA_DIR, 'w12', 'tama_mesh_final.geojson')
POP_MESH_PATH = os.path.join(DATA_DIR, 'pop500', '13', '500m_mesh_2018_13.dbf')
OUT_COMPACT = os.path.join(DATA_DIR, 'w12', 'tama_compact_v2.json')

YEARS = [2020, 2025, 2030, 2035, 2040, 2045, 2050]

# 市区町村の地域区分(日本版SSPマニュアル第2版 表-4、2026-08-05 一次確認・転記)
# A = 大都市圏市街地 / B = 大都市圏非市街地 / C = 地方圏非市街地(山梨県側、参考)
CATEGORY_A_URBAN = {  # 大都市圏市街地
    13101, 13102, 13103, 13104, 13105, 13106, 13107, 13108, 13109, 13110,
    13111, 13112, 13113, 13114, 13115, 13116, 13117, 13118, 13119, 13120,
    13121, 13122, 13123,  # 特別区
    13201, 13202, 13203, 13204, 13206, 13207, 13208, 13209, 13210, 13211,
    13212, 13213, 13214, 13215, 13218, 13219, 13220, 13221, 13222, 13223,
    13224, 13225, 13227, 13229,  # 多摩地域の市部
}
CATEGORY_B_METRO_NONURBAN = {13205, 13228, 13303, 13305, 13307, 13308}  # 大都市圏非市街地
CATEGORY_C_REGIONAL_NONURBAN = {19442, 19443}  # 地方圏非市街地(山梨県 小菅村・丹波山村)

# 日本版SSPマニュアル第2版 表-7「地域区分ごとのSSP2比」(2050年、全国集計値)
# 2026-08-05 一次確認。表-6の絶対値(百万人)から逆算し整合性をクロスチェック済み。
SSP2050_RATIO_VS_SSP2 = {
    'A': {'ssp1': 0.058, 'ssp5': 0.114},   # 大都市圏市街地: SSP1 +5.8%, SSP5 +11.4%
    'B': {'ssp1': 0.000, 'ssp5': 0.078},   # 大都市圏非市街地: SSP1 +0.0%, SSP5 +7.8%
    'C': {'ssp1': -0.070, 'ssp5': -0.001}, # 地方圏非市街地: SSP1 -0.7%, SSP5 -0.1%(表-7より)
    'other': {'ssp1': 0.0, 'ssp5': 0.0},   # 分類外(念のためのフォールバック。本流域では使用しない想定)
}


def classify(shicode):
    if shicode in CATEGORY_A_URBAN:
        return 'A'
    if shicode in CATEGORY_B_METRO_NONURBAN:
        return 'B'
    if shicode in CATEGORY_C_REGIONAL_NONURBAN:
        return 'C'
    return 'other'


def ssp_multiplier(category, scenario, year):
    """2020年を起点に、2050年時点の表-7比率まで線形補間する(簡易近似・要開示)。"""
    if year <= 2020:
        return 1.0
    ratio = SSP2050_RATIO_VS_SSP2[category][scenario]
    frac = min(1.0, (year - 2020) / (2050 - 2020))
    return 1.0 + ratio * frac


def main():
    mesh = gpd.read_file(MESH_FINAL_PATH)
    pop = pyogrio.read_dataframe(POP_MESH_PATH, encoding='cp932')
    pop_cols = ['MESH_ID', 'SHICODE'] + [f'PTN_{y}' for y in YEARS]
    pop = pop[pop_cols].copy()
    pop['MESH_ID'] = pop['MESH_ID'].astype('int64')
    mesh['code'] = mesh['code'].astype('int64')

    merged = mesh.merge(pop, left_on='code', right_on='MESH_ID', how='left')
    n_matched = merged['SHICODE'].notna().sum()
    print(f'人口データが結合できたメッシュ数: {n_matched} / {len(merged)}')
    print('(結合できなかったメッシュは人口記録なし=森林・無人地帯等と推定、人口0として扱う)')

    merged['category_own'] = merged['SHICODE'].apply(lambda s: classify(int(s)) if pop_notna(s) else None)

    # 【要開示】人口記録の無いメッシュ(主に森林・山間部)には、その地域の「管理放棄圧」の
    # 代理指標として、最も近い有人メッシュの地域区分を割り当てる(=同じ市区町村内にある
    # 可能性が高いという空間的近接性による近似)。森林の管理放棄は林業従事者の減少、
    # すなわち周辺コミュニティの人口動態に規定されるという想定に基づく。
    has_cat = merged[merged['category_own'].notna()].copy()
    no_cat = merged[merged['category_own'].isna()].copy()
    if len(no_cat) > 0 and len(has_cat) > 0:
        nearest = gpd.sjoin_nearest(
            no_cat[['code', 'geometry']].to_crs('EPSG:6677'),
            has_cat[['code', 'category_own', 'geometry']].to_crs('EPSG:6677').rename(columns={'code': 'code_ref'}),
            how='left',
        )
        nearest = nearest.drop_duplicates(subset='code')
        proxy_map = dict(zip(nearest['code'], nearest['category_own']))
        merged['category'] = merged.apply(
            lambda r: r['category_own'] if pop_notna(r['category_own']) else proxy_map.get(r['code'], 'other'),
            axis=1,
        )
        merged['category_is_proxy'] = merged['category_own'].isna()
    else:
        merged['category'] = merged['category_own']
        merged['category_is_proxy'] = False

    print(f'うち近隣メッシュから地域区分を代理割当したメッシュ数: {merged["category_is_proxy"].sum()}')

    cat_counts = merged['category'].value_counts()
    print('地域区分別メッシュ数:')
    print(cat_counts)

    # 検算: 流域全体の基準人口トレンド(2020→2050)
    for y in YEARS:
        total = merged[f'PTN_{y}'].fillna(0).sum()
        print(f'{y}年 基準人口合計(推定): {total:,.0f}人')

    # コンパクトJSON化
    merged['cx'] = merged.geometry.centroid.x
    merged['cy'] = merged.geometry.centroid.y

    # 【重要な設計判断・要開示】
    # 出力する人口系列は「実人数」ではなく「2020年を1.0とした指数(ratio)」にする。
    # 理由: 人口記録の無いメッシュ(森林・山間部、2,315件)は実人口が0のため、
    # 倍率をそのまま掛けても0のままで意味のある信号にならない(実装時に発見・修正した不具合)。
    # 指数化すれば、実人口を持つメッシュは「実測トレンド」、実人口の無いメッシュ(森林等)は
    # 「地域区分の全国集計トレンドをそのまま指数として使う」という扱いに統一でき、
    # どちらも「その地域の管理主体(住民・林業従事者等)がどれだけ増減する見込みか」という
    # 一貫した意味を持つ指標になる。ダッシュボード側は、この指数の増減を土地利用変化の
    # 圧力(開発圧・管理放棄圧)に変換する。
    rows = []
    for _, r in merged.iterrows():
        cat = r['category']
        # 【要開示】PTN_2020が1人未満の極小メッシュは、分母が小さすぎて比率が不安定
        # (例: 1.94人→0人のような急変が、たった1世帯の転出等で起こりうる)なため、
        # 「実人口データあり」とは扱わず、地域区分の指数(より安定した代理指標)にフォールバックする。
        has_local_pop = pop_notna(r['category_own']) and pop_notna(r['PTN_2020']) and float(r['PTN_2020']) >= 1.0

        if has_local_pop:
            base_2020 = float(r['PTN_2020'])
            idx_base = {y: float(r[f'PTN_{y}']) / base_2020 for y in YEARS}
        else:
            idx_base = {y: 1.0 for y in YEARS}  # 実人口なし: 基準指数は常に1.0(地域トレンドのみで動かす)

        idx_ssp1 = {y: idx_base[y] * ssp_multiplier(cat, 'ssp1', y) if cat in ('A', 'B', 'C') else idx_base[y] for y in YEARS}
        idx_ssp5 = {y: idx_base[y] * ssp_multiplier(cat, 'ssp5', y) if cat in ('A', 'B', 'C') else idx_base[y] for y in YEARS}

        rows.append([
            int(r['code']), round(float(r['cx']), 5), round(float(r['cy']), 5),
            round(float(r['f0_2022']), 4) if pop_notna(r['f0_2022']) else None,
            round(float(r['area_urban_pct']), 2), round(float(r['area_crop_pct']), 2),
            round(float(r['area_grass_pct']), 2), round(float(r['area_forest_pct']), 2),
            round(float(r['area_water_pct']), 2),
            round(float(r['es_value_2022']), 0) if pop_notna(r['es_value_2022']) else None,
            round(float(r['land_price_2022']), 0) if pop_notna(r['land_price_2022']) else None,
            cat,
            bool(has_local_pop),
            [round(idx_base[y], 4) for y in YEARS],
            [round(idx_ssp1[y], 4) for y in YEARS],
            [round(idx_ssp5[y], 4) for y in YEARS],
        ])

    out = {
        "meta": {
            "source": "JAXA HRLULC 2022 + Pricedata ES/地価 + 国土数値情報W12流域界(多摩川水系83030) + "
                       "国土数値情報500mメッシュ別将来推計人口(H30国政局推計) + "
                       "日本版SSPマニュアル第2版 表-6/7(地域区分別・全国集計値)による近似補正",
            "n_mesh": len(rows),
            "years": YEARS,
            "columns": ["code", "cx", "cy", "f0_2022", "urban_pct", "crop_pct", "grass_pct",
                        "forest_pct", "water_pct", "es_value_2022", "land_price_2022",
                        "pop_category", "pop_has_local_data",
                        "pop_index_baseline_series", "pop_index_ssp1_26_series", "pop_index_ssp5_85_series"],
            "bounds": merged.total_bounds.tolist(),
            "crosswalk_note": "JAXA分類->告示521号カテゴリの対応は外部脳の解釈。告示に直接の対応表はない。",
            "ssp_note": "人口系列は「2020年=1.0」の指数(実人数ではない)。実人口記録のあるメッシュは"
                        "国土数値情報500mメッシュ将来推計人口(H30国政局推計、社人研中位推計相当)の実測トレンドを、"
                        "実人口記録の無いメッシュ(森林・山間部、地域区分による代理推定)は"
                        "日本版SSPマニュアル第2版 表-7の地域区分別・全国集計SSP2比(2050年線形補間)を"
                        "指数1.0からの推移として用いている。多摩川流域固有のSSP別メッシュ推計ではなく、"
                        "全国集計値の局所適用という近似であることに留意。"
                        "本物の1kmメッシュSSPデータ(A-PLAT申請制、DIAS停止中)が入手でき次第、差し替えを推奨。",
            "ssp2050_ratio_table": SSP2050_RATIO_VS_SSP2,
        },
        "rows": rows,
    }
    with open(OUT_COMPACT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    print('compact json v2 size:', os.path.getsize(OUT_COMPACT), 'bytes')


def pop_notna(v):
    try:
        return v == v and v is not None  # NaN対策
    except Exception:
        return v is not None


if __name__ == '__main__':
    main()
