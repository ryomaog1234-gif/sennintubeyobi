# yobiyobi.py
from flask import Blueprint, request, jsonify, redirect
import requests
import random
import time

yobiyobi = Blueprint("yobiyobi", __name__)

# ===============================
# yt-dlp 系 API（複数対応）
# ===============================
STREAM_APIS = [
    "https://ytdl-0et1.onrender.com/api/stream/",
    "https://yudlp.vercel.app/stream/"
]

M3U8_API = "https://ytdl-0et1.onrender.com/m3u8/"

# ===============================
# Invidious / Poketube / Materialious
# ===============================
INVIDIOUS_INSTANCES = list(set([
    "https://yt.omada.cafe",
    "https://invidious.schenkel.eti.br",
    "https://invidious.nikkosphere.com",
    "https://siawaseok-wakame-server2.glitch.me",
    "https://clover-pitch-position.glitch.me",
    "https://inv.nadeko.net",
    "https://iv.duti.dev",
    "https://yewtu.be",
    "https://id.420129.xyz",
    "https://invidious.f5.si",
    "https://invidious.nerdvpn.de",
    "https://invidious.tiekoetter.com",
    "https://lekker.gay",
    "https://nyc1.iv.ggtyler.dev",
    "https://iv.ggtyler.dev",
    "https://invid-api.poketube.fun",
    "https://iv.melmac.space",
    "https://cal1.iv.ggtyler.dev",
    "https://pol1.iv.ggtyler.dev",
    "https://yt.artemislena.eu",
    "https://invidious.lunivers.trade",
    "https://eu-proxy.poketube.fun",
    "https://invidious.reallyaweso.me",
    "https://invidious.dhusch.de",
    "https://usa-proxy2.poketube.fun",
    "https://invidious.darkness.service",
    "https://iv.datura.network",
    "https://invidious.private.coffee",
    "https://invidious.projectsegfau.lt",
    "https://invidious.perennialte.ch",
    "https://usa-proxy.poketube.fun",
    "https://invidious.exma.de",
    "https://invidious.einfachzocken.eu",
    "https://inv.zzls.xyz",
    "https://yt.yoc.ovh",
    "https://rust.oskamp.nl",
    "https://invidious.adminforge.de",
    "https://invidious.catspeed.cc",
    "https://inst1.inv.catspeed.cc",
    "https://inst2.inv.catspeed.cc",
    "https://materialious.nadeko.net",
    "https://inv.us.projectsegfau.lt",
    "https://invidious.qwik.space",
    "https://invidious.jing.rocks",
    "https://yt.thechangebook.org",
    "https://vro.omcat.info",
    "https://iv.nboeck.de",
    "https://youtube.mosesmang.com",
    "https://iteroni.com",
    "https://subscriptions.gir.st",
    "https://invidious.fdn.fr",
    "https://inv.vern.cc",
    "https://invi.susurrando.com"
]))

TIMEOUT = (3, 6)
http_session = requests.Session()
INSTANCE_SCORE = {i: 0 for i in INVIDIOUS_INSTANCES}


# ===============================
# Invidious スコア管理
# ===============================
def sorted_instances():
    return sorted(
        INVIDIOUS_INSTANCES,
        key=lambda x: INSTANCE_SCORE.get(x, 0),
        reverse=True
    )

def score_success(instance, latency):
    INSTANCE_SCORE[instance] += max(1, 8 - int(latency * 2))

def score_fail(instance):
    INSTANCE_SCORE[instance] -= 5


# ===============================
# HTTP ヘッダ
# ===============================
def get_random_headers():
    return {
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Mozilla/5.0 (X11; Linux x86_64)"
        ]),
        "Accept": "*/*",
        "Accept-Language": "ja,en-US;q=0.9",
        "Referer": "https://www.youtube.com/"
    }


