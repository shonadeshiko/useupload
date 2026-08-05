"""
案B プロトタイプ — LLMエージェント層（層A）の実行可能なアーキテクチャ

【✅ 2026-08-05 更新 — Ollamaでの実行に対応】
このマシンには Ollama がインストール・稼働済み（`ollama ps` で確認）。
当初検討していたクラウドAPI（Anthropic/OpenAI）は認証情報が無く使えなかったが、
**Ollamaはローカルで動くためAPIキー不要**、この制約を解消できる。

モデル選定の経緯:
- `qwen3.5:9b`（既存導入済み）はCPU推論のみの環境で応答が極端に遅く（180秒待っても
  完了しない事例あり）、実用的でないと判断。
- **`qwen2.5:1.5b` に切り替え**（2026-08-05 pull）。簡単な挨拶で4.4秒、
  実際のエージェント判断プロンプト（JSON構造化出力）で6.0秒という実用的な速度を確認。
  日本語の理由文も一貫性のある内容が得られている（`ollama_decide_agent()` のdocstring内、
  実行結果ログ参照）。

**実装されている・実在するもの**:
- `ollama_decide_agent()`: ローカルOllama(`http://localhost:11434`)への実際のHTTP呼び出し。
  **これは本物のLLM推論であり、モックではない**。
- `mock_decide_agent()`: 比較用に残したルールベースの代理関数（Ollama不使用時のフォールバック）。
- 実際に使えるプロンプトテンプレート（`DEVELOPER_AGENT_PROMPT` / `LANDOWNER_AGENT_PROMPT`）。
- 層B（02-実装設計・04ダッシュボード）との接続点（エージェントの判断が devPct/abnPct の
  乗数として層Bの計算式に反映される設計）。
- 市区町村×地域区分単位での一括実行と、判断ログ（LLMの実際の理由文つき）の出力。

【設計思想】
[[projects/ABM事業化/02-実装設計]] で定めた二層構造（層A=LLMエージェントの意思決定、
層B=決定論的な空間更新）に基づく。層Aは**メッシュ単位ではなく、市区町村×地域区分単位**で
エージェントを置く（4,381メッシュ全部にLLMを当てると時間がかかりすぎるため）。
エージェントの出力は「開発強度」「放棄強度」という**質的な判断（0-100スコア、理由）**
であり、これが層Bの devPct/abnPct に**乗数として**掛かる。
"""
import json
import os
import time
import urllib.request

OLLAMA_URL = 'http://localhost:11434/api/generate'
OLLAMA_MODEL = 'qwen2.5:1.5b'

# ============================================================
# 1. プロンプトテンプレート（実物。実際のLLM呼び出しにそのまま使える）
# ============================================================

DEVELOPER_AGENT_PROMPT = """あなたは多摩川流域のある地域で活動する不動産開発事業者です。
以下の情報を踏まえ、今後5年間のこの地域における開発意欲を判断してください。

【地域の状況】
- 地域区分: {category_label}
- 市区町村: {municipality_names}
- この5年間の人口動向: {pop_trend_pct:+.1f}%（人口指数の変化率）
- 現在の市街地化率: {urban_pct:.1f}%
- 生態系サービス価値の動向: {es_trend}
- 地価の動向: {price_trend}

【判断してほしいこと】
この地域における開発（農地・森林から市街地への転用）の強度を
0（開発しない）〜100（積極的に開発する）のスコアで答えてください。
また、その理由を2-3文で述べてください。
【重要】理由(reasoning)は必ず日本語で書いてください。中国語や英語は使わないでください。

【出力形式（JSON）】
{{"intensity": <0-100の整数>, "reasoning": "<理由>"}}
"""

LANDOWNER_AGENT_PROMPT = """あなたは多摩川流域の中山間地・郊外で農地・山林を所有する集落の代表的な世帯です。
以下の情報を踏まえ、今後5年間のこの地域における農地・山林の管理継続意欲を判断してください。

【地域の状況】
- 地域区分: {category_label}
- 市区町村: {municipality_names}
- この5年間の人口動向: {pop_trend_pct:+.1f}%（人口指数の変化率、後継者・担い手の代理指標）
- 現在の耕地・森林の残存率: {agri_pct:.1f}%
- 近隣の開発動向: {dev_context}

【判断してほしいこと】
この地域における管理放棄（農地・森林の粗放化）の強度を
0（全く放棄しない・管理を維持）〜100（積極的に放棄が進む）のスコアで答えてください。
また、その理由を2-3文で述べてください。
【重要】理由(reasoning)は必ず日本語で書いてください。中国語や英語は使わないでください。

【出力形式（JSON）】
{{"intensity": <0-100の整数>, "reasoning": "<理由>"}}
"""


