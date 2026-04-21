# 猫维斯（Catvis）架构文档

## 1. 项目定义

`猫维斯（Catvis）` 的目标不是再做一个聊天窗口，而是把现有稳定的 `XiaoBa Runtime` 投射到一台电脑这个真实载体上，让电脑本身成为助手的“身体”：

- 麦克风是输入
- 屏幕上的动态猫猫是表情和状态
- 音响是语音输出
- `XiaoBa-CLI` 是大脑与执行核心

一句话定义：

`猫维斯 = 以 XiaoBa Runtime 为核心、以本机音视频设备为感官与表达器官、以动态猫猫为状态界面的桌面常驻 Agent。`

## 2. 现有可复用基础

当前仓库里已经有可直接复用的三块基础，不需要从零重造。

### 2.1 XiaoBa Runtime 基础

`XiaoBa-CLI` 已经具备这些底座：

- `src/core/*`：会话、上下文、conversation runner
- `src/tools/*`：工具执行和发送能力
- `src/roles/*`：角色加载机制
- `src/bridge/bridge-server.ts`：本地 HTTP bridge，可承接状态/事件通道
- `src/dashboard/server.ts`：本地 dashboard server
- `electron/main.js`：桌面壳、托盘、内置服务启动

这意味着 `猫维斯` 不应该另起一套 agent runtime，而应该作为 `XiaoBa-CLI` 的一个本地交互形态。

### 2.2 桌面壳基础

`XiaoBa-CLI/electron/main.js` 已证明当前 runtime 已能：

- 被 Electron 承载
- 常驻桌面/托盘
- 启动本地 dashboard server
- 形成本地应用分发形态

所以 `猫维斯` 最合理的壳层依然是 Electron，而不是另开一个完全独立的桌面框架。

### 2.3 动态猫猫前端基础

`E:\CatCompany-BestBotCommunity\cat-Os\cat-orb-demo` 已经有一个可复用的动态猫猫视觉底座：

- React + Vite
- OGL/WebGL 渲染
- 当前已有 hover、旋转、光效、猫头轮廓

这块适合被升级成 `Avatar Renderer`，而不是重做 2D/3D 角色系统。

## 3. 设计原则

### 3.1 一个 Runtime，多个外壳

`猫维斯` 只是 `XiaoBa Runtime` 的一个 embodied shell，不应复制会话管理、工具系统、skills、roles。

### 3.2 视觉状态必须服务交互，不做纯装饰

猫猫的动作和表情必须直接映射到运行状态，至少让用户一眼区分：

- 空闲
- 推理中
- 输出中

### 3.3 先做稳定感，再做拟人感

MVP 先追求：

- 语音输入稳定
- 状态切换准确
- 语音输出自然
- 窗口/托盘常驻可靠

而不是优先追求复杂表情骨骼、唤醒词、长时多模态。

### 3.4 本机优先

第一阶段把“这台电脑就是硬件”跑通，不依赖外接传感器、外接屏幕、外设控制器。

## 4. 总体架构

```text
用户
  -> 麦克风输入
  -> Audio Capture
  -> STT / VAD
  -> Turn Controller
  -> XiaoBa Runtime
  -> Response Planner
  -> TTS
  -> 音响输出

同时：
Turn Controller / Runtime / TTS
  -> Avatar State Service
  -> Cat Orb Renderer
  -> 屏幕上的猫猫动作、表情、字幕、状态灯

同时：
所有关键事件
  -> Session Log / Metrics / Debug Panel
```

## 5. 模块分层

## 5.1 Device I/O Layer

职责：

- 接管系统默认麦克风
- 采集音频流
- 做静音检测、VAD、录音片段切分
- 调用 STT
- 调用 TTS 并输出到系统音响

建议拆分：

1. `AudioCaptureService`
2. `VoiceActivityDetector`
3. `SpeechToTextService`
4. `TextToSpeechService`
5. `AudioPlaybackService`

说明：

- MVP 建议先做 `按键说话 / 点击说话`，再扩展到免按键唤醒
- 这样能减少误触发、串音、回声和长时监听复杂度

## 5.2 Interaction Orchestration Layer

这是 `猫维斯` 的新增核心层，负责把“语音交互”翻译成 runtime 可执行的 turn。

核心职责：

- 管理一次完整 turn 的生命周期
- 接收 STT 文本
- 调用 `XiaoBa Runtime`
- 在推理期间更新视觉状态
- 在输出阶段协调 TTS、字幕、屏幕文本

建议新增组件：

1. `TurnController`
2. `MicSessionManager`
3. `AvatarStateService`
4. `ResponseOutputCoordinator`

