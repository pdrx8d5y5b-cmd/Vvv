# 🔥 Uniq — بوت الأنمي v1.0 Pro Edition
# التعرف التلقائي على الصور + نظام النشر التلقائي
# مُصلّح ومُحسّن بالكامل

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import os
import json
import base64
import io
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict

# إعداد الـ logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('Uniq')

TOKEN = os.getenv("TOKEN")
SAUCENAO_API_KEY = "c7626f0f3cb1519513dea1ca5d2a2f307d2a5327"

# ═══════════════════════════════════════════════════════════════
# 📁 FILE PATHS
# ═══════════════════════════════════════════════════════════════

DATA_DIR = "/home/ubuntu/data"
CHANNELS_FILE = f"{DATA_DIR}/channels.json"
CACHE_FILE = f"{DATA_DIR}/cache.json"
RECOGNITION_CHANNEL_FILE = f"{DATA_DIR}/recognition_channel.json"

os.makedirs(DATA_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 💾 DATABASE
# ═══════════════════════════════════════════════════════════════

@dataclass
class ChannelConfig:
    channel_id: int
    category: str
    enabled: bool = True
    last_news_id: str = ""
    notification_role_id: Optional[int] = None
    notification_msg_id: Optional[int] = None

class Database:
    def __init__(self):
        self.channels: Dict[int, ChannelConfig] = {}
        self.notification_users: Dict[int, List[int]] = {}
        self.recognition_channel_id: Optional[int] = None
        self.last_anime_news_id: str = ""
        self.load()

    def load(self):
        try:
            if os.path.exists(CHANNELS_FILE):
                with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.get('channels', {}).items():
                        self.channels[int(k)] = ChannelConfig(**v)
                    self.notification_users = data.get('notifications', {})

            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                    self.last_anime_news_id = cache.get('last_anime_news_id', '')

            if os.path.exists(RECOGNITION_CHANNEL_FILE):
                with open(RECOGNITION_CHANNEL_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.recognition_channel_id = data.get('channel_id')

            logger.info("✅ تم تحميل البيانات بنجاح")
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل البيانات: {e}")

    def save(self):
        try:
            data = {
                'channels': {str(k): asdict(v) for k, v in self.channels.items()},
                'notifications': self.notification_users
            }
            with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            cache = {'last_anime_news_id': self.last_anime_news_id}
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

            recognition_data = {'channel_id': self.recognition_channel_id}
            with open(RECOGNITION_CHANNEL_FILE, 'w', encoding='utf-8') as f:
                json.dump(recognition_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"❌ خطأ في حفظ البيانات: {e}")

    def set_recognition_channel(self, channel_id: int):
        self.recognition_channel_id = channel_id
        self.save()

    def clear_recognition_channel(self):
        self.recognition_channel_id = None
        self.save()

    def add_channel(self, channel_id: int, category: str, role_id: int = None):
        self.channels[channel_id] = ChannelConfig(
            channel_id=channel_id,
            category=category,
            notification_role_id=role_id
        )
        self.notification_users[channel_id] = []
        self.save()

    def remove_channel(self, channel_id: int):
        if channel_id in self.channels:
            del self.channels[channel_id]
        if channel_id in self.notification_users:
            del self.notification_users[channel_id]
        self.save()

    def get_channels(self, category: str = None) -> List[ChannelConfig]:
        if category:
            return [c for c in self.channels.values() if c.category == category and c.enabled]
        return [c for c in self.channels.values() if c.enabled]

    def add_notification_user(self, channel_id: int, user_id: int):
        if channel_id not in self.notification_users:
            self.notification_users[channel_id] = []
        if user_id not in self.notification_users[channel_id]:
            self.notification_users[channel_id].append(user_id)
            self.save()

    def remove_notification_user(self, channel_id: int, user_id: int):
        if channel_id in self.notification_users:
            if user_id in self.notification_users[channel_id]:
                self.notification_users[channel_id].remove(user_id)
                self.save()

    def is_user_subscribed(self, channel_id: int, user_id: int) -> bool:
        return user_id in self.notification_users.get(channel_id, [])

db = Database()

# ═══════════════════════════════════════════════════════════════
# 🌐 API CONFIGURATION & FUNCTIONS
# ═══════════════════════════════════════════════════════════════

JIKAN_BASE = "https://api.jikan.moe/v4"
TRACE_MOE_URL = "https://api.trace.moe/search"
SAUCENAO_URL = "https://saucenao.com/search.php"

_rate_limiter = asyncio.Semaphore(1)
_jikan_cache = {}

async def jikan_get(endpoint: str, use_cache: bool = True) -> Optional[dict]:
    global _jikan_cache
    if use_cache and endpoint in _jikan_cache:
        data, timestamp = _jikan_cache[endpoint]
        if datetime.now().timestamp() - timestamp < 120:
            return data

    async with _rate_limiter:
        await asyncio.sleep(0.4)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{JIKAN_BASE}{endpoint}", timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.json()
                        _jikan_cache[endpoint] = (data, datetime.now().timestamp())
                        return data
        except Exception as e:
            logger.error(f"❌ خطأ في Jikan API: {e}")
    return None

async def search_anime(query: str, limit: int = 15) -> List[dict]:
    data = await jikan_get(f"/anime?q={query.replace(' ', '%20')}&limit={limit}&sfw=true")
    return data.get("data", []) if data else []

async def search_character(query: str, limit: int = 15) -> List[dict]:
    data = await jikan_get(f"/characters?q={query.replace(' ', '%20')}&limit={limit}&order_by=favorites&sort=desc")
    return data.get("data", []) if data else []

async def get_character_details(mal_id: int) -> Optional[dict]:
    data = await jikan_get(f"/characters/{mal_id}/full")
    return data.get("data") if data else None

async def get_anime_details(mal_id: int) -> Optional[dict]:
    data = await jikan_get(f"/anime/{mal_id}/full")
    return data.get("data") if data else None

async def get_random_anime() -> Optional[dict]:
    data = await jikan_get("/random/anime", use_cache=False)
    return data.get("data") if data else None

async def get_top_anime(limit: int = 10) -> List[dict]:
    data = await jikan_get(f"/top/anime?limit={limit}")
    return data.get("data", []) if data else []

async def get_seasonal_anime(limit: int = 10) -> List[dict]:
    data = await jikan_get(f"/seasons/now?limit={limit}")
    return data.get("data", []) if data else []

async def get_upcoming_anime(limit: int = 10) -> List[dict]:
    data = await jikan_get(f"/seasons/upcoming?limit={limit}")
    return data.get("data", []) if data else []

async def get_airing_anime(limit: int = 15) -> List[dict]:
    data = await jikan_get(f"/top/anime?filter=airing&limit={limit}")
    return data.get("data", []) if data else []

async def get_characters(mal_id: int) -> List[dict]:
    data = await jikan_get(f"/anime/{mal_id}/characters")
    return data.get("data", []) if data else []

async def get_anime_recommendations(mal_id: int, limit: int = 6) -> List[dict]:
    data = await jikan_get(f"/anime/{mal_id}/recommendations")
    return data.get("data", [])[:limit] if data else []

async def saucenao_search(image_data: bytes) -> Optional[dict]:
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field('output_type', '2')
            form.add_field('api_key', SAUCENAO_API_KEY)
            form.add_field('file', image_data, filename='image.jpg', content_type='image/jpeg')
            async with session.post(SAUCENAO_URL, data=form, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
    except Exception as e:
        logger.error(f"❌ خطأ في SauceNAO: {e}")
    return None

async def trace_moe_search(image_data: bytes) -> Optional[dict]:
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field('image', image_data, filename='image.jpg', content_type='image/jpeg')
            async with session.post(TRACE_MOE_URL, data=form, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
    except Exception as e:
        logger.error(f"❌ خطأ في Trace.moe: {e}")
    return None

# ═══════════════════════════════════════════════════════════════
# 🎨 THEME & UTILS
# ═══════════════════════════════════════════════════════════════

class Theme:
    BG = 0x2B2D31
    CARD_BG = 0x313338
    ACCENT = 0x5865F2
    PURPLE = 0x9B59B6
    SUCCESS = 0x2ECC71
    DANGER = 0xE74C3C
    WARNING = 0xF1C40F
    INFO = 0x3498DB

def medal_emoji(rank: int) -> str:
    if rank == 1: return "🥇"
    if rank == 2: return "🥈"
    if rank == 3: return "🥉"
    return "🎬"

def get_image(data: dict, type: str = "default") -> Optional[str]:
    if not data: return None
    images = data.get("images", {})
    if type == "thumbnail":
        return images.get("jpg", {}).get("image_url") or images.get("webp", {}).get("image_url")
    elif type == "banner":
        return data.get("trailer", {}).get("images", {}).get("maximum_image_url")
    return None

def get_char_image(char_data: dict) -> Optional[str]:
    if not char_data: return None
    images = char_data.get("images", {})
    return images.get("jpg", {}).get("image_url") or images.get("webp", {}).get("image_url")

def synopsis_short(anime: dict) -> str:
    synopsis = anime.get("synopsis", "لا يوجد وصف.")
    if synopsis and len(synopsis) > 300:
        return synopsis[:300] + "..."
    return synopsis or "لا يوجد وصف."

def rating_stars(score: float) -> str:
    if not score: return ""
    return "⭐" * int(score // 2)

def year_label(anime: dict) -> str:
    if aired := anime.get("aired", {}).get("prop", {}).get("from", {}).get("year"):
        return str(aired)
    return "—"

def genres_text(anime: dict, limit: int = 3) -> str:
    genres = [g["name"] for g in anime.get("genres", [])][:limit]
    return ", ".join(genres) if genres else "لا يوجد."

def status_label(status: str) -> str:
    labels = {"Finished Airing": "✅ مكتمل", "Currently Airing": "🔄 يعرض حالياً", "Not yet aired": "⏳ لم يعرض بعد"}
    return labels.get(status, status)

def format_number(num: int) -> str:
    return f"{num:,}"

def get_category_emoji(category: str) -> str:
    return {"anime": "🎬", "manga": "📚", "manhwa": "📜"}.get(category, "")

def get_category_color(category: str) -> int:
    return {"anime": Theme.ACCENT, "manga": Theme.PURPLE, "manhwa": Theme.INFO}.get(category, Theme.BG)

def get_category_name(category: str) -> str:
    return {"anime": "الأنمي", "manga": "المانجا", "manhwa": "المانهوا"}.get(category, "")

def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

# ═══════════════════════════════════════════════════════════════
# 📦 EMBED BUILDERS
# ═══════════════════════════════════════════════════════════════

def build_main_embed(anime: dict, prefix: str = "") -> discord.Embed:
    title = anime.get("title", "؟")
    title_jp = anime.get("title_japanese", "")
    mal_id = anime.get("mal_id", 0)
    
    desc = f"🇯🇵 *{title_jp}*\n\n{synopsis_short(anime)}" if title_jp else synopsis_short(anime)
    embed = discord.Embed(title=f"{prefix}{title}", description=desc, color=Theme.CARD_BG, url=anime.get("url"), timestamp=datetime.now(timezone.utc))
    
    if score := anime.get("score"):
        embed.add_field(name="⭐ التقييم", value=f"**{score}/10** {rating_stars(score)}", inline=True)
    if eps := anime.get("episodes"):
        embed.add_field(name="📺 الحلقات", value=f"**{eps}**", inline=True)
    if year := year_label(anime):
        embed.add_field(name="📅 السنة", value=f"**{year}**", inline=True)
    
    embed.add_field(name="🎭 التصنيفات", value=genres_text(anime, 5), inline=False)
    if status := anime.get("status"):
        embed.add_field(name="🏷️ الحالة", value=status_label(status), inline=True)
    
    if thumb := get_image(anime, "thumbnail"):
        embed.set_thumbnail(url=thumb)
    embed.set_footer(text=f"🌸 Uniq  |  MAL ID: {mal_id}")
    return embed

def build_search_embed(query: str, results: List[dict]) -> discord.Embed:
    embed = discord.Embed(title=f"🔍 نتائج البحث: {query}", description=f"تم العثور على **{len(results)}** نتيجة\nاختر أنمي من القائمة 👇", color=Theme.BG)
    for i, a in enumerate(results[:5]):
        score = f"⭐ **{a.get('score', '؟')}**" if a.get("score") else "✨ جديد"
        eps = f"📺 **{a.get('episodes', '؟')}** حلقة"
        embed.add_field(name=f"{medal_emoji(i+1)} {i+1}. {a.get('title', '؟')}", value=f"{score} | {eps}", inline=False)
    if results and (thumb := get_image(results[0], "thumbnail")):
        embed.set_thumbnail(url=thumb)
    return embed

def build_top_embed(anime_list: List[dict]) -> discord.Embed:
    embed = discord.Embed(title="🏆 Top 10 Anime", description="أفضل الأنميات على MyAnimeList", color=Theme.BG)
    for i, a in enumerate(anime_list[:10]):
        score = f"⭐ **{a.get('score', '')}**" if a.get("score") else ""
        embed.add_field(name=f"{medal_emoji(i+1)} #{i+1} {a.get('title', '؟')}", value=f"{score}", inline=False)
    if anime_list and (img := get_image(anime_list[0], "banner")):
        embed.set_image(url=img)
    return embed

def build_character_search_embed(query: str, characters: List[dict]) -> discord.Embed:
    embed = discord.Embed(title=f"🎭 نتائج البحث عن: {query}", description=f"تم العثور على **{len(characters)}** شخصية\nاختر شخصية من القائمة 👇", color=Theme.PURPLE)
    for i, char in enumerate(characters[:10]):
        embed.add_field(name=f"{medal_emoji(i+1) if i < 3 else '👤'} {char.get('name', '؟')}", value=f"💖 **{format_number(char.get('favorites', 0))}**", inline=False)
    if characters and (thumb := get_char_image(characters[0])):
        embed.set_thumbnail(url=thumb)
    return embed

def build_character_detail_embed(char: dict, anime_list: List[dict] = None) -> discord.Embed:
    embed = discord.Embed(title=f"🎭 {char.get('name', '؟')}", color=Theme.PURPLE, url=char.get("url"), timestamp=datetime.now(timezone.utc))
    if favs := char.get("favorites"):
        embed.add_field(name="⭐ الإعجابات", value=f"**{format_number(favs)}**", inline=True)
    if anime_list:
        titles = [f"📺 **{a.get('anime', {}).get('title', '؟')}** ({a.get('role', '')})" for a in anime_list[:5]]
        embed.add_field(name="🎬 الأنمي اللي ظهرت فيه", value="\n".join(titles), inline=False)
    if about := char.get("about"):
        embed.add_field(name="📝 نبذة", value=about[:500] + "...", inline=False)
    if img := get_char_image(char):
        embed.set_thumbnail(url=img)
    return embed

def build_news_embed(anime: dict, category: str = "anime") -> discord.Embed:
    embed = discord.Embed(title=f"{get_category_emoji(category)} خبر {get_category_name(category)} جديد!", description=f"**{anime.get('title', '؟')}**", color=get_category_color(category), url=anime.get("url"), timestamp=datetime.now(timezone.utc))
    if thumb := get_image(anime, "thumbnail"):
        embed.set_thumbnail(url=thumb)
    return embed

def build_recognition_result_embed(anime_title: str, anime_title_jp: str = None, episode: str = None, timestamp_str: str = None, similarity: float = None, image_preview: str = None, mal_url: str = None, full_anime: dict = None, characters: list = None) -> discord.Embed:
    embed = discord.Embed(title=f"🎬 {anime_title}", color=Theme.ACCENT, url=mal_url, timestamp=datetime.now(timezone.utc))
    if anime_title_jp: embed.description = f"🇯🇵 *{anime_title_jp}*"
    if episode: embed.add_field(name="📺 الحلقة", value=f"**{episode}**", inline=True)
    if timestamp_str: embed.add_field(name="⏱️ الوقت", value=f"**{timestamp_str}**", inline=True)
    if similarity is not None:
        sim = round(similarity * 100, 2)
        indicator = "✅" if sim > 87 else ("⚠️" if sim > 80 else "❌")
        embed.add_field(name="📊 التشابه", value=f"**{sim}%** {indicator}", inline=True)
    if image_preview: embed.set_thumbnail(url=image_preview)
    return embed

def loading_embed(msg: str = "⏳ جاري التحميل...") -> discord.Embed:
    return discord.Embed(description=f"🌸 {msg}", color=Theme.BG)

def error_embed(msg: str) -> discord.Embed:
    return discord.Embed(title="❌ خطأ", description=msg, color=Theme.DANGER).set_footer(text="🌸 Uniq")

def success_embed(title: str, msg: str) -> discord.Embed:
    return discord.Embed(title=f"✅ {title}", description=msg, color=Theme.SUCCESS).set_footer(text="🌸 Uniq")

def info_embed(title: str, msg: str, color: int = Theme.INFO) -> discord.Embed:
    return discord.Embed(title=f"ℹ️ {title}", description=msg, color=color).set_footer(text="🌸 Uniq")

# ═══════════════════════════════════════════════════════════════
# 🎛️ VIEWS
# ═══════════════════════════════════════════════════════════════

class SearchDropdown(discord.ui.View):
    def __init__(self, results: List[dict], user_id: int):
        super().__init__(timeout=300)
        self.results = results
        self.user_id = user_id
        options = [discord.SelectOption(label=r.get("title", "؟")[:100], value=str(i), emoji=medal_emoji(i+1) if i < 3 else "🎬") for i, r in enumerate(results[:25])]
        select = discord.ui.Select(placeholder="🔍 اختر أنمي من القائمة...", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        anime = self.results[idx]
        await interaction.response.defer(ephemeral=True)
        if mal_id := anime.get("mal_id"):
            if full := await get_anime_details(mal_id): anime = full
        await interaction.followup.send(embed=build_main_embed(anime, "🎬 "), view=AnimeActionsView(anime, interaction.user.id), ephemeral=True)

class AnimeActionsView(discord.ui.View):
    def __init__(self, anime: dict, user_id: int):
        super().__init__(timeout=300)
        self.anime, self.user_id = anime, user_id
        if url := anime.get("url"):
            self.add_item(discord.ui.Button(label="MyAnimeList", emoji="🌐", url=url, style=discord.ButtonStyle.link))

    @discord.ui.button(label="🎭 الشخصيات", style=discord.ButtonStyle.primary)
    async def characters_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if mal_id := self.anime.get("mal_id"):
            chars = await get_characters(mal_id)
            if chars:
                view = CharacterListView(self.anime, chars, interaction.user.id)
                await interaction.followup.send(embed=view.build_page(), view=view, ephemeral=True)
                return
        await interaction.followup.send(embed=error_embed("لا توجد شخصيات."), ephemeral=True)

class CharacterListView(discord.ui.View):
    PER_PAGE = 5
    def __init__(self, anime: dict, characters: list, user_id: int):
        super().__init__(timeout=180)
        self.anime, self.characters, self.user_id, self.page = anime, characters, user_id, 0
        self.total_pages = max(0, (len(characters) - 1) // self.PER_PAGE)

    def build_page(self) -> discord.Embed:
        chunk = self.characters[self.page * self.PER_PAGE : (self.page + 1) * self.PER_PAGE]
        embed = discord.Embed(title=f'🎭 شخصيات "{self.anime.get("title", "؟")}"', color=Theme.PURPLE)
        for char in chunk:
            data = char.get("character", char)
            embed.add_field(name=f"👤 {data.get('name', '؟')}", value=f"🎭 {char.get('role', '')}", inline=True)
        embed.set_footer(text=f"صفحة {self.page + 1}/{self.total_pages + 1}")
        return embed

    @discord.ui.button(emoji="◀️", label="السابق", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page > 0: self.page -= 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)

    @discord.ui.button(emoji="▶️", label="التالي", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page < self.total_pages: self.page += 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)

class CharacterSearchDropdown(discord.ui.View):
    def __init__(self, characters: List[dict], user_id: int):
        super().__init__(timeout=300)
        self.characters, self.user_id = characters, user_id
        options = [discord.SelectOption(label=c.get("name", "؟")[:100], value=str(i), emoji="👤") for i, c in enumerate(characters[:25])]
        select = discord.ui.Select(placeholder="🎭 اختر شخصية من القائمة...", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        char = self.characters[idx]
        await interaction.response.defer(ephemeral=True)
        if mal_id := char.get("mal_id"):
            if full := await get_character_details(mal_id): char = full
        await interaction.followup.send(embed=build_character_detail_embed(char, char.get("anime", [])), ephemeral=True)

class NotificationView(discord.ui.View):
    def __init__(self, channel_id: int, category: str):
        super().__init__(timeout=None)
        self.channel_id, self.category = channel_id, category

    @discord.ui.button(label="🔔 اشتراك", style=discord.ButtonStyle.success, emoji="🔔")
    async def subscribe(self, interaction: discord.Interaction, btn: discord.ui.Button):
        uid = interaction.user.id
        if db.is_user_subscribed(self.channel_id, uid):
            db.remove_notification_user(self.channel_id, uid)
            await interaction.response.send_message(embed=info_embed("إلغاء الاشتراك", "تم إلغاء اشتراكك بنجاح!", Theme.WARNING), ephemeral=True)
        else:
            db.add_notification_user(self.channel_id, uid)
            await interaction.response.send_message(embed=success_embed("اشتراك ناجح!", f"ستصلك إشعارات {get_category_name(self.category)} الجديدة"), ephemeral=True)

# ═══════════════════════════════════════════════════════════════
# 🤖 BOT SETUP & EVENTS
# ═══════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name}')
    await bot.tree.sync()
    bot.loop.create_task(news_broadcast_loop())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and 'image' in attachment.content_type:
                await process_auto_recognition(message, attachment)
                break
    await bot.process_commands(message)

async def process_auto_recognition(message: discord.Message, attachment: discord.Attachment):
    if not db.recognition_channel_id or message.channel.id != db.recognition_channel_id: return
    try:
        data = await attachment.read()
        msg = await message.reply(embed=loading_embed("جاري تحليل الصورة..."))
        trace = await trace_moe_search(data)
        if trace and trace.get("result"):
            best = trace["result"][0]
            ani = best.get("anilist", {})
            full = await get_anime_details(ani.get("mal_id")) if ani.get("mal_id") else None
            embed = build_recognition_result_embed(ani.get("title", "؟"), ani.get("title_native"), str(best.get("episode", "?")), format_timestamp(best.get("from", 0)), best.get("similarity"), best.get("image"), f"https://myanimelist.net/anime/{ani.get('mal_id')}" if ani.get('mal_id') else None, full)
            await msg.edit(embed=embed)
        else:
            await msg.edit(embed=error_embed("لم يتم التعرف على الأنمي."))
    except Exception as e:
        logger.error(f"Error in recognition: {e}")

async def news_broadcast_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            anime_list = await get_seasonal_anime(5)
            for anime in anime_list:
                mid = str(anime.get("mal_id", ""))
                if mid and mid != db.last_anime_news_id:
                    db.last_anime_news_id = mid
                    db.save()
                    for conf in db.get_channels("anime"):
                        if chan := bot.get_channel(conf.channel_id):
                            await chan.send(embed=build_news_embed(anime, "anime"), view=NotificationView(conf.channel_id, "anime"))
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Error in news loop: {e}")
            await asyncio.sleep(60)

# ═══════════════════════════════════════════════════════════════
# 📊 SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="help", description="مساعدة وأوامر البوت")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🌸 Uniq v1.0 - المساعدة", description="أوامر البوت المتاحة:", color=Theme.CARD_BG)
    embed.add_field(name="🔍 البحث", value="`/anime [اسم]`\n`/character [اسم]`\n`/suggest`", inline=False)
    embed.add_field(name="📊 التصنيفات", value="`/top`\n`/season`\n`/upcoming`\n`/airing`", inline=False)
    embed.add_field(name="🖼️ التعرف", value="`/setrecog`\n`/clearrecog`", inline=False)
    embed.add_field(name="🔧 الإدارة", value="`/setup`\n`/remove`\n`/list`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="anime", description="البحث عن أنمي")
async def anime_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    res = await search_anime(name)
    if res: await interaction.followup.send(embed=build_search_embed(name, res), view=SearchDropdown(res, interaction.user.id))
    else: await interaction.followup.send(embed=error_embed("لم يتم العثور على نتائج."))

@bot.tree.command(name="character", description="البحث عن شخصية")
async def character_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    res = await search_character(name)
    if res: await interaction.followup.send(embed=build_character_search_embed(name, res), view=CharacterSearchDropdown(res, interaction.user.id))
    else: await interaction.followup.send(embed=error_embed("لم يتم العثور على نتائج."))

@bot.tree.command(name="suggest", description="اقتراح أنمي عشوائي")
async def suggest_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    ani = await get_random_anime()
    if ani: await interaction.followup.send(embed=build_main_embed(ani, "🎲 "), view=AnimeActionsView(ani, interaction.user.id))
    else: await interaction.followup.send(embed=error_embed("خطأ في جلب البيانات."))

@bot.tree.command(name="top", description="أفضل 10 أنمي")
async def top_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_top_anime()
    if res: await interaction.followup.send(embed=build_top_embed(res))
    else: await interaction.followup.send(embed=error_embed("خطأ في جلب البيانات."))

@bot.tree.command(name="season", description="أنمي الموسم")
async def season_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_seasonal_anime()
    if res:
        embed = discord.Embed(title="🌸 أنمي الموسم", color=Theme.ACCENT)
        for i, a in enumerate(res[:10]): embed.add_field(name=f"{i+1}. {a.get('title')}", value=f"⭐ {a.get('score', '؟')}", inline=False)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="upcoming", description="أنميات قادمة")
async def upcoming_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_upcoming_anime()
    if res:
        embed = discord.Embed(title="⏳ أنميات قادمة", color=Theme.WARNING)
        for i, a in enumerate(res[:10]): embed.add_field(name=f"{i+1}. {a.get('title')}", value=f"📅 {a.get('aired', {}).get('string', 'قريباً')}", inline=False)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="airing", description="يعرض حالياً")
async def airing_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_airing_anime()
    if res:
        embed = discord.Embed(title="🔄 يعرض حالياً", color=Theme.INFO)
        for i, a in enumerate(res[:10]): embed.add_field(name=f"{i+1}. {a.get('title')}", value=f"⭐ {a.get('score', '؟')}", inline=False)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="setrecog", description="تفعيل روم التعرف")
@app_commands.default_permissions(manage_channels=True)
async def setrecog_cmd(interaction: discord.Interaction):
    db.set_recognition_channel(interaction.channel_id)
    await interaction.response.send_message(embed=success_embed("تم التفعيل", "تم تفعيل روم التعرف التلقائي."), ephemeral=True)

@bot.tree.command(name="clearrecog", description="إيقاف التعرف")
@app_commands.default_permissions(manage_channels=True)
async def clearrecog_cmd(interaction: discord.Interaction):
    db.clear_recognition_channel()
    await interaction.response.send_message(embed=success_embed("تم الإيقاف", "تم إيقاف التعرف التلقائي."), ephemeral=True)

@bot.tree.command(name="setup", description="تخصيص الروم")
@app_commands.describe(category="anime, manga, manhwa")
@app_commands.default_permissions(manage_channels=True)
async def setup_cmd(interaction: discord.Interaction, category: str):
    if category not in ["anime", "manga", "manhwa"]:
        return await interaction.response.send_message(embed=error_embed("فئة غير صالحة."), ephemeral=True)
    db.add_channel(interaction.channel_id, category)
    await interaction.response.send_message(embed=success_embed("تم التخصيص", f"تم تخصيص الروم لـ {get_category_name(category)}."), ephemeral=True)

@bot.tree.command(name="remove", description="إزالة التخصيص")
@app_commands.default_permissions(manage_channels=True)
async def remove_cmd(interaction: discord.Interaction):
    db.remove_channel(interaction.channel_id)
    await interaction.response.send_message(embed=success_embed("تم الإزالة", "تم إزالة تخصيص الروم."), ephemeral=True)

@bot.tree.command(name="list", description="الرومات المفعّلة")
@app_commands.default_permissions(manage_channels=True)
async def list_cmd(interaction: discord.Interaction):
    chans = db.get_channels()
    desc = "\n".join([f"<#{c.channel_id}> - {get_category_name(c.category)}" for c in chans]) if chans else "لا توجد رومات."
    await interaction.response.send_message(embed=info_embed("الرومات المفعّلة", desc), ephemeral=True)

if __name__ == "__main__":
    if TOKEN: bot.run(TOKEN)
    else: logger.error("❌ TOKEN NOT FOUND")