# ============================================================
# 2. エージェント意思決定インターフェース
# ============================================================

def ollama_decide_agent(prompt: str, context: dict, retries: int = 2, temperature: float = 0.0) -> dict:
    """
    ✅ 実際のLLM呼び出し（Ollama、ローカル実行、モックではない）。
    2026-08-05 動作確認済み: qwen2.5:1.5b、応答時間 4〜10秒程度（CPU推論）。

    【2026-08-05 頑健性チェックの結果を反映】
    - デフォルトtemperatureでは同一入力でも intensity が大きくばらつく
      （標準偏差7.5〜15.6、[[projects/ABM事業化/scripts/07_robustness_check.py]] 参照）。
    - temperature=0（貪欲デコーディング）にすると**完全に決定論的**（標準偏差0）になり、
      かつ極端な入力（人口+30%/-30%等）に対しては正しく異なるスコアを返す
      （文脈を無視して常に固定値を返しているわけではないことを確認済み）。
    - → **デフォルトを temperature=0 に変更**。再現性を優先する。
    - 併せて、プロンプトに「必ず日本語で書いてください」の指示を追加したところ、
      中国語が混入する言語ドリフトが解消した（qwen2.5は多言語モデルのため、
      明示指定が無いと出力言語が安定しないことがある）。
    """
    payload = {
        'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False, 'format': 'json',
        'options': {'temperature': temperature},
    }
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    last_err = None
    for attempt in range(retries + 1):
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            elapsed = time.time() - t0
            parsed = json.loads(result['response'])
            parsed['_elapsed_sec'] = round(elapsed, 1)
            parsed['_model'] = OLLAMA_MODEL
            parsed['_mock'] = False
            return parsed
        except Exception as e:
            last_err = e
            print(f"  [警告] Ollama呼び出し失敗(試行{attempt+1}/{retries+1}): {e}")
    # 全試行失敗時はエラーを明示して停止(黙って0を返さない)
    raise RuntimeError(f"Ollama呼び出しが{retries+1}回とも失敗しました: {last_err}")


def mock_decide_agent(prompt: str, context: dict) -> dict:
    """
    🔴🔴 MOCK — 実際のLLM呼び出しではない。ルールベースの代理関数。
    層Aのインターフェース（入力: プロンプト文字列 / 出力: intensity・reasoning のdict）を
    満たす形で、動作確認・デモのために用意した代替ロジック。
    人口動向・現況の閾値だけで判定する単純な線形則であり、LLMが持つはずの
    「定性的情報の統合」「文脈依存の判断」は再現できていない。
    """
    pop_trend = context.get('pop_trend_pct', 0)
    agent_type = context.get('agent_type')

    if agent_type == 'developer':
        urban_pct = context.get('urban_pct', 0)
        # 単純則: 人口増加が大きいほど、かつ既存市街地化率が低いほど開発意欲が高い(伸びしろ)
        intensity = max(0, min(100, pop_trend * 8 + max(0, 50 - urban_pct) * 0.3))
        reasoning = (
            f"[MOCK] 人口動向{pop_trend:+.1f}%、市街地化率{urban_pct:.1f}%を踏まえた"
            f"機械的な線形則による代理判断（実際のLLM推論ではない）。"
        )
    elif agent_type == 'landowner':
        agri_pct = context.get('agri_pct', 0)
        # 単純則: 人口減少が大きいほど放棄意欲が高い。残存する農地・森林が少ないほど守る意識が強まる(逆相関)と仮定
        intensity = max(0, min(100, -pop_trend * 6 + max(0, agri_pct - 30) * 0.2))
        reasoning = (
            f"[MOCK] 人口動向{pop_trend:+.1f}%、耕地・森林残存率{agri_pct:.1f}%を踏まえた"
            f"機械的な線形則による代理判断（実際のLLM推論ではない）。"
        )
    else:
        intensity, reasoning = 50, "[MOCK] 既定値"

    return {"intensity": round(intensity, 1), "reasoning": reasoning, "_mock": True, "_elapsed_sec": 0.0}


# ============================================================
# 3. 市区町村×地域区分の代表エージェント設定
# ============================================================
# 04_integrate_ssp_population.py の分類をそのまま流用
MUNICIPALITY_GROUPS = {
    'A_大都市圏市街地': {
        'label': '大都市圏市街地',
        'municipalities': '23区・八王子市・立川市・武蔵野市等 多摩地域24市',
    },
    'B_大都市圏非市街地': {
        'label': '大都市圏非市街地',
        'municipalities': '青梅市・あきる野市・瑞穂町・日の出町・檜原村・奥多摩町',
    },
}


