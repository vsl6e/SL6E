import discord
from discord.ext import commands
from discord import app_commands, FFmpegOpusAudio
import yt_dlp as ytdlp
import asyncio
import os
import logging
import random
import re
from collections import deque
from urllib.parse import urlparse, parse_qs

# ============ إعدادات ============
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('MusicBot')

TOKEN = os.environ.get('TOKEN')
if not TOKEN:
    logger.error("❌ التوكن غير موجود! أضف TOKEN في Variables")
    exit(1)

PREFIX = os.environ.get('PREFIX', '!')

# ============ البوت ============
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ============ إعدادات yt-dlp ============
ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extractaudio': True,
    'restrictfilenames': True,
    'noplaylist': False,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'geo_bypass': True,
    'extract_flat': False,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
        'preferredquality': '192',
    }],
}

# إعدادات FFmpeg للجودة العالية
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -analyzeduration 0 -loglevel panic',
    'options': '-vn -b:a 192k -af "volume=1.0"'
}

# ============ هيكل البيانات ============
servers_data = {}

class ServerData:
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.voice_client = None
        self.is_playing = False
        self.is_paused = False
        self.volume = 0.5
        self.loop = False
        self.loop_queue = False
        self.history = deque(maxlen=50)
        self.auto_play = True
        self.bass_boost = False
        self.echo = False
        self.current_effect = 'none'

# ============ سجل الأوامر ============
class MusicBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await bot.tree.sync()
        logger.info(f'✅ البوت جاهز: {bot.user.name}')
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"{PREFIX}play"))

# ============ أوامر Slash ============

@bot.tree.command(name="play", description="تشغيل أغنية من يوتيوب أو سبوتيفاي")
@app_commands.describe(query="اسم الأغنية أو الرابط")
async def slash_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    await play_command(interaction, query)

@bot.tree.command(name="skip", description="تخطي الأغنية الحالية")
async def slash_skip(interaction: discord.Interaction):
    await interaction.response.defer()
    await skip_command(interaction)

@bot.tree.command(name="stop", description="إيقاف التشغيل وطرد البوت")
async def slash_stop(interaction: discord.Interaction):
    await interaction.response.defer()
    await stop_command(interaction)

@bot.tree.command(name="queue", description="عرض قائمة الانتظار")
async def slash_queue(interaction: discord.Interaction):
    await interaction.response.defer()
    await queue_command(interaction)

@bot.tree.command(name="now", description="عرض الأغنية الحالية")
async def slash_now(interaction: discord.Interaction):
    await interaction.response.defer()
    await now_command(interaction)

@bot.tree.command(name="pause", description="إيقاف مؤقت")
async def slash_pause(interaction: discord.Interaction):
    await interaction.response.defer()
    await pause_command(interaction)

@bot.tree.command(name="resume", description="استئناف التشغيل")
async def slash_resume(interaction: discord.Interaction):
    await interaction.response.defer()
    await resume_command(interaction)

@bot.tree.command(name="volume", description="تعديل مستوى الصوت (0-200)")
@app_commands.describe(level="مستوى الصوت 0-200")
async def slash_volume(interaction: discord.Interaction, level: int):
    await interaction.response.defer()
    await volume_command(interaction, level)

@bot.tree.command(name="loop", description="تفعيل/تعطيل تكرار الأغنية")
async def slash_loop(interaction: discord.Interaction):
    await interaction.response.defer()
    await loop_command(interaction)

@bot.tree.command(name="loopqueue", description="تفعيل/تعطيل تكرار القائمة")
async def slash_loopqueue(interaction: discord.Interaction):
    await interaction.response.defer()
    await loopqueue_command(interaction)

@bot.tree.command(name="shuffle", description="خلط قائمة الانتظار")
async def slash_shuffle(interaction: discord.Interaction):
    await interaction.response.defer()
    await shuffle_command(interaction)

@bot.tree.command(name="clear", description="مسح قائمة الانتظار")
async def slash_clear(interaction: discord.Interaction):
    await interaction.response.defer()
    await clear_command(interaction)

@bot.tree.command(name="remove", description="حذف أغنية من القائمة")
@app_commands.describe(index="رقم الأغنية في القائمة")
async def slash_remove(interaction: discord.Interaction, index: int):
    await interaction.response.defer()
    await remove_command(interaction, index)

@bot.tree.command(name="history", description="عرض سجل التشغيل")
async def slash_history(interaction: discord.Interaction):
    await interaction.response.defer()
    await history_command(interaction)

@bot.tree.command(name="bassboost", description="تفعيل/تعطيل تحسين الجهير")
async def slash_bass(interaction: discord.Interaction):
    await interaction.response.defer()
    await bass_command(interaction)

@bot.tree.command(name="ping", description="سرعة الاستجابة")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.defer()
    await ping_command(interaction)

