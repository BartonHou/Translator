# Translator Platform — 详细改造计划 (planning2.md)

> 制定日期：2026-07-04
> 前置：本文是 `planning.md` §5「待拍板决策」敲定后的落地版。决策已锁定，下面是具体怎么改。
> 定位：**面向用户的正式产品**（不是演示）。

---

## 0. 已锁定的架构决策

| 决策项 | 结论 | 对本计划的影响 |
|---|---|---|
| 翻译路由 | **保留枢轴多模型**（Helsinki opus-mt + 英语枢轴） | 不引入 NLLB；重心放在把 ModelManager 做稳、修正错误模型名 |
| 用户体系 | **真正的用户体系**（注册/登录 + 用户拥有多个 API Key + 配额/用量） | 新增 users / api_keys / usage 表，两套鉴权（Web JWT + API Key）|
| 产品定位 | **面向用户的产品** | 前端去 mock、接真实能力、加登录与账户页 |
| 硬件 | **优先 GPU，无 GPU 自动回退 CPU** | Device 自动探测 + 动态批处理（GPU）+ 降级文档 |
| 额外功能 | **全做** | 语言检测 / SSE 流式 / 术语表 / 真实质量分 / 文件翻译 / 可观测性 / Webhook / 限流升级 |

---

## 1. 总体分期（里程碑）

```
M0 工程基线        ──┐
M1 核心稳定性修复    ├─ 打地基（不改契约）
M2 GPU/CPU 与吞吐  ──┘
M3 用户体系 & 鉴权   ── 产品化核心（改契约，需迁移）
M4 前端产品化        ── 去 mock + 账户 + 异步流
M5 翻译能力增强      ── 语言检测 / 流式 / 术语表 / 质量分
M6 文件翻译 & Webhook ── 基于 jobs 架构扩展
M7 可观测性 & 运维   ── Prometheus/Grafana + 限流升级
```

依赖关系：M0→M1→M2 可顺序做；M3 是产品化分水岭（引入 DB 迁移）；M4 依赖 M3；M5/M6/M7 相对独立，可并行。

---

## 2. M0 — 工程基线（0.5–1 天）

目标：让后面每一步都有 CI 兜底、依赖单一来源。

- [ ] **CI**：`.github/workflows/ci.yml` — 后端 `python -m unittest`，前端 `npm ci && npm test`，PR 必过。
- [ ] **Lint/format**：引入 `ruff` + `black` + `mypy`（宽松），`.pre-commit-config.yaml`。
- [ ] **依赖单一来源**：删 `requirement.txt`，一切以 `pyproject.toml` 为准；修 `[tool.setuptools] packages = ["app","domain","infra","workers"]`（当前只有 `app`，见 `pyproject.toml:24`）。
- [ ] **数据库迁移工具**：引入 **Alembic**（M3 起表结构频繁变化，`Base.metadata.create_all` 不够用）。
- [ ] `.env.example` + `Makefile`（`make dev` / `make test` / `make up`）。

---

## 3. M1 — 核心稳定性修复（1–2 天）

对应 planning.md §2.1/§2.2 的高中危项。

- [ ] **ModelManager 并发锁 + LRU 淘汰**（`app/inference/model_manager.py`）
  - 按 `model_name` 加锁，避免并发首载重复 `from_pretrained`。
  - `OrderedDict` + `MAX_LOADED_MODELS`（新设置项）做 LRU 淘汰，淘汰时释放显存/内存（`del model; torch.cuda.empty_cache()`）。
- [ ] **注册表健康检查 + 可用性标注**（`app/core/routing.py`, `v1_models.py`）
  - 修正可疑模型名：`opus-mt-en-jap`(en→ja)、`en-ko`/`ko-en`、`en-zh` 需逐一在 HF 上核实存在性与命名。
  - 新增 `scripts/check_registry.py`：启动或 CI 时校验每个模型可加载；`/v1/models` 输出增加 `available: bool`。
- [ ] **Metrics 降基数**（`app/main.py:78` 及各路由）
  - label 用路由模板 `request.scope["route"].path`（`/v1/jobs/{job_id}`）而非真实 URL，避免 UUID 撑爆序列。
