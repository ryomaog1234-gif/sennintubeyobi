import os
import time
import logging
from flask import Flask, jsonify, request, send_from_directory
from omada import OmadaVideoService
import requests
from moviepy.editor import VideoFileClip, AudioFileClip
from tempfile import NamedTemporaryFile

# ===================== 設定 =====================
CACHE_DIR = "cache"
CACHE_TTL = 3600 * 6  # キャッシュ6時間
TARGET_QUALITIES = ["1080p", "720p", "480p", "360p"]  # 高画質優先
INVIDIOUS_SITES = [
    'https://invidious.schenkel.eti.br/',
    'https://invidious.nikkosphere.com/',
    'https://siawaseok-wakame-server2.glitch.me/',
    'https://clover-pitch-position.glitch.me/',
    'https://inv.nadeko.net/',
    'https://iv.duti.dev/',
    'https://yewtu.be/',
    'https://id.420129.xyz/',
    'https://invidious.f5.si/',
    'https://invidious.nerdvpn.de/',
    'https://invidious.tiekoetter.com/',
    'https://lekker.gay/',
    'https://nyc1.iv.ggtyler.dev/',
    'https://iv.ggtyler.dev/',
    'https://invid-api.poketube.fun/',
    'https://iv.melmac.space/',
    'https://cal1.iv.ggtyler.dev/',
    'https://pol1.iv.ggtyler.dev/',
    'https://invidious.lunivers.trade/',
    'https://eu-proxy.poketube.fun/',
    'https://invidious.reallyaweso.me',
    'https://invidious.dhusch.de/',
    'https://usa-proxy2.poketube.fun/',
    'https://invidious.darkness.service/',
    'https://iv.datura.network/',
    'https://invidious.private.coffee/',
    'https://invidious.projectsegfau.lt/',
    'https://invidious.perennialte.ch/',
]

os.makedirs(CACHE_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO)

# ===================== Flask =====================
app = Flask(__name__)
video_service = OmadaVideoService()

# ===================== キャッシュ整理 =====================
def cleanup_cache():
    now = time.time()
    for filename in os.listdir(CACHE_DIR):
        filepath = os.path.join(CACHE_DIR, filename)
        if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > CACHE_TTL:
            logging.info(f"古いキャッシュ削除: {filename}")
            os.remove(filepath)

# ===================== 動画取得・結合 =====================
def download_stream(url, tmp_suffix=".mp4"):
    tmp_file = NamedTemporaryFile(delete=False, suffix=tmp_suffix)
    logging.info(f"ダウンロード: {url}")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=1024*1024):
            if chunk:
                tmp_file.write(chunk)
    tmp_file.close()
    return tmp_file.name

def merge_video_audio(video_url, audio_url, output_path):
    video_file = download_stream(video_url)
    audio_file = download_stream(audio_url)

    logging.info("結合処理開始...")
    video_clip = VideoFileClip(video_file)
    audio_clip = AudioFileClip(audio_file)
    video_clip = video_clip.set_audio(audio_clip)
    video_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
    video_clip.close()
    audio_clip.close()

    os.unlink(video_file)
    os.unlink(audio_file)
    logging.info(f"結合完了: {output_path}")

# ===================== 動画ルート =====================
@app.route("/video/<video_id>")
def get_video(video_id):
    cleanup_cache()
    quality = request.args.get("quality", "1080p")
    filename = f"{video_id}_{quality}.mp4"
    filepath = os.path.join(CACHE_DIR, filename)

    if os.path.exists(filepath):
        logging.info(f"キャッシュ提供: {filename}")
        return send_from_directory(CACHE_DIR, filename, as_attachment=False)

    try:
        backend = request.args.get("backend", "main")

        # yobi.py 専用最適化: main 以外は Omada + 高画質優先
        if backend == "yobi":
            stream_data = video_service.get_stream_urls(video_id, target_qualities=TARGET_QUALITIES)
        else:
            # 他のバックエンドもフェイルオーバーとして取得
            stream_data = video_service.get_stream_urls(video_id)

        if not stream_data:
            return jsonify({"error": "動画取得失敗"}), 404

        streams = stream_data['quality_streams'].get(quality)
        if not streams or not streams.get('video_url') or not streams.get('audio_url'):
            return jsonify({"error": f"{quality}のストリームがありません"}), 404

        merge_video_audio(streams['video_url'], streams['audio_url'], filepath)
        return send_from_directory(CACHE_DIR, filename, as_attachment=False)

    except Exception as e:
        logging.error(f"動画結合エラー: {e}")
        return jsonify({"error": str(e)}), 500

# ===================== 動画メタ情報 =====================
@app.route("/api/streammeta")
def get_stream_meta():
    video_id = request.args.get("video_id")
    backend = request.args.get("backend", "main")
    if not video_id:
        return jsonify({"error": "video_id が必要"}), 400

    try:
        # yobi.py最適化: 高画質優先
        if backend == "yobi":
            stream_data = video_service.get_stream_urls(video_id, target_qualities=TARGET_QUALITIES)
        else:
            stream_data = video_service.get_stream_urls(video_id)

        if not stream_data:
            return jsonify({"error": "動画取得失敗"}), 404

        # 最高画質 URL 優先
        for q in TARGET_QUALITIES:
            info = stream_data['quality_streams'].get(q)
            if info and info.get('combined_url'):
                return jsonify({"url": info['combined_url'], "type": "mp4", "quality": q})

            if info and info.get('video_url') and info.get('audio_url'):
                return jsonify({"url": info['video_url'], "audio_url": info['audio_url'], "type": "mp4", "quality": q})

        return jsonify({"error": "利用可能なストリームなし"}), 404

    except Exception as e:
        logging.error(f"ストリームメタ取得エラー: {e}")
        return jsonify({"error": str(e)}), 500

# ===================== 動画メタ情報簡易 =====================
@app.route("/meta/<video_id>")
def get_meta(video_id):
    try:
        stream_data = video_service.get_stream_urls(video_id, target_qualities=TARGET_QUALITIES)
        if not stream_data:
            return jsonify({"error": "動画取得失敗"}), 404
        return jsonify(stream_data)
    except Exception as e:
        logging.error(f"メタ情報取得エラー: {e}")
        return jsonify({"error": str(e)}), 500

# ===================== サーバ起動 =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
