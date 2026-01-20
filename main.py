import json
import requests
import urllib.parse
import time
import datetime
import os
import subprocess
import concurrent.futures

from cache import cache

from fastapi import FastAPI, Request, Response, Cookie, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response as RawResponse
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
    "https://invidious.private.coffee/",
    "https://iv.ggtyler.dev/",
    "https://iv.datura.network/",
    "https://yt.cdaut.de/",
]

apichannels = apis.copy()
apicomments = apis.copy()

if os.path.exists("./senninverify"):
    try:
        os.chmod("./senninverify", 0o755)
    except:
        pass

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


# =========================
# 例外
# =========================

class APItimeoutError(Exception):
    pass


# =========================
# 共通
# =========================

def is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


def check_cookie(cookie: Union[str, None]) -> bool:
    return cookie == "True"


def try_json(url: str):
    try:
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


# =========================
# 並列API最速勝ち
# =========================

def api_request_core(api_list, url):
    def fetch(api):
        try:
            r = session.get(api + url, timeout=max_api_wait_time)
            if r.status_code == 200 and is_json(r.text):
                return api, r.text
        except:
            pass
        return None

    start = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(api_list)) as executor:
        futures = [executor.submit(fetch, api) for api in api_list]

        for future in concurrent.futures.as_completed(futures, timeout=max_time):
            if time.time() - start >= max_time - 1:
                break

            result = future.result()
            if result:
                api, text = result
                api_list.remove(api)
                api_list.insert(0, api)
                return text

    raise APItimeoutError("API timeout")


def apirequest(url):
    return api_request_core(apis, url)


def apichannelrequest(url):
    return api_request_core(apichannels, url)


def apicommentsrequest(url):
    return api_request_core(apicomments, url)


# =========================
# APIラッパー
# =========================

@cache(seconds=30)
def get_search(q, page):
    data = json.loads(
        apirequest(f"api/v1/search?q={urllib.parse.quote(q)}&page={page}&hl=jp")
    )

    results = []
    for i in data:
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
# ★ DASH対応（そのまま）
# =========================

def get_data(videoid):
    t = json.loads(apirequest("api/v1/videos/" + urllib.parse.quote(videoid)))

    videourls = [i["url"] for i in t.get("formatStreams", [])]
    hls_url = t.get("hlsUrl")
    nocookie_url = f"https://www.youtube-nocookie.com/embed/{videoid}"

    adaptive = t.get("adaptiveFormats", [])

    audio = None
    videos = {}

    for f in adaptive:
        mime = f.get("type", "")
        if mime.startswith("audio/"):
            if not audio or f.get("bitrate", 0) > audio.get("bitrate", 0):
                audio = f
        elif mime.startswith("video/"):
            h = f.get("height")
            if h:
                if h not in videos or ("mp4" in mime and "mp4" not in videos[h]["type"]):
                    videos[h] = f

    dash = None
    if audio and videos:
        dash = {
            "audio": {
                "url": audio["url"],
                "mime": audio["type"],
                "bitrate": audio.get("bitrate")
            },
            "videos": {
                str(h): {
                    "url": videos[h]["url"],
                    "mime": videos[h]["type"],
                    "fps": videos[h].get("fps"),
                    "bitrate": videos[h].get("bitrate")
                }
                for h in sorted(videos.keys(), reverse=True)
            }
        }

    return (
        [{"id": i["videoId"], "title": i["title"], "author": i["author"], "authorId": i["authorId"]}
         for i in t["recommendedVideos"]],
        videourls,
        t["descriptionHtml"].replace("\n", "<br>"),
        t["title"],
        t["authorId"],
        t["author"],
        t["authorThumbnails"][-1]["url"],
        nocookie_url,
        hls_url,
        dash,
    )


# =========================
# FastAPI
# =========================

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.mount("/css", StaticFiles(directory="./css"), name="css")
app.mount("/word", StaticFiles(directory="./blog", html=True), name="word")
app.add_middleware(GZipMiddleware, minimum_size=1000)

templates = Jinja2Templates(directory="templates")


# =========================
# 高画質ストリーム（1080p固定）
# =========================

HLS_API_BASE_URL = "https://yudlp.vercel.app/m3u8/"


@app.get("/stream/high")
def stream_high(v: str):

    data = try_json(f"{HLS_API_BASE_URL}{v}")
    if data:
        m3u8s = [f for f in data.get("m3u8_formats", []) if f.get("url")]

        # ★ 1080p固定
        m3u8_1080 = [
            f for f in m3u8s
            if (f.get("resolution") or "").endswith("x1080")
        ]

        if m3u8_1080:
            return RedirectResponse(m3u8_1080[0]["url"])

        # フォールバック（既存動作）
        if m3u8s:
            best = sorted(
                m3u8s,
                key=lambda f: int((f.get("resolution") or "0x0").split("x")[-1]),
                reverse=True
            )[0]
            return RedirectResponse(best["url"])

    try:
        t = json.loads(apirequest("api/v1/videos/" + urllib.parse.quote(v)))
        if t.get("hlsUrl"):
            return RedirectResponse(t["hlsUrl"])
    except:
        pass

    try:
        for f in t.get("formatStreams", []):
            if f.get("url"):
                return RedirectResponse(f["url"])
    except:
        pass

    raise HTTPException(status_code=503, detail="High quality stream unavailable")
