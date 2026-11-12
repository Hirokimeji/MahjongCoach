# 雀魂新手教练

面向日麻初学者的 Windows 桌面辅助工具。根据实时牌局提供切牌、役种方向和防守参考，支持 Steam 雀魂的三麻与四麻。

## 功能

- 先胡牌、做大牌、先防守三种模式，可随时切换。
- 展示推荐切牌、简短解释、有效进张及未见张数。
- 持续显示手牌放铳风险，高风险推荐可配置提醒门槛。
- 按对手展示听牌估计和危险牌，支持手牌范围与全部牌种。
- 提供立直、吃碰、杠、拔北及和牌提示，展示牌面估分和结算结果。
- 支持置顶、小窗、窗口缩放，以及深色、浅色、粉色主题。
- 支持本地图片背景和可选动态背景。
- 集成 MAX 启动、停止恢复、正式版更新检查，以及仅打牌辅助模式。

## 运行环境

当前源码适配 Windows，推荐 Python 3.12。界面使用 PySide6，分析引擎基于 mahjong-helper。

这是依赖本机 MAX 和 Clash Verge 配置的源码版本。首次运行前需要准备依赖和目录，启动管理中的代理组及游戏路径需要按自己的安装环境调整。

```text
项目目录/
├─ MahjongCoach/
│  ├─ coach.pyw
│  ├─ engine/mahjong-coach-engine.exe
│  └─ engine-source/
└─ MajsoulMax-Steam/
   ├─ launcher.py
   └─ app/MajsoulMax/
```

安装 Python 依赖并构建引擎。在项目根目录执行以下命令。

```powershell
py -3.12 -m pip install -r requirements.txt
cd MahjongCoach/engine-source
go build -o ../engine/mahjong-coach-engine.exe .
cd ../..
py -3.12 MahjongCoach/coach.pyw
```

MAX 发行文件需要另外准备，放入上图对应目录。启动管理参数在 `MajsoulMax-Steam/launcher.py` 中，包含 Clash 配置位置、代理组名称和游戏路径。

动态背景为可选功能，相关模型运行库和第三方资源需要自行准备。基础界面和内置插画可独立显示。

## 使用

1. 打开教练，点击「示例手牌」熟悉模式切换、风险和进张显示。
2. 配置好本机依赖后，选择外观模式并启动雀魂。
3. 登录并从新的一局开始，等待识别座位和手牌。
4. 根据建议在游戏中手动操作。
5. 结束使用时点击「停止并恢复」，或关闭教练窗口。

「全解锁关闭 · 仅辅助」会在当前会话关闭外观插件并跳过皮肤恢复。模式选择会保存，停止时恢复原有插件配置。

## 如何理解概率

放铳风险根据公开弃牌、副露、巡目和立直状态估算。对手听牌概率与听牌条件下的牌种危险度相乘，再合并各家的估计。开局信息不足时显示「待估」。

危险牌列表用于辅助防守，具体等待牌仍需推测。概率尚未经过实战校准，少见牌型、对手打法和信息缺失都可能影响结果。

有效进张的未见张数包含可能在其他玩家手中的牌。和牌估分未必涵盖本场、供托、里宝牌及所有特殊役，实际点数以游戏结算为准。

实时辅助可能违反游戏平台规则。请自行了解平台要求及账号风险。

## 项目结构

| 文件 | 用途 |
| --- | --- |
| `coach.pyw`、`studio.py` | 桌面窗口、主题与牌面展示 |
| `backend.py` | 本地数据接收和启动恢复 |
| `presenter.py`、`strategy.py` | 出牌策略及中文提示 |
| `engine-source/` | 修改后的 Go 分析引擎 |
| `backgrounds.py` | 背景收藏 |
| `max_updates.py` | 正式版检查和更新 |

日志、账号会话、个人皮肤配置、代理配置及下载缓存均保存在本机。

## 来源

- [mahjong-helper](https://github.com/EndlessCheng/mahjong-helper)，MIT，分析引擎。原许可证保存在 `MahjongCoach/LICENSE-engine.txt`。
- [riichi-mahjong-tiles](https://github.com/FluffyStuff/riichi-mahjong-tiles)，CC0，麻将牌面。
- [MajsoulMax](https://github.com/Avenshy/MajsoulMax)，本机启动集成所依赖的上游项目。

内置插画和头像由 AI 生成。第三方模型、视频、游戏立绘和相关运行库的使用与分发应遵守各自授权。
