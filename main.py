import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp as ytdlp
import asyncio
import os
import logging
import random
from collections import deque
import json

# ============ إعدادات ============
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('MusicBot')

TOKEN = os.environ.get('TOKEN') or os.environ.get('DISCORD_TOKEN')
if not TOKEN:
    logger.error("❌ التوكن غير موجود! أضف TOKEN في Railway Variables")
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
}

# ============ هيكل البيانات ============
servers_data = {}

class ServerData:
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.voice_client = None
        self.is_playing = False
        self.volume = 0.5
        self.loop = False
        self.loop_queue = False
        self.history = deque(maxlen=50)

# ============ الأحداث ============

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        logger.info("✅ تم تسجيل الأوامر Slash")
    except Exception as e:
        logger.error(f"خطأ في التسجيل: {e}")

    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name=f"{PREFIX}play | {len(bot.guilds)} سيرفر"
    ))
    logger.info(f'✅ البوت جاهز: {bot.user.name} (ID: {bot.user.id})')
    logger.info(f'📊 متصل بـ {len(bot.guilds)} سيرفر')

@bot.event
async def on_guild_join(guild):
    logger.info(f'➕ انضممت إلى: {guild.name}')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name=f"{PREFIX}play | {len(bot.guilds)} سيرفر"
    ))

@bot.event
async def on_guild_remove(guild):
    logger.info(f'➖ تركت: {guild.name}')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name=f"{PREFIX}play | {len(bot.guilds)} سيرفر"
    ))

# ============ أوامر Slash ============

@bot.tree.command(name="play", description="🎵 تشغيل أغنية من يوتيوب")
@app_commands.describe(query="اسم الأغنية أو الرابط")
async def slash_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    await play_command(interaction, query)

@bot.tree.command(name="skip", description="⏭️ تخطي الأغنية الحالية")
async def slash_skip(interaction: discord.Interaction):
    await interaction.response.defer()
    await skip_command(interaction)

@bot.tree.command(name="stop", description="⏹️ إيقاف التشغيل وطرد البوت")
async def slash_stop(interaction: discord.Interaction):
    await interaction.response.defer()
    await stop_command(interaction)

@bot.tree.command(name="pause", description="⏸️ إيقاف مؤقت")
async def slash_pause(interaction: discord.Interaction):
    await interaction.response.defer()
    await pause_command(interaction)

@bot.tree.command(name="resume", description="▶️ استئناف التشغيل")
async def slash_resume(interaction: discord.Interaction):
    await interaction.response.defer()
    await resume_command(interaction)

@bot.tree.command(name="queue", description="📋 عرض قائمة الانتظار")
async def slash_queue(interaction: discord.Interaction):
    await interaction.response.defer()
    await queue_command(interaction)

@bot.tree.command(name="now", description="🎵 عرض الأغنية الحالية")
async def slash_now(interaction: discord.Interaction):
    await interaction.response.defer()
    await now_command(interaction)

@bot.tree.command(name="volume", description="🔊 تعديل مستوى الصوت (0-200)")
@app_commands.describe(level="مستوى الصوت 0-200")
async def slash_volume(interaction: discord.Interaction, level: int):
    await interaction.response.defer()
    await volume_command(interaction, level)

@bot.tree.command(name="loop", description="🔄 تفعيل/تعطيل تكرار الأغنية")
async def slash_loop(interaction: discord.Interaction):
    await interaction.response.defer()
    await loop_command(interaction)

@bot.tree.command(name="loopqueue", description="🔄 تفعيل/تعطيل تكرار القائمة")
async def slash_loopqueue(interaction: discord.Interaction):
    await interaction.response.defer()
    await loopqueue_command(interaction)

@bot.tree.command(name="shuffle", description="🔀 خلط قائمة الانتظار")
async def slash_shuffle(interaction: discord.Interaction):
    await interaction.response.defer()
    await shuffle_command(interaction)

@bot.tree.command(name="clear", description="🧹 مسح قائمة الانتظار")
async def slash_clear(interaction: discord.Interaction):
    await interaction.response.defer()
    await clear_command(interaction)

@bot.tree.command(name="remove", description="🗑️ حذف أغنية من القائمة")
@app_commands.describe(index="رقم الأغنية")
async def slash_remove(interaction: discord.Interaction, index: int):
    await interaction.response.defer()
    await remove_command(interaction, index)

@bot.tree.command(name="history", description="📜 عرض سجل التشغيل")
async def slash_history(interaction: discord.Interaction):
    await interaction.response.defer()
    await history_command(interaction)

@bot.tree.command(name="ping", description="🏓 سرعة الاستجابة")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.defer()
    await ping_command(interaction)

