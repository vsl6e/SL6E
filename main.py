import discord
from discord.ext import commands
import yt_dlp as ytdlp
import asyncio
import os
import json
from collections import deque
import logging

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('MusicBot')

# تحميل الإعدادات من ملف إن وجد
CONFIG_FILE = 'config.json'
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
else:
    config = {
        'token': 'YOUR_BOT_TOKEN_HERE',
        'prefix': '!',
        'volume': 0.5,
        'max_queue': 100
    }

TOKEN = config.get('token', 'YOUR_BOT_TOKEN_HERE')
PREFIX = config.get('prefix', '!')

# إعدادات البوت
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# إعدادات yt-dlp للتشغيل بدون تحميل
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'quiet': True,
    'no_warnings': True,
    'extractaudio': True,
    'audioformat': 'mp3',
    'restrictfilenames': True,
    'noplaylist': False,  # نعم للقوائم
    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
    'proxy': config.get('proxy', None),
}

# هيكل البيانات
servers_data = {}

class ServerData:
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.voice_client = None
        self.is_playing = False
        self.is_paused = False
        self.volume = config.get('volume', 0.5)
        self.loop = False
        self.loop_queue = False
        self.history = deque(maxlen=50)  # حفظ آخر 50 أغنية

# ============ الأوامر الأساسية ============

@bot.event
async def on_ready():
    logger.info(f'✅ البوت جاهز كـ {bot.user.name} (ID: {bot.user.id})')
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}play | {len(bot.guilds)} سيرفر"))

@bot.event
async def on_guild_join(guild):
    logger.info(f'انضممت إلى سيرفر جديد: {guild.name}')
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}play | {len(bot.guilds)} سيرفر"))

@bot.command(name='play', aliases=['p', 'تشغيل'])
async def play(ctx, *, query=None):
    """تشغيل أغنية من يوتيوب أو رابط أو بحث"""
    if not query:
        return await ctx.send("❌ أدخل اسم أغنية أو رابط!")
    
    if not ctx.author.voice:
        return await ctx.send("⚠️ يجب أن تكون في روم صوتي!")
    
    # تهيئة بيانات السيرفر
    if ctx.guild.id not in servers_data:
        servers_data[ctx.guild.id] = ServerData()
    
    server = servers_data[ctx.guild.id]
    
    # الانضمام للروم الصوتي
    if not server.voice_client or not server.voice_client.is_connected():
        try:
            server.voice_client = await ctx.author.voice.channel.connect()
        except Exception as e:
            logger.error(f"خطأ في الانضمام: {e}")
            return await ctx.send(f"❌ فشل الانضمام للروم: {str(e)[:100]}")
    
    # جلب معلومات الأغنية
    msg = await ctx.send(f"🔍 جاري البحث عن: **{query}** ...")
    
    try:
        songs = await fetch_songs(query)
        if not songs:
            return await msg.edit(content="❌ لم يتم العثور على نتائج!")
        
        # إضافة الأغاني للقائمة
        for song in songs:
            server.queue.append(song)
            server.history.append(song)
        
        total = len(songs)
        first_song = songs[0]
        
        if not server.is_playing:
            await play_next(ctx.guild.id)
            await msg.edit(content=f"🎵 بدأت تشغيل: **{first_song['title']}**")
        else:
            await msg.edit(content=f"✅ تمت إضافة {total} أغنية{' (قائمة)' if total > 1 else ''} إلى القائمة")
            
    except Exception as e:
        logger.error(f"خطأ في play: {e}")
        await msg.edit(content=f"❌ حدث خطأ: {str(e)[:200]}")

@bot.command(name='skip', aliases=['s', 'تخطي'])
async def skip(ctx):
    """تخطي الأغنية الحالية"""
    server = servers_data.get(ctx.guild.id)
    if not server or not server.is_playing:
        return await ctx.send("❌ لا توجد أغنية حالياً!")
    
    if server.voice_client and server.voice_client.is_playing():
        server.voice_client.stop()
    
    await ctx.send("⏭️ تم تخطي الأغنية")

