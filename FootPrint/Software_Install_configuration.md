#### 常备软件

> * 文字处理：office、sublime、Typora、Easydict、Paste、PDF expert、XMind
> * 效率工具：Keyboard Maestro、go2shell（官网下载）、snipaste、rename、PicGo、Easydict、flow、downie
> * 系统工具：App Cleaner、Mos、itsycal、Alfred 5、iTerm、WgetCloud、GitHub Desktop、Geph、istat menus、VS Code、The Unarchiver、

##### 触摸板

> 1. 禁用双指右边缘左滑调佣通知中心：触摸板-更多手势-通知中心（关闭）
> 2. 启用三指拖移：辅助功能 - 指针控制 - 触控板选项 - 拖移样式 - 三指拖移
> 3. 启用连接鼠标时禁用触摸板：辅助功能 - 指针控制 - 使用鼠标或无线触控板时忽略内置触控板

##### 顶部状态栏设置

> ![image-20260725003331865](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202607250033920.png)

##### 鼠标滚轮缩放

> 安住control，滚轮缩放
>
> ![image-20241111130129467](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20241111130129467.png)

##### 启动台图标数量7 x 11

> ```bash
> defaults write com.apple.dock springboard-rows -int 7;
> defaults write com.apple.dock springboard-columns -int 11;
> defaults write com.apple.dock ResetLaunchPad -bool true;
> killall Dock
> ```

##### Finder顶端显示完整路径

> ```bash
> defaults write com.apple.finder _FXShowPosixPathInTitle -bool YES
> ```

VPN开启后Chrome可翻墙，终端不行

> getcloud代理地址：http://127.0.0.1:8234
>
> ![image-20241107172851202](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20241107172851202.png)
>
> ![image-20241222080951372](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20241222080951372.png)
>
> 1. 测试IP：
>
>    `curl cip.cc`
>
> 2. 设临时代理，仅作用于当前终端
>
>    `export http_proxy=http://127.0.0.1:8234;export https_proxy=http://127.0.0.1:8234`
>
> 3. 最终解决方案
>
>    ```bash
>    # 创建 .zshrc 文件
>    echo >> ~/.zshrc
>                                                       
>    open ~/.zshrc
>                                                       
>    # 在文件最后添加下面两句
>    export http_proxy="http://127.0.0.1:8234" export https_proxy="http://127.0.0.1:8234"
>    ```

**禁止Chrome更新**

> 安装后别打开APP，立刻去'/Library/Application Support/Google/GoogleUpdater'，把GoogleUpdater文件夹删除，随意新建个文件改名为GoogleUpdater，挪到改目录，即可

##### 安装brew

> ```bash
> # 境外源
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> 
> # 获取 brew 安装位置
> which brew
> # 输出 /usr/local/bin/brew
> 
> # 创建 .zprofile文件
> echo >> ~/.zprofile
> 
> # 添加到 PATH 环境变量，否则终端无法识别 brew 命令
> # /usr/local/bin/brew 要改成 which brew 输出的位置
> echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zprofile
> 
> source ~/.zprofile
> ```

##### 安装iterm2

