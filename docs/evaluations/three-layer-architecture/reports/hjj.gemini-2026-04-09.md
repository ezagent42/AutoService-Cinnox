---
target: docs/plans/2026-04-09-three-layer-architecture.md
target_type: plan
reviewer: hjj.gemini@gmail.com
reviewer_email: hjj.gemini@gmail.com
date: 2026-04-09
status: completed
overall_score: 4/5
---

# Review: Socialware 三层架构设计 — L1/L2/L3 Package + Fork 策略

## Overall Assessment

这是一份高质量的架构设计文档，分析深度远超一般的技术方案。方案对比部分尤为出色——4 个候选方案从 10 个维度逐项对比，对方案 C 的 `.git` 安全分析和 worktree "伪优势"的量化拆解，展现了扎实的工程判断力。"机制 vs 策略"拆分原则（Section 6）是全文的设计精华，为 L1/L2 边界提供了可操作的判断清单。

主要不足集中在执行层面：迁移计划过于粗略（无时间线、无 rollback、无验收标准），L1 提取的实际工作量被低估，团队能力和规模假设缺失。风险评估虽然覆盖了 10 类风险，但遗漏了 L1 包自身的维护负担和迁移失败的退出策略。文档的设计功底扎实，但要从"approved plan"走向可执行的 engineering project，还需要补强迁移计划和可行性评估。

## Key Points

- [x] 痛点有代码级证据支撑（`config.py` 硬编码 `LANG_CONFIGS`、`session.py` 硬编码 `DOMAIN_PREFIXES`、commit `ee07d24`）
- [x] 方案对比矩阵全面公平（4 方案 x 10 维度），对每个方案的劣势不回避
- [x] L1 准入标准清晰可操作（"换一个完全不同的 app 还有没有用？"）
- [x] "机制 vs 策略"拆分原则具体到代码级别（config.py、session.py、permission.py 示例）
- [x] 子租户分析充分（3 种 L3→L3' 方案 + 决策树）
- [x] 风险识别覆盖 10 类，P0/P1/P2 分级实施优先级合理
- [x] 开发态 editable install 解决了 L1/L2 联调的零延迟问题
- [ ] 痛点 #2（提炼困难）只引用了一个 commit，频率证据不足
- [ ] 痛点 #4（复用受限）缺乏具体项目支撑，"AI 教育助手"是假设性场景
- [ ] 缺少目标规模定义（5 个租户 vs 50 个租户的风险/收益差异大）
- [ ] 迁移计划无时间线、无 rollback 策略、无验收标准
- [ ] L1 channels/ 与 L2 的耦合解耦方案未详述（`channel_server.py` 直接 import `autoservice.crm`）
- [ ] plugin.yaml schema 版本化机制缺失
- [ ] L1 包在非 PyPI 场景下的 CI 获取路径未说明

## Questions & Concerns

1. **cherry-pick 频率** — 痛点 #2 只引用了 commit `ee07d24` 作为证据。这是日常摩擦还是偶发事件？如果频率低，三层重构的投入是否成比例？
2. **非客服 app 的真实需求** — "AI 教育助手"是具体在推进的项目，还是假设性的未来收益？如果只是假设，L1/L2 拆分是否可以延迟？
3. **L1 channels/ 解耦路径** — `feishu/channel_server.py` 当前直接 import `autoservice.crm`（文档在 R2 中自行指出）。拆到 L1 后需要什么抽象层或 hook 机制？
4. **mock_db.py 的 L1 归属** — 表结构 "customers/products/subscriptions" 看似通用，但命名带有业务假设。纯框架层是否应该只提供通用 KV/document store 抽象？
5. **L1 包的维护负担** — 独立包意味着独立的 issue tracker、版本发布、changelog、CI pipeline。如果 L1/L2 维护者是同一批人，context switching 成本如何？
6. **迁移期间现有 fork 的处理** — 当前 repo 已有 fork（PR #1 来自 `allenwoods/upstream-multiuser-explain`）。Phase 3 迁移期间是否需要 code freeze？
7. **L1 在 CI 中的获取方式** — 如果不发布到 PyPI，L3 fork 的 CI 是否每次都要 clone socialware repo 做 editable install？

## Risk Identification

| Risk | Severity | Identified in Doc? | Reviewer's Suggestion |
|------|----------|--------------------|-----------------------|
| L1 提取工作量超出预期（import 重写、channel 解耦、CI 建设） | High | No | 先做 spike：提取 `core.py` + `plugin_loader.py` 验证可行性 |
| L1 包自身的维护负担（独立 issue tracker、CI、版本发布） | Medium | No | 评估团队规模是否支撑两个独立包的维护 |
| 迁移失败无退出策略 | High | No | 补充每个 Phase 的 rollback 方案 |
| plugin.yaml schema 变更导致 L3 断裂 | Medium | Partial (R3) | 引入 plugin schema 版本号，L2 提供 migration script |
| R5 提炼遗漏防控依赖人工纪律 | Medium | Yes (偏弱) | 用 CI 自动检测 L3 对非 plugins/ 目录的修改并创建提醒 |
| 3 repo 切换的 DX 下降 | Medium | No | 文档中补充 IDE 配置指南和调试 workflow |

## Improvement Suggestions

1. **补充迁移计划的时间线和 rollback 策略** — 每个 Phase 需要：预计耗时、验收标准（不仅是 `make run-channel` 正常启动）、失败时的退出路径。这是从 "approved plan" 到可执行项目的必要步骤
2. **明确目标规模** — 在 Section 1 Goals 中声明当前租户数和 1 年预期。规模直接影响 fork 管理体系（注册表、健康度看板、sync bot）的投入合理性
3. **先做 L1 提取的 spike** — 在全面重构前，提取 `core.py` + `plugin_loader.py` 到独立包，跑通 editable install + channel 层解耦，验证边界是否正确。Spike 的成本低，但能大幅降低全面迁移的风险
4. **补充 plugin.yaml schema 版本化** — 在 `plugin.yaml` 中加入 `schema_version` 字段，L2 的 plugin_loader 做向后兼容检查。否则 L2 升级 schema 时所有 L3 会静默断裂
5. **补充 DX 影响分析** — 在 Section 7 或独立章节中讨论：3 repo 工作区的 IDE 配置（monorepo workspace？）、跨 repo 调试断点、全局搜索方案。开发体验直接影响团队接受度
6. **强化 R5 防控** — 将"定期 fork diff review"从人工纪律升级为 CI 自动化：检测 L3 修改了 `autoservice/` 目录的文件时，自动在 L3 repo 中创建 issue 提醒考虑提 upstream PR

## Session Highlights

> 方案对比是全文最强的部分。对方案 C 的 `.git` 安全分析——从 `git branch -a` 到 `git fsck --unreachable`——把 worktree 的隐性风险讲得极其透彻。Section 2.4 量化了 worktree "每次提炼节省 2-10 秒 fetch 时间"vs "一次没有 review 的错误提炼可能造成数小时排查"，这个对比有说服力。

> 迁移计划是全文最薄弱的部分。4 个 Phase 只有步骤列表，缺少时间估算、rollback 策略、验收标准、Phase 间依赖说明。对于一个 status 已经是 "Approved" 的文档，执行层面的细节不够。

> L1 channels/ 的归属存在结构性矛盾：文档将 `feishu/` 和 `web/` 放入 L1，但 `channel_server.py` 当前直接 import `autoservice.crm`。这意味着迁移时需要设计一个抽象层让 channel 不依赖具体业务模块，而这个解耦方案在文档中未详述。