@bot.command(name='stop', aliases=['توقف'])
async def stop(ctx):
    """إيقاف التشغيل وطرد البوت"""
    server = servers_data.get(ctx.guild.id)
    if not server:
        return await ctx.send("❌ البوت غير متصل بأي روم!")
    
    server.queue.clear()
    server.is_playing = False
    server.current = None
    
    if server.voice_client:
        await server.voice_client.disconnect()
    
    servers_data.pop(ctx.guild.id, None)
    await ctx.send("⏹️ تم الإيقاف وطرد البوت")

@bot.command(name='queue', aliases=['q', 'قائمة'])
async def show_queue(ctx):
    """عرض قائمة الانتظار"""
    server = servers_data.get(ctx.guild.id)
    if not server or not server.queue:
        return await ctx.send("📭 قائمة الانتظار فارغة")
    
    queue_text = f"**📋 قائمة الانتظار ({len(server.queue)} أغنية):**\n"
    queue_text += "─" * 30 + "\n"
    
    for i, song in enumerate(server.queue, 1):
        duration = format_duration(song.get('duration', 0))
        queue_text += f"`{i:2d}.` {song['title'][:50]} `[{duration}]`\n"
        if len(queue_text) > 1800:
            queue_text += f"\n... و {len(server.queue) - i} أغانٍ أخرى"
            break
    
    await ctx.send(queue_text)

