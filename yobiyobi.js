import express from "express";
import ytdl from "@distube/ytdl-core";

/* =========================
   追加：外部APIエンドポイント群
   （※ 現在は未使用、将来用）
========================= */

// APIエンドポイント、全部アカウント変えて作ってる
const API_URLS = [
  "https://script.google.com/macros/s/AKfycbzqpav7y2x3q756wRSOhBzaXf-2hKaLTvxoFN8kFegrIvamH03ZXphEw2PK30L7AstC/exec",
  "https://script.google.com/macros/s/AKfycbyXCS6JsBglbqlW0eIOWpVscTdNA8QUISRaGMJUAiMlYfp4Ju-Avkw1ai3A6P_ek-FK/exec",
  "https://script.google.com/macros/s/AKfycby5bmMQBShFOv_inDOo9jUjwxjdF6PeIh8spKAncj0-h5idAHYodOy-jj9YZStcYa-L/exec",
  "https://script.google.com/macros/s/AKfycbw5Cci8LSWChLvGf17uNW5cZDqESr0XFuI3QNZDRsdn5su1K4VzTfB0oq7SKNXzimT1Aw/exec",
  "https://script.google.com/macros/s/AKfycbwJFbZ4CHnuvy8rppZLfbWWuOHMqaM89nlsv7gThIzW_x0Bn2cj7IJU6XHC5CHG2B-yqQ/exec",
  "https://script.google.com/macros/s/AKfycbzYHLmomiijxiaNGcdLY_ddDZIi3QTK408EQDEpsa82FtIt4VTGRuC8ovZxM7kUSrC2/exec",
  "https://script.google.com/macros/s/AKfycbygQyKvfPnMvY8sdOkKow6NzO91dBhQFy0Vex3qVq1tWnqKodNbFVKQhALWWBLXcRTF/exec",
  "https://script.google.com/macros/s/AKfycbyh11OPhy_xaZOPVz3uKVFy8qdN05hVRrpKrNXuIeogsTLwiQQYBUhKZMniStVhg7QF-A/exec",
  "https://script.google.com/macros/s/AKfycbyjbFpmnhvs0BSorjNuIoZkIOsiH7OsovlYkl3DBI9SA3_19jOBqjr999WA_12HYxhT0A/exec"
];

// ランダムに1つ返す関数
export function apiurl() {
  const index = Math.floor(Math.random() * API_URLS.length);
  return API_URLS[index];
}

/* =========================
   ここから下は既存コード
   （一切変更なし）
========================= */

const router = express.Router();

/* iOS判定 */
function isIOS(req) {
  const ua = req.headers["user-agent"] || "";
  return /iPad|iPhone|iPod/.test(ua);
}

/* VideoID検証 */
function validateYouTubeId(id) {
  return /^[\w-]{11}$/.test(id);
}

/**
 * yobiyobi : 最終フォールバック高画質ストリーム
 * URL: /api/streamurl/yobiyobi?video_id=xxxx
 */
router.get("/", async (req, res) => {
  const videoId = req.query.video_id;

  if (!validateYouTubeId(videoId)) {
    return res.status(400).send("invalid video id");
  }

  try {
    const info = await ytdl.getInfo(videoId);
    const formats = info.formats;

    /* =========================
       iOS / Safari → m3u8
    ========================= */
    if (isIOS(req)) {
      const hls = formats
        .filter(f =>
          f.isHLS &&
          f.mimeType?.includes("mp4") &&
          f.qualityLabel
        )
        .sort((a, b) => parseInt(b.qualityLabel) - parseInt(a.qualityLabel))[0];

      if (!hls) throw new Error("HLS not found");

      res.redirect(hls.url);
      return;
    }

    /* =========================
       非iOS → 最高画質 m3u8 優先
    ========================= */
    const hlsBest = formats
      .filter(f =>
        f.isHLS &&
        f.mimeType?.includes("mp4") &&
        f.qualityLabel
      )
      .sort((a, b) => parseInt(b.qualityLabel) - parseInt(a.qualityLabel))[0];

    if (hlsBest) {
      res.redirect(hlsBest.url);
      return;
    }

    /* =========================
       m3u8が無い → DASH fallback
    ========================= */

    const videoOnly = formats
      .filter(f =>
        f.hasVideo &&
        !f.hasAudio &&
        f.container === "mp4" &&
        f.qualityLabel
      )
      .sort((a, b) => parseInt(b.qualityLabel) - parseInt(a.qualityLabel))[0];

    const audioOnly = ytdl.chooseFormat(formats, {
      quality: "highestaudio",
      filter: "audioonly"
    });

    if (!videoOnly || !audioOnly) {
      throw new Error("DASH formats not found");
    }

    res.json({
      dash: {
        videos: {
          [videoOnly.qualityLabel.replace("p", "")]: {
            url: videoOnly.url,
            codecs: videoOnly.codecs
          }
        },
        audio: {
          url: audioOnly.url,
          codecs: audioOnly.codecs
        }
      }
    });

  } catch (err) {
    console.error("yobiyobi error:", err);
    res.status(500).send("stream error");
  }
});

export default router;
