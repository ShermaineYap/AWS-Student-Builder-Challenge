"""End-to-end check of the portfolio and the Rally game in a real headless Chrome.

Run from the repo root:  python tests/e2e_test.py
Checks: sections and nav, hint visible, a full match plays to 5, global stats render from the
API, the game still works with the API down and with the model files blocked, keyboard play,
no console errors, no sideways scroll at phone width. Saves screenshots to tests/shots/.
"""
import functools
import http.server
import json
import os
import random
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHOTS = os.path.join(ROOT, "tests", "shots")
os.makedirs(SHOTS, exist_ok=True)
API = "https://api.example.test"


def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    h.log_message = lambda *a: None
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}/"


def play_match(page, use_keys=False, max_shots=400):
    page.click("#start-btn")
    for _ in range(max_shots):
        page.wait_for_function(
            "() => !document.getElementById('result').hidden || "
            "document.querySelectorAll('#shots button:not([disabled])').length > 0", timeout=15000)
        if not page.locator("#result").is_hidden():
            return
        n = page.locator("#shots button").count()
        if use_keys:
            page.keyboard.press(str(random.randint(1, n)))
        else:
            page.locator("#shots button").nth(random.randrange(n)).click()
    raise AssertionError("match did not finish")


def main():
    random.seed(7)
    srv, url = serve()
    fails = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            fails.append(msg)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROME", "/usr/bin/google-chrome"))

        # ---- 1. desktop, API up ----
        ctx = browser.new_context(viewport={"width": 1366, "height": 860})
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fonts.g" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        posted = []

        def api(route):
            if route.request.method == "OPTIONS":
                return route.fulfill(status=204, headers={"access-control-allow-origin": "*", "access-control-allow-headers": "content-type", "access-control-allow-methods": "GET,POST"})
            posted.append(json.loads(route.request.post_data or "{}"))
            route.fulfill(status=200, headers={"access-control-allow-origin": "*", "content-type": "application/json"},
                          body=json.dumps({"matches": 128, "shots": 2900, "reads": 1200, "visitorWins": 37}))
        page.route(API + "/**", api)
        page.add_init_script(f"Object.defineProperty(window,'RALLY_API',{{get:()=>'{API}',set:()=>{{}}}})")
        page.goto(url)
        page.screenshot(path=os.path.join(SHOTS, "desktop-hero.png"))
        for sid in ["about", "skills", "projects", "contact"]:
            check(page.locator(f"#{sid} h2").is_visible(), f"section #{sid} present")
            page.click(f'.topbar a[href="#{sid}"]')
            page.wait_for_timeout(400)
        check(page.locator("#rally-hint").is_visible(), "creative-feature hint is visible in the hero")
        page.screenshot(path=os.path.join(SHOTS, "desktop-full.png"), full_page=True)

        page.click(".shuttle-btn")
        check(page.locator("#rally").is_visible(), "Rally dialog opens from the hint")
        check(page.evaluate("!!window.RALLY_MODEL"), "model loaded via script tag")
        page.click("#start-btn")
        page.wait_for_selector("#shots button")
        check("locked in" in page.inner_text("#guess-title"), "model locks its guess before the visitor picks")
        page.screenshot(path=os.path.join(SHOTS, "rally-turn.png"))
        page.locator("#shots button").first.click()
        page.wait_for_timeout(900)
        check(page.locator("#bars .bar").count() >= 2, "prediction bars revealed after the pick")
        page.screenshot(path=os.path.join(SHOTS, "rally-reveal.png"))
        page.click("#again-btn", force=True) if not page.locator("#result").is_hidden() else None
        # finish this match
        for _ in range(400):
            if not page.locator("#result").is_hidden():
                break
            page.wait_for_function("() => !document.getElementById('result').hidden || document.querySelectorAll('#shots button:not([disabled])').length > 0", timeout=15000)
            if page.locator("#result").is_hidden():
                n = page.locator("#shots button").count()
                page.locator("#shots button").nth(random.randrange(n)).click()
        you, model = int(page.inner_text("#score-you")), int(page.inner_text("#score-model"))
        check(max(you, model) == 5 and you != model, f"match finished at {you}-{model}")
        page.wait_for_function("() => document.getElementById('result-global').textContent.length > 0", timeout=6000)
        check("128 matches" in page.inner_text("#result-global"), "global stats rendered from the API")
        check(len(posted) == 1 and posted[0]["you"] == you and posted[0]["model"] == model, "result posted once with the right score")
        page.screenshot(path=os.path.join(SHOTS, "rally-result.png"))

        # play again with the keyboard only
        page.click("#again-btn")
        page.wait_for_selector("#shots button:not([disabled])")
        for _ in range(400):
            if not page.locator("#result").is_hidden():
                break
            page.wait_for_function("() => !document.getElementById('result').hidden || document.querySelectorAll('#shots button:not([disabled])').length > 0", timeout=15000)
            if page.locator("#result").is_hidden():
                page.keyboard.press(str(random.randint(1, page.locator("#shots button").count())))
        check(not page.locator("#result").is_hidden(), "a second match can be played with number keys only")
        page.keyboard.press("Escape")
        check(not page.locator("#rally").is_visible(), "Escape closes the game")
        check(not errors, f"no console errors ({errors[:3]})")
        ctx.close()

        # ---- 2. phone, API down, model files blocked ----
        ctx = browser.new_context(viewport={"width": 375, "height": 740}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        perrs = []
        page.on("pageerror", lambda e: perrs.append(str(e)))
        page.route("**/assets/model/*", lambda r: r.abort())
        page.route(API + "/**", lambda r: r.abort())
        page.add_init_script(f"Object.defineProperty(window,'RALLY_API',{{get:()=>'{API}',set:()=>{{}}}})")
        page.goto(url)
        sw = page.evaluate("document.documentElement.scrollWidth")
        check(sw <= 375, f"no sideways scroll on a 375px phone (scrollWidth {sw})")
        page.screenshot(path=os.path.join(SHOTS, "mobile-hero.png"))
        page.screenshot(path=os.path.join(SHOTS, "mobile-full.png"), full_page=True)
        page.click(".nav-rally")
        page.screenshot(path=os.path.join(SHOTS, "mobile-rally.png"))
        play_match(page)
        check(not page.locator("#result").is_hidden(), "game completes with model files and API both unavailable")
        page.screenshot(path=os.path.join(SHOTS, "mobile-result.png"))
        check(not perrs, f"no page errors in fallback mode ({perrs[:3]})")
        ctx.close()
        browser.close()
    srv.shutdown()
    print(f"\n{len(fails)} failure(s)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