@bot.tree.command(name="help", description="عرض قائمة الأوامر")
async def slash_help(interaction: discord.Interaction):
    await interaction.response.defer()
    await help_command(interaction)

@bot.tree.command(name="move", description="نقل الأغنية في القائمة")
@app_commands.describe(from_index="الرقم الحالي", to_index="الرقم الجديد")
async def slash_move(interaction: discord.Interaction, from_index: int, to_index: int):
    await interaction.response.defer()
    await move_command(interaction, from_index, to_index)

# ============ وظائف الأوامر ============

async def play_command(ctx_or_interaction, query):
    """تشغيل الأغنية"""
    if isinstance(ctx_or_interaction, discord.Interaction):
        ctx = await bot.get_context(ctx_or_interaction)
        author = ctx_or_interaction.user
        channel = ctx_or_interaction.user.voice.channel if ctx_or_interaction.user.voice else None
        respond = ctx_or_interaction.followup.send
    else:
        ctx = ctx_or_interaction
        author = ctx.author
        channel = ctx.author.voice.channel if ctx.author.voice else None
        respond = ctx.send

    if not channel:
        return await respond("⚠️ يجب أن تكون في روم صوتي!")

    # تهيئة بيانات السيرفر
    if ctx.guild.id not in servers_data:
        servers_data[ctx.guild.id] = ServerData()

    server = servers_data[ctx.guild.id]

    # الانضمام للروم
    if not server.voice_client or not server.voice_client.is_connected():
        try:
            server.voice_client = await channel.connect()
        except Exception as e:
            return await respond(f"❌ فشل الانضمام: {str(e)[:100]}")

    msg = await respond(f"🔍 جاري البحث: **{query}** ...")

    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)

            songs = []
            if 'entries' in info:
                for entry in info['entries']:
                    if entry:
                        songs.append({
                            'title': entry.get('title', 'Unknown'),
                            'url': entry.get('webpage_url', ''),
                            'duration': entry.get('duration', 0),
                            'uploader': entry.get('uploader', 'Unknown'),
                            'thumbnail': entry.get('thumbnail', ''),
                            'view_count': entry.get('view_count', 0),
                            'like_count': entry.get('like_count', 0),
                        })
            else:
                songs.append({
                    'title': info.get('title', 'Unknown'),
                    'url': info.get('webpage_url', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'thumbnail': info.get('thumbnail', ''),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                })

            if not songs:
                return await msg.edit(content="❌ لم يتم العثور على نتائج!")

            for song in songs:
                server.queue.append(song)
                server.history.append(song)

            if not server.is_playing:
                await play_next(ctx.guild.id)
                await msg.edit(content=f"🎵 **بدأ التشغيل:** {songs[0]['title']} [{format_duration(songs[0]['duration'])}]")
            else:
                await msg.edit(content=f"✅ **تمت الإضافة:** {songs[0]['title']} [{format_duration(songs[0]['duration'])}]\n📊 القائمة: {len(server.queue)} أغانٍ")

    except Exception as e:
        logger.error(f"خطأ: {e}")
        await msg.edit(content=f"❌ خطأ: {str(e)[:200]}")

async def skip_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server or not server.is_playing:
        return await respond(ctx_or_interaction, "❌ لا توجد أغنية!")
    server.voice_client.stop()
    await respond(ctx_or_interaction, "⏭️ تم التخطي")

async def stop_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server:
        return await respond(ctx_or_interaction, "❌ البوت غير متصل!")
    server.queue.clear()
    server.is_playing = False
    server.current = None
    if server.voice_client:
        await server.voice_client.disconnect()
    servers_data.pop(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id, None)
    await respond(ctx_or_interaction, "⏹️ تم الإيقاف")

async def queue_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server or not server.queue:
        return await respond(ctx_or_interaction, "📭 القائمة فارغة")

    text = f"**📋 قائمة الانتظار ({len(server.queue)}):**\n"
    for i, s in enumerate(server.queue, 1):
        dur = format_duration(s.get('duration', 0))
        text += f"`{i:2d}.` {s['title'][:40]} `[{dur}]`\n"
        if len(text) > 1800:
            text += f"\n... و {len(server.queue) - i} أغانٍ أخرى"
            break
    await respond(ctx_or_interaction, text)

async def now_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server or not server.current:
        return await respond(ctx_or_interaction, "❌ لا توجد أغنية!")

    song = server.current
    embed = discord.Embed(title="🎵 الآن يعمل", description=f"**{song['title']}**", color=0x00ff00)
    embed.add_field(name="🎤 المقدم", value=song.get('uploader', 'Unknown'), inline=True)
    embed.add_field(name="⏱️ المدة", value=format_duration(song.get('duration', 0)), inline=True)
    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])
    await respond(ctx_or_interaction, embed=embed)

