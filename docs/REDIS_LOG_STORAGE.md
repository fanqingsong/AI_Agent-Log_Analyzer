# Redis 日志存储模块技术文档

> 模块文件：`app/logs/repository.py`
> 配置文件：`app/config.py`（Redis 段）

---

## 1. 角色定位

Redis 在本系统中**只承担短期日志缓冲**，**不是持久化存储**。其唯一目的是为 LLM 智能体分析时提供一个"**时间窗口上下文**"——当一条 `ERROR`/`WARN` 日志触发分析时，能快速取出它**之前**的若干条日志，一起交给智能体判断错误模式与根因。

| 维度 | Redis | PostgreSQL |
|---|---|---|
| 职责 | 短期缓冲（提供上下文窗口） | 长期持久化（聊天历史、分析结果） |
| 保留时长 | 15 分钟（TTL 自动过期） | 永久 |
| 数据特征 | 原始日志（含 INFO/WARN/ERROR 全级别） | 仅触发分析的日志结果与用户对话 |
| 访问模式 | 按**时间范围**切片查询 | 按 `chatId` 检索 |

> 设计动机：日志是高频写入、低价值密度（绝大多数是 INFO）的数据流。如果全部直接进 PostgreSQL，既拖慢写入又撑爆数据库；而 LLM 分析"错误根因"时，只需要错误发生前后的几条上下文即可。因此用 Redis 做一个 15 分钟的滚动窗口，恰好覆盖"取前 5 条上下文"的需求。

---

## 2. 数据结构设计：双写模型

每条日志入库时执行**双写**——String 主存 + Sorted Set 时间索引，二者分工不同。

### 2.1 String 主存

```
key:   <微秒时间戳>:<6位UUID>      例: 1732345678901234:a3f9c1
value: 日志的 JSON 文本
TTL:   900 秒（15 分钟）
```

对应 Redis 命令：`SET <id> <json> EX 900`

- **key 设计**：`微秒时间戳` 前缀保证字典序与时间序一致，且天然唯一；`UUID` 后缀兜底同一微秒内的并发碰撞。
- **TTL 的意义**：让 Redis 只保留最近 15 分钟的日志，老数据自动回收，无需手动清理。

### 2.2 Sorted Set 时间索引（`temp_logs`）

```
member: 日志 ID（同上）
score:  微秒时间戳
```

对应 Redis 命令：`ZADD temp_logs <微秒时间戳> <id>`

- **为什么用 ZSET**：String 类型本身不支持"按时间范围"查询，只能精确 key 查找。而取上下文需要的是"时间在某区间内的若干条"，这必须依赖有序结构。
- **score 直接复用 ID 前缀**：因为 ID 前缀就是微秒时间戳，`int(redis_log_id.split(":")[0])` 直接当 score，保证"插入顺序"与"时间排序"一致。

### 2.3 双写的协同与"悬空成员"问题

| 操作 | String | ZSET |
|---|---|---|
| 写入 | `SET <id> <json> EX 900` | `ZADD temp_logs <ts> <id>` |
| 过期 | 15 分钟后自动删除 key | **不会自动删除成员** |

由此产生**悬空成员**：String key 已过期被删除，但 ZSET 里的成员 ID 还在。`get_logs_before` 用 `mget` 取这类 ID 时会得到 `None`，需在代码层过滤（见 §3.2）。

> 这是性能与一致性的折中：若要严格清理 ZSET，需要为每条日志设置过期回调或定时扫描，复杂度较高。当前方案接受少量悬空成员，靠 `None` 过滤兜底，性能更优。

---

## 3. 核心函数详解

### 3.1 `make_redis_log_id()` —— ID 生成器

```python
def make_redis_log_id() -> str:
    micros_timestamp = int(time.time() * 1_000_000)
    uuid_suffix = uuid4().hex[:6]
    return f"{micros_timestamp}:{uuid_suffix}"
```

- `微秒时间戳`：`time.time() * 1_000_000`，保证时间分辨率足够细，同时作为后续 ZSET 的 score。
- `6 位 UUID`：兜底同一微秒并发的碰撞。
- 格式：`<微秒时间戳>:<6位hex>`，冒号分隔便于 `split(":")[0]` 还原时间戳。

