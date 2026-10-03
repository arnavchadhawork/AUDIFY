import os
import sys
import logging
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

# Ensure proper UTF-8 stdout encoding for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")



import discord
from discord.ext import commands

from config import DISCORD_TOKEN, COMMAND_PREFIX, FFMPEG_PATH
from music_player import MusicManager, process_input_query, Song

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("MusicBot")

# Set up Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

# Initialize Bot
bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    intents=intents,
    help_command=None,  # We'll create a custom beautiful help command
)

music_manager = MusicManager(bot)


@bot.event
async def on_ready():
    logger.info("=" * 50)
    logger.info(f"Logged in as: {bot.user.name}#{bot.user.discriminator} (ID: {bot.user.id})")
    logger.info(f"Command Prefix: {COMMAND_PREFIX}")
    logger.info(f"FFmpeg Path: {FFMPEG_PATH}")
    logger.info("=" * 50)

    # Set Discord presence
    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name=f"{COMMAND_PREFIX}play | /play 🎵"
    )
    await bot.change_presence(activity=activity)

    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        logger.info(f"Successfully synced {len(synced)} slash commands!")
    except Exception as e:
        logger.warning(f"Failed to sync slash commands: {e}")

    # Generate invite link for the user
    invite_url = discord.utils.oauth_url(
        bot.user.id,
        permissions=discord.Permissions(
            connect=True,
            speak=True,
            use_voice_activation=True,
            send_messages=True,
            embed_links=True,
            read_message_history=True,
            add_reactions=True,
        ),
    )
    print("\n" + "#" * 60)
    print("🤖 YOUR BOT IS ONLINE & READY!")
    print(f"👉 Server Invite Link:\n{invite_url}")
    print("#" * 60 + "\n")


@bot.event
async def on_voice_state_update(member, before, after):
    """Auto-disconnect immediately when the voice channel becomes empty."""
    # Agar bot khud disconnect hua ho
    if member.id == bot.user.id and after.channel is None:
        player = music_manager.get_player(member.guild)
        player.stop()
        return

    # Check the guild's active voice connection
    voice_client = member.guild.voice_client
    if voice_client and voice_client.channel:
        # Check non-bot members remaining in the bot's voice channel
        non_bots = [m for m in voice_client.channel.members if not m.bot]
        if len(non_bots) == 0:
            player = music_manager.get_player(member.guild)
            player.stop()
            if player.text_channel:
                try:
                    embed = discord.Embed(
                        description="👋 **Voice channel khali ho gaya, isliye bot disconnect ho gaya.**",
                        color=0x95A5A6,
                    )
                    await player.text_channel.send(embed=embed)
                except Exception as e:
                    logger.debug(f"Could not send leave notification: {e}")
            await voice_client.disconnect(force=True)



