import discord
from discord.ext import commands
import yt_dlp as ytdlp
import asyncio
import os
from collections import deque
import logging

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('MusicBot')

# قراءة التوكن من متغيرات البيئة
TOKEN = os.environ.get('DISCORD_TOKEN') or os.environ.get('TOKEN')

if not TOKEN:
    raise ValueError("❌ التوكن غير موجود! أضفه في Railway Variables")

PREFIX = os.environ.get('PREFIX', '!')

# إعدادات البوت
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# إعدادات yt-dlp
ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extractaudio': True,
    'restrictfilenames': True,
    'noplaylist': False,
}

servers_data = {}

class ServerData:
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.voice_client = None
        self.is_playing = False
        self.volume = 0.5
        self.loop = False

@bot.event
async def on_ready():
    logger.info(f'✅ البوت جاهز: {bot.user.name} (ID: {bot.user.id})')
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}play | {len(bot.guilds)} سيرفر"))

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query=None):
    if not query:
        return await ctx.send("❌ أدخل اسم أغنية أو رابط!")
    
    if not ctx.author.voice:
        return await ctx.send("⚠️ يجب أن تكون في روم صوتي!")

    if ctx.guild.id not in servers_data:
        servers_data[ctx.guild.id] = ServerData()

    server = servers_data[ctx.guild.id]

    if not server.voice_client or not server.voice_client.is_connected():
        try:
            server.voice_client = await ctx.author.voice.channel.connect()
        except Exception as e:
            return await ctx.send(f"❌ فشل الانضمام: {str(e)[:100]}")

    msg = await ctx.send(f"🔍 جاري البحث: **{query}** ...")

    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            
            song = {
                'title': info.get('title', 'Unknown'),
                'url': info.get('webpage_url', info.get('url')),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown')
            }

        server.queue.append(song)

        if not server.is_playing:
            await play_next(ctx.guild.id)
            await msg.edit(content=f"🎵 بدأ التشغيل: **{song['title']}**")
        else:
            await msg.edit(content=f"✅ أضيفت: **{song['title']}**")

    except Exception as e:
        await msg.edit(content=f"❌ خطأ: {str(e)[:200]}")

@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    server = servers_data.get(ctx.guild.id)
    if not server or not server.is_playing:
        return await ctx.send("❌ لا توجد أغنية!")
    server.voice_client.stop()
    await ctx.send("⏭️ تم التخطي")

@bot.command(name='stop')
async def stop(ctx):
    server = servers_data.get(ctx.guild.id)
    if not server:
        return await ctx.send("❌ البوت غير متصل!")

    server.queue.clear()
    server.is_playing = False
    server.current = None
    if server.voice_client:
        await server.voice_client.disconnect()
    servers_data.pop(ctx.guild.id, None)
    await ctx.send("⏹️ تم الإيقاف")

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    server = servers_data.get(ctx.guild.id)
    if not server or not server.queue:
        return await ctx.send("📭 القائمة فارغة")

    text = f"**📋 قائمة الانتظار ({len(server.queue)}):**\n"
    for i, s in enumerate(server.queue, 1):
        text += f"`{i}.` {s['title'][:50]}\n"
        if len(text) > 1800:
            text += f"... و {len(server.queue) - i} أغانٍ أخرى"
            break
    await ctx.send(text)

@bot.command(name='now', aliases=['np'])
async def now_playing(ctx):
    server = servers_data.get(ctx.guild.id)
    if not server or not server.current:
        return await ctx.send("❌ لا توجد أغنية!")

    song = server.current
    embed = discord.Embed(
        title="🎵 الآن يعمل",
        description=f"**{song['title']}**",
        color=0x00ff00
    )
    embed.add_field(name="🎤 المقدم", value=song.get('uploader', 'Unknown'), inline=True)
    await ctx.send(embed=embed)

@bot.command(name='pause')
async def pause(ctx):
    server = servers_data.get(ctx.guild.id)
    if server and server.voice_client and server.voice_client.is_playing():
        server.voice_client.pause()
        await ctx.send("⏸️ توقف مؤقت")

@bot.command(name='resume')
async def resume(ctx):
    server = servers_data.get(ctx.guild.id)
    if server and server.voice_client and server.voice_client.is_paused():
        server.voice_client.resume()
        await ctx.send("▶️ استئناف")

@bot.command(name='volume', aliases=['vol'])
async def set_volume(ctx, level: int):
    server = servers_data.get(ctx.guild.id)
    if not server:
        return await ctx.send("❌ البوت غير متصل!")

    if not 0 <= level <= 100:
        return await ctx.send("⚠️ بين 0 و 100")

    server.volume = level / 100
    if server.voice_client and server.voice_client.source:
        server.voice_client.source.volume = server.volume
    await ctx.send(f"🔊 الصوت: {level}%")

@bot.command(name='loop')
async def loop(ctx):
    server = servers_data.get(ctx.guild.id)
    if not server or not server.current:
        return await ctx.send("❌ لا توجد أغنية!")
    server.loop = not server.loop
    await ctx.send(f"🔄 تكرار: {'مفعل' if server.loop else 'معطل'}")

@bot.command(name='shuffle')
async def shuffle(ctx):
    import random
    server = servers_data.get(ctx.guild.id)
    if not server or len(server.queue) < 2:
        return await ctx.send("❌ ما يكفي للخلط!")
    
    queue_list = list(server.queue)
    random.shuffle(queue_list)
    server.queue = deque(queue_list)
    await ctx.send("🔀 تم الخلط")

@bot.command(name='clear')
async def clear(ctx):
    server = servers_data.get(ctx.guild.id)
    if server and server.queue:
        server.queue.clear()
        await ctx.send("🧹 مسحت القائمة")

@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f"🏓 {round(bot.latency * 1000)}ms")

async def play_next(guild_id):
    server = servers_data.get(guild_id)
    if not server or not server.queue:
        server.is_playing = False
        return

    song = server.queue[0]
    server.current = song

    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song['url'], download=False)
            audio_url = info['url']

        source = discord.FFmpegOpusAudio(
            audio_url,
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options=f'-filter:a "volume={server.volume}"'
        )

        server.voice_client.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                handle_after(guild_id, e), bot.loop
            )
        )
        server.is_playing = True

    except Exception as e:
        logger.error(f"خطأ في التشغيل: {e}")
        if server.queue:
            server.queue.popleft()
        await play_next(guild_id)

async def handle_after(guild_id, error):
    if error:
        logger.error(f"خطأ: {error}")

    server = servers_data.get(guild_id)
    if not server:
        return

    if not server.loop and server.queue:
        server.queue.popleft()

    server.is_playing = False
    await play_next(guild_id)

if __name__ == "__main__":
    logger.info("🚀 بدء تشغيل البوت...")
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"فشل التشغيل: {e}")