@bot.tree.command(name="help", description="📖 عرض قائمة الأوامر")
async def slash_help(interaction: discord.Interaction):
    await interaction.response.defer()
    await help_command(interaction)

@bot.tree.command(name="move", description="🔀 نقل أغنية في القائمة")
@app_commands.describe(from_index="الرقم الحالي", to_index="الرقم الجديد")
async def slash_move(interaction: discord.Interaction, from_index: int, to_index: int):
    await interaction.response.defer()
    await move_command(interaction, from_index, to_index)

@bot.tree.command(name="autoplay", description="🎯 تفعيل/تعطيل التشغيل التلقائي")
async def slash_autoplay(interaction: discord.Interaction):
    await interaction.response.defer()
    await autoplay_command(interaction)

# ============ وظائف الأوامر ============

def get_guild_id(ctx_or_interaction):
    if isinstance(ctx_or_interaction, discord.Interaction):
        return ctx_or_interaction.guild.id
    return ctx_or_interaction.guild.id

def get_user(ctx_or_interaction):
    if isinstance(ctx_or_interaction, discord.Interaction):
        return ctx_or_interaction.user
    return ctx_or_interaction.author

def get_respond(ctx_or_interaction):
    if isinstance(ctx_or_interaction, discord.Interaction):
        return ctx_or_interaction.followup.send
    return ctx_or_interaction.send

async def play_command(ctx_or_interaction, query):
    user = get_user(ctx_or_interaction)
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)

    if not user.voice:
        return await respond("⚠️ يجب أن تكون في روم صوتي!")

    if guild_id not in servers_data:
        servers_data[guild_id] = ServerData()

    server = servers_data[guild_id]

    if not server.voice_client or not server.voice_client.is_connected():
        try:
            server.voice_client = await user.voice.channel.connect()
            logger.info(f'🎤 دخلت روم {user.voice.channel.name}')
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
                            'views': entry.get('view_count', 0),
                            'likes': entry.get('like_count', 0),
                        })
            else:
                songs.append({
                    'title': info.get('title', 'Unknown'),
                    'url': info.get('webpage_url', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'thumbnail': info.get('thumbnail', ''),
                    'views': info.get('view_count', 0),
                    'likes': info.get('like_count', 0),
                })

            if not songs:
                return await msg.edit(content="❌ لم يتم العثور على نتائج!")

            for song in songs:
                server.queue.append(song)
                server.history.append(song)

            if not server.is_playing:
                await play_next(guild_id)
                await msg.edit(content=f"🎵 **بدأ التشغيل:** {songs[0]['title']} [{format_duration(songs[0]['duration'])}]")
            else:
                await msg.edit(content=f"✅ **تمت الإضافة:** {songs[0]['title']} [{format_duration(songs[0]['duration'])}]\n📊 القائمة: {len(server.queue)} أغانٍ")

    except Exception as e:
        logger.error(f"خطأ: {e}")
        await msg.edit(content=f"❌ خطأ: {str(e)[:200]}")

async def skip_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server or not server.is_playing:
        return await respond("❌ لا توجد أغنية!")

    if server.voice_client:
        server.voice_client.stop()
    await respond("⏭️ تم التخطي")

async def stop_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server:
        return await respond("❌ البوت غير متصل!")

    server.queue.clear()
    server.is_playing = False
    server.current = None

    if server.voice_client:
        await server.voice_client.disconnect()

    servers_data.pop(guild_id, None)
    await respond("⏹️ تم الإيقاف وطرد البوت")

async def pause_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if server and server.voice_client and server.voice_client.is_playing():
        server.voice_client.pause()
        await respond("⏸️ توقف مؤقت")
    else:
        await respond("❌ لا توجد أغنية مشغلة!")

async def resume_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if server and server.voice_client and server.voice_client.is_paused():
        server.voice_client.resume()
        await respond("▶️ استئناف")
    else:
        await respond("❌ لا توجد أغنية موقفة!")

async def queue_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server or not server.queue:
        return await respond("📭 القائمة فارغة")

    text = f"**📋 قائمة الانتظار ({len(server.queue)} أغنية):**\n"
    text += "─" * 30 + "\n"

    for i, song in enumerate(server.queue, 1):
        dur = format_duration(song.get('duration', 0))
        text += f"`{i:2d}.` {song['title'][:45]} `[{dur}]`\n"
        if len(text) > 1800:
            text += f"\n... و {len(server.queue) - i} أغانٍ أخرى"
            break

    await respond(text)

async def now_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server or not server.current:
        return await respond("❌ لا توجد أغنية!")

    song = server.current
    embed = discord.Embed(
        title="🎵 الآن يعمل",
        description=f"**{song['title']}**",
        color=0x00ff00
    )
    embed.add_field(name="🎤 المقدم", value=song.get('uploader', 'Unknown'), inline=True)
    embed.add_field(name="⏱️ المدة", value=format_duration(song.get('duration', 0)), inline=True)
    embed.add_field(name="📊 القائمة", value=f"{len(server.queue)} أغانٍ", inline=True)

    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])

    await respond(embed=embed)

