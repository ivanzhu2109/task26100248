# skillgap — 进程内技能缺口计算库

为销售教练系统提供个人/团队"最需提升的两个能力项"查询。纯 Python、零依赖，
不处理时钟、并发与持久化；90 日窗口由调用方控制，到期评估通过
`remove_evaluation` 显式移除。

## API

```python
from skillgap import SkillGapTracker

t = SkillGapTracker()
t.move_rep(rep_id, team_id)                 # 首次调用登记，之后为转队
t.set_evaluation(eval_id, rep_id, scores)   # 新增或完整替换；scores 为 {competency_id: 1..10}，3..12 项
t.remove_evaluation(eval_id)                # 幂等移除
t.gaps("rep", rep_id)                       # -> [(competency_id, Fraction mean), ...] 最多两项
t.gaps("team", team_id)
```

- 均值以 `fractions.Fraction` 返回，无损、精确比较，不存在舍入后再排序的问题。
- 排序：均值升序，相等时 `competency_id` 升序。
- 团队均值 = 当前成员个人均值（仅取含该能力项的评估）的等权平均；
  无该能力项数据的成员不进分母，评估多的 rep 不会获得更高权重。
- 评估不可跨 rep 迁移（`ValueError`）；未登记 rep 或不存在团队抛 `KeyError`。

## 实现与复杂度

每个 rep、每个团队各维护一个按 `(精确均值, competency_id)` 排序的索引最小堆
（`skillgap/heap.py`，支持按 id 定位的任意删除/更新）。修改评估时只对新旧评估
涉及的能力项做增量更新：先更新个人 `(总分, 次数)` 与个人堆，再把个人均值的
旧值/新值差量累进团队的 `(成员均值和, 有数据成员数)` 与团队堆。能力项的最后
一份贡献消失时，该项立即从对应堆中删除。

| 操作 | 时间 | 说明 |
|---|---|---|
| `gaps` | O(log C) | 弹出并回填最多 2 个堆顶，C 为该 scope 的能力项数 |
| `set_evaluation` | O(k log C) | k = 新旧评估涉及的能力项数（≤ 24） |
| `remove_evaluation` | O(k log C) | k = 该评估的能力项数（≤ 12） |
| `move_rep` | O(c log C) | c = 该 rep 当前有数据的能力项数，不扫描评估历史或成员集合 |

空间：O（有效评估数 + 已登记 rep 数 + 存活 (rep, 能力项） 与 （团队， 能力项） 条目数）。
无成员的团队结构被整体删除；堆内只存活着条目，不随累计修改次数、已删除评估数
或历史团队数增长。

## 测试

```bash
python3 -m pytest                 # 正确性测试（含与定义重算的差异性随机测试）
python3 -m pytest -m perf         # 20 万评估规模 + 10 万次更正/转队基准（约 1 分钟）
```

基准实测（本机）：加载 20 万评估 19.4s；查询约 34µs/次；10 万次更正/转队
约 232µs/次。churn 前后索引条目数完全由存活数据决定（1000 条存活评估 →
约 1.19 万条 (rep, 能力项） 条目），证明无历史垃圾累积。