def run_agent_layer(decide_fn, years, ssp_ratio_table, pop_trend_by_category):
    """
    市区町村グループ×時点ごとにエージェントを呼び出し、開発・放棄の強度スコアを得る。
    出力は層B（devPct/abnPctの乗数）に接続するための係数テーブル。
    """
    log = []
    intensity_table = {}

    for cat_key, group in MUNICIPALITY_GROUPS.items():
        for yi, year in enumerate(years):
            if yi == 0:
                continue
            pop_trend_pct = pop_trend_by_category.get(cat_key, {}).get(year, 0.0)

            dev_ctx = {
                'agent_type': 'developer',
                'pop_trend_pct': pop_trend_pct,
                'urban_pct': 35.0,  # デモ用の代表値。実運用ではメッシュ集計値を渡す
            }
            dev_prompt = DEVELOPER_AGENT_PROMPT.format(
                category_label=group['label'], municipality_names=group['municipalities'],
                pop_trend_pct=pop_trend_pct, urban_pct=dev_ctx['urban_pct'],
                es_trend='未接続(デモ範囲外)', price_trend='未接続(デモ範囲外)',
            )
            dev_result = decide_fn(dev_prompt, dev_ctx)

            land_ctx = {
                'agent_type': 'landowner',
                'pop_trend_pct': pop_trend_pct,
                'agri_pct': 60.0,  # デモ用の代表値
            }
            land_prompt = LANDOWNER_AGENT_PROMPT.format(
                category_label=group['label'], municipality_names=group['municipalities'],
                pop_trend_pct=pop_trend_pct, agri_pct=land_ctx['agri_pct'],
                dev_context=f"開発強度スコア{dev_result['intensity']:.0f}(直前算出)",
            )
            land_result = decide_fn(land_prompt, land_ctx)

            intensity_table[(cat_key, year)] = {
                'dev_intensity': dev_result['intensity'],
                'abn_intensity': land_result['intensity'],
            }
            log.append({
                'year': year, 'category': cat_key,
                'developer': dev_result, 'landowner': land_result,
            })

    return intensity_table, log


def main(use_ollama: bool = True):
    years = [2020, 2025, 2030, 2035, 2040, 2045, 2050]

    # デモ用の人口トレンド(実際は04の出力から地域区分別に集計して渡す。ここでは簡略化した代表値)
    pop_trend_by_category = {
        'A_大都市圏市街地': {2025: 1.9, 2030: 1.7, 2035: 1.4, 2040: 1.2, 2045: 1.0, 2050: 0.9},
        'B_大都市圏非市街地': {2025: 1.3, 2030: 1.2, 2035: 1.0, 2040: 0.9, 2045: 0.8, 2050: 0.7},
    }

    decide_fn = ollama_decide_agent if use_ollama else mock_decide_agent
    mode_label = f"OLLAMA実行(model={OLLAMA_MODEL}, 本物のLLM推論)" if use_ollama else "MOCK実行(ルールベース代理関数)"

    print("=" * 60)
    print(mode_label)
    print("=" * 60)

    t_start = time.time()
    intensity_table, log = run_agent_layer(
        decide_fn, years, None, pop_trend_by_category
    )
    total_elapsed = time.time() - t_start

    for entry in log:
        print(f"\n[{entry['year']}年 / {entry['category']}]")
        print(f"  開発事業者エージェント: intensity={entry['developer']['intensity']} "
              f"({entry['developer'].get('_elapsed_sec', '?')}秒)")
        print(f"    理由: {entry['developer']['reasoning']}")
        print(f"  地権者エージェント:     intensity={entry['landowner']['intensity']} "
              f"({entry['landowner'].get('_elapsed_sec', '?')}秒)")
        print(f"    理由: {entry['landowner']['reasoning']}")

    print(f"\n合計所要時間: {total_elapsed:.1f}秒 ({len(log)*2}回のLLM呼び出し)")

    out_name = '_agent_layer_ollama_log.json' if use_ollama else '_agent_layer_demo_log.json'
    out_path = os.path.join(os.path.dirname(__file__), '..', out_name)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'intensity_table': {f'{k[0]}|{k[1]}': v for k, v in intensity_table.items()},
            'log': log, 'mock': not use_ollama, 'model': OLLAMA_MODEL if use_ollama else None,
            'total_elapsed_sec': round(total_elapsed, 1),
        }, f, ensure_ascii=False, indent=2)
    print(f"\n保存: {out_path}")


if __name__ == '__main__':
    main(use_ollama=True)