async def volume_command(ctx_or_interaction, level):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server:
        return await respond("❌ البوت غير متصل!")

    if not 0 <= level <= 200:
        return await respond("⚠️ أدخل قيمة بين 0 و 200")

    server.volume = level / 100
    if server.voice_client and server.voice_client.source:
        server.voice_client.source.volume = server.volume

    await respond(f"🔊 تم ضبط الصوت إلى {level}%")

async def loop_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server or not server.current:
        return await respond("❌ لا توجد أغنية!")

    server.loop = not server.loop
    status = "🔄 مفعل" if server.loop else "⏹️ معطل"
    await respond(f"{status} تكرار الأغنية")

async def loopqueue_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server:
        return await respond("❌ البوت غير متصل!")

    server.loop_queue = not server.loop_queue
    status = "🔄 مفعل" if server.loop_queue else "⏹️ معطل"
    await respond(f"{status} تكرار القائمة")

async def shuffle_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server or len(server.queue) < 2:
        return await respond("❌ لا يوجد ما يكفي من الأغاني للخلط!")

    q = list(server.queue)
    random.shuffle(q)
    server.queue = deque(q)
    await respond("🔀 تم خلط القائمة عشوائياً!")

async def clear_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if server and server.queue:
        server.queue.clear()
        await respond("🧹 تم مسح القائمة بالكامل")
    else:
        await respond("❌ القائمة فارغة بالفعل!")

async def remove_command(ctx_or_interaction, index):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server or not server.queue:
        return await respond("❌ القائمة فارغة!")

    if 1 <= index <= len(server.queue):
        removed = server.queue[index - 1]
        del server.queue[index - 1]
        await respond(f"🗑️ تم حذف **{removed['title']}** من القائمة")
    else:
        await respond(f"⚠️ أدخل رقم بين 1 و {len(server.queue)}")

async def history_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server or not server.history:
        return await respond("📭 سجل التشغيل فارغ!")

    text = "**📜 سجل التشغيل (آخر 50):**\n"
    text += "─" * 30 + "\n"

    for i, song in enumerate(server.history, 1):
        text += f"`{i:2d}.` {song['title'][:50]}\n"
        if len(text) > 1800:
            break

    await respond(text)

async def ping_command(ctx_or_interaction):
    respond = get_respond(ctx_or_interaction)
    latency = round(bot.latency * 1000)
    color = 0x00ff00 if latency < 100 else 0xffaa00 if latency < 300 else 0xff0000
    embed = discord.Embed(title="🏓 Pong!", description=f"**{latency}ms**", color=color)
    await respond(embed=embed)

async def help_command(ctx_or_interaction):
    respond = get_respond(ctx_or_interaction)
    embed = discord.Embed(
        title="🎵 قائمة الأوامر",
        description=f"البادئة: `{PREFIX}` أو `/`",
        color=0x3498db
    )

    cmds = {
        "🎵 التشغيل": "`play` / `p` - تشغيل أغنية\n`skip` / `s` - تخطي",
        "⏯️ التحكم": "`pause` - إيقاف مؤقت\n`resume` - استئناف\n`stop` - إيقاف وطرد",
        "📋 القائمة": "`queue` / `q` - عرض القائمة\n`clear` - مسح القائمة\n`shuffle` - خلط القائمة\n`remove` - حذف أغنية\n`move` - نقل أغنية",
        "⚙️ الإعدادات": "`volume` - ضبط الصوت\n`loop` - تكرار الأغنية\n`loopqueue` - تكرار القائمة\n`autoplay` - تشغيل تلقائي",
        "📊 المعلومات": "`now` / `np` - الأغنية الحالية\n`history` - سجل التشغيل\n`ping` - سرعة البوت"
    }

    for category, cmds_text in cmds.items():
        embed.add_field(name=category, value=cmds_text, inline=False)

    await respond(embed=embed)

