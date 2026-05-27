# 策略规则后续修复设计

日期：2026-05-27

## 背景

`main` 当前已经包含 `ef4c367 Fix strategy rule contracts`。上一轮修复把指标动作收紧、把组合共振从乘数改成固定加分，并把规则结果与展示字段写入候选详情。

用户随后在策略页发现一个真实回归：组合共振区域显示两个空的“选择规则”下拉框，但没有可选项，既不能恢复旧共振，也不能新建可用共振。GPT Pro 对当前 `main` 的最新审查也指出了几个边界语义问题：缺失值会被误判为 score/risk 命中，正向共振可以引用 risk 规则，display-only 指标可能可选但结果页不展示，`limit_event` 的事件值输入不友好，覆盖率元数据尚未接入真实可用性。

这份设计覆盖两类输入：

- 用户实际反馈：组合共振规则消失、没法选。
- GPT Pro 审查：策略规则语义、展示字段、事件操作符、覆盖率提示、非活跃股票口径遗留问题。

其中 GPT Pro 文档后半段关于“策略规则合约没有 push 到 main”的判断已经过时；当前 `main` 已经包含这些代码。后半段仍然有效的部分是非活跃股票更新与市场环境口径漏洞。

## 目标

1. 旧组合共振不能静默消失；无法自动迁移时也要在 UI 中可见、可解释、可恢复。
2. 新组合共振在没有可选规则时不能显示成可操作的空控件。
3. `missing_policy="neutral"` 对 score/risk/resonance 不再表示命中；缺失值应不加分、不扣分、不触发共振。
4. 正向组合共振只能引用正向规则：`filter` 和 `score`。`risk` 规则不得触发正向加分。
5. display-only 指标只有在候选结果里真的能展示时，才允许出现在策略页展示规则里。
6. `limit_event` 使用用户可读枚举和推荐规则，而不是让用户手填 `U/D/Z`。
7. 覆盖率和 freshness 元数据从“预留字段”变成可见的数据质量提示，必要时禁用硬筛。
8. 补齐非活跃股票在完整/轻量更新、市场环境、数据仓库搜索上的剩余口径漏洞。

## 非目标

- 不恢复旧的共振乘数模型。
- 不让共振重新独立填写一套阈值。
- 不在本轮实现风险共振扣分模型；如果未来需要，应单独设计 `risk_resonances` 或 `penalty`。
- 不做公式编辑器、脚本规则、自动交易或券商接入。
- 不重构整个策略页信息架构；只修复本轮行为 bug 和必要的可解释性问题。

## 优先级

### P0：必须先修

1. 组合共振消失 / 没法选。
2. score/risk 规则缺失值被 `neutral` 当成命中。
3. 正向共振允许引用 risk 规则。

### P1：同一轮建议修

4. display-only 指标可选但候选结果不展示。
5. `limit_event` 事件状态输入改成枚举。
6. 旧共振迁移 warning 需要显示具体共振名称，并给恢复入口。

### P2：后续但应进入计划

7. coverage_group 接入真实覆盖率提示。
8. 非活跃股票完整/轻量更新和市场环境口径统一。
9. 数据仓库 6 位代码搜索自动 fallback 到非活跃结果。
10. data capability 的 `coverage_kind` 显式化。

## 当前根因分析

### 组合共振空掉

前端 `StrategyResonanceBuilder` 当前只从 `strategy.strategy_rules` 中取可选规则：

```ts
const activeRules = strategy.strategy_rules
  .filter((rule) => rule.enabled !== false && rule.action !== 'display')
  .filter((rule) => Boolean(indicatorById[rule.indicator_id]));
```

如果策略还没有补充指标规则，或者旧共振只保存了 `conditions + multiplier`，下拉框就没有候选项。

后端 `_normalize_strategy_resonances()` 当前迁移旧共振时，只在旧 conditions 能精确匹配已有 `strategy_rules` 时生成 `rule_ids`。无法匹配时直接跳过，然后只给一个数量级 migration warning。这避免了旧乘数继续执行，但也造成用户看到的“共振消失”。

### 缺失值误命中

`_strategy_rule_mask()` 会把 `missing_policy in {"keep", "allow", "neutral"}` 的缺失值 OR 成命中：

```py
if missing_policy in {"keep", "allow", "neutral"}:
    mask = mask | missing_mask
```

这个逻辑用于硬筛选时表示“不因缺失剔除”，但 `_strategy_rule_score_adjustment()` 和 `_matching_strategy_resonances()` 也复用了同一套命中判断，导致缺失字段可能获得加分、扣分或触发共振。