其中：

- `TurnController` 是交互状态机核心
- `AvatarStateService` 只负责状态广播，不负责业务推理

## 5.3 Runtime Layer

直接复用 `XiaoBa-CLI`：

- `conversation-runner`
- `agent-session`
- `message-session-manager`
- `roles`
- `skills`
- `tools`

这里的输入不再只是 CLI 文本，也可以来自语音转写后的文本。

建议新增一个轻量适配器：

- `voice-runtime-adapter`

职责：

- 将 STT 文本包装成标准用户消息
- 把 runtime 输出包装成 `speakable text`、`subtitle text`、`display text`

## 5.4 Avatar Presentation Layer

基于 `cat-orb-demo` 进化为桌面 Agent 形象层。

建议拆分为：

1. `CatAvatarRenderer`
2. `ExpressionPresetManager`
3. `SubtitlePanel`
4. `StatusOverlay`

### 三个预设动作

用户提出的三个状态非常合理，建议作为第一版外显动作：

1. `Idle`
2. `Thinking`
3. `Speaking`

对应表现：

- `Idle`：低振幅呼吸、轻微漂浮、平静眼神
- `Thinking`：更高频的内发光、耳朵或轮廓轻抖、视线聚焦
- `Speaking`：口型/波纹/亮度脉冲与 TTS 音量同步

建议注意：

- 内部状态可以细分，但 UI 外显先只保留这 3 个主状态
- 用户应该不需要理解系统内部复杂状态机

## 5.5 Desktop Shell Layer

继续使用 Electron，负责：

- 开机自启动
- 托盘常驻
- 无边框/置顶/小窗模式
- 权限申请（麦克风）
- 本地页面装载
- 本地配置页、调试页

建议新增窗口形态：

1. `Avatar Window`
2. `Control Window`
3. `Debug Window`

说明：

- `Avatar Window` 是用户平时看到的猫猫
- `Control Window` 是设置和会话入口
- `Debug Window` 只给开发调试使用

## 5.6 Observability Layer

这是现有 `XiaoBa World` 思路里很重要的一层，必须保留。

应记录：

- 原始音频片段索引
- STT 文本
- turn 开始/结束时间
- runtime 耗时
- TTS 耗时
- avatar 状态切换序列
- 异常和中断原因

价值：

- 调试误唤醒、误识别
- 分析推理时延
- 反向喂给 `InspectorCat`

## 6. 核心状态机

虽然外显只有三态，但内部建议采用更严格的状态机。

```text
BOOTING
  -> IDLE
  -> LISTENING
  -> TRANSCRIBING
  -> THINKING
  -> SPEAKING
  -> INTERRUPTED
  -> ERROR
  -> IDLE
```

对用户可见的映射关系：

- `IDLE` -> 闲置
- `LISTENING / TRANSCRIBING / THINKING` -> 推理
- `SPEAKING` -> 输出
- `ERROR` -> 输出态中的错误表情或提示

这样做的原因：

- UI 仍然简单
- 工程侧可以精确定位卡在“没听到”“没识别出来”“在思考”“在播报”

## 7. 关键数据流

## 7.1 语音输入链路

```text
Mic
  -> AudioCaptureService
  -> VAD
  -> SpeechToTextService
  -> TurnController
  -> Runtime Adapter
  -> XiaoBa Runtime
```

## 7.2 输出链路

```text
XiaoBa Runtime
  -> ResponseOutputCoordinator
  -> TextToSpeechService
  -> AudioPlaybackService
  -> Speaker
```

## 7.3 视觉状态链路

```text
TurnController / Runtime / TTS callbacks
  -> AvatarStateService
  -> Electron local event bus / WebSocket / HTTP bridge
  -> CatAvatarRenderer
```

建议优先选型：

- 本地单机优先时，`WebSocket` 最合适
- 若想复用现有 `bridge-server.ts` 设计，可扩一层本地事件桥

## 8. 关键接口建议

## 8.1 Avatar 状态事件

```json
{
  "type": "avatar_state_changed",
  "sessionId": "voice-session-001",
  "turnId": "turn-042",
  "state": "thinking",
  "emotion": "focused",
  "energy": 0.72,
  "text": "我在想一下",
  "timestamp": 1760000000000
}
```

## 8.2 语音 turn 请求

```json
{
  "type": "voice_turn_request",
  "sessionId": "desktop-main",
  "inputMode": "push_to_talk",
  "transcript": "帮我总结今天的工作重点",
  "audioRef": "audio/2026-04-16/clip-001.wav",
  "timestamp": 1760000000000
}
```

## 8.3 Runtime 输出结果

