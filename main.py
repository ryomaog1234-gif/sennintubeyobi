import json
import urllib.parse
import time
import datetime
import os
import asyncio

from typing import Union

import httpx
from fastapi import FastAPI, Request, Response, Cookie, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response as RawResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from cache import cache

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

# =========================
# HTTP Client（async）
# =========================

async_client = httpx.AsyncClient(
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=max_api_wait_time,
    http2=True,
)

# =========================
# 例外
# =========================

class APItimeoutError(Exception):
    pass

# =========================
# 共通
# =========================

def is_json_fast(text: str) -> bool:
    return bool(text) and text[0] in "{["

def check_cookie(cookie: Union[str, None]) -> bool:
    return cookie == "True"

# =========================
# 並列API最速勝ち（async）
# =========================

async def api_request_core(api_list, url: str):
    async def fetch(api: str):
        try:
            r = await async_client.get(api + url)
            if r.status_code == 200 and is_json_fast(r.text):
                return api, r.text
        except:
            return None

    tasks = [fetch(api) for api in api_list]

    try:
        for coro in asyncio.as_completed(tasks, timeout=max_time):
            result = await coro
            if result:
                api, text = result
                # 先頭に持ってくる（破壊的removeを避ける）
                api_list[:] = [api] + [a for a in api_list if a != api]
                return text
    except asyncio.TimeoutError:
        pass

    raise APItimeoutError("API timeout")

async def apirequest(url: str):
    return await api_request_core(apis, url)

async def apichannelrequest(url: str):
    return await api_request_core(apichannels, url)

async def apicommentsrequest(url: str):
    return await api_request_core(apicomments, url)

# =========================
# APIラッパー
# =========================

@cache(seconds=30)
async def get_search(q, page):
    data = json.loads(
        await apirequest(
            f"api/v1/search?q={urllib.parse.quote(q)}&page={page}&hl=jp"
        )
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
# DASH対応
# =========================

async def get_data(videoid):
    t = json.loads(
        await apirequest("api/v1/videos/" + urllib.parse.quote(videoid))
    )

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
         for i in t.get("recommendedVideos", [])],
        videourls,
        t.get("descriptionHtml", "").replace("\n", "<br>"),
        t.get("title"),
        t.get("authorId"),
        t.get("author"),
        t.get("authorThumbnails", [{}])[-1].get("url"),
        nocookie_url,
        hls_url,
        dash,
        t
    )

# =========================
# チャンネル
# =========================

async def get_channel(channelid):
    t = json.loads(
        await apichannelrequest("api/v1/channels/" + urllib.parse.quote(channelid))
    )

    videos = []
    shorts = []

    for i in t.get("latestVideos", []):
        videos.append({
            "title": i["title"],
            "id": i["videoId"],
            "view_count_text": i.get("viewCountText", ""),
            "length_str": i.get("lengthText", "")
        })

    return (
        videos,
        shorts,
        {
            "channelname": t.get("author"),
            "channelicon": t.get("authorThumbnails", [{}])[-1].get("url"),
            "channelprofile": t.get("description", ""),
            "subscribers_count": t.get("subCountText"),
            "cover_img_url": (
                t["authorBanners"][-1]["url"]
                if t.get("authorBanners") else None
            )
        }
    )

@cache(seconds=30)
async def get_home():
    data = json.loads(await apirequest("api/v1/popular?hl=jp"))

    videos = []
    shorts = []
    channels = []

    for i in data:
        if i.get("type") == "video":
            if (
                i.get("isShort") is True
                or i.get("lengthSeconds") == 0
                or i.get("lengthText") in ("0:00", "", None)
            ):
                shorts.append(i)
            else:
                videos.append(i)
        elif i.get("type") == "channel":
            channels.append(i)

    return videos, shorts, channels

async def get_comments(videoid):
    t = json.loads(
        await apicommentsrequest(
            "api/v1/comments/" + urllib.parse.quote(videoid) + "?hl=jp"
        )
    )
    return [{
        "author": i["author"],
        "authoricon": i["authorThumbnails"][-1]["url"],
        "body": i["contentHtml"].replace("\n", "<br>")
    } for i in t.get("comments", [])]

# =========================
# FastAPI
# =========================

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.mount("/css", StaticFiles(directory="./css"), name="css")
app.mount("/word", StaticFiles(directory="./blog", html=True), name="word")
app.add_middleware(GZipMiddleware, minimum_size=1000)

