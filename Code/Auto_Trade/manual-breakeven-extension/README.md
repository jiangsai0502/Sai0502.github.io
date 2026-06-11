# Tradovate Manual Breakeven

这是一个独立的小 Chrome 插件，只做一件事：手动开仓后，在 TradingView 的 Tradovate 连接里读取当前持仓，并在价格到达你输入的触发价后把止损推到开仓均价。

## 使用方式

1. 打开 Chrome 扩展管理：`chrome://extensions`
2. 打开右上角“开发者模式”
3. 点击“加载已解压的扩展程序”
4. 选择这个目录：

   ```text
   /Users/jiangsai/Documents/GitHub/Sai0502.github.io/Code/Auto_Trade/manual-breakeven-extension
   ```

5. 打开 TradingView，并确认 Tradovate broker 已登录
6. 手动开仓，并放好初始止损和止盈
7. 点击 Chrome 右上角插件图标
8. 右侧面板会显示当前持仓、开仓价、当前价、止损价、止盈价
9. 在对应持仓里输入推保触发价，点击“启动推保”

## 当前逻辑

- 多单：当前价 >= 推保触发价时，把止损推到开仓均价。
- 空单：当前价 <= 推保触发价时，把止损推到开仓均价。
- 如果没有检测到止损单，插件不会乱下单，会显示错误。
- 如果止损已经在保本或更好的位置，任务会直接完成。

## 注意

TradingView / Tradovate 页面内部接口不是公开稳定 API。第一版会先尝试直接修改止损单；如果接口拒绝，会尝试新建保本止损单再撤旧止损单。如果真实测试中失败，面板里的任务错误会保留接口返回信息，后续可以按返回字段补一个更稳定的“学习手动改止损模板”。
