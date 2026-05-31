# 🔥 The Veyn — بوت الأنمي v6.0 Pro Edition
# التعرف التلقائي على الصور في روم محدد + نظام النشر التلقائي
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
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict

load_dotenv()
TOKEN = os.getenv("TOKEN")

# ═══════════════════════════════════════════════════════════════
# 📁 FILE PATHS
# ═══════════════════════════════════════════════════════════════

DATA_DIR = "/workspace/data"
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
        """تحميل البيانات من الملفات"""
        try:
            # تحميل إعدادات الرومات
            if os.path.exists(CHANNELS_FILE):
                with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.get('channels', {}).items():
                        self.channels[int(k)] = ChannelConfig(**v)
                    self.notification_users = data.get('notifications', {})

            # تحميل الكاش
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                    self.last_anime_news_id = cache.get('last_anime_news_id', '')

            # تحميل روم التعرف
            if os.path.exists(RECOGNITION_CHANNEL_FILE):
                with open(RECOGNITION_CHANNEL_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.recognition_channel_id = data.get('channel_id')

            print("✅ تم تحميل البيانات بنجاح")
        except Exception as e:
            print(f"❌ خطأ في تحميل البيانات: {e}")

    def save(self):
        """حفظ البيانات إلى الملفات"""
        try:
            # حفظ إعدادات الرومات
            data = {
                'channels': {str(k): asdict(v) for k, v in self.channels.items()},
                'notifications': self.notification_users
            }
            with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # حفظ الكاش
            cache = {'last_anime_news_id': self.last_anime_news_id}
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

            # حفظ روم التعرف
            recognition_data = {'channel_id': self.recognition_channel_id}
            with open(RECOGNITION_CHANNEL_FILE, 'w', encoding='utf-8') as f:
                json.dump(recognition_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"❌ خطأ في حفظ البيانات: {e}")

    def set_recognition_channel(self, channel_id: int):
        self.recognition_channel_id = channel_id
        self.save()
        print(f"✅ تم تحديد روم التعرف: {channel_id}")

    def clear_recognition_channel(self):
        self.recognition_channel_id = None
        self.save()
        print("✅ تم مسح روم التعرف")

    def add_channel(self, channel_id: int, category: str, role_id: int = None):
        self.channels[channel_id] = ChannelConfig(
            channel_id=channel_id,
            category=category,
            notification_role_id=role_id
        )
        self.notification_users[channel_id] = []
        self.save()
        print(f"✅ تم إضافة روم {channel_id} كفئة {category}")

    def remove_channel(self, channel_id: int):
        if channel_id in self.channels:
            del self.channels[channel_id]
        if channel_id in self.notification_users:
            del self.notification_users[channel_id]
        self.save()
        print(f"✅ تم إزالة روم {channel_id}")

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


# إنشاء كائن قاعدة البيانات
db = Database()


# ═══════════════════════════════════════════════════════════════
# 🌐 API CONFIGURATION
# ═══════════════════════════════════════════════════════════════

JIKAN_BASE = "https://api.jikan.moe/v4"
TRACE_MOE_URL = "https://api.trace.moe/search"

_rate_limiter = asyncio.Semaphore(1)
_jikan_cache = {}


# ═══════════════════════════════════════════════════════════════
# 🌐 API FUNCTIONS
# ═══════════════════════════════════════════════════════════════

async def jikan_get(endpoint: str, use_cache: bool = True) -> Optional[dict]:
    """طلب من Jikan API مع Cache و Rate Limit"""
    global _jikan_cache
    cache_key = endpoint

    if use_cache and cache_key in _jikan_cache:
        data, timestamp = _jikan_cache[cache_key]
        if datetime.now().timestamp() - timestamp < 120:
            return data

    url = f"{JIKAN_BASE}{endpoint}"

    async with _rate_limiter:
        await asyncio.sleep(0.4)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.json()
                        _jikan_cache[cache_key] = (data, datetime.now().timestamp())
                        if len(_jikan_cache) > 100:
                            keys = list(_jikan_cache.keys())[:20]
                            for k in keys:
                                del _jikan_cache[k]
                        return data
                    elif r.status == 429:
                        await asyncio.sleep(3)
        except Exception as e:
            print(f"❌ خطأ في Jikan API: {e}")
    return None


# ═══════════════════════════════════════════════════════════════
# 🔍 JIKAN FUNCTIONS
# ═══════════════════════════════════════════════════════════════

async def search_anime(query: str, limit: int = 15) -> List[dict]:
    """البحث عن أنمي في MyAnimeList"""
    encoded_query = query.replace(" ", "%20")
    data = await jikan_get(f"/anime?q={encoded_query}&limit={limit}&sfw=true")
    return data.get("data", []) if data else []


async def get_anime_details(mal_id: int) -> Optional[dict]:
    """جلب تفاصيل الأنمي"""
    data = await jikan_get(f"/anime/{mal_id}/full")
    return data.get("data") if data else None


async def get_random_anime() -> Optional[dict]:
    """أنمي عشوائي"""
    data = await jikan_get("/random/anime", use_cache=False)
    return data.get("data") if data else None


async def get_top_anime(limit: int = 10) -> List[dict]:
    """أفضل الأنميات"""
    data = await jikan_get(f"/top/anime?limit={limit}")
    return data.get("data", []) if data else []


async def get_seasonal_anime(limit: int = 10) -> List[dict]:
    """أنمي الموسم"""
    data = await jikan_get(f"/seasons/now?limit={limit}")
    return data.get("data", []) if data else []


async def get_upcoming_anime(limit: int = 10) -> List[dict]:
    """أنمي قادم"""
    data = await jikan_get(f"/seasons/upcoming?limit={limit}")
    return data.get("data", []) if data else []


async def get_airing_anime(limit: int = 15) -> List[dict]:
    """الأنمي اللي يعرض حالياً"""
    data = await jikan_get(f"/top/anime?filter=airing&limit={limit}")
    return data.get("data", []) if data else []


async def get_characters(mal_id: int) -> List[dict]:
    """جلب شخصيات الأنمي"""
    data = await jikan_get(f"/anime/{mal_id}/characters")
    return data.get("data", []) if data else []


async def get_anime_recommendations(mal_id: int, limit: int = 6) -> List[dict]:
    """توصيات الأنمي"""
    data = await jikan_get(f"/anime/{mal_id}/recommendations")
    return data.get("data", [])[:limit] if data else []


async def search_characters(query: str, limit: int = 10) -> List[dict]:
    """البحث عن شخصية أنمي"""
    encoded_query = query.replace(" ", "%20")
    data = await jikan_get(f"/characters?q={encoded_query}&limit={limit}&order=favorites&sort=desc")
    return data.get("data", []) if data else []


# ═══════════════════════════════════════════════════════════════
# 🖼️ TRACE.MOE FUNCTIONS (للتعرف على الأنمي من الصور)
# ═══════════════════════════════════════════════════════════════

async def trace_moe_search(image_data: bytes) -> Optional[dict]:
    """البحث في Trace.moe باستخدام الصورة"""
    try:
        async with aiohttp.ClientSession() as session:
            # تحويل الصورة لـ base64
            base64_image = base64.b64encode(image_data).decode('utf-8')

            # إنشاء form data
            form = aiohttp.FormData()
            form.add_field(
                'image',
                base64_image,
                filename='image.jpg',
                content_type='image/jpeg'
            )

            async with session.post(
                TRACE_MOE_URL,
                data=form,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"❌ Trace.moe خطأ: {response.status}")
                    return None
    except Exception as e:
        print(f"❌ خطأ في Trace.moe: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# 🎨 THEME & COLORS
# ═══════════════════════════════════════════════════════════════

class Theme:
    BG = 0x0D0D0D
    CARD_BG = 0x1A1A2E
    ACCENT = 0xFF6B35
    SECONDARY = 0xF7931A
    SUCCESS = 0x00D26A
    DANGER = 0xFF3860
    WARNING = 0xFFE66D
    PURPLE = 0x9D4EDD
    INFO = 0x3A86FF
    MANGA = 0x06D6A0
    MANHWA = 0xE63946

    GENRE_COLORS = {
        "Action": 0xFF3860, "Adventure": 0xFF9F1C, "Comedy": 0xFFE66D,
        "Drama": 0x9D4EDD, "Fantasy": 0x7B2CBF, "Horror": 0xC1121F,
        "Mystery": 0x3A86FF, "Romance": 0xFF006E, "Sci-Fi": 0x00F5D4,
        "Slice of Life": 0xFB8500, "Sports": 0x06D6A0, "Supernatural": 0x8338EC,
        "Psychological": 0xE63946, "Thriller": 0xD00000, "Mecha": 0x6C757D,
        "Music": 0xF72585, "Isekai": 0xFF6B35, "Harem": 0xE63946,
        "Ecchi": 0xF4A261, "Shounen": 0xFFE66D, "Shoujo": 0xFF006E,
        "Seinen": 0x3D405B, "default": 0xFF6B35,
    }


GENRE_AR = {
    "Action": "⚔️ أكشن", "Adventure": "🗺️ مغامرة", "Comedy": "😂 كوميديا",
    "Drama": "🎭 دراما", "Fantasy": "✨ فانتازيا", "Horror": "👻 رعب",
    "Mystery": "🔮 غموض", "Romance": "💕 رومانسي", "Sci-Fi": "🚀 خيال علمي",
    "Slice of Life": "☀️ حياة يومية", "Sports": "⚽ رياضة",
    "Supernatural": "👁️ خارق للطبيعة", "Thriller": "🔪 إثارة",
    "Mecha": "🤖 ميكا", "Music": "🎵 موسيقى", "Psychological": "🧠 نفسي",
    "Shounen": "🔥 شونن", "Shoujo": "🌸 شوجو", "Seinen": "🌑 سينن",
    "Isekai": "🌐 إيسيكاي", "Harem": "💝 حريم", "Ecchi": "😳 إيتشي",
}

STATUS_AR = {
    "Finished Airing": ("✅", "مكتمل"),
    "Currently Airing": ("🔴", "يعرض الآن"),
    "Not yet aired": ("⏳", "لم يعرض بعد"),
}


# ═══════════════════════════════════════════════════════════════
# 🎨 HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def get_embed_color(anime: dict) -> int:
    """جلب لون الإمبيد حسب التصنيف"""
    genres = anime.get("genres", []) + anime.get("themes", [])
    for g in genres:
        name = g.get("name", "")
        if name in Theme.GENRE_COLORS:
            return Theme.GENRE_COLORS[name]
    return Theme.GENRE_COLORS["default"]


def get_image(anime: dict, img_type: str = "thumbnail") -> Optional[str]:
    """جلب صورة الأنمي"""
    images = anime.get("images", {})
    jpg = images.get("jpg", {})
    if img_type == "banner":
        return jpg.get("large_image_url") or jpg.get("image_url")
    return jpg.get("image_url")


def get_char_image(char: dict) -> Optional[str]:
    """جلب صورة الشخصية"""
    # قد تكون الشخصية dict مستقل أو داخل مفتاح "character"
    if isinstance(char, dict):
        images = char.get("images", {})
        return images.get("jpg", {}).get("image_url")
    return None


def genres_text(anime: dict, max_items: int = 4) -> str:
    """تحويل التصنيفات لنص عربي"""
    genres = anime.get("genres", []) + anime.get("themes", [])
    names = [GENRE_AR.get(g.get("name", ""), g.get("name", "")) for g in genres[:max_items]]
    return " · ".join(names) if names else "—"


def status_label(status: str) -> str:
    """تحويل الحالة لنص عربي"""
    _, txt = STATUS_AR.get(status, ("❓", status))
    return txt


def synopsis_short(anime: dict, limit: int = 300) -> str:
    """تلخيص القصة"""
    text = anime.get("synopsis") or "لا يوجد وصف متاح."
    if len(text) > limit:
        return text[:limit].rsplit(" ", 1)[0] + "..."
    return text


def year_label(anime: dict) -> str:
    """استخراج السنة"""
    year = anime.get("year")
    if not year:
        aired = anime.get("aired", {})
        if isinstance(aired, dict):
            year = aired.get("prop", {}).get("year")
    return str(year) if year else "—"


def medal_emoji(rank: int) -> str:
    """إيموجي الميدالية"""
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "⭐")


def rating_stars(score: Optional[float]) -> str:
    """تحويل التقييم لنجوم"""
    if score is None:
        return "☆☆☆☆☆"
    full = int(score // 2)
    half = 1 if (score % 2) >= 1 else 0
    return "⭐" * full + ("✴️" if half else "") + "☆" * (5 - full - half)


def format_number(num: int) -> str:
    """تنسيق الأرقام"""
    return f"{num:,}"


def get_category_emoji(category: str) -> str:
    """إيموجي الفئة"""
    return {"anime": "🎬", "manga": "📚", "manhwa": "🇰🇷"}.get(category, "📰")


def get_category_name(category: str) -> str:
    """اسم الفئة بالعربي"""
    return {"anime": "أنمي", "manga": "مانجا", "manhwa": "مانهوا"}.get(category, "أخبار")


def get_category_color(category: str) -> int:
    """لون الفئة"""
    return {"anime": Theme.ACCENT, "manga": Theme.MANGA, "manhwa": Theme.MANHWA}.get(category, Theme.INFO)


def format_timestamp(seconds: float) -> str:
    """تحويل الثواني لصيغة وقت HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# ═══════════════════════════════════════════════════════════════
# 📦 EMBED BUILDERS
# ═══════════════════════════════════════════════════════════════

def build_main_embed(anime: dict, prefix: str = "") -> discord.Embed:
    """إنشاء الإمبيد الرئيسي"""
    title = anime.get("title", "؟")
    title_jp = anime.get("title_japanese", "")
    mal_id = anime.get("mal_id", 0)

    desc_parts = []
    if title_jp:
        desc_parts.append(f"🇯🇵 *{title_jp}*")
    desc_parts.append("")
    desc_parts.append(synopsis_short(anime))

    embed = discord.Embed(
        title=f"{prefix}{title}",
        description="\n".join(desc_parts),
        color=Theme.CARD_BG,
        url=anime.get("url"),
        timestamp=datetime.now(timezone.utc)
    )

    score = anime.get("score")
    if score:
        embed.add_field(name="⭐ التقييم", value=f"**{score}/10** {rating_stars(score)}", inline=True)

    episodes = anime.get("episodes")
    if episodes:
        embed.add_field(name="📺 الحلقات", value=f"**{episodes}**", inline=True)

    year = year_label(anime)
    if year and year != "—":
        embed.add_field(name="📅 السنة", value=f"**{year}**", inline=True)

    embed.add_field(name="🎭 التصنيفات", value=genres_text(anime, 5), inline=False)

    status = anime.get("status", "")
    if status:
        embed.add_field(name="🏷️ الحالة", value=status_label(status), inline=True)

    studios = [s["name"] for s in anime.get("studios", [])][:2]
    if studios:
        embed.add_field(name="🎥 الاستوديو", value=" · ".join(studios), inline=True)

    members = anime.get("members")
    if members:
        embed.add_field(name="👥 الأعضاء", value=f"**{format_number(members)}**", inline=True)

    if thumb := get_image(anime, "thumbnail"):
        embed.set_thumbnail(url=thumb)

    embed.set_footer(text=f"🌸 The Veyn  |  MAL ID: {mal_id}")
    return embed


def build_search_embed(query: str, results: List[dict]) -> discord.Embed:
    """إنشاء امبد نتائج البحث"""
    embed = discord.Embed(
        title=f"🔍 نتائج البحث: {query}",
        description=f"تم العثور على **{len(results)}** نتيجة\nاختر أنمي من القائمة 👇",
        color=Theme.BG
    )

    for i, a in enumerate(results[:5]):
        score = f"⭐ **{a.get('score', '؟')}**" if a.get("score") else "✨ جديد"
        eps = f"📺 **{a.get('episodes', '؟')}** حلقة" if a.get("episodes") else "📺 ?"
        embed.add_field(name=f"{medal_emoji(i+1)} {i+1}. {a.get('title', '؟')}", value=f"{score} | {eps}", inline=False)

    if results and (thumb := get_image(results[0], "thumbnail")):
        embed.set_thumbnail(url=thumb)

    embed.set_footer(text="🌸 The Veyn • اختر أنمي")
    return embed


def build_top_embed(anime_list: List[dict]) -> discord.Embed:
    """إنشاء امبد أفضل 10"""
    embed = discord.Embed(
        title="🏆 Top 10 Anime",
        description="أفضل الأنميات على MyAnimeList",
        color=Theme.BG
    )

    for i, a in enumerate(anime_list[:10]):
        score = f"⭐ **{a.get('score', '')}**" if a.get("score") else ""
        eps = f"📺 **{a.get('episodes')}**" if a.get("episodes") else ""
        embed.add_field(name=f"{medal_emoji(i+1)} #{i+1} {a.get('title', '؟')}", value=f"{score} {eps}", inline=False)

    if anime_list and (img := get_image(anime_list[0], "banner")):
        embed.set_image(url=img)

    embed.set_footer(text="🌸 The Veyn • اختر أنمي للتفاصيل")
    return embed


def build_character_embed(anime: dict, character: dict) -> discord.Embed:
    """إنشاء امبد الشخصية"""
    # استخراج بيانات الشخصية
    if "character" in character:
        char_data = character["character"]
    else:
        char_data = character

    char_name = char_data.get("name", "؟") if isinstance(char_data, dict) else "؟"
    char_images = char_data.get("images", {}) if isinstance(char_data, dict) else {}
    char_favorites = char_data.get("favorites", 0) if isinstance(char_data, dict) else 0

    embed = discord.Embed(
        title=f"🎭 {char_name}",
        description=f"من أنمي: **{anime.get('title', '؟')}**",
        color=Theme.PURPLE,
        timestamp=datetime.now(timezone.utc)
    )

    if char_favorites:
        embed.add_field(name="⭐ الإعجابات", value=f"**{format_number(char_favorites)}**", inline=True)

    role = character.get('role', 'غير محدد')
    embed.add_field(name="🎭 الدور", value=role, inline=True)

    about = char_data.get('about', '') if isinstance(char_data, dict) else ''
    if about and len(about) > 500:
        about = about[:500] + "..."
    if about:
        embed.add_field(name="📝 نبذة", value=about[:300], inline=False)

    if img := char_images.get("jpg", {}).get("image_url"):
        embed.set_thumbnail(url=img)

    embed.set_footer(text=f"🌸 The Veyn • شخصية من {anime.get('title', '')}")
    return embed


def build_news_embed(anime: dict, category: str = "anime") -> discord.Embed:
    """إنشاء امبد الخبر"""
    emoji = get_category_emoji(category)
    color = get_category_color(category)
    cat_name = get_category_name(category)

    title = anime.get("title", "؟")
    score = anime.get("score")
    score_text = f"⭐ **{score}/10**" if score else "✨ جديد"

    embed = discord.Embed(
        title=f"{emoji} خبر {cat_name} جديد!",
        description=f"**{title}**\n{score_text}",
        color=color,
        url=anime.get("url"),
        timestamp=datetime.now(timezone.utc)
    )

    if genres := genres_text(anime, 3):
        embed.add_field(name="🎭", value=genres, inline=True)

    status = anime.get("status", "")
    if status:
        embed.add_field(name="🏷️", value=status_label(status), inline=True)

    if img := get_image(anime, "thumbnail"):
        embed.set_thumbnail(url=img)

    embed.set_footer(text=f"🌸 The Veyn • {cat_name}")
    return embed


def build_notification_embed(channel_config: ChannelConfig) -> discord.Embed:
    """إنشاء امبد الإشعارات"""
    cat_name = get_category_name(channel_config.category)
    emoji = get_category_emoji(channel_config.category)

    embed = discord.Embed(
        title=f"{emoji} إشعارات {cat_name}",
        description="🔔 اضغط الزر للحصول على رول الإشعارات!\n\n"
                   "ستصلك إشعارات فورية عند نشر أي خبر جديد.",
        color=get_category_color(channel_config.category),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_footer(text=f"🌸 The Veyn • إشعارات {cat_name}")
    return embed


def build_recognition_result_embed(
    anime_title: str,
    anime_title_jp: str = None,
    episode: str = None,
    timestamp_str: str = None,
    similarity: float = None,
    image_preview: str = None,
    mal_url: str = None,
    full_anime: dict = None
) -> discord.Embed:
    """إنشاء امبد نتيجة التعرف"""
    embed = discord.Embed(
        title=f"🎬 {anime_title}",
        color=Theme.ACCENT,
        url=mal_url,
        timestamp=datetime.now(timezone.utc)
    )

    if anime_title_jp:
        embed.description = f"🇯🇵 *{anime_title_jp}*"

    if episode:
        embed.add_field(name="📺 الحلقة", value=f"**{episode}**", inline=True)

    if timestamp_str:
        embed.add_field(name="⏱️ الوقت", value=f"**{timestamp_str}**", inline=True)

    if similarity is not None:
        similarity_percent = min(99, int(similarity * 100))
        indicator = "🟢" if similarity >= 0.8 else "🟡" if similarity >= 0.5 else "🔴"
        embed.add_field(name="📊 التشابه", value=f"**{similarity_percent}%** {indicator}", inline=True)

    # التصنيفات من معلومات MAL
    if full_anime and (genres := genres_text(full_anime, 3)):
        embed.add_field(name="🎭 التصنيفات", value=genres, inline=False)

    # التقييم من MAL
    if full_anime and full_anime.get('score'):
        embed.add_field(name="⭐ التقييم", value=f"**{full_anime.get('score')}/10**", inline=True)

    if mal_url:
        embed.add_field(name="🔗 رابط", value=f"[MyAnimeList]({mal_url})", inline=True)

    if image_preview:
        embed.set_thumbnail(url=image_preview)

    embed.set_footer(text="🌸 The Veyn • التعرف التلقائي")
    return embed


def loading_embed(msg: str = "⏳ جاري التحميل...") -> discord.Embed:
    return discord.Embed(description=f"🌸 {msg}", color=Theme.BG)


def error_embed(msg: str) -> discord.Embed:
    return discord.Embed(title="❌ خطأ", description=msg, color=Theme.DANGER).set_footer(text="🌸 The Veyn")


def success_embed(title: str, msg: str) -> discord.Embed:
    return discord.Embed(title=f"✅ {title}", description=msg, color=Theme.SUCCESS).set_footer(text="🌸 The Veyn")


def info_embed(title: str, msg: str, color: int = Theme.INFO) -> discord.Embed:
    return discord.Embed(title=f"ℹ️ {title}", description=msg, color=color).set_footer(text="🌸 The Veyn")


# ═══════════════════════════════════════════════════════════════
# 🎛️ VIEWS
# ═══════════════════════════════════════════════════════════════

class SearchDropdown(discord.ui.View):
    def __init__(self, results: List[dict], user_id: int):
        super().__init__(timeout=300)
        self.results = results
        self.user_id = user_id

        options = [
            discord.SelectOption(
                label=r.get("title", "؟")[:100],
                value=str(i),
                description=f"⭐ {r.get('score', '؟')} | 📺 {r.get('episodes', '؟')} حلقة",
                emoji=medal_emoji(i+1) if i < 3 else "🎬"
            )
            for i, r in enumerate(results[:25])
        ]

        select = discord.ui.Select(placeholder="🔍 اختر أنمي من القائمة...", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        anime = self.results[idx]

        await interaction.response.defer(ephemeral=True)

        mal_id = anime.get("mal_id")
        if mal_id:
            full = await get_anime_details(mal_id)
            if full:
                anime = full

        embed = build_main_embed(anime, "🎬 ")
        view = AnimeActionsView(anime, interaction.user.id)

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class AnimeActionsView(discord.ui.View):
    def __init__(self, anime: dict, user_id: int):
        super().__init__(timeout=300)
        self.anime = anime
        self.user_id = user_id

        if url := anime.get("url"):
            self.add_item(discord.ui.Button(
                label="MyAnimeList", emoji="🌐", url=url,
                style=discord.ButtonStyle.link, row=0
            ))

    @discord.ui.button(label="🎭 الشخصيات", style=discord.ButtonStyle.primary, row=1)
    async def characters_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        mal_id = self.anime.get("mal_id")
        if not mal_id:
            await interaction.followup.send(embed=error_embed("ما قدرت أجيب معلومات."), ephemeral=True)
            return

        characters = await get_characters(mal_id)
        if not characters:
            await interaction.followup.send(embed=error_embed("ما في شخصيات."), ephemeral=True)
            return

        view = CharacterListView(self.anime, characters, interaction.user.id)
        embed = view.build_page()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🔍 مشابه", style=discord.ButtonStyle.secondary, row=1)
    async def similar_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        mal_id = self.anime.get("mal_id")
        if not mal_id:
            await interaction.followup.send(embed=error_embed("ما أقدر أجد مشابه."), ephemeral=True)
            return

        recs = await get_anime_recommendations(mal_id, 6)

        if not recs:
            await interaction.followup.send(embed=error_embed("ما لقيت توصيات."), ephemeral=True)
            return

        embed = discord.Embed(
            title=f'🔍 أنمي مشابه لـ {self.anime.get("title", "")}',
            color=Theme.BG
        )
        for rec in recs:
            rec_anime = rec.get("entry", {})
            embed.add_field(
                name=rec_anime.get("title", "؟")[:40],
                value=f"📺 [MAL]({rec_anime.get('url', '')})",
                inline=True
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎲 عشوائي", style=discord.ButtonStyle.secondary, row=2)
    async def random_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        anime = await get_random_anime()
        if not anime:
            await interaction.followup.send(embed=error_embed("حصل خطأ. جرب مرة أخرى."), ephemeral=True)
            return

        embed = build_main_embed(anime, "🎲 ")
        view = AnimeActionsView(anime, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class CharacterListView(discord.ui.View):
    PER_PAGE = 5

    def __init__(self, anime: dict, characters: list, user_id: int):
        super().__init__(timeout=180)
        self.anime = anime
        self.characters = characters
        self.user_id = user_id
        self.page = 0
        self.total_pages = max(0, (len(characters) - 1) // self.PER_PAGE) if characters else 0

    def build_page(self) -> discord.Embed:
        start = self.page * self.PER_PAGE
        end = start + self.PER_PAGE
        chunk = self.characters[start:end]

        embed = discord.Embed(
            title=f'🎭 شخصيات "{self.anime.get("title", "؟")}"',
            description=f"تم العثور على **{len(self.characters)}** شخصية",
            color=Theme.PURPLE
        )

        for char in chunk:
            # استخراج بيانات الشخصية
            if "character" in char:
                char_data = char["character"]
            else:
                char_data = char

            char_name = char_data.get("name", "؟") if isinstance(char_data, dict) else "؟"
            char_favorites = char_data.get("favorites", 0) if isinstance(char_data, dict) else 0
            role = char.get("role", "")

            embed.add_field(
                name=f"👤 {char_name}",
                value=f"🎭 {role} | 💖 {format_number(char_favorites)}",
                inline=True
            )

        embed.set_footer(text=f"صفحة {self.page + 1}/{self.total_pages + 1} | 🌸 The Veyn")

        if thumb := get_image(self.anime, "thumbnail"):
            embed.set_thumbnail(url=thumb)

        return embed

    @discord.ui.button(emoji="◀️", label="السابق", style=discord.ButtonStyle.secondary, row=0)
    async def prev(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)

    @discord.ui.button(emoji="▶️", label="التالي", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page < self.total_pages:
            self.page += 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)

    @discord.ui.button(label="👤 اختيار شخصية", style=discord.ButtonStyle.success, row=1)
    async def select_char(self, interaction: discord.Interaction, btn: discord.ui.Button):
        view = CharacterSelectView(self.anime, self.characters, interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(title="👤 اختر شخصية", description="اختر من القائمة 👇", color=Theme.PURPLE),
            view=view, ephemeral=True
        )


class CharacterSelectView(discord.ui.View):
    def __init__(self, anime: dict, characters: list, user_id: int):
        super().__init__(timeout=180)
        self.anime = anime
        self.characters = characters
        self.user_id = user_id

        options = []
        for i, char in enumerate(characters[:25]):
            # استخراج بيانات الشخصية
            if "character" in char:
                char_data = char["character"]
            else:
                char_data = char

            char_name = char_data.get("name", "؟") if isinstance(char_data, dict) else "؟"
            char_favorites = char_data.get("favorites", 0) if isinstance(char_data, dict) else 0
            role = char.get("role", "")

            options.append(discord.SelectOption(
                label=char_name[:50],
                value=str(i),
                description=f"🎭 {role} | 💖 {format_number(char_favorites)}",
                emoji="👤"
            ))

        select = discord.ui.Select(placeholder="👤 اختر شخصية...", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        char = self.characters[idx]

        embed = build_character_embed(self.anime, char)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class NotificationView(discord.ui.View):
    def __init__(self, channel_id: int, category: str):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.category = category

    @discord.ui.button(label="🔔 اشتراك", style=discord.ButtonStyle.success, emoji="🔔", row=0)
    async def subscribe(self, interaction: discord.Interaction, btn: discord.ui.Button):
        user_id = interaction.user.id

        if db.is_user_subscribed(self.channel_id, user_id):
            db.remove_notification_user(self.channel_id, user_id)
            await interaction.response.send_message(
                embed=info_embed("إلغاء الاشتراك", "تم إلغاء اشتراكك بنجاح!", color=Theme.WARNING),
                ephemeral=True
            )
        else:
            db.add_notification_user(self.channel_id, user_id)
            await interaction.response.send_message(
                embed=success_embed("اشتراك ناجح!", f"ستصلك إشعارات {get_category_name(self.category)} الجديدة."),
                ephemeral=True
            )


class Top10View(discord.ui.View):
    def __init__(self, anime_list: list):
        super().__init__(timeout=300)
        self.anime_list = anime_list

        for i in range(min(10, len(anime_list))):
            btn = discord.ui.Button(
                label=f"#{i + 1}",
                emoji=medal_emoji(i + 1),
                style=discord.ButtonStyle.primary if i < 3 else discord.ButtonStyle.secondary,
                row=i // 5
            )
            btn.callback = self.make_callback(i)
            self.add_item(btn)

    def make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            anime = self.anime_list[idx]

            await interaction.response.defer(ephemeral=True)

            mal_id = anime.get("mal_id")
            if mal_id:
                full = await get_anime_details(mal_id)
                if full:
                    anime = full

            embed = build_main_embed(anime, f"{medal_emoji(idx + 1)} #{idx + 1} ")
            view = AnimeActionsView(anime, interaction.user.id)

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        return callback


# ═══════════════════════════════════════════════════════════════
# 🤖 BOT SETUP
# ═══════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
intents.guild_messages = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="🌸 الأنمي | The Veyn v6.0")
    )
    print(f"✅ The Veyn v6.0 — {bot.user} — جاهز!")

    # بدء مهمة النشر التلقائي
    bot.loop.create_task(news_broadcast_loop())


# ═══════════════════════════════════════════════════════════════
# 📢 SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="anime", description="ابحث عن أنمي")
@app_commands.describe(name="اسم الأنمي")
async def anime_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)

    msg = await interaction.followup.send(
        embed=loading_embed(f"🔍 بدور عن **{name}**..."),
        ephemeral=True
    )

    results = await search_anime(name)
    if not results:
        await msg.edit(embed=error_embed(f'ما لقيت أنمي باسم **{name}**\nجرّب اسم مختلف.'))
        return

    embed = build_search_embed(name, results)
    view = SearchDropdown(results, interaction.user.id)

    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="suggest", description="اقتراح أنمي عشوائي")
async def suggest_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("🎲 جاري الاختيار..."), ephemeral=True)

    anime = await get_random_anime()
    if not anime:
        await msg.edit(embed=error_embed("حصل خطأ. جرب مرة أخرى."))
        return

    embed = build_main_embed(anime, "🎲 اقتراح: ")
    view = AnimeActionsView(anime, interaction.user.id)
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="top", description="أفضل 10 أنمي")
async def top_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("🏆 جاري التحميل..."), ephemeral=True)

    anime_list = await get_top_anime(10)
    if not anime_list:
        await msg.edit(embed=error_embed("فشل تحميل القائمة."))
        return

    embed = build_top_embed(anime_list)
    view = Top10View(anime_list)
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="season", description="أنمي الموسم الحالي")
async def season_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("🌸 جاري التحميل..."), ephemeral=True)

    anime_list = await get_seasonal_anime(8)
    if not anime_list:
        await msg.edit(embed=error_embed("فشل التحميل."))
        return

    now = datetime.now(timezone.utc)
    season_names = {
        1: "❄️ شتاء", 2: "❄️ شتاء", 3: "🌸 ربيع", 4: "🌸 ربيع", 5: "🌸 ربيع",
        6: "☀️ صيف", 7: "☀️ صيف", 8: "☀️ صيف", 9: "🍂 خريف", 10: "🍂 خريف", 11: "🍂 خريف", 12: "❄️ شتاء"
    }

    embed = discord.Embed(
        title=f"🌸 أنمي موسم {season_names[now.month]} {now.year}",
        color=Theme.CARD_BG
    )

    for a in anime_list:
        score = f"⭐ **{a.get('score')}**" if a.get("score") else "✨ جديد"
        embed.add_field(name=a.get("title", "؟"), value=f"{genres_text(a, 2)}\n{score}", inline=True)

    if anime_list and (img := get_image(anime_list[0], "banner")):
        embed.set_image(url=img)

    embed.set_footer(text="🌸 The Veyn • أنمي الموسم الحالي")
    await msg.edit(embed=embed)


@bot.tree.command(name="upcoming", description="أنمي قادم")
async def upcoming_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("⏳ جاري..."), ephemeral=True)

    anime_list = await get_upcoming_anime(8)
    if not anime_list:
        await msg.edit(embed=error_embed("فشل التحميل."))
        return

    embed = discord.Embed(title="⏳ أنمي قادم قريباً", color=Theme.CARD_BG)
    for a in anime_list:
        embed.add_field(name=a.get("title", "؟"), value=genres_text(a, 2), inline=True)

    if anime_list and (img := get_image(anime_list[0], "banner")):
        embed.set_image(url=img)

    embed.set_footer(text="🌸 The Veyn • أنمي قادم")
    await msg.edit(embed=embed)


@bot.tree.command(name="news", description="أخبار الأنمي الأسبوعية")
async def news_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("📰 جاري تحميل الأخبار..."), ephemeral=True)

    anime_list = await get_seasonal_anime(8)
    if not anime_list:
        await msg.edit(embed=error_embed("فشل تحميل الأخبار."))
        return

    embed = discord.Embed(
        title="📰 أخبار الأنمي لهذا الأسبوع",
        description="آخر أخبار وتحديثات عالم الأنمي 🌸",
        color=Theme.INFO,
        timestamp=datetime.now(timezone.utc)
    )

    for i, a in enumerate(anime_list[:8]):
        score = f"⭐ **{a.get('score', '؟')}**" if a.get("score") else "✨ جديد"
        status = status_label(a.get("status", ""))
        embed.add_field(
            name=f"📰 {a.get('title', '؟')[:40]}",
            value=f"{score} | {status}",
            inline=False
        )

    if anime_list and (img := get_image(anime_list[0], "banner")):
        embed.set_image(url=img)

    embed.set_footer(text="🌸 The Veyn • أخبار أسبوعية")
    await msg.edit(embed=embed)


@bot.tree.command(name="reviews", description="تقييمات الأنمي الأسبوعية")
async def reviews_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("📊 جاري تحميل التقييمات..."), ephemeral=True)

    anime_list = await get_top_anime(5)
    if not anime_list:
        await msg.edit(embed=error_embed("فشل تحميل التقييمات."))
        return

    embed = discord.Embed(
        title="📊 تقييمات الأنمي لهذا الأسبوع",
        description="أفضل الأنميات حسب تقييمات المستخدمين 🌸",
        color=Theme.PURPLE,
        timestamp=datetime.now(timezone.utc)
    )

    for i, a in enumerate(anime_list[:5]):
        score = a.get("score", 0)
        stars = rating_stars(score)
        rank_change = a.get("rank", 0)
        embed.add_field(
            name=f"{medal_emoji(i+1)} {a.get('title', '؟')[:35]}",
            value=f"**{score}/10** {stars}\n📊 الترتيب: #{rank_change}" if rank_change else f"**{score}/10** {stars}",
            inline=False
        )

    if anime_list and (img := get_image(anime_list[0], "banner")):
        embed.set_image(url=img)

    embed.set_footer(text="🌸 The Veyn • تقييمات أسبوعية")
    await msg.edit(embed=embed)


@bot.tree.command(name="airing", description="الأنمي الحالي في العرض")
async def airing_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("🔴 جاري التحميل..."), ephemeral=True)

    anime_list = await get_airing_anime(10)
    if not anime_list:
        await msg.edit(embed=error_embed("فشل التحميل."))
        return

    embed = discord.Embed(
        title="🔴 الأنمي يعرض حالياً",
        description="الأنمي اللي تشاهده حالياً في جميع المنصات 🌸",
        color=Theme.DANGER,
        timestamp=datetime.now(timezone.utc)
    )

    for i, a in enumerate(anime_list[:10]):
        score = f"⭐ **{a.get('score', '؟')}**" if a.get("score") else "✨ جديد"
        episodes = a.get("episodes", "?")
        genres = genres_text(a, 2)
        embed.add_field(
            name=f"🍿 {a.get('title', '؟')[:35]}",
            value=f"{score} | 📺 {episodes} | {genres}",
            inline=False
        )

    if anime_list and (img := get_image(anime_list[0], "banner")):
        embed.set_image(url=img)

    embed.set_footer(text="🌸 The Veyn • يعرض حالياً")
    await msg.edit(embed=embed)


@bot.tree.command(name="character", description="بحث عن شخصية أنمي")
@app_commands.describe(name="اسم الشخصية")
async def character_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(
        embed=loading_embed(f"🔍 بدور عن **{name}**..."),
        ephemeral=True
    )

    anime_results = await search_anime(name, limit=5)

    if not anime_results:
        await msg.edit(embed=error_embed(f'ما لقيت نتائج لـ **{name}**'))
        return

    anime = anime_results[0]
    mal_id = anime.get("mal_id")

    if mal_id:
        full_anime = await get_anime_details(mal_id)
        if full_anime:
            anime = full_anime

    characters = await get_characters(mal_id) if mal_id else []

    if not characters:
        await msg.edit(embed=error_embed("ما لقيت شخصيات."))
        return

    embed = discord.Embed(
        title=f"🎭 شخصيات لـ {anime.get('title', '؟')}",
        description=f"تم العثور على **{len(characters)}** شخصية",
        color=Theme.PURPLE,
        timestamp=datetime.now(timezone.utc)
    )

    for char in characters[:5]:
        if "character" in char:
            char_data = char["character"]
        else:
            char_data = char

        char_name = char_data.get("name", "؟") if isinstance(char_data, dict) else "؟"
        role = char.get("role", "")
        favorites = char_data.get("favorites", 0) if isinstance(char_data, dict) else 0
        embed.add_field(
            name=f"👤 {char_name}",
            value=f"🎭 {role} | 💖 {format_number(favorites)}",
            inline=False
        )

    if thumb := get_image(anime, "thumbnail"):
        embed.set_thumbnail(url=thumb)

    view = CharacterSelectView(anime, characters, interaction.user.id)
    await msg.edit(embed=embed, view=view)


# ═══════════════════════════════════════════════════════════════
# 🔧 SETUP & CHANNEL MANAGEMENT COMMANDS
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="setup", description="تخصيص روم لنشر الأخبار")
@app_commands.describe(category="نوع المحتوى (anime/manga/manhwa)")
async def setup_cmd(interaction: discord.Interaction, category: str):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send(
            embed=error_embed("❌ تحتاج صلاحيات Administrator لهذا الأمر."),
            ephemeral=True
        )
        return

    valid_categories = ["anime", "manga", "manhwa"]
    if category not in valid_categories:
        await interaction.followup.send(
            embed=error_embed(f"فئة غير صالحة! استخدم: {', '.join(valid_categories)}"),
            ephemeral=True
        )
        return

    channel_id = interaction.channel.id
    cat_name = get_category_name(category)
    emoji = get_category_emoji(category)
    color = get_category_color(category)

    db.add_channel(channel_id, category)

    embed = discord.Embed(
        title=f"{emoji} تم تخصيص الروم!",
        description=f"✅ تم تفعيل روم <#{channel_id}> لـ **{cat_name}**\n\n"
                   f"📢 سيتم نشر:\n"
                   f"• أخبار {cat_name} الفورية\n"
                   f"• تحديثات وتصنيفات جديدة\n"
                   f"• تقييمات أسبوعية\n\n"
                   f"🔔 رسالة الإشعارات ستظهر أدناه.",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

    await interaction.followup.send(embed=embed, ephemeral=True)

    notification_embed = build_notification_embed(db.channels[channel_id])
    notification_view = NotificationView(channel_id, category)

    notification_msg = await interaction.channel.send(embed=notification_embed, view=notification_view)

    db.channels[channel_id].notification_msg_id = notification_msg.id
    db.save()


@bot.tree.command(name="remove", description="إزالة الروم من نظام النشر")
async def remove_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send(
            embed=error_embed("❌ تحتاج صلاحيات Administrator."),
            ephemeral=True
        )
        return

    channel_id = interaction.channel.id

    if channel_id not in db.channels:
        await interaction.followup.send(
            embed=error_embed("❌ هذا الروم غير مضاف لنظام النشر."),
            ephemeral=True
        )
        return

    cat_name = get_category_name(db.channels[channel_id].category)
    db.remove_channel(channel_id)

    await interaction.followup.send(
        embed=success_embed("تم الإزالة", f"تم إزالة روم <#{channel_id}> من نظام {cat_name}."),
        ephemeral=True
    )


@bot.tree.command(name="list", description="عرض الرومات المفعّلة")
async def list_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    channels = db.get_channels()

    if not channels:
        await interaction.followup.send(
            embed=info_embed("لا توجد رومات", "لم يتم تخصيص أي روم بعد.", color=Theme.INFO),
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="📋 الرومات المفعّلة",
        description=f"عدد الرومات: **{len(channels)}**",
        color=Theme.CARD_BG
    )

    for ch in channels:
        cat_name = get_category_name(ch.category)
        emoji = get_category_emoji(ch.category)
        subscribers = len(db.notification_users.get(ch.channel_id, []))

        try:
            channel = bot.get_channel(ch.channel_id)
            channel_name = channel.name if channel else f"ID: {ch.channel_id}"
        except:
            channel_name = f"ID: {ch.channel_id}"

        embed.add_field(
            name=f"{emoji} {channel_name}",
            value=f"📁 الفئة: **{cat_name}**\n👥 المشتركين: **{subscribers}**",
            inline=False
        )

    embed.set_footer(text="🌸 The Veyn • رومات الأخبار")
    await interaction.followup.send(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# 🖼️ RECOGNITION CHANNEL COMMANDS
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="setrecog", description="تحديد روم للتعرف التلقائي على الصور")
async def setrecog_cmd(interaction: discord.Interaction):
    """تحديد الروم الحالي كروم للتعرف التلقائي على صور الأنمي"""
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send(
            embed=error_embed("❌ تحتاج صلاحيات Administrator."),
            ephemeral=True
        )
        return

    channel_id = interaction.channel.id
    db.set_recognition_channel(channel_id)

    embed = discord.Embed(
        title="🖼️ تم تفعيل التعرف التلقائي!",
        description=f"✅ تم تحديد <#{channel_id}> كروم للتعرف التلقائي.\n\n"
                   f"📸 **الآن أي صورة تُرسل في هذا الروم:\n"
                   f"   البوت سيحللها ويقول اسم الأنمي والشخصية!**\n\n"
                   f"⚠️ لا حاجة لأي أمر - التحليل تلقائي!",
        color=Theme.PURPLE,
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="💡 كيف يعمل؟",
        value="أي شخص يرسل صورة → البوت يتعرف عليها → يرجع:\n"
              "🎬 اسم الأنمي\n"
              "📺 رقم الحلقة\n"
              "📊 نسبة التشابه",
        inline=False
    )

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="clearrecog", description="إزالة روم التعرف التلقائي")
async def clearrecog_cmd(interaction: discord.Interaction):
    """إزالة روم التعرف التلقائي"""
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send(
            embed=error_embed("❌ تحتاج صلاحيات Administrator."),
            ephemeral=True
        )
        return

    if not db.recognition_channel_id:
        await interaction.followup.send(
            embed=error_embed("❌ ما في روم للتعرف حالياً."),
            ephemeral=True
        )
        return

    old_channel = db.recognition_channel_id
    db.clear_recognition_channel()

    await interaction.followup.send(
        embed=success_embed(
            "تم الإزالة",
            f"✅ تم إزالة روم <#{old_channel}> من نظام التعرف التلقائي."
        ),
        ephemeral=True
    )


@bot.tree.command(name="recogstatus", description="عرض حالة نظام التعرف")
async def recogstatus_cmd(interaction: discord.Interaction):
    """عرض الروم المحدد للتعرف التلقائي"""
    await interaction.response.defer(ephemeral=True)

    if db.recognition_channel_id:
        try:
            channel = bot.get_channel(db.recognition_channel_id)
            channel_name = channel.name if channel else f"ID: {db.recognition_channel_id}"
        except:
            channel_name = f"ID: {db.recognition_channel_id}"

        embed = discord.Embed(
            title="🖼️ حالة نظام التعرف",
            description=f"✅ **مفعّل!**\n\n"
                       f"📁 الروم: <#{db.recognition_channel_id}> ({channel_name})\n\n"
                       f"💡 أي صورة تُرسل هناك ستُحلل تلقائياً.",
            color=Theme.SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )
    else:
        embed = discord.Embed(
            title="🖼️ حالة نظام التعرف",
            description="❌ **غير مفعّل!**\n\n"
                       f"استخدم `/setrecog` في الروم المطلوب لتفعيله.",
            color=Theme.WARNING,
            timestamp=datetime.now(timezone.utc)
        )

    await interaction.followup.send(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# 📨 AUTO IMAGE RECOGNITION HANDLER
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_message(message: discord.Message):
    """معالجة الرسائل - التعرف التلقائي على الصور"""
    if message.author.bot:
        await bot.process_commands(message)
        return

    if not message.attachments:
        await bot.process_commands(message)
        return

    image_attachment = None
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith('image/'):
            image_attachment = attachment
            break

    if not image_attachment:
        await bot.process_commands(message)
        return

    # التحقق إذا كان الروم هو روم التعرف المحدد
    if db.recognition_channel_id and message.channel.id == db.recognition_channel_id:
        await process_auto_recognition(message, image_attachment)
        return

    await bot.process_commands(message)


async def process_auto_recognition(message: discord.Message, image_attachment: discord.Attachment):
    """معالجة التعرف التلقائي على الصورة"""

    try:
        await message.channel.typing()

        # رسالة المعالجة
        processing_embed = discord.Embed(
            title="🔍 جاري التحليل...",
            description=f"⏳ يتم التعرف على الصورة...\n"
                       f"📷 من: {message.author.mention}",
            color=Theme.INFO,
            timestamp=datetime.now(timezone.utc)
        )
        processing_msg = await message.reply(embed=processing_embed)

        # تحميل الصورة
        image_data = await image_attachment.read()

        # البحث في Trace.moe
        trace_result = await trace_moe_search(image_data)

        if trace_result and trace_result.get('result') and len(trace_result['result']) > 0:
            # أفضل نتيجة
            best_match = trace_result['result'][0]
            anime_info = best_match.get('anime', {})
            episode_info = best_match.get('episode', '?')
            from_time = best_match.get('from', 0)
            similarity = best_match.get('similarity', 0)
            image_preview = best_match.get('image')

            # تحويل الوقت
            time_str = format_timestamp(from_time)

            # معلومات الأنمي
            mal_id = anime_info.get('mal_id')
            anime_title = anime_info.get('title', 'غير معروف')
            anime_title_jp = anime_info.get('title_native', '')
            mal_url = f"https://myanimelist.net/anime/{mal_id}" if mal_id else None

            # جلب معلومات إضافية من MAL
            full_anime = None
            if mal_id:
                full_anime = await get_anime_details(mal_id)

            # إنشاء امبد النتيجة
            result_embed = build_recognition_result_embed(
                anime_title=anime_title,
                anime_title_jp=anime_title_jp if anime_title_jp else None,
                episode=str(episode_info),
                timestamp_str=time_str,
                similarity=similarity,
                image_preview=image_preview,
                mal_url=mal_url,
                full_anime=full_anime
            )
            result_embed.set_footer(text=f"🌸 The Veyn • تم التحليل بنجاح | من: {message.author.name}")

            await processing_msg.edit(embed=result_embed)

        else:
            # ما لقي نتيجة
            no_result_embed = discord.Embed(
                title="❌ لم يتم التعرف",
                description="🔍 عذراً، ما قدرت أتعرف على هذه الصورة.\n\n"
                           "💡 **نصائح:**\n"
                           "• تأكد إن الصورة واضحة وفيها مشهد أنمي\n"
                           "• جرب صورة من زاوية مختلفة\n"
                           "• تأكد إن الأنمي في قاعدة بيانات Trace.moe",
                color=Theme.WARNING,
                timestamp=datetime.now(timezone.utc)
            )
            no_result_embed.set_image(url=image_attachment.url)
            no_result_embed.set_footer(text=f"🌸 The Veyn • من: {message.author.name}")

            await processing_msg.edit(embed=no_result_embed)

    except Exception as e:
        error_embed_result = error_embed(f"حصل خطأ: {str(e)}")
        await processing_msg.edit(embed=error_embed_result)


# ═══════════════════════════════════════════════════════════════
# 📡 NEWS BROADCAST SYSTEM
# ═══════════════════════════════════════════════════════════════

async def news_broadcast_loop():
    """حلقة نشر الأخبار التلقائية"""
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            anime_list = await get_seasonal_anime(20)

            for anime in anime_list[:5]:
                mal_id = str(anime.get("mal_id", ""))

                if mal_id and mal_id != db.last_anime_news_id:
                    db.last_anime_news_id = mal_id
                    db.save()

                    channels = db.get_channels("anime")

                    for channel_config in channels:
                        try:
                            channel = bot.get_channel(channel_config.channel_id)
                            if not channel:
                                continue

                            # حذف رسالة الإشعارات القديمة
                            if channel_config.notification_msg_id:
                                try:
                                    old_msg = await channel.fetch_message(channel_config.notification_msg_id)
                                    await old_msg.delete()
                                except:
                                    pass

                            # نشر الخبر
                            news_embed = build_news_embed(anime, "anime")
                            notification_view = NotificationView(channel_config.channel_id, "anime")

                            news_msg = await channel.send(embed=news_embed, view=notification_view)

                            channel_config.notification_msg_id = news_msg.id
                            db.save()

                            # إشعار للمشتركين
                            subscribers = db.notification_users.get(channel_config.channel_id, [])
                            for user_id in subscribers:
                                try:
                                    user = await bot.fetch_user(user_id)
                                    if user:
                                        await user.send(
                                            embed=discord.Embed(
                                                title=f"🎬 خبر أنمي جديد!",
                                                description=f"**{anime.get('title', '؟')}**\n"
                                                           f"⭐ {anime.get('score', '؟')}\n\n"
                                                           f"📁 تم النشر في: {channel.name}",
                                                color=Theme.ACCENT
                                            )
                                        )
                                except:
                                    pass

                            await asyncio.sleep(2)

                        except Exception as e:
                            print(f"❌ خطأ في نشر الخبر: {e}")
                            continue

            await asyncio.sleep(300)  # 5 دقائق

        except Exception as e:
            print(f"❌ خطأ في حلقة الأخبار: {e}")
            await asyncio.sleep(60)


# ═══════════════════════════════════════════════════════════════
# 📊 HELP COMMAND
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="help", description="مساعدة وأوامر البوت")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌸 The Veyn v1 - المساعدة",
        description="أوامر البوت المتاحة:",
        color=Theme.CARD_BG,
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="🔍 البحث",
        value="`/anime [اسم]` - البحث عن أنمي\n"
              "`/character [اسم]` - البحث عن شخصية\n"
              "`/suggest` - اقتراح عشوائي",
        inline=False
    )

    embed.add_field(
        name="📊 التصنيفات",
        value="`/top` - أفضل 10 أنمي\n"
              "`/season` - أنمي الموسم\n"
              "`/upcoming` - أنمي قادم\n"
              "`/airing` - يعرض حالياً",
        inline=False
    )

    embed.add_field(
        name="📰 الأخبار",
        value="`/news` - أخبار أسبوعية\n"
              "`/reviews` - تقييمات أسبوعية",
        inline=False
    )

    embed.add_field(
        name="🖼️ التعرف التلقائي (للمشرفين)",
        value="`/setrecog` - تفعيل روم التعرف في الروم الحالي\n"
              "`/clearrecog` - إيقاف التعرف التلقائي\n"
              "`/recogstatus` - عرض حالة النظام\n\n"
              "📸 أي صورة تُرسل هناك تُحلل تلقائياً!",
        inline=False
    )

    embed.add_field(
        name="🔧 تخصيص الرومات (للمشرفين)",
        value="`/setup anime|manga|manhwa` - تخصيص الروم الحالي\n"
              "`/remove` - إزالة الروم\n"
              "`/list` - عرض الرومات المفعّلة",
        inline=False
    )

    embed.set_footer(text="🌸 The Veyn • بوت الأنمي العربي")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# 🚀 RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    bot.run(TOKEN)