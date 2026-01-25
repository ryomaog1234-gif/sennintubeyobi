import random
import requests
import urllib.parse
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

app = FastAPI()

INVIDIOUS_INSTANCES = [
    'https://inv.nadeko.net/',
    'https://invidious.f5.si/',
    'https://invidious.lunivers.trade/',
    'https://invidious.ducks.party/',
    'https://super8.absturztau.be/',
    'https://invidious.nikkosphere.com/',
    'https://yt.omada.cafe/',
    'https://iv.melmac.space/',
    'https://iv.duti.dev/',
]

STREAM_API = "https://ytdl-0et1.onrender.com/stream/"
M3U8_API = "https://ytdl-0et1.onrender.com/m3u8/"


# =========================
# utils
# =========================

def pick_instance():
    return random.choice(INVIDIOUS_INSTANCES).rstrip("/")


def get_invidious_video(video_id: str):
    inst = pick_instance()
    url = f"{inst}/api/v1/videos/{video_id}"
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    return r.json()


def extract_best_video(formats):
    """
    progressive (audio+video) 優先
    """
    videos = [
        f for f in formats
        if f.get("type", "").startswith("video/")
        and f.get("audioQuality")
    ]
    videos.sort(key=lambda x: x.get("qualityLabel", ""), reverse=True)
    return videos[0]["url"] if videos else None


# =========================
# main endpoint
# =========================

@app.get("/api/streamurl/yobiyobi")
def yobiyobi_stream(video_id: str = Query(...)):
    """
    フロントからは <video src=ここ> で使う
    """
    # ① Invidious 直URL
    try:
        data = get_invidious_video(video_id)
        fmt = extract_best_video(data.get("formatStreams", []))
        if fmt:
            return RedirectResponse(fmt)
    except Exception:
        pass

    # ② ytdl stream API
    try:
        stream_url = urllib.parse.urljoin(STREAM_API, video_id)
        r = requests.head(stream_url, timeout=5)
        if r.status_code == 200:
            return RedirectResponse(stream_url)
    except Exception:
        pass

    # ③ m3u8 最終フォールバック
    try:
        m3u8_url = urllib.parse.urljoin(M3U8_API, video_id)
        return RedirectResponse(m3u8_url)
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="yobiyobi: stream unavailable")


# =========================
# debug / health
# =========================

@app.get("/api/streamurl/yobiyobi/health")
def health():
    return JSONResponse({
        "status": "ok",
        "mode": "yobiyobi",
        "strategy": [
            "invidious_direct",
            "ytdl_stream",
            "m3u8_fallback"
        ]
    })
