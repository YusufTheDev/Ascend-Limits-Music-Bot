# FlaviBot-style Music Bot


A Discord music bot inspired by FlaviBot, with core music features and simple filters (nightcore, daycore, vaporwave).


## Features


- Play from YouTube or Spotify (tracks and playlists)
- Queue management: add, skip, clear, shuffle, loop
- Now playing info
- Simple filters: **nightcore**, **daycore**, **vaporwave**
- Disconnect/stop command


## Setup


1. Clone repo and create a virtual environment:


```bash
python -m venv venv
source venv/bin/activate
```


2. Install dependencies:

```bash
pip install -r requirements.txt
```
3. Copy to .env.example to .env and fill in your credentials.

4. Run the bot:
```bash
./run.sh
```

## Requirements
* Python 3.9+
* FFmpeg installed and available in PATH