async def move_command(ctx_or_interaction, from_index, to_index):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server or not server.queue:
        return await respond("❌ القائمة فارغة!")

    q = list(server.queue)
    if not (1 <= from_index <= len(q) and 1 <= to_index <= len(q)):
        return await respond(f"⚠️ أدخل أرقام بين 1 و {len(q)}")

    song = q.pop(from_index - 1)
    q.insert(to_index - 1, song)
    server.queue = deque(q)
    await respond(f"✅ تم نقل **{song['title']}** من {from_index} إلى {to_index}")

async def autoplay_command(ctx_or_interaction):
    guild_id = get_guild_id(ctx_or_interaction)
    respond = get_respond(ctx_or_interaction)
    server = servers_data.get(guild_id)

    if not server:
        return await respond("❌ البوت غير متصل!")

    server.autoplay = not getattr(server, 'autoplay', False)
    status = "✅ مفعل" if server.autoplay else "❌ معطل"
    await respond(f"🎯 التشغيل التلقائي: {status}")

# ============ أوامر البادئة ============

@bot.command(name='play', aliases=['p', 'تشغيل'])
async def prefix_play(ctx, *, query):
    await play_command(ctx, query)

@bot.command(name='skip', aliases=['s', 'تخطي'])
async def prefix_skip(ctx):
    await skip_command(ctx)

@bot.command(name='stop', aliases=['توقف'])
async def prefix_stop(ctx):
    await stop_command(ctx)

@bot.command(name='pause', aliases=['إيقاف'])
async def prefix_pause(ctx):
    await pause_command(ctx)

@bot.command(name='resume', aliases=['استئناف'])
async def prefix_resume(ctx):
    await resume_command(ctx)

@bot.command(name='queue', aliases=['q', 'قائمة'])
async def prefix_queue(ctx):
    await queue_command(ctx)

@bot.command(name='now', aliases=['np', 'الحالية'])
async def prefix_now(ctx):
    await now_command(ctx)

@bot.command(name='volume', aliases=['vol', 'صوت'])
async def prefix_volume(ctx, level: int = None):
    if level is None:
        server = servers_data.get(ctx.guild.id)
        if server:
            await ctx.send(f"🔊 مستوى الصوت الحالي: {int(server.volume * 100)}%")
        else:
            await ctx.send("❌ البوت غير متصل!")
        return
    await volume_command(ctx, level)

@bot.command(name='loop', aliases=['تكرار'])
async def prefix_loop(ctx):
    await loop_command(ctx)

@bot.command(name='loopqueue', aliases=['lq', 'تكرارقائمة'])
async def prefix_loopqueue(ctx):
    await loopqueue_command(ctx)

@bot.command(name='shuffle', aliases=['خلط'])
async def prefix_shuffle(ctx):
    await shuffle_command(ctx)

@bot.command(name='clear', aliases=['مسح'])
async def prefix_clear(ctx):
    await clear_command(ctx)

@bot.command(name='remove', aliases=['rm', 'حذف'])
async def prefix_remove(ctx, index: int):
    await remove_command(ctx, index)

@bot.command(name='history', aliases=['سجل'])
async def prefix_history(ctx):
    await history_command(ctx)

@bot.command(name='ping')
async def prefix_ping(ctx):
    await ping_command(ctx)

@bot.command(name='help', aliases=['مساعدة'])
async def prefix_help(ctx):
    await help_command(ctx)

@bot.command(name='move', aliases=['نقل'])
async def prefix_move(ctx, from_idx: int, to_idx: int):
    await move_command(ctx, from_idx, to_idx)

@bot.command(name='autoplay', aliases=['تلقائي'])
async def prefix_autoplay(ctx):
    await autoplay_command(ctx)

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

        source = discord.FFmpegOpusAudio(
            audio_url,
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -analyzeduration 0 -loglevel panic',
            options=f'-vn -b:a 192k -af "volume={server.volume}"'
        )

        def after_callback(error):
            if error:
                logger.error(f"خطأ في التشغيل: {error}")
            asyncio.run_coroutine_threadsafe(handle_after(guild_id, error), bot.loop)

        server.voice_client.play(source, after=after_callback)
        server.is_playing = True

        # تحديث حالة البوت
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{song['title'][:30]}"
        ))

        logger.info(f'🎵 تشغيل: {song["title"]}')

    except Exception as e:
        logger.error(f"خطأ في play_next: {e}")
        if server.queue:
            server.queue.popleft()
        await play_next(guild_id)

async def handle_after(guild_id, error):
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
    if hrs:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"
    
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
    'cookiefile': 'cookies.txt',  # <--- أضف هذا السطر
}

# ============ التشغيل ============

if __name__ == "__main__":
    logger.info("🚀 جاري تشغيل البوت...")
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error("❌ التوكن غير صحيح! تأكد من متغير TOKEN في Railway")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
