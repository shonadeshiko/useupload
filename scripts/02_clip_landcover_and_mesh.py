"""
多摩川流域の抽出パイプライン (2/3) — 500mメッシュのクリップとJAXA土地被覆のゾーン統計

【入力】
- 01_extract_tama_watershed.py の出力(tama_watershed_dissolved.gpkg)
- Pricedata/地価と自然の価値比較.gpkg (500mメッシュ、東京都、17,423件、ES価値・地価)
- Pricedata/2022_merged.tif (JAXA HRLULC 2022年、全国、EPSG:4326、10m、クラス1-15)

【出力】
- tama_mesh_2022base.gpkg: 多摩川流域内(重心判定)の500mメッシュ(東京都データの範囲内のみ)
- tama_mesh_with_lulc.gpkg: 上記に土地被覆クラス別ピクセル数を結合したもの

【重要な既知の限界】
- 東京都のメッシュデータのみを対象としているため、多摩川流域のうち山梨県(水源域)・
  神奈川県(川崎市側の一部支流域)にまたがる部分はこの抽出には含まれない。
  流域全体は約1,239km2だが、本抽出は東京都内の4,381メッシュ(約1,095km2相当)のみ。

【既知の環境バグ(重要)】
- rasterio.windows.from_bounds() がこの環境でネイティブクラッシュする(例外を投げずに
  exit code 127で落ちる)。Window()を手動計算して回避している(下記 col_off/row_off/width/height)。
  原因はrasterio 1.5.0 / affine 2.4.0の組み合わせ、またはGDAL周りのDLL不整合と推測されるが未特定。
  MEMORY.mdに教訓として記録済み。他の環境ではfrom_bounds()が普通に動く可能性が高いので、
  移植時はまず素直にfrom_bounds()を試し、同様のクラッシュが出た場合のみ本回避策を使うこと。
"""
import os
import rasterio
from rasterio.windows import Window
from rasterio.features import rasterize
import numpy as np
import geopandas as gpd
import pandas as pd

# データ配置: このスクリプトから見て ../data/ 以下に配置しておくこと。
# (実データはリポジトリに含めない。.gitignore対象。各自でダウンロード・コピーして配置する)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
EXTERNAL_DATA_DIR = os.path.join(DATA_DIR, 'external')  # 他プロジェクト由来の地価・ES価値/LULCデータ置き場

MESH_PATH = os.path.join(EXTERNAL_DATA_DIR, '地価と自然の価値比較.gpkg')
LULC_PATH = os.path.join(EXTERNAL_DATA_DIR, '2022_merged.tif')
WATERSHED_PATH = os.path.join(DATA_DIR, 'w12', 'tama_watershed_dissolved.gpkg')

OUT_MESH = os.path.join(DATA_DIR, 'w12', 'tama_mesh_2022base.gpkg')
OUT_MESH_LULC = os.path.join(DATA_DIR, 'w12', 'tama_mesh_with_lulc.gpkg')


def clip_mesh_to_watershed():
    mesh = gpd.read_file(MESH_PATH)
    tama = gpd.read_file(WATERSHED_PATH)
    # メッシュ重心が流域ポリゴンに入るかで帰属判定(500mメッシュなので実務上十分な近似)
    mesh_centroid = gpd.GeoDataFrame(mesh[['code']], geometry=mesh.geometry.centroid, crs=mesh.crs)
    within = gpd.sjoin(mesh_centroid, tama, predicate='within', how='inner')
    tama_mesh = mesh[mesh['code'].isin(within['code'])].copy()
    print(f'多摩川流域内メッシュ数(東京都データ範囲内、重心判定): {len(tama_mesh)}')
    tama_mesh.to_file(OUT_MESH, layer='tama_mesh', driver='GPKG')
    return tama_mesh


def clip_landcover_window(bounds):
    """
    from_bounds()のクラッシュを避けるため、Windowを手動計算する。
    bounds = (minx, miny, maxx, maxy) in the raster's CRS (EPSG:4326)
    """
    minx, miny, maxx, maxy = bounds
    with rasterio.open(LULC_PATH) as src:
        t = src.transform
        col_off = (minx - t.c) / t.a
        row_off = (maxy - t.f) / t.e
        width = (maxx - minx) / t.a
        height = (miny - maxy) / t.e
        win = Window(col_off, row_off, width, height)
        arr = src.read(1, window=win)
        win_transform = src.window_transform(win)
    return arr, win_transform


def zonal_stats(mesh, arr, transform):
    mesh = mesh.reset_index(drop=True)
    mesh['zone_id'] = mesh.index
    shapes = [(geom, zid) for geom, zid in zip(mesh.geometry, mesh['zone_id'])]
    zone_arr = rasterize(shapes, out_shape=arr.shape, transform=transform, fill=-1, dtype='int32')

    valid = (zone_arr >= 0) & (arr >= 1) & (arr <= 15)
    zvals = zone_arr[valid]
    lvals = arr[valid].astype(np.int64)

    n_zone = len(mesh)
    key = zvals.astype(np.int64) * 16 + lvals
    counts = np.bincount(key, minlength=n_zone * 16).reshape(n_zone, 16)

    class_cols = [f'lulc_{c}' for c in range(1, 16)]
    df_counts = pd.DataFrame(counts[:, 1:16], columns=class_cols)
    df_counts['zone_id'] = mesh['zone_id'].values

    result = mesh.merge(df_counts, on='zone_id')
    return result


def main():
    tama_mesh = clip_mesh_to_watershed()
    bounds = tuple(tama_mesh.total_bounds)  # (minx, miny, maxx, maxy)
    # 少し余裕を持たせる(メッシュ端の取りこぼし防止)
    pad = 0.02
    bounds = (bounds[0]-pad, bounds[1]-pad, bounds[2]+pad, bounds[3]+pad)

    arr, transform = clip_landcover_window(bounds)
    print('landcover window shape:', arr.shape)

    result = zonal_stats(tama_mesh, arr, transform)
    result.to_file(OUT_MESH_LULC, layer='tama_mesh_lulc', driver='GPKG')
    print('saved:', OUT_MESH_LULC)


if __name__ == '__main__':
    main()
