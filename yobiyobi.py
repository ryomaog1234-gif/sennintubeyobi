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
# Invidious 解決（MP4は1080pのみ）
# ===============================
def resolve_invidious(video_id):
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
            formats = data.get("adaptiveFormats", []) + data.get("formatStreams", [])

            for f in formats:
                if f.get("container") != "mp4":
                    continue
                try:
                    h = int(f.get("resolution", "0x0").split("x")[-1])
                except:
                    continue

                # ★ MP4は1080pのみ許可
                if h == 1080 and f.get("url"):
                    score_success(base, time.time() - start)
                    return {"type": "mp4", "url": f["url"]}

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
        "m3u8_best": None,
        "invidious": None
    }

    # ===============================
    # yt-dlp MP4（1080pのみ）
    # ===============================
    for api in STREAM_APIS:
        try:
            res = http_session.get(
                f"{api}{video_id}",
                headers=get_random_headers(),
                timeout=TIMEOUT
            )
            if res.status_code != 200:
                continue

            for fmt in res.json().get("formats", []):
                if fmt.get("vcodec") == "none":
                    continue
                try:
                    h = int(fmt.get("resolution", "0x0").split("x")[-1])
                except:
                    continue

                # ★ MP4は1080pのみ
                if h == 1080 and fmt.get("url"):
                    urls["mp4_1080"] = fmt["url"]
                    break

            if urls["mp4_1080"]:
                break
        except:
            continue

    # ===============================
    # yt-dlp HLS（解像度不問・best）
    # ===============================
    if want_hls:
        try:
            res = http_session.get(
                f"{M3U8_API}{video_id}",
                headers=get_random_headers(),
                timeout=TIMEOUT
            )
            if res.status_code == 200:
                best_h = 0
                for f in res.json().get("m3u8_formats", []):
                    try:
                        h = int(f.get("resolution", "0x0").split("x")[-1])
                    except:
                        h = 0

                    if h > best_h and f.get("url"):
                        urls["m3u8_best"] = f["url"]
                        best_h = h
        except:
            pass

    # ===============================
    # Invidious（MP4 1080pのみ）
    # ===============================
    if not urls["mp4_1080"]:
        urls["invidious"] = resolve_invidious(video_id)

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

    # ★ MP4 1080p 最優先
    if urls["mp4_1080"]:
        return redirect(urls["mp4_1080"], 302)

    # ★ MP4が無い場合のみ HLS 許可
    if want_hls and urls["m3u8_best"]:
        return redirect(urls["m3u8_best"], 302)

    # ★ Invidious MP4 1080p
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

    if urls["mp4_1080"]:
        return jsonify({"type": "mp4", "url": urls["mp4_1080"]})

    if want_hls and urls["m3u8_best"]:
        return jsonify({"type": "m3u8", "url": urls["m3u8_best"]})

    if urls["invidious"]:
        return jsonify(urls["invidious"])

    return jsonify({}), 404
