"""
案B 頑健性チェック — 同一入力への複数回応答のばらつきを測定する

【目的】
06_agent_layer_prototype.py の実行で「人口動向+0.9%(プラス成長)でも放棄強度が
65まで上昇する」等、数値コンテキストと非単調な応答が観測された(D-015参照)。
これがモデル固有のランダム性(temperature由来)によるものか、プロンプト設計の
問題かを切り分けるため、**同一の入力を複数回投げ、スコアのばらつきを実測する**。

【検証すること】
1. デフォルト設定(temperatureはOllamaのモデル既定値)でのばらつき
2. temperature=0(貪欲デコーディング、理論上は毎回同じ出力になるはず)でのばらつき
   → (1)と(2)の差が大きければ「ランダム性由来」、変わらなければ「プロンプトや
     モデル自体の限界」の可能性が高いと判断できる
"""
import json
import os
import time
import urllib.request
import statistics

OLLAMA_URL = 'http://localhost:11434/api/generate'
OLLAMA_MODEL = 'qwen2.5:1.5b'

# 出力先: このスクリプトから見てリポジトリ直下(scripts/の一つ上)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_LOG_PATH = os.path.join(BASE_DIR, '..', '_robustness_check_log.json')

# 06と同じプロンプト。固定コンテキスト(2050年/A_大都市圏市街地、開発事業者)
FIXED_PROMPT = """あなたは多摩川流域のある地域で活動する不動産開発事業者です。
以下の情報を踏まえ、今後5年間のこの地域における開発意欲を判断してください。

【地域の状況】
- 地域区分: 大都市圏市街地
- 市区町村: 23区・八王子市・立川市等 多摩地域24市
- この5年間の人口動向: +0.9%（人口指数の変化率）
- 現在の市街地化率: 35.0%
- 生態系サービス価値の動向: 未接続(デモ範囲外)
- 地価の動向: 未接続(デモ範囲外)

【判断してほしいこと】
この地域における開発（農地・森林から市街地への転用）の強度を
0（開発しない）〜100（積極的に開発する）のスコアで答えてください。
また、その理由を2-3文で述べてください。
【重要】理由(reasoning)は必ず日本語で書いてください。中国語や英語は使わないでください。

【出力形式（JSON）】
{"intensity": <0-100の整数>, "reasoning": "<理由>"}
"""

FIXED_PROMPT_LANDOWNER = """あなたは多摩川流域の中山間地・郊外で農地・山林を所有する集落の代表的な世帯です。
以下の情報を踏まえ、今後5年間のこの地域における農地・山林の管理継続意欲を判断してください。

【地域の状況】
- 地域区分: 大都市圏非市街地
- 市区町村: 青梅市・あきる野市・瑞穂町・日の出町・檜原村・奥多摩町
- この5年間の人口動向: +0.7%（人口指数の変化率、後継者・担い手の代理指標）
- 現在の耕地・森林の残存率: 60.0%
- 近隣の開発動向: 開発強度スコア65(直前算出)

【判断してほしいこと】
この地域における管理放棄（農地・森林の粗放化）の強度を
0（全く放棄しない・管理を維持）〜100（積極的に放棄が進む）のスコアで答えてください。
また、その理由を2-3文で述べてください。
【重要】理由(reasoning)は必ず日本語で書いてください。中国語や英語は使わないでください。

【出力形式（JSON）】
{"intensity": <0-100の整数>, "reasoning": "<理由>"}
"""


def call_ollama(prompt: str, temperature=None, timeout=60):
    payload = {'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False, 'format': 'json'}
    if temperature is not None:
        payload['options'] = {'temperature': temperature}
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    elapsed = time.time() - t0
    parsed = json.loads(result['response'])
    parsed['_elapsed_sec'] = round(elapsed, 1)
    return parsed


def run_repeats(prompt, label, n=5, temperature=None):
    print(f"\n=== {label} (temperature={temperature}, n={n}) ===")
    scores = []
    reasonings = []
    for i in range(n):
        try:
            r = call_ollama(prompt, temperature=temperature)
            scores.append(r['intensity'])
            reasonings.append(r['reasoning'])
            print(f"  試行{i+1}: intensity={r['intensity']} ({r['_elapsed_sec']}秒)")
        except Exception as e:
            print(f"  試行{i+1}: 失敗 ({e})")
    if scores:
        print(f"  → 平均={statistics.mean(scores):.1f} 標準偏差={statistics.pstdev(scores):.1f} "
              f"最小={min(scores)} 最大={max(scores)} 全値={scores}")
    return scores, reasonings


def main():
    results = {}

    scores_default, reasonings_default = run_repeats(
        FIXED_PROMPT, "開発事業者(デフォルトtemperature)", n=5, temperature=None)
    results['developer_default'] = scores_default

    scores_t0, reasonings_t0 = run_repeats(
        FIXED_PROMPT, "開発事業者(temperature=0)", n=5, temperature=0.0)
    results['developer_temp0'] = scores_t0

    scores_land_default, _ = run_repeats(
        FIXED_PROMPT_LANDOWNER, "地権者(デフォルトtemperature)", n=5, temperature=None)
    results['landowner_default'] = scores_land_default

    scores_land_t0, _ = run_repeats(
        FIXED_PROMPT_LANDOWNER, "地権者(temperature=0)", n=5, temperature=0.0)
    results['landowner_temp0'] = scores_land_t0

    print("\n" + "=" * 60)
    print("まとめ")
    print("=" * 60)
    for k, v in results.items():
        if v:
            print(f"{k}: mean={statistics.mean(v):.1f} std={statistics.pstdev(v):.1f} "
                  f"range=[{min(v)},{max(v)}] values={v}")

    with open(OUT_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump({
            'results': results,
            'reasonings_default_sample': reasonings_default,
            'reasonings_temp0_sample': reasonings_t0,
        }, f, ensure_ascii=False, indent=2)
    print("\n保存完了")


if __name__ == '__main__':
    main()
