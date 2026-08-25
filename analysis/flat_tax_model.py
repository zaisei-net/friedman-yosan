# -*- coding: utf-8 -*-
"""
所得税総額半減・フラットタックス試算モデル【最終確定版】
note.com連載「所得税総額半減、フラットタックス」用

対象年: 令和9年分（2027年分）推計
設計: 均一控除＋単一税率（金融所得・事業所得込み、全所得統合）

============================================================
データソース一覧（すべて確報・一次資料ベース）
============================================================
1. 令和8年度予算（当初）租税及び印紙収入：所得税25兆3,250億円
   財務省「令和8年度税制改正の大綱」「令和8年度予算」(令和7年12月26日閣議決定)
2. 令和6年分民間給与実態統計調査 第16表・第21表（国税庁）
   給与階級別の給与所得者数・給与総額
3. 令和5年分申告所得税標本調査 第1表 総括表（国税庁、税務統計から見た申告所得税の実態）
   合計所得階級別・所得者区分別の人員・所得金額
4. 令和5年度国税庁統計年報「源泉所得税」(3)課税状況 第(4)(5)(6)表
   利子所得等・配当所得・特定口座内上場株式譲渡所得等の支払金額・源泉徴収税額（確定値）
5. 東証「2024年度株式分布状況調査」投資部門別株式保有比率
   配当の個人受取分按分に使用（個人・その他17.3%）
6. 令和6年度分会社標本調査 第1表 総括表（国税庁）
   資本金階級別の所得金額・法人税額（法人税モデルに使用）
7. 財務省「令和8年度税制改正の大綱の概要」（令和7年12月26日閣議決定）
   基礎控除・給与所得控除の令和8・9年分特例、防衛特別所得税創設等

============================================================
重要な設計判断（修正履歴）
============================================================
[v1] 令和6年度決算ベース→[v2] 令和8年度予算ベースに変更（ユーザー指摘）
[v3] 半減目標を「令和9年推計値の半分」→「令和8年度予算額の単純半分」に変更
[v4] 給与・事業所得のみ→金融所得（利子・配当・株式譲渡益）を追加
[v5] 配当所得の法人受取分混入を発見・東証データで個人按分（重要な補正）
[v6] 【重大修正】給与所得者の課税ベース計算で、現行の給与所得控除を適用した
     "給与所得金額"を使っていたが、フラットタックスは旧来の控除体系を均一控除
     一本に置き換える設計のため、給与"収入"金額（額面）をそのまま使うべきと
     判明（ユーザー指摘）。課税ベースが236兆円→306兆円に拡大、必要税率が
     大きく低下した。
[v7] 「誰も増税にならない」制約分析を追加（令和8・9年度税制改正の基礎控除
     特例・給与所得控除最低保障額引き上げを反映）
[v8] 高所得層に引っ張られない頑健な近似（95%タイル限定回帰、L1中央値回帰）
[v9] 法人税モデルを追加（令和6年度分会社標本調査、資本金階級別実効税率）
"""

import numpy as np

# ============================================================
# PART A: 所得税フラットタックス（給与所得控除廃止版）
# ============================================================

R8_BUDGET_INCOME_TAX = 25.325  # 兆円（令和8年度当初予算所得税）
TARGET_HALF = R8_BUDGET_INCOME_TAX / 2  # 12.6625兆円
INCOME_BASE_GROWTH_RATE = 0.03  # 課税ベース外挿の年率（賃金上昇率想定）
g = INCOME_BASE_GROWTH_RATE

# --- 給与所得分布（令和6年分、民間給与実態統計第21表） ---
salary_brackets = [
    # (下限万円, 上限万円, 人員千人, 給与総額億円)
    (0, 100, 3934, 31542), (100, 200, 5707, 81360), (200, 300, 6767, 170626),
    (300, 400, 8258, 290534), (400, 500, 7870, 353073), (500, 600, 6059, 332117),
    (600, 700, 3907, 252802), (700, 800, 2710, 202253), (800, 900, 1741, 147521),
    (900, 1000, 1208, 114615), (1000, 1500, 2306, 273008), (1500, 2000, 576, 99411),
    (2000, 2500, 147, 32624), (2500, 9999, 174, 71409),
]

def bracket_mid(lo, hi):
    return lo * 1.6 if hi >= 99999 else (lo + hi) / 2

