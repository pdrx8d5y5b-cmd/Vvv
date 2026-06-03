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
        """تحميل البيانات من الملفات"""
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
        """حفظ البيانات إلى الملفات"""
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
        logger.info(f"✅ تم تحديد روم التعرف: {channel_id}")

    def clear_recognition_channel(self):
        self.recognition_channel_id = None
        self.save()
        logger.info("✅ تم مسح روم التعرف")

    def add_channel(self, channel_id: int, category: str, role_id: int = None):
        self.channels[channel_id] = ChannelConfig(
            channel_id=channel_id,
            category=category,
            notification_role_id=role_id
        )
        self.notification_users[channel_id] = []
        self.save()
        logger.info(f"✅ تم إضافة روم {channel_id} كفئة {category}")

    def remove_channel(self, channel_id: int):
        if channel_id in self.channels:
            del self.channels[channel_id]
        if channel_id in self.notification_users:
            del self.notification_users[channel_id]
        self.save()
        logger.info(f"✅ تم إزالة روم {channel_id}")

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
# 🌐 API CONFIGURATION
# ═══════════════════════════════════════════════════════════════

JIKAN_BASE = "https://api.jikan.moe/v4"
TRACE_MOE_URL = "https://api.trace.moe/search"
SAUCENAO_URL = "https://saucenao.com/search.php"


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
            logger.error(f"❌ خطأ في Jikan API: {e}")
    return None


# ═══════════════════════════════════════════════════════════════
# 🔍 JIKAN FUNCTIONS
# ═══════════════════════════════════════════════════════════════

async def search_anime(query: str, limit: int = 15) -> List[dict]:
    """البحث عن أنمي في MyAnimeList"""
    encoded_query = query.replace(" ", "%20")
    data = await jikan_get(f"/anime?q={encoded_query}&limit={limit}&sfw=true")
    return data.get("data", []) if data else []


async def search_character(query: str, limit: int = 15) -> List[dict]:
    """البحث عن شخصية أنمي مباشرة - يبحث عن الشخصيات أولاً"""
    encoded_query = query.replace(" ", "%20")
    data = await jikan_get(f"/characters?q={encoded_query}&limit={limit}&order_by=favorites&sort=desc")
    return data.get("data", []) if data else []


async def get_character_details(mal_id: int) -> Optional[dict]:
    """جلب تفاصيل الشخصية"""
    data = await jikan_get(f"/characters/{mal_id}/full")
    return data.get("data") if data else None


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


# ═══════════════════════════════════════════════════════════════
# 🖼️ TRACE.MOE FUNCTIONS (للتعرف على الأنمي من الصور)
# ═══════════════════════════════════════════════════════════════

