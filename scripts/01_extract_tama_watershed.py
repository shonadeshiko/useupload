"""
多摩川流域の抽出パイプライン (1/3) — 流域界データの取得と流域ポリゴンの結合

【前提・入力】
- 国土数値情報 W12(流域界・非集水域)の東京都(13)・神奈川県(14)・山梨県(19)の
  シェープファイルを事前にダウンロード・展開しておくこと。
  ダウンロードURL(2026-08-04 時点で実在確認済み):
    https://nlftp.mlit.go.jp/ksj/gmlold/data/W12/W12-52A/W12-52A-{pref}-01.1_GML.zip
    (pref = 13, 14, 19)
- 多摩川水系の水系域コード(旧水系域コード, W12_002) = "83030"。
  これは告示や属性テーブルに直接「多摩川」と書かれているわけではなく、
  河口(東京都大田区・川崎市境, 約139.7469E 35.5311N)と
  水源域(山梨県丹波山村付近, 約138.9400E 35.7900N)の2地点を含むポリゴンの
  W12_002属性値が両方とも"83030"と一致したことから同定した(2026-08-04)。
  流域面積の算出値(約1,239km2)が公表値(約1,240km2)と一致することも確認済み。

【出力】
- tama_watershed_dissolved.gpkg: 結合・修復済みの流域ポリゴン(1レコード)

【既知の環境バグ】
- このマシンの conda 環境(gienv)では、rasterio.windows.from_bounds() が
  ネイティブクラッシュ(exit code 127, 例外を投げずに落ちる)を起こす既知の問題がある。
  Window() を手動計算して回避すること(02_clip_landcover.py 参照)。原因未特定。
  MEMORY.md に教訓として記録済み。
"""
import os
import pyogrio
import geopandas as gpd
import pandas as pd
import shapely

# データ配置: このスクリプトから見て ../data/w12/ 以下にダウンロード・展開しておくこと。
# (実データはリポジトリに含めない。.gitignore対象。各自でダウンロードして配置する)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data', 'w12')

# ここを環境に合わせて変更
W12_DIR = {
    13: os.path.join(DATA_DIR, '13', 'W12-52A_13_WatershedBoundary.shp'),
    14: os.path.join(DATA_DIR, '14', 'W12-52A_14_WatershedBoundary.shp'),
    19: os.path.join(DATA_DIR, '19', 'W12-52A_19_WatershedBoundary.shp'),
}
TAMA_WATER_SYSTEM_CODE = '83030'
OUT_DISSOLVED = os.path.join(DATA_DIR, 'tama_watershed_dissolved.gpkg')
OUT_PARTS = os.path.join(DATA_DIR, 'tama_watershed_parts.gpkg')


def main():
    parts = []
    for pref, path in W12_DIR.items():
        # W12は旧測地系(Tokyo Datum, EPSG:4612)。encoding=cp932(シフトJIS)。
        # 一部ポリゴンでリング非閉合エラーが出るため on_invalid='fix' で修復しながら読む。
        g = pyogrio.read_dataframe(path, encoding='cp932', on_invalid='fix')
        g = g.set_crs('EPSG:4612', allow_override=True)
        sub = g[g['W12_002'] == TAMA_WATER_SYSTEM_CODE].copy()
        sub['pref'] = pref
        parts.append(sub)
        print(f'pref {pref}: {len(sub)} 件抽出')

    tama = pd.concat(parts, ignore_index=True)
    tama = gpd.GeoDataFrame(tama, geometry='geometry', crs='EPSG:4612')
    tama_wgs = tama.to_crs('EPSG:4326')

    # 一部ジオメトリが無効(自己交差等)なため make_valid してから結合
    tama_wgs['geometry'] = tama_wgs['geometry'].apply(lambda geom: shapely.make_valid(geom))
    union = shapely.union_all(tama_wgs.geometry.values)
    print('union valid:', union.is_valid, 'geom_type:', union.geom_type)
    print('union bounds:', union.bounds)

    diss = gpd.GeoDataFrame({'name': ['多摩川水系']}, geometry=[union], crs='EPSG:4326')
    diss.to_file(OUT_DISSOLVED, layer='tama_watershed', driver='GPKG')
    tama_wgs.to_file(OUT_PARTS, layer='tama_watershed_parts', driver='GPKG')

    # 面積検算(EPSG:6677=平面直角座標系IX系に投影して概算)
    tama_6677 = diss.to_crs('EPSG:6677')
    area_km2 = tama_6677.area.sum() / 1e6
    print(f'概算面積: {area_km2:.1f} km2 (公表値の目安: 約1,240km2)')


if __name__ == '__main__':
    main()