> 1. 官网下载安装App
>
> 2. 官网下载安装go2shell
>
>    ![image-20260725012032392](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202607250120444.png)
>
> 3. 设为默认：iTerm2 -> Make ITerm2 Default Term
>
>    ![](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/20220413110312.png)
>
> 4. 快捷键
>
>    1. 光标按照单词快速移动：iTerm2 -> Settings -> Keys -> Key Bindings
>
>       修改 ⌘← 和 ⌘→ 的映射，双击进入后，选择Action为 “Send Escape Sequence”，Esc+为 ⌘← 对应 b ， ⌘→ 对应 f
>
>       ![](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/20220412205506.png)
>
>    2. 按照单词快速删除（结合Keyboard Maestro）
>
>       * 修改 ⌘+Delete 的映射，⌘+Delete 代表 control + w
>
> 5. 安装Oh my zsh [参考](https://segmentfault.com/a/1190000041138667?utm_source=sf-similar-article)
>
>    ```bash
>    # 1. 设置 oh-my-zsh 从 Gitee 镜像安装
>    export REMOTE=https://gitee.com/imirror/ohmyzsh.git
>    
>    # 2. 用 curl 下载并执行安装脚本（替代 wget）
>    sh -c "$(curl -fsSL https://cdn.jsdelivr.net/gh/ohmyzsh/ohmyzsh/tools/install.sh)"
>    
>    # 3. 打开 .zshrc 手动编辑
>    open ~/.zshrc
>    
>    # 在.zshrc文件中搜索 source $ZSH/oh-my-zsh.sh，在本句之前加一句
>    ZSH_DISABLE_COMPFIX="true"
>    
>    # 禁用oh-my-zsh自动更新：找到 DISABLE_AUTO_UPDATE 一行，将行首的注释'#'去掉
>    DISABLE_AUTO_UPDATE="true"
>    
>    source ~/.zshrc
>    ```
>
> 6. 安装PowerFonts字体
>
>    ```bash
>    1. 下载：https://github.com/powerline/fonts
>    2. 解压
>    3. 进入文件夹：cd fonts-master
>    4. 安装：./install.sh
>    ```
>
> 7. 设置字体
>
>    * iTerm2 -> Settings -> Profiles -> Text，在Font区域选中Change Font，然后找到Meslo LG字体，有L、M、S可选
>
>    ![](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/20220413112345.png)
>
> 8. 配色方案
>
>    iTerm2 -> Settings -> Profiles -> Colors -> Color Presets
>
>    ![image-20241222090429902](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20241222090429902.png)
>
> 9. 设置主题
>
>    ```bash
>    open ~/.zshrc
>    # 搜索'ZSH_THEME'，修改为ZSH_THEME="agnoster"
>    source ~/.zshrc
>    ```
>
> 10. 设置语法高亮
>
>     ```bash
>     brew install zsh-syntax-highlighting
>     输出To activate the syntax highlighting, add the following at the end of your .zshrc:
>       source /usr/local/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
>
>     open ~/.zshrc
>
>     最后插入一行：source /usr/local/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
>
>     source ~/.zshrc
>     ```
>
> 11. 自动提示与命令补全
>
>     ```bash
>     下载 https://github.com/zsh-users/zsh-autosuggestions，解压并改名为 zsh-autosuggestions
>     open ~/.oh-my-zsh/plugins
>     # 将 zsh-autosuggestions 拖入目录 ~/.oh-my-zsh/plugins
>     open ~/.zshrc
>
>     搜索'plugins'，修改为 plugins=(zsh-autosuggestions)
>     source ~/.zshrc
>     ```
>
> 12. 隐藏名字和主机名
>
>     ```bash
>     open ~/.oh-my-zsh/themes
>                             
>     打开agnoster.zsh-theme文件，找到prompt_context()函数，替换为
>     prompt_context() {
>       if [[ "$USERNAME" != "$DEFAULT_USER" || -n "$SSH_CLIENT" ]]; then
>         prompt_segment black default "Sai"
>       fi
>     }
>                             
>     source ~/.oh-my-zsh/themes/agnoster.zsh-theme
>     ```

##### mpv

> ```bash
> brew install mpv --cask
> 
> # 打开 mpv 一次
> # 创建 input.conf 文件
> echo >> ~/.config/mpv/input.conf
> 
> # 打开 input.conf 文件
> nano ~/.config/mpv/input.conf
> 
> # 复制到该文件
> # ----------------------------------------
> # 1. 键盘方向键（按键直觉：左退右进，上加下减）
> # ----------------------------------------
> LEFT seek -2 exact
> RIGHT seek 2 exact
> UP add volume 2
> DOWN add volume -2
> 
> # ----------------------------------------
> # 2. 触控板 / 鼠标手势（对齐 Mac 自然滚动）
> # ----------------------------------------
> # 双指左右滑动
> AXIS_LEFT seek 2 exact
> AXIS_RIGHT seek -2 exact
> 
> # 双指上下滑动调节音量（调换正负号以对齐自然滚动）
> WHEEL_UP add volume -2
> WHEEL_DOWN add volume 2
> 
> Ctrl + O 保存，Enter 键确认保存，Ctrl + X 退出 nano 编辑器
> ```
>
> 设置mpv多开
>
> 1. 打开Script Editor
>
>    ```bash
>    on run
>        do shell script "open -n /Applications/mpv.app"
>        tell application "mpv" to activate
>    end run
>
>    on open theFiles
>        repeat with theFile in theFiles
>            -- 对路径进行适当的转义
>            set filePath to POSIX path of theFile
>            set escapedPath to quoted form of filePath
>            do shell script "open -na /Applications/mpv.app --args " & escapedPath
>        end repeat
>        tell application "mpv" to activate
>    end open
>
>    ```
>
> 2. 保存
>
>    1. 名称：mpv多开器
>    2. 文件格式：应用程序
>
> 3. 将mpv multiple拖入应用程序，修改视频文件的默认打开方式

##### yt-dlp

> **先安装FFmpeg**
>
> * [下载](https://evermeet.cx/ffmpeg/)：右侧版本 - Download as ZIP，解压得到可执行文件 ffmpeg
>
>   ```bash
>   sudo mkdir -p /usr/local/bin
>   sudo mv ~/Downloads/ffmpeg /usr/local/bin/
>   sudo chmod +x /usr/local/bin/ffmpeg
>   sudo xattr -dr com.apple.quarantine /usr/local/bin/ffmpeg
>   ffmpeg -version
>   ```
>
> **再安装 yt-dlp**
>
> ```bash
> python3 -m pip install yt-dlp
> 
> # 把路径加到 PATH
> echo 'export PATH="$HOME/Library/Python/3.9/bin:$PATH"' >> ~/.zshrc
> source ~/.zshrc
> ```
>
> > 直接下载往往被限制分辨率，增加参数可模拟浏览器
>
> * 查看视频所有类型
>
>   `yt-dlp -F --cookies-from-browser chrome URL`
>
> * 直接下载最高品质视频
>
>   `yt-dlp --cookies-from-browser chrome URL`
>
> * 下载指定ID的视频
>
>   `yt-dlp -f ID --cookies-from-browser chrome URL`
>
> * 下载列表
>
>   `yt-dlp --yes-playlist --cookies-from-browser chrome URL`
>
> * 音频、视频分别下载
>
>   > 视频不包含音频
>   >
>   > `yt-dlp -f 242 --cookies-from-browser chrome URL`
>   >
>   > 音频不包含视频
>   >
>   > `yt-dlp -f 230 --cookies-from-browser chrome URL`
>   >
>   > 视频 + 音频
>   >
>   > * 默认mkv：`yt-dlp -f 242+ 230 --cookies-from-browser chrome URL`
>   > * 转mp4：`yt-dlp -f 230 --cookies-from-browser chrome --remux-video mp4 URL`
>   >
>   > ![img](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202308271236418.png)

##### 禁用自动更新

> ```bash
> backup="$HOME/Desktop/iStat-All-Cache-Backup-$(date '+%Y%m%d-%H%M%S')"
> mkdir -p "$backup"
> 
> # 暂时停止菜单栏和后台助手，避免清理过程中自动重建缓存
> launchctl bootout "gui/$UID" \
> "$HOME/Library/LaunchAgents/com.bjango.istatmenus.status.plist" 2>/dev/null
> 
> launchctl bootout "gui/$UID" \
> "$HOME/Library/LaunchAgents/com.bjango.istatmenus.agent.plist" 2>/dev/null
> 
> # 结束设置程序、更新器及其网页子进程
> killall "iStat Menus" 2>/dev/null
> killall "iStat Menus Updater" 2>/dev/null
> pkill -f 'com\.bjango\.istatmenus\.updater|updates\.istatmenus\.app' 2>/dev/null
> 
> sleep 1
> 
> # 隔离主程序、菜单栏、后台代理和更新器的全部网络缓存
> for area in Caches WebKit HTTPStorages; do
>     for bundle in \
>         com.bjango.istatmenus \
>         com.bjango.istatmenus.status \
>         com.bjango.istatmenus.agent \
>         com.bjango.istatmenus.updater
>     do
>         source_path="$HOME/Library/$area/$bundle"
> 
>         if [[ -e "$source_path" ]]; then
>             mv "$source_path" "$backup/${area}-${bundle}"
>         fi
>     done
> done
> 
> # 重新加载后台助手和菜单栏
> launchctl bootstrap "gui/$UID" \
> "$HOME/Library/LaunchAgents/com.bjango.istatmenus.agent.plist"
> 
> launchctl bootstrap "gui/$UID" \
> "$HOME/Library/LaunchAgents/com.bjango.istatmenus.status.plist"
> 
> launchctl kickstart -k "gui/$UID/com.bjango.istatmenus.agent"
> launchctl kickstart -k "gui/$UID/com.bjango.istatmenus.status"
> 
> echo "全部iStat网络缓存已隔离到：$backup"
> ```

##### Itsycal安装后隐藏系统日期

> ```bash
> defaults write com.apple.menuextra.clock DateFormat -string "HH:mm"
> killall SystemUIServer
> killall ControlCenter
> ```

##### Alfred配置

> 1. 将Spotlight的快捷键分给Alfred
>
>    ![](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/20220413142827.png)
>
> 2. 搜索排除某个文件夹
>
>    1. 添加要排除的文件夹
>
>    2. 调出alfred，输入reload回车，清空alfred缓存
>
>       ![](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/20220413143239.png)
>
>    3. 自定义文件操作
>
>       ![](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/20220413143409.png)
>
>    **Quick Search**：最常用，`Space + 关键字`快速启用打开文件，功能类似于使用 `Open + 关键字`
>
>    **Inside Files**：最常用，`in + 关键字`查找包含查询字的文件

##### GitHub + PicGo + Typora搭建图床

> 1. 创建GitHub图床
>
>    > 创建的token只展示一次，要好好保存
>
>    ![image-20241223100207621](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20241223100207621.png)
>
> 2. 配置PicGo
>
>    > * 设定仓库名的时候，是按照“账户名/仓库名”的格式填写
>    >
>    >   * 如 jiangsai0502/PicBedRepo
>    >
>    > * 分支名统一填写“master”
>    >
>    > * 将之前的Token黏贴在这里：`74d803fcee14a9c36a8f1f387e5085446c2489f1`
>    >
>    > * 存储路径可以写成img/，这样会在repository下创建一个“img”文件夹
>    >
>    > * 自定义域名的作用是，在上传图片后成功后，PicGo会将“自定义域名+上传的图片名”生成的访问链接，放到剪切板上https://raw.githubusercontent.com/账户名/仓库名/分支名，自定义域名需要按照这样去填写
>    >
>    >   * 如https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master
>    >
>    > * PicGo报错
>    >
>    >   ![image-20241107173202457](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20241107173202457.png)
>
> 3. Typora自动上传
>
>    > Typora到语言必须调成中文，上传服务才能看到PicGo.app
>
>    ![image-20240504172744911](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202405041727992.png)

1. Typora设置

   > 1. 展示设置：增加行宽
   >
   >    > ![](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202312161642913.png)
   >
   > 2. 打印设置
   >
   >    1. 页边距
   >
   >       > ![](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202310261112999.png)
   >
   >    2. [行距](https://www.twblogs.net/a/5db288f8bd9eee310d9fd66c/?lang=zh-cn)
   >
   >       > 1. 微调`body`中的`line-height`参数
   >       > 2. 关闭文件重新打开，修改即可生效
   >       >
   >       > ![](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202310261109296.png)

##### Mac Mouse Fix

>![image-20260724222539542](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202607242225621.png)
>
>1. 鼠标缩放图片：Option + 鼠标滚轮（若缩放过快，则在mos中将该app设为例外）
>2. 鼠标左右滚动图片：Shift + 鼠标滚轮

##### Longshot

> ![image-20260726183433793](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202607261834855.png)

##### sublime配置

> 1. 安装
>
>    > ⌘+⇧+P，输入install package，回车自动安装
>
>    > [无法加载 install package](https://www.tangxdou.com/2024/05/24/%E8%A7%A3%E5%86%B3%E6%96%B0%E7%89%88%E6%9C%ACMacOS%E4%B8%8BSublimeText4packagecontrol%E6%97%A0%E6%B3%95%E5%8A%A0%E8%BD%BD%E9%97%AE%E9%A2%98/)，因为新版本的 macos 不支持旧版package control 
>    >
>    > 1. [下载 beta 版本的 package control 插件](https://github.com/wbond/package_control/releases/download/4.0.0-beta8/Package.Control.sublime-package)，下载后将`Package.Control.sublime-package`改名为`Package Control.sublime-package`（去掉.加个空格）
>    > 2. Settings - Browser packages，找到同级目录Installed Packages，将`Package Control.sublime-package`拖入该目录
>    > 3. 重启 sublime
>
> 2. 解决乱码问题
>
>    > ⌘+⇧+P，输入install package，弹出框，输入ConvertToUTF8,回车自动安装
>
> 3. 中文汉化包
>
>    > ⌘+⇧+P，输入install package，弹出框，输入ChineseLocalizations，回车自动安装
>
> 4. Ayu主题
>
>    > ⌘+⇧+P，输入install package，弹出框，输入ayu，回车自动安装
>    >
>    > 选择主题：ayu: Activate theme，选择，回车

##### Karabiner

> 问题：连外接键盘时，键位不对应
>
> 1. 修改单个键位
>
>    > ![image-20240827025736308](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20240827025736308.png)
>    >
>    > 
>
> 2. 修改组合快捷键[参考](https://blog.csdn.net/qq_26012495/article/details/88539120)
>
> 3. 新建MyShortcut.json，放入`~/.config/karabiner/assets/complex_modifications`
>
>    > ```css
>    > {
>    > "title": "JiangSai",
>    > "rules": [
>    >  {
>    >    "description": "锁屏",
>    >    "manipulators": [
>    >      {
>    >        "type": "basic",
>    >        "from": {
>    >          "key_code": "l",
>    >          "modifiers": {
>    >            "mandatory": ["command"]
>    >          }
>    >        },
>    >        "to": [
>    >          {
>    >            "key_code": "q",
>    >            "modifiers": [
>    >              "command",
>    >              "control"
>    >              ]
>    >          }
>    >        ]
>    >      }
>    >    ]
>    >  },
>    >  {
>    >    "description": "录音-新建",
>    >    "manipulators": [
>    >      {
>    >        "type": "basic",
>    >        "from": {
>    >          "key_code": "1",
>    >          "modifiers": {
>    >            "mandatory": ["option"]
>    >          }
>    >        },
>    >        "to": [
>    >          {
>    >            "key_code": "r",
>    >            "modifiers": [
>    >              "shift",
>    >              "command"
>    >              ]
>    >          }
>    >        ]
>    >      }
>    >    ]
>    >  }
>    > ]
>    > }
>    > ```
>
> 4. preference - complex modification - add rule - 第一行Anki_cloze内的命令"Change command+option+shift+c key to command+3"点击"Enable"
>
> 5. grave_accent_and_tilde即键盘esc下方的`

##### 罗技鼠标Logitech G HUB

> ![image-20260724232614638](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/img/202607242326698.png)
>
> 1. 关闭板载内存
>
> 2. DPI：第1个启用：灵敏度 - 2400；剩余都关闭
>
> 3. 侧键快捷键
>    1. 分配 -宏 - 新建宏 - 不重复 - 立即开始 - 记录按键 - 停止录制
>       1. 全屏左滑宏：control ⌃ + ArrowLift ←
>
>       2. 全屏右滑宏：control ⌃ + ArrowRight →
>       3. 窗口管理 宏：control ⌃ + ArrowUp ↑
>
>    2. 将新建的「全屏左滑宏」拖到侧上键；将新建的「全屏右滑宏」拖到侧下键
>
> 4. 保存设置
>    1. 开启板载内存模式：「关闭」->「开启」
>
>    2. 保存到「桌面 默认」 - 等待保存完成
>
>    3. 关闭板载内存模式：「开启」->「关闭」
>
> 5. 开启板载内存
>

##### OBS

> [参考](https://www.bilibili.com/video/BV1PYASeLEb6)
>
> * 基础设置
>
>   ![image-20250315222703689](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20250315222703689.png)
>
>   ![image-20250319003142590](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20250319003142590.png)
>
> * 去除环境音
>
>   ![image-20250315230635808](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20250315230635808.png)
>
> * 画质提升
>
>   ![image-20250319003024248](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20250319003024248.png)
>   
> * 外接屏幕调整尺寸
>
>   ![image-20260706225358439](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20260706225358439.png)

##### PDF Expert 禁止更新

> PDF /Applications/PDF Expert.app/Contents/Info.plist
>
> ```
> <key>SUFeedURL</key>
> <string>https://downloads.pdfexpert.com/release/appcast.xml</string>
> ```
>
> > 删除`https://downloads.pdfexpert.com/release/appcast.xml`
>
> ```
> <key>SUEnableAutomaticChecks</key>
> <string>YES</string>
> ```
>
> > `YES`改成`NO`
>
> ```
> <key>SUScheduledCheckInterval</key>
> <string>86400</string>
> ```
>
> > `86400`改成`3153600000`（100年）

##### VPN自检流程 [教程](https://www.youtube.com/watch?v=_CMNgW3r_9g)

1. 获取当前vpn的IP

   ![image-20260404225014554](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20260404225014554.png)

2. 检测IP

   ![image-20260404225432899](https://raw.githubusercontent.com/jiangsai0502/PicBedRepo/master/image-20260404225432899.png)

##### VPS 搭建 VPN [教程](https://www.youtube.com/watch?v=MuWTmEiNe1g)

##### MacOS 连接 iPhone热点抽风断开的自动重连脚本

> ```
> 启动程序
> ↓
> 单例检查（排他运行）
> ├─ 已有进程运行 ──> 提示并退出
> └─ 无运行进程 ───> 初始化日志与单例锁，进入主循环
>         ↓
> 【循环监控】每秒并发探测多网站，检查整体联网状态
> ├─ 网络正常 ───> 重置故障计数，保持静默监控
> └─ 连续 2 次断网 ──> 确认断网，触发故障处理机制
>         ↓
> 【故障处理】检查当前默认出口
> ├─ 为 iPhone USB ──> 尝试禁用一次该 USB 服务（为 Wi-Fi 让路）
> └─ 非 USB / 处理完毕 ──> 发起 Wi-Fi 恢复（最多尝试 3 次）
>         ↓
> 【Wi-Fi 重连与验证】（每次连接后验证 IP/路由/联网）
> ├─ 任意阶段恢复联网 ──> 重置状态，返回【循环监控】
> └─ 尝试 3 次均失败 ──> 触发人工干预流程
>         ↓
> 【人工干预】
> └─ 弹出系统通知（仅一次），停止自动重连
> └─ 持续后台检测 ──> 一旦联网成功 ──> 清除状态，恢复【循环监控】
> ```
>
> **功能**
>
> - 通过多目标并发探测，每秒监控系统联网状态
> - 确认**连续两次断网**后，会自动停用 iPhone USB 共享网络，并尝试**连接指定 Wi-Fi**（最多 3 次）。
> - 自动连接 3 次都失败后，弹窗提醒人工介入
> - 手动连接成功后再次重启监控
> - 所有操作记录到桌面日志文件`macos-network-watchdog.log`
>
> **使用方法**：macos-network-watchdog.command`右键-制作替身（快捷方式）-挪到桌面
>
> **注意**：Wi-Fi 名称必须写对，大小写都不能错
>
> 