- [ ] **datetime 时区化**：全量 `datetime.utcnow()` → `datetime.now(timezone.utc)`（`domain/models.py`、`workers/tasks.py`、`v1_jobs.py`）。
- [ ] **Redis 降级**（`infra/cache.py`）：读失败降级为 miss（记 metric）而非抛错；限流失败策略化（`RATE_LIMIT_FAIL_OPEN` 开关）。
- [ ] **`require_api_key` 去重**：抽到 `app/api/deps.py`，用 `secrets.compare_digest`（此逻辑在 M3 会被用户体系替换，先做临时统一）。
- [ ] **Redis 依赖统一**（`v1_jobs.py:27`）：`create_job` 改用注入的 `get_redis(request)`，不再每请求新建连接。

---

## 4. M2 — GPU/CPU 与吞吐（1–2 天）

- [ ] **Device 自动探测**（`app/settings.py`, `model_manager.py`）
  - `DEVICE=auto`（新默认）：有 CUDA 用 GPU，否则 CPU；`cuda`/`cpu` 仍可强制。
  - `/health` 与启动日志打印实际使用的 device、GPU 名、显存。
- [ ] **半精度**：GPU 上 `torch_dtype=float16`（可配 `TORCH_DTYPE`），显著省显存提速。
- [ ] **动态批处理（micro-batching）**：新增 `app/inference/batcher.py`，用短时间窗（如 20ms）合并并发请求的句子成大 batch 再送 GPU；CPU 下退化为直通。
- [ ] **压测脚本** `scripts/bench.py`（locust 或简单 asyncio），记录 CPU vs GPU 的 p50/p95、吞吐。
- [ ] **文档**：README 增加 GPU 部署（`docker-compose.gpu.yml` + `deploy.resources.reservations.devices`）与 CPU 回退说明。

---

## 5. M3 — 用户体系 & 鉴权（3–5 天，产品化核心）

### 5.1 数据模型（Alembic 迁移）

新增表（`domain/models.py`）：

```
users
  id            uuid pk
  email         unique, indexed
  password_hash str           # argon2/bcrypt
  role          enum(user, admin) default user
  is_active     bool
  created_at / updated_at

api_keys
  id            uuid pk
  user_id       fk -> users.id
  name          str           # 用户自定义，如 "生产环境"
  key_prefix    str(8)        # 明文前缀，用于展示 "tk_ab12…"
  key_hash      str           # 完整 key 只在创建时返回一次，库里存 hash
  rpm_limit     int           # 每 key 限流
  monthly_quota int null      # 每月字符/请求配额，null=无限
  is_active     bool
  last_used_at  datetime null
  created_at

usage_records                 # 用量与计费基础
  id            uuid pk
  api_key_id    fk
  day           date, indexed
  requests      int
  chars_in      bigint
  chars_out     bigint
  (api_key_id, day) unique     # 按天聚合，避免每请求一行
```

`translation_jobs` 增列：`api_key_id`（归属）、`chars_in`/`chars_out`。

### 5.2 两套鉴权

| 场景 | 方式 | 说明 |
|---|---|---|
| Web 前端 | 邮箱/密码登录 → **JWT**（access + refresh） | 供账户页、控制台使用 |
| API 调用方 | **X-API-Key**（`tk_` 前缀） | 面向程序化调用，key 属于某用户 |

- [ ] **鉴权重写**（`app/api/deps.py`, 新增 `app/core/auth.py`）
  - `get_current_user`（JWT 依赖）与 `get_api_key_context`（X-API-Key → 查 api_keys 表，返回 user+quota）。
  - key 校验用 hash 比对；命中后异步更新 `last_used_at`（不阻塞请求）。
- [ ] **限流按 key**（`infra/rate_limit.py`）：`rl:{api_key_id}:{window}`，rpm 取该 key 的 `rpm_limit`（不再全局 `settings.rate_limit_rpm`）；升级为滑动窗口（见 M7）。
- [ ] **配额扣减**：翻译成功后累加 `usage_records`（Redis 计数 + 定期 flush 到 DB，避免热点写库）；超月配额返回 402/429。

### 5.3 新增账户/管理接口