# --- 事業・不動産・雑・他所得分布（令和5年分、申告所得税標本調査第1表、給与所得者を除く） ---
other_filers_brackets = [
    (0, 70, 105924-27862, 69837-18954), (70, 100, 240503-55803, 205922-47232),
    (100, 150, 597295-158366, 753222-201299), (150, 200, 730117-225993, 1277279-397549),
    (200, 250, 691159-250587, 1548878-563040), (250, 300, 588230-229168, 1609755-626685),
    (300, 400, 904060-397221, 3131484-1383608), (400, 500, 611627-284928, 2727249-1271592),
    (500, 600, 416245-195082, 2275453-1068810), (600, 700, 305407-150586, 1975694-975399),
    (700, 800, 225229-113347, 1682220-847691), (800, 1000, 305495-158124, 2722512-1411203),
    (1000, 1200, 194394-106578, 2124232-1165745), (1200, 1500, 195462-110923, 2616203-1486867),
    (1500, 2000, 201904-120375, 3489000-2085360), (2000, 3000, 179259-104476, 4339445-2525425),
    (3000, 5000, 107614-52814, 4066665-1975980), (5000, 10000, 56546-22091, 3834708-1471534),
    (10000, 20000, 18468-5140, 2497089-680994), (20000, 50000, 7352-1323, 2169040-378157),
    (50000, 100000, 1583-202, 1089680-133301), (100000, 200000, 609-45, 823335-58452),
    (200000, 500000, 283-12, 841301-32720), (500000, 1000000, 64-0, 427561-0),
    (1000000, 99999999, 43-1, 1542957-26607),
]

# 【v6修正】給与所得控除を適用せず、給与収入金額（額面）をそのまま課税ベースとする
salary_units_r9 = [(p * 1000, bracket_mid(lo, hi) * (1 + g) ** 3)
                    for lo, hi, p, _ in salary_brackets]
other_units_r9 = [(p, (inc_m * 100 / p) * (1 + g) ** 4)
                   for lo, hi, p, inc_m in other_filers_brackets if p > 0]
all_units = salary_units_r9 + other_units_r9

# --- 金融所得（令和5年分、源泉所得税統計年報確報、配当は個人按分後） ---
WITHHOLDING_RATE = 0.15315
INTEREST_TAX_R5 = 415_537
DIVIDEND_TAX_R5 = 5_622_514
STOCK_GAIN_TAX_R5 = 819_721
INDIVIDUAL_SHARE_OF_DIVIDENDS = 0.173  # 東証「株式分布状況調査」2024年度

INTEREST_BASE = INTEREST_TAX_R5 / WITHHOLDING_RATE / 1e6
DIVIDEND_BASE = (DIVIDEND_TAX_R5 / WITHHOLDING_RATE / 1e6) * INDIVIDUAL_SHARE_OF_DIVIDENDS
STOCK_BASE = STOCK_GAIN_TAX_R5 / WITHHOLDING_RATE / 1e6
FINANCIAL_R9 = (INTEREST_BASE + DIVIDEND_BASE + STOCK_BASE) * (1 + g) ** 4
FINANCIAL_MAN = FINANCIAL_R9 * 1e8


def revenue(deduction_man, rate):
    """均一控除(万円)・フラット税率(0-1)での所得税収(兆円)を返す"""
    rev = sum(p * max(inc - deduction_man, 0) * rate for p, inc in all_units) / 10000 / 10000
    rev += FINANCIAL_MAN * rate / 1e8
    return rev


def solve_rate(target_tril, deduction_man):
    """目標税収を達成する税率を逆算"""
    base = revenue(deduction_man, 1.0)
    return target_tril / base if base > 0 else None


# ============================================================
# PART B: 現行制度の税額関数（令和8・9年度改正反映、「誰も増税にならない」判定用）
# ============================================================

def basic_deduction_r9(total_income_man):
    """令和8・9年分の基礎控除（特例加算含む）"""
    base = 52  # 48+4(物価連動恒久加算)
    if total_income_man <= 489:
        extra = 42
    elif total_income_man <= 655:
        extra = 5
    elif total_income_man <= 2350:
        extra = 0
    elif total_income_man <= 2400:
        return 32
    elif total_income_man <= 2450:
        return 16
    else:
        return 0
    return base + extra


