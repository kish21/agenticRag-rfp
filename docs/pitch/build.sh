#!/usr/bin/env bash
# Rebuilds Meridian_AI_Platform_Pitch.mp4 from deck.html + narration.json.
# Needs: ffmpeg, chromium, `pip install playwright kokoro-onnx soundfile`, plus
# kokoro.onnx + voices.bin from github.com/thewh1teagle/kokoro-onnx/releases (model-files-v1.0) in this folder.
set -euo pipefail
cd "$(dirname "$0")"
python3 tts_all.py          # narration.json -> a01..a11.wav
python3 render.py           # deck.html -> f01..f11/ animation frames
rm -f list.txt
for s in $(seq -w 1 11); do
  D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 a$s.wav)
  T=$(python3 -c "print(round($D+1.5,2))"); FO=$(python3 -c "print(round($T-0.4,2))")
  ffmpeg -loglevel error -y -framerate 30 -i f$s/%04d.jpg -i a$s.wav -filter_complex \
    "[0]tpad=stop_mode=clone:stop_duration=$T,trim=duration=$T,fade=in:st=0:d=0.4,fade=out:st=$FO:d=0.4,format=yuv420p[v];[1]adelay=600|600,apad,atrim=duration=$T,aformat=sample_rates=48000:channel_layouts=stereo[a]" \
    -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 18 -r 30 -c:a aac -b:a 192k seg$s.mp4
  echo "file seg$s.mp4" >> list.txt
done
ffmpeg -loglevel error -y -f concat -safe 0 -i list.txt -c copy -movflags +faststart Meridian_AI_Platform_Pitch.mp4
rm -rf f?? a??.wav seg??.mp4 list.txt