### 3.2 `store_log_redis()` —— 写入

```python
async def store_log_redis(redis_db, redis_log_id, entry):
    LOG_TTL = 15 * 60
    micros_timestamp = int(redis_log_id.split(":")[0])
    await redis_db.set(redis_log_id, json.dumps(entry), ex=LOG_TTL)   # ① String 主存
    await redis_db.zadd("temp_logs", {redis_log_id: micros_timestamp}) # ② ZSET 索引
```

| 步骤 | Redis 命令 | 作用 |
|---|---|---|
| ① | `SET <id> <json> EX 900` | 写入日志正文，15 分钟过期 |
| ② | `ZADD temp_logs <ts> <id>` | 登记时间索引，支持后续按 score 范围查询 |

### 3.3 `get_logs_before()` —— 上下文窗口查询（重点）

这是 Redis 模块最核心、也最容易混淆的函数。它的目标：**取出参考日志之前（更早）的最多 N 条日志**。

```python
log_ids = await redis_db.zrangebyscore(
    "temp_logs",
    min='-inf',
    max=ref_timestamp - 1,
    start=0,
    num=num_of_logs,
)
```

#### 关键：两组参数属于不同维度

`zrangebyscore` 的参数可以分成两组，作用在**完全不同的轴上**。

**① `min` / `max` —— 作用在 score（时间戳）轴上，做范围过滤**

| 参数 | 取值 | 含义 |
|---|---|---|
| `min` | `'-inf'` | 下界为负无穷，即从最早一条开始 |
| `max` | `ref_timestamp - 1` | 上界为"当前日志时间戳 - 1 微秒" |

`-1` 微秒是关键技巧：因为 score 是微秒级整数，减 1 微秒就能**精确排除当前日志自身**，只取"严格之前"的日志。

等价 Redis 命令片段：`ZRANGEBYSCORE temp_logs -inf <ref_ts - 1>`

> 业务语义：选出"**时间上更早**"的所有候选日志。

**② `start` / `num` —— 作用在结果集上，做分页切片（LIMIT）**

| 参数 | 取值 | 含义 |
|---|---|---|
| `start` | `0` | 偏移量，从筛选结果的第一条开始 |
| `num` | `num_of_logs`（默认 5） | 最多取多少条 |

这组参数**完全不碰 score**，是对上一步筛选结果做切片，等价于 Python 的 `list[start : start+num]` 或 SQL 的 `LIMIT start, num`。

等价 Redis 命令片段：`LIMIT 0 5`

> 业务语义：在"时间更早"的候选里**只取最近 5 条**。

#### 完整执行顺序与 SQL 类比

整个过程可类比为一条 SQL：

```sql
SELECT log_id FROM temp_logs
WHERE score BETWEEN -inf AND ref_timestamp - 1   -- 对应 min/max
ORDER BY score ASC                                -- ZSET 天然有序
LIMIT 0, 5;                                       -- 对应 start/num
```

执行顺序：

```
[全量 ZSET] --min/max 按 score 过滤--> [候选集] --升序排列--> [有序候选] --start/num 切片--> [最终结果]
```

#### 三步完整流程

```python
# 步骤一：ZRANGEBYSCORE 取出符合条件的日志 ID（按时间升序）
log_ids = await redis_db.zrangebyscore("temp_logs", min='-inf', max=ref_ts-1, start=0, num=5)

# 步骤二：MGET 一次性批量取出这些 ID 的 JSON 内容（单次往返，比循环 GET 高效）
log_entries = await redis_db.mget(log_ids)

# 步骤三：过滤悬空成员（ZSET 残留但 String 已过期的 ID，mget 返回 None）
return [{"log_id": lid, "message": e} for lid, e in zip(log_ids, log_entries) if e is not None]
```

| 步骤 | Redis 命令 | 目的 |
|---|---|---|
| 一 | `ZRANGEBYSCORE` | 按 score 范围 + LIMIT 取出 ID 列表 |
| 二 | `MGET` | 批量取正文（1 次网络往返） |
| 三 | Python 过滤 | 剔除 `None`（悬空成员） |

#### 具体示例

假设当前日志时间戳为 `1000`，想取前 3 条，ZSET 当前内容：

