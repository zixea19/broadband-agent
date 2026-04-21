# Token 用量查询手册

数据库路径：`data/sessions.db`（observability 库，同步写入 JSONL `data/logs/trace/YYYY-MM-DD.jsonl`）

```bash
sqlite3 data/sessions.db
```

---

## 1. 查当前有哪些会话

```sql
SELECT id, session_hash, created_at, ended_at, task_type
FROM sessions
ORDER BY created_at DESC
LIMIT 20;
```

---

## 2. 按 SubAgent 汇总某次会话的 token 用量

`llm_calls` = 该 Agent 在本次会话里独立调用 LLM 的次数。

```sql
SELECT
    agent_name,
    SUM(json_extract(payload_json, '$.input_tokens'))     AS input_tokens,
    SUM(json_extract(payload_json, '$.output_tokens'))    AS output_tokens,
    SUM(json_extract(payload_json, '$.total_tokens'))     AS total_tokens,
    SUM(json_extract(payload_json, '$.reasoning_tokens')) AS reasoning_tokens,
    COUNT(*)                                               AS llm_calls
FROM traces
WHERE event_type = 'llm_usage'
  AND session_id = <SESSION_ID>
GROUP BY agent_name
ORDER BY total_tokens DESC;
```

**典型输出说明**

| agent_name | 含义 |
|---|---|
| `orchestrator` | Team leader（意图识别 + 路由 + 汇总），coordinate 模式下每轮派发都调用一次 |
| `planning` | PlanningAgent，goal_parsing / plan_design / plan_review / plan_store 各占若干次 |
| `insight` | InsightAgent，Plan→Decompose→Execute→Reflect→Report 每阶段一次 |
| `provisioning-wifi` | ProvisioningWifiAgent |
| `provisioning-delivery` | ProvisioningDeliveryAgent |
| `provisioning-cei-chain` | ProvisioningCeiChainAgent |

---

## 3. 展示调用时序流（orchestrator → planning → orchestrator → provisioning-wifi …）

按时间展开每次 LLM 调用，直观看到各 Agent 的交替顺序和每步 token 消耗。

```sql
SELECT
    ROW_NUMBER() OVER (ORDER BY created_at)            AS seq,
    agent_name,
    json_extract(payload_json, '$.input_tokens')       AS input,
    json_extract(payload_json, '$.output_tokens')      AS output,
    json_extract(payload_json, '$.total_tokens')       AS total,
    json_extract(payload_json, '$.reasoning_tokens')   AS reasoning,
    substr(created_at, 12, 8)                          AS time
FROM traces
WHERE event_type = 'llm_usage'
  AND session_id = <SESSION_ID>
ORDER BY created_at;
```

> **为什么 orchestrator 的 input 会在某次突然变大？**  
> 每次 SubAgent 完成后，其工具调用结果被追加到消息历史；orchestrator 再次调用时把完整历史全部带入，input token 随之"滚雪球"增长。

---

## 4. 跨所有会话按 Agent 汇总

```sql
SELECT
    agent_name,
    SUM(json_extract(payload_json, '$.total_tokens'))  AS total_tokens,
    COUNT(*)                                            AS llm_calls
FROM traces
WHERE event_type = 'llm_usage'
GROUP BY agent_name
ORDER BY total_tokens DESC;
```

---

## 5. 查某次会话的完整 trace 事件列表

```sql
SELECT
    id,
    event_type,
    agent_name,
    substr(created_at, 1, 19) AS ts,
    substr(payload_json, 1, 120)  AS payload_preview
FROM traces
WHERE session_id = <SESSION_ID>
ORDER BY created_at;
```

常见 `event_type`：

| event_type | 含义 |
|---|---|
| `request` | 用户消息进入 |
| `llm_usage` | 单次 LLM API 调用的 token 计量（含 agent 字段） |
| `llm_prompt` | 发送给 LLM 的完整 messages + tools（由 inject_prompt_tracer 触发） |
| `thinking` | LLM 推理内容（reasoning token 段） |
| `tool_invoke` | Skill 调用开始 |
| `tool_result` | Skill 调用完成（含 latency_ms） |
| `member_content` | SubAgent 的文本回复 |
| `member_completed` | SubAgent 运行完成 |
| `response` | Team leader 最终回复（含本次会话累计 token 汇总） |
| `error` | 异常事件 |

---

## 6. 查 response 事件中记录的会话级 token 汇总

`response` 事件的 payload 里存有整次会话的累计 token（所有 Agent 合计）。

```sql
SELECT
    session_id,
    json_extract(payload_json, '$.input_tokens')     AS total_input,
    json_extract(payload_json, '$.output_tokens')    AS total_output,
    json_extract(payload_json, '$.total_tokens')     AS grand_total,
    json_extract(payload_json, '$.reasoning_tokens') AS total_reasoning,
    substr(created_at, 1, 19)                        AS ts
FROM traces
WHERE event_type = 'response'
ORDER BY created_at DESC
LIMIT 20;
```
