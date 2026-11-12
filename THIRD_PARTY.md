# 第三方组件

发行包保留各组件的许可证文件与包元数据。组件版本可在 runtime/Lib/site-packages 的 dist-info 目录查看。

- Python，PSF License，许可证位于 runtime/LICENSE.txt。
- PySide6、Qt、Shiboken，LGPL/GPL/商业许可组合，许可证和版权信息随原包保留。官方源码和许可说明见 https://doc.qt.io/qtforpython-6/licenses.html 。发行包以独立动态库使用，用户可替换兼容库。
- PyYAML、Pillow、NumPy，许可证位于各自 dist-info 目录。
- live2d-py、PyOpenGL，许可证及元数据位于 MahjongCoach/model-runtime。live2d-py 使用 Cubism SDK，Cubism 许可见 https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html ，版权归 Live2D Inc. 所有。
- mahjong-helper 引擎，MIT，许可证位于 MahjongCoach/LICENSE-engine.txt。对应修改源码随本项目 GitHub 仓库提供。
- Mahjong tile artwork，CC0，见 MahjongCoach/LICENSE-tiles.md。
- MajsoulMax，原发行包随附，项目与授权见 https://github.com/Avenshy/MajsoulMax 。

动态背景、角色模型及视频按需从第三方服务下载，相关权利归各自权利人所有。
