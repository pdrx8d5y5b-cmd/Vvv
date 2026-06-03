# 🔥 Uniq — بوت الأنمي v2.2 Final Edition
# نظام التعرف على الصور + نظام الأخبار المقسم
# مُصحّح بالكامل - URLs صحيحة

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
import io

# إعداد الـ logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('Uniq')

load_dotenv()
TOKEN = os.getenv("TOKEN")

# ═══════════════════════════════════════════════════════════════
# ⚠️ API KEYS
# ═══════════════════════════════════════════════════════════════

SAUCENAO_API_KEY = os.getenv("SAUCENAO_API_KEY", "c7626f0f3cb1519513dea1ca5d2a2f307d2a5327")

# ═══════════════════════════════════════════════════════════════
# 📁 FILE PATHS
# ═══════════════════════════════════════════════════════════════

DATA_DIR = "/home/ubuntu/data"
CHANNELS_FILE = f"{DATA_DIR}/news_channels.json"
CACHE_FILE = f"{DATA_DIR}/cache.json"
RECOGNITION_CHANNEL_FILE = f"{DATA_DIR}/recognition_channel.json"

os.makedirs(DATA_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 💾 DATABASE
# ═══════════════════════════════════════════════════════════════

@dataclass
class NewsChannelConfig:
    channel_id: int
    category: str
    enabled: bool = True
    last_news_id: str = ""

class NewsDatabase:
    def __init__(self):
        self.channels: Dict[str, Dict[int, NewsChannelConfig]] = {
            "anime": {}, "manga": {}, "manhwa": {}
        }
        self.notification_users: Dict[str, Dict[int, List[int]]] = {
            "anime": {}, "manga": {}, "manhwa": {}
        }
        self.recognition_channel_id: Optional[int] = None
        self.last_ids: Dict[str, str] = {"anime": "", "manga": "", "manhwa": ""}
        self.load()

    def load(self):
        try:
            if os.path.exists(CHANNELS_FILE):
                with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for cat in ["anime", "manga", "manhwa"]:
                        if cat in data:
                            for k, v in data[cat].items():
                                self.channels[cat][int(k)] = NewsChannelConfig(**v)
                        if f"notifications_{cat}" in data:
                            self.notification_users[cat] = data[f"notifications_{cat}"]
                        if f"last_id_{cat}" in data:
                            self.last_ids[cat] = data[f"last_id_{cat}"]

            if os.path.exists(RECOGNITION_CHANNEL_FILE):
                with open(RECOGNITION_CHANNEL_FILE, 'r', encoding='utf-8') as f:
                    self.recognition_channel_id = json.load(f).get("channel_id")

            logger.info("✅ تم تحميل البيانات بنجاح")
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل البيانات: {e}")

    def save(self):
        try:
            data = {}
            for cat in ["anime", "manga", "manhwa"]:
                data[cat] = {str(k): asdict(v) for k, v in self.channels[cat].items()}
                data[f"notifications_{cat}"] = self.notification_users[cat]
                data[f"last_id_{cat}"] = self.last_ids[cat]

            with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            with open(RECOGNITION_CHANNEL_FILE, 'w', encoding='utf-8') as f:
                json.dump({"channel_id": self.recognition_channel_id}, f)

        except Exception as e:
            logger.error(f"❌ خطأ في حفظ البيانات: {e}")

    def set_recognition_channel(self, channel_id: int):
        self.recognition_channel_id = channel_id
        self.save()
        logger.info(f"✅ تم تعيين روم التعرف: {channel_id}")

    def clear_recognition_channel(self):
        self.recognition_channel_id = None
        self.save()
        logger.info("❌ تم إلغاء روم التعرف")

    def add_news_channel(self, channel_id: int, category: str):
        self.channels[category][channel_id] = NewsChannelConfig(
            channel_id=channel_id, category=category
        )
        self.notification_users[category][channel_id] = []
        self.save()

    def remove_news_channel(self, channel_id: int, category: str):
        if channel_id in self.channels[category]:
            del self.channels[category][channel_id]
        if channel_id in self.notification_users[category]:
            del self.notification_users[category][channel_id]
        self.save()

    def get_news_channels(self, category: str) -> List[NewsChannelConfig]:
        return [c for c in self.channels[category].values() if c.enabled]

    def is_channel_configured(self, channel_id: int, category: str) -> bool:
        return channel_id in self.channels[category]

    def set_last_news_id(self, category: str, news_id: str):
        self.last_ids[category] = news_id
        self.save()

    def get_last_news_id(self, category: str) -> str:
        return self.last_ids.get(category, "")

db = NewsDatabase()

# ═══════════════════════════════════════════════════════════════
# 🌐 API FUNCTIONS
# ═══════════════════════════════════════════════════════════════

JIKAN_BASE = "https://api.jikan.moe/v4"

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

# === Anime APIs ===
async def search_anime(query: str, limit: int = 15) -> List[dict]:
    data = await jikan_get(f"/anime?q={query.replace(' ', '%20')}&limit={limit}&sfw=true")
    return data.get("data", []) if data else []

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

# === Manga APIs ===
async def search_manga(query: str, limit: int = 15) -> List[dict]:
    data = await jikan_get(f"/manga?q={query.replace(' ', '%20')}&limit={limit}&sfw=true")
    return data.get("data", []) if data else []

async def get_manga_details(mal_id: int) -> Optional[dict]:
    data = await jikan_get(f"/manga/{mal_id}/full")
    return data.get("data") if data else None

async def get_top_manga(limit: int = 10) -> List[dict]:
    data = await jikan_get(f"/top/manga?limit={limit}")
    return data.get("data", []) if data else []

async def get_publishing_manga(limit: int = 10) -> List[dict]:
    data = await jikan_get(f"/top/manga?filter=airing&limit={limit}")
    return data.get("data", []) if data else []

# === Character APIs ===
async def search_character(query: str, limit: int = 15) -> List[dict]:
    data = await jikan_get(f"/characters?q={query.replace(' ', '%20')}&limit={limit}&order_by=favorites&sort=desc")
    return data.get("data", []) if data else []

async def get_character_details(mal_id: int) -> Optional[dict]:
    data = await jikan_get(f"/characters/{mal_id}/full")
    return data.get("data") if data else None

async def get_characters(mal_id: int) -> List[dict]:
    data = await jikan_get(f"/anime/{mal_id}/characters")
    return data.get("data", []) if data else []

# ═══════════════════════════════════════════════════════════════
# 🖼️ IMAGE RECOGNITION APIs (URLs مُصحّحة)
# ═══════════════════════════════════════════════════════════════

async def saucenao_search(image_data: bytes) -> Optional[dict]:
    """
    البحث في SauceNAO باستخدام API Key
    ✅ URL الصحيح: https://saucenao.com/api.php
    """
    if not SAUCENAO_API_KEY or len(SAUCENAO_API_KEY) < 10:
        logger.warning("⚠️ SauceNAO API Key غير موجود أو قصير!")
        return None

    try:
        async with aiohttp.ClientSession() as session:
            # إنشاء Form Data
            form = aiohttp.FormData()
            form.add_field('output_type', '2')  # JSON output
            form.add_field('api_key', SAUCENAO_API_KEY)
            form.add_field('file', ('image.png', image_data, 'image/png'))

            logger.info("🔍 جاري البحث في SauceNAO...")

            # ✅ URL الصحيح هو api.php وليس search.php
            async with session.post(
                "https://saucenao.com/api.php",
                data=form,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                logger.info(f"📡 SauceNAO Response Status: {response.status}")

                if response.status == 200:
                    result = await response.json()
                    results_count = len(result.get('results', []))
                    logger.info(f"✅ SauceNAO: {results_count} نتائج")
                    return result

                elif response.status == 401:
                    logger.error("❌ SauceNAO: API Key غير صحيح")
                elif response.status == 403:
                    logger.error("❌ SauceNAO: تم رفض الوصول - تحقق من الـ API Key")
                elif response.status == 429:
                    logger.error("❌ SauceNAO: تم تجاوز الحد المسموح")
                else:
                    text = await response.text()
                    logger.error(f"❌ SauceNAO Error: {response.status} - {text[:200]}")

    except asyncio.TimeoutError:
        logger.error("❌ SauceNAO: انتهت مهلة الطلب")
    except aiohttp.ClientError as e:
        logger.error(f"❌ SauceNAO Client Error: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ في SauceNAO: {e}")

    return None


async def trace_moe_search(image_data: bytes) -> Optional[dict]:
    """
    البحث في Trace.moe (مجاني - لا يحتاج API Key)
    ✅ URL الصحيح: https://api.trace.moe/search
    """
    try:
        async with aiohttp.ClientSession() as session:
            # إنشاء Form Data مع الملف
            form = aiohttp.FormData()
            form.add_field('image', ('image.png', image_data, 'image/png'))

            logger.info("🔍 جاري البحث في Trace.moe...")

            # ✅ URL صحيح
            async with session.post(
                "https://api.trace.moe/search",
                data=form,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                logger.info(f"📡 Trace.moe Response Status: {response.status}")

                if response.status == 200:
                    result = await response.json()
                    if result.get("result"):
                        logger.info(f"✅ Trace.moe: {len(result['result'])} نتيجة")
                    else:
                        logger.warning("⚠️ Trace.moe: لا توجد نتائج")
                    return result

                elif response.status == 400:
                    text = await response.text()
                    logger.error(f"❌ Trace.moe: {text}")
                    # قد تكون المشكلة في صيغة الملف - جرب بصيغة أخرى
                elif response.status == 413:
                    logger.error("❌ Trace.moe: الصورة كبيرة جداً")
                elif response.status == 429:
                    logger.error("❌ Trace.moe: تم تجاوز الحد المسموح")
                else:
                    text = await response.text()
                    logger.error(f"❌ Trace.moe Error: {response.status} - {text[:200]}")

    except asyncio.TimeoutError:
        logger.error("❌ Trace.moe: انتهت مهلة الطلب")
    except aiohttp.ClientError as e:
        logger.error(f"❌ Trace.moe Client Error: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ في Trace.moe: {e}")

    return None


async def trace_moe_search_with_retry(image_data: bytes) -> Optional[dict]:
    """
    محاولة البحث بصيغ مختلفة
    """
    # محاولة 1: PNG
    result = await trace_moe_search(image_data)
    if result and result.get("result"):
        return result

    # محاولة 2: JPEG
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_data))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85)
        jpeg_data = output.getvalue()

        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field('image', ('image.jpg', jpeg_data, 'image/jpeg'))

            async with session.post(
                "https://api.trace.moe/search",
                data=form,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    return await response.json()
    except ImportError:
        logger.warning("⚠️ PIL غير موجود - لا يمكن تحويل الصورة")
    except Exception as e:
        logger.error(f"❌ خطأ في تحويل الصورة: {e}")

    return result  # رجع النتيجة السابقة حتى لو فشلت

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
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "🎬")