async def pause_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if server and server.voice_client and server.voice_client.is_playing():
        server.voice_client.pause()
        await respond(ctx_or_interaction, "⏸️ توقف مؤقت")

async def resume_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if server and server.voice_client and server.voice_client.is_paused():
        server.voice_client.resume()
        await respond(ctx_or_interaction, "▶️ استئناف")

async def volume_command(ctx_or_interaction, level):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server:
        return await respond(ctx_or_interaction, "❌ البوت غير متصل!")
    if not 0 <= level <= 200:
        return await respond(ctx_or_interaction, "⚠️ بين 0 و 200")
    server.volume = level / 100
    if server.voice_client and server.voice_client.source:
        server.voice_client.source.volume = server.volume
    await respond(ctx_or_interaction, f"🔊 الصوت: {level}%")

async def loop_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server:
        return await respond(ctx_or_interaction, "❌ لا توجد أغنية!")
    server.loop = not server.loop
    await respond(ctx_or_interaction, f"🔄 تكرار: {'مفعل' if server.loop else 'معطل'}")

async def loopqueue_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server:
        return await respond(ctx_or_interaction, "❌ البوت غير متصل!")
    server.loop_queue = not server.loop_queue
    await respond(ctx_or_interaction, f"🔄 تكرار القائمة: {'مفعل' if server.loop_queue else 'معطل'}")

async def shuffle_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server or len(server.queue) < 2:
        return await respond(ctx_or_interaction, "❌ ما يكفي للخلط!")
    q = list(server.queue)
    random.shuffle(q)
    server.queue = deque(q)
    await respond(ctx_or_interaction, "🔀 تم الخلط")

async def clear_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if server and server.queue:
        server.queue.clear()
        await respond(ctx_or_interaction, "🧹 مسحت القائمة")

async def remove_command(ctx_or_interaction, index):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server or not server.queue:
        return await respond(ctx_or_interaction, "❌ القائمة فارغة!")
    if 1 <= index <= len(server.queue):
        removed = server.queue[index - 1]
        del server.queue[index - 1]
        await respond(ctx_or_interaction, f"🗑️ حذفت: {removed['title']}")

async def history_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server or not server.history:
        return await respond(ctx_or_interaction, "📭 السجل فارغ")
    text = "**📜 سجل التشغيل:**\n"
    for i, s in enumerate(server.history, 1):
        text += f"`{i}.` {s['title'][:50]}\n"
        if len(text) > 1800:
            break
    await respond(ctx_or_interaction, text)

async def bass_command(ctx_or_interaction):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server:
        return await respond(ctx_or_interaction, "❌ البوت غير متصل!")
    server.bass_boost = not server.bass_boost
    await respond(ctx_or_interaction, f"🎵 جهير: {'مفعل' if server.bass_boost else 'معطل'}")

async def ping_command(ctx_or_interaction):
    latency = round(bot.latency * 1000)
    await respond(ctx_or_interaction, f"🏓 {latency}ms")

async def help_command(ctx_or_interaction):
    embed = discord.Embed(title="🎵 قائمة الأوامر", color=0x3498db)
    cmds = {
        "/play": "تشغيل أغنية",
        "/skip": "تخطي الأغنية",
        "/stop": "إيقاف وطرد البوت",
        "/pause": "إيقاف مؤقت",
        "/resume": "استئناف",
        "/queue": "عرض القائمة",
        "/now": "الأغنية الحالية",
        "/volume": "ضبط الصوت 0-200%",
        "/loop": "تكرار الأغنية",
        "/loopqueue": "تكرار القائمة",
        "/shuffle": "خلط القائمة",
        "/clear": "مسح القائمة",
        "/remove": "حذف أغنية من القائمة",
        "/history": "سجل التشغيل",
        "/bassboost": "تفعيل/تعطيل الجهير",
        "/move": "نقل أغنية في القائمة",
        "/ping": "سرعة الاستجابة"
    }
    for cmd, desc in cmds.items():
        embed.add_field(name=cmd, value=desc, inline=True)
    await respond(ctx_or_interaction, embed=embed)

async def move_command(ctx_or_interaction, from_idx, to_idx):
    server = servers_data.get(ctx_or_interaction.guild.id if hasattr(ctx_or_interaction, 'guild') else ctx_or_interaction.guild.id)
    if not server or not server.queue:
        return await respond(ctx_or_interaction, "❌ القائمة فارغة!")
    q = list(server.queue)
    if 1 <= from_idx <= len(q) and 1 <= to_idx <= len(q):
        song = q.pop(from_idx - 1)
        q.insert(to_idx - 1, song)
        server.queue = deque(q)
        await respond(ctx_or_interaction, f"✅ نُقلت: {song['title']}")

