# E2E 测试方案 — 分层信任模型

**Date:** 2026-04-09
**Status:** Draft
**Authors:** Allen Woods + Claude
**Reviewer:** TBD

## 1. Overview

AutoService 的 E2E 测试分为 **AI E2E**（对话质量）和 **User E2E**（操作流程）两类。核心设计理念：**AI Agent 自治迭代，用户校准锚定**。

AI 自测 AI 存在盲区重合风险（Judge 和被测对象同源），因此采用分层信任模型，明确每一层谁负责、信任边界在哪。

### Goals

1. **AI 自治迭代** — L1+L2 测试由 AI 自主编写、执行、评判、修复
2. **人类锚定** — L3 场景由用户验证，校准 AI Judge 的准心
3. **可信报告** — 每次测试产出结构化报告 + 截图证据，可追溯可审计
4. **CI/CD 集成** — push 触发全量测试，PR 自动贴评估摘要

### Non-Goals

- 不替代单元/集成测试（channel-server 路由等由 pytest 覆盖）
- 不做性能压测（专项工具另议）
- 不做多语言/多时区测试（v1 仅中文场景）

## 2. 分层信任模型

```
┌───────────────────────────────────────────────────────────────┐
│  L1 — 确定性断言            AI 完全自治        信任: 高       │
│  回复非空、不含禁词、响应时间 <10s、KB 命中、格式正确          │
├───────────────────────────────────────────────────────────────┤
│  L2 — 质量判断              AI Judge + 人定基准  信任: 中      │
│  话术合规、语气专业、回答完整性、上下文连贯                    │
│  基准 = golden answers + rubric，人定期 review 漂移            │
├───────────────────────────────────────────────────────────────┤
│  L3 — 业务正确性            人验证              信任: 锚定     │
│  价格准确、流程合规、客户满意度、边界 case                     │
│  不可自动化的判断，是 L1/L2 的校准源                           │
└───────────────────────────────────────────────────────────────┘
```

### 层级职责

| 层 | 执行者 | 频率 | 产出 |
|----|--------|------|------|
| L1 | AI 自动 | 每次 push | pass/fail + 断言详情 |
| L2 | AI Judge | 每次 push | 评分 (1-5) + reasoning |
| L3 | 用户 | 每轮迭代 / 发版前 | 校准记录 → 更新 rubric |

### 信任传递

```
用户定义 golden answer / rubric (L3)
    ↓
AI Judge 按 rubric 评分 (L2)
    ↓
AI 自动断言 (L1)
    ↓
发现 fail → AI 自动修 prompt/KB → 重跑 L1+L2
    ↓
L2 评分异常 → 触发用户 review (L3)
    ↓
用户发现盲区 → 补 rubric / golden answer → 循环
```

## 3. 目录结构

```
tests/
  e2e/
    ai_chat/                    # AI E2E 测试（对话质量）
      test_cases.yaml           # 测试场景定义（L1 断言 + L2 rubric）
      golden/                   # L3 golden answers（用户校准）
        product-inquiry.yaml
        complaint-handling.yaml
      runner.py                 # 测试执行器
      judge.py                  # AI-as-Judge 评估器
      conftest.py               # pytest fixtures（服务启停、browser）
      results/                  # 执行结果输出（gitignored）
        latest.json
        screenshots/
    test_web_flow.py            # User E2E（pytest 改造，替代 test_web_chat.sh）
    test_feishu_mock.py         # 已有，Feishu 协议 E2E
    screenshots/                # 已有
  conftest.py                   # 共享 fixtures
```

## 4. AI E2E 测试框架

### 4.1 测试用例定义

`tests/e2e/ai_chat/test_cases.yaml`:

