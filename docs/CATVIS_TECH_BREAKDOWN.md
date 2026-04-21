# 猫维斯（Catvis）技术拆解清单

## 1. 文档目标

本文件用于把 `猫维斯` 从概念和 PRD 拆成可以直接执行的工程任务，目标是：

- 明确复用哪些现有能力
- 明确新增哪些模块
- 明确建议目录和接入点
- 明确实施顺序、依赖关系、完成标准和测试策略

## 2. 总体实现策略

核心原则只有一句：

`不要重写 XiaoBa Runtime，只在外层增加 voice adapter、turn orchestration 和 avatar presentation。`

因此实现策略应是：

1. 保留 `XiaoBa-CLI` 作为统一 runtime
2. 在 `XiaoBa-CLI` 内新增 embodied interaction 模块
3. 用 Electron 承载桌面壳
4. 用 dashboard/API 或本地事件总线驱动猫猫前端
5. 以 `cat-orb-demo` 作为猫猫渲染原型来源

## 3. 现有代码资产与接入点

当前最关键的接入点如下：

### 3.1 Runtime 入口

- `XiaoBa-CLI/src/index.ts`
- `XiaoBa-CLI/src/core/*`
- `XiaoBa-CLI/src/commands/chat.ts`

价值：

- 已有统一对话入口和会话机制
- 后续需要补一个“语音 turn -> 标准消息”的适配入口

### 3.2 桌面壳

- `XiaoBa-CLI/electron/main.js`

价值：

- 已有 Electron 主进程
- 已有窗口、托盘、dashboard server 启动逻辑
- 后续适合新增 `Avatar Window`

### 3.3 Dashboard / API

- `XiaoBa-CLI/src/dashboard/server.ts`
- `XiaoBa-CLI/src/dashboard/routes/api.ts`

价值：

- 已有 Express API 体系
- 适合挂载 `avatar status`、`voice config`、`turn logs`、`debug endpoints`

### 3.4 服务编排

- `XiaoBa-CLI/src/dashboard/service-manager.ts`

价值：

- 现有服务管理机制可参考，但 `猫维斯` MVP 不建议一开始拆成太多独立子进程

### 3.5 本地事件桥

- `XiaoBa-CLI/src/bridge/bridge-server.ts`

价值：

- 可复用其事件和结果回传设计
- 也可作为后续本地 bot/avatar 事件桥参考

### 3.6 猫猫前端原型

- `E:\CatCompany-BestBotCommunity\cat-Os\cat-orb-demo`

重点文件：

- `src/App.jsx`
- `src/CatOrb.jsx`
- `src/Orb.jsx`

价值：

- 已有动态视觉底座，可直接升级成三态猫猫 renderer

## 4. 建议目录方案

建议在 `XiaoBa-CLI` 内增量式落地，不另起新 runtime 仓库。

```text
XiaoBa-CLI/
  src/
    embodied/
      types/
        voice.ts
        avatar.ts
      audio/
        audio-capture-service.ts
        audio-playback-service.ts
        voice-activity-detector.ts
      speech/
        speech-provider.ts
        stt-service.ts
        tts-service.ts
      orchestration/
        turn-controller.ts
        mic-session-manager.ts
        response-output-coordinator.ts
      runtime/
        voice-runtime-adapter.ts
      avatar/
        avatar-state-service.ts
        avatar-event-bus.ts
      observability/
        voice-turn-logger.ts
        latency-metrics.ts
    dashboard/
      routes/
        api.ts
        avatar.ts
    desktop/
      avatar-window-manager.ts
```

前端建议两种路线二选一：

### 路线 A：迁入现有 dashboard

优点：

- 统一打包
- Electron 集成最简单

### 路线 B：保留独立前端包

优点：

- 更利于独立迭代猫猫表现层

MVP 建议：

`优先路线 A`。先把 `cat-orb-demo` 的核心渲染逻辑迁入现有 dashboard/static frontend 体系，减少进程和打包复杂度。

## 5. 模块拆解

## 5.1 Voice Types

