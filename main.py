import json
import requests
import urllib.parse
import time
import datetime
import random
import os
import subprocess
import concurrent.futures

from cache import cache

from fastapi import FastAPI, Response, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Union


# =========================
# 基本設定
# =========================

max_api_wait_time = 3
max_time = 10
version = "1.0"

apis = [
    "https://yewtu.be/",
    "https://invidious.f5.si/",
    "https://invidious.perennialte.ch/",
    "https://iv.nboeck.de/",
    "https://invidious.jing.rocks/",
    "https://yt.omada.cafe/",
    "https://invidious.reallyaweso.me/",
    "https://invidious.privacyredirect.com/",
    "https://invidious.nerdvpn.de/",
    "https://iv.nowhere.moe/",
    "https://inv.tux.pizza/",
    "https://invidious.privacydev.net/",
    "https://invidious.yourdevice.ch/",
    "https://iv.ggtyler.dev/",
    "https://invidious.einfachzocken.eu/",
    "https://iv.datura.network/",
    "https://invidious.private.coffee/",
    "https://invidious.protokolla.fi/",
    "https://yt.cdaut.de/",
]

apichannels = apis.copy()
apicomments = apis.copy()

os.path.exists("./senninverify") and os.chmod("./senninverify", 0o755)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


# =========================
# 例外
# =========================

class APItimeoutError(Exception):
    pass


# =========================
# 共通関数
# =========================

def is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


# =========================
# API 最速勝ち
# =========================

def api_request_core(api_list, url):
    def fetch(api):
        try:
            res = session.get(api + url, timeout=max_api_wait_time)
            if res.status_code == 200 and is_json(res.text):
                return api, res.text
        except requests.RequestException:
            pass
        return None

    starttime = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(api_list)) as executor:
        futures = [executor.submit(fetch, api) for api in api_list]

        for future in concurrent.futures.as_completed(futures, timeout=max_time):
            if time.time() - starttime >= max_time - 1:
                break

            result = future.result()
            if result:
                api, text = result
                api_list.remove(api)
                api_list.insert(0, api)
                return text

    raise APItimeoutError("APIがタイムアウトしました")


def apirequest(url):
    return api_request_core(apis, url)


def apichannelrequest(url):
    return api_request_core(apichannels, url)


def apicommentsrequest(url):
    return api_request_core(apicomments, url)


def check_cookie(cookie: Union[str, None]) -> bool:
    return cookie == "True"


# =========================
# APIラッパー（キャッシュ）
# =========================

@cache(seconds=30)
def get_search(q, page):
    t = json.loads(apirequest(
        f"api/v1/search?q={urllib.parse.quote(q)}&page={page}&hl=jp"
    ))

    results = []
    for i in t:
        if i["type"] == "video":
            results.append({
                "type": "video",
                "title": i["title"],
                "id": i["videoId"],
                "author": i["author"],
                "authorId": i["authorId"],
                "length": str(datetime.timedelta(seconds=i["lengthSeconds"])),
                "published": i["publishedText"]
            })
        elif i["type"] == "playlist":
            results.append({
                "type": "playlist",
                "title": i["title"],
                "id": i["playlistId"],
                "count": i["videoCount"]
            })
        else:
            thumb = i["authorThumbnails"][-1]["url"]
            if not thumb.startswith("https"):
                thumb = "https://" + thumb
            results.append({
                "type": "channel",
                "author": i["author"],
                "id": i["authorId"],
                "thumbnail": thumb
            })
    return results


# =========================
# FastAPI
# =========================

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.mount("/css", StaticFiles(directory="./css"), name="css")
app.mount("/word", StaticFiles(directory="./blog", html=True), name="word")

app.add_middleware(GZipMiddleware, minimum_size=1000)

templates = Jinja2Templates(directory="templates")


@app.get("/")
def home(request: Request, response: Response, yuki: Union[str, None] = Cookie(None)):
    if check_cookie(yuki):
        response.set_cookie("yuki", "True", max_age=7 * 24 * 60 * 60)
        return templates.TemplateResponse("home.html", {"request": request})
    return RedirectResponse("/word")


# =========================
# ★ 検索エンドポイント
# =========================

@app.get("/search")
def search(q: str, page: int = 1):
    return JSONResponse({
        "query": q,
        "page": page,
        "results": get_search(q, page)
    })


# =========================
# 404 Not Found 対策
# =========================

@app.exception_handler(StarletteHTTPException)
def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return RedirectResponse("/")
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
