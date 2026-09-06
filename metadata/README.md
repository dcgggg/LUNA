# 元数据登记说明

所有表使用 CSV，空单元格表示未知或尚未获得，不用 `0` 代替未知天数、评分或时间。

## 表粒度和关系

| 表 | 一行代表什么 | 主键/关联 |
|---|---|---|
| `animals.csv` | 一只实验动物 | `animal_id` |
| `records.csv` | 一只动物的一次记录/session | `session_id`；关联 `animal_id` |
| `files.csv` | 一个输入 FIF 文件及其给药节点标签 | `file_id`；关联 `session_id` |
| `epochs.csv` | 一个 FIF 中保留/候选 epoch 的追溯行 | `file_id + saved_index` |
| `behavior.csv` | 一个动物×记录节点×给药时点的行为评分/视频信息 | 由 `animal_id + session_id + nominal_dose_time_min` 关联 |
| `channel_map.csv` | 一个实际通道名称到物理编号/脑区的确认映射 | `channel_name` |
| `field_dictionary.csv` | 字段定义和允许值说明 | `table_name + field_name` |

## 关键规则

- `drug` 明确区分 `L-DOPA` 与 `LDN`；LDN 的完整名称、剂量、安排未提供时留空。
- 给药前基线使用 `dose_state=pre_dose_baseline`，不得自动写成给药后 `0` 分钟。
- `nominal_dose_time_min` 是名义给药后时点，不等于每个 epoch 的精确起止时间。
- `events_raw_value`、`selection_value`、`drop_log` 原样保留。未核实上游裁剪/重采样历史前，不能把 event 值除以当前采样率解释为原始记录时间。
- `is_example` 只可在明确的示例/模拟行中使用；真实登记不应复制示例身份。
- 当前 `files.csv` 中的 T80 行是用户确认的已知样例，但标记为 `known_sample_unresolved_identity`；它只用于文件级运行，不代表动物身份已确认。