```json
{
  "type": "assistant_response",
  "turnId": "turn-042",
  "displayText": "今天建议先处理三件事……",
  "speakText": "今天建议你先处理三件事。",
  "mood": "calm",
  "actions": ["speak"],
  "timestamp": 1760000005000
}
```

## 9. 典型时序

## 9.1 一次正常交互

```text
用户按住说话
  -> 猫猫进入 Thinking 外显态（内部为 Listening）
  -> 录音结束
  -> STT 完成
  -> TurnController 调 XiaoBa Runtime
  -> 猫猫维持 Thinking 态
  -> runtime 返回文本
  -> TTS 开始
  -> 猫猫切 Speaking
  -> 屏幕显示字幕
  -> 音频播报完成
  -> 猫猫回到 Idle
```

## 9.2 中断场景

```text
TTS 播放中用户再次说话
  -> TurnController 触发 interrupt
  -> AudioPlaybackService 停止当前播放
  -> 当前 turn 标记为 interrupted
  -> 重新进入 Listening
```

## 10. 部署方式

第一阶段建议单机进程内或单机本地多进程部署。

### 方案 A：Electron + 内嵌本地服务

```text
Electron Main
  -> Dashboard / API Server
  -> Runtime Service
  -> Voice Service
  -> Avatar Frontend
```

优点：

- 最贴近现有 `XiaoBa-CLI`
- 打包简单
- 本地调试路径清晰

### 方案 B：Runtime 独立进程 + Avatar 独立前端

```text
Runtime Process
  <-> local ws/http
Avatar Frontend
  <-> Electron Shell
```

优点：

- 更利于后续分布式扩展
- 更容易替换前端表现层

当前建议：

`MVP 用方案 A，二期再考虑拆进程。`

## 11. 推荐目录落法

可以先在 `XiaoBa-CLI` 内部增量式接入，不急着重组整个仓库。

```text
XIAOBA-World/
  docs/
    CATVIS_ARCHITECTURE.md
    CATVIS_PRD.md
  XiaoBa-CLI/
    src/
      embodied/
        audio/
        avatar/
        turn-controller/
        voice-runtime-adapter/
      desktop/
        avatar-gateway/
```

`cat-orb-demo` 可以作为：

- 前期原型来源
- shader / renderer 参考实现
- 后续再决定是迁入 `XiaoBa-CLI/dashboard`，还是保留成独立前端包

## 12. 技术选型建议

MVP 推荐：

- 桌面壳：Electron
- runtime：复用 `XiaoBa-CLI`
- 前端：React
- 动态渲染：延续 `cat-orb-demo` 的 OGL/WebGL 方案
- 状态通道：本地 WebSocket
- STT：先接稳定云服务或系统 API
- TTS：先接稳定云服务或系统 API

原因很直接：

- 你当前最强资产不是音频算法，而是稳定的 runtime
- `猫维斯` 的第一优先级是把运行稳定性转成“有身体感的存在”

## 13. 风险与约束

### 13.1 语音链路比文字链路更脆弱

主要风险：

- 噪音环境误触发
- 回声导致重复识别
- STT 错字
- TTS 打断不自然

### 13.2 状态切换很容易假

如果 `Thinking` 和 `Speaking` 切换不准，猫猫会像装饰，而不是 agent 身体。

### 13.3 多进程同步复杂度会上升

如果一开始就把 runtime、voice、renderer 拆太散，调试成本会急剧变高。

### 13.4 麦克风权限和后台运行是桌面产品真实门槛

这部分不是“写完代码就自然成立”，需要在 Electron 壳层处理好。

## 14. 实施建议

### Phase 1：最小闭环

目标：

- 按键说话
- 语音转文本
- 调用 XiaoBa
- TTS 播报
- 猫猫三态切换

### Phase 2：桌面化

目标：

- 托盘常驻
- 小窗模式
- 配置页
- 会话字幕
- 中断机制

### Phase 3：更像“贾维斯”

目标：

- 唤醒词
- 更细表情
- 情绪映射
- 主动提醒
- 与系统通知、文件、日历联动

## 15. 当前结论

这个 idea 完全成立，而且技术路线也不是空想。

最关键的判断是：

- `XiaoBa-CLI` 已经是稳定的大脑
- 电脑本机就是第一代硬件壳
- `cat-orb-demo` 可以成为外显身体
- 真正需要新增的是 `语音交互编排层 + Avatar 状态服务`

所以 `猫维斯` 最合理的落地方式不是另起炉灶，而是：

`在现有 XiaoBa Runtime 之上，加一层 embodied interaction stack，让电脑变成 XiaoBa 的身体。`
