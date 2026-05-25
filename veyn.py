"""
╔═══════════════════════════════════════════════════════════════╗
║     🌸  The Veyn — بوت الأنمي v5.4 (Redesigned)               ║
║  تصميم احترافي على شكل aiven's anime                          ║
╚═══════════════════════════════════════════════════════════════╝
"""

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Optional, List
import urllib.parse

load_dotenv()
TOKEN = os.getenv("TOKEN")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", "0"))

# ═══════════════════════════════════════════════════════════════
# 🌐 CONSUMET API (Gogoanime)
# ═══════════════════════════════════════════════════════════════

CONSUMET_BASE = "https://api.consumet.org"

async def consumet_request(endpoint: str, params: dict = None) -> Optional[dict]:
    url = f"{CONSUMET_BASE}{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    
    for _ in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        return await r.json()
                    elif r.status == 429:
                        await asyncio.sleep(2)
        except Exception:
            await asyncio.sleep(1)
    return None

async def gogo_search(query: str) -> List[dict]:
    data = await consumet_request("/anime/gogoanime/search", {"search": query})
    if not data:
        return []
    results = data.get("results", [])
    return [
        {
            "id": r.get("id", ""),
            "title": r.get("title", "؟"),
            "image": r.get("image", ""),
            "mal_id": r.get("malId", 0),
        }
        for r in results[:15]
    ]

async def gogo_info(anime_id: str) -> Optional[dict]:
    return await consumet_request(f"/anime/gogoanime/info/{anime_id}")

async def gogo_watch(episode_id: str) -> Optional[dict]:
    return await consumet_request(f"/anime/gogoanime/watch/{episode_id}")

# ═══════════════════════════════════════════════════════════════
# 🌐 JIKAN API (MyAnimeList)
# ═══════════════════════════════════════════════════════════════

JIKAN_BASE = "https://api.jikan.moe/v4"
_rate_limiter = asyncio.Semaphore(1)
_jikan_cache = {}

async def jikan_request(endpoint: str, use_cache: bool = True) -> Optional[dict]:
    global _jikan_cache
    
    if use_cache and endpoint in _jikan_cache:
        cached_data, cached_time = _jikan_cache[endpoint]
        if datetime.now().timestamp() - cached_time < 60:
            return cached_data
    
    url = f"{JIKAN_BASE}{endpoint}"
    
    async with _rate_limiter:
        await asyncio.sleep(0.4)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.json()
                        _jikan_cache[endpoint] = (data, datetime.now().timestamp())
                        if len(_jikan_cache) > 100:
                            keys = list(_jikan_cache.keys())[:20]
                            for k in keys:
                                del _jikan_cache[k]
                        return data
        except Exception:
            pass
    return None

async def search_jikan(query: str, limit: int = 15) -> List[dict]:
    data = await jikan_request(f"/anime?q={urllib.parse.quote(query)}&limit={limit}&sfw=true")
    return data.get("data", []) if data else []

async def anime_detail(mal_id: int) -> Optional[dict]:
    data = await jikan_request(f"/anime/{mal_id}/full")
    return data.get("data") if data else None

async def random_anime() -> Optional[dict]:
    data = await jikan_request("/random/anime", use_cache=False)
    return data.get("data") if data else None

async def top_anime(limit: int = 10) -> List[dict]:
    data = await jikan_request(f"/top/anime?limit={limit}")
    return data.get("data", []) if data else []

async def seasonal_anime(limit: int = 10) -> List[dict]:
    data = await jikan_request(f"/seasons/now?limit={limit}")
    return data.get("data", []) if data else []

async def upcoming_anime(limit: int = 10) -> List[dict]:
    data = await jikan_request(f"/seasons/upcoming?limit={limit}")
    return data.get("data", []) if data else []

# ═══════════════════════════════════════════════════════════════
# 🎨 COLORS & THEME
# ═══════════════════════════════════════════════════════════════