# ============ وظيفة المساعدة ============
async def respond(ctx_or_interaction, content):
    if isinstance(ctx_or_interaction, discord.Interaction):
        return await ctx_or_interaction.followup.send(content)
    else:
        return await ctx_or_interaction.send(content)

# ============ أوامر البادئة ============

@bot.command(name='play', aliases=['p'])
async def prefix_play(ctx, *, query):
    await play_command(ctx, query)

@bot.command(name='skip', aliases=['s'])
async def prefix_skip(ctx):
    await skip_command(ctx)

@bot.command(name='stop')
async def prefix_stop(ctx):
    await stop_command(ctx)

@bot.command(name='queue', aliases=['q'])
async def prefix_queue(ctx):
    await queue_command(ctx)

@bot.command(name='now', aliases=['np'])
async def prefix_now(ctx):
    await now_command(ctx)

@bot.command(name='pause')
async def prefix_pause(ctx):
    await pause_command(ctx)

@bot.command(name='resume')
async def prefix_resume(ctx):
    await resume_command(ctx)

@bot.command(name='volume', aliases=['vol'])
async def prefix_volume(ctx, level: int):
    await volume_command(ctx, level)

@bot.command(name='loop')
async def prefix_loop(ctx):
    await loop_command(ctx)

@bot.command(name='loopqueue', aliases=['lq'])
async def prefix_loopqueue(ctx):
    await loopqueue_command(ctx)

@bot.command(name='shuffle')
async def prefix_shuffle(ctx):
    await shuffle_command(ctx)

@bot.command(name='clear')
async def prefix_clear(ctx):
    await clear_command(ctx)

@bot.command(name='remove', aliases=['rm'])
async def prefix_remove(ctx, index: int):
    await remove_command(ctx, index)

@bot.command(name='history')
async def prefix_history(ctx):
    await history_command(ctx)

@bot.command(name='bassboost', aliases=['bass'])
async def prefix_bass(ctx):
    await bass_command(ctx)

@bot.command(name='ping')
async def prefix_ping(ctx):
    await ping_command(ctx)

@bot.command(name='help')
async def prefix_help(ctx):
    await help_command(ctx)

@bot.command(name='move')
async def prefix_move(ctx, from_idx: int, to_idx: int):
    await move_command(ctx, from_idx, to_idx)

# ============ وظائف التشغيل ============

async def play_next(guild_id):
    server = servers_data.get(guild_id)
    if not server or not server.queue:
        server.is_playing = False
        server.current = None
        return

    if server.loop and server.current:
        server.queue.appendleft(server.current)

    if not server.queue and server.loop_queue:
        if server.history:
            server.queue = deque(list(server.history)[-20:])

    if not server.queue:
        server.is_playing = False
        server.current = None
        return

    song = server.queue[0]
    server.current = song

    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song['url'], download=False)
            audio_url = info['url']

        # تأثيرات الصوت
        effects = []
        if server.bass_boost:
            effects.append('bass=g=15,f=110,w=0.3')
        if server.echo:
            effects.append('aecho=0.8:0.88:60:0.4')

        filter_chain = ','.join(effects) if effects else 'volume={}'.format(server.volume)

        source = FFmpegOpusAudio(
            audio_url,
            before_options=FFMPEG_OPTIONS['before_options'],
            options=f'-vn -b:a 192k -af "{filter_chain}"'
        )

        def after_callback(error):
            asyncio.run_coroutine_threadsafe(handle_after(guild_id, error), bot.loop)

        server.voice_client.play(source, after=after_callback)
        server.is_playing = True

        # تحديث حالة البوت
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"{song['title'][:30]}"))

        logger.info(f'🎵 تشغيل: {song["title"]}')

    except Exception as e:
        logger.error(f"خطأ: {e}")
        if server.queue:
            server.queue.popleft()
        await play_next(guild_id)

async def handle_after(guild_id, error):
    if error:
        logger.error(f"خطأ في التشغيل: {error}")

    server = servers_data.get(guild_id)
    if not server:
        return

    if not server.loop and server.queue:
        server.queue.popleft()

    server.is_playing = False
    await play_next(guild_id)

def format_duration(seconds):
    if not seconds:
        return "0:00"
    mins, secs = divmod(int(seconds), 60)
    hrs, mins = divmod(mins, 60)
    return f"{hrs}:{mins:02d}:{secs:02d}" if hrs else f"{mins}:{secs:02d}"

# ============ التشغيل ============

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        logger.info("✅ تم تسجيل الأوامر")
    except Exception as e:
        logger.error(f"خطأ في تسجيل الأوامر: {e}")

    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"{PREFIX}play"))
    logger.info(f'✅ البوت جاهز: {bot.user.name}')

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"فشل التشغيل: {e}")