### risk 规则进入正向共振

前端只排除了 `display`，所以 `risk` 规则仍能被选入组合共振。当前共振只有正向 `bonus`，因此“过热风险命中 + 题材热”也可能触发正向加分，语义错误。

## 设计方案

### 1. 旧共振保留为可见的停用项

后端 normalization 不应静默丢弃用户写过的共振。规则如下：

1. 新格式 `rule_ids + bonus`：保留现有行为，只保留仍存在且可用于正向共振的规则 id。
2. 旧格式 `conditions + multiplier` 且能匹配至少两个现有规则：迁移为 `rule_ids + bonus`。
3. 旧格式无法匹配至少两个现有规则：保留为停用 legacy 共振，不参与执行。

停用 legacy 共振结构建议：

```json
{
  "id": "legacy-hot-volume",
  "name": "旧题材放量",
  "rule_ids": [],
  "bonus": 8,
  "enabled": false,
  "source": "legacy_unmatched",
  "migration_warning": "旧组合共振无法匹配已有规则，需先恢复为补充规则后才能启用。",
  "legacy_conditions": [
    {"indicator_id": "topic_heat", "operator": "gte", "value": 70},
    {"indicator_id": "volume_ratio", "operator": "gte", "value": 2}
  ]
}
```

`StrategyResonance` 类型新增可选字段：

```ts
source?: 'rule_ids' | 'legacy_unmatched' | string;
migration_warning?: string;
legacy_conditions?: StrategyRuleCondition[];
```

执行层必须忽略 `enabled=false`、`rule_ids` 少于 2 个、或 `source="legacy_unmatched"` 的共振。

### 2. 提供“从旧共振恢复规则”的用户路径

前端在 legacy 共振卡片中显示：

- 共振名称。
- 旧条件摘要，例如“题材热度 >= 70；量比 >= 2”。
- 加分值，例如“恢复后 +8 分”。
- 状态：`已停用 · 需重新绑定规则`。
- 操作按钮：`恢复为补充规则`、`删除`。

点击 `恢复为补充规则` 时，前端从 `legacy_conditions` 生成零权重的 backing rules：

```ts
{
  id: createRuleId(),
  indicator_id: condition.indicator_id,
  action: 'score',
  operator: condition.operator,
  value: condition.value,
  value2: condition.value2,
  weight: 0,
  missing_policy: condition.missing_policy || 'neutral',
  enabled: true
}
```

然后把该共振更新为：

```ts
{
  ...resonance,
  rule_ids: createdRuleIds,
  source: 'rule_ids',
  migration_warning: undefined,
  legacy_conditions: undefined,
  enabled: true
}
```

零权重 backing rules 的含义是“只作为共振条件，不单独加分”。用户仍可之后把这些规则改成真实 score/filter 规则。

### 3. 共振空态不再显示空下拉框

当 `activeRules.length < 2` 时：

- 不渲染两个空 select。
- 显示空态：

```text
还没有可用于共振的规则
先在“补充指标条件”里创建至少两个筛选或加分规则；共振只引用这些规则，不单独填写阈值。
```

- 如果存在 legacy 共振，则额外显示：

```text
检测到旧共振，可在下方卡片中恢复为补充规则。
```

当 `activeRules.length >= 2` 时，才显示规则选择器和新增按钮。

### 4. 正向共振只允许引用 filter / score

前端可选规则改为：

```ts
const resonanceEligibleRules = strategy.strategy_rules
  .filter((rule) => rule.enabled !== false)
  .filter((rule) => rule.action === 'filter' || rule.action === 'score')
  .filter((rule) => Boolean(indicatorById[rule.indicator_id]));
```

后端 normalization 和 scoring 也要做同样约束，不能只靠前端：

- `_normalize_strategy_resonances()` 只接受 action 为 `filter` 或 `score` 的 rule ids。
- `_matching_strategy_resonances()` 遇到 risk/display/missing rule 直接视为不满足。

如果旧配置里共振引用了 risk/display 规则，migration warning 写明：

```text
组合共振「高风险确认」引用了风险/展示规则，已停用；正向共振只能引用筛选或加分规则。
```

### 5. action-aware missing policy

把“缺失是否保留”和“规则是否命中”拆开。

建议新增 helper：