class Theme:
    # ألوان البوت
    BACKGROUND = 0x1E1F22      # خلفية الديسكورد
    EMBED_BG = 0x2B2D31        # خلفية الإمبيد
    BORDER = 0x313338          # حدود الإمبيد
    TEXT_PRIMARY = 0xFFFFFF    # نص رئيسي
    TEXT_SECONDARY = 0xB5BAC1  # نص ثانوي
    
    # ألوان الحادث
    ACCENT = 0x5865F2          # أزرق ديسكورد
    SUCCESS = 0x23A559         # أخضر
    DANGER = 0xED4245          # أحمر
    WARNING = 0xFEE75C         # أصفر
    
    # ألوان التوثيق
    GENRE_COLOR = 0xFEE75C     # أصفر للتاج
    RATING_COLOR = 0xFEE75C    # أصفر للنجوم
    EPISODES_COLOR = 0x5865F2  # أزرق
    YEAR_COLOR = 0x5865F2      # أزرق
    STATUS_COLOR = 0xEB459E    # وردي
    
    GENRE_COLORS = {
        "Action": 0xED4245, "Adventure": 0xEE8707, "Comedy": 0xFEE75C,
        "Drama": 0x5865F2, "Fantasy": 0x9B59B6, "Horror": 0xC93C3C,
        "Mystery": 0x7B68EE, "Romance": 0xEB459E, "Sci-Fi": 0x00D5FF,
        "Slice of Life": 0xF59E0B, "Sports": 0x23A559, "Supernatural": 0x9B59B6,
        "Psychological": 0xC93C70, "Thriller": 0xB03C3C, "Mecha": 0x4B5563,
        "Music": 0xF472B6, "Isekai": 0x5865F2, "Harem": 0xFB7185,
        "Ecchi": 0xF43F5E, "Shounen": 0xFEE75C, "Shoujo": 0xF472B6,
        "Seinen": 0x64748B, "default": 0x5865F2,
    }

GENRE_AR = {
    "Action": "أكشن", "Adventure": "مغامرة", "Comedy": "كوميديا",
    "Drama": "دراما", "Fantasy": "فانتازيا", "Horror": "رعب",
    "Mystery": "غموض", "Romance": "رومانسي", "Sci-Fi": "خيال علمي",
    "Slice of Life": "حياة يومية", "Sports": "رياضة",
    "Supernatural": "خارق للطبيعة", "Thriller": "إثارة",
    "Mecha": "ميكا", "Music": "موسيقى", "Psychological": "نفسي",
    "Shounen": "شونن", "Shoujo": "شوجو", "Seinen": "سينن",
    "Isekai": "إيسيكاي", "Harem": "حريم", "Ecchi": "إيتشي",
}

SEASON_AR = {
    "winter": "❄️ شتاء", "spring": "🌸 ربيع",
    "summer": "☀️ صيف", "fall": "🍂 خريف"
}

STATUS_AR = {
    "Finished Airing": ("✅", "مكتمل"),
    "Currently Airing": ("🔴", "يعرض الآن"),
    "Not yet aired": ("⏳", "لم يعرض بعد"),
}

# ═══════════════════════════════════════════════════════════════
# 🎨 HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def get_color(anime: dict) -> int:
    genres = anime.get("genres", []) + anime.get("themes", [])
    for g in genres:
        c = Theme.GENRE_COLORS.get(g.get("name", ""))
        if c:
            return c
    return Theme.GENRE_COLORS["default"]

def get_thumbnail(anime: dict) -> Optional[str]:
    return anime.get("images", {}).get("jpg", {}).get("image_url")

def get_banner(anime: dict) -> Optional[str]:
    images = anime.get("images", {})
    jpg = images.get("jpg", {})
    webp = images.get("webp", {})
    return webp.get("large_image_url") or jpg.get("large_image_url") or jpg.get("image_url")

