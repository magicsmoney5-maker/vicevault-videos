#!/usr/bin/env python3
"""Vice Vault short renderer (footage-led format, matching the 13 Nov posts).

render.py spec.json
Spec keys: id, out, voice, music, credit, hook{title,tag}, end{text,tag}, highlights[], fixups{}, scenes[]
Each scene: label (or ""), at (seconds into the voice where the scene starts), layout full|window,
x (0..1 crop position for full), shots [{src, in, len}].
"""
import json, os, re, subprocess, sys, math

FOOT = os.environ.get("VVC_FOOT", os.path.expanduser("~/foot"))
W, H, FPS = 1080, 1920, 30
YEL = "&H001FD2FF"  # #FFD21F in ASS BGR
# letterboxed sources: trim the baked-in black bars before scaling
PRECROP = {"t2": "crop=3840:1728:0:216,", "launch": "crop=3840:1920:0:120,"}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr[-3000:])
        raise SystemExit("ffmpeg failed: " + " ".join(cmd[:6]))
    return r


def dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip())


def transcribe(voice):
    cache = voice + ".words.json"
    if os.path.exists(cache):
        return json.load(open(cache))
    import numpy as np
    from faster_whisper import WhisperModel
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", voice, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    m = WhisperModel("small.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(np.frombuffer(pcm, np.float32), word_timestamps=True, beam_size=5)
    words = [[round(w.start, 3), round(w.end, 3), w.word.strip()] for s in segs for w in s.words]
    json.dump(words, open(cache, "w"))
    return words


def ass_time(t):
    t = max(0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def esc_ass(s):
    return s.replace("{", "(").replace("}", ")")


def chunks(words, fixups):
    """Group words into caption chunks of up to 3 words, breaking after punctuation."""
    out, cur = [], []
    merged = []
    for w in words:  # glue split tokens ("pre" + "-loading", "79" + ".99") back onto the previous word
        if merged and re.match(r"^[-.]\w", w[2]):
            merged[-1] = [merged[-1][0], w[1], merged[-1][2] + w[2]]
        else:
            merged.append(list(w))
    words = merged
    for w in words:
        cur.append(w)
        end_punct = re.search(r"[.,?!:;]$", w[2])
        if len(cur) >= 3 or end_punct:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    res = []
    for i, c in enumerate(out):
        text = " ".join(x[2] for x in c)
        for a, b in fixups.items():
            text = re.sub(a, b, text, flags=re.I)
        text = re.sub(r"[.,!;:](?=\s|$)", "", text).strip().upper()  # keep inner dots such as $79.99
        start = c[0][0]
        nxt = out[i + 1][0][0] if i + 1 < len(out) else c[-1][1] + 0.4
        end = min(nxt, c[-1][1] + 0.6)
        res.append((start, end, text))
    return res


def build_ass(spec, words, total, scene_times):
    hl = [h.upper() for h in spec.get("highlights", [])]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Cap,Anton,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,5,3,5,60,60,0,1",
        "Style: Label,Anton,70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,4,2,5,60,60,0,1",
        "Style: Credit,Inter,26,&H22FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,2,1,5,60,60,0,1",
        "Style: Hook,Anton,118,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,6,4,5,60,60,0,1",
        "Style: Tag,Anton,50,&H00101010,&H00101010," + YEL + ",&H00000000,0,0,0,0,100,100,1,0,3,14,0,5,60,60,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    ev = []
    credit = spec["credit"]
    ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(total)},Credit,,0,0,0,,{{\\pos(540,300)}}{esc_ass(credit)}")
    first_label = next((s for s in scene_times if s["label"]), None)
    hook_end = first_label["start"] if first_label else min(3.0, total)
    hk = spec["hook"]
    ev.append(f"Dialogue: 2,{ass_time(0)},{ass_time(hook_end)},Hook,,0,0,0,,{{\\pos(540,860)\\fad(0,150)}}{esc_ass(hk['title'])}")
    ev.append(f"Dialogue: 2,{ass_time(0)},{ass_time(hook_end)},Tag,,0,0,0,,{{\\pos(540,1012)\\fad(0,150)}}{esc_ass(hk['tag'])}")
    for s in scene_times:
        if s["label"]:
            ev.append(f"Dialogue: 1,{ass_time(s['start'])},{ass_time(s['end'])},Label,,0,0,0,,{{\\pos(540,215)\\fad(120,0)}}{esc_ass(s['label'])}")
    en = spec["end"]
    end_start = scene_times[-1]["start"]
    ev.append(f"Dialogue: 2,{ass_time(end_start)},{ass_time(total)},Hook,,0,0,0,,{{\\pos(540,830)\\fs96\\fad(150,0)}}{esc_ass(en['text'])}")
    ev.append(f"Dialogue: 2,{ass_time(end_start)},{ass_time(total)},Tag,,0,0,0,,{{\\pos(540,1012)\\fad(150,0)}}{esc_ass(en['tag'])}")
    for (a, b, text) in chunks(words, spec.get("fixups", {})):
        parts = []
        for tok in text.split():
            key = re.sub(r"[^A-Z0-9']", "", tok)
            if any(key == h or key.startswith(h) for h in hl):
                parts.append("{\\c" + YEL + "&}" + tok + "{\\c&H00FFFFFF&}")
            else:
                parts.append(tok)
        ev.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,{{\\pos(540,1440)}}{' '.join(parts)}")
    return "\n".join(lines + ev) + "\n"