```
POST /v1/auth/register        邮箱+密码注册
POST /v1/auth/login           → JWT
POST /v1/auth/refresh
GET  /v1/me                   当前用户信息
GET  /v1/me/keys              列出我的 API Key（不返回明文）
POST /v1/me/keys              创建 Key（明文仅此次返回）
DELETE /v1/me/keys/{id}       吊销
GET  /v1/me/usage             用量统计（按天/按 key）
# admin
GET  /v1/admin/users          （role=admin）
```

- [ ] 密码哈希用 `argon2-cli`/`passlib`；JWT 用 `python-jose`；新增设置 `JWT_SECRET`、`ACCESS_TTL`、`REFRESH_TTL`。
- [ ] 保留一条兼容路径：现有 `dev-api-key` 作为「种子用户/种子 key」通过迁移写入，避免现有前端一上来就废。

---

## 6. M4 — 前端产品化（3–4 天）

去掉 `frontend/src/App.jsx` 里的假元素（tone 不发后端、confidence/queue/recent 全 mock），接真实能力。

- [ ] **登录/注册页** + JWT 存储（httpOnly 优先，或内存+refresh）；未登录跳登录。
- [ ] **账户/控制台页**：API Key 管理（创建/吊销/复制一次性明文）、用量图表（复用 dataviz 规范）。
- [ ] **翻译页真实化**：
  - `tone` 要么接后端（作为 prompt/后处理，见 M5 术语/风格），要么移除。
  - `confidence` 换成 M5 的真实质量分；`Recent Translations` 换成 localStorage/后端真实历史；移除写死的 `Queue: 0 pending` 或接真实队列深度指标。
- [ ] **异步 job 流**：大文本/批量 → 提交 job → 轮询 `GET /v1/jobs/{id}` 进度 → 展示结果/下载。
- [ ] **语言选择**：加「自动检测」选项（M5）。
- [ ] 前端测试（RTL）：登录态、错误态、异步流。

---

## 7. M5 — 翻译能力增强（3–5 天）

- [ ] **语言自动检测**（`app/core/lang_detect.py`）
  - `fasttext-langdetect` 或 `lingua`；`source_lang="auto"` 时先检测再路由；响应回传 `detected_source_lang`。
- [ ] **SSE 流式翻译**：`POST /v1/translate/stream` 逐句返回（枢轴场景按最终段逐句 flush）；前端边翻边显示。注意：流式与句级缓存/去重需协调（先查缓存命中的句子立即 yield）。
- [ ] **术语表 / Glossary**（新增 `glossaries` 表，属于 user）
  - 上传术语对（源→目标强制映射）；推理前做占位符保护、推理后回填，保证术语不被模型改写。
  - 前端「tone/风格」可并入此模块（风格提示或后处理规则）。
- [ ] **真实质量分**（替换 mock confidence）
  - 方案 A（轻）：beam 分数归一化 / 长度比异常检测。
  - 方案 B（准）：回译（back-translation）+ 句向量相似度，异步在 job 里算，避免拖慢同步接口。
  - 先上 A，B 作为可选增强。

---

## 8. M6 — 文件翻译 & Webhook（2–3 天）

基于现有 Celery jobs 架构扩展，天然契合。

- [ ] **文件翻译**
  - `POST /v1/jobs/file`（multipart 上传 `.txt/.srt/.docx/.md`）→ 解析成段落 → 复用异步翻译 → 产出译文文件。
  - `GET /v1/jobs/{id}/download` 返回结果文件；大文件走对象存储（本地卷或 S3 兼容，设置 `STORAGE_BACKEND`）。
  - 解析器：txt/md 直读，srt 保留时间轴，docx 用 `python-docx` 保留段落结构。
- [ ] **Webhook 回调**：`JobCreateRequest.callback_url`（`domain/schemas.py:26` 已预留但未实现）
  - job 完成/失败后 POST 回调，带 HMAC 签名（`X-Signature`）；失败指数退避重试（复用 Celery）。

---

## 9. M7 — 可观测性 & 运维（1–2 天）