@bot.command(name='now', aliases=['np', 'الحالية'])
async def now_playing(ctx):
    """عرض الأغنية الحالية"""
    server = servers_data.get(ctx.guild.id)
    if not server or not server.current:
        return await ctx.send("❌ لا توجد أغنية حالياً!")
    
    song = server.current
    embed = discord.Embed(
        title="🎵 الآن يعمل",
        description=f"**[{song['title']}]({song.get('webpage_url', '')})**",
        color=0x00ff00
    )
    embed.add_field(name="🎤 المقدم", value=song.get('uploader', 'Unknown'), inline=True)
    embed.add_field(name="⏱️ المدة", value=format_duration(song.get('duration', 0)), inline=True)
    embed.add_field(name="📊 الترتيب", value=f"{len(server.queue)} أغانٍ في القائمة", inline=True)
    
    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])
    
    embed.set_footer(text=f"طلب من {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
    await ctx.send(embed=embed)

@bot.command(name='pause', aliases=['إيقاف'])
async def pause(ctx):
    """إيقاف مؤقت"""
    server = servers_data.get(ctx.guild.id)
    if server and server.voice_client and server.voice_client.is_playing():
        server.voice_client.pause()
        server.is_paused = True
        await ctx.send("⏸️ تم الإيقاف المؤقت")
    else:
        await ctx.send("❌ لا توجد أغنية مشغلة!")

@bot.command(name='resume', aliases=['استئناف'])
async def resume(ctx):
    """استئناف التشغيل"""
    server = servers_data.get(ctx.guild.id)
    if server and server.voice_client and server.is_paused:
        server.voice_client.resume()
        server.is_paused = False
        await ctx.send("▶️ تم استئناف التشغيل")
    else:
        await ctx.send("❌ لا توجد أغنية موقفة!")

@bot.command(name='volume', aliases=['vol', 'صوت'])
async def set_volume(ctx, level: int = None):
    """تعديل مستوى الصوت (0-100)"""
    server = servers_data.get(ctx.guild.id)
    if not server:
        return await ctx.send("❌ البوت غير متصل بأي روم!")
    
    if level is None:
        return await ctx.send(f"🔊 مستوى الصوت الحالي: {int(server.volume * 100)}%")
    
    if not 0 <= level <= 100:
        return await ctx.send("⚠️ أدخل قيمة بين 0 و 100")
    
    server.volume = level / 100
    if server.voice_client and server.voice_client.source:
        server.voice_client.source.volume = server.volume
    
    # حفظ الإعداد
    config['volume'] = server.volume
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    
    await ctx.send(f"🔊 تم ضبط الصوت إلى {level}%")

@bot.command(name='loop', aliases=['تكرار'])
async def loop(ctx):
    """تفعيل/إلغاء تكرار الأغنية الحالية"""
    server = servers_data.get(ctx.guild.id)
    if not server or not server.current:
        return await ctx.send("❌ لا توجد أغنية حالياً!")
    
    server.loop = not server.loop
    status = "🔄 مفعل" if server.loop else "⏹️ معطل"
    await ctx.send(f"{status} تكرار الأغنية")

@bot.command(name='loopqueue', aliases=['lq', 'تكرارقائمة'])
async def loop_queue(ctx):
    """تفعيل/إلغاء تكرار قائمة الانتظار"""
    server = servers_data.get(ctx.guild.id)
    if not server:
        return await ctx.send("❌ البوت غير متصل بأي روم!")
    
    server.loop_queue = not server.loop_queue
    status = "🔄 مفعل" if server.loop_queue else "⏹️ معطل"
    await ctx.send(f"{status} تكرار القائمة")

@bot.command(name='remove', aliases=['rm', 'حذف'])
async def remove_song(ctx, index: int):
    """حذف أغنية من القائمة برقمها"""
    server = servers_data.get(ctx.guild.id)
    if not server or not server.queue:
        return await ctx.send("❌ القائمة فارغة!")
    
    if 1 <= index <= len(server.queue):
        removed = server.queue[index - 1]
        del server.queue[index - 1]
        await ctx.send(f"🗑️ تم حذف **{removed['title']}** من القائمة")
    else:
        await ctx.send(f"⚠️ أدخل رقم بين 1 و {len(server.queue)}")

@bot.command(name='clear', aliases=['مسح'])
async def clear_queue(ctx):
    """مسح قائمة الانتظار بالكامل"""
    server = servers_data.get(ctx.guild.id)
    if server and server.queue:
        server.queue.clear()
        await ctx.send("🧹 تم مسح القائمة بالكامل")
    else:
        await ctx.send("❌ القائمة فارغة بالفعل!")

@bot.command(name='shuffle', aliases=['خلط'])
async def shuffle_queue(ctx):
    """خلط قائمة الانتظار عشوائياً"""
    import random
    server = servers_data.get(ctx.guild.id)
    if not server or len(server.queue) < 2:
        return await ctx.send("❌ لا يوجد ما يكفي من الأغاني للخلط!")
    
    queue_list = list(server.queue)
    random.shuffle(queue_list)
    server.queue = deque(queue_list)
    await ctx.send("🔀 تم خلط القائمة عشوائياً!")

@bot.command(name='history', aliases=['سجل'])
async def show_history(ctx):
    """عرض سجل الأغاني المشغلة"""
    server = servers_data.get(ctx.guild.id)
    if not server or not server.history:
        return await ctx.send("📭 سجل التشغيل فارغ!")
    
    history_text = "**📜 سجل التشغيل (آخر 50):**\n"
    history_text += "─" * 30 + "\n"
    
    for i, song in enumerate(server.history, 1):
        history_text += f"`{i:2d}.` {song['title'][:50]}\n"
        if len(history_text) > 1800:
            break
    
    await ctx.send(history_text)

@bot.command(name='help', aliases=['مساعدة'])
async def help_command(ctx):
    """عرض قائمة الأوامر"""
    embed = discord.Embed(
        title="🎵 قائمة أوامر بوت الموسيقى",
        description="جميع الأوامر المتاحة",
        color=0x3498db
    )
    
    commands_list = {
        "🎵 التشغيل": "`play` / `p` - تشغيل أغنية\n`skip` / `s` - تخطي الأغنية",
        "⏯️ التحكم": "`pause` - إيقاف مؤقت\n`resume` - استئناف\n`stop` - إيقاف وطرد البوت",
        "📋 القائمة": "`queue` / `q` - عرض القائمة\n`remove` - حذف أغنية\n`clear` - مسح القائمة\n`shuffle` - خلط القائمة",
        "⚙️ الإعدادات": "`volume` - ضبط الصوت\n`loop` - تكرار الأغنية\n`loopqueue` - تكرار القائمة",
        "📊 المعلومات": "`now` / `np` - الأغنية الحالية\n`history` - سجل التشغيل\n`ping` - سرعة البوت"
    }
    
    for category, cmds in commands_list.items():
        embed.add_field(name=category, value=cmds, inline=False)
    
    embed.set_footer(text=f"طلب من {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
    await ctx.send(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    """سرعة الاستجابة"""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"سرعة الاستجابة: **{latency}ms**",
        color=0x00ff00 if latency < 100 else 0xffaa00 if latency < 300 else 0xff0000
    )
    await ctx.send(embed=embed)

# ============ وظائف مساعدة ============

async def fetch_songs(query):
    """جلب الأغاني من يوتيوب"""
    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            
            songs = []
            if 'entries' in info:  # قائمة تشغيل
                for entry in info['entries']:
                    if entry:
                        songs.append({
                            'title': entry.get('title', 'Unknown'),
                            'webpage_url': entry.get('webpage_url', ''),
                            'duration': entry.get('duration', 0),
                            'uploader': entry.get('uploader', 'Unknown'),
                            'thumbnail': entry.get('thumbnail', ''),
                            'url': entry.get('url', ''),
                        })
            else:  # أغنية واحدة
                songs.append({
                    'title': info.get('title', 'Unknown'),
                    'webpage_url': info.get('webpage_url', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'thumbnail': info.get('thumbnail', ''),
                    'url': info.get('url', ''),
                })
            
            return songs
    except Exception as e:
        logger.error(f"خطأ في fetch_songs: {e}")
        raise

async def play_next(guild_id):
    """تشغيل الأغنية التالية في القائمة"""
    server = servers_data.get(guild_id)
    if not server or not server.queue:
        server.is_playing = False
        server.current = None
        return
    
    # تكرار الأغنية
    if server.loop and server.current:
        server.queue.appendleft(server.current)
    
    # تكرار القائمة
    if not server.queue and server.loop_queue:
        # إعادة القائمة من السجل
        if server.history:
            server.queue = deque(list(server.history)[-10:])  # آخر 10 أغاني
    
    if not server.queue:
        server.is_playing = False
        server.current = None
        return
    
    song = server.queue[0]
    server.current = song
    
    try:
        # جلب رابط الصوت
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song['webpage_url'], download=False)
            audio_url = info['url']
        
        # إنشاء مصدر الصوت
        source = discord.FFmpegOpusAudio(
            audio_url,
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options=f'-filter:a "volume={server.volume}"'
        )
        
        # تشغيل
        server.voice_client.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                handle_after(guild_id, e),
                bot.loop
            )
        )
        server.is_playing = True
        server.is_paused = False
        
        logger.info(f'🎵 جاري التشغيل: {song["title"]} في {bot.get_guild(guild_id).name}')
        
    except Exception as e:
        logger.error(f"خطأ في play_next: {e}")
        if server.queue:
            server.queue.popleft()
        await play_next(guild_id)

async def handle_after(guild_id, error):
    """معالجة بعد انتهاء الأغنية"""
    if error:
        logger.error(f"خطأ في التشغيل: {error}")
    
    server = servers_data.get(guild_id)
    if not server:
        return
    
    # حذف الأغنية الحالية
    if not server.loop and server.queue:
        server.queue.popleft()
    
    server.is_playing = False
    await play_next(guild_id)

def format_duration(seconds):
    """تنسيق المدة الزمنية"""
    if not seconds:
        return "0:00"
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"

# ============ تشغيل البوت ============

if __name__ == "__main__":
    if TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("⚠️ يرجى إضافة توكن البوت في ملف config.json أو مباشرة في الكود!")
        print("قم بإنشاء ملف config.json بالمحتوى:")
        print('{"token": "YOUR_BOT_TOKEN_HERE", "prefix": "!"}')
        exit()
    
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info("تم إيقاف البوت")
    except Exception as e:
        logger.error(f"خطأ في التشغيل: {e}")