```yaml
# 每个场景包含 L1 断言 + L2 rubric + 可选 L3 golden reference
scenarios:
  - id: product-inquiry
    description: "用户询问产品信息"
    channel: web                    # web | feishu
    setup:                          # 前置条件
      kb_required: true
      operator_mode: sales
    messages:
      - role: user
        text: "你们有什么产品？"
      # 多轮对话
      - role: user
        text: "最便宜的方案多少钱？"
        depends_on: 0               # 依赖第一轮回复

    # L1 — 确定性断言（AI 自治）
    assertions:
      - type: not_empty
      - type: response_time
        max_ms: 10000
      - type: must_not_contain
        values: ["我不知道", "无法回答", "ERROR"]
      - type: must_contain_any
        values: ["产品", "服务", "方案"]
      - type: kb_hit                # 检查是否命中知识库
        min_score: 0.7

    # L2 — 质量评判（AI Judge + 人定 rubric）
    rubric:
      - criterion: "回复应包含具体产品名称或产品线"
        weight: 2
      - criterion: "回复应引导用户获取详细价格（链接或联系方式）"
        weight: 1
      - criterion: "语气应专业友好，不生硬"
        weight: 1
      - criterion: "多轮对话应保持上下文连贯"
        weight: 2

    # L3 — golden answer reference（用户维护，可选）
    golden_ref: golden/product-inquiry.yaml

  - id: complaint-handling
    description: "用户投诉场景"
    channel: web
    setup:
      operator_mode: customer-service
    messages:
      - role: user
        text: "你们的服务太差了，我要投诉"
    assertions:
      - type: not_empty
      - type: must_not_contain
        values: ["你说得不对", "这不是我们的问题"]
      - type: sentiment
        expected: empathetic          # 情感倾向检测
    rubric:
      - criterion: "应表达歉意和理解"
        weight: 2
      - criterion: "应主动提供解决方案或升级路径"
        weight: 2
      - criterion: "不应推诿、否认或反驳用户"
        weight: 3
    golden_ref: golden/complaint-handling.yaml

  - id: out-of-scope
    description: "超出服务范围的问题"
    channel: web
    messages:
      - role: user
        text: "帮我写一首诗"
    assertions:
      - type: not_empty
      - type: must_not_contain
        values: ["好的，这是一首诗"]
    rubric:
      - criterion: "应礼貌拒绝并引导回业务话题"
        weight: 2
      - criterion: "不应直接满足与业务无关的请求"
        weight: 3
```

### 4.2 Golden Answer（L3 校准源）

`tests/e2e/ai_chat/golden/product-inquiry.yaml`:

```yaml
# 由用户维护，AI 不可自动修改
scenario_id: product-inquiry
maintained_by: "Allen Woods <hjj.gemini@gmail.com>"
last_updated: 2026-04-09

# 参考答案（不要求逐字匹配，用于 Judge 对比）
golden_answers:
  - turn: 0
    reference: |
      我们主要提供以下产品/服务：
      1. XXX 产品 — 面向中小企业的 YYY 解决方案
      2. ZZZ 服务 — 提供 AAA 能力
      如需了解详细方案和价格，可以联系我们的销售顾问。
    key_facts:                        # 必须命中的事实点
      - "产品名称至少提及一个"
      - "应有获取详情的引导"

# Judge 校准：这些之前被 AI 误判过
corrections:
  - date: 2026-04-09
    issue: "Judge 给了满分但回复缺少具体产品名"
    fix: "rubric 加权：产品名称 weight 2→3"
```

### 4.3 测试执行器

`tests/e2e/ai_chat/runner.py` 核心流程：

