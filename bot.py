import os
import sys
import logging
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

from config import DISCORD_TOKEN, COMMAND_PREFIX, FFMPEG_PATH, validate_ffmpeg
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
        player.handle_voice_disconnect()
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
        voice_client = await user_channel.connect(reconnect=True)
    elif not voice_client.is_connected():
        await voice_client.disconnect(force=True)
        voice_client = await user_channel.connect(reconnect=True)
    elif voice_client.channel != user_channel:
        await voice_client.move_to(user_channel)

    return voice_client


# ==========================================
# HYBRID COMMANDS (Prefix '!' & Slash '/')
# ==========================================

@bot.hybrid_command(
    name="play",
    description="Play a song or queue YouTube/Spotify links and playlists.",
)
async def play(ctx: commands.Context, *, query: str):
    """Search or play links and queue playlist tracks in order."""
    # A voice connection or metadata lookup can take longer than Discord's
    # initial interaction window, so acknowledge only if it is still pending.
    if ctx.interaction and not ctx.interaction.response.is_done():
        await ctx.defer()

    voice_client = await ensure_voice_connection(ctx)
    if not voice_client:
        return

    player = music_manager.get_player(ctx.guild)
    player.voice_client = voice_client
    player.voice_connected.set()
    player.text_channel = ctx.channel

    requester_name = ctx.author.display_name
    songs, desc = await process_input_query(query, requester_name)

    if not songs:
        embed = discord.Embed(
            title="🔍 No Results",
            description=f"Could not find playable audio for: `{query}`\nDetails: {desc}",
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
        embed.set_footer(text="Tracks will play sequentially.")
        await ctx.send(embed=embed)

    # If nothing is currently playing, trigger playback immediately
    if not player.current and not voice_client.is_playing():
        player.play_next_song.set()


@bot.hybrid_command(name="skip", description="Skip to the next song in the queue.")
async def skip(ctx: commands.Context):
    player = music_manager.get_player(ctx.guild)
    current_title = player.current.title if player.current else None
    if player.skip():
        embed = discord.Embed(
            description=f"⏭️ Skipped **{current_title}**",
            color=0x3498DB,
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send("⚠️ No song is currently playing to skip.")


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

    try:
        validate_ffmpeg()
    except RuntimeError as error:
        logger.critical("%s", error)
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
