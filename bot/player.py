import discord
import asyncio
import yt_dlp
import spotipy
import os
from spotipy.oauth2 import SpotifyClientCredentials

SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")

# Keep ffmpeg simple; filters are added later
FFMPEG_BASE_BEFORE = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin'
FFMPEG_BASE_OPTIONS = '-vn'

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET
))


class YTDLSource(discord.PCMVolumeTransformer):
    ytdl = yt_dlp.YoutubeDL({
        'format': 'bestaudio/best',
        'quiet': True,
        'default_search': 'ytsearch',
        'noplaylist': True
    })

    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, filters=None, start_time=None):
        """
        Streams the URL (download=False) and returns a YTDLSource wrapping
        an FFmpegPCMAudio built from the direct URL. This avoids local downloads
        and makes ffmpeg handle the stream directly.
        """
        loop = loop or asyncio.get_event_loop()

        # Use download=False to get a direct stream URL from yt-dlp
        try:
            data = await loop.run_in_executor(None, lambda: cls.ytdl.extract_info(url, download=False))
        except Exception as e:
            raise RuntimeError(f"yt-dlp extract_info failed: {e}")

        if not data:
            raise RuntimeError("yt-dlp returned no data.")

        if 'entries' in data:
            data = data['entries'][0]

        # data should contain a 'url' field we can pass to ffmpeg
        stream_url = data.get('url')
        if not stream_url:
            raise RuntimeError("No playable URL found in yt-dlp data.")

        # build ffmpeg options; append -af when filters are present
        before = FFMPEG_BASE_BEFORE
        options = FFMPEG_BASE_OPTIONS
        if start_time:
            before = f"{before} -ss {start_time}"
        if filters:
            # careful with quoting — pass the whole -af as part of options
            # e.g. -af "asetrate=...,aresample=...,atempo=..."
            options = f'{options} -af "{filters}"'

        ffmpeg_kwargs = {
            'before_options': before,
            'options': options
        }

        source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_kwargs)
        return cls(source, data=data)


class GuildMusic:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.queue = []               # list of (query, filters) where query can be url or search
        self.history = []             # optional: record of played songs (not used heavily here)
        self.current = None           # (query, filters)
        self.loop_song = False
        self.loop_queue = False
        self.autoplay = False
        self.global_filter = None     # If set, applied to songs that don't have their own filter
        self.force_filter = None      # Temporary flag: next play should replay current with this filter
        self.replaying = False


    async def add_song(self, query, *, filters=None):
        # resolve spotify track -> text search if necessary
        if "spotify.com" in query:
            try:
                if "track" in query:
                    track = sp.track(query)
                    query = f"{track['artists'][0]['name']} {track['name']}"
                elif "playlist" in query:
                    offset = 0
                    count = 0
                    while True:
                        playlist = sp.playlist_items(query, offset=offset, limit=100)
                        if not playlist['items']:
                            break
                        for item in playlist['items']:
                            track = item.get('track')
                            if not track:
                                continue
                            try:
                                track_query = f"{track['artists'][0]['name']} {track['name']}"
                                self.queue.append((track_query, filters))
                                count += 1
                            except Exception as e:
                                print(f"Skipped a track due to error: {e}")
                        offset += 100
                        if len(playlist['items']) < 100:
                            break
                    print(f"Queued {count} songs from Spotify playlist")
                    return
            except Exception as e:
                print(f"Spotify error: {e}")
                return
        # fallback: just add as a normal query
        self.queue.append((query, filters))


    async def play_next(self, text_channel=None, force_filters=None):
        """
        Play the next song in queue. Sends messages via text_channel instead of interaction
        to avoid Unknown interaction (404).
        """

        filters = None

        # Determine song to play
        if force_filters and self.current:
            query, _ = self.current
            filters = force_filters
            self.current = (query, filters)
        elif self.force_filter and self.current:
            query, _ = self.current
            filters = None if self.force_filter == "RESET_FILTER" else self.force_filter
            self.current = (query, filters)
            self.force_filter = None
        elif self.loop_song and self.current:
            query, filters = self.current
        else:
            if not self.queue:
                if self.loop_queue and self.current:
                    query, filters = self.current
                else:
                    self.current = None
                    if text_channel:
                        await text_channel.send("Queue is empty.")
                    return
            else:
                query, filters = self.queue.pop(0)
                if self.current and self.loop_queue:
                    self.queue.append(self.current)
                self.current = (query, filters)

        # Active filter: per-song > global
        active_filter = filters if filters is not None else self.global_filter

        # Build audio player
        try:
            player = await YTDLSource.from_url(query, loop=self.bot.loop, filters=active_filter)
        except Exception as e:
            if text_channel:
                await text_channel.send(f"❌ Error playing `{query}`: {e}")
            return

        vc = self.guild.voice_client
        if not vc:
            if text_channel:
                await text_channel.send("Bot is not connected to a voice channel.")
            return

        def after_play(error):
            if error:
                print(f"[after_play error] {error}")
            if not self.replaying:
                asyncio.run_coroutine_threadsafe(
                    self.play_next(text_channel=text_channel), self.bot.loop
                )

        # Stop current playback if any
        if vc.is_playing():
            vc.stop()
            await asyncio.sleep(0.2)

        self.replaying = False
        vc.play(player, after=after_play)

        # Send "Now playing" via channel
        if text_channel:
            title = getattr(player, "title", "Unknown")
            filter_display = active_filter if active_filter else "None"
            await text_channel.send(f"🎶 Now playing: **{title}**\nFilter: `{filter_display}`")


    async def stop(self, interaction=None):
        vc = self.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.stop()
            # FFmpeg might still hang; disconnecting will clean it up in most cases

        # Clear everything
        self.queue.clear()
        self.current = None
        self.loop_song = False
        self.loop_queue = False
        self.global_filter = None
        self.force_filter = None
        self.replaying = False
        self._empty_sent = False  # reset empty queue flag