任务：

- 定义语音 turn、录音片段、STT 结果、TTS 结果、avatar 状态事件等基础类型

建议文件：

- `src/embodied/types/voice.ts`
- `src/embodied/types/avatar.ts`

完成标准：

- 关键事件和状态都具备稳定类型定义
- 后续模块不再各自定义松散对象

## 5.2 Audio Capture

任务：

- 接收麦克风输入
- 管理录音开始、录音停止、错误事件
- 输出音频 buffer 或文件引用

建议文件：

- `src/embodied/audio/audio-capture-service.ts`

注意：

- 第一版优先做 `push-to-talk`
- 不要第一版就做持续监听

完成标准：

- 能从 UI 触发录音开始/结束
- 能获得稳定音频片段
- 权限异常可回报到上层

## 5.3 Voice Activity Detector

任务：

- 对音频做简单静音检测和截断辅助

建议文件：

- `src/embodied/audio/voice-activity-detector.ts`

注意：

- MVP 可选做最简版本
- 如果接入按键说话，VAD 不是阻塞项

完成标准：

- 即便没有复杂 VAD，录音结束边界也清晰可控

## 5.4 STT Service

任务：

- 将音频转文本
- 支持 provider 抽象，避免和单一模型强绑定

建议文件：

- `src/embodied/speech/speech-provider.ts`
- `src/embodied/speech/stt-service.ts`

建议能力：

- `transcribe(audioInput): Promise<TranscriptResult>`
- 返回文本、耗时、原始 provider metadata

完成标准：

- 一次语音输入可稳定转换成文本
- 错误和耗时可被记录

## 5.5 TTS Service

任务：

- 将 runtime 文本回复转成可播放音频

建议文件：

- `src/embodied/speech/tts-service.ts`
- `src/embodied/audio/audio-playback-service.ts`

建议能力：

- `synthesize(text): Promise<AudioOutput>`
- `play(audioOutput): Promise<void>`
- `stop(): void`

完成标准：

- 可播报文本
- 可中断当前播报
- 可回调“播放开始/播放结束/播放失败”

## 5.6 Voice Runtime Adapter

任务：

- 将 STT 文本包装成标准 runtime 输入
- 将 runtime 输出包装为显示文本、播报文本、字幕文本

建议文件：

- `src/embodied/runtime/voice-runtime-adapter.ts`

建议能力：

- `runVoiceTurn(transcript, sessionId, role?): Promise<VoiceTurnResult>`

完成标准：

- 不修改 core runtime 的主逻辑
- 语音 turn 能复用现有会话与日志机制

## 5.7 Turn Controller

任务：

- 管理一次完整语音 turn 的生命周期
- 负责状态机推进
- 负责中断和错误恢复

建议文件：

- `src/embodied/orchestration/turn-controller.ts`

核心状态：

- `idle`
- `listening`
- `transcribing`
- `thinking`
- `speaking`
- `interrupted`
- `error`

完成标准：

- 任意一次 turn 都能清晰追踪状态变化
- 中断和失败不会导致状态机悬空

## 5.8 Response Output Coordinator

任务：

- 接收 runtime 结果
- 决定显示文本、字幕文本、播报文本
- 协调 TTS 与 avatar 状态

建议文件：

- `src/embodied/orchestration/response-output-coordinator.ts`

完成标准：

- `thinking -> speaking -> idle` 的状态切换稳定
- 字幕和播报能保持基本一致

## 5.9 Avatar State Service

任务：

- 把 turn 状态广播给前端猫猫
- 把文本片段、能量值、错误信息等转成 UI 可用事件

建议文件：

- `src/embodied/avatar/avatar-state-service.ts`
- `src/embodied/avatar/avatar-event-bus.ts`

建议事件：

- `avatar_state_changed`
- `subtitle_updated`
- `voice_level_updated`
- `turn_failed`

完成标准：

- 前端不需要知道 runtime 内部细节
- 前端只消费稳定事件

## 5.10 Avatar Frontend

任务：