- [ ] **限流升级**（`infra/rate_limit.py`）：固定窗口（现有，边界有突刺）→ **滑动窗口**（Redis sorted set）或**令牌桶**（Lua 脚本原子化）。
- [ ] **可观测性栈**：`docker-compose.observability.yml`（Prometheus + Grafana + 预置面板）。
  - 面板指标：p95 翻译延迟、缓存命中率、队列深度、模型加载耗时、GPU 显存、每租户请求量、限流拒绝率、job 成功/失败率。
  - 补充新指标：`model_load_seconds`、`gpu_memory_bytes`、`queue_depth`、`quota_exceeded_total`。
- [ ] **就绪/存活探针**：`/health`（存活）+ `/ready`（探测 Redis/Postgres 连通）；docker-compose 加 `healthcheck`。
- [ ] **request_id 贯穿**：structlog contextvars 中间件，日志与响应头带 `X-Request-ID`。
- [ ] **结构化错误响应**：统一 error envelope（`{error: {code, message, request_id}}`）。

---

## 10. 测试策略（贯穿各期，不单列阶段）

| 层 | 用什么测 |
|---|---|
| 单元 | `engine`（分句/去重/句级缓存回填）、`orchestrator`（枢轴两段）、`rate_limit`（窗口边界）、`auth`（JWT/key hash）、`lang_detect` |
| 集成 | `fakeredis` + SQLite 内存库 + mock HF 推理，端到端跑 translate/jobs/auth |
| 前端 | RTL：登录态、异步流、错误态 |
| 迁移 | Alembic upgrade/downgrade 在 CI 跑一遍 |

目标：M3 起 PR 必须带测试，覆盖率不倒退。

---

## 11. 新增/改动文件一览（速查）

**新增**
```
alembic/…                         DB 迁移
app/core/auth.py                  JWT + API Key 上下文
app/core/lang_detect.py           语言检测
app/inference/batcher.py          动态批处理
app/api/v1_auth.py                注册/登录
app/api/v1_account.py             /me、keys、usage
app/api/v1_files.py               文件翻译
scripts/check_registry.py         注册表健康检查
scripts/bench.py                  压测
docker-compose.gpu.yml            GPU 部署
docker-compose.observability.yml  监控栈
.github/workflows/ci.yml          CI
frontend/src/pages/…              登录/账户/控制台页
```

**重点改动**
```
app/inference/model_manager.py    锁 + LRU + GPU/fp16
app/core/routing.py               修正模型名 + 可用性
app/api/deps.py                   统一鉴权依赖
infra/rate_limit.py               按 key + 滑动窗口
infra/cache.py                    降级
domain/models.py                  users/api_keys/usage/glossaries + job 增列
app/settings.py                   新增 DEVICE=auto/JWT/quota/storage 等设置
app/main.py                       metrics 降基数 + request_id + /ready
frontend/src/App.jsx              去 mock + 真实能力
pyproject.toml                    packages + 新依赖(passlib/jose/alembic/fasttext…)
```

---

## 12. 风险与注意点

- **破坏性变更**：M3 引入鉴权后，现有「一个 dev-api-key」契约改变。缓解：迁移时种子化 `dev-api-key`，并在 README 标注 breaking change 与升级步骤。
- **DB 迁移**：从 `create_all` 切到 Alembic 时，需为现有 `translation_jobs` 表写首个基线迁移，避免线上表被误重建。
- **流式 + 缓存**：SSE 与句级缓存/去重逻辑耦合，需仔细设计「命中即 yield、未命中排队翻译」，否则顺序错乱。
- **GPU 显存**：LRU 淘汰阈值要按显存实测调，fp16 下仍需留余量给动态批处理。
- **配额写库热点**：用量若每请求写库会成瓶颈，必须 Redis 累计 + 定期 flush。

---

## 13. 建议执行顺序

1. **M0 + M1**：先把地基和稳定性做好（不改对外契约，低风险）。
2. **M2**：GPU/CPU 与吞吐（部署相关，越早越好）。
3. **M3 → M4**：产品化核心（鉴权 + 前端），这是"面向用户产品"的关键一跃。
4. **M5 / M6 / M7**：能力增强，三者相对独立，可按价值优先级并行推进（建议先 M5 语言检测+流式，最贴近用户感知）。

> 确认这份计划后，我再按 M0 开始动手。需要我把每个里程碑再拆成带验收标准的 issue/任务清单吗？