# ===============================
# Invidious 解決（1080p 最優先）
# ===============================
def resolve_invidious(video_id, want_hls=False):
    for base in sorted_instances():
        start = time.time()
        try:
            res = http_session.get(
                f"{base}/api/v1/videos/{video_id}",
                headers=get_random_headers(),
                timeout=TIMEOUT
            )
            if res.status_code != 200:
                score_fail(base)
                continue

            data = res.json()

            if want_hls:
                hls_url = data.get("hlsUrl") or data.get("manifestUrl")
                if hls_url:
                    score_success(base, time.time() - start)
                    return {"type": "m3u8", "url": hls_url}

            formats = data.get("adaptiveFormats", []) + data.get("formatStreams", [])
            best = None
            best_h = 0

            for f in formats:
                if f.get("container") != "mp4":
                    continue
                try:
                    h = int(f.get("resolution", "0x0").split("x")[-1])
                except:
                    h = 0
                if h >= best_h and f.get("url"):
                    best = f
                    best_h = h

            if best:
                score_success(base, time.time() - start)
                return {"type": "mp4", "url": best["url"]}

            score_fail(base)
        except:
            score_fail(base)
            continue

    return None


# ===============================
# yt-dlp / Invidious 統合解決
# ===============================
def resolve_stream(video_id, want_hls=False):
    urls = {
        "mp4_1080": None,
        "mp4_best": None,
        "m3u8_1080": None,
        "m3u8_best": None,
        "invidious": None
    }

    # yt-dlp MP4
    for api in STREAM_APIS:
        try:
            res = http_session.get(
                f"{api}{video_id}",
                headers=get_random_headers(),
                timeout=TIMEOUT
            )
            if res.status_code != 200:
                continue

            formats = res.json().get("formats", [])
            best_h = 0

            for fmt in formats:
                if fmt.get("vcodec") == "none":
                    continue
                url = fmt.get("url")
                try:
                    h = int(fmt.get("resolution", "0x0").split("x")[-1])
                except:
                    h = 0

                if h >= 1080 and not urls["mp4_1080"]:
                    urls["mp4_1080"] = url

                if h > best_h and url:
                    urls["mp4_best"] = url
                    best_h = h

            if urls["mp4_1080"] or urls["mp4_best"]:
                break
        except:
            continue

    # yt-dlp HLS
    if want_hls:
        try:
            res = http_session.get(
                f"{M3U8_API}{video_id}",
                headers=get_random_headers(),
                timeout=TIMEOUT
            )
            if res.status_code == 200:
                m3u8_formats = res.json().get("m3u8_formats", [])
                best_h = 0
                for f in m3u8_formats:
                    try:
                        h = int(f.get("resolution", "0x0").split("x")[-1])
                    except:
                        h = 0
                    if h >= 1080 and not urls["m3u8_1080"]:
                        urls["m3u8_1080"] = f.get("url")
                    if h > best_h and f.get("url"):
                        urls["m3u8_best"] = f.get("url")
                        best_h = h
        except:
            pass

    if not any(urls.values()):
        urls["invidious"] = resolve_invidious(video_id, want_hls)

    return urls


# ===============================
# redirect API
# ===============================
@yobiyobi.route("/api/streamurl/yobiyobi")
def api_streamurl_yobiyobi():
    video_id = request.args.get("video_id")
    mode = request.args.get("mode", "stream")

    if not video_id:
        return "", 400

    want_hls = (mode == "download")
    urls = resolve_stream(video_id, want_hls)

    if want_hls:
        if urls["m3u8_1080"]:
            return redirect(urls["m3u8_1080"], 302)
        if urls["m3u8_best"]:
            return redirect(urls["m3u8_best"], 302)

    if urls["mp4_1080"]:
        return redirect(urls["mp4_1080"], 302)
    if urls["mp4_best"]:
        return redirect(urls["mp4_best"], 302)

    if urls["invidious"]:
        return redirect(urls["invidious"]["url"], 302)

    return "", 404


# ===============================
# streammeta
# ===============================
@yobiyobi.route("/api/streammeta")
def api_streammeta():
    video_id = request.args.get("video_id")
    backend = request.args.get("backend")
    mode = request.args.get("mode", "stream")

    if backend != "yobiyobi" or not video_id:
        return jsonify({}), 400

    want_hls = (mode == "download")
    urls = resolve_stream(video_id, want_hls)

    for k in ["m3u8_1080", "m3u8_best", "mp4_1080", "mp4_best"]:
        if urls.get(k):
            return jsonify({
                "type": "m3u8" if k.startswith("m3u8") else "mp4",
                "url": urls[k]
            })

    if urls["invidious"]:
        return jsonify(urls["invidious"])

    return jsonify({}), 404
