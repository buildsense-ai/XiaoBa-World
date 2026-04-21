# XiaoBa World Agent Loop 设计文档

## 1. 目标

`XiaoBa World` 的目标不是简单堆多个角色，而是形成一个可持续自我演化的 agent loop：

1. 用户在不同平台使用本地或云端 `XiaoBa Runtime`
2. Runtime 产生 `.log` 和 `.jsonl`
3. `InspectorCat` 从日志中发现 runtime 问题、skill 问题、角色机会
4. 修复型角色与提炼型角色接手，生成 runtime patch、skill spec、role spec
5. 验证型角色确认修复是否有效
6. 发布型角色把新 runtime、skills、roles 推给用户
7. 新一轮真实日志再次进入 loop

这条 loop 的核心不是“让一个 agent 什么都做”，而是让多个角色各自承担稳定职责，并通过标准化产物交接。

## 2. 总体原则

- 只维护一套 `XiaoBa-CLI` runtime 内核
- 角色是 runtime 上的 specialization，不是复制 runtime
- 公共能力进 core，角色差异进 `roles/<role>` 和 `src/roles/<role>`
- 日志、报告、spec、patch、验证结果必须标准化
- agent 之间通过群聊协作，不走隐式魔法调用
- 群聊消息和文件发送只使用 `send_text` 与 `send_file`
- 角色默认先审查、再交接、再执行，不盲目直接改

## 3. Agent Loop 数据流

```text
用户使用 XiaoBa
  -> runtime 生成 logs
  -> send_to_inspector 上传 logs
  -> Inspector inbox/store 收件
  -> Inspector worker 自动分析
  -> InspectorCat 产出 review report
  -> RuntimeDoctor / SkillDoctor / RoleArchitect 接手
  -> VerifierCat 回归验证
  -> Publisher/OpsCat 发布
  -> 用户继续使用
  -> 新 logs 回流
```

## 4. 角色分层

`XiaoBa World` 里的角色建议分成三层。

### 4.1 系统角色

这些角色服务于 agent loop 自身，是整个世界的“自我进化系统”。

1. `InspectorCat`
2. `RuntimeDoctor`
3. `SkillDoctor`
4. `RoleArchitect`
5. `VerifierCat`
6. `Publisher` 或 `OpsCat`

### 4.2 领域角色

这些角色服务具体业务流程，不负责 runtime 自我进化。

当前已有：

1. `SciPaperDoctor`

未来可扩展：

1. `CodeDoctor`
2. `DataDoctor`
3. `OpsDoctor`
4. `ReportDoctor`

### 4.3 协调角色

严格来说，协调角色可以先不独立成 role，而是由群聊协议和简单 dispatcher 先承担。

长期建议新增：

1. `LoopCoordinator`

它只负责：

- 收集各角色产物
- 判定交给谁
- 维护 case 状态
- 不亲自做深分析或深实现

## 5. 最小闭环角色集

如果只追求真正跑通 agent loop，最小可用集合是：

1. `InspectorCat`
2. `RuntimeDoctor`
3. `SkillDoctor`
4. `VerifierCat`

如果要让 loop 还能长出新角色，再加：

5. `RoleArchitect`

如果要形成“从优化到发布”的完整工程闭环，再加：

6. `Publisher`

## 6. 每个角色的目标与产物

### 6.1 InspectorCat

目标：

- 深度分析 XiaoBa 的 `.log` 与 `.jsonl`
- 识别 runtime 缺陷、skill 缺陷、prompt/usage 问题
- 识别 skill opportunity 与 role opportunity
- 给出高可信 review report

输入：

- runtime `.log`
- session `.jsonl`
- case 描述

输出：

- `review_report.md`
- `runtime_findings.json`
- `skill_opportunities.json`
- `role_opportunities.json`
- `priority_recommendation.json`

已有能力：

- `analyze_log` tool
- `log-review`
- `log-to-skill`
- `log-to-role`
- `runtime-doctor`

还需要强化：

- 跨多文件日志聚合
- 群聊交接模板
- 更强的证据等级标注
- 面向其他 agent 的标准报告格式

需要的 system prompt 目标：

- review first
- 用证据说话
- 不直接吞没实现职责
- 明确把问题分流给 RuntimeDoctor / SkillDoctor / RoleArchitect

### 6.2 RuntimeDoctor

目标：

- 接收 Inspector 的 runtime findings
- 修复 core runtime、tools、platform integration、context、token、scheduler 问题
- 输出最小有效 patch

