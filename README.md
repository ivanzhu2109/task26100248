# skill-gaps

进程内技能缺口计算库，供销售教练系统查询个人/团队最需要提升的两个能力项。
纯 Python、零依赖，不涉及时钟、并发与持久化；90 日窗口由调用方控制，
到期评估通过 `remove_evaluation` 显式移除。

## API

```python
from skill_gaps import SkillGapTracker

t = SkillGapTracker()
t.move_rep("rep1", "teamA")                 # 首次调用登记，之后调用转队
t.set_evaluation("ev1", "rep1", {3: 7, 5: 4, 8: 9})   # 新增或完整替换
t.remove_evaluation("ev1")                  # 重复移除无效果
t.gaps("rep", "rep1")                       # [(competency_id, Fraction), ...]
t.gaps("team", "teamA")
```

- `scores`：dict，3–12 个整数 `competency_id`，分数为 1–10 的整数。
  已有评估不能更换 rep（抛 `ValueError`）；未登记 rep 抛 `KeyError`。
- `gaps(scope, id)` 返回 `[(competency_id, fractions.Fraction), ...]`，
  按精确均值升序、并列按 `competency_id` 升序；不足两个则全部返回。
  `Fraction` 无损表达均值，比较全程不舍入、无误差容忍区间。
- 未登记/已清空的 id 查询抛 `KeyError`；团队无数据时返回空列表。

## 语义

- 个人均值：仅取本人包含该能力项的有效评估。
- 团队均值：先算各成员个人均值，再对**有该项数据**的成员等权平均；
  无数据成员不进分母，评估次数多不会获得更高权重。
- 替换评估可同时增删能力项；某能力项最后一份贡献消失时，
  它立即从相应候选集合中消失。

## 实现与复杂度

每个 rep 和每个 team 各维护一个按 `(精确均值, competency_id)` 排序的
随机 treap（`skill_gaps/treap.py`）。团队聚合按能力项保存
`(成员均值之和, 有数据成员数)`，成员均值用 `Fraction` 精确累加，
任何修改都是「撤销旧贡献 + 施加新贡献」的增量更新。

记 `k` = 单条评估的能力项数（≤12），`c` = 单个 rep 当前有数据的能力项数，
`C` = 候选能力项总数（≤2000）：

| 操作 | 时间 | 说明 |
| --- | --- | --- |
| `gaps` | O(log C) | treap 取最小两项，不扫描评估/成员/候选集 |
| `set_evaluation` | O(k log C) 摊销 | 仅触碰新旧评估涉及的能力项 |
| `remove_evaluation` | O(k log C) 摊销 | 同上 |
| `move_rep` | O(c log C) | 只搬运该 rep 当前有数据的能力项，不扫描其评估历史或两队成员 |

空间 O(有效评估涉及的能力项条目数 + 已登记 rep 数)。评估删除、rep 离队的
最后一名成员都会触发对应索引项的物理删除（无惰性删除墓碑），因此内存不随
累计修改次数、已删除评估数或历史团队数增长。

## 测试

```bash
python3 -m unittest discover -s tests -v      # 全部测试
python3 -m unittest tests.test_correctness    # 团队等权语义 + 精确并列排序
python3 -m unittest tests.test_differential   # 随机操作 vs 定义重算的对拍
python3 -m unittest tests.test_scale          # 20 万评估 + 10 万次更正/转队（约 2 分钟）
```

- `test_correctness`：同队两名 rep 评估频率悬殊（50:1）且覆盖不同，
  证明团队均值是成员均值的等权平均而非全部评估的直接平均；
  覆盖同分母/跨分母精确并列排序与近邻但不等均值的区分。
- `test_differential`：4000 步随机替换/移除/转队与朴素重算逐步核对，
  并断言出现了「一次操作同时改变两个团队最低两项」和
  「能力项失去最后一份贡献后消失」的场景。
- `test_scale`：20 万条有效评估构建与查询计时；随后仅留 200 条存活评估
  反复更正/转队 10 万次，记录修改与查询耗时，并用索引条目数快照与
  tracemalloc 净增量证明无历史垃圾累积。