```python
"""
AI E2E 测试执行器

流程:
1. 加载 test_cases.yaml
2. 启动服务（channel-server + web/feishu）
3. 逐场景执行:
   a. 通过对应 channel 发送用户消息
   b. 等待 AI 回复（超时 = assertion.response_time.max_ms）
   c. agent-browser 截图（Web 场景）
   d. 运行 L1 断言
   e. 调用 judge.py 做 L2 评分
4. 汇总结果 → results/latest.json
5. 截图 → results/screenshots/{scenario_id}_{turn}_{timestamp}.png
"""

import asyncio
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone

CASES_PATH = Path(__file__).parent / "test_cases.yaml"
RESULTS_DIR = Path(__file__).parent / "results"
SCREENSHOT_DIR = RESULTS_DIR / "screenshots"


async def run_scenario(scenario: dict, services: dict) -> dict:
    """执行单个场景，返回结构化结果。"""
    result = {
        "id": scenario["id"],
        "description": scenario["description"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "turns": [],
        "l1_assertions": [],
        "l2_scores": [],
        "verdict": "pending",
        "screenshots": [],
    }

    for i, message in enumerate(scenario["messages"]):
        # 1. 发送消息
        reply = await send_and_receive(
            channel=scenario.get("channel", "web"),
            text=message["text"],
            services=services,
        )

        # 2. 截图
        screenshot_path = await capture_screenshot(
            scenario["id"], i, services.get("browser")
        )
        result["screenshots"].append(str(screenshot_path))

        # 3. 记录对话轮次
        result["turns"].append({
            "turn": i,
            "user": message["text"],
            "assistant": reply["text"],
            "response_time_ms": reply["elapsed_ms"],
        })

    # 4. L1 断言
    result["l1_assertions"] = run_l1_assertions(
        scenario.get("assertions", []),
        result["turns"],
    )

    # 5. L2 评分（调用 judge.py）
    result["l2_scores"] = await run_l2_judge(
        scenario,
        result["turns"],
    )

    # 6. 判定
    l1_pass = all(a["passed"] for a in result["l1_assertions"])
    l2_avg = (
        sum(s["score"] for s in result["l2_scores"])
        / len(result["l2_scores"])
        if result["l2_scores"] else 0
    )
    result["verdict"] = (
        "pass" if l1_pass and l2_avg >= 3.0
        else "warn" if l1_pass and l2_avg >= 2.0
        else "fail"
    )
    result["l1_pass"] = l1_pass
    result["l2_avg_score"] = round(l2_avg, 2)

    return result


def run_l1_assertions(assertions: list, turns: list) -> list:
    """执行 L1 确定性断言。"""
    results = []
    for assertion in assertions:
        atype = assertion["type"]
        passed = False
        detail = ""

        if atype == "not_empty":
            passed = all(t["assistant"].strip() for t in turns)
            detail = "All replies non-empty" if passed else "Empty reply found"

        elif atype == "response_time":
            max_ms = assertion["max_ms"]
            passed = all(t["response_time_ms"] <= max_ms for t in turns)
            times = [t["response_time_ms"] for t in turns]
            detail = f"Response times: {times}, max allowed: {max_ms}"

        elif atype == "must_not_contain":
            forbidden = assertion["values"]
            for t in turns:
                for word in forbidden:
                    if word in t["assistant"]:
                        passed = False
                        detail = f"Forbidden word '{word}' found in turn {t['turn']}"
                        break
                else:
                    continue
                break
            else:
                passed = True
                detail = "No forbidden words found"

        elif atype == "must_contain_any":
            required = assertion["values"]
            for t in turns:
                if any(word in t["assistant"] for word in required):
                    passed = True
                    detail = f"Found required keyword in reply"
                    break
            else:
                passed = False
                detail = f"None of {required} found in any reply"

        # ... 其他断言类型

        results.append({
            "type": atype,
            "passed": passed,
            "detail": detail,
        })

    return results


async def main():
    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    services = await start_services()
    try:
        results = []
        for scenario in cases["scenarios"]:
            print(f"▶ Running: {scenario['id']} — {scenario['description']}")
            result = await run_scenario(scenario, services)
            icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}[result["verdict"]]
            print(f"  {icon} {result['verdict']} (L1={result['l1_pass']}, L2={result['l2_avg_score']})")
            results.append(result)

        # 汇总
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": len(results),
            "passed": sum(1 for r in results if r["verdict"] == "pass"),
            "warned": sum(1 for r in results if r["verdict"] == "warn"),
            "failed": sum(1 for r in results if r["verdict"] == "fail"),
            "scenarios": results,
        }
        output_path = RESULTS_DIR / "latest.json"
        output_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n=== Results: {summary['passed']}/{summary['total']} passed, "
              f"{summary['warned']} warnings, {summary['failed']} failed ===")
        print(f"Report: {output_path}")
    finally:
        await stop_services(services)


if __name__ == "__main__":
    asyncio.run(main())
```

