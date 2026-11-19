#!/usr/bin/env bash
# Download / regenerate data/test_videos for ECHO MOVE posture demos.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/data/test_videos"
UR=https://fenix.ur.edu.pl/~mkepski/ds/data
CDN=https://cdn.jsdelivr.net/gh/namnq/workout-free-videos@v2.0.0/media/video
mkdir -p "$OUT"
cd "$OUT"

dl() {
  local url="$1" dest="$2"
  if [[ -f "$dest" ]]; then echo "skip $dest"; return; fi
  echo "get $dest"
  curl -fsSL --retry 3 -o "$dest" "$url"
}

for id in 01 05 12; do dl "$UR/fall-${id}-cam0.mp4" "fall-${id}-cam0.mp4"; done
for id in 01 04 15 20; do dl "$UR/adl-${id}-cam0.mp4" "adl-${id}-cam0.mp4"; done

cp -f fall-01-cam0.mp4 fall_demo.mp4
cp -f adl-01-cam0.mp4 standing_adl_demo.mp4

ffmpeg -y -hide_banner -loglevel error -i adl-01-cam0.mp4 \
  -vf "crop=iw:ih*0.55:0:0,scale=640:-2" -c:v libx264 -preset fast -crf 23 -an partial_no_legs.mp4
ffmpeg -y -hide_banner -loglevel error -i adl-01-cam0.mp4 \
  -vf "crop=iw:ih*0.55:0:ih*0.45,scale=640:-2" -c:v libx264 -preset fast -crf 23 -an partial_no_face.mp4
ffmpeg -y -hide_banner -loglevel error -i adl-01-cam0.mp4 \
  -vf "crop=iw*0.45:ih:0:0,scale=640:-2" -c:v libx264 -preset fast -crf 23 -an partial_edge.mp4

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL --retry 3 -o "$tmp/squat.mp4" "$CDN/barbell-back-squat.mp4"
curl -fsSL --retry 3 -o "$tmp/stoop.mp4" "$CDN/good-mornings.mp4"
curl -fsSL --retry 3 -o "$tmp/deep.mp4" "$CDN/deep-squat-prying.mp4"
ffmpeg -y -hide_banner -loglevel error -stream_loop 3 -i "$tmp/squat.mp4" -c:v libx264 -preset fast -crf 23 -an -t 12 squat_demo.mp4
ffmpeg -y -hide_banner -loglevel error -stream_loop 3 -i "$tmp/stoop.mp4" -c:v libx264 -preset fast -crf 23 -an -t 12 stoop_demo.mp4
ffmpeg -y -hide_banner -loglevel error -stream_loop 3 -i "$tmp/deep.mp4" -c:v libx264 -preset fast -crf 23 -an -t 12 squat_deep_demo.mp4
ffmpeg -y -hide_banner -loglevel error -stream_loop 2 -i fall-01-cam0.mp4 -c:v libx264 -preset fast -crf 23 -an -t 12 fall_loop.mp4

echo "OK → $OUT"
ls -lh "$OUT"/*.mp4
