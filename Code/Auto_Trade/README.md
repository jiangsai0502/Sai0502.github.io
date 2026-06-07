# MSS Bot

Auto_Trade 是一个本地运行的 MGC 5分钟 MSS/BOS 自动交易原型。

它的核心思路是：TradingView Pine 指标识别 5m 结构突破，发 webhook 到本地 Node 服务，本地服务做风控和任务排队，Chrome 扩展再在 TradingView 已登录 Tradovate 的页面里执行 bracket limit 单。

它不使用 Tradovate 官方 API key，而是依赖 TradingView 页面内已经登录的 Tradovate 会话。

这个设计主要是为了适配 prop firm / Tradovate 考试号这类场景。

## 整体数据流

1. TradingView 图表加载 Pine 指标。
2. Pine 在 5m MGC 图表上识别 swing high / swing low。
3. 当价格收盘突破结构点时，Pine 生成 MSS 或 BOS 信号。
4. 自动化版本 Pine 发送 JSON alert 到 /webhook/tradingview。
5. 本地 Node 服务验证 webhookSecret、检查风控、过滤重复/过期信号。
6. 合格信号进入本地任务队列。
7. Chrome 扩展在 TradingView 页面里轮询本地服务。
8. 扩展拿到任务后，通过页面内 Tradovate 会话下 bracket limit 单。
9. 本地控制台显示状态、最近事件、扩展在线状态、模板状态、任务状态。

## 核心目录

1. src/ 是本地 Node 服务。负责 webhook、风控、状态存储、任务队列和控制台 API。
2. pine/ 是 TradingView Pine 指标。一个用于手机提醒，一个用于自动化 webhook 信号。
3. extension/ 是 Chrome 扩展。负责连接本地服务和 TradingView 页面内的 Tradovate 会话。
4. public/ 是本地控制台页面。浏览器打开 http://127.0.0.1:8787 查看。
5. scripts/ 是辅助脚本。目前主要是从 TradingView 拉取 MGC 5分钟 OHLC 历史数据，用于复盘和研究结构。
6. data/ 保存运行状态，例如任务、事件、风控状态。data/state.json 是运行时生成的，不适合作为固定配置。

## 关键文

* src/server.js
  本地 HTTP 服务入口。提供控制台页面、状态 API、配置保存 API、TradingView webhook 接口、扩展轮询任务接口、扩展回报接口、手动全平接口。每分钟还会执行一次定时任务，例如北京时间 04:00 自动排队全平任务。
* src/relay.js
  核心交易中转逻辑。它验证 Pine 发来的信号，检查 secret、方向、entry/sl/tp/waveStart/waveEnd，过滤重复信号和过期信号，根据风控判断是否允许交易，然后把信号变成本地任务。也负责手动全平、定时全平、扩展任务回报、状态汇总。
* src/config.js
  读取配置。优先读取 config.local.json，没有则读取 config.example.json，再和代码里的默认配置合并。控制台保存设置时，会写入 config.local.json。
* src/store.js
  读写本地运行状态，默认路径是 data/state.json。里面保存已处理信号、任务队列、事件日志、扩展状态、风控状态、最后一次信号等。
* src/time.js
  北京时间相关工具。用于判断当前是否处于禁开仓时段、计算信号年龄。
* public/index.html 和 public/app.js
  本地控制台页面。可以查看自动交易开关、禁开时段、扩展在线状态、Tradovate 登录状态、bracket 模板状态、任务队列、日 PnL、连续亏损、最近事件。也可以保存部分策略参数、刷新状态、手动全平。
* extension/content/relay-client.js
  Chrome content script。运行在 TradingView 页面里，定时向本地服务汇报扩展状态，并轮询 /api/extension/next-task 获取任务。拿到任务后，把任务转交给页面主世界里的 bridge 执行。
* extension/page/tradovate-bridge.js
  真正接触 TradingView / Tradovate 页面环境的执行桥。它 hook 页面里的 fetch，捕获 Tradovate JWT、账户信息、订单/持仓状态，并学习手动 bracket limit 单的请求模板。自动下单时复用这个模板，只替换合约、方向、手数、entry、stop loss、take profit。
* pine/mgc_mss_OnlyAlert.pine
  手机提醒版 Pine。它只负责画结构线、显示 swing、触发人类可读的 TradingView alert，不发送自动化 JSON，不应该用于自动下单。
