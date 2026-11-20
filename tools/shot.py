import sys, asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, w, h, mobile in [('d',1457,812,False),('m',390,844,True)]:
            pg = await b.new_page(viewport={'width':w,'height':h}, device_scale_factor=1)
            for path in sys.argv[1:]:
                await pg.goto(f'http://localhost:8765/{path}', wait_until='networkidle')
                await pg.wait_for_timeout(300)
                await pg.screenshot(path=f'/home/claude/shots/{name}_{path.replace("/","_") or "index"}.png')
        await b.close()
asyncio.run(main())
