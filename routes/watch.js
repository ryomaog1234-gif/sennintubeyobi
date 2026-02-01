const express = require("express");
const router = express.Router();
const wakame = require("../server/wakame");
const serverYt = require("../server/youtube");

router.get("/:id", async (req,res)=>{
  const id = req.params.id;

  const videoData = await wakame.getYouTube(id);
  const info = await serverYt.infoGet(id);

  res.render("tube/watch.ejs",{
    videoid:id,
    videotitle:info.primary_info.title.text,
    videourls:[videoData.stream_url],
    description:videoData.description,
    author:videoData.author,
    authorid:videoData.authorId,
    authoricon:videoData.authorImage,
    res:[]
  });
});

module.exports = router;
