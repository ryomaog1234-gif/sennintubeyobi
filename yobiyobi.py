# yobiyobi.py
from flask import Blueprint, request, jsonify, redirect, url_for
import requests
import random
import time

yobiyobi = Blueprint("yobiyobi", __name__)

STREAM_API = "https://ytdl-0et1.onrender.com/api/stream/"
M3U8_API   = "https://ytdl-0et1.onrender.com/m3u8/"

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
http_session = requests.Session()
INSTANCE_SCORE = {i: 0 for i in INVIDIOUS_INSTANCES}

def sorted_instances():
    return sorted(INVIDIOUS_INSTANCES, key=lambda x: INSTANCE_SCORE.get(x,0), reverse=True)

def score_success(instance, latency):
    INSTANCE_SCORE[instance] += max(1, 5 - int(latency*2))

def score_fail(instance):
    INSTANCE_SCORE[instance] -= 3

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

def resolve_invidious(video_id, want_hls=False):
    for base in sorted_instances():
        start = time.time()
        try:
            if want_hls:
                res = http_session.get(f"{base}/api/v1/videos/{video_id}", headers=get_random_headers(), timeout=TIMEOUT)
                if res.status_code==200:
                    data = res.json()
                    hls_url = data.get("hlsUrl") or data.get("manifestUrl")
                    if hls_url:
                        score_success(base, time.time()-start)
                        return {"type":"m3u8","url":hls_url}
            res = http_session.get(f"{base}/latest_version", params={"id":video_id,"itag":"18","local":"true"}, headers=get_random_headers(), timeout=TIMEOUT, allow_redirects=True)
            if res.status_code==200 and res.url:
                score_success(base,time.time()-start)
                return {"type":"mp4","url":res.url}
            score_fail(base)
        except:
            score_fail(base)
            continue
    return None

def resolve_stream(video_id, want_hls=False):
    urls = {"primary":None,"fallback":None,"m3u8":None,"invidious":None}
    try:
        res = http_session.get(f"{STREAM_API}{video_id}", headers=get_random_headers(), timeout=TIMEOUT)
        if res.status_code==200:
            formats = res.json().get("formats",[])
            for fmt in formats:
                if str(fmt.get("itag"))=="18" and fmt.get("url"):
                    urls["primary"]=fmt["url"]
                    break
            for fmt in formats:
                if fmt.get("url") and fmt.get("vcodec")!="none":
                    urls["fallback"]=fmt["url"]
                    break
    except:
        pass
    if want_hls:
        try:
            res = http_session.get(f"{M3U8_API}{video_id}", headers=get_random_headers(), timeout=TIMEOUT)
            if res.status_code==200:
                m3u8_formats = res.json().get("m3u8_formats",[])
                if m3u8_formats:
                    best=max(m3u8_formats,key=lambda x:int((x.get("resolution","0x0").split("x")[-1]) or 0))
                    urls["m3u8"]=best.get("url")
        except:
            pass
    if not urls["m3u8"] and not urls["fallback"] and not urls["primary"]:
        urls["invidious"]=resolve_invidious(video_id, want_hls)
    return urls

@yobiyobi.route("/api/streamurl/yobiyobi")
def api_streamurl_yobiyobi():
    video_id = request.args.get("video_id")
    mode = request.args.get("mode","stream")
    if not video_id:
        return "",400
    want_hls = (mode=="download")
    urls = resolve_stream(video_id,want_hls)
    if mode=="download":
        if urls["m3u8"]: return redirect(urls["m3u8"],302)
        if urls["invidious"]: return redirect(urls["invidious"]["url"],302)
        if urls["fallback"]: return redirect(urls["fallback"],302)
        if urls["primary"]: return redirect(urls["primary"],302)
        return "",404
    if urls["fallback"]: return redirect(urls["fallback"],302)
    if urls["primary"]: return redirect(urls["primary"],302)
    if urls["invidious"] and urls["invidious"]["type"]=="mp4":
        return redirect(urls["invidious"]["url"],302)
    return "",404

@yobiyobi.route("/api/streammeta")
def api_streammeta():
    video_id = request.args.get("video_id")
    backend = request.args.get("backend")
    mode = request.args.get("mode","stream")
    if backend!="yobiyobi" or not video_id:
        return jsonify({}),400
    want_hls = (mode=="download")
    urls = resolve_stream(video_id,want_hls)
    m3u8_url = urls.get("m3u8") or (urls.get("invidious")["url"] if urls.get("invidious") and urls.get("invidious")["type"]=="m3u8" else None)
    return jsonify({
        "primary": urls.get("primary"),
        "fallback": urls.get("fallback"),
        "m3u8_url": m3u8_url
    })
