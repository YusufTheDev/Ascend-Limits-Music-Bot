import discord
import asyncio
from discord.ext import commands, tasks
from bot.player import GuildMusic

MAX_QUEUE_PAGE = 10  # number of songs per embed page


class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_instances = {}  # Store GuildMusic per guild

    def get_music(self, guild):
        if guild.id not in self.music_instances:
            self.music_instances[guild.id] = GuildMusic(self.bot, guild)
        return self.music_instances[guild.id]

    async def join_vc(self, interaction):
        """Join the user's voice channel if not already."""
        if interaction.user.voice and interaction.user.voice.channel:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(channel)
            else:
                await channel.connect()
            return True
        else:
            await interaction.response.send_message(
                "You must be in a voice channel.", ephemeral=True
            )
            return False

    @discord.app_commands.command(name="play", description="Play a song")
    async def play_slash(self, interaction: discord.Interaction, query: str):
        music = self.get_music(interaction.guild)

        if not await self.join_vc(interaction):
            return

        await interaction.response.send_message(f"✅ Queuing: {query}")

        # Queue songs asynchronously
        asyncio.create_task(music.add_song(query))

        vc = interaction.guild.voice_client
        if vc is None or not vc.is_playing():
            asyncio.create_task(music.play_next(text_channel=interaction.channel))

    @discord.app_commands.command(name="skip", description="Skip the current song")
    async def skip_slash(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Skipped current song.")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @discord.app_commands.command(
        name="skipto", description="Skip to a specific index in the queue"
    )
    async def skipto_slash(self, interaction: discord.Interaction, index: int):
        music = self.get_music(interaction.guild)
        vc = interaction.guild.voice_client

        await interaction.response.defer(thinking=True)

        if not music.queue and not music.current:
            await interaction.followup.send("Nothing is in the queue.", ephemeral=True)
            return

        if music.loop_song:
            if vc and vc.is_playing():
                vc.stop()
            await interaction.followup.send(
                "Looping current song; skipto ignored.", ephemeral=True
            )
            return

        if index < 1 or index > len(music.queue):
            await interaction.followup.send(
                f"Invalid index. Queue has {len(music.queue)} song(s).", ephemeral=True
            )
            return

        target_pos = index - 1
        skipped_songs = music.queue[:target_pos]
        music.queue = music.queue[target_pos:]

        if music.loop_queue:
            music.queue += skipped_songs

        music.manual_skip = True
        if vc and vc.is_playing():
            vc.stop()

        await music.play_next(text_channel=interaction.channel)
        music.manual_skip = False

        await interaction.followup.send(f"⏭️ Skipped to song {index} in the queue.")

    @discord.app_commands.command(name="queue", description="Show the song queue")
    async def queue_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)

        if not music.queue:
            await interaction.response.send_message("The queue is currently empty.")
            return

        await interaction.response.defer(thinking=True)

        # Build queue pages
        pages = []
        for i in range(0, len(music.queue), MAX_QUEUE_PAGE):
            chunk = music.queue[i : i + MAX_QUEUE_PAGE]
            description = ""
            for j, (title, filter_name) in enumerate(chunk, start=i + 1):
                if filter_name:
                    description += f"{j}. **{title}** — `{filter_name}`\n"
                else:
                    description += f"{j}. **{title}**\n"
            embed = discord.Embed(
                title=f"Queue (songs {i+1}-{min(i+MAX_QUEUE_PAGE,len(music.queue))})",
                description=description,
                color=discord.Color.blurple(),
            )
            pages.append(embed)

        # Paginate if multiple pages
        for page in pages:
            await interaction.followup.send(embed=page)

    @discord.app_commands.command(name="clearqueue", description="Clear the song queue")
    async def clearqueue_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)
        music.queue.clear()
        await interaction.response.send_message("🗑️ Queue cleared.")

    @discord.app_commands.command(
        name="stop", description="Stop and disconnect the bot"
    )
    async def stop_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)

        await music.stop(interaction)

        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()

        await interaction.response.send_message(
            "⏹️ Stopped, cleared the queue, and disconnected."
        )

    @discord.app_commands.command(
        name="nowplaying", description="Show the currently playing song"
    )
    async def nowplaying_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)
        vc = interaction.guild.voice_client
        if music.current and vc and vc.source:
            title = getattr(vc.source, "title", None)
            per_song_filter = music.current[1] if isinstance(music.current, tuple) else None
            active_filter = per_song_filter if per_song_filter is not None else music.global_filter
            embed = discord.Embed(
                title="🎶 Now Playing",
                description=f"**{title or 'Unknown'}**\nFilter: `{active_filter or 'None'}`",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed)
            return

        await interaction.response.send_message("Nothing is playing.")

    @discord.app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle_slash(self, interaction: discord.Interaction):
        import random

        music = self.get_music(interaction.guild)
        random.shuffle(music.queue)
        await interaction.response.send_message("🔀 Queue shuffled.")

    @discord.app_commands.command(
        name="loop_song", description="Toggle looping the current song"
    )
    async def loop_song_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)
        music.loop_song = not music.loop_song
        if music.loop_song:
            music.loop_queue = False
        await interaction.response.send_message(
            f"Loop song is now {'on' if music.loop_song else 'off'}."
        )

    @discord.app_commands.command(
        name="loop_queue", description="Toggle looping the queue"
    )
    async def loop_queue_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)
        music.loop_queue = not music.loop_queue
        if music.loop_queue:
            music.loop_song = False
        await interaction.response.send_message(
            f"Loop queue is now {'on' if music.loop_queue else 'off'}."
        )

    @discord.app_commands.command(
        name="filter",
        description="Apply a filter to the current song (or all songs if global)",
    )
    @discord.app_commands.choices(
        filter_name=[
            discord.app_commands.Choice(name="Nightcore", value="nightcore"),
            discord.app_commands.Choice(name="Daycore", value="daycore"),
            discord.app_commands.Choice(name="Vaporwave", value="vaporwave"),
            discord.app_commands.Choice(name="None", value="none"),
        ]
    )
    async def filter_slash(self, interaction: discord.Interaction, filter_name: str):
        filters = {
            "nightcore": "asetrate=48000*1.25,aresample=48000,atempo=1.1,aformat=channel_layouts=stereo,acompressor=threshold=0.5:ratio=2:attack=200:release=1000",
            "daycore": "asetrate=48000*0.8,aresample=48000,atempo=0.9,aformat=channel_layouts=stereo,acompressor=threshold=0.5:ratio=2:attack=200:release=1000",
            "vaporwave": "asetrate=44100*0.8,aresample=44100,atempo=0.9,aformat=channel_layouts=stereo,acompressor=threshold=0.5:ratio=2:attack=200:release=1000",
            "none": None
        }

        music = self.get_music(interaction.guild)
        chosen_filter = filters.get(filter_name, None)

        music.global_filter = chosen_filter

        if music.current:
            if chosen_filter is None:
                music.force_filter = "RESET_FILTER"
            else:
                music.force_filter = chosen_filter

        await interaction.response.send_message(f"Global filter set to `{filter_name}`.")

        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            music.replaying = True
            vc.stop()
            await asyncio.sleep(0.2)
            await music.play_next(text_channel=interaction.channel)
            music.replaying = False
