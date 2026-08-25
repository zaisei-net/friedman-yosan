"""
歳出・歳入 統合サマリー
歳出: friedman_items_r8.csv  (一般会計 科目別)
歳入: friedman_revenue_r8.csv (一般会計+特別会計公課 74項目)
"""
import csv

GDP = 6_000_000  # 600兆円

def load_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

# ── 歳出 ──────────────────────────────────────────────────────────
exp_rows = load_csv(r'C:\Users\s1\projects\friedman-yosan\output\friedman_items_r8.csv')
# 【合計】行を除外
total_row = next((r for r in exp_rows if r['所管'] == '【合計】'), None)
exp_g = int(total_row['元額_億円'])
exp_k = int(total_row['残す額_億円'])

# ── 歳入 ──────────────────────────────────────────────────────────
rev_rows = load_csv(r'C:\Users\s1\projects\friedman-yosan\output\friedman_revenue_r8.csv')
# 総合計行のみ
rev_total = next((r for r in rev_rows if '総合計' in r['項目名']), None)
rev_g = int(rev_total['現行_億円'])
rev_k = int(rev_total['改革後_億円'])

# カテゴリ別集計（歳入）
cats = {}
for r in rev_rows:
    if r['カテゴリ'] and r['現行_億円'] and r['項目名'] and \
       '小計' not in r['項目名'] and '合計' not in r['項目名']:
        c = r['カテゴリ']
        cats.setdefault(c, [0, 0])
        cats[c][0] += int(r['現行_億円'])
        cats[c][1] += int(r['改革後_億円'])

# フラットタックス新税収試算
flat_base = 302_0000  # 302兆円 = 3,020,000億円  ← 302 * 10000
flat_rate = 0.078
flat_new = int(flat_base * flat_rate)  # 235,560億円

consumption_new = 133_440  # 消費税5% (CSVより)
pigou_new = 11470+9760+9720+5980+3140+40+400+9030  # ピグー税類

print("=" * 65)
print("  フリードマン改革 令和8年度 統合サマリー")
print("=" * 65)

print("\n【歳出（一般会計 科目別 760項目）】")
print(f"  現行:  {exp_g:>12,} 億円  (GDP比 {exp_g/GDP*100:.1f}%)")
print(f"  改革後:{exp_k:>12,} 億円  (GDP比 {exp_k/GDP*100:.1f}%)")
print(f"  削減:  {exp_g-exp_k:>12,} 億円  ({(exp_g-exp_k)/exp_g*100:.1f}%削減)")

print("\n【歳入（74項目 改革シミュレーション）】")
for c, (g, k) in sorted(cats.items()):
    print(f"  {c:<16} {g:>10,} → {k:>10,}  ({(g-k)/g*100:.1f}%削減)")
print(f"  {'合計':<16} {rev_g:>10,} → {rev_k:>10,}  ({(rev_g-rev_k)/rev_g*100:.1f}%削減)")
print(f"  GDP比: {rev_g/GDP*100:.1f}% → {rev_k/GDP*100:.1f}%")

print("\n【フラットタックス 新税収試算】")
print(f"  課税ベース: 302兆円 × 7.8% = {flat_new:,} 億円")
print(f"  (参考) 現行 所得税+法人税+復興特別所得税: {253250+206960+380+5760+4938:,} 億円")
print(f"  フラット新税収 vs 現行: {flat_new:,} vs {253250+206960+380+5760+4938:,}")

print("\n【GDP比 目標との対比】")
print(f"  目標: 歳出19%  歳入18%")
print(f"  歳出: {exp_g/GDP*100:.1f}% → {exp_k/GDP*100:.1f}%  (一般会計のみ)")
print(f"  歳入: {rev_g/GDP*100:.1f}% → {rev_k/GDP*100:.1f}%  (国・公課ベース)")
print(f"  ※特別会計純計(216兆円)・地方財政(100兆円)は別途分析が必要")

print("\n【主要削減内訳（歳入トップ5）】")
items = [(r['項目名'], int(r['現行_億円']), int(r['改革後_億円']))
         for r in rev_rows
         if r['現行_億円'] and r['改革後_億円'] and
         '小計' not in r['項目名'] and '合計' not in r['項目名'] and
         int(r['現行_億円']) > 10000]
items.sort(key=lambda x: x[1]-x[2], reverse=True)
for name, g, k in items[:10]:
    print(f"  {name[:28]:<30} {g:>8,} → {k:>8,} (▲{g-k:,})")
