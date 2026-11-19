#!/usr/bin/env bash
# Build data/test_videos + curated/ — single-view RGB only (no depth|RGB split).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/data/test_videos"
CUR="$OUT/curated"
UR=https://fenix.ur.edu.pl/~mkepski/ds/data
CDN=https://cdn.jsdelivr.net/gh/namnq/workout-free-videos@v2.0.0/media/video
INTEL=https://github.com/intel-iot-devkit/sample-videos/raw/master
mkdir -p "$OUT" "$CUR"
cd "$OUT"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

dl() {
  local url="$1" dest="$2"
  if [[ -f "$dest" ]]; then echo "skip $dest"; return; fi
  echo "get $dest"
  curl -fsSL --retry 3 -L -o "$dest" "$url"
}

rgb_from_ur() {
  # UR Fall mp4 is 640x240 = depth | RGB side-by-side → keep right half only.
  local src="$1" dest="$2"
  ffmpeg -y -hide_banner -loglevel error -i "$src" \
    -vf "crop=iw/2:ih:iw/2:0,scale=1280:720:flags=lanczos,setsar=1" \
    -c:v libx264 -preset fast -crf 20 -an "$dest"
}

echo "== UR Fall (raw then RGB crop) =="
for id in 01 05 12; do
  dl "$UR/fall-${id}-cam0.mp4" "$tmp/fall-${id}-cam0.mp4"
  rgb_from_ur "$tmp/fall-${id}-cam0.mp4" "$tmp/fall-${id}-rgb.mp4"
done
for id in 01 04 15 20; do
  dl "$UR/adl-${id}-cam0.mp4" "$tmp/adl-${id}-cam0.mp4"
  rgb_from_ur "$tmp/adl-${id}-cam0.mp4" "$tmp/adl-${id}-rgb.mp4"
done

ffmpeg -y -hide_banner -loglevel error -stream_loop 2 -i "$tmp/fall-01-rgb.mp4" \
  -c:v libx264 -preset fast -crf 20 -an -t 14 fall_demo.mp4
ffmpeg -y -hide_banner -loglevel error -stream_loop 2 -i "$tmp/fall-05-rgb.mp4" \
  -c:v libx264 -preset fast -crf 20 -an -t 14 fall_alt.mp4
ffmpeg -y -hide_banner -loglevel error -stream_loop 2 -i "$tmp/fall-12-rgb.mp4" \
  -c:v libx264 -preset fast -crf 20 -an -t 14 fall_loop.mp4
ffmpeg -y -hide_banner -loglevel error -stream_loop 2 -i "$tmp/adl-01-rgb.mp4" \
  -c:v libx264 -preset fast -crf 20 -an -t 12 standing_demo.mp4
cp -f "$tmp/fall-01-rgb.mp4" fall-01-rgb.mp4
cp -f "$tmp/fall-05-rgb.mp4" fall-05-rgb.mp4
cp -f "$tmp/fall-12-rgb.mp4" fall-12-rgb.mp4
cp -f "$tmp/adl-15-rgb.mp4" adl-15-rgb.mp4
cp -f "$tmp/adl-20-rgb.mp4" adl-20-rgb.mp4

echo "== PARTIAL crops =="
ffmpeg -y -hide_banner -loglevel error -i standing_demo.mp4 \
  -vf "crop=iw:ih*0.42:0:0" -c:v libx264 -preset fast -crf 20 -an partial_no_legs.mp4
ffmpeg -y -hide_banner -loglevel error -i standing_demo.mp4 \
  -vf "crop=iw:ih*0.55:0:ih*0.45" -c:v libx264 -preset fast -crf 20 -an partial_no_face.mp4
ffmpeg -y -hide_banner -loglevel error -i standing_demo.mp4 \
  -vf "crop=iw*0.48:ih:0:0" -c:v libx264 -preset fast -crf 20 -an partial_edge.mp4