def genres_list(anime: dict, max_items: int = 4) -> str:
    genres = anime.get("genres", []) + anime.get("themes", [])
    names = [GENRE_AR.get(g.get("name", ""), g.get("name", "")) for g in genres[:max_items]]
    return " · ".join(names) if names else "—"

def score_text(score) -> str:
    if not score:
        return "غير مقيّم"
    return f"{score}"

def status_text(status: str) -> str:
    icon, txt = STATUS_AR.get(status, ("❓", status))
    return txt

def synopsis_text(anime: dict, limit: int = 350) -> str:
    s = anime.get("synopsis") or "لا يوجد وصف متاح."
    return (s[:limit].rsplit(" ", 1)[0] + "...") if len(s) > limit else s

def progress_bar(current: int, total: int) -> str:
    if total <= 0:
        return "⬜" * 10
    filled = int(min(current / total, 1.0) * 10)
    return "🟩" * filled + "⬜" * (10 - filled)

def medal(num: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(num, "⭐")

# ═══════════════════════════════════════════════════════════════
# 📦 EMBED BUILDERS - تصميم aiven's anime
# ═══════════════════════════════════════════════════════════════

def build_anime_embed(anime: dict, prefix: str = "") -> discord.Embed:
    """إنشاء إمبيد الأنمي بتصميم احترافي"""
    color = get_color(anime)
    title = anime.get("title", "؟")
    title_jp = anime.get("title_japanese", "")
    mal_id = anime.get("mal_id", 0)
    
    # الوصف مع النص الياباني
    desc_parts = []
    if title_jp:
        desc_parts.append(f"🇯🇵 *{title_jp}*")
    desc_parts.append("")
    desc_parts.append(synopsis_text(anime))
    
    # إنشاء الإمبيد بدون حدود جانبية
    embed = discord.Embed(
        title=f'{prefix}{title}',
        description="\n".join(desc_parts),
        color=Theme.EMBED_BG,  # لون الخلفية للـ embed
        url=anime.get("url"),
        timestamp=datetime.now(timezone.utc)
    )
    
    # إضافة التقييم كنص فقط بدون أيكون
    score = anime.get("score")
    if score:
        embed.add_field(
            name="⭐ التقييم",
            value=f"**{score}/10**",
            inline=True
        )
    
    # إضافة الحلقات
    episodes = anime.get("episodes")
    if episodes:
        embed.add_field(
            name="📺 الحلقات",
            value=f"**{episodes}**",
            inline=True
        )
    
    # إضافة السنة
    year = anime.get("year") or anime.get("aired", {}).get("prop", {}).get("year", None)
    if year:
        embed.add_field(
            name="📅 السنة",
            value=f"**{year}**",
            inline=True
        )
    
    # إضافة التصنيفات
    embed.add_field(
        name="🎭 التصنيفات",
        value=genres_list(anime, 5),
        inline=False
    )
    
    # إضافة الحالة
    status = anime.get("status", "")
    if status:
        embed.add_field(
            name="🏷️ الحالة",
            value=status_text(status),
            inline=True
        )
    
    # الاستوديو
    studios = [s["name"] for s in anime.get("studios", [])][:2]
    if studios:
        embed.add_field(
            name="🎥 الاستوديو",
            value=" · ".join(studios),
            inline=True
        )
    
    # الصورة المصغرة على اليمين
    if thumb := get_thumbnail(anime):
        embed.set_thumbnail(url=thumb)
    
    # الفوتر
    embed.set_footer(text=f"🌸 The Veyn  |  MAL ID: {mal_id}")
    
    return embed


def build_episode_embed(anime: dict, ep_num: int, total: int) -> discord.Embed:
    """إنشاء إمبيد الحلقة"""
    title = anime.get("title", "؟")
    
    embed = discord.Embed(
        title=f'▶️ "{title}"',
        description=f"🎬 **الحلقة {ep_num} من {total}**\n\n🌸 استمتع بالمشاهدة!",
        color=Theme.SUCCESS,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.add_field(name="📊 التقدم", value=f"{progress_bar(ep_num, total)} `{ep_num}/{total}`", inline=False)
    
    if thumb := get_thumbnail(anime):
        embed.set_thumbnail(url=thumb)
    
    embed.set_footer(text=f"🌸 The Veyn • {title}")
    return embed


def build_search_embed(query: str, results: List[dict]) -> discord.Embed:
    """إنشاء إمبيد نتائج البحث"""
    embed = discord.Embed(
        title=f"🔍 نتائج البحث: {query}",
        description=f"تم العثور على **{len(results)}** نتيجة\nاختر أنمي من القائمة 👇",
        color=Theme.EMBED_BG
    )
    
    for i, a in enumerate(results[:5]):
        score = f"⭐ **{a.get('score', '؟')}**" if a.get("score") else "✨ جديد"
        eps = f"📺 **{a.get('episodes', '؟')}** حلقة" if a.get("episodes") else "📺 ? حلقة"
        embed.add_field(
            name=f"{medal(i + 1)} {i + 1}. {a.get('title', '؟')}",
            value=f"{score} | {eps}",
            inline=False
        )
    
    if results and (thumb := get_thumbnail(results[0])):
        embed.set_thumbnail(url=thumb)
    
    embed.set_footer(text="🌸 The Veyn • اختر أنمي من القائمة")
    return embed


def build_top_embed(anime_list: List[dict]) -> discord.Embed:
    """إنشاء إمبيد أفضل 10"""
    embed = discord.Embed(
        title="🏆 Top 10 Anime",
        description="أفضل الأنميات على MyAnimeList",
        color=Theme.EMBED_BG
    )
    
    for i, a in enumerate(anime_list[:10]):
        score = f"⭐ **{a.get('score', '')}**" if a.get("score") else ""
        eps = f"📺 **{a.get('episodes')}** حلقة" if a.get("episodes") else ""
        embed.add_field(
            name=f"{medal(i + 1)} #{i + 1} {a.get('title', '؟')}",
            value=f"{score} {eps}",
            inline=False
        )
    
    if anime_list and (img := get_banner(anime_list[0])):
        embed.set_image(url=img)
    
    embed.set_footer(text="🌸 The Veyn • اختر أنمي للتفاصيل")
    return embed


def embed_loading(msg: str = "⏳ جاري التحميل...") -> discord.Embed:
    return discord.Embed(description=f"🌸 {msg}", color=Theme.EMBED_BG)

def embed_error(msg: str) -> discord.Embed:
    return discord.Embed(title="❌ خطأ", description=msg, color=Theme.DANGER).set_footer(text="🌸 The Veyn")

def embed_success(title: str, msg: str) -> discord.Embed:
    return discord.Embed(title=f"✅ {title}", description=msg, color=Theme.SUCCESS).set_footer(text="🌸 The Veyn")

# ═══════════════════════════════════════════════════════════════
# 🎛️ VIEWS - الأزرار والقوائم (تصميم aiven's)
# ═══════════════════════════════════════════════════════════════

class SearchDropdown(discord.ui.View):
    """قائمة نتائج البحث"""
    def __init__(self, results: List[dict], user_id: int):
        super().__init__(timeout=300)
        self.results = results
        self.user_id = user_id
        
        options = [
            discord.SelectOption(
                label=r.get("title", "؟")[:100],
                value=str(i),
                description=f"⭐ {r.get('score', '؟')} | 📺 {r.get('episodes', '؟')} حلقة",
                emoji=medal(i + 1) if i < 3 else "🎬"
            )
            for i, r in enumerate(results[:25])
        ]
        
        select = discord.ui.Select(
            placeholder="🔍 اختر أنمي من القائمة...",
            options=options
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        anime = self.results[idx]
        
        await interaction.response.defer(ephemeral=True)
        
        mal_id = anime.get("mal_id") or anime.get("malId", 0)
        if mal_id:
            full = await anime_detail(mal_id)
            if full:
                anime = full
        
        embed = build_anime_embed(anime, "🎬 ")
        view = AnimeActionsView(anime, interaction.user.id)
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class AnimeActionsView(discord.ui.View):
    """أزرار تفاصيل الأنمي - تصميم aiven's"""
    def __init__(self, anime: dict, user_id: int):
        super().__init__(timeout=300)
        self.anime = anime
        self.user_id = user_id
        self.gogo_id = None
        
        # زر رابط MAL
        if url := anime.get("url"):
            self.add_item(discord.ui.Button(
                label="MyAnimeList",
                emoji="🌐",
                url=url,
                style=discord.ButtonStyle.link,
                row=0
            ))
    
    @discord.ui.button(label="📋 الحلقات", style=discord.ButtonStyle.primary, row=1)
    async def episodes_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        title = self.anime.get("title", "")
        
        # البحث في Gogoanime
        gogo_results = await gogo_search(title)
        if not gogo_results:
            await interaction.followup.send(embed=embed_error("ما لقيت أنمي."), ephemeral=True)
            return
        
        self.gogo_id = gogo_results[0].get("id", "")
        gogo_data = await gogo_info(self.gogo_id)
        
        episodes = []
        if gogo_data:
            episodes = gogo_data.get("episodes", [])
        
        if not episodes:
            await interaction.followup.send(embed=embed_error("ما في حلقات."), ephemeral=True)
            return
        
        view = EpisodeListView(self.anime, episodes, interaction.user.id, self.gogo_id)
        embed = view.build_page()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="🔍 مشابه", style=discord.ButtonStyle.secondary, row=1)
    async def similar_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        genres = self.anime.get("genres", [])
        if not genres:
            await interaction.followup.send(embed=embed_error("ما أقدر أجد مشابه."), ephemeral=True)
            return
        
        genre_id = genres[0].get("mal_id")
        data = await jikan_request(f"/anime?genres={genre_id}&order_by=score&sort=desc&limit=6&sfw=true")
        results = data.get("data", []) if data else []
        results = [a for a in results if a.get("mal_id") != self.anime.get("mal_id")][:4]
        
        if not results:
            await interaction.followup.send(embed=embed_error("ما لقيت."), ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f'🔍 أنمي مشابه لـ {self.anime.get("title", "")}',
            color=Theme.EMBED_BG
        )
        for a in results:
            score = f"⭐ **{a.get('score')}" if a.get("score") else ""
            embed.add_field(name=a.get("title", "؟"), value=f"{genres_list(a, 2)}\n{score}", inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🎲 عشوائي", style=discord.ButtonStyle.secondary, row=2)
    async def random_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        anime = await random_anime()
        if not anime:
            await interaction.followup.send(embed=embed_error("فشل."), ephemeral=True)
            return
        
        embed = build_anime_embed(anime, "🎲 ")
        view = AnimeActionsView(anime, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class EpisodeListView(discord.ui.View):
    """عرض قائمة الحلقات"""
    PER_PAGE = 10
    
    def __init__(self, anime: dict, episodes: list, user_id: int, gogo_id: str):
        super().__init__(timeout=180)
        self.anime = anime
        self.episodes = episodes
        self.user_id = user_id
        self.gogo_id = gogo_id
        self.page = 0
        self.total_pages = max(0, (len(episodes) - 1) // self.PER_PAGE)
    
    def build_page(self) -> discord.Embed:
        start = self.page * self.PER_PAGE
        chunk = self.episodes[start:start + self.PER_PAGE]
        
        embed = discord.Embed(
            title=f'📋 "{self.anime.get("title", "؟")}"',
            description="اختر الحلقة للمشاهدة 👇",
            color=Theme.EMBED_BG,
        )
        
        for ep in chunk:
            num = ep.get("number", ep.get("episodeNumber", "?"))
            title = ep.get("title", f"الحلقة {num}")
            embed.add_field(name=f"🍚 الحلقة {num}", value=title[:60], inline=True)
        
        embed.set_footer(text=f"صفحة {self.page + 1}/{self.total_pages + 1} | 🌸 The Veyn")
        
        if thumb := get_thumbnail(self.anime):
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
    
    @discord.ui.button(label="✅ اختر حلقة", style=discord.ButtonStyle.success, row=1)
    async def select_ep(self, interaction: discord.Interaction, btn: discord.ui.Button):
        view = EpisodeSelectView(self.anime, self.episodes, self.user_id, self.gogo_id)
        await interaction.response.send_message(
            embed=discord.Embed(title="🎬 اختر الحلقة", description="اختر من القائمة 👇", color=Theme.EMBED_BG),
            view=view, ephemeral=True
        )


class EpisodeSelectView(discord.ui.View):
    """قائمة اختيار الحلقة"""
    def __init__(self, anime: dict, episodes: list, user_id: int, gogo_id: str):
        super().__init__(timeout=180)
        self.anime = anime
        self.episodes = episodes
        self.user_id = user_id
        self.gogo_id = gogo_id
        
        options = [
            discord.SelectOption(
                label=f"الحلقة {ep.get('number', ep.get('episodeNumber', '?'))}",
                value=str(ep.get("number", ep.get("episodeNumber", 0))),
                description=ep.get("title", "")[:80] or f"Episode {ep.get('number', '?')}",
                emoji="🍚"
            )
            for ep in episodes[:25]
        ]
        
        select = discord.ui.Select(placeholder="🎬 اختر حلقة للمشاهدة...", options=options)
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: discord.Interaction):
        ep_num = int(interaction.data["values"][0])
        
        # Find episode ID
        ep_id = None
        for ep in self.episodes:
            ep_num_str = str(ep.get("number", ep.get("episodeNumber", 0)))
            if ep_num_str == str(ep_num):
                ep_id = ep.get("id", ep.get("episodeId"))
                break
        
        embed = build_episode_embed(self.anime, ep_num, len(self.episodes))
        view = EpisodePlayerView(self.anime, ep_num, len(self.episodes), self.gogo_id, ep_id)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class EpisodePlayerView(discord.ui.View):
    """أزرار التحكم بالمشغل"""
    def __init__(self, anime: dict, current_ep: int, total: int, gogo_id: str, ep_id: str):
        super().__init__(timeout=300)
        self.anime = anime
        self.current_ep = current_ep
        self.total_ep = total
        self.gogo_id = gogo_id
        self.ep_id = ep_id
    
    def update_embed(self) -> discord.Embed:
        return build_episode_embed(self.anime, self.current_ep, self.total_ep)
    
    @discord.ui.button(emoji="◀️", label="السابق", style=discord.ButtonStyle.secondary, row=0)
    async def prev_ep(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.current_ep > 1:
            self.current_ep -= 1
        await interaction.response.edit_message(embed=self.update_embed(), view=self)
    
    @discord.ui.button(emoji="▶️", label="تشغيل", style=discord.ButtonStyle.success, row=0)
    async def play(self, interaction: discord.Interaction, btn: discord.ui.Button):
        title = self.anime.get("title", "؟")
        await interaction.response.defer(ephemeral=True)
        
        if not self.ep_id:
            await interaction.followup.send(embed=embed_error("ما لقيت رابط."), ephemeral=True)
            return
        
        stream_data = await gogo_watch(self.ep_id)
        if not stream_data:
            await interaction.followup.send(embed=embed_error("ما في رابط متاح."), ephemeral=True)
            return
        
        sources = stream_data.get("sources", [])
        if not sources:
            await interaction.followup.send(embed=embed_error("ما في مصدر."), ephemeral=True)
            return
        
        video_url = sources[0].get("url", "")
        
        link_view = discord.ui.View(timeout=60)
        link_view.add_item(discord.ui.Button(
            label="🎬 مشاهدة الآن",
            emoji="▶️",
            url=video_url,
            style=discord.ButtonStyle.link
        ))
        
        sub_msg = ""
        subtitles = stream_data.get("subtitles", [])
        for sub in subtitles:
            if "english" in sub.get("lang", "").lower():
                sub_msg = "\n\n🇬🇧 **ترجمة إنجليزية** متاحة"
                break
        
        await interaction.followup.send(
            embed=embed_success("✅ تم التحميل!", f'🎬 **{title}** — الحلقة {self.current_ep}\n\n📺 الرابط جاهز!\n⚠️ بعض الروابط تحتاج VPN{sub_msg}'),
            view=link_view, ephemeral=True
        )
    
    @discord.ui.button(emoji="▶️", label="التالي", style=discord.ButtonStyle.secondary, row=0)
    async def next_ep(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.current_ep < self.total_ep:
            self.current_ep += 1
        await interaction.response.edit_message(embed=self.update_embed(), view=self)
    
    @discord.ui.button(label="🔢 رقم الحلقة", style=discord.ButtonStyle.primary, row=1)
    async def pick_ep(self, interaction: discord.Interaction, btn: discord.ui.Button):
        view = EpisodeSelectView(self.anime, self.episodes, self.user_id, self.gogo_id)
        await interaction.response.send_message(
            embed=discord.Embed(title="🔢 اختر الحلقة", description="اختر من القائمة 👇", color=Theme.EMBED_BG),
            view=view, ephemeral=True
        )


class Top10View(discord.ui.View):
    """أزرار أفضل 10 أنمي"""
    def __init__(self, anime_list: list):
        super().__init__(timeout=300)
        self.anime_list = anime_list
        
        for i in range(min(10, len(anime_list))):
            btn = discord.ui.Button(
                label=f"#{i + 1}",
                emoji=medal(i + 1),
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
                full = await anime_detail(mal_id)
                if full:
                    anime = full
            
            embed = build_anime_embed(anime, f"{medal(idx + 1)} #{idx + 1} ")
            view = TopActionsView(anime)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        return callback


class TopActionsView(discord.ui.View):
    """أزرار أنمي من التوب"""
    def __init__(self, anime: dict):
        super().__init__(timeout=300)
        self.anime = anime
    
    @discord.ui.button(label="▶️ تشغيل", style=discord.ButtonStyle.success, row=0)
    async def play_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        title = self.anime.get("title", "؟")
        await interaction.response.defer(ephemeral=True)
        
        results = await gogo_search(title)
        if not results:
            await interaction.followup.send(embed=embed_error("ما لقيت."), ephemeral=True)
            return
        
        gogo_id = results[0].get("id", "")
        info = await gogo_info(gogo_id)
        
        if not info or not info.get("episodes"):
            await interaction.followup.send(embed=embed_error("ما في حلقات."), ephemeral=True)
            return
        
        first_ep = info["episodes"][0]
        ep_id = first_ep.get("id", first_ep.get("episodeId"))
        
        stream = await gogo_watch(ep_id)
        if not stream or not stream.get("sources"):
            await interaction.followup.send(embed=embed_error("ما في رابط."), ephemeral=True)
            return
        
        video_url = stream["sources"][0].get("url", "")
        
        view = discord.ui.View(timeout=60)
        view.add_item(discord.ui.Button(label="🎬 مشاهدة الآن", emoji="▶️", url=video_url, style=discord.ButtonStyle.link))
        
        await interaction.followup.send(
            embed=embed_success("✅ تم!", f'🎬 **{title}** — الحلقة 1'),
            view=view, ephemeral=True
        )
    
    @discord.ui.button(label="🔍 التفاصيل", style=discord.ButtonStyle.primary, row=0)
    async def details_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        embed = build_anime_embed(self.anime, "🔍 ")
        view = AnimeActionsView(self.anime, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# 🤖 BOT SETUP
# ═══════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="🌸 الأنمي | The Veyn v5.4")
    )
    print(f"✅ The Veyn v5.4 — {bot.user} — جاهز!")


# ═══════════════════════════════════════════════════════════════
# 📢 SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="anime", description="ابحث عن أنمي")
@app_commands.describe(name="اسم الأنمي")
async def anime_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    
    msg = await interaction.followup.send(embed=embed_loading(f"🔍 بدور عن **{name}**..."), ephemeral=True)
    
    results = await search_jikan(name)
    if not results:
        await msg.edit(embed=embed_error(f'ما لقيت أنمي باسم **{name}**'))
        return
    
    embed = build_search_embed(name, results)
    view = SearchDropdown(results, interaction.user.id)
    
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="suggest", description="اقتراح أنمي عشوائي")
async def suggest_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=embed_loading("🎲 جاري الاختيار..."), ephemeral=True)
    
    anime = await random_anime()
    if not anime:
        await msg.edit(embed=embed_error("حصل خطأ."))
        return
    
    embed = build_anime_embed(anime, "🎲 اقتراح: ")
    view = AnimeActionsView(anime, interaction.user.id)
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="top", description="أفضل 10 أنمي")
async def top_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=embed_loading("🏆 جاري التحميل..."), ephemeral=True)
    
    anime_list = await top_anime(10)
    if not anime_list:
        await msg.edit(embed=embed_error("فشل التحميل."))
        return
    
    embed = build_top_embed(anime_list)
    view = Top10View(anime_list)
    
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="season", description="أنمي الموسم الحالي")
async def season_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=embed_loading("🌸 جاري التحميل..."), ephemeral=True)
    
    anime_list = await seasonal_anime(8)
    if not anime_list:
        await msg.edit(embed=embed_error("فشل."))
        return
    
    now = datetime.now(timezone.utc)
    season_names = {1: "❄️ شتاء", 2: "❄️ شتاء", 3: "🌸 ربيع", 4: "🌸 ربيع", 5: "🌸 ربيع",
                    6: "☀️ صيف", 7: "☀️ صيف", 8: "☀️ صيف", 9: "🍂 خريف", 10: "🍂 خريف", 11: "🍂 خريف", 12: "❄️ شتاء"}
    
    embed = discord.Embed(
        title=f"🌸 أنمي موسم {season_names[now.month]} {now.year}",
        color=Theme.EMBED_BG
    )
    
    for a in anime_list:
        score = f"⭐ **{a.get('score')}**" if a.get("score") else "✨ جديد"
        embed.add_field(name=a.get("title", "؟"), value=f"{genres_list(a, 2)}\n{score}", inline=True)
    
    if anime_list and (img := get_banner(anime_list[0])):
        embed.set_image(url=img)
    
    embed.set_footer(text="🌸 The Veyn • أنمي الموسم الحالي")
    
    await msg.edit(embed=embed)


@bot.tree.command(name="upcoming", description="أنمي قادم")
async def upcoming_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=embed_loading("⏳ جاري..."), ephemeral=True)
    
    anime_list = await upcoming_anime(8)
    if not anime_list:
        await msg.edit(embed=embed_error("فشل."))
        return
    
    embed = discord.Embed(title="⏳ أنمي قادم قريباً", color=Theme.EMBED_BG)
    for a in anime_list:
        embed.add_field(name=a.get("title", "؟"), value=genres_list(a, 2), inline=True)
    
    if anime_list and (img := get_banner(anime_list[0])):
        embed.set_image(url=img)
    
    embed.set_footer(text="🌸 The Veyn • أنمي قادم")
    
    await msg.edit(embed=embed)


# ═══════════════════════════════════════════════════════════════
# 🚀 RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    bot.run(TOKEN)
