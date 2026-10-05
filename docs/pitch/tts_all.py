import json, soundfile as sf, sys
from kokoro_onnx import Kokoro
k = Kokoro("kokoro.onnx", "voices.bin")
for i, t in enumerate(json.load(open("narration.json")), 1):
    s, sr = k.create(t, voice="am_michael", speed=1.0, lang="en-us")
    sf.write(f"a{i:02d}.wav", s, sr); print(i, round(len(s)/sr,1), flush=True)