| member | score |
|---|---|
| `log_A` | 800 |
| `log_B` | 900 |
| `log_C` | 950 |
| `log_D` | 1000（**当前日志，需排除**） |
| `log_E` | 1100（更晚，需排除） |

- `min=-inf, max=999` → 筛出 `{log_A(800), log_B(900), log_C(950)}`，排除 `log_D`（自身）和 `log_E`（更晚）
- `start=0, num=3` → 取这 3 条全部
- 最终返回 `[log_A, log_B, log_C]`（按时间升序）

---

## 4. 设计要点与权衡

### 4.1 为什么用微秒时间戳而不是毫秒或秒？

- **秒**：同一秒内多条日志会碰撞，且 score 精度不足以排序。
- **毫秒**：通常够用，但高并发场景仍可能碰撞。
- **微秒**：碰撞概率极低，且 ID 前缀即时间戳，一份字段两用（唯一性 + 排序依据）。

### 4.2 升序查询的语义提示

`zrangebyscore` 默认**升序**，`start=0` 取的是**时间最旧**的那批，而非"离当前日志最近的"。本项目的业务意图是"取前 5 条上下文"：

- 若实际想要"最近的 5 条"，应改用 `zrevrangebyscore`（降序）。
- 当前实现下，由于日志间隔通常很短、TTL 仅 15 分钟，候选集往往不足 5 条，影响可忽略。

### 4.3 为什么 ZSET 不设 TTL？

Redis 原生**不支持**对 ZSET 的单个成员设 TTL（只能对整个 key 设）。可选的清理方案：

| 方案 | 复杂度 | 当前采用 |
|---|---|---|
| 接受悬空成员，查询时用 `None` 过滤 | 低 | ✅ |
| 定时任务扫描清理 ZSET | 中 | ❌ |
| Redis Keyspace Notifications + 过期回调 | 高 | ❌ |

### 4.4 性能特征

| 操作 | 时间复杂度 | 说明 |
|---|---|---|
| `store_log_redis` | O(log N) | `ZADD` 的复杂度，N 为 ZSET 大小 |
| `get_logs_before` | O(log N + M) | `ZRANGEBYSCORE` 为 O(log N + M)，M 为返回数；`MGET` 为 O(M) |

由于 TTL 限制，ZSET 实际大小受限于 15 分钟内的日志量，N 不会无限增长，性能稳定。

---

## 5. 配置项

配置位于 `app/config.py`，通过环境变量注入（`sample.env` 提供模板）：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis 主机 |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `REDIS_DB` | `0` | Redis 逻辑库编号 |

TTL（15 分钟）和 `num_of_logs`（默认 5）目前为代码内常量，如需运行时可调，可改为环境变量。

---

## 6. 速查表：函数 ↔ Redis 命令

| 函数 | 对应 Redis 命令 |
|---|---|
| `redis_init` / `test_redis_conn` | `PING` |
| `make_redis_log_id` | （纯 Python，无 Redis 操作） |
| `store_log_redis` | `SET <id> <json> EX 900` + `ZADD temp_logs <ts> <id>` |
| `get_logs_before` | `ZRANGEBYSCORE temp_logs -inf <ts-1> LIMIT 0 N` + `MGET <id1> <id2> ...` |

---

## 7. 一图总览

```
日志进入
   │
   ▼
make_redis_log_id()  →  ID = "<微秒时间戳>:<6位UUID>"
   │
   ▼
store_log_redis()  ──双写──┐
   │                       │
   ├─→  String 主存         │  SET <id> <json> EX 900
   │    (key=ID, TTL=15min) │  （15 分钟后自动过期）
   │                       │
   └─→  ZSET 时间索引       │  ZADD temp_logs <微秒ts> <id>
        temp_logs           │  （不自动过期，留悬空成员）
                            │
                            ▼
                  ERROR/WARN 触发 LLM 分析
                            │
                            ▼
              get_logs_before(ref_log_id, N=5)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ① ZRANGEBYSCORE      ② MGET             ③ 过滤 None
   按 score 范围过滤     批量取正文          剔除悬空成员
   (-inf ~ ref_ts-1)   (一次往返)          (ZSET 残留 ID)
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                            ▼
                  [最多 5 条上下文日志]
                            │
                            ▼
                  交给 LLM 智能体分析
```
