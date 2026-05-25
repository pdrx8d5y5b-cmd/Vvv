"""
╔═══════════════════════════════════════════════════════════════╗
║     🌸  The Veyn — بوت الأنمي v5.0 (Clean Edition)       ║
║  Embed أنمي + Dropdown حلقات + زر تشغيل برابط مباشر            ║
╚═══════════════════════════════════════════════════════════════╝
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Optional, List

load_dotenv()
TOKEN = os.getenv("TOKEN")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", "0"))

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
    DARK      = 0x2D2D2D
    GOLD      = 0xFFD700

    GENRE_COLORS = {
        "Action": 0xFF4757, "Adventure": 0xF97316, "Comedy": 0xFFD93D,
        "Drama": 0x3B82F6, "Fantasy": 0x8B5CF6, "Horror": 0xDC2626,
        "Mystery": 0x6D28D9, "Romance": 0xEC4899, "Sci-Fi": 0x06B6D4,
        "Slice of Life": 0xF59E0B, "Sports": 0x10B981, "Supernatural": 0x7C3AED,
        "Psychological": 0xBE185D, "Thriller": 0x991B1B, "Mecha": 0x4B5563,
        "Music": 0xF472B6, "Isekai": 0x6366F1, "Harem": 0xFB7185,
        "Ecchi": 0xF43F5E, "Shounen": 0xFBBF24, "Shoujo": 0xF472B6,
        "Seinen": 0x64748B, "Historical": 0x92400E, "School": 0x3B82F6,
        "Magic": 0xA78BFA, "default": 0xFF6B9D,
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
# 🌐  API - Jikan (MyAnimeList)
# ═══════════════════════════════════════════════════════════════

async def jikan_get(path: str) -> Optional[dict]:
    url = f"https://api.jikan.moe/v4{path}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if r.status != 200:
                return None
            return await r.json()

async def fetch_anime_search(query: str, limit: int = 10) -> List[dict]:
    data = await jikan_get(f"/anime?q={query}&limit={limit}&sfw=true")
    if not data:
        return []
    return data.get("data", [])

async def fetch_anime_by_id(mal_id: int) -> Optional[dict]:
    data = await jikan_get(f"/anime/{mal_id}/full")
    return data.get("data") if data else None

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

async def fetch_episodes(mal_id: int) -> List[dict]:
    """Fetch episodes with pagination support"""
    all_eps = []
    page = 1
    while True:
        data = await jikan_get(f"/anime/{mal_id}/episodes?page={page}")
        if not data:
            break
        eps = data.get("data", [])
        if not eps:
            break
        all_eps.extend(eps)
        pagination = data.get("pagination", {})
        if not pagination.get("has_next_page"):
            break
        page += 1
        await asyncio.sleep(0.5)  # Rate limit respect
    return all_eps

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

def get_large_image(anime: dict) -> Optional[str]:
    images = anime.get("images", {})
    jpg = images.get("jpg", {})
    return jpg.get("large_image_url") or jpg.get("image_url")

def get_thumbnail(anime: dict) -> Optional[str]:
    images = anime.get("images", {})
    jpg = images.get("jpg", {})
    return jpg.get("image_url")

def get_banner_image(anime: dict) -> Optional[str]:
    images = anime.get("images", {})
    jpg = images.get("jpg", {})
    webp = images.get("webp", {})
    return (
        webp.get("large_image_url") or 
        jpg.get("large_image_url") or 
        webp.get("image_url") or 
        jpg.get("image_url")
    )

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

def format_duration(duration: str) -> str:
    if not duration:
        return "—"
    return duration.replace("per ep", "لكل حلقة")

# ═══════════════════════════════════════════════════════════════
# 📦  EMBED BUILDERS
# ═══════════════════════════════════════════════════════════════

def build_embed(anime: dict, prefix: str = "", color: Optional[int] = None) -> discord.Embed:
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
        title=f'{prefix}"{title_en}"',
        description="\n".join(desc_lines),
        color=color,
        url=url,
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(name="🎭 التصنيفات", value=genres_ar(anime), inline=False)
    embed.add_field(name="⭐ التقييم", value=score_bar(score), inline=True)
    embed.add_field(name="📺 الحلقات", value=f"`{episodes}`", inline=True)
    embed.add_field(name="📅 السنة", value=f"{season_ar} `{year}`".strip(), inline=True)
    embed.add_field(name="🏷️ الحالة", value=status_fmt(status), inline=True)
    embed.add_field(name="🎥 الاستوديو", value=" · ".join(studios[:2]) if studios else "—", inline=True)

    duration = anime.get("duration")
    if duration:
        embed.add_field(name="⏱️ المدة", value=f"`{format_duration(duration)}`", inline=True)

    rating = anime.get("rating")
    if rating:
        embed.add_field(name="🔞 التصنيف العمري", value=f"`{rating}`", inline=True)

    large_img = get_banner_image(anime)
    if large_img:
        embed.set_image(url=large_img)

    thumb_img = get_thumbnail(anime)
    if thumb_img:
        embed.set_thumbnail(url=thumb_img)

    embed.set_footer(
        text=f"🌸 The Veyn  |  MAL ID: {anime.get('mal_id', '؟')}",
        icon_url="https://cdn.discordapp.com/embed/avatars/0.png"
    )
    return embed


def build_search_dropdown_embed(query: str, results: List[dict]) -> discord.Embed:
    embed = discord.Embed(
        title=f"🔍 نتائج البحث: {query}",
        description=f"تم العثور على **{len(results)}** نتيجة\n\nاختر الأنمي من القائمة أدناه 👇",
        color=Theme.PRIMARY,
        timestamp=datetime.now(timezone.utc)
    )

    for i, a in enumerate(results[:5]):
        score = f"⭐ {a.get('score')}" if a.get('score') else "✨ جديد"
        status = STATUS_AR.get(a.get('status', ''), ('', ''))[1] or a.get('status', '')
        embed.add_field(
            name=f"{i+1}. {a.get('title', '؟')}",
            value=f"{score} | 📺 {a.get('episodes', '؟')} حلقة | {status}",
            inline=False
        )

    if results and (img := get_thumbnail(results[0])):
        embed.set_thumbnail(url=img)

    embed.set_footer(text="🌸 The Veyn • اختر أنمي من القائمة للتفاصيل")
    return embed


def build_top_embed(anime_list: List[dict], title: str = "🏆 Top 10") -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description="أفضل الأنميات حسب تقييم المستخدمين على MyAnimeList",
        color=Theme.GOLD,
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

    if anime_list:
        img = get_banner_image(anime_list[0])
        if img:
            embed.set_image(url=img)

    embed.set_footer(text="🌸 The Veyn • اختر من القائمة أدناه للتفاصيل")
    return embed


def build_episode_embed(anime: dict, episode_num: int, total_eps: int) -> discord.Embed:
    title = anime.get("title", "؟")
    embed = discord.Embed(
        title=f'▶️ "{title}"',
        description=(
            f"🎬 **الحلقة {episode_num} من {total_eps}**\n\n"
            f"🌸 استمتع بالمشاهدة!\n"
            f"⏱️ استخدم الأزرار للتنقل بين الحلقات"
        ),
        color=Theme.SUCCESS,
        timestamp=datetime.now(timezone.utc)
    )

    bar = progress_bar(episode_num, total_eps)
    embed.add_field(name="📊 التقدم", value=f"{bar} `{episode_num}/{total_eps}`", inline=False)

    img = get_banner_image(anime)
    if img:
        embed.set_image(url=img)

    thumb = get_thumbnail(anime)
    if thumb:
        embed.set_thumbnail(url=thumb)

    embed.set_footer(text=f"🌸 The Veyn • {title}")
    return embed


def err_embed(msg: str) -> discord.Embed:
    return discord.Embed(
        title="❌ خطأ", 
        description=msg, 
        color=Theme.DANGER
    ).set_footer(text="🌸 The Veyn")

def loading_embed(msg: str = "⏳ جاري التحميل...") -> discord.Embed:
    return discord.Embed(
        description=f"🌸 {msg}", 
        color=Theme.SECONDARY
    )

def success_embed(title: str, msg: str) -> discord.Embed:
    return discord.Embed(
        title=f"✅ {title}",
        description=msg,
        color=Theme.SUCCESS
    ).set_footer(text="🌸 The Veyn")

# ═══════════════════════════════════════════════════════════════
# 🎛️  VIEWS — نفس نظام The Veyn بالضبط
# ═══════════════════════════════════════════════════════════════

class AnimeDropdown(discord.ui.View):
    """Dropdown menu for anime search results — exactly like the screenshot"""
    def __init__(self, results: List[dict], user_id: int):
        super().__init__(timeout=300)
        self.results = results
        self.user_id = user_id

        options = []
        for i, a in enumerate(results[:25]):
            label = a.get("title", "؟")[:100]
            description = f"⭐ {a.get('score', '؟')} | 📺 {a.get('episodes', '؟')} eps"
            if len(description) > 100:
                description = description[:97] + "..."

            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(i),
                    description=description,
                    emoji=medal_emoji(i + 1) if i < 3 else "🎬"
                )
            )

        select = discord.ui.Select(
            placeholder="🔍 اختر أنمي من القائمة...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        anime = self.results[idx]

        await interaction.response.defer(ephemeral=True)
        full_anime = await fetch_anime_by_id(anime["mal_id"])
        if not full_anime:
            full_anime = anime

        embed = build_embed(full_anime, "🎬 ")
        view = AnimeDetailView(full_anime, interaction.user.id)

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class AnimeDetailView(discord.ui.View):
    """Detailed view for a single anime — matches screenshot exactly"""
    def __init__(self, anime: dict, user_id: int):
        super().__init__(timeout=300)
        self.anime = anime
        self.user_id = user_id

        # External links row
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

    @discord.ui.button(label="📌 قائمتي", style=discord.ButtonStyle.success, row=1)
    async def add_watch(self, interaction: discord.Interaction, btn: discord.ui.Button):
        embed = success_embed(
            "تمت الإضافة!",
            f'**{self.anime.get("title")}** انضاف لـ قائمتك 🌸'
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📋 الحلقات", style=discord.ButtonStyle.primary, row=1)
    async def episodes_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        eps = await fetch_episodes(self.anime["mal_id"])
        if not eps:
            await interaction.followup.send(
                embed=err_embed("ما في بيانات حلقات متاحة."),
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
            title=f'🔍 أنمي مشابه لـ {self.anime.get("title")}',
            color=get_color(self.anime)
        )
        for a in results:
            score = f"⭐ {a.get('score')}" if a.get("score") else "غير مقيّم"
            e.add_field(
                name=a.get("title", "؟"),
                value=f"{genres_ar(a)}\n{score}",
                inline=True
            )
        await interaction.followup.send(embed=e, ephemeral=True)

    @discord.ui.button(label="🎲 عشوائي آخر", style=discord.ButtonStyle.secondary, row=2)
    async def random_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        anime = await fetch_random()
        if not anime:
            await interaction.followup.send(embed=err_embed("فشل التحميل."), ephemeral=True)
            return

        embed = build_embed(anime, "🎲 ")
        view = AnimeDetailView(anime, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class EpisodesView(discord.ui.View):
    """Episode selection with pagination — matches screenshot dropdown style"""
    PER_PAGE = 10

    def __init__(self, anime: dict, eps: list, user_id: int):
        super().__init__(timeout=180)
        self.anime = anime
        self.eps = eps
        self.user_id = user_id
        self.page = 0
        self.total_pages = max(0, (len(eps) - 1) // self.PER_PAGE)

    def build_page(self) -> discord.Embed:
        start = self.page * self.PER_PAGE
        chunk = self.eps[start:start + self.PER_PAGE]

        color = get_color(self.anime)
        embed = discord.Embed(
            title=f'📋 "{self.anime.get("title", "؟")}"',
            description="اختر الحلقة للمشاهدة 👇",
            color=color,
        )

        for ep in chunk:
            # Jikan returns mal_id as episode number for episodes endpoint
            num = ep.get("mal_id") or "؟"
            title = ep.get("title") or ep.get("title_romanji") or f"الحلقة {num}"
            aired = ep.get("aired") or "—"
            embed.add_field(
                name=f"🍚 الحلقة {num}",
                value=f"{title}\n📅 {aired}",
                inline=True,
            )

        embed.set_footer(text=f"صفحة {self.page+1}/{self.total_pages+1} | 🌸 The Veyn")

        if img := get_thumbnail(self.anime):
            embed.set_thumbnail(url=img)

        return embed

    @discord.ui.button(emoji="◀️", label="السابق", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)

    @discord.ui.button(emoji="▶️", label="التالي", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page < self.total_pages:
            self.page += 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)

    @discord.ui.button(label="✅ اختر الحلقة", style=discord.ButtonStyle.success, row=1)
    async def select_episode(self, interaction: discord.Interaction, btn: discord.ui.Button):
        # Show episode selector with pagination
        view = EpisodeSelectView(self.anime, self.eps, self.user_id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎬 اختر الحلقة",
                description="اختر الحلقة اللي تبي تشوفها من القائمة 👇",
                color=Theme.PRIMARY
            ),
            view=view,
            ephemeral=True
        )


class EpisodeSelectView(discord.ui.View):
    """Dropdown to select specific episode — exactly like screenshot"""
    def __init__(self, anime: dict, eps: list, user_id: int):
        super().__init__(timeout=180)
        self.anime = anime
        self.eps = eps
        self.user_id = user_id

        # Discord Select max 25 options — show first 25 episodes
        options = []
        for ep in eps[:25]:
            num = ep.get("mal_id") or "؟"  # Jikan uses mal_id as episode number
            title = ep.get("title") or f"الحلقة {num}"
            options.append(
                discord.SelectOption(
                    label=f"الحلقة {num}",
                    value=str(num),
                    description=title[:100],
                    emoji="🍚"
                )
            )

        select = discord.ui.Select(
            placeholder="🎬 اختر حلقة للمشاهدة...",
            options=options
        )
        select.callback = self.episode_selected
        self.add_item(select)

    async def episode_selected(self, interaction: discord.Interaction):
        ep_num = int(interaction.data["values"][0])
        total_eps = len(self.eps)

        embed = build_episode_embed(self.anime, ep_num, total_eps)
        view = EpisodeControlView(self.anime, self.eps, ep_num, self.user_id)

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )


class EpisodeControlView(discord.ui.View):
    """Control buttons for episode viewing — matches screenshot exactly"""
    def __init__(self, anime: dict, eps: list, current_ep: int, user_id: int):
        super().__init__(timeout=300)
        self.anime = anime
        self.eps = eps
        self.current_ep = current_ep
        self.total_eps = len(eps)
        self.user_id = user_id

    def update_embed(self) -> discord.Embed:
        return build_episode_embed(self.anime, self.current_ep, self.total_eps)

    @discord.ui.button(emoji="⏪", label="السابق", style=discord.ButtonStyle.secondary, row=0)
    async def prev_ep(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.current_ep > 1:
            self.current_ep -= 1
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(emoji="▶️", label="تشغيل", style=discord.ButtonStyle.success, row=0)
    async def play_ep(self, interaction: discord.Interaction, btn: discord.ui.Button):
        # Build direct watch link like animewatch.shop
        mal_id = self.anime.get("mal_id", 0)
        title = self.anime.get("title", "؟")

        # Create a direct streaming link (placeholder — replace with your actual source)
        watch_url = f"https://animewatch.shop/AnimeBotStream?ep={mal_id}_{self.current_ep}"

        # Send ephemeral message with the link button
        link_view = discord.ui.View(timeout=60)
        link_view.add_item(discord.ui.Button(
            label="مشاهدة عبر المتصفح",
            emoji="🌐",
            url=watch_url,
            style=discord.ButtonStyle.link
        ))

        await interaction.response.send_message(
            embed=success_embed(
                "تم التشغيل!", 
                f'🎬 **{title}** — الحلقة {self.current_ep}\n\n'
                f'اضغط الزر أدناه للمشاهدة:'
            ),
            view=link_view,
            ephemeral=True
        )

    @discord.ui.button(emoji="⏩", label="التالي", style=discord.ButtonStyle.secondary, row=0)
    async def next_ep(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.current_ep < self.total_eps:
            self.current_ep += 1
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(emoji="🔢", label="رقم الحلقة", style=discord.ButtonStyle.primary, row=1)
    async def ep_number(self, interaction: discord.Interaction, btn: discord.ui.Button):
        view = EpisodeSelectView(self.anime, self.eps, self.user_id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔢 اختر رقم الحلقة",
                description="اختر الحلقة المطلوبة من القائمة 👇",
                color=Theme.PRIMARY
            ),
            view=view,
            ephemeral=True
        )


class TopWeeklyView(discord.ui.View):
    """10 buttons for top 10 anime"""
    def __init__(self, anime_list: List[dict]):
        super().__init__(timeout=300)
        self.anime_list = anime_list

        for i in range(min(10, len(anime_list))):
            medal = medal_emoji(i + 1)
            btn = discord.ui.Button(
                label=f"#{i+1}",
                emoji=medal,
                style=discord.ButtonStyle.primary if i < 3 else discord.ButtonStyle.secondary,
                row=i // 5
            )
            btn.callback = self.make_callback(i)
            self.add_item(btn)

    def make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            anime = self.anime_list[idx]
            prefix = f"{medal_emoji(idx + 1)} #{idx+1} "

            await interaction.response.defer(ephemeral=True)
            full_anime = await fetch_anime_by_id(anime["mal_id"])
            if not full_anime:
                full_anime = anime

            embed = build_embed(full_anime, prefix)
            view = TopAnimeActionView(full_anime, interaction.user.id)

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        return callback


class TopAnimeActionView(discord.ui.View):
    """Action buttons for top anime"""
    def __init__(self, anime: dict, user_id: int):
        super().__init__(timeout=300)
        self.anime = anime
        self.user_id = user_id

    @discord.ui.button(label="▶️ تشغيل", style=discord.ButtonStyle.success, row=0)
    async def play_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        mal_id = self.anime.get("mal_id", 0)
        title = self.anime.get("title", "؟")
        watch_url = f"https://animewatch.shop/AnimeBotStream?ep={mal_id}_1"

        link_view = discord.ui.View(timeout=60)
        link_view.add_item(discord.ui.Button(
            label="مشاهدة عبر المتصفح",
            emoji="🌐",
            url=watch_url,
            style=discord.ButtonStyle.link
        ))

        await interaction.response.send_message(
            embed=success_embed("تم التشغيل!", f'🎬 **{title}** — الحلقة 1'),
            view=link_view,
            ephemeral=True
        )

    @discord.ui.button(label="🔍 الأنمي", style=discord.ButtonStyle.primary, row=0)
    async def anime_cmd_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        embed = build_embed(self.anime, "🔍 ")
        view = AnimeDetailView(self.anime, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📋 الحلقات", style=discord.ButtonStyle.secondary, row=0)
    async def eps_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        eps = await fetch_episodes(self.anime["mal_id"])
        if not eps:
            await interaction.followup.send(
                embed=err_embed("ما في بيانات حلقات متاحة."),
                ephemeral=True
            )
            return

        view = EpisodesView(self.anime, eps, interaction.user.id)
        embed = view.build_page()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


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
        view = AnimeDetailView(anime, inter.user.id)
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
            name="🌸 الأنمي | The Veyn v5.0"
        )
    )
    weekly_notify.start()
    print(f"✅ The Veyn Bot v5.0 — {bot.user} — جاهز!")

# ═══════════════════════════════════════════════════════════════
# 📢  SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="anime", description="ابحث عن أنمي - يظهر قائمة dropdown")
@app_commands.describe(name="اسم الأنمي (عربي أو إنجليزي)")
async def anime_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)

    msg = await interaction.followup.send(
        embed=loading_embed(f"🔍 بدور عن **{name}**..."),
        ephemeral=True
    )

    results = await fetch_anime_search(name, limit=15)
    if not results:
        await msg.edit(embed=err_embed(
            f'ما لقيت أنمي باسم **{name}**.\nتأكد من الاسم أو جرب اسم مختلف.'
        ))
        return

    embed = build_search_dropdown_embed(name, results)
    view = AnimeDropdown(results, interaction.user.id)

    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="suggest", description="احصل على اقتراح أنمي عشوائي")
async def suggest_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("🎲 جاري الاختيار العشوائي..."), ephemeral=True)

    anime = await fetch_random()
    if not anime:
        await msg.edit(embed=err_embed("حصل خطأ، حاول مرة أخرى."))
        return

    embed = build_embed(anime, "🎲 اقتراح: ")
    view = AnimeDetailView(anime, interaction.user.id)
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="top", description="أفضل 10 أنمي على MyAnimeList")
async def top_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("🏆 جاري تحميل الترتيب..."), ephemeral=True)

    anime_list = await fetch_top(10)
    if not anime_list:
        await msg.edit(embed=err_embed("فشل تحميل القائمة."))
        return

    embed = build_top_embed(anime_list)
    view = TopWeeklyView(anime_list)
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="season", description="أنمي الموسم الحالي")
async def season_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("🌸 جاري تحميل أنمي الموسم..."), ephemeral=True)

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
            value=f"{genres_ar(a)}\n{score}",
            inline=True,
        )

    if anime_list and (img := get_banner_image(anime_list[0])):
        embed.set_image(url=img)

    embed.set_footer(text="🌸 The Veyn • بوت الأنمي الاحترافي")

    view = SeasonSelectView(anime_list[:8])
    await msg.edit(embed=embed, view=view)


@bot.tree.command(name="airing", description="أنمي يعرض حالياً")
async def airing_cmd(interaction: discord.Interaction):
    """Use seasonal now instead of broken /schedules endpoint"""
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("📡 جاري تحميل..."), ephemeral=True)

    anime_list = await fetch_seasonal(15)
    if not anime_list:
        await msg.edit(embed=err_embed("فشل التحميل."))
        return

    # Filter to only currently airing
    airing = [a for a in anime_list if a.get("status") == "Currently Airing"][:10]

    if not airing:
        await msg.edit(embed=err_embed("ما لقيت أنمي يعرض حالياً."))
        return

    embed = discord.Embed(title="📡 يعرض الآن", color=Theme.DANGER)
    for a in airing[:8]:
        score = f"⭐ {a.get('score')}" if a.get("score") else ""
        embed.add_field(name=a.get("title", "؟"), value=f"{genres_ar(a, 2)}\n{score}", inline=True)

    if airing and (img := get_banner_image(airing[0])):
        embed.set_image(url=img)

    await msg.edit(embed=embed)


@bot.tree.command(name="upcoming", description="أنمي قادم قريباً")
async def upcoming_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=loading_embed("⏳ جاري تحميل..."), ephemeral=True)

    anime_list = await fetch_upcoming(10)
    if not anime_list:
        await msg.edit(embed=err_embed("فشل التحميل."))
        return

    embed = discord.Embed(title="⏳ قادم قريباً", color=Theme.SECONDARY)
    for a in anime_list[:8]:
        embed.add_field(name=a.get("title", "؟"), value=genres_ar(a, 2), inline=True)

    if anime_list and (img := get_banner_image(anime_list[0])):
        embed.set_image(url=img)

    await msg.edit(embed=embed)


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

    now = datetime.now(timezone.utc)
    season_names = {
        1: "❄️ شتاء", 2: "❄️ شتاء", 3: "🌸 ربيع", 4: "🌸 ربيع", 5: "🌸 ربيع",
        6: "☀️ صيف", 7: "☀️ صيف", 8: "☀️ صيف", 9: "🍂 خريف", 10: "🍂 خريف",
        11: "🍂 خريف", 12: "❄️ شتاء"
    }
    season_label = f"{season_names[now.month]} {now.year}"

    embed = discord.Embed(
        title="📰 أخبار The Veyn",
        description=(
            f"🌸 **أبرز أنمي يعرض هذا الموسم**\n"
            f"📅 {season_label}\n"
            f"✨ *يتجدد تلقائياً كل أسبوع*\n\n"
            f"🏆 **توب الأسبوعي**"
        ),
        color=Theme.PRIMARY,
        timestamp=now,
    )

    for i, a in enumerate(anime_list[:5]):
        score = f"⭐ {a.get('score')}" if a.get("score") else "✨ جديد"
        genres = genres_ar(a, 3)
        status_icon = "🔴" if a.get("status") == "Currently Airing" else "⏳"
        medal = medal_emoji(i + 1)
        embed.add_field(
            name=f"{medal} #{i+1} {a.get('title', '؟')}",
            value=f"{status_icon} {genres}\n{score}",
            inline=False,
        )

    embed.add_field(
        name="⚠️ تنبيه",
        value="🔔 **القائمة تتغير كل أسبوع!** تابعونا للمزيد 🌸",
        inline=False
    )

    if anime_list:
        first_img = get_banner_image(anime_list[0])
        if first_img:
            embed.set_image(url=first_img)

    guild = channel.guild
    server_logo = guild.icon.url if guild.icon else None
    if server_logo:
        embed.set_author(
            name="The Veyn • بوت الأنمي الاحترافي",
            icon_url=server_logo
        )

    embed.set_footer(text="🌸 The Veyn • يتجدد كل أسبوع • اضغط على الأزرار للتفاصيل")

    view = TopWeeklyView(anime_list)
    await channel.send(embed=embed, view=view)


# ═══════════════════════════════════════════════════════════════
# 🚀  RUN
# ═══════════════════════════════════════════════════════════════

bot.run(TOKEN)

