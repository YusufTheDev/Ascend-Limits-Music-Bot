#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Create bin folder if not exists
mkdir -p bin

# Download FFmpeg if missing
if [ ! -f bin/ffmpeg ]; then
    echo "Downloading FFmpeg..."
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
    tar xvf ffmpeg-release-amd64-static.tar.xz
    # Move binaries to bin/
    mv ffmpeg-*-amd64-static/ffmpeg bin/ffmpeg
    mv ffmpeg-*-amd64-static/ffprobe bin/ffprobe
    # Clean up
    rm -rf ffmpeg-release-amd64-static.tar.xz ffmpeg-*-amd64-static
    chmod +x bin/ffmpeg bin/ffprobe
    echo "FFmpeg installed to bin/"
fi