```py
def _value_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None


def _strategy_rule_matches_row(row: Dict[str, Any], rule: Dict[str, Any], action: str) -> bool:
    indicator = _strategy_rule_indicator(rule, action)
    if not indicator:
        return False
    column = str(indicator.get("analysis_field") or indicator.get("id") or "")
    if column not in row:
        return action == "filter" and str(rule.get("missing_policy") or "neutral") in {"keep", "allow", "neutral"}
    value = row.get(column)
    if _value_missing(value):
        if action == "filter":
            return str(rule.get("missing_policy") or "neutral") in {"keep", "allow", "neutral"}
        return False
    series = pd.Series([value])
    return bool(_strategy_rule_mask(series, rule, missing_matches=False).iloc[0])
```

`_strategy_rule_mask()` 应支持参数：

```py
def _strategy_rule_mask(series: pd.Series, rule: Dict[str, Any], missing_matches: bool = True) -> pd.Series:
    ...
    if missing_matches and missing_policy in {"keep", "allow", "neutral"}:
        mask = mask | missing_mask
```

使用规则：

- 硬筛选 DataFrame：`missing_matches=True`，保持“缺失不剔除”的能力。
- score/risk：`missing_matches=False`。
- resonance：通过 `_strategy_rule_matches_row(..., action)`，score/filter 行为分开。
- display：只展示实际存在的字段；缺失字段不生成显示值。

### 6. rule results 记录 missing 状态

`strategy_rule_results` 增加：

```json
{
  "missing": false,
  "reason": null
}
```

缺失但未命中的 score/risk 规则示例：

```json
{
  "rule_id": "main-flow-score",
  "indicator_id": "main_net_amount",
  "action": "score",
  "matched": false,
  "missing": true,
  "adjustment": 0,
  "reason": "字段缺失，未加分"
}
```

前端可在“规则影响”里显示“缺失未计分”，避免用户误以为规则坏了。

### 7. display-only 指标增加展示范围

`display_only` 还不够细。新增字段：

```ts
display_scope?: 'candidate' | 'warehouse' | 'planned' | string;
```

规则：

- `display_scope="candidate"`：分析候选 row 中有字段，可在策略页作为展示规则选择。
- `display_scope="warehouse"`：数据仓库/详情页可看，但候选结果不保证有字段；不进入策略页展示规则。
- `display_scope="planned"`：暂不可用。

第一轮建议：

| 指标 | display_scope |
| --- | --- |
| `top_list_net_amount` | `candidate` |
| `top_inst_net_buy` | `candidate` |
| `hot_money_net_amount` | `candidate` |
| `cost_50pct` | `candidate`，前提是分析帧已有该字段 |
| `macd_state` | `planned` 或 `warehouse`，除非候选 row 真的有 `macd_state` |
| `overheat_risk` | `planned`，除非拆成真实字段 |

前端策略规则选择器只允许：

- executable 指标的真实 action。
- display-only 且 `display_scope="candidate"` 的 display action。

### 8. limit_event 使用枚举和推荐规则

`limit_event` 元数据增加可选项：

```json
"choice_options": [
  {"value": "U", "label": "涨停"},
  {"value": "Z", "label": "炸板"},
  {"value": "D", "label": "跌停"}
]
```

推荐规则：

```json
[
  {"label": "今日涨停", "action": "score", "operator": "eq", "value": "U", "weight": 8},
  {"label": "今日炸板风险", "action": "risk", "operator": "eq", "value": "Z", "weight": 8},
  {"label": "今日跌停风险", "action": "risk", "operator": "eq", "value": "D", "weight": 15}
]
```

前端当 `operator_semantics === "event_state"` 且存在 `choice_options` 时，规则值输入渲染为 select。

### 9. 覆盖率和 freshness 提示

已有字段：

- `hard_filter_allowed`
- `min_coverage_for_filter`
- `freshness_required`
- `coverage_group`

下一步把它们接到 data capabilities：

```ts
type IndicatorCoverageInfo = {
  group: string;
  covered_count: number;
  denominator: number;
  latest_date?: string | null;
  coverage_ratio: number;
};
```

策略页规则选择时显示：

```text
资金流向 · 覆盖 4,932 / 5,203 · 最新 2026-05-27
```

禁用硬筛条件：

- `hard_filter_allowed !== true`
- 或 `min_coverage_for_filter` 存在且实时覆盖率低于阈值
- 或 `freshness_required=true` 且 latest date 过旧

禁用时文案要说明原因，不只隐藏按钮。

### 10. 非活跃股票口径遗留修复

这部分属于数据仓库/市场环境，不阻塞 P0 策略修复，但应进入同一个后续计划。

#### 更新路径

`_history_stocks_for_update()`：

- 完整更新分支加 `b.suspended IS DISTINCT FROM TRUE`。
- 轻量更新分支也显式加 `b.suspended IS DISTINCT FROM TRUE`。

#### 市场环境