- 把 `cat-orb-demo` 升级成三态猫猫界面
- 接收状态事件，切换 `idle / thinking / speaking`
- 显示字幕和错误状态

建议来源：

- 迁移 `cat-orb-demo/src/CatOrb.jsx` 的渲染逻辑

建议前端组件：

- `CatAvatar`
- `SubtitlePanel`
- `StatusBadge`
- `AvatarShell`

完成标准：

- 三态视觉差异明显
- speaking 态可响应音量或节奏
- thinking 态和 idle 态不会混淆

## 5.11 Electron Avatar Window

任务：

- 新增一个专门显示猫猫的小窗口
- 支持置顶、透明背景、拖动、隐藏、恢复

建议文件：

- `electron/main.js`
- `src/desktop/avatar-window-manager.ts`

完成标准：

- 猫猫窗口可以独立存在
- 不依赖完整 dashboard 主窗口常驻前台

## 5.12 API 与调试面板

任务：

- 暴露语音配置、最近 turn、状态流、错误日志等接口

建议改动：

- 扩展 `src/dashboard/routes/api.ts`
- 如有必要新增 `src/dashboard/routes/avatar.ts`

建议接口：

- `GET /api/avatar/status`
- `GET /api/avatar/turns`
- `POST /api/avatar/listen/start`
- `POST /api/avatar/listen/stop`
- `POST /api/avatar/speak/stop`
- `GET /api/avatar/config`
- `PUT /api/avatar/config`

完成标准：

- 不进入终端也能完成主要调试
- 调试页可查看最近 turn 的全过程

## 5.13 Observability

任务：

- 记录 turn 开始/结束时间
- 记录 STT、runtime、TTS、播放耗时
- 记录状态切换和异常

建议文件：

- `src/embodied/observability/voice-turn-logger.ts`
- `src/embodied/observability/latency-metrics.ts`

完成标准：

- 出现问题时能判断卡在录音、识别、推理还是播报
- 日志可回流给现有 `InspectorCat`

## 6. 推荐实现顺序

## Phase 0：最小原型验证

目标：

- 不接真实语音模型，先用假数据打通状态机和猫猫三态

任务：

1. 搭建 `TurnController`
2. 搭建 `AvatarStateService`
3. 让前端猫猫接收状态并切换三态
4. 用 mock transcript 和 mock response 演示完整流程

完成标准：

- 可以手动触发 `idle -> thinking -> speaking -> idle`
- 三态切换稳定可见

## Phase 1：接入真实 STT/TTS

目标：

- 从 mock 进入真实语音闭环

任务：

1. 实现 `AudioCaptureService`
2. 实现 `STTService`
3. 实现 `TTSService`
4. 实现 `AudioPlaybackService`

完成标准：

- 用户可完成一次真实语音输入和语音播报

## Phase 2：接入 XiaoBa Runtime

目标：

- 把识别文本送入真实 runtime

任务：

1. 实现 `VoiceRuntimeAdapter`
2. 让 runtime 输出进入 `ResponseOutputCoordinator`
3. 把结果写入标准会话日志

完成标准：

- 一次语音 turn 与现有文本 turn 在日志层可统一追踪

## Phase 3：桌面常驻与 UI 调试

目标：

- 让它变成真正可挂在桌面的产品原型

任务：

1. 新增 `Avatar Window`
2. 托盘控制窗口显示/隐藏
3. 增加调试页和设置页

完成标准：

- 猫猫可独立显示、隐藏、恢复
- 用户可查看最近 turn 日志

## Phase 4：中断与错误恢复

目标：

- 让交互像真实助手，而不是播放器

任务：

1. 实现 speaking 中断
2. 实现失败状态反馈
3. 实现超时与恢复逻辑

完成标准：

- 用户可以在播报中发起新输入
- 失败后可恢复到 idle

## Phase 5：可用性打磨

目标：

- 从可演示原型进入可持续使用原型

任务：

1. 优化状态切换准确性
2. 优化字幕体验
3. 优化启动和恢复
4. 优化配置与 provider 切换

