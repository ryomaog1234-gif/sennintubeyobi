from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import requests, random, time

app = FastAPI()

# ===============================
# CONFIG
# ===============================
VIDEO_APIS = [
    "https://iv.melmac.space",
    "https://pol1.iv.ggtyler.dev",
    "https://cal1.iv.ggtyler.dev",
    "https://invidious.0011.lt",
    "https://yt.omada.cafe",
]

STREAM_APIS = [
    "https://yudlp.vercel.app/stream/",
    "https://yt-dl-kappa.vercel.app/short/",
]

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 6

# ===============================
# CACHE / BLACKLIST
# ===============================
SUCCESS_CACHE = {}        # video_id -> api
FAIL_CACHE = {}           # api -> expire
FAIL_TTL = 300            # sec

def blacklisted(api):
    return FAIL_CACHE.get(api, 0) > time.time()

def mark_fail(api):
    FAIL_CACHE[api] = time.time() + FAIL_TTL

def mark_success(video_id, api):
    SUCCESS_CACHE[video_id] = api

# ===============================
# UTILS
# ===============================
def try_json(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def is_video(f): return str(f.get("type","")).startswith("video")
def is_audio(f): return str(f.get("type","")).startswith("audio")

# ===============================
# STREAM URL DIRECT
# ===============================
def try_direct(video_id):
    for base in STREAM_APIS:
        if blacklisted(base):
            continue
        data = try_json(base + video_id)
        if data and data.get("url"):
            mark_success(video_id, base)
            return data["url"]
        mark_fail(base)
    return None

# ===============================
# MSE API
# ===============================
@app.get("/api/mse")
def api_mse(video_id: str):
    direct = try_direct(video_id)
    if direct:
        return {"mode": "direct", "url": direct}

    random.shuffle(VIDEO_APIS)

    for base in VIDEO_APIS:
        if blacklisted(base):
            continue

        data = try_json(f"{base}/api/v1/videos/{video_id}")
        if not data:
            mark_fail(base)
            continue

        fmts = data.get("adaptiveFormats", [])
        videos = [f for f in fmts if is_video(f)]
        audios = [f for f in fmts if is_audio(f)]

        if not videos or not audios:
            mark_fail(base)
            continue

        videos.sort(key=lambda x:(x.get("height",0),x.get("fps",0)), reverse=True)
        audios.sort(key=lambda x:x.get("bitrate",0), reverse=True)

        mark_success(video_id, base)
        return {
            "mode": "mse",
            "video": videos[0]["url"],
            "audio": audios[0]["url"]
        }

    raise HTTPException(503)

# ===============================
# ROOT HTML (PLAYER)
# ===============================
@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MSE Player</title>
<style>
body{background:#000;color:#fff;font-family:sans-serif;text-align:center}
video{width:90%;max-width:960px;margin-top:20px;background:#000}
#error{color:#f55;margin-top:10px}
button{padding:8px 16px;font-size:16px}
</style>
</head>
<body>

<h2>MSE Player</h2>
<input id="vid" placeholder="YouTube videoId">
<button onclick="start()">再生</button>

<video id="v" controls></video>
<div id="error"></div>

<script>
const video = document.getElementById("v");
const errorBox = document.getElementById("error");
let currentId = null;

function show(msg){
  errorBox.textContent = msg;
}

async function start(){
  currentId = document.getElementById("vid").value.trim();
  if(!currentId) return;
  play(currentId);
}

async function play(id){
  show("");
  video.pause();
  video.removeAttribute("src");
  video.load();

  let res = await fetch("/api/mse?video_id="+id);
  if(!res.ok){
    show("取得失敗");
    return;
  }
  let info = await res.json();

  if(info.mode === "direct"){
    video.src = info.url;
    video.play().catch(()=>show("再生失敗"));
    return;
  }

  const ms = new MediaSource();
  video.src = URL.createObjectURL(ms);

  ms.addEventListener("sourceopen", async ()=>{
    const ab = ms.addSourceBuffer('audio/mp4; codecs="mp4a.40.2"');
    const vb = ms.addSourceBuffer('video/mp4; codecs="avc1.64001f"');

    try{
      // 🔊 audio first
      const a = await fetch(info.audio).then(r=>r.arrayBuffer());
      ab.appendBuffer(a);
    }catch{
      show("音声取得失敗");
      return;
    }

    ab.addEventListener("updateend", async ()=>{
      video.play().catch(()=>{});
      try{
        // 🎥 video later
        const v = await fetch(info.video).then(r=>r.arrayBuffer());
        vb.appendBuffer(v);
      }catch{
        show("映像取得失敗");
      }

      vb.addEventListener("updateend", ()=>{
        try{ ms.endOfStream(); }catch{}
      }, {once:true});
    }, {once:true});
  });
}

// URL 期限切れ対策
video.onerror = ()=>{
  show("再接続中…");
  if(currentId){
    setTimeout(()=>play(currentId), 1000);
  }
};
</script>

</body>
</html>
"""
