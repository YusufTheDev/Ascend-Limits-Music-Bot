import discord
import asyncio
from discord.ext import commands
from bot.player import GuildMusic

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_instances = {}  # Store GuildMusic per guild

    def get_music(self, guild):
        if guild.id not in self.music_instances:
            self.music_instances[guild.id] = GuildMusic(self.bot, guild)
        return self.music_instances[guild.id]

    async def join_vc(self, interaction):
        # join the user's voice channel and return True if successful
        if interaction.user.voice and interaction.user.voice.channel:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(channel)
            else:
                await channel.connect()
            return True
        else:
            await interaction.response.send_message("You must be in a voice channel.", ephemeral=True)
            return False

    @discord.app_commands.command(name="play", description="Play a song")
    async def play_slash(self, interaction: discord.Interaction, query: str):
        music = self.get_music(interaction.guild)

        # Join VC
        if interaction.user.voice and interaction.user.voice.channel:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(channel)
            else:
                await channel.connect()
        else:
            await interaction.response.send_message("You must be in a voice channel.", ephemeral=True)
            return

        # Add song
        await music.add_song(query)

        # Respond immediately to interaction
        await interaction.response.send_message(f"✅ Added to queue: {query}")

        # Play next if not already playing
        vc = interaction.guild.voice_client
        if vc is None or not vc.is_playing():
            await music.play_next(text_channel=interaction.channel)


    @discord.app_commands.command(name="skip", description="Skip the current song")
    async def skip_slash(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("Skipped current song.")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @discord.app_commands.command(name="queue", description="Show the song queue")
    async def queue_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)

        if not music.queue:
            await interaction.response.send_message("The queue is currently empty.")
            return

        # Build queue lines with optional filter
        lines = []
        for i, (title, filter_name) in enumerate(music.queue):
            if filter_name:
                lines.append(f"{i+1}. **{title}** — `{filter_name}`")
            else:
                lines.append(f"{i+1}. **{title}**")

        # Split lines into messages <= 2000 chars
        chunks = []
        current_chunk = ""
        for line in lines:
            if len(current_chunk) + len(line) + 1 > 2000:
                chunks.append(current_chunk)
                current_chunk = ""
            current_chunk += line + "\n"
        if current_chunk:
            chunks.append(current_chunk)

        # Send first chunk as main response
        await interaction.response.send_message(f"**Queue:**\n{chunks[0]}")

        # Send the rest as follow-ups
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk)

    @discord.app_commands.command(name="clearqueue", description="Clear the song queue")
    async def clearqueue_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)
        music.queue.clear()
        await interaction.response.send_message("Queue cleared.")

    @discord.app_commands.command(name="stop", description="Stop and disconnect the bot")
    async def stop_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)

        # Stop current playback & reset music state
        await music.stop(interaction)

        # Disconnect from voice channel
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()

        await interaction.response.send_message("⏹️ Stopped, cleared the queue, and disconnected.")


    @discord.app_commands.command(name="nowplaying", description="Show the currently playing song")
    async def nowplaying_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)
        vc = interaction.guild.voice_client
        if music.current and vc and vc.source:
            # prefer the live player's title (accurate)
            title = getattr(vc.source, "title", None)
            # filter display: prefer per-song filter then global filter
            per_song_filter = music.current[1] if isinstance(music.current, tuple) else None
            active_filter = per_song_filter if per_song_filter is not None else music.global_filter
            if title:
                if active_filter:
                    await interaction.response.send_message(f"Now playing: **{title}**\nFilter: `{active_filter}`")
                else:
                    await interaction.response.send_message(f"Now playing: **{title}**")
                return
        await interaction.response.send_message("Nothing is playing.")

    @discord.app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle_slash(self, interaction: discord.Interaction):
        import random
        music = self.get_music(interaction.guild)
        random.shuffle(music.queue)
        await interaction.response.send_message("Queue shuffled.")

    @discord.app_commands.command(name="loop_song", description="Toggle looping the current song")
    async def loop_song_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)
        music.loop_song = not music.loop_song
        if music.loop_song:
            music.loop_queue = False  # Disable queue loop if song loop is enabled
        await interaction.response.send_message(f"Loop song is now {'on' if music.loop_song else 'off'}.")

    @discord.app_commands.command(name="loop_queue", description="Toggle looping the queue")
    async def loop_queue_slash(self, interaction: discord.Interaction):
        music = self.get_music(interaction.guild)
        music.loop_queue = not music.loop_queue
        if music.loop_queue:
            music.loop_song = False
        await interaction.response.send_message(f"Loop queue is now {'on' if music.loop_queue else 'off'}.")

    @discord.app_commands.command(name="filter", description="Apply a filter to the current song (or all songs if global)")
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
            "nightcore": "asetrate=48000*1.25,aresample=48000,atempo=1.1",
            "daycore": "asetrate=48000*0.8,aresample=48000,atempo=0.9",
            "vaporwave": "asetrate=44100*0.8,aresample=44100,atempo=0.9",
            "none": None
        }

        music = self.get_music(interaction.guild)
        chosen_filter = filters.get(filter_name, None)

        # set as global default for songs that don't have per-song filter
        music.global_filter = chosen_filter

        if music.current:
            if chosen_filter is None:
                music.force_filter = "RESET_FILTER"  # sentinel
            else:
                music.force_filter = chosen_filter


        await interaction.response.send_message(f"Global filter set to `{filter_name}`.")

        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            # Mark that this is a manual replay (so after_play won't double-trigger)
            music.replaying = True
            vc.stop()  # stop the current song
            await asyncio.sleep(0.2)  # tiny delay to let it fully stop
            # Manually trigger replay once with new filter
            await music.play_next(text_channel=interaction.channel)
            music.replaying = False