完成标准：

- 能稳定支撑长时间桌面常驻试用

## 7. 每阶段建议交付物

### Phase 0

- 三态猫猫 demo
- turn 状态机图
- mock 事件流

### Phase 1

- 语音输入原型
- STT/TTS provider 封装
- 第一版音频日志

### Phase 2

- `VoiceRuntimeAdapter`
- 真实 runtime 闭环
- 统一 turn 日志

### Phase 3

- Electron avatar 小窗
- 调试页
- 基础设置页

### Phase 4

- 中断机制
- 错误恢复机制
- 更完整的状态追踪

## 8. 接口与数据结构建议

## 8.1 Voice Turn Request

```json
{
  "sessionId": "desktop-main",
  "turnId": "turn-001",
  "inputMode": "push_to_talk",
  "transcript": "帮我总结今天的工作重点",
  "audioRef": "audio/2026-04-16/clip-001.wav",
  "role": null
}
```

## 8.2 Voice Turn Result

```json
{
  "turnId": "turn-001",
  "displayText": "今天建议先处理三件事……",
  "subtitleText": "今天建议先处理三件事……",
  "speakText": "今天建议你先处理三件事。",
  "status": "ok"
}
```

## 8.3 Avatar Event

```json
{
  "type": "avatar_state_changed",
  "turnId": "turn-001",
  "state": "thinking",
  "emotion": "focused",
  "timestamp": 1760000000000
}
```

## 9. 测试策略

## 9.1 单元测试

重点覆盖：

- `TurnController` 状态机
- `VoiceRuntimeAdapter` 输入输出包装
- `ResponseOutputCoordinator`
- `AvatarStateService`

## 9.2 集成测试

重点覆盖：

- 录音结束到 runtime 调用
- runtime 返回到 TTS 播报
- speaking 中断后重新开始新 turn

## 9.3 手工验证脚本

建议至少验证：

1. 正常问答
2. 连续两轮快速发问
3. 播报中断
4. STT 故障
5. TTS 故障
6. 麦克风权限缺失

## 10. 风险与回避策略

### 10.1 语音 provider 不稳定

回避：

- provider 抽象接口先行
- 不把业务逻辑绑死在某一家实现上

### 10.2 一开始拆太多进程

回避：

- MVP 尽量在一个本地应用进程体系内完成
- 先做本地事件总线，再考虑服务拆分

### 10.3 UI 很漂亮但状态不准

回避：

- 先写状态机和事件流
- 再做视觉表现

### 10.4 语音输入误触发与打断复杂

回避：

- 第一版只做 push-to-talk
- 唤醒词延期

## 11. 并行开发建议

可以并行的部分：

1. `TurnController` 与 `AvatarStateService`
2. `cat-orb-demo` 到三态猫猫前端
3. STT/TTS provider 封装
4. 调试页接口设计

需要串行的关键链路：

1. 真实语音输入
2. runtime 适配
3. TTS 播报
4. 中断控制

原因：

- 这四项共同构成真实闭环，必须统一调试

## 12. MVP 完成定义

MVP 可以认为完成，当且仅当下面条件同时成立：

1. 用户能通过按键或点击开始一次语音输入
2. STT 能稳定产出文本
3. 文本能进入现有 `XiaoBa Runtime`
4. runtime 回复能被 TTS 播报
5. 猫猫在整个过程中稳定切换 `闲置 / 推理 / 输出`
6. 用户能在播报中打断并开始下一轮
7. 调试面板能看到最近 turn 的主要事件

## 13. 当前建议

最稳的推进方式不是马上去接所有语音模型和复杂表情，而是按下面顺序做：

1. 先用 mock 事件把三态猫猫和状态机跑通
2. 再接真实 STT/TTS
3. 再接 `XiaoBa Runtime`
4. 最后做桌面常驻、中断和打磨

这样能最大化利用你当前已经很稳定的 runtime，把新增复杂度压缩在最该新增的那一层，而不是把整套系统重新做一遍。
