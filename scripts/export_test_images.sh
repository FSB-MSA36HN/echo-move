#!/usr/bin/env bash
# Export still JPG from curated fall clips + keep Unsplash worker photos.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CUR="$ROOT/data/test_videos/curated"
IMG="$ROOT/data/test_images"
FALL="${FALL:-$ROOT/data/test_videos/fall.mp4}"
mkdir -p "$IMG"

need() { [[ -f "$1" ]] || { echo "missing $1 — run scripts/download_test_videos.sh first"; exit 1; }; }
need "$CUR/01_fall.mp4"

ffmpeg -y -hide_banner -loglevel error -ss 4.5 -i "$CUR/01_fall.mp4" -frames:v 1 -q:v 2 "$IMG/01_fall_lying.jpg"
ffmpeg -y -hide_banner -loglevel error -ss 3.5 -i "$CUR/01_fall.mp4" -frames:v 1 -q:v 2 "$IMG/01_fall_mid.jpg"
if [[ -f "$FALL" ]]; then
  ffmpeg -y -hide_banner -loglevel error -ss 3 -i "$FALL" -frames:v 1 -q:v 2 "$IMG/01b_fall_lying.jpg"
  ffmpeg -y -hide_banner -loglevel error -ss 5 -i "$FALL" -frames:v 1 -q:v 2 "$IMG/01c_fall_motion.jpg"
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
INTEL=https://github.com/intel-iot-devkit/sample-videos/raw/master
curl -fsSL --retry 3 -L -o "$tmp/hallway.mp4" "$INTEL/face-demographics-walking.mp4"
curl -fsSL --retry 3 -L -o "$tmp/street.mp4" "$INTEL/person-bicycle-car-detection.mp4"
ffmpeg -y -hide_banner -loglevel error -ss 3 -i "$tmp/hallway.mp4" \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -frames:v 1 -q:v 2 "$IMG/06_hallway_person.jpg"
ffmpeg -y -hide_banner -loglevel error -ss 6 -i "$tmp/street.mp4" \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -frames:v 1 -q:v 2 "$IMG/06b_parking_person.jpg"

# Unsplash (free) — multi workers
[[ -f "$IMG/workers_construction.jpg" ]] || curl -fsSL --retry 3 -L -o "$IMG/workers_construction.jpg" \
  "https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=1280&q=80"
[[ -f "$IMG/workers_site_team.jpg" ]] || curl -fsSL --retry 3 -L -o "$IMG/workers_site_team.jpg" \
  "https://images.unsplash.com/photo-1541888946425-d81bb19240f5?w=1280&q=80"

echo "OK → $IMG"
ls -lh "$IMG"
