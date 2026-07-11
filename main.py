import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio

# ======== قراءة التوكن ========
TOKEN = os.getenv('DISCORD_TOKEN')

if TOKEN is None:
    print("❌ خطأ: لم يتم العثور على DISCORD_TOKEN في متغيرات البيئة.")
    exit()

# ======== إعدادات البوت ========
ALLOWED_ROLE_NAME = "k"
STREAM_LINK = "https://www.twitch.tv/king"
STREAM_NAME = "KINGS!"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def has_allowed_role(interaction: discord.Interaction) -> bool:
    return any(role.name == ALLOWED_ROLE_NAME for role in interaction.user.roles)

# ============================================
# الأمر: يطلب منك كتابة الرسالة في الخاص
# ============================================
@tree.command(
    name="send",
    description="إرسال رسالة للجميع في الخاص مع مسافات وأسطر جديدة"
)
@app_commands.describe(
    gap="المسافة (الإشارة) مثل: --- أو === (اختياري)"
)
async def send(
    interaction: discord.Interaction,
    gap: str = "---"
):
    if not has_allowed_role(interaction):
        await interaction.response.send_message(
            f"❌ ليس لديك الصلاحية. تحتاج إلى رتبة `{ALLOWED_ROLE_NAME}`.",
            ephemeral=True
        )
        return

    # إحصاء الأعضاء
    total_members = len(interaction.guild.members)
    members_without_bots = len([m for m in interaction.guild.members if not m.bot])

    await interaction.response.send_message(
        f"📝 **أرسل لي الرسالة في الخاص (DM) مع المسافات التي تريدها.**\n"
        f"📊 سيتم إرسالها لـ **{members_without_bots}** عضو.\n"
        f"⏳ لديك **دقيقتين** لكتابة الرسالة.\n"
        f"📌 اكتب الرسالة كاملة مع الأسطر الجديدة ثم أرسلها لي في الخاص.",
        ephemeral=True
    )

    # انتظار الرسالة من المستخدم في الخاص
    def check(m):
        return m.author == interaction.user and isinstance(m.channel, discord.DMChannel)

    try:
        # إرسال رسالة للمستخدم في الخاص ليبدأ الكتابة
        await interaction.user.send(
            f"✏️ **اكتب الرسالة التي تريد إرسالها للجميع.**\n"
            f"يمكنك استخدام الأسطر الجديدة (Enter) بحرية.\n"
            f"⏳ لديك دقيقتين.\n\n"
            f"📌 **عند الانتهاء، أرسل الرسالة لي.**"
        )
        
        msg = await bot.wait_for("message", timeout=120.0, check=check)
        message_content = msg.content

    except asyncio.TimeoutError:
        await interaction.followup.send("❌ انتهى الوقت. أعد المحاولة.", ephemeral=True)
        return

    # تنسيق الرسالة مع المسافة
    formatted_message = f"{gap}\n\n{message_content}\n\n{gap}"
    
    # معاينة
    preview = formatted_message[:500] + ("..." if len(formatted_message) > 500 else "")
    
    await interaction.followup.send(
        f"📝 **معاينة الرسالة:**\n```\n{preview}\n```\n\n"
        f"📨 سيتم إرسالها لـ **{members_without_bots}** عضو في الخاص.\n"
        f"**اكتب `confirm` خلال 30 ثانية للتأكيد.**",
        ephemeral=True
    )

    # انتظار التأكيد
    def confirm_check(m):
        return m.author == interaction.user and m.channel == interaction.channel and m.content.lower() == "confirm"

    try:
        await bot.wait_for("message", timeout=30.0, check=confirm_check)
    except asyncio.TimeoutError:
        await interaction.followup.send("❌ تم الإلغاء.", ephemeral=True)
        return

    # بدء الإرسال
    await interaction.followup.send(f"✅ جارٍ الإرسال إلى {members_without_bots} عضو...", ephemeral=True)

    success = 0
    failed = 0

    for member in interaction.guild.members:
        if member.bot:
            continue

        try:
            await member.send(formatted_message)
            success += 1
            await asyncio.sleep(0.5)
        except:
            failed += 1

        if (success + failed) % 50 == 0:
            print(f"[*] تقدم: {success + failed}/{members_without_bots}")

    await interaction.followup.send(
        f"✅ **تم الانتهاء!**\n"
        f"✅ نجح: {success}\n"
        f"❌ فشل: {failed}\n"
        f"📊 المجموع: {members_without_bots}",
        ephemeral=True
    )

# ============================================
# تشغيل البوت
# ============================================
@bot.event
async def on_ready():
    await tree.sync()
    
    await bot.change_presence(
        activity=discord.Streaming(
            name=STREAM_NAME,
            url=STREAM_LINK
        )
    )
    
    print(f"[+] Bot is ready as {bot.user}")
    print(f"[+] Slash commands synced!")

bot.run(TOKEN)
