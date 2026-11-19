#!/usr/bin/env python3
"""Vice Vault "Streamer Moment" renderer (launch-week stream clipping format).

stream_clip.py spec.json

Spec keys:
  id, out, url (Twitch clip / VOD / YouTube link) or file (local mp4),
  start, end            seconds inside the source to keep (optional; default whole clip)
  hook_at               seconds (inside the kept part) of the peak reaction; the video opens on it
  hook_len              how long the cold-open peak plays before rewinding (default 1.6)
  streamer              handle shown on screen and in the credit, e.g. "MeowSparky"
  platform              "Twitch" | "YouTube" | "Kick"
  cam                   facecam box in source pixels [x, y, w, h], or null for no facecam
  game_x                0..1 horizontal crop position for the gameplay panel (default 0.5)
  hook {title, tag}     on-screen hook card for the cold open
  fixups {}             caption regex fixes, highlights []
  context               our own context caption(s): a string, or [[start, end, text], ...] in seconds of the
                        kept clip (after the cold open). REQUIRED for Instagram originality (Owner, 18 Nov 2026)
  captions              false if the stream already burns in its own captions (default true)
  Set game_x so the gameplay crop avoids the stream's own facecam overlay.

Layout: facecam on top (~35%), gameplay below (~65%). No facecam: full-height gameplay crop.
Audio: the streamer's own audio, normalised to -14 LUFS. Captions: the streamer's speech, word timed.
"""
import json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import run, dur, ass_time, esc_ass, chunks, YEL, W, H, FPS  # noqa: E402

CAM_H = 672            # top panel height (35%)
GAME_H = H - CAM_H     # 1248


def fetch(spec, work):
    if spec.get("file"):
        return spec["file"]
    src = f"{work}/source.mp4"
    if not os.path.exists(src):
        cmd = ["yt-dlp", "-q", "-f", "best[height<=1080]/best", "-o", src]
        if spec.get("end") and "clip" not in spec["url"]:
            cmd += ["--download-sections", f"*{spec.get('start', 0)}-{spec['end']}"]
            spec["end"] = spec["end"] - spec.get("start", 0); spec["start"] = 0
        run(cmd + [spec["url"]])
    return src


def transcribe(wav):
    import numpy as np
    from faster_whisper import WhisperModel
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", wav, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    m = WhisperModel("small.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(np.frombuffer(pcm, np.float32), word_timestamps=True, beam_size=5, vad_filter=True)
    return [[round(w.start, 3), round(w.end, 3), w.word.strip()] for s in segs for w in s.words]


def frame_filter(spec, sw, sh):
    gx = spec.get("game_x", 0.5)
    cam = spec.get("cam")
    if cam:
        x, y, w, h = cam
        return (f"[0:v]split[c][g];"
                f"[c]crop={w}:{h}:{x}:{y},scale={W}:{CAM_H}:force_original_aspect_ratio=increase,crop={W}:{CAM_H},setsar=1[top];"
                f"[g]scale=-2:{GAME_H}:flags=bicubic,crop={W}:{GAME_H}:(iw-{W})*{gx}:0,setsar=1[bot];"
                f"[top][bot]vstack,fps={FPS}[v]")
    return f"[0:v]scale=-2:{H}:flags=bicubic,crop={W}:{H}:(iw-{W})*{gx}:0,fps={FPS},setsar=1[v]"