* pine/mgc_mss_retracement_alerts.pine
  自动化信号版 Pine。它识别结构突破后，计算 61.8% 回撤入场、止损、止盈，并通过 alert() 发 JSON 给本地服务。这个文件用于自动化程序。
* scripts/fetch_tv_mgc_5m.py
  研究/复盘辅助脚本。通过 databento api 获取 MGC 5分钟 OHLC 数据，从 TradingView  只能拉取最近30天

## Pine 结构定义

* swing high：某根 K 线高点高过前一根高点，先成为候选 swing high；之后如果后面的 K 线低点跌破这根候选 K 线的 low，就确认它是 swing high。

* swing low：某根 K 线低点低过前一根低点，先成为候选 swing low；之后如果后面的 K 线高点突破这根候选 K 线的 high，就确认它是 swing low。

* Loose 模式下，收盘价突破最近未被突破的 swing high / swing low 就确认结构突破。Strict 模式会额外要求实体突破之前刺破形成的 wick extreme，过滤一部分只插针、不收盘确认的突破。

## 交易规则

* 自动化 Pine 只在 5分钟周期发交易 JSON。
  突破 swing high 是多头结构突破，突破 swing low 是空头结构突破。第一次反向或初始方向突破记为 MSS，顺着已有 bias 的继续突破记为 BOS。

* 入场价是结构腿的 61.8% 回撤位。
  多头时，从 waveStart 低点到 waveEnd 高点计算回撤买入；空头时，从 waveStart 高点到 waveEnd 低点计算回撤卖出。止损放在 waveStart，止盈放在 waveEnd。

## 风控和限制

* strategy.enabled 为 false 时不会自动交易。默认禁开仓时间是北京时间 04:00-07:00。北京时间 04:00 会自动排队全平/撤单任务，07:00 之后重置当日风控状态。

* 当前代码里 dailyLossLimit、dailyProfitLimit、maxConsecutiveLosses 有检查逻辑，但依赖扩展回报日 PnL 和连续亏损数据；扩展目前主要回报任务执行结果，不一定完整计算这些数值。maxSameDirectionTrades、retryAttempts、flattenScope 目前在配置里存在，但没有完整落地成严格执行逻辑。

## 注意事项

* config.local.json、data/state.json 都是本机运行文件，不要公开。
* webhookSecret 必须和自动化 Pine 输入参数里的 secret 完全一致。
* 两个 Pine 文件不要混用：手机提醒用 mgc_mss_OnlyAlert.pine，自动交易 webhook 用 mgc_mss_retracement_alerts.pine。

## 启动

1. 第一次使用需要复制配置：

```bash
cd /Users/jiangsai/Desktop/Auto_Trade_V1
cp config.example.json config.local.json
```

2. 编辑 `config.local.json`：

   - `server.webhookSecret`：改成你自己的随机字符串

   - `strategy.contract`：默认 `MGCM6`

3. 新建**命令行窗口1**：启动脚本：

   ```bash
   npm start
   ```

2. 打开控制台：http://127.0.0.1:8787

## TradingView Alert

1. 新建 TradingView 指标：把 `pine/mgc_mss_retracement_alerts.pine` 复制到新指标里

2. 创建 指标的信号中转桥

   > 因为本地服务不能直接被 TradingView 云端访问

   1. 再新建一个**命令行窗口2**：安装 cloudflared

      ```bash
      curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz | tar xz
      sudo mv cloudflared /usr/local/bin/
      ```

   2. 创建 临时公网 tunnel 地址

      ```bash
      cloudflared tunnel --url http://127.0.0.1:8787
      ```

      等待输出，例如

      ```bash
      INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
      INF |  https://designs-explanation-sanyo-slight.trycloudflare.com                                |
      ```

      即临时公网 tunnel 地址： https://designs-explanation-sanyo-slight.trycloudflare.com  

   3. 测试 公网 tunnel 地址 是否通畅

      * **2个命令行窗口**都不要关，测试公网地址能不能访问本地 bot，在浏览器打开上一步得到的**临时公网 tunnel 地址**，如果能看到 MSS Local Bot 控制台，就说明 tunnel 通了

      * **命令行窗口一关，这个公网地址基本就失效了。下次再运行，要重新生成一个，重新配置下一步的Webhook URL**

        > 脚本跑通后可考虑 **创建固定 tunnel**

