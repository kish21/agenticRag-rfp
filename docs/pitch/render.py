import os
from playwright.sync_api import sync_playwright
FPS=30; ANIM=3.3
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    pg=b.new_page(viewport={"width":1920,"height":1080})
    for s in range(1,12):
        d=f"f{s:02d}"; os.makedirs(d,exist_ok=True)
        pg.goto(f"file://{os.getcwd()}/deck.html?s={s}"); pg.wait_for_load_state("networkidle")
        pg.evaluate("document.fonts.ready")
        pg.evaluate("document.getAnimations().forEach(a=>a.pause())")
        for f in range(int(ANIM*FPS)):
            pg.evaluate(f"document.getAnimations().forEach(a=>a.currentTime={f*1000/FPS})")
            pg.screenshot(path=f"{d}/{f:04d}.jpg",type="jpeg",quality=94)
        print(s,flush=True)
    b.close()