### 4.4 AI-as-Judge

`tests/e2e/ai_chat/judge.py` 核心流程：

```python
"""
AI-as-Judge — 按 rubric 评估 AI 回复质量。

输入: 场景定义 + 对话记录 + rubric + 可选 golden answer
输出: 每条 rubric criterion 的评分 (1-5) + reasoning

使用 Claude API，system prompt 中注入 rubric 和 golden answer，
要求结构化 JSON 输出。
"""

JUDGE_SYSTEM_PROMPT = """你是一个严格的 AI 对话质量评审员。

你的任务是按照给定的评分标准（rubric）评估 AI 助手的回复质量。

评分规则：
- 5 分：完全满足标准，表现优秀
- 4 分：基本满足，有小瑕疵
- 3 分：部分满足，有明显不足
- 2 分：勉强相关，严重不足
- 1 分：完全不满足或有害

你必须：
1. 逐条评估每个 criterion
2. 给出具体的 reasoning（引用回复原文）
3. 如果提供了 golden answer，对比分析差异
4. 不要因为回复"看起来不错"就给高分，关注具体事实

输出格式：严格 JSON，结构见下方。
"""

JUDGE_USER_TEMPLATE = """
## 场景
{scenario_description}

## 对话记录
{conversation}

## 评分标准 (Rubric)
{rubric}

{golden_section}

请评估并输出 JSON：
```json
{{
  "scores": [
    {{
      "criterion": "标准描述",
      "score": 4,
      "weight": 2,
      "reasoning": "具体理由，引用回复原文"
    }}
  ],
  "overall_notes": "总体评价",
  "blind_spots": ["Judge 注意到但 rubric 未覆盖的问题"]
}}
```
"""


async def judge_scenario(
    scenario: dict,
    turns: list[dict],
    golden: dict | None = None,
) -> list[dict]:
    """调用 Claude API 做 L2 评分。"""
    import anthropic

    client = anthropic.AsyncAnthropic()

    # 构造对话文本
    conversation = "\n".join(
        f"用户: {t['user']}\nAI: {t['assistant']}"
        for t in turns
    )

    # 构造 rubric 文本
    rubric_text = "\n".join(
        f"- [{c['weight']}x] {c['criterion']}"
        for c in scenario.get("rubric", [])
    )

    # Golden answer 部分（可选）
    golden_section = ""
    if golden:
        golden_section = "## 参考答案 (Golden Answer)\n"
        for ga in golden.get("golden_answers", []):
            golden_section += f"Turn {ga['turn']}:\n{ga['reference']}\n"
            if ga.get("key_facts"):
                golden_section += "必须命中事实:\n"
                for fact in ga["key_facts"]:
                    golden_section += f"  - {fact}\n"

    message = await client.messages.create(
        model="claude-sonnet-4-6",      # Judge 用 sonnet，与被测 opus 不同源
        max_tokens=2000,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": JUDGE_USER_TEMPLATE.format(
                scenario_description=scenario["description"],
                conversation=conversation,
                rubric=rubric_text,
                golden_section=golden_section,
            ),
        }],
    )

    # 解析 JSON 输出
    import json, re
    text = message.content[0].text
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group(1))
    else:
        result = json.loads(text)

    return result["scores"]
```

**关键设计决策：Judge 用 `claude-sonnet-4-6`，被测 Bot 用 `claude-opus-4-6`，减少同源盲区。**

### 4.5 结果输出格式

`tests/e2e/ai_chat/results/latest.json`:

