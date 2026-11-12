"""Play cached Mahjong Soul Spine scenes. Browser requests resolve only to local files."""
import base64
from io import BytesIO
import time
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

from PIL import Image
from playwright.sync_api import sync_playwright
from model_player import SIZE

HTML = """<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="player.css">
<style>*{margin:0}html,body,#stage{width:100%;height:100%;background:transparent}</style>
<div id="stage"></div><script src="player.js"></script><script>
new spine.SpinePlayer('stage', {
    binaryUrl:'model.skel', atlasUrl:'model.atlas', alpha:true, backgroundColor:'#00000000',
    preserveDrawingBuffer:true, showControls:false, showLoading:false,
    success(player) {
        const names=player.skeleton.data.animations.map(a=>a.name);
        const idle=names.find(s=>s.toLowerCase()==='idle') || names.find(s=>/idle/i.test(s)) || names[0];
        if(idle) player.setAnimation(idle,true);
        player.play();
        player.stopRendering();
        window.player=player;
        window.ready=true;
    },
    error(player,msg){window.problem=String(msg);}
});
</script>"""


def main():
    folder = Path(sys.argv[1]).resolve().parent
    runtime = Path(__file__).resolve().parent/'spine-runtime'
    files = {'player.js':runtime/'spine-player.min.js','player.css':runtime/'spine-player.min.css',
             'model.skel':folder/'spine.skel.txt','model.atlas':folder/'spine.atlas.txt'}
    for image in folder.glob('*.png'):
        files[image.name] = image
    def serve(route):
        url = urlsplit(route.request.url)
        name = unquote(url.path.lstrip('/'))
        if url.hostname!='coach.invalid':
            route.abort()
        elif not name:
            route.fulfill(content_type='text/html',body=HTML)
        elif name in files:
            mime = {'js':'application/javascript','css':'text/css','png':'image/png','atlas':'text/plain'}
            route.fulfill(path=files[name],content_type=mime.get(name.split('.')[-1],'application/octet-stream'))
        else:
            route.fulfill(status=404,body='')
    with sync_playwright() as pw:
        options = dict(headless=True,args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-background-networking'])
        try:
            browser = pw.chromium.launch(**options)
        except Exception:
            browser = pw.chromium.launch(channel='msedge',**options)
        page = browser.new_page(viewport={'width':SIZE,'height':SIZE},device_scale_factor=1,service_workers='block')
        page.route('**/*',serve)
        page.goto('https://coach.invalid/')
        page.wait_for_function('window.ready || window.problem',timeout=15000)
        error = page.evaluate('window.problem')
        if error:
            raise ValueError(error)
        first = True
        for req in sys.stdin.buffer:
            if req.strip()!=b'frame':
                break
            deadline = time.monotonic()+5
            while True:
                data = page.evaluate("""() => { player.drawFrame(false);
                    return player.canvas.toDataURL('image/png').split(',')[1]; }""")
                with Image.open(BytesIO(base64.b64decode(data))) as img:
                    rgba = img.convert('RGBA').resize((SIZE,SIZE))
                if not first or rgba.getchannel('A').getbbox():
                    pixels = rgba.tobytes()
                    first = False
                    break
                if time.monotonic()>deadline:
                    raise RuntimeError('未能绘制可见的动态立绘')
                time.sleep(.05)
            sys.stdout.buffer.write(pixels)
            sys.stdout.buffer.flush()
        browser.close()


if __name__=='__main__':
    main()
