FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/
COPY backend/src backend/src
# Set ECHO_WITH_AI=1 at build time to include YOLO/MediaPipe (large image).
ARG ECHO_WITH_AI=0
RUN pip install --no-cache-dir ./backend && \
    if [ "$ECHO_WITH_AI" = "1" ]; then pip install --no-cache-dir "ultralytics>=8.1" "mediapipe>=0.10" --extra-index-url https://download.pytorch.org/whl/cpu; fi
ENV ECHO_MATLAB_DIR=/data/output
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health')" || exit 1
CMD ["python", "-m", "echo_move"]
