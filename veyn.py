"""
╔══════════════════════════════════════════╗
║     🌸  The Veyn — بوت الأنمي v2        ║
║  قائمة حلقات · Watchlist · Top Anime    ║
║  إشعارات أسبوعية · ألوان حسب التصنيف   ║
╚══════════════════════════════════════════╝
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timezone

# ──────────────────────────────────────────
TOKEN = "YOUR_BOT_TOKEN_HERE"
# قناة الإشعارات الأسبوعية (ضع ID القناة)
NOTIFY_CHANNEL_ID = 123456789012345678
# ──────────────────────────────────────────

# ════════════ ألوان حسب التصنيف ════════════
GENRE_COLORS = {
    "Action":        0xFF4757,   # أحمر
    "Romance":       0xFF6B9D,   # وردي
    "Comedy":        0xFFD93D,   # أصفر
    "Horror":        0x2C2C54,   # أسود/بنفسجي
    "Fantasy":       0x6C63FF,   # بنفسجي
    "Sci-Fi":        0x00D4AA,   # تيل
    "Mystery":       0x8B5CF6,   # بنفسجي داكن
    "Sports":        0x10B981,   # أخضر
    "Slice of Life": 0xF59E0B,   # برتقالي
    "Mecha":         0x6B7280,   # رمادي
    "Psychological": 0xDC2626,   # أحمر داكن
    "Supernatural":  0x7C3AED,   # بنفسجي
    "Drama":         0x3B82F6,   # أزرق
    "Adventure":     0xF97316,   # برتقالي
    "default":       0x6C63FF,
}

STATUS_AR = {
    "Finished Airing":  ("✅", "مكتمل"),
    "Currently Airing": ("🔴", "يعرض الآن"),
    "Not yet aired":    ("⏳", "لم يعرض بعد"),
}

GENRE_AR = {
    "Action":"أكشن","Adventure":"مغامرة","Comedy":"كوميديا",
    "Drama":"دراما","Fantasy":"فانتازيا","Horror":"رعب",
    "Mystery":"غموض","Romance":"رومانسي","Sci-Fi":"خيال علمي",
    "Slice of Life":"حياة يومية","Sports":"رياضة",
    "Supernatural":"خارق للطبيعة","Thriller":"إثارة",
    "Mecha":"ميكا","Music":"موسيقى","Psychological":"نفسي",
    "Shounen":"شونن","Shoujo":"شوجو","Seinen":"سينن",
    "Historical":"تاريخي","School":"مدرسية","Magic":"سحر",
    "Isekai":"إيسيكاي","Harem":"حريم","Ecchi":"إيتشي",
}

SEASON_AR = {"winter":"شتاء","spring":"ربيع","summer":"صيف","fall":"خريف"}

# ════════════ JSON Storage ════════════
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
        db[key] = {"watchlist": [], "watching": {}}
    return db[key]

# ════════════ API Helpers ════════════
async def jikan_get(path: str) -> dict | None:
    url = f"https://api.jikan.moe/v4{path}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if r.status != 200:
                return None
            return await r.json()

async def fetch_anime_search(query: str) -> dict | None:
    data = await jikan_get(f"/anime?q={query}&limit=1&sfw=true")
    if not data:
        return None
    results = data.get("data", [])
    return results[0] if results else None

async def fetch_random() -> dict | None:
    data = await jikan_get("/random/anime")
    return data.get("data") if data else None

async def fetch_top(limit: int = 10) -> list:
    data = await jikan_get(f"/top/anime?limit={limit}")
    return data.get("data", []) if data else []

async def fetch_episodes(mal_id: int) -> list:
    data = await jikan_get(f"/anime/{mal_id}/episodes")
    return data.get("data", []) if data else []

async def fetch_seasonal() -> list:
    data = await jikan_get("/seasons/now?limit=10")
    return data.get("data", []) if data else []

# ════════════ Utilities ════════════
def get_color(anime: dict) -> int:
    genres = anime.get("genres", []) + anime.get("themes", [])
    for g in genres:
        c = GENRE_COLORS.get(g["name"])
        if c:
            return c
    return GENRE_COLORS["default"]

def genres_ar(anime: dict) -> str:
    genres = anime.get("genres", []) + anime.get("themes", [])
    names = [GENRE_AR.get(g["name"], g["name"]) for g in genres[:5]]
    return " · ".join(names) if names else "—"

def score_bar(score) -> str:
    if not score:
        return "☆☆☆☆☆  غير مقيّم"
    filled = round(score / 2)
    bar = "★" * filled + "☆" * (5 - filled)
    return f"{bar}  `{score}/10`"

def status_fmt(status: str) -> str:
    icon, txt = STATUS_AR.get(status, ("❓", status))
    return f"{icon} {txt}"

def thumb(anime: dict) -> str | None:
    return anime.get("images", {}).get("jpg", {}).get("large_image_url")

def synopsis_short(anime: dict, limit=380) -> str:
    s = anime.get("synopsis") or "لا يوجد وصف."
    return s[:limit] + "..." if len(s) > limit else s

# ════════════ MAIN EMBED BUILDER ════════════
def build_embed(anime: dict, prefix: str = "", color: int | None = None) -> discord.Embed:
    color = color or get_color(anime)
    title_en = anime.get("title") or "؟"
    title_jp = anime.get("title_japanese") or ""
    url      = anime.get("url", "")
    episodes = anime.get("episodes") or "؟"
    year     = anime.get("year") or "—"
    score    = anime.get("score")
    status   = anime.get("status", "")
    rank     = anime.get("rank") or "—"
    studios  = [s["name"] for s in anime.get("studios", [])]
    season   = anime.get("season") or ""
    season_ar = SEASON_AR.get(season, season)

    embed = discord.Embed(
        title=f"{prefix}{title_en}",
        description=(
            f"*{title_jp}*\n\n"
            f"📖 **القصة**\n{synopsis_short(anime)}"
        ),
        color=color,
        url=url or discord.Embed.Empty,
    )

    embed.add_field(name="🎭 التصنيفات", value=genres_ar(anime), inline=False)

    embed.add_field(name="⭐ التقييم",   value=score_bar(score),   inline=True)
    embed.add_field(name="📺 الحلقات",   value=str(episodes),      inline=True)
    embed.add_field(name="🏆 الترتيب",   value=f"#{rank}",         inline=True)

    embed.add_field(name="📅 السنة",     value=f"{season_ar} {year}".strip(), inline=True)
    embed.add_field(name="🏷️ الحالة",   value=status_fmt(status), inline=True)
    embed.add_field(
        name="🎥 الاستوديو",
        value=" · ".join(studios[:2]) if studios else "—",
        inline=True,
    )

    if t := thumb(anime):
        embed.set_thumbnail(url=t)

    embed.set_footer(
        text=f"The Veyn • بوت الأنمي  |  MAL ID: {anime.get('mal_id','؟')}",
    )
    return embed

# ════════════ VIEWS ════════════

class AnimeView(discord.ui.View):
    """الأزرار الرئيسية تحت بطاقة الأنمي"""
    def __init__(self, anime: dict, user_id: int):
        super().__init__(timeout=180)
        self.anime   = anime
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

    @discord.ui.button(label="+ Watchlist", emoji="📌", style=discord.ButtonStyle.success, row=1)
    async def add_watch(self, interaction: discord.Interaction, btn: discord.ui.Button):
        db  = load_db()
        usr = get_user(db, interaction.user.id)
        mal = self.anime.get("mal_id")
        existing = [a for a in usr["watchlist"] if a["mal_id"] == mal]
        if existing:
            await interaction.response.send_message(
                embed=err_embed("هاد الأنمي موجود بالفعل في Watchlist تاعتك! 📋"),
                ephemeral=True
            )
            return
        usr["watchlist"].append({
            "mal_id":   mal,
            "title":    self.anime.get("title"),
            "episodes": self.anime.get("episodes") or 0,
            "watched":  0,
            "score":    self.anime.get("score"),
            "image":    thumb(self.anime),
        })
        save_db(db)
        e = discord.Embed(
            title="✅ تمت الإضافة!",
            description=f"**{self.anime.get('title')}** انضاف لـ Watchlist تاعتك.",
            color=0x00D4AA
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="قائمة الحلقات", emoji="📋", style=discord.ButtonStyle.primary, row=1)
    async def episodes_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        eps = await fetch_episodes(self.anime["mal_id"])
        if not eps:
            await interaction.followup.send(
                embed=err_embed("ما في بيانات حلقات متاحة لهاد الأنمي."), ephemeral=True
            )
            return
        view = EpisodesView(self.anime, eps, self.user_id)
        embed = view.build_page()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="أنمي مشابه", emoji="🔍", style=discord.ButtonStyle.secondary, row=1)
    async def similar_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        genres = self.anime.get("genres", [])
        if not genres:
            await interaction.followup.send(
                embed=err_embed("ما أقدر أجد أنمي مشابه."), ephemeral=True
            )
            return
        genre_id = genres[0]["mal_id"]
        data = await jikan_get(f"/anime?genres={genre_id}&order_by=score&sort=desc&limit=5&sfw=true")
        results = (data or {}).get("data", [])
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
                name=a.get("title","؟"),
                value=f"{genres_ar(a)}\n{score}",
                inline=True
            )
        await interaction.followup.send(embed=e, ephemeral=True)

    @discord.ui.button(label="عشوائي آخر", emoji="🎲", style=discord.ButtonStyle.secondary, row=2)
    async def random_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.defer()
        anime = await fetch_random()
        if not anime:
            await interaction.followup.send(embed=err_embed("فشل التحميل."), ephemeral=True)
            return
        embed = build_embed(anime, "🎲 ")
        view  = AnimeView(anime, interaction.user.id)
        await interaction.edit_original_response(embed=embed, view=view)


class EpisodesView(discord.ui.View):
    """صفحات قائمة الحلقات مع تتبع المشاهدة"""
    PER_PAGE = 10

    def __init__(self, anime: dict, eps: list, user_id: int):
        super().__init__(timeout=120)
        self.anime   = anime
        self.eps     = eps
        self.user_id = user_id
        self.page    = 0
        self.total   = (len(eps) - 1) // self.PER_PAGE

    def build_page(self) -> discord.Embed:
        start = self.page * self.PER_PAGE
        chunk = self.eps[start:start + self.PER_PAGE]

        db  = load_db()
        usr = get_user(db, self.user_id)
        watched_num = usr.get("watching", {}).get(str(self.anime["mal_id"]), 0)

        color = get_color(self.anime)
        embed = discord.Embed(
            title=f"📋 حلقات {self.anime.get('title','؟')}",
            description=f"شاهدت: **{watched_num}** / {len(self.eps)} حلقة",
            color=color,
        )

        for ep in chunk:
            num   = ep.get("mal_id") or "؟"
            title = ep.get("title") or f"الحلقة {num}"
            aired = ep.get("aired") or "—"
            icon  = "✅" if isinstance(num, int) and num <= watched_num else "⬜"
            embed.add_field(
                name=f"{icon} الحلقة {num}",
                value=f"{title}\n📅 {aired}",
                inline=True,
            )

        embed.set_footer(text=f"صفحة {self.page+1} / {self.total+1}  |  The Veyn")
        if t := thumb(self.anime):
            embed.set_thumbnail(url=t)
        return embed

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page < self.total:
            self.page += 1
        await interaction.response.edit_message(embed=self.build_page(), view=self)

    @discord.ui.button(label="✅ سجّل حلقة", style=discord.ButtonStyle.success)
    async def mark_ep(self, interaction: discord.Interaction, btn: discord.ui.Button):
        db  = load_db()
        usr = get_user(db, interaction.user.id)
        mid = str(self.anime["mal_id"])
        cur = usr.get("watching", {}).get(mid, 0)
        total_eps = len(self.eps)
        if cur >= total_eps:
            await interaction.response.send_message(
                embed=err_embed("شاهدت كل الحلقات بالفعل! 🎉"), ephemeral=True
            )
            return
        usr.setdefault("watching", {})[mid] = cur + 1
        save_db(db)
        e = discord.Embed(
            title="✅ تم التسجيل!",
            description=f"سجّلت الحلقة **{cur+1}** من **{self.anime.get('title')}**.\nالمتبقي: {total_eps - cur - 1} حلقة",
            color=0x00D4AA
        )
        await interaction.response.send_message(embed=e, ephemeral=True)
        await interaction.message.edit(embed=self.build_page(), view=self)


class WatchlistView(discord.ui.View):
    """عرض Watchlist مع خيارات الإدارة"""
    PER_PAGE = 5

    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.page = 0

    def get_data(self):
        db  = load_db()
        usr = get_user(db, self.user_id)
        return usr.get("watchlist", []), usr.get("watching", {})

    def build_embed(self) -> discord.Embed:
        wl, watching = self.get_data()
        if not wl:
            return discord.Embed(
                title="📋 Watchlist فارغة",
                description="ما أضفت أي أنمي بعد!\nاستخدم الزر 📌 في بطاقة الأنمي لإضافته.",
                color=0x6C63FF
            )

        total = len(wl)
        chunk = wl[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]
        self.total_pages = (total - 1) // self.PER_PAGE

        embed = discord.Embed(
            title="📋 Watchlist تاعتك",
            description=f"عندك **{total}** أنمي  |  صفحة {self.page+1}/{self.total_pages+1}",
            color=0x6C63FF
        )

        for a in chunk:
            mid      = str(a.get("mal_id",""))
            watched  = watching.get(mid, 0)
            total_ep = a.get("episodes") or "؟"
            score    = f"⭐ {a['score']}" if a.get("score") else ""
            progress = f"{watched}/{total_ep}"
            if isinstance(total_ep, int) and total_ep > 0:
                pct  = int((watched / total_ep) * 10)
                bar  = "🟩" * pct + "⬜" * (10 - pct)
            else:
                bar = "—"

            embed.add_field(
                name=a.get("title","؟"),
                value=f"{bar}\n`{progress}` حلقة  {score}",
                inline=False,
            )

        embed.set_footer(text="The Veyn • بوت الأنمي")
        return embed

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev_p(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_p(self, interaction: discord.Interaction, btn: discord.ui.Button):
        wl, _ = self.get_data()
        total_pages = (len(wl) - 1) // self.PER_PAGE
        if self.page < total_pages:
            self.page += 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="🗑️ مسح أنمي", style=discord.ButtonStyle.danger)
    async def remove_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        wl, _ = self.get_data()
        if not wl:
            await interaction.response.send_message(embed=err_embed("القائمة فارغة."), ephemeral=True)
            return
        view = RemoveSelect(self.user_id, wl[:25])
        await interaction.response.send_message(
            embed=discord.Embed(title="🗑️ اختر الأنمي اللي تبي تمسحه", color=0xFF4757),
            view=view, ephemeral=True
        )


class RemoveSelect(discord.ui.View):
    def __init__(self, user_id: int, watchlist: list):
        super().__init__(timeout=60)
        self.user_id = user_id
        options = [
            discord.SelectOption(label=a["title"][:100], value=str(a["mal_id"]))
            for a in watchlist
        ]
        select = discord.ui.Select(placeholder="اختر أنمي...", options=options)
        select.callback = self.do_remove
        self.add_item(select)

    async def do_remove(self, interaction: discord.Interaction):
        mal_id = int(interaction.data["values"][0])
        db  = load_db()
        usr = get_user(db, self.user_id)
        before = len(usr["watchlist"])
        usr["watchlist"] = [a for a in usr["watchlist"] if a["mal_id"] != mal_id]
        usr.get("watching", {}).pop(str(mal_id), None)
        save_db(db)
        removed = before - len(usr["watchlist"])
        e = discord.Embed(
            title="🗑️ تم الحذف" if removed else "❌ ما وجدناه",
            color=0xFF4757 if removed else 0xFF4757
        )
        await interaction.response.edit_message(embed=e, view=None)


class TopAnimeView(discord.ui.View):
    """عرض Top 10 مع Select للتفاصيل"""
    def __init__(self, anime_list: list):
        super().__init__(timeout=180)
        self.anime_list = anime_list
        options = [
            discord.SelectOption(
                label=f"#{i+1} {a['title'][:80]}",
                value=str(i),
                emoji="🏆" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else "⭐"))
            )
            for i, a in enumerate(anime_list)
        ]
        select = discord.ui.Select(placeholder="اختر أنمي للتفاصيل...", options=options)
        select.callback = self.show_detail
        self.add_item(select)

    async def show_detail(self, interaction: discord.Interaction):
        idx   = int(interaction.data["values"][0])
        anime = self.anime_list[idx]
        medals = ["🥇","🥈","🥉"]
        prefix = (medals[idx] if idx < 3 else f"#{idx+1} ") + " "
        embed  = build_embed(anime, prefix)
        view   = AnimeView(anime, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ════════════ ERROR EMBED ════════════
def err_embed(msg: str) -> discord.Embed:
    return discord.Embed(
        title="❌ خطأ",
        description=msg,
        color=0xFF4757
    ).set_footer(text="The Veyn • بوت الأنمي")

def loading_embed(msg: str = "⏳ جاري التحميل...") -> discord.Embed:
    return discord.Embed(description=msg, color=0x6C63FF)

# ════════════ BOT SETUP ════════════
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="🌸 الأنمي | The Veyn"
        )
    )
    weekly_notify.start()
    print(f"✅ The Veyn Bot — {bot.user} — جاهز!")

# ════════════ SLASH COMMANDS ════════════

# ─── /anime ───────────────────────────────
@bot.tree.command(name="anime", description="ابحث عن أنمي")
@app_commands.describe(name="اسم الأنمي (عربي أو إنجليزي)")
async def anime_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    msg = await interaction.followup.send(embed=loading_embed(f"🔍 بدور عن **{name}**..."))
    anime = await fetch_anime_search(name)
    if not anime:
        await msg.edit(embed=err_embed(
            f"ما لقيت أنمي باسم **{name}**.\n"
            "تأكد من الاسم أو جرب اسم مختلف."
        ))
        return
    embed = build_embed(anime, "🔍 ")
    view  = AnimeView(anime, interaction.user.id)
    await msg.edit(embed=embed, view=view)

# ─── /suggest ─────────────────────────────
@bot.tree.command(name="suggest", description="احصل على اقتراح أنمي عشوائي")
async def suggest_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    msg = await interaction.followup.send(embed=loading_embed("🎲 جاري الاختيار العشوائي..."))
    anime = await fetch_random()
    if not anime:
        await msg.edit(embed=err_embed("حصل خطأ، حاول مرة أخرى."))
        return
    embed = build_embed(anime, "🎲 اقتراح: ")
    view  = AnimeView(anime, interaction.user.id)
    await msg.edit(embed=embed, view=view)

# ─── /top ─────────────────────────────────
@bot.tree.command(name="top", description="أفضل 10 أنمي على MyAnimeList")
async def top_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    msg = await interaction.followup.send(embed=loading_embed("🏆 جاري تحميل الترتيب..."))
    anime_list = await fetch_top(10)
    if not anime_list:
        await msg.edit(embed=err_embed("فشل تحميل القائمة."))
        return

    embed = discord.Embed(
        title="🏆 Top 10 أنمي — MyAnimeList",
        color=0xFFD93D,
        description="أفضل 10 أنمي حسب تقييم المستخدمين"
    )
    medals = ["🥇","🥈","🥉"]
    for i, a in enumerate(anime_list):
        medal = medals[i] if i < 3 else f"`#{i+1}`"
        score = f"⭐ {a.get('score')}" if a.get("score") else ""
        eps   = f"📺 {a.get('episodes')} حلقة" if a.get("episodes") else ""
        embed.add_field(
            name=f"{medal} {a.get('title','؟')}",
            value=f"{score}  {eps}",
            inline=False,
        )

    embed.set_footer(text="اختر من القائمة أدناه للتفاصيل  |  The Veyn")
    view = TopAnimeView(anime_list)
    await msg.edit(embed=embed, view=view)

# ─── /watchlist ───────────────────────────
@bot.tree.command(name="watchlist", description="شوف أو دير Watchlist تاعتك")
async def watchlist_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    view  = WatchlistView(interaction.user.id)
    embed = view.build_embed()
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

# ─── /season ──────────────────────────────
@bot.tree.command(name="season", description="أنمي الموسم الحالي")
async def season_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    msg = await interaction.followup.send(embed=loading_embed("🌸 جاري تحميل أنمي الموسم..."))
    anime_list = await fetch_seasonal()
    if not anime_list:
        await msg.edit(embed=err_embed("فشل تحميل أنمي الموسم."))
        return

    now = datetime.now(timezone.utc)
    season_names = {1:"شتاء",2:"شتاء",3:"ربيع",4:"ربيع",5:"ربيع",
                    6:"صيف",7:"صيف",8:"صيف",9:"خريف",10:"خريف",
                    11:"خريف",12:"شتاء"}
    season_label = f"🌸 أنمي موسم {season_names[now.month]} {now.year}"

    embed = discord.Embed(title=season_label, color=0xFF6B9D)
    for a in anime_list[:8]:
        score = f"⭐ {a.get('score')}" if a.get("score") else "جديد"
        embed.add_field(
            name=a.get("title","؟"),
            value=f"{genres_ar(a)}\n{score}",
            inline=True,
        )
    embed.set_footer(text="The Veyn • بوت الأنمي")

    # زر تفاصيل أول أنمي
    class SeasonView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            options = [
                discord.SelectOption(label=a["title"][:100], value=str(i))
                for i, a in enumerate(anime_list[:8])
            ]
            sel = discord.ui.Select(placeholder="اختر أنمي...", options=options)
            sel.callback = self.show
            self.add_item(sel)

        async def show(self, inter: discord.Interaction):
            idx   = int(inter.data["values"][0])
            anime = anime_list[idx]
            e     = build_embed(anime, "🌸 ")
            v     = AnimeView(anime, inter.user.id)
            await inter.response.send_message(embed=e, view=v, ephemeral=True)

    await msg.edit(embed=embed, view=SeasonView())

# ════════════ WEEKLY TASK ════════════
@tasks.loop(hours=168)   # كل أسبوع
async def weekly_notify():
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return
    anime_list = await fetch_seasonal()
    if not anime_list:
        return

    embed = discord.Embed(
        title="📢 أنمي الأسبوع — The Veyn",
        description="هون أبرز أنمي يعرض هالموسم 🌸",
        color=0xFF6B9D,
        timestamp=datetime.now(timezone.utc),
    )
    for a in anime_list[:5]:
        score = f"⭐ {a.get('score')}" if a.get("score") else "جديد"
        embed.add_field(
            name=a.get("title","؟"),
            value=f"{genres_ar(a)}\n{score}",
            inline=False,
        )
    embed.set_footer(text="The Veyn • يتجدد كل أسبوع")
    await channel.send(embed=embed)

# ════════════════════════════════════════
bot.run(TOKEN)