async def saucenao_search(image_data: bytes) -> Optional[dict]:
    """البحث في SauceNAO باستخدام الصورة"""
    if not SAUCENAO_API_KEY:
        logger.warning("❌ SAUCENAO_API_KEY غير موجود في .env")
        return None

    try:
        logger.info("🔍 جاري البحث في SauceNAO...")
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field(
                'output_type', '2' # JSON output
            )
            form.add_field(
                'api_key', SAUCENAO_API_KEY
            )
            form.add_field(
                'file', image_data, filename='image.jpg', content_type='image/jpeg'
            )

            async with session.post(
                SAUCENAO_URL,
                data=form,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                logger.info(f"📡 SauceNAO Response Status: {response.status}")

                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ تم العثور على {len(result.get("results", []))} نتيجة في SauceNAO")
                    return result
                else:
                    text = await response.text()
                    logger.error(f"❌ SauceNAO خطأ: {response.status} - {text}")
                    return None

    except asyncio.TimeoutError:
        logger.error("❌ SauceNAO انتهت المهلة")
        return None
    except Exception as e:
        logger.error(f"❌ خطأ في SauceNAO: {type(e).__name__} - {e}")
        return None


async def trace_moe_search(image_data: bytes) -> Optional[dict]:
    """البحث في Trace.moe باستخدام الصورة - الطريقة الصحيحة"""
    try:
        logger.info("🔍 جاري البحث في Trace.moe...")

        async with aiohttp.ClientSession() as session:
            # الطريقة الصحيحة: نرسل الصورة مباشرة كـ binary data
            form = aiohttp.FormData()
            form.add_field('image', image_data, filename='image.jpg', content_type='image/jpeg')

            async with session.post(
                TRACE_MOE_URL,
                data=form,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                logger.info(f"📡 Trace.moe Response Status: {response.status}")

                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ تم العثور على {len(result.get('result', []))} نتيجة في Trace.moe")
                    return result
                else:
                    text = await response.text()
                    logger.error(f"❌ Trace.moe خطأ: {response.status} - {text}")
                    return None

    except asyncio.TimeoutError:
        logger.error("❌ Trace.moe انتهت المهلة")
        return None
    except Exception as e:
        logger.error(f"❌ خطأ في Trace.moe: {type(e).__name__} - {e}")
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
    if len(synopsis) > 300:
        return synopsis[:300] + "..."
    return synopsis

def rating_stars(score: float) -> str:
    if not score: return ""
    full_stars = int(score // 2)
    half_star = "⭐" if score % 2 >= 1 else ""
    return "⭐" * full_stars + half_star

def year_label(anime: dict) -> str:
    if aired := anime.get("aired", {}).get("prop", {}).get("from", {}).get("year"):
        return str(aired)
    return "—"

def genres_text(anime: dict, limit: int = 3) -> str:
    genres = [g["name"] for g in anime.get("genres", [])][:limit]
    if not genres: return "لا يوجد."
    return ", ".join(genres)

def status_label(status: str) -> str:
    if status == "Finished Airing": return "✅ مكتمل"
    if status == "Currently Airing": return "🔄 يعرض حالياً"
    if status == "Not yet aired": return "⏳ لم يعرض بعد"
    return status

def format_number(num: int) -> str:
    return f"{num:,}"

def get_category_emoji(category: str) -> str:
    if category == "anime": return "🎬"
    if category == "manga": return "📚"
    if category == "manhwa": return "📜"
    return ""

def get_category_color(category: str) -> int:
    if category == "anime": return Theme.ACCENT
    if category == "manga": return Theme.PURPLE
    if category == "manhwa": return Theme.INFO
    return Theme.BG

def get_category_name(category: str) -> str:
    if category == "anime": return "الأنمي"
    if category == "manga": return "المانجا"
    if category == "manhwa": return "المانهوا"
    return ""

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

    embed.set_footer(text=f"🌸 Uniq  |  MAL ID: {mal_id}")
    return embed

def build_search_embed(query: str, results: List[dict]) -> discord.Embed:
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

    embed.set_footer(text="🌸 Uniq • اختر أنمي")
    return embed

def build_top_embed(anime_list: List[dict]) -> discord.Embed:
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

    embed.set_footer(text="🌸 Uniq • اختر أنمي للتفاصيل")
    return embed

def build_character_search_embed(query: str, characters: List[dict]) -> discord.Embed:
    """إنشاء امبد لنتائج البحث عن الشخصيات"""
    embed = discord.Embed(
        title=f"🎭 نتائج البحث عن: {query}",
        description=f"تم العثور على **{len(characters)}** شخصية\nاختر شخصية من القائمة 👇",
        color=Theme.PURPLE,
        timestamp=datetime.now(timezone.utc)
    )

    for i, char in enumerate(characters[:10]):
        char_name = char.get("name", "؟")
        favorites = char.get("favorites", 0)
        about = char.get("about", "")

        # استخراج الأنمي اللي ظهرت فيه الشخصية
        anime_preview = ""
        if "anime" in char and char["anime"]:
            anime_list = char["anime"]
            anime_names = [a.get("anime", {}).get("title", "؟") for a in anime_list[:2]]
            anime_preview = f"\n📺 {', '.join(anime_names[:2])}" if anime_names else ""

        embed.add_field(
            name=f"{medal_emoji(i+1) if i < 3 else '👤'} {char_name}",
            value=f"💖 **{format_number(favorites)}**{anime_preview}",
            inline=False
        )

    if characters and (thumb := get_char_image(characters[0])):
        embed.set_thumbnail(url=thumb)

    embed.set_footer(text="🌸 Uniq • اختر شخصية")
    return embed

def build_character_embed(anime: dict, character: dict) -> discord.Embed:
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

    embed.set_footer(text=f"🌸 Uniq • شخصية من {anime.get('title', '')}")
    return embed

def build_character_detail_embed(char: dict, anime_list: List[dict] = None) -> discord.Embed:
    """إنشاء امبد تفصيلي للشخصية مع الأنمي اللي ظهرت فيه"""
    char_name = char.get("name", "؟")
    char_images = char.get("images", {})
    char_favorites = char.get("favorites", 0)
    char_url = char.get("url", "")
    about = char.get("about", "")

    embed = discord.Embed(
        title=f"🎭 {char_name}",
        color=Theme.PURPLE,
        url=char_url,
        timestamp=datetime.now(timezone.utc)
    )

    if char_favorites:
        embed.add_field(name="⭐ الإعجابات", value=f"**{format_number(char_favorites)}**", inline=True)

    # الأنمي اللي ظهرت فيه
    if anime_list:
        anime_titles = []
        for a in anime_list[:5]:
            if isinstance(a, dict):
                anime_title = a.get("anime", {}).get("title", "؟") if "anime" in a else a.get("title", "؟")
                role = a.get("role", "") if isinstance(a, dict) else ""
                anime_titles.append(f"📺 **{anime_title}** ({role})")

        if anime_titles:
            embed.add_field(
                name="🎬 الأنمي اللي ظهرت فيه",
                value="\n".join(anime_titles),
                inline=False
            )

    if about:
        # تنظيف وصف الشخصية
        about_clean = about.replace("\n\n\n", "\n").replace("\n\n", "\n").strip()
        if len(about_clean) > 600:
            about_clean = about_clean[:600] + "..."
        embed.add_field(name="📝 نبذة", value=about_clean, inline=False)

    if img := char_images.get("jpg", {}).get("image_url"):
        embed.set_thumbnail(url=img)

    embed.set_footer(text=f"🌸 Uniq • {char_name}")
    return embed

def build_news_embed(anime: dict, category: str = "anime") -> discord.Embed:
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

    embed.set_footer(text=f"🌸 Uniq • {cat_name}")
    return embed

def build_notification_embed(channel_config: ChannelConfig) -> discord.Embed:
    cat_name = get_category_name(channel_config.category)
    emoji = get_category_emoji(channel_config.category)

    embed = discord.Embed(
        title=f"{emoji} إشعارات {cat_name}",
        description="🔔 اضغط الزر للحصول على رول الإشعارات!\n\n"
                   "ستصلك إشعارات فورية عند نشر أي خبر جديد.",
        color=get_category_color(channel_config.category),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_footer(text=f"🌸 Uniq • إشعارات {cat_name}")
    return embed

def build_recognition_result_embed(
    anime_title: str,
    anime_title_jp: str = None,
    episode: str = None,
    timestamp_str: str = None,
    similarity: float = None,
    image_preview: str = None,
    mal_url: str = None,
    full_anime: dict = None,
    characters: list = None
) -> discord.Embed:
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
        similarity_percent = round(similarity * 100, 2)
        indicator = "✅" if similarity_percent > 87 else ("⚠️" if similarity_percent > 80 else "❌")
        embed.add_field(name="📊 التشابه", value=f"**{similarity_percent}%** {indicator}", inline=True)

    if full_anime and (genres := genres_text(full_anime, 3)):
        embed.add_field(name="🎭 التصنيفات", value=genres, inline=False)

    if full_anime and full_anime.get('score'):
        embed.add_field(name="⭐ التقييم", value=f"**{full_anime.get('score')}/10**", inline=True)

    if mal_url:
        embed.add_field(name="🔗 رابط", value=f"[MyAnimeList]({mal_url})", inline=True)

    if image_preview:
        embed.set_thumbnail(url=image_preview)

    # إضافة الشخصيات إن وجدت
    if characters and len(characters) > 0:
        char_names = []
        for char in characters[:5]:  # أعلام 5 شخصيات فقط
            if isinstance(char, dict):
                if "character" in char:
                    char_data = char["character"]
                else:
                    char_data = char
                name = char_data.get("name", "؟") if isinstance(char_data, dict) else "؟"
                role = char.get("role", "")
                char_names.append(f"👤 **{name}** ({role})")
            elif isinstance(char, str):
                char_names.append(f"👤 **{char}**")

        if char_names:
            embed.add_field(
                name="🎭 الشخصيات في المشهد",
                value="\n".join(char_names),
                inline=False
            )

    embed.set_footer(text="🌸 Uniq • التعرف التلقائي")
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

        embed.set_footer(text=f"صفحة {self.page + 1}/{self.total_pages + 1} | 🌸 Uniq")

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

        await interaction.response.defer(ephemeral=True)

        # جلب تفاصيل الشخصية الكاملة
        mal_id = char.get("mal_id")
        if mal_id:
            full_char = await get_character_details(mal_id)
            if full_char:
                char = full_char

        # الأنمي اللي ظهرت فيه
        anime_list = char.get("anime", []) if isinstance(char, dict) else []

        # اختيار أول أنمي للعرض
        anime_data = None
        if anime_list:
            first_anime_entry = anime_list[0] if isinstance(anime_list[0], dict) else {}
            anime_info = first_anime_entry.get("anime", {}) if "anime" in first_anime_entry else first_anime_entry

            if isinstance(anime_info, dict) and anime_info.get("mal_id"):
                anime_data = await get_anime_details(anime_info.get("mal_id"))

        if not anime_data:
            anime_data = {"title": "غير محدد", "mal_id": 0}

        embed = build_character_detail_embed(char, anime_list)
        await interaction.followup.send(embed=embed, ephemeral=True)


class CharacterSearchDropdown(discord.ui.View):
    """قائمة منسدلة لاختيار الشخصية من نتائج البحث"""
    def __init__(self, characters: List[dict], user_id: int):
        super().__init__(timeout=300)
        self.characters = characters
        self.user_id = user_id

        options = []
        for i, char in enumerate(characters[:25]):
            char_name = char.get("name", "؟")
            favorites = char.get("favorites", 0)

            # استخراج الأنمي
            anime_preview = ""
            if "anime" in char and char["anime"]:
                anime_list = char["anime"]
                if anime_list:
                    first_anime = anime_list[0].get("anime", {}).get("title", "؟")
                    anime_preview = f" - {first_anime[:30]}"

            options.append(discord.SelectOption(
                label=char_name[:50],
                value=str(i),
                description=f"💖 {format_number(favorites)}{anime_preview}",
                emoji="👤"
            ))

        select = discord.ui.Select(placeholder="🎭 اختر شخصية من القائمة...", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        char = self.characters[idx]

        await interaction.response.defer(ephemeral=True)

        # جلب تفاصيل الشخصية الكاملة
        mal_id = char.get("mal_id")
        if mal_id:
            full_char = await get_character_details(mal_id)
            if full_char:
                char = full_char

        # الأنمي اللي ظهرت فيه
        anime_list = char.get("anime", []) if isinstance(char, dict) else []

        # اختيار أول أنمي للعرض
        anime_data = None
        if anime_list:
            first_anime_entry = anime_list[0] if isinstance(anime_list[0], dict) else {}
            anime_info = first_anime_entry.get("anime", {}) if "anime" in first_anime_entry else first_anime_entry

            if isinstance(anime_info, dict) and anime_info.get("mal_id"):
                anime_data = await get_anime_details(anime_info.get("mal_id"))

        if not anime_data:
            anime_data = {"title": "غير محدد", "mal_id": 0}

        embed = build_character_detail_embed(char, anime_list)
        await interaction.followup.send(embed=embed, ephemeral=True)


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
                embed=success_embed("اشتراك ناجح!", f"ستصلك إشعارات {get_category_name(self.category)} الجديدة"),
                ephemeral=True
            )


# ═══════════════════════════════════════════════════════════════
# 🤖 BOT SETUP
# ═══════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    await bot.tree.sync()
    logger.info("Synced slash commands.")
    bot.loop.create_task(news_broadcast_loop())


@bot.event
async def on_message(message: discord.Message):
    """معالجة الرسائل - التعرف التلقائي على الصور"""
    # تجاهل رسائل البوت
    if message.author.bot: return

    # تجاهل الرسائل بدون مرفقات
    if not message.attachments:
        await bot.process_commands(message)
        return

    # معالجة الصور المرفقة
    for attachment in message.attachments:
        if 'image' in attachment.content_type:
            await process_auto_recognition(message, attachment)
            break # معالجة أول صورة فقط

    await bot.process_commands(message)


async def process_auto_recognition(message: discord.Message, image_attachment: discord.Attachment):
    """معالجة التعرف التلقائي على الصور (الأنمي والشخصيات)"""
    processing_msg = None
    try:
        recognition_channel_id = db.recognition_channel_id
        if not recognition_channel_id or message.channel.id != recognition_channel_id:
            return

        image_data = await image_attachment.read()
        processing_msg = await message.reply(embed=loading_embed("جاري تحليل الصورة..."))

        # 1. محاولة التعرف على الشخصية باستخدام SauceNAO
        logger.info("🔍 محاولة التعرف على الشخصية باستخدام SauceNAO...")
        saucenao_result = await saucenao_search(image_data)

        if saucenao_result and saucenao_result.get("results"):
            best_match = saucenao_result["results"][0]
            header = best_match.get("header", {})
            data = best_match.get("data", {})
            ext_urls = data.get("ext_urls", [])

            character_name = data.get("creator") or data.get("character") or "غير معروف"
            similarity = float(header.get("similarity", 0))

            if similarity > 70: # نسبة تشابه عالية تعتبر كافية للتعرف على الشخصية
                embed = discord.Embed(
                    title=f"🎭 تم التعرف على الشخصية: {character_name}",
                    description=f"**التشابه:** {similarity:.2f}%\n**المصدر:** [اضغط هنا]({source_url})",
                    color=Theme.PURPLE
                )
                if header.get("thumbnail"):
                    embed.set_thumbnail(url=header["thumbnail"])
                embed.set_footer(text=f"🌸 Uniq • تعرف على الشخصيات | من: {message.author.name}")
                await processing_msg.edit(embed=embed)
                logger.info(f"✅ تم التعرف على الشخصية بنجاح لـ {message.author}")
                return
            else:
                logger.info("⚠️ نسبة تشابه SauceNAO منخفضة، جاري محاولة Trace.moe...")

        # 2. إذا لم يتم التعرف على الشخصية أو كانت نسبة التشابه منخفضة، نعود لـ Trace.moe للأنمي
        logger.info("🔍 جاري البحث في Trace.moe عن الأنمي...")
        trace_result = await trace_moe_search(image_data)

        if trace_result and trace_result.get("result"):
            best_match = trace_result["result"][0]
            anime_info = best_match.get("anilist", {})
            from_time = best_match.get("from", 0)
            to_time = best_match.get("to", 0)
            episode_info = best_match.get("episode", "?")
            similarity = best_match.get("similarity", 0)
            image_preview = best_match.get("image")

            # تحويل نسبة التشابه إلى مئوية
            similarity_percent = round(similarity * 100, 2)
            indicator = "✅" if similarity_percent > 87 else ("⚠️" if similarity_percent > 80 else "❌")

            # تحويل الوقت
            time_str = format_timestamp(from_time)

            # معلومات الأنمي
            mal_id = anime_info.get("mal_id")
            anime_title = anime_info.get("title", "غير معروف")
            anime_title_jp = anime_info.get("title_native", "")
            mal_url = f"https://myanimelist.net/anime/{mal_id}" if mal_id else None

            # جلب معلومات إضافية من MAL
            full_anime = None
            anime_characters = []
            if mal_id:
                logger.info(f"📡 جاري جلب معلومات MAL لـ: {mal_id}")
                full_anime = await get_anime_details(mal_id)

                # جلب الشخصيات
                logger.info(f"🎭 جاري جلب شخصيات الأنمي...")
                anime_characters = await get_characters(mal_id)
                if anime_characters:
                    logger.info(f"✅ تم العثور على {len(anime_characters)} شخصية")

            # إنشاء امبد النتيجة
            result_embed = build_recognition_result_embed(
                anime_title=anime_title,
                anime_title_jp=anime_title_jp if anime_title_jp else None,
                episode=str(episode_info),
                timestamp_str=time_str,
                similarity=similarity,
                image_preview=image_preview,
                mal_url=mal_url,
                full_anime=full_anime,
                characters=anime_characters
            )
            result_embed.set_footer(text=f"🌸 Uniq • تم التحليل بنجاح | من: {message.author.name}")

            await processing_msg.edit(embed=result_embed)
            logger.info(f"✅ تم إرسال نتيجة التعرف لـ {message.author}")

        else:
            logger.warning("❌ ما تم العثور على نتائج في Trace.moe")
            # ما لقي نتيجة
            no_result_embed = discord.Embed(
                title="❌ لم يتم التعرف على الأنمي",
                description="🔍 عذراً، ما قدرت أتعرف على هذه الصورة.\n\n"
                           "💡 **نصائح:**\n"
                           "• تأكد إن الصورة واضحة وفيها مشهد أنمي\n"
                           "• جرب صورة من زاوية مختلفة\n"
                           "• تأكد إن الأنمي في قاعدة بيانات Trace.moe",
                color=Theme.WARNING,
                timestamp=datetime.now(timezone.utc)
            )
            no_result_embed.set_image(url=image_attachment.url)
            no_result_embed.set_footer(text=f"🌸 Uniq • من: {message.author.name}")

            await processing_msg.edit(embed=no_result_embed)

    except Exception as e:
        logger.error(f"❌ خطأ في process_auto_recognition: {type(e).__name__} - {e}")

        if processing_msg:
            error_embed_result = error_embed(f"حصل خطأ أثناء التحليل: {str(e)}")
            await processing_msg.edit(embed=error_embed_result)
        else:
            await message.reply(embed=error_embed(f"حصل خطأ أثناء التحليل: {str(e)}"))


# ═══════════════════════════════════════════════════════════════
# 📡 NEWS BROADCAST SYSTEM
# ═══════════════════════════════════════════════════════════════

async def news_broadcast_loop():
    """حلقة نشر الأخبار التلقائية"""
    await bot.wait_until_ready()
    logger.info("📡 بدأ نظام نشر الأخبار التلقائي")

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
                            logger.error(f"❌ خطأ في نشر الخبر: {e}")
                            continue

            await asyncio.sleep(300)  # 5 دقائق

        except Exception as e:
            logger.error(f"❌ خطأ في حلقة الأخبار: {e}")
            await asyncio.sleep(60)


# ═══════════════════════════════════════════════════════════════
# 📊 HELP COMMAND
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="help", description="مساعدة وأوامر البوت")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌸 Uniq v1.0 - المساعدة",
        description="أوامر البوت المتاحة:",
        color=Theme.CARD_BG,
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="🔍 البحث",
        value="`/anime [اسم]` - البحث عن أنمي\n"
              "`/character [اسم]` - البحث عن شخصية (يبحث عن الشخصيات أولاً!)\n"
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

    embed.set_footer(text="🌸 Uniq • بوت الأنمي العربي")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# 🚀 RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("🚀 جاري تشغيل البوت...")
    if TOKEN:
        bot.run(TOKEN)
    else:
        logger.error("❌ لم يتم العثور على توكن البوت. يرجى التأكد من وجوده في ملف .env")


@bot.tree.command(name="anime", description="البحث عن أنمي في MyAnimeList")
@app_commands.describe(name="اسم الأنمي للبحث عنه")
async def anime_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    results = await search_anime(name)
    if results:
        view = SearchDropdown(results, interaction.user.id)
        await interaction.followup.send(embed=build_search_embed(name, results), view=view)
    else:
        await interaction.followup.send(embed=error_embed("ما لقيت أي أنمي بهذا الاسم."))


@bot.tree.command(name="character", description="البحث عن شخصية أنمي")
@app_commands.describe(name="اسم الشخصية للبحث عنها")
async def character_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    characters = await search_character(name)
    if characters:
        view = CharacterSearchDropdown(characters, interaction.user.id)
        await interaction.followup.send(embed=build_character_search_embed(name, characters), view=view)
    else:
        await interaction.followup.send(embed=error_embed("ما لقيت أي شخصية بهذا الاسم."))


@bot.tree.command(name="suggest", description="الحصول على اقتراح أنمي عشوائي")
async def suggest_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    anime = await get_random_anime()
    if anime:
        embed = build_main_embed(anime, "🎲 ")
        view = AnimeActionsView(anime, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.followup.send(embed=error_embed("حصل خطأ أثناء جلب اقتراح الأنمي."))


@bot.tree.command(name="top", description="عرض أفضل 10 أنمي")
async def top_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    anime_list = await get_top_anime()
    if anime_list:
        embed = build_top_embed(anime_list)
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(embed=error_embed("لم أتمكن من جلب أفضل الأنميات."))


@bot.tree.command(name="season", description="عرض أنمي الموسم الحالي")
async def season_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    anime_list = await get_seasonal_anime()
    if anime_list:
        embed = discord.Embed(
            title="🌸 أنمي الموسم الحالي",
            description="أبرز أنميات الموسم",
            color=Theme.ACCENT
        )
        for i, anime in enumerate(anime_list[:10]):
            embed.add_field(name=f"{i+1}. {anime.get('title', '؟')}", value=f"⭐ {anime.get('score', '؟')}", inline=False)
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(embed=error_embed("لم أتمكن من جلب أنمي الموسم."))


@bot.tree.command(name="upcoming", description="عرض الأنميات القادمة")
async def upcoming_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    anime_list = await get_upcoming_anime()
    if anime_list:
        embed = discord.Embed(
            title="⏳ أنميات قادمة",
            description="قائمة بالأنميات التي لم تعرض بعد",
            color=Theme.WARNING
        )
        for i, anime in enumerate(anime_list[:10]):
            embed.add_field(name=f"{i+1}. {anime.get("title", "؟")}", value=f"تاريخ العرض: {anime.get("aired", {}).get("string", "قريباً")}", inline=False)
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(embed=error_embed("لم أتمكن من جلب الأنميات القادمة."))


@bot.tree.command(name="airing", description="عرض الأنميات التي تعرض حالياً")
async def airing_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    anime_list = await get_airing_anime()
    if anime_list:
        embed = discord.Embed(
            title="🔄 أنميات تعرض حالياً",
            description="قائمة بالأنميات التي تعرض حالياً",
            color=Theme.INFO
        )
        for i, anime in enumerate(anime_list[:10]):
            embed.add_field(name=f"{i+1}. {anime.get("title", "؟")}", value=f"⭐ {anime.get("score", "؟")}", inline=False)
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(embed=error_embed("لم أتمكن من جلب الأنميات التي تعرض حالياً."))


@bot.tree.command(name="setrecog", description="تفعيل روم التعرف التلقائي في الروم الحالي (للمشرفين)")
@app_commands.default_permissions(manage_channels=True)
async def setrecog_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(embed=error_embed("ليس لديك الصلاحيات الكافية لاستخدام هذا الأمر."), ephemeral=True)
        return

    db.set_recognition_channel(interaction.channel_id)
    await interaction.response.send_message(embed=success_embed("تم التفعيل", f"تم تفعيل روم التعرف التلقائي في هذا الروم: <#{interaction.channel_id}>."), ephemeral=True)


@bot.tree.command(name="clearrecog", description="إيقاف التعرف التلقائي على الصور (للمشرفين)")
@app_commands.default_permissions(manage_channels=True)
async def clearrecog_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(embed=error_embed("ليس لديك الصلاحيات الكافية لاستخدام هذا الأمر."), ephemeral=True)
        return

    db.clear_recognition_channel()
    await interaction.response.send_message(embed=success_embed("تم الإيقاف", "تم إيقاف التعرف التلقائي على الصور."), ephemeral=True)


@bot.tree.command(name="recogstatus", description="عرض حالة نظام التعرف التلقائي (للمشرفين)")
@app_commands.default_permissions(manage_channels=True)
async def recogstatus_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(embed=error_embed("ليس لديك الصلاحيات الكافية لاستخدام هذا الأمر."), ephemeral=True)
        return

    channel_id = db.recognition_channel_id
    if channel_id:
        await interaction.response.send_message(embed=info_embed("حالة التعرف التلقائي", f"التعرف التلقائي مفعل في الروم: <#{channel_id}>."), ephemeral=True)
    else:
        await interaction.response.send_message(embed=info_embed("حالة التعرف التلقائي", "التعرف التلقائي غير مفعل في أي روم."), ephemeral=True)


@bot.tree.command(name="setup", description="تخصيص الروم الحالي لفئة معينة (للمشرفين)")
@app_commands.describe(category="الفئة (anime, manga, manhwa)", role_id="معرف الرول للإشعارات (اختياري)")
@app_commands.default_permissions(manage_channels=True)
async def setup_cmd(interaction: discord.Interaction, category: str, role_id: Optional[str] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(embed=error_embed("ليس لديك الصلاحيات الكافية لاستخدام هذا الأمر."), ephemeral=True)
        return

    if category not in ["anime", "manga", "manhwa"]:
        await interaction.response.send_message(embed=error_embed("الفئة غير صالحة. يجب أن تكون: anime, manga, manhwa."), ephemeral=True)
        return

    try:
        role_id_int = int(role_id) if role_id else None
    except ValueError:
        await interaction.response.send_message(embed=error_embed("معرف الرول غير صالح. يجب أن يكون رقماً."), ephemeral=True)
        return

    db.add_channel(interaction.channel_id, category, role_id_int)
    await interaction.response.send_message(embed=success_embed("تم التخصيص", f"تم تخصيص هذا الروم لفئة {get_category_name(category)}."), ephemeral=True)


@bot.tree.command(name="remove", description="إزالة تخصيص الروم الحالي (للمشرفين)")
@app_commands.default_permissions(manage_channels=True)
async def remove_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(embed=error_embed("ليس لديك الصلاحيات الكافية لاستخدام هذا الأمر."), ephemeral=True)
        return

    db.remove_channel(interaction.channel_id)
    await interaction.response.send_message(embed=success_embed("تم الإزالة", "تم إزالة تخصيص هذا الروم."), ephemeral=True)


@bot.tree.command(name="list", description="عرض الرومات المفعّلة (للمشرفين)")
@app_commands.default_permissions(manage_channels=True)
async def list_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(embed=error_embed("ليس لديك الصلاحيات الكافية لاستخدام هذا الأمر."), ephemeral=True)
        return

    channels = db.get_channels()
    if channels:
        description = "\n".join([f"<#{c.channel_id}> - {get_category_name(c.category)}" for c in channels])
        await interaction.response.send_message(embed=info_embed("الرومات المفعّلة", description), ephemeral=True)
    else:
        await interaction.response.send_message(embed=info_embed("الرومات المفعّلة", "لا توجد رومات مفعلة حالياً."), ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# 🤖 BOT SETUP
# ═══════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    await bot.tree.sync()
    logger.info("Synced slash commands.")
    bot.loop.create_task(news_broadcast_loop())


@bot.event
async def on_message(message: discord.Message):
    """معالجة الرسائل - التعرف التلقائي على الصور"""
    # تجاهل رسائل البوت
    if message.author.bot: return

    # تجاهل الرسائل بدون مرفقات
    if not message.attachments:
        await bot.process_commands(message)
        return

    # معالجة الصور المرفقة
    for attachment in message.attachments:
        if 'image' in attachment.content_type:
            await process_auto_recognition(message, attachment)
            break # معالجة أول صورة فقط

    await bot.process_commands(message)


async def process_auto_recognition(message: discord.Message, image_attachment: discord.Attachment):
    """معالجة التعرف التلقائي على الصور (الأنمي والشخصيات)"""
    processing_msg = None
    try:
        recognition_channel_id = db.recognition_channel_id
        if not recognition_channel_id or message.channel.id != recognition_channel_id:
            return

        image_data = await image_attachment.read()
        processing_msg = await message.reply(embed=loading_embed("جاري تحليل الصورة..."))

        # 1. محاولة التعرف على الشخصية باستخدام SauceNAO
        logger.info("🔍 محاولة التعرف على الشخصية باستخدام SauceNAO...")
        saucenao_result = await saucenao_search(image_data)

        if saucenao_result and saucenao_result.get("results"):
            best_match = saucenao_result["results"][0]
            header = best_match.get("header", {})
            data = best_match.get("data", {})
            ext_urls = data.get("ext_urls", [])

            character_name = data.get("creator") or data.get("character") or "غير معروف"
            similarity = float(header.get("similarity", 0))

            if similarity > 70: # نسبة تشابه عالية تعتبر كافية للتعرف على الشخصية
                embed = discord.Embed(
                    title=f"🎭 تم التعرف على الشخصية: {character_name}",
                    description=f"**التشابه:** {similarity:.2f}%\n**المصدر:** [اضغط هنا]({source_url})",
                    color=Theme.PURPLE
                )
                if header.get("thumbnail"):
                    embed.set_thumbnail(url=header["thumbnail"])
                embed.set_footer(text=f"🌸 Uniq • تعرف على الشخصيات | من: {message.author.name}")
                await processing_msg.edit(embed=embed)
                logger.info(f"✅ تم التعرف على الشخصية بنجاح لـ {message.author}")
                return
            else:
                logger.info("⚠️ نسبة تشابه SauceNAO منخفضة، جاري محاولة Trace.moe...")

        # 2. إذا لم يتم التعرف على الشخصية أو كانت نسبة التشابه منخفضة، نعود لـ Trace.moe للأنمي
        logger.info("🔍 جاري البحث في Trace.moe عن الأنمي...")
        trace_result = await trace_moe_search(image_data)

        if trace_result and trace_result.get("result"):
            best_match = trace_result["result"][0]
            anime_info = best_match.get("anilist", {})
            from_time = best_match.get("from", 0)
            to_time = best_match.get("to", 0)
            episode_info = best_match.get("episode", "?")
            similarity = best_match.get("similarity", 0)
            image_preview = best_match.get("image")

            # تحويل نسبة التشابه إلى مئوية
            similarity_percent = round(similarity * 100, 2)
            indicator = "✅" if similarity_percent > 87 else ("⚠️" if similarity_percent > 80 else "❌")

            # تحويل الوقت
            time_str = format_timestamp(from_time)

            # معلومات الأنمي
            mal_id = anime_info.get("mal_id")
            anime_title = anime_info.get("title", "غير معروف")
            anime_title_jp = anime_info.get("title_native", "")
            mal_url = f"https://myanimelist.net/anime/{mal_id}" if mal_id else None

            # جلب معلومات إضافية من MAL
            full_anime = None
            anime_characters = []
            if mal_id:
                logger.info(f"📡 جاري جلب معلومات MAL لـ: {mal_id}")
                full_anime = await get_anime_details(mal_id)

                # جلب الشخصيات
                logger.info(f"🎭 جاري جلب شخصيات الأنمي...")
                anime_characters = await get_characters(mal_id)
                if anime_characters:
                    logger.info(f"✅ تم العثور على {len(anime_characters)} شخصية")

            # إنشاء امبد النتيجة
            result_embed = build_recognition_result_embed(
                anime_title=anime_title,
                anime_title_jp=anime_title_jp if anime_title_jp else None,
                episode=str(episode_info),
                timestamp_str=time_str,
                similarity=similarity,
                image_preview=image_preview,
                mal_url=mal_url,
                full_anime=full_anime,
                characters=anime_characters
            )
            result_embed.set_footer(text=f"🌸 Uniq • تم التحليل بنجاح | من: {message.author.name}")

            await processing_msg.edit(embed=result_embed)
            logger.info(f"✅ تم إرسال نتيجة التعرف لـ {message.author}")

        else:
            logger.warning("❌ ما تم العثور على نتائج في Trace.moe")
            # ما لقي نتيجة
            no_result_embed = discord.Embed(
                title="❌ لم يتم التعرف على الأنمي",
                description="🔍 عذراً، ما قدرت أتعرف على هذه الصورة.\n\n"
                           "💡 **نصائح:**\n"
                           "• تأكد إن الصورة واضحة وفيها مشهد أنمي\n"
                           "• جرب صورة من زاوية مختلفة\n"
                           "• تأكد إن الأنمي في قاعدة بيانات Trace.moe",
                color=Theme.WARNING,
                timestamp=datetime.now(timezone.utc)
            )
            no_result_embed.set_image(url=image_attachment.url)
            no_result_embed.set_footer(text=f"🌸 Uniq • من: {message.author.name}")

            await processing_msg.edit(embed=no_result_embed)

    except Exception as e:
        logger.error(f"❌ خطأ في process_auto_recognition: {type(e).__name__} - {e}")

        if processing_msg:
            error_embed_result = error_embed(f"حصل خطأ أثناء التحليل: {str(e)}")
            await processing_msg.edit(embed=error_embed_result)
        else:
            await message.reply(embed=error_embed(f"حصل خطأ أثناء التحليل: {str(e)}"))


# ═══════════════════════════════════════════════════════════════
# 📡 NEWS BROADCAST SYSTEM
# ═══════════════════════════════════════════════════════════════

async def news_broadcast_loop():
    """حلقة نشر الأخبار التلقائية"""
    await bot.wait_until_ready()
    logger.info("📡 بدأ نظام نشر الأخبار التلقائي")

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
                                                description=f"**{anime.get(\'title\', \'؟\')}**\n"
                                                           f"⭐ {anime.get(\'score\', \'؟\')}\n\n"
                                                           f"📁 تم النشر في: {channel.name}",
                                                color=Theme.ACCENT
                                            )
                                        )
                                except:
                                    pass

                            await asyncio.sleep(2)

                        except Exception as e:
                            logger.error(f"❌ خطأ في نشر الخبر: {e}")
                            continue

            await asyncio.sleep(300)  # 5 دقائق

        except Exception as e:
            logger.error(f"❌ خطأ في حلقة الأخبار: {e}")
            await asyncio.sleep(60)


# ═══════════════════════════════════════════════════════════════
# 📊 HELP COMMAND
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="help", description="مساعدة وأوامر البوت")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌸 Uniq v1.0 - المساعدة",
        description="أوامر البوت المتاحة:",
        color=Theme.CARD_BG,
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="🔍 البحث",
        value="`/anime [اسم]` - البحث عن أنمي\n"
              "`/character [اسم]` - البحث عن شخصية (يبحث عن الشخصيات أولاً!)\n"
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

    embed.set_footer(text="🌸 Uniq • بوت الأنمي العربي")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# 🚀 RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("🚀 جاري تشغيل البوت...")
    if TOKEN:
        bot.run(TOKEN)
    else:
        logger.error("❌ لم يتم العثور على توكن البوت. يرجى التأكد من وجوده في ملف .env"))


@bot.tree.command(name="news", description="عرض الأخبار الأسبوعية (غير مفعل حالياً)")
async def news_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=info_embed("الأخبار", "عذراً، أمر الأخبار غير مفعل حالياً."), ephemeral=True)


@bot.tree.command(name="reviews", description="عرض التقييمات الأسبوعية (غير مفعل حالياً)")
async def reviews_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=info_embed("التقييمات", "عذراً، أمر التقييمات غير مفعل حالياً."), ephemeral=True)
