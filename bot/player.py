import discord
import asyncio
import yt_dlp
import spotipy
import os
from spotipy.oauth2 import SpotifyClientCredentials

SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")

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
        self.thumbnail = data.get('thumbnail')  # added for embed

    @classmethod
    async def from_url(cls, url, *, loop=None, filters=None, start_time=None):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: cls.ytdl.extract_info(url, download=False))
        except Exception as e:
            raise RuntimeError(f"yt-dlp extract_info failed: {e}")

        if not data:
            raise RuntimeError("yt-dlp returned no data.")

        if 'entries' in data:
            data = data['entries'][0]

        stream_url = data.get('url')
        if not stream_url:
            raise RuntimeError("No playable URL found in yt-dlp data.")

        before = FFMPEG_BASE_BEFORE
        options = FFMPEG_BASE_OPTIONS
        if start_time:
            before = f"{before} -ss {start_time}"
        if filters:
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
        self.queue = []
        self.history = []
        self.current = None
        self.loop_song = False
        self.loop_queue = False
        self.autoplay = False
        self.global_filter = None
        self.force_filter = None
        self.replaying = False
        self.manual_skip = False
        self._empty_sent = False

    async def add_song(self, query, *, filters=None):
        if "spotify.com" in query:
            try:
                if "track" in query:
                    track = sp.track(query)
                    if track and track.get('artists') and track.get('name'):
                        query = f"{track['artists'][0]['name']} {track['name']}"
                    else:
                        print("Skipped invalid Spotify track")
                        return
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
                                if not track.get('artists') or not track.get('name'):
                                    continue
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

        if query:
            self.queue.append((query, filters))

    async def play_next(self, text_channel=None, interaction=None, force_filters=None):
        filters = None

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
                    if not self._empty_sent:
                        self._empty_sent = True
                        if interaction:
                            await interaction.followup.send("Queue is empty.")
                        elif text_channel:
                            await text_channel.send("Queue is empty.")
                    return
            else:
                query, filters = self.queue.pop(0)
                if self.current and self.loop_queue:
                    self.queue.append(self.current)
                self.current = (query, filters)

        active_filter = filters if filters is not None else self.global_filter

        try:
            player = await YTDLSource.from_url(query, loop=self.bot.loop, filters=active_filter)
        except Exception as e:
            msg = f"❌ Error playing `{query}`: {e}"
            if interaction:
                await interaction.followup.send(msg)
            elif text_channel:
                await text_channel.send(msg)
            return

        vc = self.guild.voice_client
        if not vc:
            msg = "Bot is not connected to a voice channel."
            if interaction:
                await interaction.followup.send(msg)
            elif text_channel:
                await text_channel.send(msg)
            return

        def after_play(error):
            if error:
                print(f"[after_play error] {error}")
            if not self.replaying and not self.manual_skip:
                asyncio.run_coroutine_threadsafe(
                    self.play_next(text_channel=text_channel, interaction=interaction),
                    self.bot.loop
                )

        if vc.is_playing():
            vc.stop()
            await asyncio.sleep(0.2)

        self.replaying = False
        vc.play(player, after=after_play)

        # Now Playing Embed
        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"**{player.title}**",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Filter", value=active_filter or "None", inline=True)
        if getattr(player, "thumbnail", None):
            embed.set_thumbnail(url=player.thumbnail)
        if text_channel:
            await text_channel.send(embed=embed)

    async def stop(self, interaction=None):
        vc = self.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
        self.queue.clear()
        self.current = None
        self.loop_song = False
        self.loop_queue = False
        self.global_filter = None
        self.force_filter = None
        self.replaying = False
        self._empty_sent = False
