FROM python:3.11-slim
WORKDIR /app
# OpenCV (headless + ultralytics/mediapipe wheels) needs a few X libs even without a display.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 libxcb1 libx11-6 libxext6 libxrender1 libsm6 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/
COPY backend/src backend/src
# Set ECHO_WITH_AI=1 at build time to include YOLO/MediaPipe (large image).
ARG ECHO_WITH_AI=0
RUN pip install --no-cache-dir ./backend && \
    if [ "$ECHO_WITH_AI" = "1" ]; then \
      pip install --no-cache-dir "ultralytics>=8.1" "mediapipe>=0.10" \
        --extra-index-url https://download.pytorch.org/whl/cpu && \
      pip uninstall -y opencv-python opencv-contrib-python 2>/dev/null || true && \
      pip install --no-cache-dir --force-reinstall "opencv-python-headless>=4.8"; \
    fi
COPY web web
ENV ECHO_MATLAB_DIR=/data/output \
    ECHO_DATA_DIR=/data/output \
    ECHO_WEB_DIR=/app/web
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health')" || exit 1
CMD ["python", "-m", "echo_move"]
