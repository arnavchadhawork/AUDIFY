# 🎵 Discord Music Bot (YouTube + SoundCloud + Spotify)

Ye ek Discord music bot hai jo **YouTube** (videos, playlists, search) aur **Spotify** links support karta hai. YouTube search fail hone par bot **SoundCloud** par fallback search karta hai. Spotify links se track metadata lekar YouTube/SoundCloud par audio search kiya jata hai.

---

## 🌟 Features
- 🟢 **Spotify Link Support**: Spotify tracks, playlists, aur albums ke metadata se audio search hota hai.
- 🔴 **YouTube Support**: Song name search karein, video link dalein, ya puri YouTube playlist queue karein.
- 🟠 **SoundCloud Fallback**: YouTube search fail hone par bot SoundCloud par search karke playable track queue karta hai.
- ⚡ **Dual Commands**: Standard prefix commands (`!play`) aur modern slash commands (`/play`) dono support karta hai.
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

---

## 📜 Commands List

Aap Prefix (`!`) ya Slash (`/`) dono use kar sakte hain:

| Command | Shortcut / Slash | Description |
|---|---|---|
| `!play <song name ya link>` | `/play <query>` | YouTube song/link, YouTube search fail hone par SoundCloud fallback, ya Spotify track/playlist play karein |
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
- Spotify Track: `!play https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT`
- Spotify Playlist: `!play https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M`
- YouTube Direct: `!play https://www.youtube.com/watch?v=kJQP7kiw5Fk`
- Song Name Search: `!play arijit singh kesariya`
