# yobiyobi.py
from flask import Blueprint, request, jsonify, redirect
import requests
import random

yobiyobi = Blueprint("yobiyobi", __name__)

# =========================================================
# 設定
# =========================================================

STREAM_API = "https://example.com/api/stream/"   # mp4 系 API
M3U8_API   = "https://example.com/api/m3u8/"     # hls 系 API

INVIDIOUS_INSTANCES = [
    'https://inv.nadeko.net',
    'https://invidious.f5.si',
    'https://invidious.lunivers.trade',
    'https://invidious.ducks.party',
    'https://super8.absturztau.be',
    'https://invidious.nikkosphere.com',
    'https://yt.omada.cafe',
    'https://iv.melmac.space',
    'https://iv.duti.dev'
]

TIMEOUT = (3, 6)

# =========================================================
# HTTP セッション
# =========================================================

http_session = requests.Session()

# =========================================================
# ヘッダ生成
# =========================================================

def get_random_headers():
    ua = random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Mozilla/5.0 (X11; Linux x86_64)"
    ])
    return {
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.youtube.com/"
    }

# =========================================================
# Invidious フォールバック解決
# =========================================================

def resolve_invidious(video_id):
    """
    Invidious の latest_version API から
    直接再生可能な mp4 URL を取得
    """
    for base in INVIDIOUS_INSTANCES:
        try:
            res = http_session.get(
                f"{base}/latest_version",
                params={
                    "id": video_id,
                    "itag": "18",     # 360p mp4
                    "local": "true"
                },
                headers=get_random_headers(),
                timeout=TIMEOUT,
                allow_redirects=True
            )

            if res.status_code == 200 and res.url:
                return res.url
        except:
            continue

    return None

# =========================================================
# メイン取得ロジック
# =========================================================

def resolve_stream(video_id):
    """
    return:
        {
            "primary": mp4 低画質,
            "fallback": mp4 高画質,
            "m3u8": hls url,
            "invidious": invidious mp4
        }
    """
    urls = {
        "primary": None,
        "fallback": None,
        "m3u8": None,
        "invidious": None
    }

    # ---------------- MP4 ----------------
    try:
        res = http_session.get(
            f"{STREAM_API}{video_id}",
            headers=get_random_headers(),
            timeout=TIMEOUT
        )
        if res.status_code == 200:
            data = res.json()
            formats = data.get("formats", [])

            # itag 18 = 360p mp4
            for fmt in formats:
                if str(fmt.get("itag")) == "18" and fmt.get("url"):
                    urls["primary"] = fmt["url"]
                    break

            # fallback = video codec がある最初のもの
            if not urls["primary"]:
                for fmt in formats:
                    if fmt.get("url") and fmt.get("vcodec") != "none":
                        urls["fallback"] = fmt["url"]
                        break
    except:
        pass

    # ---------------- HLS ----------------
    try:
        res = http_session.get(
            f"{M3U8_API}{video_id}",
            headers=get_random_headers(),
            timeout=TIMEOUT
        )
        if res.status_code == 200:
            data = res.json()
            m3u8_formats = data.get("m3u8_formats", [])

            if m3u8_formats:
                best = max(
                    m3u8_formats,
                    key=lambda x: int(
                        (x.get("resolution", "0x0").split("x")[-1]) or 0
                    )
                )
                urls["m3u8"] = best.get("url")
    except:
        pass

    # ---------------- Invidious ----------------
    if not urls["m3u8"] and not urls["fallback"] and not urls["primary"]:
        urls["invidious"] = resolve_invidious(video_id)

    return urls

# =========================================================
# /api/streamurl/yobiyobi
# <video src="..."> 用
# =========================================================

@yobiyobi.route("/api/streamurl/yobiyobi")
def api_streamurl_yobiyobi():
    video_id = request.args.get("video_id")
    if not video_id:
        return "", 400

    urls = resolve_stream(video_id)

    # 優先順位: HLS → mp4 fallback → mp4 primary → Invidious
    if urls["m3u8"]:
        return redirect(urls["m3u8"], 302)

    if urls["fallback"]:
        return redirect(urls["fallback"], 302)

    if urls["primary"]:
        return redirect(urls["primary"], 302)

    if urls["invidious"]:
        return redirect(urls["invidious"], 302)

    return "", 404

# =========================================================
# /api/streammeta
# JS failover 用
# =========================================================

@yobiyobi.route("/api/streammeta")
def api_streammeta():
    video_id = request.args.get("video_id")
    backend = request.args.get("backend")

    if backend != "yobiyobi" or not video_id:
        return jsonify({}), 400

    urls = resolve_stream(video_id)

    if urls["m3u8"]:
        return jsonify({
            "type": "m3u8",
            "url": urls["m3u8"]
        })

    if urls["fallback"]:
        return jsonify({
            "type": "mp4",
            "url": urls["fallback"]
        })

    if urls["primary"]:
        return jsonify({
            "type": "mp4",
            "url": urls["primary"]
        })

    if urls["invidious"]:
        return jsonify({
            "type": "mp4",
            "url": urls["invidious"]
        })

    return jsonify({}), 404