`_build_market_environment_row()` 和 `_market_turnover_score()` 统计历史 K 线时 join `stock_basic`：

```sql
FROM historical_bars h
JOIN stock_basic b ON b.code = h.code
WHERE h.date = ?
  AND b.suspended IS DISTINCT FROM TRUE
```

过去 20 日成交额基准也使用同样活跃股票口径。

#### 数据仓库搜索

完整代码搜索扩展为支持 6 位代码：

```py
re.fullmatch(r"\d{6}(\.(SH|SZ|BJ))?", text.upper())
```

当 `status=active` 且 6 位/完整代码搜索为空时，自动 fallback 到 `status=all`，返回非活跃股票并带 `非活跃` badge。

#### capability definitions

所有 `CAPABILITY_DEFINITIONS` 显式声明：

- `coverage_kind="stock"`
- `coverage_kind="event"`
- `coverage_kind="dataset"`

不要依赖默认值，避免新增能力时分母口径漂移。

## 测试要求

### P0 tests

新增或修改 `backend/tests/test_strategy_service.py`：

- 旧 condition 共振无法匹配规则时，normalize 后仍保留 disabled legacy resonance，并包含 `migration_warning`、`legacy_conditions`。
- 旧 condition 共振可匹配规则时，仍迁移成 `rule_ids + bonus`。
- 共振引用 risk/display 规则时被停用或过滤，并写 migration warning。

新增或修改 `backend/tests/test_indicators.py`：

- score 规则字段缺失且 `missing_policy="neutral"` 时，`custom_rules == 0`。
- risk 规则字段缺失且 `missing_policy="neutral"` 时，不扣分。
- 共振引用的 score 规则字段缺失时，不触发 `resonance_bonus`。
- filter 规则字段缺失且 `missing_policy="neutral"` 时，仍不剔除候选。

新增或修改前端测试或构建期断言：

- `StrategyResonanceBuilder` 在可选规则少于 2 个时不渲染空 select。
- 可选共振规则只包含 `filter` / `score`。
- legacy resonance card 显示恢复入口。

### P1 tests

`backend/tests/test_indicator_registry.py`：

- `limit_event.choice_options` 包含 `U/Z/D`。
- `limit_event.recommended_rules` 包含涨停 score、炸板 risk、跌停 risk。
- `macd_state`、`overheat_risk` 不进入候选 display 规则，除非 display_scope 为 candidate。

前端 build：

- `npm --prefix frontend run build`

### P2 tests

`backend/tests/test_data_warehouse.py` 和 `backend/tests/test_market_environment.py`：

- 完整历史更新不返回 suspended 股票。
- 轻量历史更新不返回 suspended 股票。
- 市场环境宽度和成交额只统计 active 股票。
- 6 位代码搜索能 fallback 到非活跃股票。
- 每个 capability definition 都显式有 `coverage_kind`。

## 验收标准

1. 用户打开旧策略时，旧共振不会直接消失；无法迁移的旧共振以停用卡片出现，并说明原因。
2. 如果没有至少两个可用规则，共振区域显示清晰空态，不显示空下拉框。
3. 创建两个 score/filter 规则后，共振下拉框能正常选择规则并创建 `rule_ids + bonus` 共振。
4. risk/display 规则不会出现在正向共振选择器里。
5. 缺失字段不会给 score/risk 加扣分，也不会触发共振。
6. 结果详情能区分“命中”“未命中”“缺失未计分”。
7. `limit_event` 的值输入是涨停/炸板/跌停枚举，不要求用户记住 `U/Z/D`。
8. display-only 指标只有候选结果能展示时才出现在策略页展示规则中。
9. 非活跃股票不再进入默认完整/轻量历史更新和市场环境口径。
10. 后端全量测试和前端 build 通过。

## 实施拆分建议

虽然本 spec 收录了 GPT Pro 和用户反馈的全部问题，但实现时建议拆成两个计划：

1. `strategy-rule-followup-fixes`：P0 + P1，直接修策略页和策略执行语义。
2. `inactive-stock-coverage-followup`：P2，修更新路径、市场环境和数据仓库搜索口径。

这样第一轮可以尽快解决用户现在看到的共振回归，不被数据口径修复拖住。

## 自审

- 没有恢复旧乘数模型，仍保持规则引用式共振方向。
- 用户反馈的“组合共振规则消失、没法选”已作为 P0，并给出后端迁移和前端空态两侧修复。
- GPT Pro 的 P0/P1/P2 建议均已归入设计；过时的“未 push 到 main”判断已明确排除。
- 每个行为改变都有对应测试要求和验收标准。
