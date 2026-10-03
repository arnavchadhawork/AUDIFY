# 🎵 Discord YouTube Music Bot

Ye Discord music bot sirf **yt-dlp** se YouTube par gaana naam se search karta hai aur video URLs play karta hai. YouTube playlist sirf playlist URL se add hoti hai. Playback YouTube/yt-dlp ki availability par depend karta hai; Render jaise hosts par YouTube bot checks ki wajah se kuch requests fail ho sakti hain. FFmpeg system par nahi milne par `imageio-ffmpeg` ka bundled executable use hota hai.

---

## 🌟 Features
- 🔴 **YouTube Support**: Song name search karein, video URL play karein, ya playlist URL se playlist queue karein.
- ⚡ **Dual Commands**: Standard prefix commands (`!play`) aur modern slash commands (`/play`) dono support karta hai.
- 📋 **Sequential Queue**: Playing song ke dauran add kiye gaye songs queue mein rehte hain aur baari-baari play hote hain. Playlist sirf playlist URL se add hoti hai; plain text ek song search karta hai.
- 🔁 **Voice Recovery**: Voice connection temporarily drops hone par current track queue mein preserve hota hai aur connection wapas aane par dobara play hota hai.
- 🔌 **Instant Auto Disconnect**: Jaise hi Voice Channel khali hoga (saare users leave karenge), bot turant music stop karega aur VC se disconnect ho jayega.


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

Windows par bot chalana behad aasan hai:
- `run.bat` file par **Double Click** karein!
- Ya terminal mein command chalayein:
  ```powershell
  python bot.py
  ```

Jab terminal par:
`🤖 YOUR BOT IS ONLINE & READY!`
likha aa jaye, iska matlab aapka bot ready hai!

### Render Deployment

Render par **Python** runtime use karein (Docker nahi). Build command `python -m pip install --upgrade -r requirements.txt yt-dlp` aur start command `python bot.py` set karein. Render dashboard mein `DISCORD_TOKEN` environment variable add karein; secret ko repository mein commit na karein. Har deploy par **Clear build cache & deploy** chunein. Bot startup par FFmpeg binary verify karta hai aur FFmpeg missing/broken hone par playback ke waqt chup-chaap fail hone ke bajaye clear startup error deta hai.

---

## 📜 Commands List

Aap Prefix (`!`) ya Slash (`/`) dono use kar sakte hain:

| Command | Shortcut / Slash | Description |
|---|---|---|
| `!play <song name ya link>` | `/play <query>` | Song name ya video URL play/queue karein. Playlist ke liye playlist URL dein. |
| `!pause` | `/pause` | Gaana pause karein |
| `!resume` | `/resume` | Paused gaana resume karein |
| `!skip` | `/skip` | Agle gaane par skip karein |
| `!queue` | `/queue` | Upcoming gaano ki list dekhein |
| `!nowplaying` | `/nowplaying` ya `!np` | Current song aur duration ki details dekhein |
| `!volume <1-100>` | `/volume <level>` | Volume adjust karein (e.g. `!volume 80`) |
| `!loop` | `/loop` | Loop switch karein: Off / Single Track / Entire Queue |
| `!shuffle` | `/shuffle` | Queue ke saare gaano ko shuffle karein |
| `!remove <number>` | `/remove <index>` | Queue se specific gaana hatayein (e.g. `!remove 3`) |
| `!stop` | `/stop` | Music stop karein aur queue clear karein |
| `!leave` | `/leave` | Bot ko voice channel se disconnect karein |
| `!help` | `/help` | Saari commands ka help menu dekhein |

---

## 💡 Examples
- YouTube Direct: `!play https://www.youtube.com/watch?v=kJQP7kiw5Fk`
- YouTube Playlist: `!play https://www.youtube.com/playlist?list=PLAYLIST_ID`
- Song Name Search: `!play arijit singh kesariya`
