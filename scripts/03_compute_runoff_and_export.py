"""
多摩川流域の抽出パイプライン (3/3) — 流出係数の算出とダッシュボード用JSON出力

【入力】
- 02_clip_landcover_and_mesh.py の出力(tama_mesh_with_lulc.gpkg)

【出力】
- tama_mesh_final.geojson: 流出係数付きメッシュ(GeoJSON、フル)
- tama_compact.json: ダッシュボード埋め込み用の軽量JSON(座標+属性の配列、~360KB)

【クロスウォークについて(重要・要開示)】
JAXA HRLULCのクラス(#1-15)と、平成16年国土交通省告示第521号
(特定都市河川浸水被害対策法施行規則 第20条第3項に基づく、土地利用形態ごとの流出係数を
定める告示)のカテゴリの対応は、外部脳(このスクリプトの作成者)による解釈であり、
告示に直接の対応表があるわけではない。特に:
  - 告示上「林地・耕地・原野」は同一区分(係数0.20)。JAXAの水田・畑地・草地・森林(4種)・竹林を
    すべてこの0.20に対応させているため、これらの間の土地利用転換(耕作放棄等)だけでは
    流出係数は変化しない。転用(市街地化、係数0.90)だけが係数を大きく動かす。
  - #12ソーラーパネル・#14農業用温室は「不浸透面」として便宜的に宅地(0.90)扱いとしたが、
    告示にこれらの直接規定はない(暫定)。
  - #10裸地は「締め固められていない土地」(0.20)としたが、施工中の裸地であれば
    実際にはローラー等で締め固められ0.50に近い可能性がある(暫定)。
数値を論文・提案書・客先資料に転記する前に、このクロスウォークの妥当性を再検証すること。
"""
import geopandas as gpd
import pandas as pd
import json
import os

# データ配置: このスクリプトから見て ../data/w12/ 以下(02の出力と同じ場所)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data', 'w12')

IN_PATH = os.path.join(DATA_DIR, 'tama_mesh_with_lulc.gpkg')
OUT_GEOJSON = os.path.join(DATA_DIR, 'tama_mesh_final.geojson')
OUT_COMPACT = os.path.join(DATA_DIR, 'tama_compact.json')

# 平成16年国土交通省告示第521号(2026-08-04 一次確認・PyMuPDFで本文抽出)に基づく流出係数。
# JAXAクラス -> (告示上の名称, 係数, 対応関係の注記)
CROSSWALK = {
    1:  ("水域",           1.00, "池沼・水路"),
    2:  ("市街地",         0.90, "宅地"),
    3:  ("水田",           0.20, "耕地(告示上は林地・耕地・原野と同一区分)"),
    4:  ("畑地",           0.20, "耕地"),
    5:  ("草地",           0.20, "原野(告示上は耕地と同一区分。放棄地の代理として使用)"),
    6:  ("森林1",          0.20, "林地"),
    7:  ("森林2",          0.20, "林地"),
    8:  ("森林3",          0.20, "林地"),
    9:  ("森林4",          0.20, "林地"),
    10: ("裸地",           0.20, "締め固められていない土地(暫定)"),
    11: ("竹林",           0.20, "林地"),
    12: ("ソーラーパネル", 0.90, "不浸透面(暫定・宅地扱い、告示に直接規定なし)"),
    13: ("湿地",           1.00, "池沼等(暫定)"),
    14: ("農業用温室",     0.90, "不浸透面(暫定・宅地扱い、告示に直接規定なし)"),
    15: ("岩礁・干潟",     1.00, "水域扱い"),
}


def main():
    mesh = gpd.read_file(IN_PATH)
    class_cols = [f'lulc_{c}' for c in range(1, 16)]
    coef = pd.Series({f'lulc_{c}': v[1] for c, v in CROSSWALK.items()})

    total = mesh[class_cols].sum(axis=1).replace(0, pd.NA)
    weighted = (mesh[class_cols] * coef).sum(axis=1)
    mesh['f0_2022'] = weighted / total

    mesh['area_urban_pct'] = mesh['lulc_2'] / total * 100
    mesh['area_crop_pct'] = (mesh['lulc_3'] + mesh['lulc_4']) / total * 100
    mesh['area_grass_pct'] = mesh['lulc_5'] / total * 100
    mesh['area_forest_pct'] = (mesh['lulc_6'] + mesh['lulc_7'] + mesh['lulc_8'] + mesh['lulc_9'] + mesh['lulc_11']) / total * 100
    mesh['area_water_pct'] = (mesh['lulc_1'] + mesh['lulc_13'] + mesh['lulc_15']) / total * 100

    print('f0 平均:', mesh['f0_2022'].mean())
    print('水田(#3)の流域合計比率:', mesh['lulc_3'].sum() / mesh[class_cols].sum().sum() * 100, '%')
    print('  -> 注意: この値が小さい場合、「耕作放棄で水田(=貯留インフラ)が失われる」という')
    print('     物語は本流域では実証力が弱い可能性がある。別途 D-005 の水田比率と要突合。')

    mesh_out = mesh.rename(columns={'2022sum': 'es_value_2022', '2022地価mean': 'land_price_2022'})
    out_cols = ['code', 'f0_2022', 'area_urban_pct', 'area_crop_pct', 'area_grass_pct',
                'area_forest_pct', 'area_water_pct', 'es_value_2022', 'land_price_2022', 'geometry']
    mesh_final = mesh_out[out_cols].copy()
    mesh_final['f0_2022'] = mesh_final['f0_2022'].round(4)
    mesh_final.to_file(OUT_GEOJSON, driver='GeoJSON')

    # ダッシュボード用コンパクトJSON(GeoJSONは冗長で重いため、配列ベースに変換)
    mesh_final['cx'] = mesh_final.geometry.centroid.x
    mesh_final['cy'] = mesh_final.geometry.centroid.y

    rows = []
    for _, r in mesh_final.iterrows():
        rows.append([
            int(r['code']), round(float(r['cx']), 5), round(float(r['cy']), 5),
            round(float(r['f0_2022']), 4) if pd.notna(r['f0_2022']) else None,
            round(float(r['area_urban_pct']), 2), round(float(r['area_crop_pct']), 2),
            round(float(r['area_grass_pct']), 2), round(float(r['area_forest_pct']), 2),
            round(float(r['area_water_pct']), 2),
            round(float(r['es_value_2022']), 0) if pd.notna(r['es_value_2022']) else None,
            round(float(r['land_price_2022']), 0) if pd.notna(r['land_price_2022']) else None,
        ])

    out = {
        "meta": {
            "source": "JAXA HRLULC 2022 (2022_merged.tif) + Pricedata/地価と自然の価値比較.gpkg + 国土数値情報W12流域界(多摩川水系=83030)",
            "n_mesh": len(rows),
            "columns": ["code", "cx", "cy", "f0_2022", "urban_pct", "crop_pct", "grass_pct", "forest_pct", "water_pct", "es_value_2022", "land_price_2022"],
            "bounds": mesh_final.total_bounds.tolist(),
            "crosswalk_note": "JAXA分類->告示521号カテゴリの対応は外部脳の解釈。告示に直接の対応表はない。詳細はこのファイルのdocstring参照。",
        },
        "rows": rows,
    }
    with open(OUT_COMPACT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    print('compact json size:', os.path.getsize(OUT_COMPACT), 'bytes')


if __name__ == '__main__':
    main()
