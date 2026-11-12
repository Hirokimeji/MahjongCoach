"""Render one Cubism frame per request in a separate, local OpenGL process."""
import os
import sys
from pathlib import Path

SIZE = 720


def main():
    # Keep SDK console output separate from the binary frame channel.
    frames = os.fdopen(os.dup(sys.stdout.fileno()), 'wb')
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root/'model-runtime'))
    from PySide6.QtGui import QGuiApplication, QImage, QOpenGLContext, QOffscreenSurface, QSurfaceFormat
    from PySide6.QtOpenGL import QOpenGLFramebufferObject
    import live2d
    from OpenGL.GL import glViewport
    app = QGuiApplication([])
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
    fmt.setAlphaBufferSize(8)
    ctx = QOpenGLContext()
    ctx.setFormat(fmt)
    if not ctx.create():
        raise RuntimeError('无法创建 OpenGL 绘图环境')
    surface = QOffscreenSurface()
    surface.setFormat(ctx.format())
    surface.create()
    if not ctx.makeCurrent(surface):
        raise RuntimeError('显卡无法启用离屏渲染')
    fbo = QOpenGLFramebufferObject(SIZE, SIZE, QOpenGLFramebufferObject.CombinedDepthStencil)
    if not fbo.isValid() or not fbo.bind():
        raise RuntimeError('无法创建模型画布')
    live2d.enableLog(False)
    live2d.init()
    live2d.glInit()
    model = live2d.Model()
    path = Path(sys.argv[1]).resolve()
    os.chdir(path.parent)
    model.LoadModelJson(path.as_posix())
    model.Resize(SIZE, SIZE)
    model.SetAutoBlink(True)
    model.SetAutoBreath(True)
    groups = model.GetMotions() or {}
    idle = next((name for name in groups if 'idle' in name.lower()), None)
    for request in sys.stdin.buffer:
        if request.strip() != b'frame':
            break
        fbo.bind()
        glViewport(0,0,SIZE,SIZE)
        live2d.clearBuffer()
        if idle and model.IsMotionFinished():
            model.StartRandomMotion(idle,live2d.MotionPriority.IDLE)
        model.Update()
        model.Draw()
        img = fbo.toImage().convertToFormat(QImage.Format_RGBA8888)
        frames.write(img.constBits())
        frames.flush()
    del model
    live2d.dispose()
    frames.close()


if __name__=='__main__':
    main()