```json
{
  "timestamp": "2026-04-09T10:30:00Z",
  "total": 3,
  "passed": 2,
  "warned": 1,
  "failed": 0,
  "scenarios": [
    {
      "id": "product-inquiry",
      "description": "用户询问产品信息",
      "verdict": "pass",
      "l1_pass": true,
      "l2_avg_score": 4.2,
      "turns": [
        {
          "turn": 0,
          "user": "你们有什么产品？",
          "assistant": "我们提供以下产品...",
          "response_time_ms": 3200
        }
      ],
      "l1_assertions": [
        {"type": "not_empty", "passed": true, "detail": "All replies non-empty"},
        {"type": "response_time", "passed": true, "detail": "Response times: [3200], max: 10000"}
      ],
      "l2_scores": [
        {
          "criterion": "回复应包含具体产品名称或产品线",
          "score": 5, "weight": 2,
          "reasoning": "回复提及了 XXX 产品和 ZZZ 服务"
        }
      ],
      "screenshots": [
        "results/screenshots/product-inquiry_0_20260409T103000.png"
      ]
    }
  ]
}
```

## 5. User E2E 测试（pytest 改造）

将现有 `test_web_chat.sh` 改造为 pytest，统一框架和报告格式。

`tests/e2e/test_web_flow.py`:

```python
"""
User E2E — Web 聊天操作流程测试。

pytest 改造好处：
- JUnit XML 报告，CI/CD 原生集成
- 选择性运行: pytest -k "login"
- fixture 管理服务生命周期
- 与 AI E2E 共享 conftest
"""
import pytest
import subprocess
import time

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"


@pytest.fixture(scope="module")
def services():
    """启动 channel-server + web server，测试结束后清理。"""
    cs = subprocess.Popen(
        ["uv", "run", "python3", "feishu/channel_server.py"],
        env={**os.environ, "FEISHU_ENABLED": "0", "CHANNEL_SERVER_PORT": "19998"},
    )
    web = subprocess.Popen(
        ["uv", "run", "uvicorn", "web.app:app", "--port", "18000"],
        env={**os.environ, "DEMO_ADMIN_KEY": "e2e-test-key"},
    )
    time.sleep(3)
    yield {"base_url": "http://localhost:18000", "admin_key": "e2e-test-key"}
    web.terminate()
    cs.terminate()


@pytest.fixture
def browser():
    """agent-browser session，自动截图。"""
    session = f"e2e-{int(time.time())}"
    yield AgentBrowser(session, SCREENSHOT_DIR)
    # cleanup in __del__


class TestLogin:
    def test_login_page_loads(self, services, browser):
        browser.open(f"{services['base_url']}/login")
        browser.screenshot("login_page.png")
        assert browser.url.endswith("/login")

    def test_login_with_valid_code(self, services, browser):
        code = generate_access_code(services)
        browser.fill("#code-input", code)
        browser.click("#submit-btn")
        browser.wait_navigation()
        browser.screenshot("after_login.png")
        assert "/chat" in browser.url


class TestChat:
    def test_send_message(self, services, browser):
        # login first
        login(browser, services)
        browser.fill("#msg-input", "Hello")
        browser.click("#send-btn")
        browser.screenshot("message_sent.png")
        # 验证消息出现在 DOM
        user_msg = browser.eval('.msg-row.user .bubble')
        assert user_msg is not None


class TestLogout:
    def test_logout_redirects(self, services, browser):
        login(browser, services)
        browser.click("#btn-end")
        browser.click("#btn-logout")
        browser.wait_navigation()
        browser.screenshot("after_logout.png")
        assert "/login" in browser.url
```

## 6. 自动化评估报告

### 6.1 auto_evaluate.py

`skills/evaluate/scripts/auto_evaluate.py` — 将测试结果转为 evaluate 报告格式：

