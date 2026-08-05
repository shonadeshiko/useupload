# data/ フォルダについて

このフォルダには `scripts/` のパイプラインが読み書きする**中間生成物・入力データ**を配置する。
実データ自体はサイズが大きく、出典によっては再配布条件が異なるため、**このリポジトリには
含めていない**（`.gitignore` で除外）。各自で以下の通りダウンロード・配置すること。

## 配置構成

```
data/
├── w12/                 # 国土数値情報 W12(流域界)、および 01〜04 の中間・最終生成物
│   ├── 13/, 14/, 19/    # 東京都・神奈川県・山梨県の W12 シェープファイル(ダウンロード後に展開)
│   └── (パイプライン実行で自動生成される .gpkg / .geojson / .json 群)
├── pop500/
│   └── 13/500m_mesh_2018_13.dbf   # 国土数値情報 500mメッシュ将来推計人口(東京都)
└── external/
    ├── 地価と自然の価値比較.gpkg   # 500mメッシュ、ES価値・地価(別プロジェクト由来)
    └── 2022_merged.tif             # JAXA HRLULC 2022年 土地被覆(全国)
```

## 入手先

- **W12(流域界)**: https://nlftp.mlit.go.jp/ksj/gmlold/data/W12/W12-52A/W12-52A-{pref}-01.1_GML.zip
  (`{pref}` = 13, 14, 19)
- **500mメッシュ将来推計人口**: https://nlftp.mlit.go.jp/ksj/gml/data/m500h30/m500h30-18/500m_mesh_suikei_2018_shape_13.zip
- **JAXA HRLULC / 地価・ES価値データ**: 別プロジェクト([[projects/生態系サービス価値-地価相関]])由来。
  このリポジトリのスコープ外のため、手元のコピーを `external/` に配置すること。

## 実行順序

`scripts/01_extract_tama_watershed.py` → `02_clip_landcover_and_mesh.py` →
`03_compute_runoff_and_export.py` → `04_integrate_ssp_population.py` の順に実行すると、
このフォルダ内に中間生成物が積み上がり、最終的に `data/w12/tama_compact_v2.json` が
できる（ダッシュボードへの埋め込みは手動、または別途スクリプト化を推奨）。
