// On-screen text of rendered frames with macOS Vision (ru + en) through JXA, for broll_qa.py's caption check.
// No compiler needed (a Swift build can fail on CommandLineTools
// "redefinition of module SwiftBridging").
// Usage: osascript -l JavaScript ocr_text.js img1.jpg img2.jpg ...  -> one JSON line per image on stdout:
//   {"img": path, "w": W, "h": H, "lines": [{"text": s, "conf": c, "box": [x, y, w, h] (pixels, origin top-left)}]}
ObjC.import('Foundation');
ObjC.import('AppKit');
ObjC.import('Vision');

function run(argv) {
  const out = [];
  for (const path of argv) {
    const img = $.NSImage.alloc.initWithContentsOfFile(path);
    if (img.isNil()) { out.push(JSON.stringify({img: path, error: 'unreadable'})); continue; }
    const rep = img.representations.objectAtIndex(0);
    const W = rep.pixelsWide, H = rep.pixelsHigh;
    const req = $.VNRecognizeTextRequest.alloc.init;
    req.recognitionLevel = 0;               // accurate
    req.usesLanguageCorrection = false;
    req.recognitionLanguages = $(['ru-RU', 'en-US']);
    req.minimumTextHeight = 0.008;
    const handler = $.VNImageRequestHandler.alloc.initWithURLOptions($.NSURL.fileURLWithPath(path), $({}));
    const ok = handler.performRequestsError($([req]), null);
    if (!ok) { out.push(JSON.stringify({img: path, error: 'vision failed'})); continue; }
    const res = req.results;
    const lines = [];
    for (let i = 0; i < res.count; i++) {
      const obs = res.objectAtIndex(i);
      const cands = obs.topCandidates(1);
      if (cands.count < 1) continue;
      const c = cands.objectAtIndex(0);
      const b = obs.boundingBox;
      lines.push({text: c.string.js, conf: c.confidence,
                  box: [b.origin.x * W, (1 - b.origin.y - b.size.height) * H, b.size.width * W, b.size.height * H]});
    }
    out.push(JSON.stringify({img: path, w: W, h: H, lines: lines}));
  }
  return out.join('\n');
}