def build_ass(spec, words, total, hook_len):
    hl = [h.upper() for h in spec.get("highlights", [])]
    cap_y = CAM_H + 110 if spec.get("cam") else 1440
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,Anton,{spec.get('caption_size', 104)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,6,3,5,60,60,0,1",
        "Style: Label,Anton,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,4,2,5,60,60,0,1",
        "Style: Hook,Anton,110,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,6,4,5,60,60,0,1",
        "Style: Tag,Anton,50,&H00101010,&H00101010," + YEL + ",&H00000000,0,0,0,0,100,100,1,0,3,14,0,5,60,60,0,1",
        "Style: Ctx,Anton,62,&H00FFFFFF,&H00FFFFFF,&H40000000,&H00000000,0,0,0,0,100,100,1,0,3,18,0,5,90,90,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    ev = []
    plat = spec.get("platform", "Twitch")
    label = f"@{spec['streamer']} · {plat} · GTA 6 Day 1"
    # top label sits low and large so the Instagram header doesn't cover it (Owner rule, 15 Nov)
    ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(total)},Label,,0,0,0,,{{\\pos(540,300)}}{esc_ass(label)}")
    hk = spec["hook"]
    ev.append(f"Dialogue: 2,{ass_time(0)},{ass_time(hook_len)},Hook,,0,0,0,,{{\\pos(540,{CAM_H + 330})\\fad(0,150)}}{esc_ass(hk['title'])}")
    ev.append(f"Dialogue: 2,{ass_time(0)},{ass_time(hook_len)},Tag,,0,0,0,,{{\\pos(540,{CAM_H + 470})\\fad(0,150)}}{esc_ass(hk['tag'])}")
    # context captions: our own commentary explaining the moment (Instagram originality, Owner 18 Nov)
    ctx = spec.get("context") or []
    if isinstance(ctx, str):
        ctx = [[0, total - hook_len, ctx]]
    for a, b, text in ctx:
        ev.append(f"Dialogue: 3,{ass_time(hook_len + a)},{ass_time(min(total, hook_len + b))},Ctx,,0,0,0,,{{\\pos(540,1560)}}{esc_ass(text)}")
    for (a, b, text) in (chunks(words, spec.get("fixups", {})) if spec.get("captions", True) else []):
        parts = []
        for tok in text.split():
            key = re.sub(r"[^A-Z0-9']", "", tok)
            parts.append("{\\c" + YEL + "&}" + tok + "{\\c&H00FFFFFF&}" if any(key == h or key.startswith(h) for h in hl) else tok)
        ev.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,{{\\pos(540,{cap_y})}}{' '.join(parts)}")
    return "\n".join(lines + ev) + "\n"


def main(path):
    spec = json.load(open(path))
    work = os.path.join(os.environ.get("VVC_WORK", os.path.expanduser("~/vvc-work")), spec["id"])
    os.makedirs(work, exist_ok=True)
    src = fetch(spec, work)
    s0 = spec.get("start", 0)
    s1 = spec.get("end") or dur(src)
    hook_at = spec.get("hook_at")
    hook_len = spec.get("hook_len", 1.6) if hook_at is not None else 0
    # segments in source time: cold-open peak, then the full moment from the start
    segs = ([(s0 + hook_at, s0 + hook_at + hook_len)] if hook_len else []) + [(s0, s1)]
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", src], capture_output=True, text=True).stdout.strip().split(",")
    sw, sh = int(probe[0]), int(probe[1])
    parts = []
    for i, (a, b) in enumerate(segs):
        p = f"{work}/seg{i}.mp4"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src,
             "-filter_complex", frame_filter(spec, sw, sh) + ";[0:a]aresample=48000,aformat=channel_layouts=stereo[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
             "-c:a", "pcm_s16le", f"{work}/seg{i}.mkv"])
        parts.append(f"{work}/seg{i}.mkv")
    lst = f"{work}/all.txt"
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    joined = f"{work}/joined.mkv"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    total = round(dur(joined), 2)
    wav = f"{work}/audio.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-vn", "-ac", "2", "-ar", "48000", wav])
    words = transcribe(wav)
    json.dump(words, open(f"{work}/words.json", "w"))
    ass = f"{work}/captions.ass"
    open(ass, "w").write(build_ass(spec, words, total, hook_len))
    r = run(["ffmpeg", "-v", "info", "-y", "-i", wav, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    js = json.loads(r.stderr[r.stderr.rfind("{"):])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
          f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")
    ass_path = ass.replace(":", "\\:")
    run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-filter_complex",
         f"[0:v]ass='{ass_path}':fontsdir={os.path.expanduser('~/.fonts')}[v];[0:a]{ln},aresample=48000[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
         "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", spec["out"]])
    print("wrote", spec["out"], total, "s")


if __name__ == "__main__":
    main(sys.argv[1])
