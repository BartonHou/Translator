# Translator Platform — 改进计划书 (planning.md)

> 制定日期：2026-07-04
> 范围：基于当前 `master` 分支代码全量走查后，整理出的缺陷修复、架构改进与新增功能路线图。

---

## 1. 项目现状概览

当前是一个结构清晰的「生产导向」翻译平台，分层合理：

| 层 | 模块 | 说明 |
|---|---|---|
| API | `app/api/v1_translate.py`, `v1_jobs.py`, `v1_models.py` | FastAPI 路由，API Key 鉴权、限流 |
| 策略 | `app/core/orchestrator.py`, `policies.py`, `routing.py` | 同步/异步决策、语言对路由（英语枢轴）、文本级缓存 |
| 推理 | `app/inference/model_manager.py`, `engine.py` | HF seq2seq 懒加载、分句、句级缓存与去重、批量推理 |
| 基础设施 | `infra/cache.py`, `db.py`, `rate_limit.py`, `redis_client.py` | Redis 缓存/限流、SQLAlchemy 持久化 |
| 异步 | `workers/celery_app.py`, `tasks.py` | Celery 大批量任务 |
| 前端 | `frontend/src/App.jsx` | Vite + React 交互界面 |

分层职责边界清楚（策略层不碰执行、执行层不碰业务），是这个仓库最大的优点。下面的计划以「不破坏这个边界」为前提。

---

## 2. 需要修复的缺陷与风险（按严重度）

### 2.1 高 — 正确性 / 稳定性

1. **`ModelManager` 无并发保护与内存回收**（`app/inference/model_manager.py:28`）
   - 同步接口 `translate()` 是 `def`，FastAPI 会放进线程池并发执行。多个请求同时首次加载同一模型会重复 `from_pretrained`，浪费内存且可能 OOM。
   - `self._pipelines` 只增不减，模型常驻内存无 LRU 淘汰；语言对多时（16 个方向）在 CPU 上会吃满内存。
   - **改法**：加载路径加 `threading.Lock`（按 model_name 加锁），并引入基于数量/内存的 LRU 淘汰（可配置 `MAX_LOADED_MODELS`）。

2. **`opus-mt-en-ko` / `opus-mt-en-jap` 等模型可能不存在或命名不符**（`app/core/routing.py:11-14`）
   - Helsinki-NLP 对 en↔ko、en↔ja、en↔zh 的部分方向模型缺失或使用不同命名（`en-jap` 是历史命名）。首个请求会 500。
   - **改法**：启动时做一次「注册表健康检查」脚本，标记不可用方向；对缺失方向在 `/v1/models` 里明确标注 `available: false`，避免前端展示不可用组合。

3. **Metrics 标签高基数导致内存膨胀**（`app/main.py:78`, 各路由 `REQ_COUNT.labels(path=...)`）
   - `path=request.url.path` 对 `/v1/jobs/{job_id}` 会把每个 UUID 变成一个独立时间序列，Prometheus 序列爆炸。
   - **改法**：用路由模板（`request.scope["route"].path`）而非实际路径作为 label。

4. **`datetime.utcnow()` 已弃用**（`domain/models.py`, `workers/tasks.py`, `app/api/v1_jobs.py`）
   - Python 3.12+ 弃用，且是 naive datetime。**改法**：统一 `datetime.now(timezone.utc)`。

### 2.2 中 — 设计 / 可维护性

5. **`require_api_key` 在两个路由文件里重复定义**（`v1_translate.py:17`, `v1_jobs.py:20`）
   - **改法**：抽到 `app/api/deps.py` 统一，同时统一到常量时间比较（`secrets.compare_digest`）防时序侧信道。

6. **单一静态 API Key，无多租户**（`app/settings.py:8`）
   - 限流以 key 分桶（`infra/rate_limit.py`）但只有一个 key，等于全局限流。
   - **改法**：支持多 key（配置或 DB 表），每 key 独立配额/限流；为后续计费/审计打基础。

7. **`create_job` 在请求线程里 `get_redis()` 新建连接**（`v1_jobs.py:27`）
   - 每次请求新建 Redis 连接，无连接池复用（`translate` 路由用了 `app.state.redis`，此处不一致）。
   - **改法**：统一走依赖注入 `get_redis(request)`。

8. **Redis 无重试/降级**（`infra/cache.py`, `redis_client.py`）
   - Redis 挂掉时缓存/限流直接抛异常拖垮请求。
   - **改法**：缓存读失败降级为「miss」而非报错；限流失败可选「fail-open / fail-closed」策略化。

9. **`pyproject.toml` 只打包 `app`**（`pyproject.toml:24`）
   - `domain`/`infra`/`workers` 未纳入 packages，`pip install --no-deps -e .` 在某些环境下 import 会失败（现在靠 CWD 侥幸工作）。
   - **改法**：`packages = ["app", "domain", "infra", "workers"]` 或改用 `find` 自动发现。

10. **`requirement.txt` 与 `pyproject.toml` 依赖重复且易漂移**
    - **改法**：以 `pyproject.toml` 为单一来源，删除 `requirement.txt`（或用 pip-tools 生成锁文件）。

### 2.3 低 — 前端与体验

11. **前端有大量「假」元素**（`frontend/src/App.jsx`）
    - `tone`（语气选择）不发给后端；`confidence` 是写死的 mock；`Queue: 0 pending`、`Recent Translations` 全是 mock 数据。
    - **改法**：要么接真实后端能力，要么移除以免误导（见 §4 新功能）。

