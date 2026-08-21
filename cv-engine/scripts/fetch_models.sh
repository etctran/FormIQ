#!/usr/bin/env bash
# cv-engine/scripts/fetch_models.sh
#
# Downloads MediaPipe's published pose-detector and pose-landmark TFLite
# models into cv-engine/models/. Pinned to MediaPipe's public model asset
# bucket. Idempotent — skips files that already exist so repeated local
# builds don't re-download.
set -euo pipefail

MODELS_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/models}"
mkdir -p "$MODELS_DIR"

fetch() {
  local url="$1" dest="$2"
  if [[ -s "$dest" ]]; then
    echo "already present: $dest"
    return 0
  fi
  echo "fetching $url -> $dest"
  curl -fSL --retry 3 -o "$dest.tmp" "$url"
  mv "$dest.tmp" "$dest"
}

fetch "https://storage.googleapis.com/mediapipe-assets/pose_detection.tflite" \
  "$MODELS_DIR/pose_detection.tflite"
fetch "https://storage.googleapis.com/mediapipe-assets/pose_landmark_lite.tflite" \
  "$MODELS_DIR/pose_landmark_lite.tflite"

echo "models ready in $MODELS_DIR"
