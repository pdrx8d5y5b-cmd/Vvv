
# I'll create the final clean bot code WITHOUT any file writing operations
# The user should just copy-paste this directly into their bot file

final_bot = '''
"""
╔═══════════════════════════════════════════════════════════════╗
║     🌸  The Veyn — بوت الأنمي v3.2 (Final Clean Edition)      ║
║  صور كبيرة · بطاقات فاخرة · 10 أزرار · إشعارات أسبوعية     ║
╚═══════════════════════════════════════════════════════════════╝
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Optional, List

load_dotenv()
TOKEN = os.getenv("TOKEN")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID"))

# ═══════════════════════════════════════════════════════════════
# 🎨  THEME
# ═══════════════════════════════════════════════════════════════

class Theme:
    PRIMARY   = 0xFF6B9D
    SECONDARY = 0x6C63FF
    ACCENT    = 0x00D4AA
    WARNING   = 0xFFD93D
    DANGER    = 0xFF4757
    SUCCESS   = 0x10B981
    
    GENRE_COLORS = {
        "Action": 0xFF4757, "Adventure": 0xF97316, "Comedy": 0xFFD93D,
        "Drama": 0x3B82F6, "Fantasy": 0x8B5CF6, "Horror": 0xDC2626,
        "Mystery": 0x6D28D9, "Romance": 0xEC4899, "Sci-Fi": 0x06B6D4,
        "Slice of Life": 0xF59E0B, "Sports": 0x10B981, "Supernatural": 0x7C3AED,
        "Psychological": 0xBE185D, "Thriller": 0x991B1B, "Mecha": 0x4B5563,
        "Music": 0xF472B6, "Isekai": 0x6366F1, "Harem": 0xFB7185,
        "Ecchi": 0xF43F5E, "Shounen": 0xFBBF24, "Shoujo": 0xF472B6,
        "Seinen": 0x64748B, "Historical": 0x92400E, "School": 0x3B82F6,
        "Magic": 0xA78BFA, "default": 0x6C63FF,
    }

# ═══════════════════════════════════════════════════════════════
# 🌐  TRANSLATIONS
# ═══════════════════════════════════════════════════════════════

STATUS_AR = {
    "Finished Airing": ("✅", "مكتمل"),
    "Currently Airing": ("🔴", "يعرض الآن"),
    "Not yet aired": ("⏳", "لم يعرض بعد"),
}

GENRE_AR = {
    "Action": "أكشن", "Adventure": "مغامرة", "Comedy": "كوميديا",
    "Drama": "دراما", "Fantasy": "فانتازيا", "Horror": "رعب",
    "Mystery": "غموض", "Romance": "رومانسي", "Sci-Fi": "خيال علمي",
    "Slice of Life": "حياة يومية", "Sports": "رياضة",
    "Supernatural": "خارق للطبيعة", "Thriller": "إثارة",
    "Mecha": "ميكا", "Music": "موسيقى", "Psychological": "نفسي",
    "Shounen": "شونن", "Shoujo": "شوجو", "Seinen": "سينن",
    "Historical": "تاريخي", "School": "مدرسية", "Magic": "سحر",
    "Isekai": "إيسيكاي", "Harem": "حريم", "Ecchi": "إيتشي",
    "Reincarnation": "تناسخ", "Military": "عسكري", "Demons": "شياطين",
    "Game": "ألعاب", "Martial Arts": "فنون قتالية", "Vampire": "مصاص دماء",
    "Parody": "ساخر", "Police": "شرطة", "Space": "فضاء",
    "Super Power": "قوى خارقة", "Kids": "أطفال", "Josei": "جوسي",
}

SEASON_AR = {
    "winter": "❄️ شتاء", "spring": "🌸 ربيع",
    "summer": "☀️ صيف", "fall": "🍂 خريف"
}

# ═══════════════════════════════════════════════════════════════
# 💾  DATABASE
# ═══════════════════════════════════════════════════════════════

DB_FILE = "watchlist.json"

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db(data: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(db: dict, user_id: int) -> dict:
    key = str(user_id)
    if key not in db:
        db[key] = {"watchlist": [], "watching": {}, "favorites": []}
    return db[key]

# ═══════════════════════════════════════════════════════════════
# 🌐  API
# ═══════════════════════════════════════════════════════════════

async def jikan_get(path: str) -> Optional[dict]:
    url = f"https://api.jikan.moe/v4{path}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if r.status != 200:
                return None
            return await r.json()

async def fetch_anime_search(query: str) -> Optional[dict]:
    data = await jikan_get(f"/anime?q={query}&limit=1&sfw=true")
    if not data:
        return None
    results = data.get("data", [])
    return results[0] if results else None

async def fetch_random() -> Optional[dict]:
    data = await jikan_get("/random/anime")
    return data.get("data") if data else None

async def fetch_top(limit: int = 10, type_: str = "", filter_: str = "") -> List[dict]:
    params = f"?limit={limit}"
    if type_:
        params += f"&type={type_}"
    if filter_:
        params += f"&filter={filter_}"
    data = await jikan_get(f"/top/anime{params}")
    return data.get("data", []) if data else []

async def fetch_seasonal(limit: int = 10) -> List[dict]:
    data = await jikan_get(f"/seasons/now?limit={limit}")
    return data.get("data", []) if data else []

async def fetch_upcoming(limit: int = 10) -> List[dict]:
    data = await jikan_get(f"/seasons/upcoming?limit={limit}")
    return data.get("data", []) if data else []

async def fetch_airing(limit: int = 10) -> List[dict]:
    data = await jikan_get(f"/schedules?limit={limit}")
    return data.get("data", []) if data else []

async def fetch_episodes(mal_id: int) -> List[dict]:
    data = await jikan_get(f"/anime/{mal_id}/episodes")
    return data.get("data", []) if data else []

async def fetch_by_genre(genre_id: int, limit: int = 5) -> List[dict]:
    data = await jikan_get(f"/anime?genres={genre_id}&order_by=score&sort=desc&limit={limit}&sfw=true")
    return data.get("data", []) if data else []

# ═══════════════════════════════════════════════════════════════
# 🎨  VISUAL UTILITIES
# ═══════════════════════════════════════════════════════════════

def get_color(anime: dict) -> int:
    genres = anime.get("genres", []) + anime.get("themes", [])
    for g in genres:
        c = Theme.GENRE_COLORS.get(g["name"])
        if c:
            return c
    return Theme.GENRE_COLORS["default"]

def genres_ar(anime: dict, max_items: int = 5) -> str:
    genres = anime.get("genres", []) + anime.get("themes", [])
    names = [GENRE_AR.get(g["name"], g["name"]) for g in genres[:max_items]]
    return " · ".join(names) if names else "—"

def score_bar(score) -> str:
    if not score:
        return "☆☆☆☆☆  `غير مقيّم`"
    filled = round(score / 2)
    bar = "★" * filled + "☆" * (5 - filled)
    return f"{bar}  `{score}/10`"

def status_fmt(status: str) -> str:
    icon, txt = STATUS_AR.get(status, ("❓", status))
    return f"{icon} {txt}"

# 🔥 IMAGE FUNCTIONS
def get_large_image(anime: dict) -> Optional[str]:
    """Get LARGE image for embed.set_image()"""
    images = anime.get("images", {})
    jpg = images.get("jpg", {})
    return jpg.get("large_image_url") or jpg.get("image_url")

def get_thumbnail(anime: dict) -> Optional[str]:
    """Get small image for embed.set_thumbnail()"""
    images = anime.get("images", {})
    jpg = images.get("jpg", {})
    return jpg.get("image_url")

def synopsis_short(anime: dict, limit: int = 300) -> str:
    s = anime.get("synopsis") or "لا يوجد وصف متاح."
    if len(s) > limit:
        return s[:limit].rsplit(" ", 1)[0] + "..."
    return s

def progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "⬜" * length
    pct = min(current / total, 1.0)
    filled = int(pct * length)
    return "🟩" * filled + "⬜" * (length - filled)

def medal_emoji(rank: int) -> str:
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    return medals.get(rank, "⭐")

# ═══════════════════════════════════════════════════════════════
# 📦  EMBED BUILDERS (WITH IMAGES)
# ═══════════════════════════════════════════════════════════════

def build_embed(anime: dict, prefix: str = "", color: Optional[int] = None) -> discord.Embed:
    """Build anime card with BIG IMAGE"""
    color = color or get_color(anime)
    
    title_en = anime.get("title") or "؟"
    title_jp = anime.get("title_japanese") or ""
    url = anime.get("url") or None
    
    episodes = anime.get("episodes") or "؟"
    year = anime.get("year") or "—"
    score = anime.get("score")
    status = anime.get("status", "")
    rank = anime.get("rank") or "—"
    studios = [s["name"] for s in anime.get("studios", [])]
    season = anime.get("season") or ""
    season_ar = SEASON_AR.get(season, season)
    
    desc_lines = []
    if title_jp:
        desc_lines.append(f"🇯🇵 *{title_jp}*")
    desc_lines.append("")
    desc_lines.append(f"📖 **القصة**")
    desc_lines.append(synopsis_short(anime))
    
    embed = discord.Embed(
        title=f"{prefix}{title_en}",
        description="\\n".join(desc_lines),
        color=color,
        url=url,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.add_field(name="🎭 التصنيفات", value=genres_ar(anime), inline=False)
    embed.add_field(name="⭐ التقييم", value=score_bar(score), inline=True)
    embed.add_field(name="📺 الحلقات", value=f"`{episodes}`", inline=True)
    embed.add_field(name="🏆 الترتيب", value=f"`#{rank}`", inline=True)
    embed.add_field(name="📅 السنة", value=f"{season_ar} `{year}`".strip(), inline=True)
    embed.add_field(name="🏷️ الحالة", value=status_fmt(status), inline=True)
    embed.add_field(name="🎥 الاستوديو", value=" · ".join(studios[:2]) if studios else "—", inline=True)
    
    duration = anime.get("duration")
    if duration:
        embed.add_field(name="⏱️ المدة", value=f"`{duration}`", inline=True)
    
    rating = anime.get("rating")
    if rating:
        embed.add_field(name="🔞 التصنيف العمري", value=f"`{rating}`", inline=True)
    
    # 🔥 BIG IMAGE
    large_img = get_large_image(anime)
    if large_img:
        embed.set_image(url=large_img)
    
    # Thumbnail
    thumb_img = get_thumbnail(anime)
    if thumb_img:
        embed.set_thumbnail(url=thumb_img)
    
    embed.set_footer(text=f"🌸 The Veyn • بوت الأنمي  |  MAL ID: {anime.get('mal_id', '؟')}")
    return embed


def build_weekly_embed(anime_list: List[dict]) -> discord.Embed:
    now = datetime.now(timezone.utc)
    season_names = {
        1: "❄️ شتاء", 2: "❄️ شتاء", 3: "🌸 ربيع", 4: "🌸 ربيع", 5: "🌸 ربيع",
        6: "☀️ صيف", 7: "☀️ صيف", 8: "☀️ صيف", 9: "🍂 خريف", 10: "🍂 خريف",
        11: "🍂 خريف", 12: "❄️ شتاء"
    }
    season_label = f"{season_names[now.month]} {now.year}"
    
    embed = discord.Embed(
        title="📢 أنمي الأسبوع — The Veyn",
        description=(
            f"🌸 **أبرز أنمي يعرض هذا الموسم**\\n"
            f"📅 {season_label}\\n"
            f"✨ *يتجدد تلقائياً كل أسبوع*"
        ),
        color=Theme.PRIMARY,
        timestamp=now,
    )
    
    for i, a in enumerate(anime_list[:5]):
        score = f"⭐ {a.get('score')}" if a.get("score") else "✨ جديد"
        genres = genres_ar(a, 3)
        status_icon = "🔴" if a.get("status") == "Currently Airing" else "⏳"
        embed.add_field(
            name=f"{status_icon} {a.get('title', '؟')}",
            value=f"{genres}\\n{score}",
            inline=False,
        )
    
    # First anime image as banner
    if anime_list:
        first_img = get_large_image(anime_list[0])
        if first_img:
            embed.set_image(url=first_img)
    
    embed.set_footer(text="🌸 The Veyn • يتجدد كل أسبوع • اضغط على الأزرار للتفاصيل")
    return embed


def build_top_embed(anime_list: List[dict], title: str = "🏆 Top 10") -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description="أفضل الأنميات حسب تقييم المستخدمين على MyAnimeList",
        color=Theme.WARNING,
    )
    
    for i, a in enumerate(anime_list[:10]):
        medal = medal_emoji(i + 1)
        score = f"⭐ {a.get('score')}" if a.get("score") else ""
        eps = f"📺 {a.get('episodes')} حلقة" if a.get("episodes") else ""
        embed.add_field(
            name=f"{medal} #{i+1} {a.get('title', '؟')}",
            value=f"{score}  {eps}",
            inline=False,
        )
    
    # Show #1 image
    if anime_list:
        img = get_large_image(anime_list[0])
        if img:
            embed.set_image(url=img)
    
    embed.set_footer(text="🌸 The Veyn • اختر من القائمة أدناه للتفاصيل")
    return embed


def err_embed(msg: str) -> discord.Embed:
    return discord.Embed(title="❌ خطأ", description=msg, color=Theme.DANGER).set_footer(text="🌸 The Veyn")

def loading_embed(msg: str = "⏳ جاري التحميل...") -> discord.Embed:
    return discord.Embed(description=f"🌸 {msg}", color=Theme.SECONDARY)

# ═══════════════════════════════════════════════════════════════
# 🎛️  VIEWS
# ═══════════════════════════════════════════════════════════════

class AnimeView(discord.ui.View):
    def __init__(self, anime: dict, user_id: int):
        super().__init__(timeout=300)
        self.anime = anime
        self.user_id = user_id
        
        if url := anime.get("url"):
            self.add_item(discord.ui.Button(
                label="MyAnimeList", emoji="🌐",
                url=url, style=discord.ButtonStyle.link, row=0
            ))
        if trailer := anime.get("trailer", {}).get("url"):
            self.add_item(discord.ui.Button(
                label="الترايلر", emoji="▶️",
                url=trailer, style=discord.ButtonStyle.link, row=0
            ))
    
    @discord.ui.button(label="📌 Watchlist", style=discord.ButtonStyle.success, row=1)
    async def add_watch(self, interaction: discord.Interaction, btn: discord.ui.Button):
        db = load_db()
        usr = get_user(db, interaction.user.id)
        mal = self.anime.get("mal_id")
        
        if any(a["mal_id"] == mal for a in usr["watchlist"]):
            await interaction.response.send_message(
                embed=err_embed("هذا الأنمي موجود بالفعل في قائمتك! 📋"),
                ephemeral=True
            )
            return
        
        usr["watchlist"].append({
            "mal_id": mal,
            "title": self.anime.get("title"),
            "episodes": self.anime.get("episodes") or 0,
            "watched": 0,
            "score": self.anime.get("score"),
            "image": get_thumbnail(self.anime),
        })
        save_db(db)
        
        e = discord.Embed(
            title="✅ تمت الإضافة!",
            description=f"**{self.anime.get('title')}** انضاف لـ Watchlist تاعتك. 🌸",
            color=Theme.SUCCESS
        )
        await interaction.response.send_message(embed=e, ephemeral=True)
    
    @discord.ui.button(label="📋 الحلقات", style=discord.ButtonStyle.primary, row=1)
    async def episodes_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        eps = await fetch_episodes(self.anime["mal_id"])
        if not eps:
            await interaction.followup.send(
                embed=err_embed("ما في بيانات حلقات متاحة لهذا الأنمي."),
                ephemeral=True
            )
            return
        
        view = EpisodesView(self.anime, eps, interaction.user.id)
        embed = view.build_page()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="🔍 مشابه", style=discord.ButtonStyle.secondary, row=1)
    async def similar_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        genres = self.anime.get("genres", [])
        if not genres:
            await interaction.followup.send(
                embed=err_embed("ما أقدر أجد أنمي مشابه."),
                ephemeral=True
            )
            return
        
        genre_id = genres[0]["mal_id"]
        results = await fetch_by_genre(genre_id, 5)
        results = [a for a in results if a["mal_id"] != self.anime["mal_id"]][:4]
        
        if not results:
            await interaction.followup.send(embed=err_embed("ما لقيت نتائج."), ephemeral=True)
            return
        
        e = discord.Embed(
            title=f"🔍 أنمي مشابه لـ {self.anime.get('title')}",
            color=get_color(self.anime)
        )
        for a in results:
            score = f"⭐ {a.get('score')}" if a.get("score") else "غير مقيّم"
            e.add_field(
                name=a.get("title", "؟"),
                value=f"{genres_ar(a)}\\n{score}",
                inline=True
            )
        await interaction.followup.send(embed=e, ephemeral=True)
    
    @discord.ui.button(label="🎲 عشوائي آخر", style=discord.ButtonStyle.secondary, row=2)
    async def random_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        anime = await fetch_random()
        if not anime:
            await interaction.followup.send(embed=err_embed("فشل التحميل."), ephemeral=True)
            return
        
        embed = build_embed(anime, "🎲 ")
        view = AnimeView(anime, interaction.user.id)
        await interaction.edit_original_response(embed=embed, view=view)
    
    @discord.ui.button(label="❤️ مفضل", style=discord.ButtonStyle.danger, row=2)
    async def favorite_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        db = load_db()
        usr = get_user(db, interaction.user.id)
        mal = self.anime.get("mal_id")
        
        if mal in usr.get("favorites", []):
            usr["favorites"].remove(mal)
            save_db(db)
            await interaction.response.send_message(
                embed=discord.Embed(title="❌ تم الإزالة", description="تم إزالة الأنمي من المفضلة", color=Theme.DANGER),
                ephemeral=True
            )
        else:
            usr.setdefault("favorites", []).append(mal)
            save_db(db)
            await interaction.response.send_message(
                embed=discord.Embed(title="❤️ تمت الإضافة!", description="أضيف الأنمي للمفضلة", color=Theme.PRIMARY),
                ephemeral=True
            )


class EpisodesView(discord.ui.View):
    PER_PAGE = 10
    
    def __init__(self, anime: dict, eps: list, user_id: int):
        super().__init__(timeout=180)
        self.anime = anime
        self.eps = eps
        self.user_id = user_id
        self.page = 0
        self.total_pages = (len(eps) - 1) // self.PER_PAGE
    
    def build_page(self) -> discord.Embed:
        start = self.page * self.PER_PAGE
        chunk = self.eps[start:start + self.PER_PAGE]
        
        db = load_db()
        usr = get_user(db, self.user_id)
        watched_num = usr.get("watching", {}).get(str(self.anime["mal_id"]), 0)
        
        color = get_color(self.anime)
        embed = discord.Embed(
            title=f"📋 حلقات {self.anime.get('title', '؟')}",
            description=f"شاهدت: **{watched_num}** / {len(self.eps)} حلقة\\n{progress_bar(watched_num, len(self.eps))}",
            color=color,
        )
        
        for ep in chunk:
            num = ep.get("mal_id") or "؟"
            title = ep.get("title") or f"الحلقة {num}"
            aired = ep.get("aired") or "—"
            icon = "✅" if isinstance(num, int) and num <= watched_num else "⬜"
            embed.add_field(
                name=f"{icon} الحلقة {num}",
                value=f"{title}\\n📅 {aired}",
                inline=True,
            )
        
        embed.set_footer(text=f"صفحة {self.page+1}/{self.total_pages+1} | 🌸 The Veyn")
        
        if img := get_thumbnail(self.anime):
            embed.set_thumbnail(url=img)
        
        return embed
    
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)
    
    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page < self.total_pages:
            self.page += 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)
    
    @discord.ui.button(label="✅ سجّل حلقة", style=discord.ButtonStyle.success, row=1)
    async def mark_ep(self, interaction: discord.Interaction, btn: discord.ui.Button):
        db = load_db()
        usr = get_user(db, interaction.user.id)
        mid = str(self.anime["mal_id"])
        cur = usr.get("watching", {}).get(mid, 0)
        total_eps = len(self.eps)
        
        if cur >= total_eps:
            await interaction.response.send_message(
                embed=err_embed("شاهدت كل الحلقات بالفعل! 🎉"),
                ephemeral=True
            )
            return
        
        usr.setdefault("watching", {})[mid] = cur + 1
        save_db(db)
        
        remaining = total_eps - cur - 1
        e = discord.Embed(
            title="✅ تم التسجيل!",
            description=f"سجّلت الحلقة **{cur+1}** من **{self.anime.get('title')}**.\\nالمتبقي: {remaining} حلقة",
            color=Theme.SUCCESS
        )
        await interaction.response.send_message(embed=e, ephemeral=True)
        await interaction.message.edit(embed=self.build_page(), view=self)


class WatchlistView(discord.ui.View):
    PER_PAGE = 5
    
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.page = 0
    
    def get_data(self):
        db = load_db()
        usr = get_user(db, self.user_id)
        return usr.get("watchlist", []), usr.get("watching", {})
    
    def build_embed(self) -> discord.Embed:
        wl, watching = self.get_data()
        if not wl:
            return discord.Embed(
                title="📋 Watchlist فارغة",
                description=(
                    "ما أضفت أي أنمي بعد!\\n\\n"
                    "🌸 **كيف تضيف أنمي؟**\\n"
                    "استخدم الزر 📌 في بطاقة الأنمي لإضافته."
                ),
                color=Theme.SECONDARY,
            )
        
        total = len(wl)
        chunk = wl[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]
        total_pages = (total - 1) // self.PER_PAGE
        
        embed = discord.Embed(
            title="📋 Watchlist تاعتك",
            description=f"عندك **{total}** أنمي  |  صفحة {self.page+1}/{total_pages+1}",
            color=Theme.SECONDARY,
        )
        
        for a in chunk:
            mid = str(a.get("mal_id", ""))
            watched = watching.get(mid, 0)
            total_ep = a.get("episodes") or "؟"
            score = f"⭐ {a['score']}" if a.get("score") else ""
            progress = f"{watched}/{total_ep}"
            bar = progress_bar(watched, total_ep if isinstance(total_ep, int) else 0)
            
            embed.add_field(
                name=a.get("title", "؟"),
                value=f"{bar}\\n`{progress}` حلقة  {score}",
                inline=False,
            )
        
        if chunk and chunk[0].get("image"):
            embed.set_thumbnail(url=chunk[0]["image"])
        
        embed.set_footer(text="🌸 The Veyn • بوت الأنمي")
        return embed
    
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_p(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
    
    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def next_p(self, interaction: discord.Interaction, btn: discord.ui.Button):
        wl, _ = self.get_data()
        total_pages = (len(wl) - 1) // self.PER_PAGE
        if self.page < total_pages:
            self.page += 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
    
    @discord.ui.button(label="🗑️ مسح أنمي", style=discord.ButtonStyle.danger, row=1)
    async def remove_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        wl, _ = self.get_data()
        if not wl:
            await interaction.response.send_message(
                embed=err_embed("القائمة فارغة."), ephemeral=True
            )
            return
        view = RemoveSelect(self.user_id, wl[:25])
        await interaction.response.send_message(
            embed=discord.Embed(title="🗑️ اختر الأنمي اللي تبي تمسحه", color=Theme.DANGER),
            view=view, ephemeral=True
        )


class RemoveSelect(discord.ui.View):
    def __init__(self, user_id: int, watchlist: list):
        super().__init__(timeout=120)
        self.user_id = user_id
        options = [
            discord.SelectOption(label=a["title"][:100], value=str(a["mal_id"]), emoji="🗑️")
            for a in watchlist
        ]
        select = discord.ui.Select(placeholder="اختر أنمي...", options=options)
        select.callback = self.do_remove
        self.add_item(select)
    
    async def do_remove(self, interaction: discord.Interaction):
        mal_id = int(interaction.data["values"][0])
        db = load_db()
        usr = get_user(db, self.user_id)
        before = len(usr["watchlist"])
        usr["watchlist"] = [a for a in usr["watchlist"] if a["mal_id"] != mal_id]
        usr.get("watching", {}).pop(str(mal_id), None)
        save_db(db)
        removed = before - len(usr["watchlist"])
        
        e = discord.Embed(
            title="🗑️ تم الحذف" if removed else "❌ ما وجدناه",
            color=Theme.DANGER
        )
        await interaction.response.edit_message(embed=e, view=None)


class TopAnimeView(discord.ui.View):
    def __init__(self, anime_list: list):
        super().__init__(timeout=300)
        self.anime_list = anime_list
        
        options = [
            discord.SelectOption(
                label=f"#{i+1} {a['title'][:80]}",
                value=str(i),
                emoji=medal_emoji(i + 1)
            )
            for i, a in enumerate(anime_list[:10])
        ]
        select = discord.ui.Select(placeholder="🔍 اختر أنمي للتفاصيل...", options=options)
        select.callback = self.show_detail
        self.add_item(select)
    
    async def show_detail(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        anime = self.anime_list[idx]
        prefix = f"{medal_emoji(idx + 1)} #{idx+1} "
        embed = build_embed(anime, prefix)
        view = AnimeView(anime, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# 🎯  MAIN MENU (10 BUTTONS)
# ═══════════════════════════════════════════════════════════════

class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(emoji="🏆", label="الأفضل", style=discord.ButtonStyle.primary, row=0)
    async def top_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=loading_embed("جاري تحميل الأفضل..."), ephemeral=True)
        anime_list = await fetch_top(10)
        if not anime_list:
            await msg.edit(embed=err_embed("فشل تحميل القائمة."))
            return
        
        embed = build_top_embed(anime_list)
        view = TopAnimeView(anime_list)
        await msg.edit(embed=embed, view=view)
    
    @discord.ui.button(emoji="🌸", label="الموسم", style=discord.ButtonStyle.success, row=0)
    async def season_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=loading_embed("جاري تحميل موسم الأنمي..."), ephemeral=True)
        anime_list = await fetch_seasonal(10)
        if not anime_list:
            await msg.edit(embed=err_embed("فشل التحميل."))
            return
        
        now = datetime.now(timezone.utc)
        embed = discord.Embed(
            title=f"🌸 أنمي الموسم — {now.year}",
            color=Theme.PRIMARY,
        )
        for a in anime_list[:8]:
            score = f"⭐ {a.get('score')}" if a.get("score") else "✨ جديد"
            embed.add_field(
                name=a.get("title", "؟"),
                value=f"{genres_ar(a, 3)}\\n{score}",
                inline=True,
            )
        
        if anime_list and (img := get_large_image(anime_list[0])):
            embed.set_image(url=img)
        
        view = SeasonSelectView(anime_list[:8])
        await msg.edit(embed=embed, view=view)
    
    @discord.ui.button(emoji="📡", label="يعرض الآن", style=discord.ButtonStyle.danger, row=0)
    async def airing_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=loading_embed("جاري تحميل..."), ephemeral=True)
        anime_list = await fetch_airing(10)
        if not anime_list:
            await msg.edit(embed=err_embed("فشل التحميل."))
            return
        
        embed = discord.Embed(title="📡 يعرض الآن", color=Theme.DANGER)
        for a in anime_list[:8]:
            score = f"⭐ {a.get('score')}" if a.get("score") else ""
            embed.add_field(name=a.get("title", "؟"), value=f"{genres_ar(a, 2)}\\n{score}", inline=True)
        
        if anime_list and (img := get_large_image(anime_list[0])):
            embed.set_image(url=img)
        
        await msg.edit(embed=embed)
    
    @discord.ui.button(emoji="⏳", label="قادم", style=discord.ButtonStyle.secondary, row=0)
    async def upcoming_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=loading_embed("جاري تحميل..."), ephemeral=True)
        anime_list = await fetch_upcoming(10)
        if not anime_list:
            await msg.edit(embed=err_embed("فشل التحميل."))
            return
        
        embed = discord.Embed(title="⏳ قادم قريباً", color=Theme.SECONDARY)
        for a in anime_list[:8]:
            embed.add_field(name=a.get("title", "؟"), value=genres_ar(a, 2), inline=True)
        
        if anime_list and (img := get_large_image(anime_list[0])):
            embed.set_image(url=img)
        
        await msg.edit(embed=embed)
    
    @discord.ui.button(emoji="🔥", label="شعبي", style=discord.ButtonStyle.primary, row=1)
    async def popular_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=loading_embed("جاري تحميل..."), ephemeral=True)
        anime_list = await fetch_top(10, filter_="bypopularity")
        if not anime_list:
            await msg.edit(embed=err_embed("فشل التحميل."))
            return
        
        embed = discord.Embed(title="🔥 الأكثر شعبية", color=0xFF6B35)
        for i, a in enumerate(anime_list[:8]):
            embed.add_field(name=f"#{i+1} {a.get('title', '؟')}", value=f"⭐ {a.get('score', '؟')}", inline=True)
        
        if anime_list and (img := get_large_image(anime_list[0])):
            embed.set_image(url=img)
        
        await msg.edit(embed=embed)
    
    @discord.ui.button(emoji="🎬", label="أفلام", style=discord.ButtonStyle.success, row=1)
    async def movie_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=loading_embed("جاري تحميل..."), ephemeral=True)
        anime_list = await fetch_top(10, type_="movie")
        if not anime_list:
            await msg.edit(embed=err_embed("فشل التحميل."))
            return
        
        embed = discord.Embed(title="🎬 أفلام أنمي", color=0xFFD700)
        for a in anime_list[:8]:
            embed.add_field(name=a.get("title", "؟"), value=f"⭐ {a.get('score', '؟')}", inline=True)
        
        if anime_list and (img := get_large_image(anime_list[0])):
            embed.set_image(url=img)
        
        await msg.edit(embed=embed)
    
    @discord.ui.button(emoji="📀", label="OVA", style=discord.ButtonStyle.secondary, row=1)
    async def ova_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=loading_embed("جاري تحميل..."), ephemeral=True)
        anime_list = await fetch_top(10, type_="ova")
        if not anime_list:
            await msg.edit(embed=err_embed("فشل التحميل."))
            return
        
        embed = discord.Embed(title="📀 حلقات OVA خاصة", color=0xC0C0C0)
        for a in anime_list[:8]:
            embed.add_field(name=a.get("title", "؟"), value=f"⭐ {a.get('score', '؟')}", inline=True)
        
        if anime_list and (img := get_large_image(anime_list[0])):
            embed.set_image(url=img)
        
        await msg.edit(embed=embed)
    
    @discord.ui.button(emoji="🎲", label="عشوائي", style=discord.ButtonStyle.primary, row=2)
    async def random_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=loading_embed("🎲 جاري الاختيار العشوائي..."), ephemeral=True)
        anime = await fetch_random()
        if not anime:
            await msg.edit(embed=err_embed("حصل خطأ، حاول مرة أخرى."))
            return
        
        embed = build_embed(anime, "🎲 اقتراح: ")
        view = AnimeView(anime, interaction.user.id)
        await msg.edit(embed=embed, view=view)
    
    @discord.ui.button(emoji="🔍", label="بحث", style=discord.ButtonStyle.secondary, row=2)
    async def search_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔍 بحث عن أنمي",
                description="استخدم الأمر `/anime <اسم>` للبحث",
                color=Theme.SECONDARY
            ),
            ephemeral=True
        )
    
    @discord.ui.button(emoji="📋", label="قائمتي", style=discord.ButtonStyle.success, row=2)
    async def watchlist_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        view = WatchlistView(interaction.user.id)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class SeasonSelectView(discord.ui.View):
    def __init__(self, anime_list: list):
        super().__init__(timeout=180)
        self.anime_list = anime_list
        
        options = [
            discord.SelectOption(label=a["title"][:100], value=str(i), emoji="🌸")
            for i, a in enumerate(anime_list)
        ]
        select = discord.ui.Select(placeholder="اختر أنمي للتفاصيل...", options=options)
        select.callback = self.show
        self.add_item(select)
    
    async def show(self, inter: discord.Interaction):
        idx = int(inter.data["values"][0])
        anime = self.anime_list[idx]
        embed = build_embed(anime, "🌸 ")
        view = AnimeView(anime, inter.user.id)
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# 🤖  BOT SETUP
# ═══════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="🌸 الأنمي | The Veyn v3.2"
        )
    )
    weekly_notify.start()
    print(f"✅ The Veyn Bot v3.2 — {bot.user} — جاهز!")

# ═══════════════════════════════════════════════════════════════
# 📢  SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="menu", description="افتح القائمة الرئيسية للبوت")
async def menu_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌸 The Veyn — مركز الأنمي",
        description=(
            "**مرحباً بك في عالم الأنمي!** 🎌\\n\\n"
            "استخدم الأزرار أدناه لاستكشاف:\\n"
            "• 🏆 الأنميات الأفضل تقييماً\\n"
            "• 🌸 أنمي الموسم الحالي\\n"
            "• 📡 ما يعرض الآن\\n"
            "• ⏳ القادم قريباً\\n"
            "• 🔥 الأكثر شعبية\\n"
            "• 🎬 أفلام الأنمي\\n"
            "• 📀 حلقات OVA\\n"
            "• 🎲 اقتراح عشوائي\\n"
            "• 🔍 بحث متقدم\\n"
            "• 📋 قائمة مشاهدتك\\n\\n"
            "✨ *يتم التحديث أسبوعياً*"
        ),
        color=Theme.PRIMARY,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="🌸 The Veyn v3.2 • بوت الأنمي العربي")
    
    view = MainMenuView()
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="anime", description="ابحث عن أنمي")
@app_commands.describe(name="اسم الأنمي (عربي أو إنجليزي)")
async def anime_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    msg = await interaction.followup.send(embed=loading_embed(f"🔍 بدور عن **{name}**..."))
    
    anime = await fetch_anime_search(name)
    if not anime:
        await msg.edit(embed=err_embed(
            f"ما لقيت أنمي باسم **{name}**.\\nتأكد من الاسم أو جرب اسم مختلف."
        ))
        return
    
    embed = build_embed(anime, "🔍 ")
    view = AnimeView(anime, interaction.user.id)
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="suggest", description="احصل على اقتراح أنمي عشوائي")
async def suggest_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    msg = await interaction.followup.send(embed=loading_embed("🎲 جاري الاختيار العشوائي..."))
    
    anime = await fetch_random()
    if not anime:
        await msg.edit(embed=err_embed("حصل خطأ، حاول مرة أخرى."))
        return
    
    embed = build_embed(anime, "🎲 اقتراح: ")
    view = AnimeView(anime, interaction.user.id)
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="top", description="أفضل 10 أنمي على MyAnimeList")
async def top_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    msg = await interaction.followup.send(embed=loading_embed("🏆 جاري تحميل الترتيب..."))
    
    anime_list = await fetch_top(10)
    if not anime_list:
        await msg.edit(embed=err_embed("فشل تحميل القائمة."))
        return
    
    embed = build_top_embed(anime_list)
    view = TopAnimeView(anime_list)
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="watchlist", description="شوف أو دير Watchlist تاعتك")
async def watchlist_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    view = WatchlistView(interaction.user.id)
    embed = view.build_embed()
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="season", description="أنمي الموسم الحالي")
async def season_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    msg = await interaction.followup.send(embed=loading_embed("🌸 جاري تحميل أنمي الموسم..."))
    
    anime_list = await fetch_seasonal(10)
    if not anime_list:
        await msg.edit(embed=err_embed("فشل تحميل أنمي الموسم."))
        return
    
    now = datetime.now(timezone.utc)
    season_names = {
        1: "❄️ شتاء", 2: "❄️ شتاء", 3: "🌸 ربيع", 4: "🌸 ربيع", 5: "🌸 ربيع",
        6: "☀️ صيف", 7: "☀️ صيف", 8: "☀️ صيف", 9: "🍂 خريف", 10: "🍂 خريف",
        11: "🍂 خريف", 12: "❄️ شتاء"
    }
    season_label = f"🌸 أنمي موسم {season_names[now.month]} {now.year}"
    
    embed = discord.Embed(title=season_label, color=Theme.PRIMARY)
    for a in anime_list[:8]:
        score = f"⭐ {a.get('score')}" if a.get("score") else "✨ جديد"
        embed.add_field(
            name=a.get("title", "؟"),
            value=f"{genres_ar(a)}\\n{score}",
            inline=True,
        )
    
    if anime_list and (img := get_large_image(anime_list[0])):
        embed.set_image(url=img)
    
    embed.set_footer(text="🌸 The Veyn • بوت الأنمي")
    
    view = SeasonSelectView(anime_list[:8])
    await msg.edit(embed=embed, view=view)


# ═══════════════════════════════════════════════════════════════
# 📅  WEEKLY NOTIFICATION
# ═══════════════════════════════════════════════════════════════

@tasks.loop(hours=168)
async def weekly_notify():
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return
    
    anime_list = await fetch_seasonal(10)
    if not anime_list:
        return
    
    embed = build_weekly_embed(anime_list)
    view = MainMenuView()
    await channel.send(embed=embed, view=view)

# ═══════════════════════════════════════════════════════════════
# 🚀  RUN
# ═══════════════════════════════════════════════════════════════
bot.run(TOKEN)
'''