def render_scene(i, sc, length, work):
    """Render one scene to an intermediate 1080x1920 clip of exactly `length` seconds."""
    shots = sc["shots"]
    total_src = sum(s["len"] for s in shots)
    speed = min(1.0, total_src / length) if total_src < length else 1.0  # <1 means slow down
    parts = []
    for j, s in enumerate(shots):
        p = f"{work}/s{i:02d}_{j}.mp4"
        src = os.path.join(FOOT, s["src"] + ".mp4")
        need = min(s["len"], length * speed) if len(shots) == 1 else s["len"]
        x = s.get("x", sc.get("x", 0.5))
        layout = s.get("layout", sc.get("layout", "full"))
        pc = PRECROP.get(s["src"], "")
        if layout == "full":
            vf = (f"{pc}scale=-2:{H}:flags=bicubic,crop={W}:{H}:(iw-{W})*{x}:0,fps={FPS},setsar=1")
        else:
            vf = (f"{pc}split[a][b];[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=14:2,eq=brightness=-0.12:saturation=1.1,scale={W}:{H},setsar=1[bg];"
                  f"[b]scale={W}:-2:flags=bicubic[fg];[bg][fg]overlay=0:{sc.get('wy', 560)},fps={FPS},setsar=1")
        if s.get("still"):
            png = f"{work}/s{i:02d}_{j}.png"
            run(["ffmpeg", "-v", "error", "-y", "-ss", str(s["in"]), "-i", src, "-frames:v", "1"] + (["-vf", pc.rstrip(",")] if pc else []) + [png])
            n = int(round(need * FPS)); z = s.get("zoom", 1.12)
            base = (f"scale=-2:{H}:flags=bicubic,crop={W}:{H}:(iw-{W})*{x}:0" if layout == "full" else f"scale={W}:-2")
            vf2 = (f"{base},scale={W*2}:-2,zoompan=z='1+({z}-1)*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H if layout == 'full' else 608}:fps={FPS}")
            if layout != "full":
                vf2 = (f"split[a][b];[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=14:2,eq=brightness=-0.12,scale={W}:{H},loop=loop={n}:size=1,setsar=1[bg];"
                       f"[b]{vf2}[fg];[bg][fg]overlay=0:{sc.get('wy', 560)},setsar=1")
            run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", png, "-filter_complex", vf2, "-frames:v", str(n),
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", p])
            parts.append(p)
            continue
        run(["ffmpeg", "-v", "error", "-y", "-ss", str(s["in"]), "-t", str(need), "-i", src, "-an",
             "-filter_complex" if layout != "full" else "-vf", vf,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", p])
        parts.append(p)
    joined = f"{work}/j{i:02d}.mp4"
    if len(parts) > 1:
        lst = f"{work}/l{i:02d}.txt"
        open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    else:
        joined = parts[0]
    have = dur(joined)
    factor = max(1.0, length / have)
    out = f"{work}/scene{i:02d}.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-vf", f"setpts={factor:.4f}*PTS,fps={FPS},trim=duration={length:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", out])
    return out, factor


def main(path):
    spec = json.load(open(path))
    work = os.path.join(os.environ.get("VVC_WORK", os.path.expanduser("~/vvc-work")), spec["id"])
    os.makedirs(work, exist_ok=True)
    words = transcribe(spec["voice"])
    vdur = dur(spec["voice"])
    lead = spec.get("lead", 0.25)
    total = round(vdur + lead + spec.get("tail", 0.9), 2)
    words = [[a + lead, b + lead, t] for a, b, t in words]
    scenes = spec["scenes"]
    times = []
    for i, sc in enumerate(scenes):
        st = 0.0 if i == 0 else sc["at"] + lead
        en = total if i == len(scenes) - 1 else scenes[i + 1]["at"] + lead
        times.append({"start": round(st, 3), "end": round(en, 3), "label": sc.get("label", "")})
    clips = []
    for i, (sc, tm) in enumerate(zip(scenes, times)):
        c, f = render_scene(i, sc, tm["end"] - tm["start"], work)
        if f > 1.6:
            print(f"warning: scene {i} slowed {f:.2f}x")
        clips.append(c)
    lst = f"{work}/all.txt"
    open(lst, "w").write("".join(f"file '{c}'\n" for c in clips))
    silent = f"{work}/silent.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent])
    ass = f"{work}/captions.ass"
    open(ass, "w").write(build_ass(spec, words, total, times))
    # audio: voice delayed by lead, music ducked under it, then loudness to -14 LUFS
    mus_gain = spec.get("music_gain_db", -17)
    fc = (f"[1:a]adelay={int(lead*1000)}|{int(lead*1000)},apad=whole_dur={total},asplit=2[v][sc];"
          f"[2:a]atrim=0:{total},volume={mus_gain}dB,afade=t=out:st={total-1.2}:d=1.2,"
          f"equalizer=f=2500:t=q:w=1.2:g=-3[m];"
          f"[m][sc]sidechaincompress=threshold=0.03:ratio=4:attack=60:release=450[md];"
          f"[v][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89[mix]")
    pre = f"{work}/premix.wav"
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-i", spec["voice"], "-i", spec["music"],
         "-filter_complex", fc, "-map", "[mix]", "-t", str(total), "-ar", "48000", "-ac", "2", pre])
    r = run(["ffmpeg", "-v", "info", "-y", "-i", pre, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    js = json.loads(r.stderr[r.stderr.rfind("{"):])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
          f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")
    ass_path = ass.replace(":", "\\:")
    run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", pre, "-filter_complex",
         f"[0:v]ass='{ass_path}':fontsdir={os.path.expanduser('~/.fonts')}[v];[1:a]{ln},aresample=48000[a]", "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(total), spec["out"]])
    print("wrote", spec["out"], total, "s")


if __name__ == "__main__":
    main(sys.argv[1])