输入：

- `review_report.md`
- `runtime_findings.json`
- 相关代码路径

输出：

- `runtime_patch_plan.md`
- `code_diff`
- `migration_notes.md`
- `runtime_fix_report.md`

需要的 skills：

1. `runtime-patch-planner`
2. `platform-compat-doctor`
3. `tool-reliability-doctor`
4. `context-window-doctor`
5. `log-pipeline-doctor`

需要的 tools：

- `read_file`
- `edit_file`
- `write_file`
- `grep`
- `glob`
- `execute_shell`
- 测试工具

需要的 utils：

- patch summary formatter
- regression target collector
- issue-to-file mapper

system prompt 目标：

- 默认修最小闭环
- 先解释归因再改
- 不越权去重写产品路线

### 6.3 SkillDoctor

目标：

- 将 Inspector 发现的稳定重复模式沉淀成 skill
- 修复已有 skill 的 trigger、tool policy、输出协议问题

输入：

- `skill_opportunities.json`
- 代表性 logs
- 失败/成功案例

输出：

- `skill_spec.md`
- `SKILL.md`
- `tool_policy.json`
- `trigger_examples.md`
- `skill_validation_report.md`

需要的 skills：

1. `skill-spec-writer`
2. `trigger-tightener`
3. `tool-policy-doctor`
4. `skill-evaluator`

需要的 tools：

- 文件编辑工具
- role/skill 目录扫描工具
- 测试工具

需要的 utils：

- skill scaffold helper
- prompt compact formatter
- invocation example generator

system prompt 目标：

- 不把一次性操作误判成 skill
- 先定义边界，再写 skill 文本
- skill 必须可触发、可复现、可验证

### 6.4 RoleArchitect

目标：

- 判断某类模式是否已经不适合只做 skill，而应该独立成 role
- 为新 role 定义边界、职责、与其他角色的关系

输入：

- `role_opportunities.json`
- 多份 logs
- 现有 role/skill 版图

输出：

- `role_spec.md`
- `role_boundary.md`
- `role_interaction_map.md`
- `role_bootstrap_plan.md`

需要的 skills：

1. `role-spec-writer`
2. `role-boundary-check`
3. `role-to-skill-splitter`

需要的 utils：

- role manifest validator
- capability overlap checker

system prompt 目标：

- 保证新 role 真有独立长期职责
- 不制造名字不同但行为相同的空壳角色

### 6.5 VerifierCat

目标：

- 验证 runtime 修复和 skill 提炼是否真的有效
- 回放真实 case，看问题是否消失
- 拦截回归

输入：

- patch
- skill spec
- 历史失败 case
- 新运行日志

输出：

- `verification_report.md`
- `regression_matrix.json`
- `go_no_go.md`

需要的 skills：

1. `case-replay-verifier`
2. `runtime-regression-check`
3. `skill-regression-check`
4. `diff-impact-review`

需要的 tools：

- 测试运行工具
- 日志对比工具
- 文件与目录 diff 工具

需要的 utils：

- replay harness
- result comparer
- baseline case packager

system prompt 目标：

- 只看证据与回放结果
- 不掺入产品幻想
- 结论必须明确：通过 / 不通过 / 需人工确认

### 6.6 Publisher / OpsCat

目标：

- 把经过验证的 runtime、skills、roles 推送给用户
- 管理版本、发布说明、升级节奏

输入：

- 验证通过的 patch 和 spec
- 发布目标用户范围

输出：

- `release_note.md`
- `upgrade_pack`
- `rollout_plan.md`

需要的 skills：

1. `release-note-writer`
2. `rollout-planner`
3. `user-impact-summarizer`

system prompt 目标：

- 不发未验证内容
- 关注兼容性与回滚

### 6.7 SciPaperDoctor

这是现有领域角色样板，不属于 loop 自我修复核心，但会不断产生高质量真实日志，反向喂养 loop。

目标：

- 推进论文项目交付
- 审查实验、稿件、编译、审稿意见

价值：

- 提供长链路真实场景
- 产生 role opportunity 与 skill opportunity

## 7. 角色需要的能力栈

每个角色最终都应该从四层能力来描述。

### 7.1 system prompt

回答：

- 这个角色存在是为了解决什么问题
- 它不该解决什么问题
- 它默认如何决策
- 它与其他角色怎么分工

### 7.2 skills

回答：