def get_image(data: dict, type: str = "default") -> Optional[str]:
    if not data: return None
    images = data.get("images", {})
    if type == "thumbnail":
        return images.get("jpg", {}).get("image_url") or images.get("webp", {}).get("image_url")
    elif type == "banner":
        return data.get("trailer", {}).get("images", {}).get("maximum_image_url")
    return images.get("jpg", {}).get("image_url")

def get_char_image(char_data: dict) -> Optional[str]:
    if not char_data: return None
    images = char_data.get("images", {})
    return images.get("jpg", {}).get("image_url") or images.get("webp", {}).get("image_url")

def synopsis_full(data: dict, max_len: int = 400) -> str:
    syn = data.get("synopsis") or data.get("background") or "لا يوجد وصف."
    syn = syn.replace("[Written by MAL Rewrite]", "").strip()
    return (syn[:max_len] + "...") if len(syn) > max_len else syn

def rating_stars(score: float) -> str:
    return "⭐" * int(score // 2) if score else ""

def year_label(data: dict) -> str:
    aired = data.get("aired", {}).get("prop", {}).get("from", {})
    if year := aired.get("year"): return str(year)
    published = data.get("published", {}).get("prop", {}).get("from", {})
    if year := published.get("year"): return str(year)
    return "—"

def genres_text(data: dict, limit: int = 4) -> str:
    genres = [g["name"] for g in data.get("genres", [])][:limit]
    return ", ".join(genres) if genres else "—"

def genres_list(data: dict) -> List[str]:
    return [g["name"] for g in data.get("genres", [])]

def status_label(status: str) -> str:
    labels = {
        "Finished Airing": "✅ مكتمل", "Currently Airing": "🔄 يعرض حالياً",
        "Not yet aired": "⏳ لم يعرض بعد", "Publishing": "📖 يُنشر حالياً",
        "Finished": "✅ مكتمل", "On Hiatus": "⏸️ متوقف مؤقتاً"
    }
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
    h, m = int(seconds // 3600), int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def get_trailer_url(data: dict) -> Optional[str]:
    trailer = data.get("trailer", {})
    return trailer.get("url") or trailer.get("embed_url")

def get_url(data: dict) -> str:
    return data.get("url", "")

def get_watch_url(data: dict) -> Optional[str]:
    title = data.get("title", "").replace(" ", "+")
    return f"https://www.crunchyroll.com/search?q={title}"

def get_read_url(data: dict) -> Optional[str]:
    title = data.get("title", "").replace(" ", "+")
    return f"https://mangadex.org/search?q={title}"

def get_item_type(data: dict, category: str) -> str:
    if category == "anime": return data.get("type", "TV")
    return data.get("type", "Manga")

def get_total_chapters(data: dict) -> str:
    chapters = data.get("chapters")
    if chapters: return str(chapters)
    volumes = data.get("volumes")
    if volumes: return f"{volumes} مجلد"
    return "—"

def get_studios(data: dict) -> str:
    studios = [s["name"] for s in data.get("studios", [])][:1]
    return studios[0] if studios else "—"

def get_authors(data: dict) -> str:
    authors = [a["name"] for a in data.get("authors", [])][:2]
    return ", ".join(authors) if authors else "—"

def get_studios_or_authors(data: dict, category: str) -> str:
    return get_studios(data) if category == "anime" else get_authors(data)

# ═══════════════════════════════════════════════════════════════
# 📦 EMBED BUILDERS
# ═══════════════════════════════════════════════════════════════

def build_main_embed(item: dict, prefix: str = "", category: str = "anime") -> discord.Embed:
    title = item.get("title", "؟")
    title_jp = item.get("title_japanese", "")
    mal_id = item.get("mal_id", 0)
    source = get_studios_or_authors(item, category)
    desc = f"🇯🇵 *{title_jp}*\n\n{synopsis_full(item, 350)}" if title_jp else synopsis_full(item, 350)
    color = get_category_color(category)
    embed = discord.Embed(title=f"{prefix}{title}", description=desc, color=color, url=item.get("url"), timestamp=discord.utils.utcnow())

    if score := item.get("score"):
        embed.add_field(name="⭐ التقييم", value=f"**{score}/10** {rating_stars(score)}", inline=True)
    if category == "anime":
        if eps := item.get("episodes"):
            embed.add_field(name="📺 الحلقات", value=f"**{eps}**", inline=True)
    else:
        if chapters := get_total_chapters(item):
            embed.add_field(name="📖 الفصول", value=f"**{chapters}**", inline=True)

    embed.add_field(name="📅 السنة", value=f"**{year_label(item)}**", inline=True)
    embed.add_field(name=f"🏷️ {get_item_type(item, category)}", value=source, inline=True)
    embed.add_field(name="🎭 التصنيفات", value=genres_text(item, 4), inline=False)
    if status := item.get("status"):
        embed.add_field(name="🏷️ الحالة", value=status_label(status), inline=True)
    if thumb := get_image(item, "thumbnail"):
        embed.set_thumbnail(url=thumb)
    embed.set_footer(text=f"🌸 Uniq • {get_category_name(category)} | MAL ID: {mal_id}")
    return embed

def build_search_embed(query: str, results: List[dict], category: str = "anime") -> discord.Embed:
    item_type = "أنمي" if category == "anime" else "مادة"
    embed = discord.Embed(title=f"🔍 نتائج البحث: {query}", description=f"تم العثور على **{len(results)}** {item_type}\nاختر من القائمة 👇", color=get_category_color(category))

    for i, item in enumerate(results[:5]):
        score = f"⭐ **{item.get('score', '؟')}**" if item.get("score") else "✨ جديد"
        detail = f"📺 {item.get('episodes', '؟')} حلقة" if category == "anime" else f"📖 {get_total_chapters(item)} فصل"
        embed.add_field(name=f"{medal_emoji(i+1)} {i+1}. {item.get('title', '؟')}", value=f"{score} | {detail}", inline=False)

    if results and (thumb := get_image(results[0], "thumbnail")):
        embed.set_thumbnail(url=thumb)
    return embed

def build_top_embed(items: List[dict], category: str = "anime") -> discord.Embed:
    name = get_category_name(category)
    embed = discord.Embed(title=f"🏆 Top 10 {name}", description=f"أفضل {name} على MyAnimeList", color=get_category_color(category))
    for i, item in enumerate(items[:10]):
        embed.add_field(name=f"{medal_emoji(i+1)} #{i+1} {item.get('title', '؟')}", value=f"⭐ {item.get('score', '؟')}", inline=False)
    if items and (img := get_image(items[0], "banner")):
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
    embed = discord.Embed(title=f"🎭 {char.get('name', '؟')}", color=Theme.PURPLE, url=char.get("url"), timestamp=discord.utils.utcnow())
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

def build_news_embed_full(item: dict, category: str = "anime") -> discord.Embed:
    title = item.get("title", "؟")
    mal_id = item.get("mal_id", 0)
    source = get_studios_or_authors(item, category)
    description = synopsis_full(item, 400)
    extra_info = []
    if score := item.get("score"):
        extra_info.append(f"⭐ التقييم: **{score}/10**")
    if category == "anime":
        if eps := item.get("episodes"):
            extra_info.append(f"📺 الحلقات: **{eps}**")
    else:
        if chapters := get_total_chapters(item):
            extra_info.append(f"📖 الفصول: **{chapters}**")
    if year := year_label(item):
        if year != "—":
            extra_info.append(f"📅 السنة: **{year}**")
    extra_info.append(f"🏷️ النوع: **{get_item_type(item, category)}**")
    if source:
        extra_info.append(f"🎨 {source}")
    if extra_info:
        description += "\n\n" + "\n".join(extra_info)
    genres = genres_list(item)
    if genres:
        genre_text = " ".join([f"`{g}`" for g in genres[:5]])
        description += f"\n\n🎭 {genre_text}"

    embed = discord.Embed(title=f"{get_category_emoji(category)} خبر {get_category_name(category)} جديد!", description=description, color=get_category_color(category), url=item.get("url"), timestamp=discord.utils.utcnow())
    embed.add_field(name="🎬", value=f"**{title}**", inline=False)
    if status := item.get("status"):
        embed.add_field(name="🏷️ الحالة", value=status_label(status), inline=True)
    if thumb := get_image(item, "thumbnail"):
        embed.set_thumbnail(url=thumb)
    embed.set_footer(text=f"🌸 Uniq • MAL ID: {mal_id}")
    return embed

def build_recognition_embed(title: str, description: str, thumbnail: str = None, color: int = Theme.PURPLE, footer: str = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    embed.set_footer(text=footer or "🌸 Uniq • التعرف التلقائي")
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
    def __init__(self, results: List[dict], user_id: int, category: str = "anime"):
        super().__init__(timeout=300)
        self.results, self.user_id, self.category = results, user_id, category
        options = [discord.SelectOption(label=r.get("title", "؟")[:100], value=str(i), emoji=medal_emoji(i+1) if i < 3 else get_category_emoji(category)) for i, r in enumerate(results[:25])]
        select = discord.ui.Select(placeholder=f"🔍 اختر {get_category_name(category)}...", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        item = self.results[idx]
        await interaction.response.defer(ephemeral=True)
        mal_id = item.get("mal_id")
        if mal_id:
            if self.category == "anime":
                if full := await get_anime_details(mal_id): item = full
            else:
                if full := await get_manga_details(mal_id): item = full
        await interaction.followup.send(embed=build_main_embed(item, f"{get_category_emoji(self.category)} ", self.category), view=ItemActionsView(item, interaction.user.id, self.category), ephemeral=True)

class ItemActionsView(discord.ui.View):
    def __init__(self, item: dict, user_id: int, category: str):
        super().__init__(timeout=300)
        self.item, self.user_id, self.category = item, user_id, category
        if url := item.get("url"):
            self.add_item(discord.ui.Button(label="MyAnimeList", emoji="🌐", url=url, style=discord.ButtonStyle.link))
        watch_url = get_watch_url(item) if category == "anime" else get_read_url(item)
        if watch_url:
            self.add_item(discord.ui.Button(label="📖 قراءة/مشاهدة", emoji="▶️", url=watch_url, style=discord.ButtonStyle.link))

    @discord.ui.button(label="🎭 الشخصيات", style=discord.ButtonStyle.primary)
    async def characters_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.category != "anime":
            await interaction.response.send_message(embed=error_embed("الشخصيات متاحة للأنمي فقط."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        mal_id = self.item.get("mal_id")
        if mal_id:
            chars = await get_characters(mal_id)
            if chars:
                view = CharacterListView(self.item, chars, interaction.user.id)
                await interaction.followup.send(embed=view.build_page(), view=view, ephemeral=True)
                return
        await interaction.followup.send(embed=error_embed("لا توجد شخصيات."), ephemeral=True)

    @discord.ui.button(label="📋 التفاصيل", style=discord.ButtonStyle.secondary)
    async def details_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        mal_id = self.item.get("mal_id")
        if mal_id:
            full = await get_anime_details(mal_id) if self.category == "anime" else await get_manga_details(mal_id)
            if full:
                await interaction.followup.send(embed=build_main_embed(full, "📋 ", self.category), ephemeral=True)
                return
        await interaction.followup.send(embed=error_embed("خطأ في جلب التفاصيل."), ephemeral=True)

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

class NewsActionsView(discord.ui.View):
    def __init__(self, item: dict, channel_id: int, category: str):
        super().__init__(timeout=None)
        self.item, self.channel_id, self.category = item, channel_id, category
        watch_url = get_watch_url(item) if category == "anime" else get_read_url(item)
        btn_label = "▶️ مشاهدة" if category == "anime" else "📖 قراءة"
        if watch_url:
            self.add_item(discord.ui.Button(label=btn_label, emoji="▶️", url=watch_url, style=discord.ButtonStyle.link))
        mal_url = get_url(item)
        if mal_url:
            self.add_item(discord.ui.Button(label="🌐 التفاصيل", emoji="🌐", url=mal_url, style=discord.ButtonStyle.link))
        if category == "anime":
            trailer_url = get_trailer_url(item)
            if trailer_url:
                self.add_item(discord.ui.Button(label="🎬 الفيديو", emoji="🎬", url=trailer_url, style=discord.ButtonStyle.secondary))

# ═══════════════════════════════════════════════════════════════
# 🤖 BOT SETUP & EVENTS
# ═══════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    logger.info(f'✅ Logged in as {bot.user.name}')
    logger.info(f'📋 Recognition Channel: {db.recognition_channel_id}')
    logger.info(f'🔑 SauceNAO API Key: {" موجود" if len(SAUCENAO_API_KEY or "") > 10 else " غير موجود"}')
    await bot.tree.sync()
    bot.loop.create_task(news_broadcast_loop("anime"))
    bot.loop.create_task(news_broadcast_loop("manga"))
    bot.loop.create_task(news_broadcast_loop("manhwa"))

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
    """
    معالجة الصورة المرفقة - التعرف التلقائي
    """
    if not db.recognition_channel_id:
        return

    if message.channel.id != db.recognition_channel_id:
        return

    logger.info(f"🖼️ تم اكتشاف صورة في روم التعرف - من: {message.author.name}")

    try:
        # قراءة الصورة
        image_data = await attachment.read()
        image_size = len(image_data) / 1024
        logger.info(f"📊 حجم الصورة: {image_size:.2f} KB")

        # رسالة التحميل
        loading_msg = await message.reply(embed=loading_embed("🔍 جاري تحليل الصورة..."))

        # =========================================
        # البحث في SauceNAO أولاً (الشخصيات)
        # =========================================
        logger.info("🔍 البحث في SauceNAO...")
        saucenao_result = await saucenao_search(image_data)

        if saucenao_result and saucenao_result.get("results"):
            best = saucenao_result["results"][0]
            header = best.get("header", {})
            sim = float(header.get("similarity", 0))
            logger.info(f"📊 SauceNAO Similarity: {sim}%")

            if sim > 50:  # حد أدنى 50%
                data = best.get("data", {})
                char_name = data.get("character") or data.get("source") or data.get("creator") or "غير معروف"
                ext_urls = data.get("ext_urls", [])
                source_url = ext_urls[0] if ext_urls else "#"

                embed = build_recognition_embed(
                    title=f"🎭 تم التعرف على الشخصية!",
                    description=f"**{char_name}**\n\n📊 التشابه: **{sim:.2f}%**\n🔗 [المصدر]({source_url})",
                    thumbnail=header.get("thumbnail"),
                    color=Theme.PURPLE,
                    footer=f"🌸 Uniq • من: {message.author.name}"
                )

                if creator := data.get("creator"):
                    embed.add_field(name="🎨 الصانع", value=creator, inline=True)
                if source := data.get("source"):
                    embed.add_field(name="📺 المصدر", value=source, inline=True)

                await loading_msg.edit(embed=embed)
                logger.info(f"✅ تم التعرف على شخصية: {char_name}")
                return

        # =========================================
        # البحث في Trace.moe (الأنمي)
        # =========================================
        logger.info("🔍 البحث في Trace.moe...")
        trace_result = await trace_moe_search(image_data)

        if trace_result and trace_result.get("result") and len(trace_result["result"]) > 0:
            best = trace_result["result"][0]
            anilist = best.get("anilist", {})
            sim = best.get("similarity", 0)
            logger.info(f"📊 Trace.moe Similarity: {sim * 100:.2f}%")

            if sim > 0.4:  # حد أدنى 40%
                anime_title = anilist.get("title", {}).get("romaji", "؟")
                anime_title_native = anilist.get("title", {}).get("native")
                episode = best.get("episode")
                from_time = best.get("from", 0)
                image_url = best.get("image")
                mal_id = anilist.get("id")

                # جلب معلومات الأنمي الكاملة
                full_anime = None
                if mal_id and str(mal_id).isdigit():
                    full_anime = await get_anime_details(mal_id)

                embed = build_recognition_embed(
                    title=f"🎬 تم التعرف على الأنمي!",
                    description=f"**{anime_title}**" + (f"\n🇯🇵 {anime_title_native}" if anime_title_native else ""),
                    thumbnail=image_url,
                    color=Theme.ACCENT,
                    footer=f"🌸 Uniq • من: {message.author.name}"
                )

                embed.add_field(name="📺 الحلقة", value=f"**{episode or '؟'}**", inline=True)
                embed.add_field(name="⏱️ الوقت", value=f"**{format_timestamp(from_time)}**", inline=True)

                sim_percent = round(sim * 100, 2)
                indicator = "✅" if sim_percent > 85 else ("⚠️" if sim_percent > 70 else "❌")
                embed.add_field(name="📊 التشابه", value=f"**{sim_percent}%** {indicator}", inline=True)

                if full_anime:
                    if score := full_anime.get("score"):
                        embed.add_field(name="⭐ التقييم", value=f"**{score}/10**", inline=True)
                    if genres := genres_text(full_anime, 3):
                        embed.add_field(name="🎭 التصنيفات", value=genres, inline=False)

                if mal_id and str(mal_id).isdigit():
                    embed.add_field(name="🔗 رابط MAL", value=f"[MyAnimeList](https://myanimelist.net/anime/{mal_id})", inline=False)

                await loading_msg.edit(embed=embed)
                logger.info(f"✅ تم التعرف على أنمي: {anime_title}")
                return

        # =========================================
        # لم يتم التعرف
        # =========================================
        logger.warning("❌ لم يتم التعرف على أي نتيجة")

        error_msg = "❌ لم يتم التعرف على هذه الصورة.\n\n"
        error_msg += "💡 تأكد من:\n"
        error_msg += "• أن الصورة تحتوي على أنمي أو شخصية أنمي\n"
        error_msg += "• أن جودة الصورة جيدة\n"
        error_msg += "• أن صيغة الصورة مدعومة (PNG, JPG)"

        await loading_msg.edit(embed=error_embed(error_msg))

    except Exception as e:
        logger.error(f"❌ خطأ في process_auto_recognition: {e}")
        try:
            await loading_msg.edit(embed=error_embed(f"❌ حدث خطأ: {str(e)[:100]}"))
        except:
            pass

# ═══════════════════════════════════════════════════════════════
# 📰 NEWS BROADCAST LOOPS
# ═══════════════════════════════════════════════════════════════

async def get_news_items(category: str, limit: int = 5) -> List[dict]:
    if category == "anime":
        return await get_seasonal_anime(limit)
    elif category == "manga":
        return await get_top_manga(limit)
    elif category == "manhwa":
        return await get_top_manga(limit)
    return []

async def news_broadcast_loop(category: str):
    await bot.wait_until_ready()
    cat_name = get_category_name(category)
    logger.info(f"🔄 بدء Loop نشر أخبار {cat_name}")

    while not bot.is_closed():
        try:
            items = await get_news_items(category, 5)
            last_id = db.get_last_news_id(category)

            for item in items:
                mid = str(item.get("mal_id", ""))
                if mid and mid != last_id:
                    db.set_last_news_id(category, mid)
                    channels = db.get_news_channels(category)
                    for conf in channels:
                        if chan := bot.get_channel(conf.channel_id):
                            try:
                                embed = build_news_embed_full(item, category)
                                view = NewsActionsView(item, conf.channel_id, category)
                                await chan.send(embed=embed, view=view)
                                logger.info(f"📰 تم نشر خبر {cat_name}: {item.get('title')}")
                            except Exception as e:
                                logger.error(f"❌ خطأ في نشر الخبر: {e}")

            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"❌ خطأ في {cat_name} loop: {e}")
            await asyncio.sleep(60)

# ═══════════════════════════════════════════════════════════════
# 📊 SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="help", description="مساعدة وأوامر البوت")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🌸 Uniq v2.2 - المساعدة", description="أوامر البوت المتاحة:", color=Theme.CARD_BG)
    embed.add_field(name="🎬 الأنمي", value="`/anime` `/top` `/season` `/upcoming` `/airing` `/suggest`", inline=False)
    embed.add_field(name="📚 المانجا", value="`/manga` `/manga-top` `/manga-new`", inline=False)
    embed.add_field(name="📜 المانهوا", value="`/manhwa` `/manhwa-top`", inline=False)
    embed.add_field(name="🎭 الشخصيات", value="`/character`", inline=False)
    embed.add_field(name="🖼️ التعرف", value="`/setrecog` `/clearrecog` `/recog-status`", inline=False)
    embed.add_field(name="📰 الأخبار", value="`/activate-anime` `/activate-manga` `/activate-manhwa`\n`/deactivate` `/news-status`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# === Anime Commands ===
@bot.tree.command(name="anime", description="البحث عن أنمي")
async def anime_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    res = await search_anime(name)
    if res:
        await interaction.followup.send(embed=build_search_embed(name, res, "anime"), view=SearchDropdown(res, interaction.user.id, "anime"))
    else:
        await interaction.followup.send(embed=error_embed("لم يتم العثور على نتائج."))

@bot.tree.command(name="suggest", description="اقتراح أنمي عشوائي")
async def suggest_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    ani = await get_random_anime()
    if ani:
        await interaction.followup.send(embed=build_main_embed(ani, "🎲 ", "anime"), view=ItemActionsView(ani, interaction.user.id, "anime"))
    else:
        await interaction.followup.send(embed=error_embed("خطأ في جلب البيانات."))

@bot.tree.command(name="top", description="أفضل 10 أنمي")
async def top_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_top_anime()
    if res:
        await interaction.followup.send(embed=build_top_embed(res, "anime"))
    else:
        await interaction.followup.send(embed=error_embed("خطأ في جلب البيانات."))

@bot.tree.command(name="season", description="أنمي الموسم")
async def season_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_seasonal_anime()
    if res:
        embed = discord.Embed(title="🌸 أنمي الموسم", color=Theme.ACCENT)
        for i, a in enumerate(res[:10]):
            embed.add_field(name=f"{i+1}. {a.get('title')}", value=f"⭐ {a.get('score', '؟')}", inline=False)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="upcoming", description="أنميات قادمة")
async def upcoming_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_upcoming_anime()
    if res:
        embed = discord.Embed(title="⏳ أنميات قادمة", color=Theme.WARNING)
        for i, a in enumerate(res[:10]):
            embed.add_field(name=f"{i+1}. {a.get('title')}", value=f"📅 {a.get('aired', {}).get('string', 'قريباً')}", inline=False)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="airing", description="يعرض حالياً")
async def airing_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_airing_anime()
    if res:
        embed = discord.Embed(title="🔄 يعرض حالياً", color=Theme.INFO)
        for i, a in enumerate(res[:10]):
            embed.add_field(name=f"{i+1}. {a.get('title')}", value=f"⭐ {a.get('score', '؟')}", inline=False)
        await interaction.followup.send(embed=embed)

# === Manga Commands ===
@bot.tree.command(name="manga", description="البحث عن مانجا")
async def manga_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    res = await search_manga(name)
    if res:
        await interaction.followup.send(embed=build_search_embed(name, res, "manga"), view=SearchDropdown(res, interaction.user.id, "manga"))
    else:
        await interaction.followup.send(embed=error_embed("لم يتم العثور على نتائج."))

@bot.tree.command(name="manga-top", description="أفضل 10 مانجا")
async def manga_top_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_top_manga()
    if res:
        await interaction.followup.send(embed=build_top_embed(res, "manga"))
    else:
        await interaction.followup.send(embed=error_embed("خطأ في جلب البيانات."))

@bot.tree.command(name="manga-new", description="مانجا جديدة")
async def manga_new_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_publishing_manga()
    if res:
        embed = discord.Embed(title="📚 مانجا تُنشر حالياً", color=Theme.PURPLE)
        for i, m in enumerate(res[:10]):
            embed.add_field(name=f"{i+1}. {m.get('title')}", value=f"📖 {get_total_chapters(m)} | ⭐ {m.get('score', '؟')}", inline=False)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="manhwa", description="البحث عن مانهوا")
async def manhwa_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    res = await search_manga(name)
    if res:
        await interaction.followup.send(embed=build_search_embed(name, res, "manhwa"), view=SearchDropdown(res, interaction.user.id, "manhwa"))
    else:
        await interaction.followup.send(embed=error_embed("لم يتم العثور على نتائج."))

@bot.tree.command(name="manhwa-top", description="أفضل 10 مانهوا")
async def manhwa_top_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    res = await get_top_manga()
    if res:
        await interaction.followup.send(embed=build_top_embed(res, "manhwa"))
    else:
        await interaction.followup.send(embed=error_embed("خطأ في جلب البيانات."))

@bot.tree.command(name="character", description="البحث عن شخصية")
async def character_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    res = await search_character(name)
    if res:
        await interaction.followup.send(embed=build_character_search_embed(name, res), view=CharacterSearchDropdown(res, interaction.user.id))
    else:
        await interaction.followup.send(embed=error_embed("لم يتم العثور على نتائج."))

# === Recognition Commands ===
@bot.tree.command(name="setrecog", description="تفعيل روم التعرف التلقائي على الصور")
@app_commands.default_permissions(manage_channels=True)
async def setrecog_cmd(interaction: discord.Interaction):
    db.set_recognition_channel(interaction.channel_id)

    embed = success_embed("✅ تم تفعيل روم التعرف!", f"📍 الروم: {interaction.channel.mention}\n\n🖼️ أرسل صورة في هذا الروم وسأقوم بالتعرف عليها!\n\n🔍 البحث في:\n• SauceNAO (الشخصيات)\n• Trace.moe (الأنمي)")
    embed.add_field(name="💡 ملاحظات", value="• استخدم `/recog-status` لعرض الحالة\n• استخدم `/clearrecog` لإلغاء التفعيل", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="clearrecog", description="إيقاف التعرف التلقائي")
@app_commands.default_permissions(manage_channels=True)
async def clearrecog_cmd(interaction: discord.Interaction):
    db.clear_recognition_channel()
    await interaction.response.send_message(embed=success_embed("❌ تم إيقاف التعرف", "تم إيقاف روم التعرف التلقائي."), ephemeral=True)

@bot.tree.command(name="recog-status", description="عرض حالة نظام التعرف")
@app_commands.default_permissions(manage_channels=True)
async def recog_status_cmd(interaction: discord.Interaction):
    if db.recognition_channel_id:
        embed = success_embed("🖼️ حالة التعرف", f"✅ روم التعرف مفعّل!\n📍 الروم ID: `{db.recognition_channel_id}`\n\n💡 أرسل صورة في الروم المفعّل لبدء التعرف.")
    else:
        embed = info_embed("🖼️ حالة التعرف", "❌ روم التعرف غير مفعّل.\n\nاستخدم `/setrecog` في الروم الذي تريد تفعيله.", Theme.WARNING)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# === News Activation Commands ===
@bot.tree.command(name="activate-anime", description="تفعيل روم أخبار الأنمي")
@app_commands.default_permissions(manage_channels=True)
async def activate_anime_cmd(interaction: discord.Interaction):
    if db.is_channel_configured(interaction.channel_id, "anime"):
        await interaction.response.send_message(embed=info_embed("مفعّل مسبقاً", "هذا الروم مفعّل لأخبار الأنمي!", Theme.ACCENT), ephemeral=True)
        return
    db.add_news_channel(interaction.channel_id, "anime")
    embed = success_embed("✅ تم التفعيل", f"سيتم نشر أخبار الأنمي تلقائياً في هذا الروم!\n📰 الروم: {interaction.channel.mention}")
    embed.add_field(name="💡 أوامر الأخبار", value="`/deactivate` - إلغاء التفعيل\n`/news-status` - عرض الحالة", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="activate-manga", description="تفعيل روم أخبار المانجا")
@app_commands.default_permissions(manage_channels=True)
async def activate_manga_cmd(interaction: discord.Interaction):
    if db.is_channel_configured(interaction.channel_id, "manga"):
        await interaction.response.send_message(embed=info_embed("مفعّل مسبقاً", "هذا الروم مفعّل لأخبار المانجا!", Theme.PURPLE), ephemeral=True)
        return
    db.add_news_channel(interaction.channel_id, "manga")
    embed = success_embed("✅ تم التفعيل", f"سيتم نشر أخبار المانجا تلقائياً في هذا الروم!\n📰 الروم: {interaction.channel.mention}")
    embed.add_field(name="💡 أوامر الأخبار", value="`/deactivate` - إلغاء التفعيل\n`/news-status` - عرض الحالة", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="activate-manhwa", description="تفعيل روم أخبار المانهوا")
@app_commands.default_permissions(manage_channels=True)
async def activate_manhwa_cmd(interaction: discord.Interaction):
    if db.is_channel_configured(interaction.channel_id, "manhwa"):
        await interaction.response.send_message(embed=info_embed("مفعّل مسبقاً", "هذا الروم مفعّل لأخبار المانهوا!", Theme.INFO), ephemeral=True)
        return
    db.add_news_channel(interaction.channel_id, "manhwa")
    embed = success_embed("✅ تم التفعيل", f"سيتم نشر أخبار المانهوا تلقائياً في هذا الروم!\n📰 الروم: {interaction.channel.mention}")
    embed.add_field(name="💡 أوامر الأخبار", value="`/deactivate` - إلغاء التفعيل\n`/news-status` - عرض الحالة", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="deactivate", description="إلغاء تفعيل روم الأخبار")
@app_commands.describe(category="الفئة: anime, manga, manhwa, all")
@app_commands.default_permissions(manage_channels=True)
async def deactivate_cmd(interaction: discord.Interaction, category: str):
    categories = ["anime", "manga", "manhwa", "all"]
    if category not in categories:
        return await interaction.response.send_message(embed=error_embed("فئة غير صالحة. استخدم: anime, manga, manhwa, all"), ephemeral=True)

    removed = []
    for cat in ["anime", "manga", "manhwa"]:
        if category == "all" or category == cat:
            if db.is_channel_configured(interaction.channel_id, cat):
                db.remove_news_channel(interaction.channel_id, cat)
                removed.append(get_category_name(cat))

    if removed:
        await interaction.response.send_message(embed=success_embed("تم الإلغاء", f"تم إلغاء تفعيل: {', '.join(removed)}"), ephemeral=True)
    else:
        await interaction.response.send_message(embed=info_embed("غير مفعّل", "هذا الروم غير مفعّل لأي فئة!", Theme.WARNING), ephemeral=True)

@bot.tree.command(name="news-status", description="عرض حالة نظام الأخبار")
@app_commands.default_permissions(manage_channels=True)
async def news_status_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📰 حالة نظام الأخبار", color=Theme.CARD_BG)
    status_text = ""
    for cat in ["anime", "manga", "manhwa"]:
        channels = db.get_news_channels(cat)
        cat_emoji = get_category_emoji(cat)
        cat_name = get_category_name(cat)
        if channels:
            channel_list = "\n".join([f"<#{c.channel_id}>" for c in channels])
            status_text += f"\n\n{cat_emoji} **{cat_name}** ({len(channels)} روم):\n{channel_list}"
        else:
            status_text += f"\n\n{cat_emoji} **{cat_name}**: ❌ لا توجد رومات"
    embed.description = status_text if status_text else "❌ لا توجد رومات مفعّلة"
    embed.add_field(name="💡 طريقة التفعيل", value="1️⃣ اذهب للروم\n2️⃣ استخدم: `/activate-anime` أو `/activate-manga` أو `/activate-manhwa`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

if __name__ == "__main__":
    if TOKEN:
        logger.info("🚀 جاري تشغيل البوت...")
        bot.run(TOKEN)
    else:
        logger.error("❌ TOKEN NOT FOUND - أضف TOKEN في ملف .env")