12. **前端不支持异步 job 流**：无法提交大批量、无法查询 job 状态。

13. **缓存 TTL 未透传**（`orchestrator.py:78` 文本级 `set_json` 未传 ttl，走默认）— 行为正确但不易调优，建议区分句级/文本级 TTL。

---

## 3. 改进路线图（分阶段）

### Phase 0 — 工程基线（0.5–1 天）
- [ ] 加 CI（GitHub Actions）：后端 `unittest` + 前端 `npm test`，PR 必过。
- [ ] 加 `ruff` + `black` + `mypy`（宽松档）与 pre-commit。
- [ ] 依赖单一来源化（§2.2-10），修 `pyproject.toml` packages（§2.2-9）。
- [ ] 补 `.env.example` 与统一的本地启动脚本（`make dev` / `docker compose`）。

### Phase 1 — 正确性与稳定性修复（1–2 天）
- [ ] ModelManager 并发锁 + LRU 淘汰（§2.1-1）。
- [ ] 注册表健康检查 + `/v1/models` 标注可用性（§2.1-2）。
- [ ] Metrics 用路由模板降基数（§2.1-3）。
- [ ] `datetime` timezone-aware 全量替换（§2.1-4）。
- [ ] Redis 降级策略（§2.2-8）。

### Phase 2 — API 与鉴权强化（2–3 天）
- [ ] `require_api_key` 去重 + `compare_digest`（§2.2-5）。
- [ ] 多 API Key / 多租户与每 key 配额（§2.2-6）。
- [ ] Redis 依赖注入统一（§2.2-7）。
- [ ] `/health` 增加 Redis / Postgres 连通性探测（就绪探针 `/ready`）。
- [ ] 请求级 `request_id` 贯穿日志（structlog contextvars）。

### Phase 3 — 测试补强（2 天）
- [ ] 单测：`engine`（分句/去重/句级缓存命中回填）、`orchestrator`（枢轴两段路由）、`rate_limit`（窗口边界）、`cache`（降级）。
- [ ] 集成测试：用 `fakeredis` + SQLite 内存库 + mock 掉 HF 推理，端到端跑 `/v1/translate` 与 `/v1/jobs`。
- [ ] 前端：为异步流与错误态补 RTL 测试。

### Phase 4 — 前端真实化（2–3 天）
- [ ] 移除/接真：confidence、queue、recent（§2.3-11）。
- [ ] 异步 job 提交 + 轮询/进度 UI（§2.3-12）。
- [ ] localStorage 保存最近翻译历史（真实数据）。

---

## 4. 额外功能建议（增量价值）

按「投入产出比」排序：

1. **语言自动检测**（高价值）
   - 集成 `fasttext-langdetect` 或 `langid`，`source_lang` 支持 `auto`，路由前先检测。前端加「自动检测」选项。

2. **流式翻译（SSE）**
   - 大文本逐句返回，前端边翻边显示，显著改善感知延迟。新增 `POST /v1/translate/stream`。

3. **术语表 / 自定义词典**
   - 允许用户上传 glossary（术语强制映射），推理前后处理。企业场景刚需。

4. **真实质量分**
   - 用回译（back-translation）+ 相似度，或 beam score 归一化，给出真实 `confidence`，替换前端 mock。

5. **批量文件翻译**
   - 支持上传 `.txt/.docx/.srt`，异步 job 产出译文文件下载。天然契合现有 jobs 架构。

6. **可观测性完善**
   - 附带 Prometheus + Grafana + 预置面板的 `docker-compose.observability.yml`；关键指标：p95 延迟、缓存命中率、队列深度、模型加载耗时。

7. **GPU / 批处理吞吐优化**
   - 动态批处理（micro-batching）合并并发短请求；`DEVICE=cuda` 路径压测与文档化。

8. **Webhook 回调**
   - `JobCreateRequest.callback_url` 已预留（`domain/schemas.py:26`）但未实现——job 完成后 POST 回调，闭环异步体验。

9. **模型可插拔**
   - 抽象 provider 接口，除 Helsinki-NLP 外支持 NLLB-200（单模型覆盖 200 语言，可去掉英语枢轴的双段损失）或外部 API（DeepL/Google）作为 fallback。

10. **速率限制升级**
    - 从固定窗口（`infra/rate_limit.py` 有边界突刺问题）升级为滑动窗口或令牌桶。

---

## 5. 关键架构决策待确认

以下几点会影响后续设计方向，建议先拍板：

- **单模型 vs 枢轴多模型**：是否引入 NLLB-200 取代 Helsinki 枢轴路由？影响 §4-9 与内存占用。
- **多租户范围**：是否需要真正的用户体系（DB + 计费），还是配置多 key 即可？影响 Phase 2。
- **部署目标**：CPU-only 还是要正式支持 GPU？影响 ModelManager 淘汰策略与 §4-7。
- **前端定位**：是「演示 UI」还是「面向用户的产品」？决定 §2.3 是删除 mock 还是全部接真。

---

## 6. 建议的第一批落地（本周可完成）

1. Phase 0 工程基线（CI + lint + 依赖修复）。
2. Phase 1 中最关键的两项：ModelManager 并发锁/淘汰、Metrics 降基数。
3. `require_api_key` 去重（一次性清债）。

这三项风险低、收益明确，且不改变对外契约，适合作为改进的起点。