3. 创建 TradingView 指标 Alert （TradingView 顶部「回放」左侧的「警报」）：

   ![image-20260602164025033](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20260602164025033.png)

   - 条件：MGC 5m 自动化指标

   - 触发方式：Any alert() function call

   - 周期：5分

   - 通知：

     ✅ 在app中通知

     ✅ 显示弹窗通知

     ✅ Webhook URL：https://designs-explanation-sanyo-slight.trycloudflare.com/webhook/tradingview（一定要带后面的：/webhook/tradingview）

4. TradingView 指标设置

   1. TradingView 的指标列表找到「MGC 5m 自动化指标」

   2. 进入设置，**输入tab** 的 Webhook secret： GodloveSai

      > 因为config.local.json 里现在是：GodloveSai，这个值会被 指标 放进 alert 发出的 JSON 里，本地 bot 收到后会检查它是不是和 config.local.json 一致。）

## Chrome 扩展

1. 打开 Chrome: `chrome://extensions`
2. 打开右上角「开发者模式」。
3. 点击「加载已解压的扩展程序」。
4. 选择本项目里的 `extension/` 文件夹。
5. 打开 TradingView，并在 TradingView broker 面板里登录 Tradovate demo。
6. 保持本地 bot 启动，打开控制台页面确认「扩展在线」和「Tradovate 已登录」，说明扩展连接正常。

### 第一次使用前的 bracket 模板学习

* 第一次要在 demo 里手动用 TradingView 的 Tradovate 面板下一笔 bracket limit 单，带止盈和止损

  > * 不用等MSS后挂单，可以任意下一笔 demo bracket limit 单
  > * 一定用 demo 账户。
  > * 一定是 limit 挂单。
  > * 一定带止盈和止损。
  > * 价格放远一点，不要马上成交。
  > * 下完后可以马上撤掉。

* TradingView/Tradovate 的 bracket 下单字段不是公开稳定接口。为了避免自动化误下裸单，扩展默认不会猜字段。扩展会捕获这次手动 bracket 单的请求模板，后续自动信号会复用模板并替换：

  > - 合约
  >
  > - 方向
  >
  > - 手数
  >
  > - entry
  >
  > - stop loss
  >
  > - take profit

* 如果模板还没捕获，自动任务会被拒绝，并在本地控制台记录原因。

## 脚本运行中的注意事项

* **Chrome 不能关掉，TradingView 页面也不能关掉**

  因为扩展在 TradingView 页面里运行，并捕获 Tradovate 登录状态。页面关掉、崩掉、长时间休眠，都会导致自动化断掉。

  而TradingView 页面运行在 Chrome 里。Chrome 关了，扩展就没地方运行，自动化就不会执行。

* **Tradovate 要保持登录**

  如果 TradingView 里的 Tradovate 登录过期，扩展会检测不到有效授权，任务会失败或不执行。

* **电脑不能睡眠**

  屏幕可以关，但 Mac 进入睡眠后 Node 服务、Chrome 扩展、tunnel 都可能停。

* **不要在同一个 TradingView/Tradovate 页面里乱操作交易面板**

  可以用 Chrome 看别的网站，但不要在运行自动化的那个 TradingView 页面里手动乱下单、切账户、切 broker、改 Tradovate 面板状态。因为扩展依赖这个页面里的 Tradovate 会话和账户状态。

* **不要关本地服务和 tunnel**

  * npm start 的命令行窗口要开着。
  * cloudflared tunnel --url http://127.0.0.1:8787 的窗口也要开着。
  * 关掉其中任何一个，TradingView alert 到本地 bot 的链路都会断。

* **建议**：单独开一个 Chrome 窗口，只放 TradingView + Tradovate 自动化页面；平时干别的用其他Chrome 窗口。这样自动化最稳，也不影响正常使用电脑。

## 策略 V1

- 只做 5m。
- MSS 和 BOS 都交易。
- 只做一个 Tradovate 账户。
- 合约默认 `MGCM6`，手动配置。
- 入场：波段 61.8% limit。
- 止损：波段起点。
- 止盈：波段终点。
- 入场使用 TradingView 页面内 Tradovate broker 请求，复用手动 bracket 模板。
- 北京时间 04:00-07:00 不开仓、不持仓。
- 北京时间 04:00 自动全平并撤挂单。
- 北京时间 07:00 重置风控。
