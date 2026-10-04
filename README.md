# 🎵 Audify Discord Music Bot

Ye Discord bot YouTube search, YouTube links/playlists, aur Spotify track/album/playlist links ko support karta hai. Spotify metadata se har track ka YouTube audio match search hota hai; Spotify ka audio stream directly play nahi hota. Playback YouTube/yt-dlp ki availability par depend karta hai. FFmpeg system par nahi milne par `imageio-ffmpeg` ka bundled executable use hota hai.

---

## 🌟 Features
- **Play:** `/play <query>` or `!play <query>` plays or queues a YouTube URL, Spotify track/album/playlist, or song-name search.
- **Skip:** `/skip` or `!skip` skips the currently playing song.
- Songs and playlist tracks are queued in order while another song is playing. Spotify tracks are matched to YouTube audio; streams are resolved when each track is about to play, so queued tracks do not rely on stale stream URLs.
---

## 🚀 Setup Guide (Step-by-Step)

### Step 1: Discord Bot Token Banayein
1. Apne browser mein [Discord Developer Portal](https://discord.com/developers/applications) kholein aur Discord se login karein.
2. Top right mein **"New Application"** button dabayein aur bot ka naam rakhein (e.g. `MusicBot`).
3. Left sidebar mein **"Bot"** tab par jayein:
   - **"Reset Token"** dabayein aur jo **Token** aayega use copy kar lein (isko kisi ke saath share na karein).
   - Scroll down karke **"Privileged Gateway Intents"** section mein:
     - ✅ **PRESENCE INTENT** -> ON karein
     - ✅ **SERVER MEMBERS INTENT** -> ON karein
     - ✅ **MESSAGE CONTENT INTENT** -> ON karein (ye sabse zaroori hai!)
   - **"Save Changes"** dabayein.

### Step 2: Bot Token `.env` File Mein Daalein
1. Project root folder (jahan `bot.py` hai) mein `.env` file banayein.
2. `.env` file ko Notepad ya kisi editor mein kholein:
   ```env
   DISCORD_TOKEN=yahan_apna_discord_bot_token_paste_karein
   ```
3. File save kar lein.
4. Spotify links ke liye [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) se app banayein aur uska Client ID/Client Secret bhi `.env` mein add karein:
   ```env
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   SPOTIFY_MARKET=IN
   ```
   `SPOTIFY_MARKET` optional hai; apna two-letter country code use karein. Spotify links public hone chahiye. Spotify audio nahi, YouTube par milta hua audio chalega.

### Step 3: Bot Ko Apne Server Mein Invite Karein
1. Developer portal mein **"Installation"** ya **"OAuth2" -> "URL Generator"** par jayein:
   - **SCOPES** mein: `bot` aur `applications.commands` tick karein.
   - **BOT PERMISSIONS** mein:
     - `Connect` (Voice)
     - `Speak` (Voice)
     - `Send Messages` (Text)
     - `Embed Links` (Text)
     - `Read Message History` (Text)
2. Bottom mein generated URL copy karein aur browser mein open karke apne server mein add kar lein.

---

## ▶️ Bot Kaise Chalayein

Project folder (`AUDIFY`) mein pehle locked dependencies ke saath `.venv` banayein:
  ```powershell
  uv sync --locked
  ```

Isse `.venv` folder create hoga. Uske baad:
- Windows par `run.bat` par **Double Click** karein, ya
- Terminal mein `uv run python bot.py` chalayein.

Jab terminal par:
`🤖 YOUR BOT IS ONLINE & READY!`
likha aa jaye, iska matlab aapka bot ready hai!

### Render Deployment

Render par **Python** runtime use karein (Docker nahi). Build command `uv sync --locked` aur start command `uv run python bot.py` set karein. Render dashboard mein `DISCORD_TOKEN` add karein; Spotify links enable karne ke liye `SPOTIFY_CLIENT_ID` aur `SPOTIFY_CLIENT_SECRET` bhi add karein. Secrets ko repository mein commit na karein. Bot startup par FFmpeg binary verify karta hai aur FFmpeg missing/broken hone par clear startup error deta hai.

---

## 📜 Commands List

Aap sirf ye do commands use kar sakte hain, Prefix (`!`) ya Slash (`/`) dono ke saath:

| Command | Shortcut / Slash | Description |
|---|---|---|
| `!play <song name ya link>` | `/play <query>` | Gaana search/play karein ya YouTube/Spotify playlist ke tracks queue karein. |
| `!skip` | `/skip` | Abhi chal raha gaana skip karein. |

---

## 💡 Examples
- YouTube Direct: `!play https://www.youtube.com/watch?v=kJQP7kiw5Fk`
- YouTube Playlist: `!play https://www.youtube.com/playlist?list=PLAYLIST_ID`
- Spotify Track/Playlist: `!play https://open.spotify.com/track/TRACK_ID` or `!play https://open.spotify.com/playlist/PLAYLIST_ID`
- Song Name Search: `!play arijit singh kesariya`