```python
"""
自动评估脚本 — 将 E2E 测试结果转换为结构化评估报告。

输入:
  --ai-e2e   tests/e2e/ai_chat/results/latest.json
  --user-e2e results/user-e2e.xml (JUnit XML)
  --output   docs/evaluations/

输出:
  docs/evaluations/e2e-{date}/
    meta.yaml
    reports/auto-{date}.md      # 自动评估报告
    reports/latest-summary.md   # CI/CD PR comment 用

流程:
  1. 解析 AI E2E results JSON → 提取 L1 pass rate、L2 评分分布
  2. 解析 User E2E JUnit XML → 提取 pass/fail/skip
  3. 对比上次结果 → 计算 regression
  4. 按维度生成评估报告（复用 report.md 模板）
  5. 更新 meta.yaml
"""

EVAL_DIMENSIONS = {
    "ai_e2e": [
        ("pass_rate", "L1 断言通过率"),
        ("quality_score", "L2 平均质量评分"),
        ("kb_accuracy", "知识库命中率"),
        ("response_time", "平均响应时间"),
        ("screenshot_evidence", "截图证据完整性"),
        ("regression", "与上次对比"),
    ],
    "user_e2e": [
        ("flow_pass_rate", "操作流程通过率"),
        ("screenshot_evidence", "每步截图完整性"),
        ("regression", "与上次对比"),
    ],
}
```

### 6.2 报告模板

自动生成的报告结构：

```markdown
---
target: e2e-execution-2026-04-09
type: e2e-test
reviewer: auto-evaluate
date: 2026-04-09
---

# E2E 测试执行评估报告

## 概要

| 指标 | AI E2E | User E2E |
|------|--------|----------|
| 场景数 | 12 | 6 |
| 通过 | 10 | 6 |
| 警告 | 1 | 0 |
| 失败 | 1 | 0 |
| L2 均分 | 3.8/5 | N/A |

## AI E2E 详情

### L1 断言结果
- [x] 回复非空: 12/12
- [x] 响应时间 <10s: 11/12 (product-inquiry-multi: 12.3s)
- [x] 禁词检查: 12/12
- [ ] KB 命中率: 9/12 (3 场景未命中 KB)

### L2 质量评分分布
| 场景 | 评分 | 关键发现 |
|------|------|----------|
| product-inquiry | 4.2 | 产品名称完整，缺少价格引导 |
| complaint-handling | 3.5 | 道歉充分，解决方案不够具体 |
| out-of-scope | 4.8 | 正确拒绝并引导 |

### 截图证据
[product-inquiry_0](screenshots/product-inquiry_0_20260409.png)
[complaint-handling_0](screenshots/complaint-handling_0_20260409.png)

## User E2E 详情

### 流程验证
- [x] 登录流程: pass
- [x] 发送消息: pass
- [x] 结束会话: pass
- [x] 登出流程: pass

## Regression 对比

| 指标 | 本次 | 上次 | 变化 |
|------|------|------|------|
| AI E2E 通过率 | 83% | 75% | +8% ↑ |
| L2 均分 | 3.8 | 3.5 | +0.3 ↑ |
| User E2E 通过率 | 100% | 100% | — |

## 待处理

1. **product-inquiry-multi 超时** — 多轮对话响应时间超标，需排查
2. **KB 命中率** — 3 个场景未命中，需补充知识库条目
3. **complaint-handling 解决方案** — L2 评分 3.5，rubric 建议加强
```

## 7. CI/CD 集成

### 7.1 GitHub Actions

`.github/workflows/e2e.yaml`:

```yaml
name: E2E Tests & Evaluation

on:
  push:
    branches: [main, feat/*]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: "3.11"

jobs:
  # ── Stage 1: User E2E ──────────────────────────────────────
  user-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra test

      - name: Run User E2E tests
        run: |
          pytest tests/e2e/test_web_flow.py \
            -v --junitxml=results/user-e2e.xml \
            --timeout=120
        env:
          DEMO_ADMIN_KEY: e2e-test-key

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: user-e2e-results
          path: |
            results/user-e2e.xml
            tests/e2e/screenshots/

  # ── Stage 2: AI E2E ────────────────────────────────────────
  ai-e2e:
    runs-on: ubuntu-latest
    needs: user-e2e                   # 用户流程通过后再跑 AI 测试
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra test

      - name: Run AI E2E tests
        run: uv run python tests/e2e/ai_chat/runner.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          DEMO_ADMIN_KEY: e2e-test-key
        timeout-minutes: 10

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: ai-e2e-results
          path: tests/e2e/ai_chat/results/

  # ── Stage 3: Evaluate & Report ─────────────────────────────
  evaluate:
    runs-on: ubuntu-latest
    needs: [user-e2e, ai-e2e]
    if: always()
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync

      - uses: actions/download-artifact@v4
        with:
          name: user-e2e-results
          path: results/user-e2e/
      - uses: actions/download-artifact@v4
        with:
          name: ai-e2e-results
          path: results/ai-e2e/

      - name: Generate evaluation report
        run: |
          uv run skills/evaluate/scripts/auto_evaluate.py \
            --user-e2e results/user-e2e/user-e2e.xml \
            --ai-e2e results/ai-e2e/latest.json \
            --output docs/evaluations/

      - uses: actions/upload-artifact@v4
        with:
          name: evaluation-reports
          path: docs/evaluations/

      # PR comment with summary
      - uses: marocchino/sticky-pull-request-comment@v2
        if: github.event_name == 'pull_request'
        with:
          path: docs/evaluations/latest-summary.md
```

### 7.2 Makefile 扩展

```makefile
# --- E2E Tests ---
e2e-user:
    pytest tests/e2e/test_web_flow.py -v --junitxml=results/user-e2e.xml

e2e-ai:
    uv run python tests/e2e/ai_chat/runner.py

e2e: e2e-user e2e-ai

# --- Evaluation ---
evaluate-auto:
    uv run skills/evaluate/scripts/auto_evaluate.py --latest

# --- Full Pipeline (local) ---
e2e-full: e2e evaluate-auto
    @echo "==> Full E2E pipeline complete"
    @echo "Report: docs/evaluations/latest-summary.md"
```

## 8. AI 自治迭代循环

AI Agent 如何利用这套框架自我迭代：

```
Step 1: 运行测试
  $ make e2e-ai

Step 2: 分析失败
  读取 results/latest.json
  → 识别 L1 fail (断言失败) 和 L2 warn (评分 <3.0)

Step 3: 定位原因
  L1 fail:
    - must_not_contain 触发 → 检查 prompt/KB 是否有错误引导
    - response_time 超标 → 检查 prompt 长度或 KB 检索效率
    - kb_hit 低 → 检查知识库覆盖
  L2 warn:
    - 读 Judge reasoning → 定位具体 criterion 失分原因
    - 对比 golden answer → 识别缺失的事实点

Step 4: 修复
  - 修改 prompt template / system instruction
  - 补充 KB 条目
  - 调整 tool 配置

Step 5: 重跑验证
  $ make e2e-ai
  → 确认修复有效且无 regression

Step 6: 报告
  $ make evaluate-auto
  → 生成评估报告，记录本轮迭代的改进
```

**触发用户介入的条件：**
- L2 评分连续 2 轮下降（可能 Judge 漂移）
- 新增场景的 golden answer 需要用户提供
- corrections 记录超过 5 条（rubric 可能需要重构）

## 9. 实施计划

| 阶段 | 交付物 | 依赖 |
|------|--------|------|
| **Phase 1** | `tests/e2e/ai_chat/` 框架: `test_cases.yaml` (3 场景), `runner.py`, `judge.py` | 无 |
| **Phase 2** | `auto_evaluate.py` + 报告模板 | Phase 1 |
| **Phase 3** | `test_web_flow.py` pytest 改造 | 无（可与 Phase 1 并行） |
| **Phase 4** | `.github/workflows/e2e.yaml` + Makefile 扩展 | Phase 1-3 |
| **Phase 5** | Golden answers 初始集 + L3 校准流程文档 | Phase 1 运行后 |
