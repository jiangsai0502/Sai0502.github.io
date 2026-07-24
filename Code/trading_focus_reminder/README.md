# Trading Focus Reminder

每天指定时间弹出全屏置顶提醒，必须手动输入当天抽到的句子才能关闭。

提醒内容会从 `quotes.txt` 里按日期随机抽取一句。同一天重复触发会使用同一句，第二天自动换一句。

默认时间：北京时间 `21:25`。

## 修改时间或文案

编辑：

```text
/Users/jiangsai/Documents/GitHub/Sai0502.github.io/Code/trading_focus_reminder/config.json
```

配置只在后台程序启动时读取。修改后请重新运行安装脚本，或先卸载再安装。

示例：

```json
{
  "times": ["21:25"],
  "quotes_file": "quotes.txt",
  "message": "并非每天都有绝佳的机会，没有就空仓一天",
  "title": "交易前提醒",
  "timezone": "Asia/Shanghai",
  "allow_weekends": true,
  "keep_front_seconds": 3,
  "snooze_seconds_after_success": 60
}
```

`message` 是备用文案：当 `quotes.txt` 不存在或为空时才会使用。

## 查看今天抽到哪一句

```bash
/opt/anaconda3/bin/python3 /Users/jiangsai/Documents/GitHub/Sai0502.github.io/Code/trading_focus_reminder/trading_focus_reminder.py --print-message
```

## 立即测试

```bash
/opt/anaconda3/bin/python3 /Users/jiangsai/Documents/GitHub/Sai0502.github.io/Code/trading_focus_reminder/trading_focus_reminder.py --once
```

## 安装为登录后自动运行

```bash
bash /Users/jiangsai/Documents/GitHub/Sai0502.github.io/Code/trading_focus_reminder/install_launch_agent.sh
```

## 卸载

```bash
bash /Users/jiangsai/Documents/GitHub/Sai0502.github.io/Code/trading_focus_reminder/uninstall_launch_agent.sh
```

## 查看下一次提醒时间

```bash
/opt/anaconda3/bin/python3 /Users/jiangsai/Documents/GitHub/Sai0502.github.io/Code/trading_focus_reminder/trading_focus_reminder.py --print-next
```

## 说明

这个工具会尽量置顶和抢焦点。macOS 仍然可能拦截极少数系统级场景，例如锁屏、系统密码弹窗、独占全屏应用等。