- 这个角色有哪些稳定工作流
- 哪些步骤值得复用
- 如何输入、如何输出

### 7.3 tools

回答：

- 角色直接拥有的硬能力是什么
- 哪些事情是 deterministic 的，必须写成 tool

典型判断：

- 日志收发、解析、文件操作、测试运行，适合 tool
- 审查流程、诊断流程、提炼流程，适合 skill

### 7.4 utils

回答：

- 角色 runtime 的支撑设施是什么
- 例如 store、router、worker、formatter、replay harness

## 8. Agent 间通信设计

通信目标不是“模拟人聊天”，而是让角色之间能稳定交接任务和产物。

### 8.1 通信载体

通信统一基于群聊。

建议有两类群：

1. `系统 loop 群`
2. `领域项目群`

系统 loop 群用于：

- `InspectorCat`
- `RuntimeDoctor`
- `SkillDoctor`
- `RoleArchitect`
- `VerifierCat`
- `Publisher`

领域项目群用于：

- `SciPaperDoctor`
- 其他领域 doctor
- 人类用户

### 8.2 通信工具

agent 间只允许这两类外显通信工具：

1. `send_text`
2. `send_file`

原则：

- 短交接走 `send_text`
- 长报告、spec、patch plan、verification report 走 `send_file`

### 8.3 标准通信协议

所有 agent 之间的交接消息都建议遵守固定协议。

短消息结构：

```text
[case_id]
[from]
[to]
[intent]
[summary]
[required_artifacts]
[priority]
```

长文件结构建议统一：

1. 背景
2. 证据
3. 当前判断
4. 需要下游角色做什么
5. 完成标准

### 8.4 推荐通信动作

`InspectorCat -> RuntimeDoctor`

- `send_text` 发送摘要
- `send_file` 附 `review_report.md`

`InspectorCat -> SkillDoctor`

- `send_text` 发送 skill opportunity 简述
- `send_file` 附 `skill_opportunities.json`

`InspectorCat -> RoleArchitect`

- `send_text` 发送 role opportunity 判断
- `send_file` 附 `role_opportunities.json`

`RuntimeDoctor / SkillDoctor -> VerifierCat`

- `send_text` 通知“需要验证”
- `send_file` 附 patch plan 或 skill spec

`VerifierCat -> Publisher`

- `send_text` 通知 go/no-go
- `send_file` 附验证报告

### 8.5 为什么用群聊

群聊模式的好处：

- 交接透明
- 方便人类旁观与插话
- 天然形成 case 时间线
- 适合多个 agent 串行或并行协作

需要注意：

- 群聊不是随意闲聊，必须有结构化消息模板
- 超长内容不能直接刷屏，必须 `send_file`

## 9. 先造什么

按优先级，建议这样落：

### 第一阶段：打通最小 loop

1. `InspectorCat`
2. `RuntimeDoctor`
3. `SkillDoctor`
4. `VerifierCat`

目标：

- 从真实日志发现问题
- 修 runtime
- 提 skill
- 回归验证

### 第二阶段：长出角色工厂能力

1. `RoleArchitect`

目标：

- 从长日志中判断新 role 机会
- 输出新角色定义

### 第三阶段：上线发布闭环

1. `Publisher`

目标：

- 把验证通过的版本推给用户

### 第四阶段：扩业务 doctor

1. `SciPaperDoctor`
2. 其他领域 doctor

目标：

- 用更复杂的真实世界任务反哺系统 loop

## 10. 未来目录建议

```text
XiaoBa-CLI/
  roles/
    inspector-cat/
    runtime-doctor/
    skill-doctor/
    role-architect/
    verifier-cat/
    publisher/
    sci-paper-doctor/
  src/
    roles/
      inspector-cat/
        tools/
        utils/
      runtime-doctor/
        utils/
      verifier-cat/
        utils/
```

## 11. 当前结论

`XiaoBa World` 的 agent loop 核心不是“多造几个酷炫角色”，而是先形成这条稳定链：

`真实用户日志 -> InspectorCat -> RuntimeDoctor / SkillDoctor / RoleArchitect -> VerifierCat -> Publisher -> 新日志回流`

群聊通信不是附属品，而是整个世界的协作骨架。

`send_text` 负责轻量交接，`send_file` 负责正式产物。

只要这条链跑通，后面的 doctor 角色就会越长越自然，`XiaoBa World` 也才会真正从“角色集合”进化成“能自我优化的 agent 世界”。
