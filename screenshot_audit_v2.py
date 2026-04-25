#!/usr/bin/env python3
"""
Pixel-perfect design audit screenshotter
- Desktop + iPhone 14 Pro mobile
- Smart wait, lazy-load, fonts.ready
- Hide cookie banners, freeze animations, pause video
- Sitemap-first discovery, no <nav> dependency
- Resume support, manifest.json, Figma-friendly names
"""
import asyncio, os, json, re, time
from urllib.parse import urlparse, urljoin, urldefrag
from pathlib import Path
import argparse
from playwright.async_api import async_playwright

BLOCK_PATTERNS = [
    "googletagmanager.com", "google-analytics.com", "hotjar.com",
    "intercom.io", "drift.com", "fullstory.com", "segment.com",
    "doubleclick.net", "facebook.net/tr", "linkedin.com/px"
]

HIDE_SELECTORS = """
#onetrust-consent-sdk, .onetrust-pc-dark-filter, .cookie-banner,
[id*="cookie"], [class*="cookie"], .gdpr, #gdpr, .cc-banner,
.intercom-lightweight-app, #intercom-container, .drift-frame,
#drift-widget, .chat-widget, [id*="chat"], .hs-eu-cookie
"""

def slugify(url, base):
    p = urlparse(url)
    path = p.path.strip('/') or 'home'
    slug = re.sub(r'[^a-z0-9]+', '-', path.lower())[:80]
    return slug or 'home'

async def block_trackers(route):
    url = route.request.url
    if any(b in url for b in BLOCK_PATTERNS):
        return await route.abort()
    await route.continue_()

async def prepare_page(page):
    await page.add_style_tag(content=f"{HIDE_SELECTORS} {{display:none !important; visibility:hidden !important; opacity:0 !important; pointer-events:none !important}}")
    await page.evaluate("""() => {
        document.querySelectorAll('details').forEach(d=>d.open=true);
        const css = '* { animation: none !important; transition: none !important; caret-color: transparent !important; }';
        const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
        document.querySelectorAll('video').forEach(v=>{try{v.pause();v.currentTime=0;}catch(e){}});
        window.scrollTo(0,0);
    }""")

async def smart_wait(page):
    for _ in range(12):
        await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
        await page.wait_for_timeout(120)
    await page.evaluate("window.scrollTo(0,0)")
    try:
        await page.evaluate("document.fonts.ready")
    except:
        pass
    await page.wait_for_timeout(250)

async def shoot(browser, context_opts, url, out_path, retries=2):
    for attempt in range(retries+1):
        page = await browser.new_page(**context_opts)
        try:
            await page.route("**/*", block_trackers)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_load_state("load", timeout=15000)
            await prepare_page(page)
            await smart_wait(page)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            await page.screenshot(path=out_path, full_page=True)
            await page.close()
            return True, ""
        except Exception as e:
            await page.close()
            if attempt == retries:
                return False, str(e)
            await asyncio.sleep(1.5 * (attempt+1))

async def get_links(page, base_origin):
    hrefs = await page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.href)")
    links = set()
    for h in hrefs:
        h,_ = urldefrag(h)
        h = h.split('?')[0]
        if h.startswith(base_origin):
            links.add(h.rstrip('/') or base_origin)
    return links

async def discover(start, max_pages, page):
    origin = f"{urlparse(start).scheme}://{urlparse(start).netloc}"
    seen, queue = set(), [start.rstrip('/') or origin]
    try:
        await page.goto(urljoin(start, "/sitemap.xml"), timeout=10000)
        txt = await page.content()
        urls = re.findall(r'<loc>([^<]+)</loc>', txt)
        for u in urls:
            u = u.split('?')[0].rstrip('/')
            if u.startswith(origin):
                queue.append(u)
    except:
        pass

    results = []
    while queue and len(seen) < max_pages:
        url = queue.pop(0)
        if url in seen: continue
        seen.add(url); results.append(url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            for l in await get_links(page, origin):
                if l not in seen and l not in queue:
                    queue.append(l)
        except:
            pass
    return results

async def main(args):
    out_base = Path(args.out)
    out_base.mkdir(parents=True, exist_ok=True)
    manifest_path = out_base / "manifest.json"
    manifest = []
    if args.resume and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    
    done_urls = {m['url'] for m in manifest if m.get('status')=='ok'}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context_opts_base = dict(
            locale="en-US",
            timezone_id="UTC",
            color_scheme="light",
            reduced_motion="reduce",
        )
        if args.auth:
            context_opts_base["storage_state"] = args.auth

        disc_page = await browser.new_page(**context_opts_base)
        urls = await discover(args.site, args.max_pages, disc_page)
        await disc_page.close()
        urls = [u for u in urls if u not in done_urls]

        viewports = []
        if args.desktop:
            viewports.append(("desktop", {"viewport":{"width":1440,"height":900}, **context_opts_base}))
        if args.mobile:
            viewports.append(("mobile", {"viewport":{"width":390,"height":844}, "device_scale_factor":3, "is_mobile":True, "has_touch":True, **context_opts_base}))
        if args.dark:
            dark_vps = []
            for name, opts in viewports:
                o = dict(opts); o["color_scheme"]="dark"
                dark_vps.append((name+"-dark", o))
            viewports.extend(dark_vps)

        sem = asyncio.Semaphore(args.concurrency)
        async def worker(url):
            slug = slugify(url, args.site)
            entry_base = {"url":url, "slug":slug, "timestamp":int(time.time())}
            for vp_name, opts in viewports:
                async with sem:
                    folder = out_base / vp_name
                    path = folder / f"{slug}.png"
                    i=2
                    while path.exists() and url not in done_urls:
                        path = folder / f"{slug}-{i}.png"; i+=1
                    ok, err = await shoot(browser, opts, url, str(path))
                    manifest.append({**entry_base, "viewport":vp_name, "file":str(path.relative_to(out_base)), "status":"ok" if ok else "error", "error":err})
                    manifest_path.write_text(json.dumps(manifest, indent=2))

        await asyncio.gather(*(worker(u) for u in urls))
        await browser.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Pixel-perfect screenshot audit")
    ap.add_argument("--site", required=True)
    ap.add_argument("--out", default="shots")
    ap.add_argument("--max-pages", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--desktop", action="store_true", default=True)
    ap.add_argument("--mobile", action="store_true", default=True)
    ap.add_argument("--dark", action="store_true", help="also capture dark mode")
    ap.add_argument("--auth", help="path to storage_state.json")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--headless", action="store_true", default=True)
    args = ap.parse_args()
    asyncio.run(main(args))