def salary_deduction_r9(income_man):
    """令和8・9年分の給与所得控除（最低保障74万円＝69+5の特例反映）"""
    if income_man <= 190:
        return max(income_man - 74, 0)
    elif income_man <= 360:
        return income_man - (income_man * 0.3 + 8)
    elif income_man <= 660:
        return income_man - (income_man * 0.2 + 44)
    elif income_man <= 850:
        return income_man - (income_man * 0.1 + 110)
    else:
        return income_man - 195


SURTAX_RATE = 0.021  # 防衛特別所得税1%+復興特別所得税1.1%（令和9年以降）


def progressive_tax(taxable):
    brackets = [(195, 0.05, 0), (330, 0.10, 9.75), (695, 0.20, 42.75),
                (900, 0.23, 63.6), (1800, 0.33, 153.6), (4000, 0.40, 279.6),
                (float('inf'), 0.45, 479.6)]
    for limit, rate, deduct in brackets:
        if taxable <= limit:
            return max(taxable * rate - deduct, 0)
    return 0


def current_tax_r9(gross_income_man):
    """令和9年分・現行制度（累進）での所得税額（単身給与所得者モデル、国税のみ）"""
    si = salary_deduction_r9(gross_income_man)
    bd = basic_deduction_r9(si)
    taxable = max(si - bd, 0)
    return progressive_tax(taxable) * (1 + SURTAX_RATE)


def max_rate_no_losers(deduction_man, test_incomes):
    """指定された控除額のもとで、誰も増税にならない上限税率を返す"""
    max_rate = 1.0
    binding_income = None
    for y in test_incomes:
        if y > deduction_man:
            ct = current_tax_r9(y)
            allowed = ct / (y - deduction_man)
            if allowed < max_rate:
                max_rate = allowed
                binding_income = y
    return max_rate, binding_income


# ============================================================
# PART C: 法人税モデル（令和6年度分会社標本調査確報ベース）
# ============================================================
CORP_INCOME_BASE_R6 = 102.061  # 兆円（利益計上法人の所得金額合計、令和6年度分確報）
CORP_TAX_FINAL_R6 = 18.682     # 兆円（法人税額、令和6年度分確報）
CORP_EFFECTIVE_RATE_R6 = CORP_TAX_FINAL_R6 / CORP_INCOME_BASE_R6  # 18.30%
CORP_TAX_R8_BUDGET = 20.696    # 兆円（令和8年度当初予算法人税）


def corp_revenue(rate, base_year_growth=3):
    """法人税フラット税率での税収(兆円)。令和6年度分→指定年数分を年率3%で外挿"""
    base_r9 = CORP_INCOME_BASE_R6 * (1 + g) ** base_year_growth
    return base_r9 * rate


# ============================================================
# 実行例（このファイルをそのまま実行すると主要な試算結果を表示）
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("所得税フラットタックス試算（令和9年分推計）")
    print("=" * 60)
    print(f"課税ベース合計: {sum(p*inc for p,inc in all_units)/1e8 + FINANCIAL_R9:.1f}兆円")
    print(f"半減目標: {TARGET_HALF:.4f}兆円\n")

    for D in [0, 48, 103, 178, 200, 250, 270, 300]:
        r = solve_rate(TARGET_HALF, D)
        print(f"控除{D:>4}万円 → 税率{r*100:5.2f}% (税収{revenue(D, r):.2f}兆円)")

    print("\n--- 「誰も増税にならない」制約（令和8・9年度改正後の現行制度比較）---")
    test_incomes = (list(range(0, 600, 5)) + list(range(600, 2000, 20)) +
                     list(range(2000, 10000, 100)) + list(range(10000, 50001, 1000)))
    for D in [178, 200, 220, 250, 270, 300]:
        r_max, binding = max_rate_no_losers(D, test_incomes)
        rev = revenue(D, r_max)
        print(f"控除{D:>4}万円 → 上限税率{r_max*100:5.2f}% "
              f"(制約点:収入{binding}万円, 税収{rev:.2f}兆円, 半減比{rev/TARGET_HALF*100:.1f}%)")

    print(f"\n--- 法人税（令和6年度分確報ベース）---")
    print(f"実効税率: {CORP_EFFECTIVE_RATE_R6*100:.2f}%")
    print(f"令和9年推計所得ベース: {CORP_INCOME_BASE_R6*(1+g)**3:.1f}兆円")
    print(f"10%フラット時税収: {corp_revenue(0.10):.2f}兆円")