async def ensure_voice_connection(ctx: commands.Context) -> Optional[discord.VoiceClient]:
    """Ensures the bot is connected to the same voice channel as the author."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        embed = discord.Embed(
            description="❌ **Aapko pehle kisi Voice Channel mein connect hona hoga!**",
            color=0xE74C3C,
        )
        await ctx.send(embed=embed)
        return None

    user_channel = ctx.author.voice.channel
    voice_client = ctx.voice_client

    if not voice_client:
        voice_client = await user_channel.connect()
    elif voice_client.channel != user_channel:
        await voice_client.move_to(user_channel)

    return voice_client


# ==========================================
# HYBRID COMMANDS (Prefix '!' & Slash '/')
# ==========================================

@bot.hybrid_command(
    name="play",
    description="Play a song, YouTube link, or Spotify link (track/playlist/album) ad-free!",
)
async def play(ctx: commands.Context, *, query: str):
    """Plays song from YouTube search, YouTube link, or Spotify link."""
    voice_client = await ensure_voice_connection(ctx)
    if not voice_client:
        return

    # Defer response so Discord doesn't timeout during network fetch
    await ctx.defer()

    player = music_manager.get_player(ctx.guild)
    player.voice_client = voice_client
    player.text_channel = ctx.channel

    requester_name = ctx.author.display_name
    songs, desc = await process_input_query(query, requester_name)

    if not songs:
        embed = discord.Embed(
            title="🔍 No Results",
            description=f"Could not find any playable songs for: `{query}`\nDetails: {desc}",
            color=0xE74C3C,
        )
        await ctx.send(embed=embed)
        return

    # Add song(s) to queue
    for song in songs:
        player.queue.append(song)

    if len(songs) == 1:
        song = songs[0]
        embed = discord.Embed(
            title="➕ Added to Queue",
            description=f"**[{song.title}]({song.webpage_url if song.webpage_url else 'https://youtube.com'})**",
            color=0x2ECC71,
        )
        embed.add_field(name="⏱️ Duration", value=song.duration_str, inline=True)
        embed.add_field(name="👤 Requester", value=song.requester, inline=True)
        embed.add_field(name="🌐 Source", value=song.source, inline=True)
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        if player.current:
            embed.set_footer(text=f"Position in queue: #{len(player.queue)}")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="🎶 Playlist Added to Queue",
            description=f"Successfully queued {desc}!",
            color=0x2ECC71,
        )
        embed.add_field(name="🔢 Songs Queued", value=f"{len(songs)} tracks", inline=True)
        embed.add_field(name="👤 Requester", value=requester_name, inline=True)
        embed.set_footer(text="Songs will play sequentially without ads!")
        await ctx.send(embed=embed)

    # If nothing is currently playing, trigger playback immediately
    if not player.current and not voice_client.is_playing():
        player.play_next_song.set()


@bot.hybrid_command(name="pause", description="Pause the currently playing song.")
async def pause(ctx: commands.Context):
    player = music_manager.get_player(ctx.guild)
    if player.pause():
        await ctx.send("⏸️ **Playback paused.** Type `!resume` or `/resume` to continue.")
    else:
        await ctx.send("⚠️ Nothing is currently playing to pause.")


@bot.hybrid_command(name="resume", description="Resume the paused song.")
async def resume(ctx: commands.Context):
    player = music_manager.get_player(ctx.guild)
    if player.resume():
        await ctx.send("▶️ **Playback resumed!**")
    else:
        await ctx.send("⚠️ Playback is not paused.")


@bot.hybrid_command(name="skip", description="Skip to the next song in the queue.")
async def skip(ctx: commands.Context):
    player = music_manager.get_player(ctx.guild)
    if player.current and player.skip():
        embed = discord.Embed(
            description=f"⏭️ Skipped **{player.current.title}**",
            color=0x3498DB,
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send("⚠️ No song is currently playing to skip.")


@bot.hybrid_command(name="stop", description="Stop music, clear queue, and disconnect.")
async def stop(ctx: commands.Context):
    player = music_manager.get_player(ctx.guild)
    player.stop()
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    embed = discord.Embed(
        description="⏹️ **Music stopped, queue cleared, and disconnected.**",
        color=0xE74C3C,
    )
    await ctx.send(embed=embed)


@bot.hybrid_command(name="queue", description="Show the list of upcoming songs.")
async def queue(ctx: commands.Context):
    player = music_manager.get_player(ctx.guild)

    if not player.current and not player.queue:
        await ctx.send("📭 **The queue is currently empty.** Add songs with `!play <song>`!")
        return

    embed = discord.Embed(
        title="📋 Server Music Queue",
        color=0x9B59B6,
    )

    if player.current:
        embed.add_field(
            name="▶️ Currently Playing",
            value=f"**[{player.current.title}]({player.current.webpage_url})** | `{player.current.duration_str}` (by {player.current.requester})",
            inline=False,
        )

    if player.queue:
        queue_text = []
        # Show first 10 tracks
        for idx, song in enumerate(list(player.queue)[:10], start=1):
            queue_text.append(f"`{idx}.` **{song.title}** (`{song.duration_str}`) - *{song.requester}*")

        more_count = len(player.queue) - 10
        if more_count > 0:
            queue_text.append(f"\n*...and {more_count} more songs in queue.*")

        embed.add_field(
            name=f"Up Next ({len(player.queue)} songs)",
            value="\n".join(queue_text),
            inline=False,
        )
    else:
        embed.add_field(name="Up Next", value="No upcoming songs.", inline=False)

    loop_status = {
        "off": "Off",
        "one": "🔂 Current Track",
        "all": "🔁 Entire Queue",
    }.get(player.loop_mode, "Off")
    embed.set_footer(text=f"Loop: {loop_status} • Volume: {int(player.volume * 100)}%")
    await ctx.send(embed=embed)


@bot.hybrid_command(name="nowplaying", aliases=["np"], description="Show info about the song currently playing.")
async def nowplaying(ctx: commands.Context):
    player = music_manager.get_player(ctx.guild)
    if not player.current:
        await ctx.send("🔇 Nothing is playing right now.")
        return

    embed = player.create_now_playing_embed(player.current)
    await ctx.send(embed=embed)


@bot.hybrid_command(name="volume", description="Change playback volume (1-100%).")
async def volume(ctx: commands.Context, level: int):
    if level < 1 or level > 100:
        await ctx.send("⚠️ Volume must be between 1 and 100.")
        return

    player = music_manager.get_player(ctx.guild)
    player.set_volume(level / 100.0)
    await ctx.send(f"🔊 Volume set to **{level}%**")


@bot.hybrid_command(
    name="loop",
    description="Toggle looping mode: off, one (single song), or all (queue).",
)
async def loop(ctx: commands.Context, mode: Optional[str] = None):
    player = music_manager.get_player(ctx.guild)

    if mode:
        mode = mode.lower()
        if mode in ("off", "none", "disable"):
            player.loop_mode = "off"
        elif mode in ("one", "single", "track", "current"):
            player.loop_mode = "one"
        elif mode in ("all", "queue"):
            player.loop_mode = "all"
        else:
            await ctx.send("⚠️ Valid modes are: `off`, `one`, `all`")
            return
    else:
        # Cycle through modes
        cycles = {"off": "one", "one": "all", "all": "off"}
        player.loop_mode = cycles.get(player.loop_mode, "off")

    mode_labels = {
        "off": "❌ Loop Disabled",
        "one": "🔂 Looping Current Song",
        "all": "🔁 Looping Entire Queue",
    }
    await ctx.send(f"🔄 **{mode_labels[player.loop_mode]}**")


@bot.hybrid_command(name="shuffle", description="Shuffle all songs currently in the queue.")
async def shuffle(ctx: commands.Context):
    player = music_manager.get_player(ctx.guild)
    if len(player.queue) < 2:
        await ctx.send("⚠️ Need at least 2 songs in the queue to shuffle.")
        return

    queue_list = list(player.queue)
    random.shuffle(queue_list)
    player.queue.clear()
    player.queue.extend(queue_list)
    await ctx.send(f"🔀 **Shuffled {len(player.queue)} songs in the queue!**")


@bot.hybrid_command(name="remove", description="Remove a specific song from queue by its index number.")
async def remove(ctx: commands.Context, index: int):
    player = music_manager.get_player(ctx.guild)
    if index < 1 or index > len(player.queue):
        await ctx.send(f"⚠️ Invalid song number. Current queue has {len(player.queue)} songs.")
        return

    removed_song = player.queue[index - 1]
    del player.queue[index - 1]
    await ctx.send(f"🗑️ Removed **{removed_song.title}** from the queue.")


@bot.hybrid_command(name="leave", aliases=["disconnect", "dc"], description="Disconnect bot from the voice channel.")
async def leave(ctx: commands.Context):
    player = music_manager.get_player(ctx.guild)
    player.stop()
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Disconnected from voice channel.")
    else:
        await ctx.send("⚠️ I am not connected to any voice channel.")


@bot.hybrid_command(name="help", description="Show all available music bot commands.")
async def help_command(ctx: commands.Context):
    embed = discord.Embed(
        title="🎵 Free & Ad-Free Music Bot Commands",
        description="Supports **YouTube** (videos, playlists, search) & **Spotify** (tracks, playlists, albums) without ads or subscriptions!",
        color=0x5865F2,
    )
    embed.add_field(
        name="🎶 Playback Commands",
        value=(
            f"`{COMMAND_PREFIX}play <query/url>` or `/play` - Play YouTube or Spotify\n"
            f"`{COMMAND_PREFIX}pause` or `/pause` - Pause music\n"
            f"`{COMMAND_PREFIX}resume` or `/resume` - Resume music\n"
            f"`{COMMAND_PREFIX}skip` or `/skip` - Skip current song\n"
            f"`{COMMAND_PREFIX}stop` or `/stop` - Stop & clear queue"
        ),
        inline=False,
    )
    embed.add_field(
        name="📋 Queue & Controls",
        value=(
            f"`{COMMAND_PREFIX}queue` or `/queue` - View upcoming songs\n"
            f"`{COMMAND_PREFIX}nowplaying` (`!np`) - Song details\n"
            f"`{COMMAND_PREFIX}volume <1-100>` - Set volume\n"
            f"`{COMMAND_PREFIX}loop [off/one/all]` - Toggle loop\n"
            f"`{COMMAND_PREFIX}shuffle` - Randomize queue\n"
            f"`{COMMAND_PREFIX}remove <number>` - Remove track\n"
            f"`{COMMAND_PREFIX}leave` - Disconnect bot"
        ),
        inline=False,
    )
    embed.set_footer(text="Tip: You can use both !prefix and /slash commands!")
    await ctx.send(embed=embed)


class HealthHandler(BaseHTTPRequestHandler):
    """Small HTTP endpoint so Render can detect that the service is up."""

    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_error(404)
            return
        body = b"Audify Discord bot is running.\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        logger.info("HTTP: " + format, *args)


def start_render_http_server():
    """Bind Render's assigned port without blocking the Discord event loop."""
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, name="render-http", daemon=True).start()
    logger.info("Render health server listening on 0.0.0.0:%s", port)
    return server


def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n" + "!" * 65)
        print("❌ ERROR: DISCORD_TOKEN is not set in the .env file!")
        print("👉 Please edit the '.env' file in this folder and paste your Discord bot token.")
        print("!" * 65 + "\n")
        sys.exit(1)

    start_render_http_server()

    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        print("\n" + "!" * 65)
        print("❌ ERROR: Invalid Discord Bot Token!")
        print("Please check your token in the .env file and ensure it is correct.")
        print("!" * 65 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