templates = Jinja2Templates(directory="templates")

# =========================
# 高画質ストリーム
# =========================

STREAM_YTDL_API_BASE_URL = "https://yudlp.vercel.app/stream/"

@app.get("/stream/high")
async def stream_high(v: str):
    try:
        return RedirectResponse(f"{STREAM_YTDL_API_BASE_URL}{v}")
    except:
        pass

    t = json.loads(await apirequest("api/v1/videos/" + urllib.parse.quote(v)))
    if t.get("hlsUrl"):
        return RedirectResponse(t["hlsUrl"])

    raise HTTPException(status_code=503, detail="High quality stream unavailable")

# =========================
# ルーティング
# =========================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, response: Response, sennin: Union[str, None] = Cookie(None)):
    if not check_cookie(sennin):
        return RedirectResponse("/word")

    response.set_cookie("sennin", "True", max_age=7 * 24 * 60 * 60)
    videos, shorts, channels = await get_home()

    return templates.TemplateResponse(
        "home.html",
        {"request": request, "videos": videos, "shorts": shorts, "channels": channels}
    )

@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, response: Response, q: str, page: int = 1, sennin: Union[str, None] = Cookie(None)):
    if not check_cookie(sennin):
        return RedirectResponse("/")
    response.set_cookie("sennin", "True", max_age=7 * 24 * 60 * 60)

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "results": await get_search(q, page),
            "word": q,
            "next": f"/search?q={q}&page={page+1}",
        }
    )

@app.get("/watch", response_class=HTMLResponse)
async def watch(request: Request, response: Response, v: str, sennin: Union[str, None] = Cookie(None)):
    if not check_cookie(sennin):
        return RedirectResponse("/")
    response.set_cookie("sennin", "True", max_age=7 * 24 * 60 * 60)

    data = await get_data(v)
    t = data[10]

    if t.get("isShort") is True:
        return templates.TemplateResponse(
            "shorts.html",
            {
                "request": request,
                "videoid": v,
                "author": t["author"],
                "authorid": t["authorId"],
                "authoricon": t["authorThumbnails"][-1]["url"],
                "title": t["title"],
                "hls_url": t.get("hlsUrl"),
            }
        )

    return templates.TemplateResponse(
        "video.html",
        {
            "request": request,
            "videoid": v,
            "videourls": data[1],
            "res": data[0],
            "description": data[2],
            "videotitle": data[3],
            "authorid": data[4],
            "author": data[5],
            "authoricon": data[6],
            "nocookie_url": data[7],
            "hls_url": data[8],
            "dash": data[9],
        }
    )

@app.get("/channel/{cid}", response_class=HTMLResponse)
async def channel(request: Request, response: Response, cid: str, sennin: Union[str, None] = Cookie(None)):
    if not check_cookie(sennin):
        return RedirectResponse("/")
    response.set_cookie("sennin", "True", max_age=7 * 24 * 60 * 60)

    videos, shorts, info = await get_channel(cid)

    return templates.TemplateResponse(
        "channel.html",
        {
            "request": request,
            "results": videos,
            "shorts": shorts,
            "channelname": info["channelname"],
            "channelicon": info["channelicon"],
            "channelprofile": info["channelprofile"],
            "subscribers_count": info["subscribers_count"],
            "cover_img_url": info["cover_img_url"],
        }
    )

@app.get("/subuscript", response_class=HTMLResponse)
async def subuscript(request: Request, sennin: Union[str, None] = Cookie(None)):
    if not check_cookie(sennin):
        return RedirectResponse("/")
    return templates.TemplateResponse("subuscript.html", {"request": request})

@app.get("/comments", response_class=HTMLResponse)
async def comments(request: Request, v: str):
    return templates.TemplateResponse(
        "comments.html",
        {"request": request, "comments": await get_comments(v)}
    )

@app.get("/thumbnail")
async def thumbnail(v: str):
    async with async_client.stream("GET", f"https://img.youtube.com/vi/{v}/0.jpg") as r:
        content = await r.aread()
    return RawResponse(content=content, media_type="image/jpeg")

# =========================
# 例外
# =========================

@app.exception_handler(APItimeoutError)
async def api_wait(request: Request, _):
    return templates.TemplateResponse("APIwait.html", {"request": request}, status_code=500)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_, exc):
    if exc.status_code == 404:
        return RedirectResponse("/")
    raise exc