echo "== Squat / Stoop (CC0 gym, single view) =="
curl -fsSL --retry 3 -o "$tmp/squat.mp4" "$CDN/barbell-back-squat.mp4"
curl -fsSL --retry 3 -o "$tmp/stoop.mp4" "$CDN/good-mornings.mp4"
curl -fsSL --retry 3 -o "$tmp/deep.mp4" "$CDN/deep-squat-prying.mp4"
ffmpeg -y -hide_banner -loglevel error -stream_loop 3 -i "$tmp/squat.mp4" \
  -c:v libx264 -preset fast -crf 20 -an -t 12 squat_demo.mp4
ffmpeg -y -hide_banner -loglevel error -stream_loop 3 -i "$tmp/stoop.mp4" \
  -c:v libx264 -preset fast -crf 20 -an -t 12 stoop_demo.mp4
ffmpeg -y -hide_banner -loglevel error -stream_loop 3 -i "$tmp/deep.mp4" \
  -c:v libx264 -preset fast -crf 20 -an -t 12 squat_deep_demo.mp4

echo "== Multi-person (Intel samples) =="
dl "$INTEL/people-detection.mp4" "$tmp/people-detection.mp4"
dl "$INTEL/face-demographics-walking.mp4" "$tmp/hallway.mp4"
dl "$INTEL/person-bicycle-car-detection.mp4" "$tmp/street.mp4"
ffmpeg -y -hide_banner -loglevel error -i "$tmp/people-detection.mp4" \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -preset fast -crf 20 -an -t 20 multiperson_crowd.mp4
ffmpeg -y -hide_banner -loglevel error -i "$tmp/hallway.mp4" \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -preset fast -crf 20 -an -t 20 multiperson_hallway.mp4
ffmpeg -y -hide_banner -loglevel error -i "$tmp/street.mp4" \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -preset fast -crf 20 -an -t 25 multiperson_street.mp4
cp -f multiperson_crowd.mp4 multiperson_demo.mp4

ffmpeg -y -hide_banner -loglevel error \
  -i multiperson_hallway.mp4 -i fall_demo.mp4 \
  -filter_complex "[0:v]fps=20,scale=1280:720,setsar=1,trim=0:8,setpts=PTS-STARTPTS[a];
                   [1:v]fps=20,scale=1280:720,setsar=1,trim=0:10,setpts=PTS-STARTPTS[b];
                   [a][b]concat=n=2:v=1:a=0[v]" \
  -map "[v]" -c:v libx264 -preset fast -crf 20 multiperson_then_fall.mp4

echo "== curated/ =="
cp -f fall_demo.mp4 "$CUR/01_fall.mp4"
cp -f fall_alt.mp4 "$CUR/01b_fall_alt.mp4"
cp -f standing_demo.mp4 "$CUR/02_standing.mp4"
cp -f squat_demo.mp4 "$CUR/03_squat.mp4"
cp -f stoop_demo.mp4 "$CUR/04_stoop.mp4"
cp -f partial_no_legs.mp4 "$CUR/05_partial_no_legs.mp4"
cp -f partial_no_face.mp4 "$CUR/05b_partial_no_face.mp4"
cp -f partial_edge.mp4 "$CUR/05c_partial_edge.mp4"
cp -f multiperson_hallway.mp4 "$CUR/06_multiperson_hallway.mp4"
cp -f multiperson_street.mp4 "$CUR/06b_multiperson_street.mp4"
cp -f multiperson_crowd.mp4 "$CUR/06c_multiperson_room.mp4"
cp -f multiperson_then_fall.mp4 "$CUR/07_multiperson_then_fall.mp4"

# Do not leave split depth|RGB files in OUT
rm -f "$OUT"/*-cam0.mp4 "$OUT"/*_DEPTH_RGB_SPLIT.mp4 2>/dev/null || true

echo "OK → $CUR"
ls -lh "$CUR"
