import asyncio
import os
import random
import secrets
import time
import json
import math
import re
import shutil
import zipfile
import urllib.parse
from pathlib import Path
import requests
import yt_dlp

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, MessageNotModifiedError
from telethon.tl.functions.channels import EditBannedRequest, CreateChannelRequest, LeaveChannelRequest, JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest, GetBotCallbackAnswerRequest
from telethon.tl.functions.account import (
    UpdateProfileRequest, UpdateEmojiStatusRequest, UpdateColorRequest,
    UpdateBirthdayRequest, UpdateBusinessLocationRequest, UpdateBusinessWorkHoursRequest
)
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest, GetUserPhotosRequest
from telethon.tl.types import (
    MessageEntityCustomEmoji,
    ChatBannedRights, ChannelParticipantCreator, ChannelParticipantAdmin,
    DocumentAttributeSticker, InputStickerSetEmpty, InputUser, EmojiStatus, EmojiStatusEmpty,
    EmojiStatusCollectible, PeerColor, Birthday, BusinessLocation, BusinessWorkHours,
    BusinessWeeklyOpen, InputGeoPoint
)


# ==================== Telegram Premium Emoji UI ====================
# المعرّفات تخص إيموجيات تيليجرام مميزة عامة؛ يظهر الرمز قبل عنوان الزر في عملاء Telegram الداعمة.
PREMIUM_EMOJI_IDS = {
    "⏳": 5451732530048802485,
    "📥": 5433811242135331842,
    "🔍": 5188217332748527444,
    "🤖": 5372981976804366741,
    "🎙": 5382013970905309819,
    "✅": 5427009714745517609,
    "❌": 5465665476971471368,
    "📖": 5226512880362332956,
    "📊": 5431577498364158238,
    "🧠": 5237799019329105246,
    "🖼": 5375074927252621134,
    "👤": 5373012449597335010,
    "👥": 5372926953978341366,
    "👑": 5467406098367521267,
    "🔄": 5264727218734524899,
    "➕": 5226945370684140473,
    "✏": 5334673106202010226,
    "🔗": 5375129357373165375,
    "📂": 5431721976769027887,
    "📬": 5350421256627838238,
    "📱": 5407025283456835913,
    "🎟": 5377599075237502153,
    "🎭": 5359441070201513074,
    "🎯": 5350460637182993292,
    "💬": 5465300082628763143,
    "✨": 5472164874886846699,
    "🚀": 5445284980978621387,
    "🎤": 5382360961313152917,
    "🔑": 5330115548900501467,
    "⚡": 5431449001532594346,
    "⭐": 5435957248314579621,
    "📣": 5469903029144657419,
}

# رموز لا يوجد لها بديل مباشر في الحزمة المستخدمة؛ نربطها بعلامة مميزة متقاربة.
PREMIUM_ICON_ALIASES = {
    "🔙": "👈", "◀": "👈", "↩": "👈",
    "🗑": "❌", "⚠": "❌", "🛑": "❌", "⏹": "❌", "🔇": "❌",
    "⏱": "⏳", "⌛": "⏳", "📋": "📖", "📜": "📖",
    "📦": "📥", "📌": "🔗", "📍": "🔗", "📢": "📣",
    "▶": "🚀", "🎧": "🎙", "🖼️": "🖼", "💾": "📂",
    "🛡": "👑", "💳": "👤", "⚙": "🧠", "🧩": "🧠",
    "🧰": "🧠", "🧹": "✨", "🔢": "📊", "🔘": "🔍",
    "🩸": "✨", "🔴": "❌", "⚪": "✨", "🏧": "📖", "📟": "📊",
    "🏷": "🎟", "🚶": "👤", "📅": "📊", "🔊": "🎙",
}
PREMIUM_EMOJI_IDS["👈"] = 5469735272017043817
# أول ملصق من حزمة الريس التي حددها المستخدم: hell @TgEmodziBot.
OWNER_PREMIUM_EMOJI_ID = 5003588413954197329
PREMIUM_DEFAULT_SYMBOL = "✨"
PREMIUM_DEFAULT_ICON_ID = PREMIUM_EMOJI_IDS[PREMIUM_DEFAULT_SYMBOL]


def _premium_icon_for_text(text):
    """يعيد الرمز الأصلي ومعرف الإيموجي المميز المناسب للنص."""
    value = str(text or "").lstrip()
    for symbol in sorted(PREMIUM_EMOJI_IDS, key=len, reverse=True):
        if value.startswith(symbol) or value.startswith(symbol + "️"):
            return symbol, PREMIUM_EMOJI_IDS[symbol]
    for symbol, alias in PREMIUM_ICON_ALIASES.items():
        if value.startswith(symbol) or value.startswith(symbol + "️"):
            return symbol, PREMIUM_EMOJI_IDS[alias]
    return None, None


def _strip_leading_ui_symbol(text, symbol):
    if not symbol:
        return str(text or "")
    value = str(text or "").lstrip()
    if value.startswith(symbol):
        value = value[len(symbol):]
        if value.startswith("️"):
            value = value[1:]
    return value.lstrip()


# icon في KeyboardButtonStyle يظهر قبل تسمية الزر؛ لذلك يكون على يسار الاسم كما طلب المستخدم.
_ORIGINAL_BUTTON_INLINE = Button.inline

def _premium_inline_button(text, data=None, style=None, icon=None):
    original_text = str(text)
    symbol, custom_icon_id = _premium_icon_for_text(original_text)
    if icon is None:
        # حتى الأزرار التي لا تحمل إيموجي تحصل على علامة مميزة افتراضية.
        custom_icon_id = custom_icon_id or PREMIUM_DEFAULT_ICON_ID
        text = _strip_leading_ui_symbol(original_text, symbol) if symbol else original_text
        icon = custom_icon_id
    # عندما لا يحدد الزر data نحافظ على بياناته الأصلية رغم تنظيف النص الظاهر.
    if data is None:
        data = original_text
    return _ORIGINAL_BUTTON_INLINE(text, data=data, style=style, icon=icon)


_ORIGINAL_BUTTON_URL = Button.url

def _premium_url_button(text, url=None, style=None, icon=None):
    original_text = str(text)
    symbol, custom_icon_id = _premium_icon_for_text(original_text)
    # زر الريس حصرياً يأخذ أول ملصق من الحزمة التي أرسلها المستخدم.
    if "الريس" in original_text:
        custom_icon_id = OWNER_PREMIUM_EMOJI_ID
    if icon is None:
        text = _strip_leading_ui_symbol(original_text, symbol) if symbol else original_text
        icon = custom_icon_id or PREMIUM_DEFAULT_ICON_ID
    return _ORIGINAL_BUTTON_URL(text, url=url, style=style, icon=icon)


Button.inline = staticmethod(_premium_inline_button)
Button.url = staticmethod(_premium_url_button)


# تغليف مركزي لرسائل اليوزر بوت اليدوية، بما فيها الردود المعدلة بعد بدء الأمر.
_ORIGINAL_CLIENT_SEND_MESSAGE = TelegramClient.send_message
_ORIGINAL_CLIENT_EDIT_MESSAGE = TelegramClient.edit_message


def _is_manager_bot_client(client):
    return client is globals().get("bot")


def _premium_outgoing_text_payload(message, kwargs):
    if not isinstance(message, str) or not message.strip() or kwargs.get("formatting_entities"):
        return message, kwargs
    decorated, entities = prepare_premium_command_message(message)
    if entities:
        kwargs = dict(kwargs)
        kwargs["formatting_entities"] = entities
        kwargs["parse_mode"] = None
    return decorated, kwargs


async def _premium_client_send_message(self, entity, message="", *args, **kwargs):
    if not _is_manager_bot_client(self):
        message, kwargs = _premium_outgoing_text_payload(message, kwargs)
    return await _ORIGINAL_CLIENT_SEND_MESSAGE(self, entity, message, *args, **kwargs)


async def _premium_client_edit_message(self, entity, message=None, text=None, *args, **kwargs):
    if not _is_manager_bot_client(self):
        if text is not None:
            text, kwargs = _premium_outgoing_text_payload(text, kwargs)
        elif isinstance(message, str):
            message, kwargs = _premium_outgoing_text_payload(message, kwargs)
    return await _ORIGINAL_CLIENT_EDIT_MESSAGE(self, entity, message, text=text, *args, **kwargs)


TelegramClient.send_message = _premium_client_send_message
TelegramClient.edit_message = _premium_client_edit_message

def _utf16_length(value):
    return len(str(value).encode("utf-16-le")) // 2


def build_damon_welcome_message():
    """ترحيب Damon المطلوب مع رموز عادية احتياطية وكيانات مميزة في مواضع صحيحة."""
    welcome_text = (
        "مرحبًا بك في بوت Damon 👑\n\n"
        "أزرار التحكم بالأسفل 👇:"
    )
    custom_icons = {
        # نفس إيموجي Nardouv الحصري، مع رمز 👑 عادي كبديل في العملاء غير الداعمة.
        "👑": OWNER_PREMIUM_EMOJI_ID,
        "👇": 5470177992950946662,
    }
    entities = []
    cursor = 0
    for char in welcome_text:
        char_length = _utf16_length(char)
        if char in custom_icons:
            entities.append(MessageEntityCustomEmoji(
                offset=cursor,
                length=char_length,
                document_id=custom_icons[char],
            ))
        cursor += char_length
    return welcome_text, entities


def prepare_premium_command_message(message):
    """يضيف إيموجي مميزاً في نهاية النص العربي ليظهر بصرياً على اليسار."""
    if not isinstance(message, str) or not message.strip():
        return message, None
    raw = message
    symbol, emoji_id = _premium_icon_for_text(raw)
    if not emoji_id:
        normalized = raw.lstrip()
        if any(token in normalized for token in ("جاري التحميل", "تم تحميل", "تحميل")):
            symbol, emoji_id = "📥", PREMIUM_EMOJI_IDS["📥"]
        elif any(token in normalized for token in ("جاري البحث", "بحث", "جاري فهم")):
            symbol, emoji_id = "🔍", PREMIUM_EMOJI_IDS["🔍"]
        elif any(token in normalized for token in ("جاري توليد", "الفويس", "الصوت")):
            symbol, emoji_id = "🎙", PREMIUM_EMOJI_IDS["🎙"]
        elif any(token in normalized for token in ("جاري التفكير", "الذكاء الاصطناعي")):
            symbol, emoji_id = "🤖", PREMIUM_EMOJI_IDS["🤖"]
        elif any(token in normalized for token in ("تم ", "بنجاح")):
            symbol, emoji_id = "✅", PREMIUM_EMOJI_IDS["✅"]
        elif any(token in normalized for token in ("تعذر", "فشل", "خطأ", "غير صالح")):
            symbol, emoji_id = "❌", PREMIUM_EMOJI_IDS["❌"]
        elif any(token in normalized for token in ("تحذير", "انتبه")):
            symbol, emoji_id = "❌", PREMIUM_EMOJI_IDS["❌"]
    if not emoji_id:
        # تغطية شاملة للردود اليدوية التي لا تملك كلمة مفتاحية معروفة.
        symbol, emoji_id = PREMIUM_DEFAULT_SYMBOL, PREMIUM_DEFAULT_ICON_ID

    # نحذف الإيموجي العادي من بداية النص ثم نضع أساس الإيموجي في النهاية؛ entity يحوله إلى مميز.
    clean = _strip_leading_ui_symbol(raw, symbol)
    try:
        from telethon.extensions import markdown
        parsed_text, entities = markdown.parse(clean)
    except Exception:
        parsed_text, entities = clean, []
    decorated = f"{parsed_text} {symbol}"
    entities = list(entities or [])
    entities.append(MessageEntityCustomEmoji(
        offset=_utf16_length(parsed_text + " "),
        length=_utf16_length(symbol),
        document_id=emoji_id,
    ))
    return decorated, entities

# ==================== Configuration ====================
API_ID = 39686732
API_HASH = "4ccd261405e1fe78120b5e0a0efe48a7"
BOT_TOKEN = "8617294862:AAEP0kl5B6DfSic5KZMCE1avY4JgRndK_F8"

# آيدي بوت الإدارة لمنع التداخل (تم وضعه هنا)
manager_bot_id = [8617294862] 

# قائمة المسؤولين (المطور الأساسي)
ADMIN_IDS = [520859814]

# رابط المطور وقناة البوت
DEV_URL = "https://t.me/Nardouv"
CHANNEL_URL = "https://t.me/PabloBot666"
DEVELOPERS = [{"username": "Nardouv", "display_name": "Nardouv"}]

# ملفات البيانات والجلسات. عيّن PERSISTENT_DATA_DIR لمسار القرص الدائم في السيرفر.
# إذا لم يضبط المتغير، تعمل الملفات محلياً في مجلد المشروع كالمعتاد.
PERSISTENT_DIR = os.path.abspath(os.getenv("PERSISTENT_DATA_DIR", "."))
os.makedirs(PERSISTENT_DIR, exist_ok=True)
DATA_FILE = os.path.join(PERSISTENT_DIR, "bot_data.json")
VOICES_DIR = os.path.join(PERSISTENT_DIR, "voices")
SESSIONS_DIR = os.path.join(PERSISTENT_DIR, "sessions")
TEMP_DIR = os.path.join(PERSISTENT_DIR, "temp_media")
# ملفات النسخ تبقى في مجلد مستقل حتى لا تدخل النسخة داخل نفسها عند ضغط الوسائط.
BACKUP_DIR = os.path.join(PERSISTENT_DIR, "backups")

for _directory in (VOICES_DIR, SESSIONS_DIR, TEMP_DIR, BACKUP_DIR):
    os.makedirs(_directory, exist_ok=True)

# خريطة السرعة بالثواني
SPEED_MAP = {
    "0.5": 0.5,
    "1": 1.0,
    "2": 2.0,
    "3": 3.0,
    "4": 4.0,
    "5": 5.0,
    "6": 6.0,
    "7": 7.0,
    "8": 8.0,
    "9": 9.0,
    "10": 10.0
}

# قواعد البيانات في الذاكرة والتخزين المؤقت للبحث
activation_codes = {}
source_activation_codes = {}
all_activation_codes = {}
activation_log = []
admin_error_log = []
expired_code_history = []
users_db = {}
user_clients = {}
user_states = {}
search_cache = {}
hybrid_download_cache = {}
_gemini_hybrid_unavailable_until = 0.0

# القوائم الأساسية العامة (تدار عبر لوحة الأدمن وتنعكس للجميع)
default_tastir = []
default_fardiyyat = []
default_reply = []

# المهام النشطة
running_tasks = {}
# رموز مؤقتة لعرض تفاصيل عمليات قسم التسطير عبر الأزرار التفاعلية.
tastir_operation_views = {}
auto_publish_tasks = {}
auto_publish_meta = {}
broadcast_tasks = {}
calculator_sessions = {}
publish_stop_reasons = {}
manual_flush_tasks = {}
# مهام التفليش التي تبدأ من زر البوت؛ تستخدم لإيقاف العملية من الزر نفسه.
bot_flush_tasks = {}
storage_notice_cache = {}
# آخر مصدر أرسل بطاقة تنبيه لكل حساب؛ تتغير البطاقة فقط عند الانتقال لمصدر مختلف.
storage_active_sources = {}
# تخزين مؤقت خفيف لتقليل طلبات الشبكة والقرص المتكررة، من دون تغيير الميزات.
_user_me_cache = {}
_translation_cache = {}
_pending_save_handle = None

# جلسة مستقلة للبوت؛ تمنع استخدام جلسة حساب شخصي قديمة بدل بوت الإدارة.
bot = TelegramClient("manager_bot_8617294862", API_ID, API_HASH)

# المالك الرئيسي ثابت ولا يمكن أن يفقد صلاحية إدارة البوت من البيانات المحفوظة.
OWNER_ID = 520859814
RESPONSIBLE_IDS = []
navigation_history = {}


def is_owner(user_id):
    return int(user_id) == OWNER_ID


def is_responsible(user_id):
    return int(user_id) in RESPONSIBLE_IDS


def is_staff(user_id):
    return is_owner(user_id) or is_responsible(user_id) or int(user_id) in ADMIN_IDS


def track_menu_navigation(user_id, callback_data):
    """يحفظ المسار الحالي للقوائم ليتوافق الرجوع مع القسم السابق."""
    menu_callbacks = {
        b"main_menu", b"tastir_section", b"tastir_menu", b"fardiyyat_menu", b"reply_menu", b"nick_am_menu", b"speed_menu",
        b"source_features_menu", b"flush_section", b"flush_menu", b"mute_menu", b"voice_menu", b"clone_menu", b"welcome_menu",
        b"auto_publish_menu", b"conversion_menu", b"id_menu", b"ai_main_menu", b"ai_chat_help", b"ai_voices_help", b"admin_menu", b"admin_users_menu", b"admin_admins_menu",
        b"admin_words_menu", b"admin_codes_menu", b"admin_data_menu", b"admin_tastir_menu", b"admin_fardiyyat_menu",
    }
    if callback_data == b"main_menu":
        return
    if callback_data not in menu_callbacks:
        return
    stack = navigation_history.setdefault(int(user_id), [])
    if callback_data in stack:
        while stack and stack[-1] != callback_data:
            stack.pop()
    else:
        stack.append(callback_data)
    del stack[:-16]


OWNER_ONLY_CALLBACKS = {
    b"add_admin_start", b"delete_admin_start",
    b"backup_export", b"backup_import_start", b"sessions_menu", b"session_disconnect_start",
    b"admin_error_log_menu", b"admin_error_log_clear", b"change_channel_start",
    b"manage_developers_menu", b"add_developer_start", b"add_responsible_start", b"delete_responsible_start",
    b"list_admins",
}



def normalize_telegram_username(value):
    raw = str(value or "").strip()
    raw = raw.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "")
    username = raw.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        return None
    return username


def developer_url(item):
    username = normalize_telegram_username(item.get("username", "")) if isinstance(item, dict) else None
    return f"https://t.me/{username}" if username else DEV_URL


def developer_display_name(item):
    """يعرض اسم الحساب الذي اختاره صاحبه، مع بديل اليوزر عند غياب الاسم."""
    if not isinstance(item, dict):
        return str(item or "المطور")
    name = str(item.get("display_name", "")).strip()
    if name:
        return name[:64]
    username = str(item.get("username", "")).strip().lstrip("@")
    return username or "المطور"


async def resolve_developer_display_name(username):
    """يجلب الاسم الظاهر مرة عند الإضافة أو التغيير، ثم يحفظه للعرض السريع لاحقاً."""
    fallback = str(username or "").strip().lstrip("@") or "المطور"
    try:
        entity = await bot.get_entity(f"@{fallback}")
        first_name = str(getattr(entity, "first_name", "") or "").strip()
        last_name = str(getattr(entity, "last_name", "") or "").strip()
        title = str(getattr(entity, "title", "") or "").strip()
        full_name = " ".join(part for part in (first_name, last_name) if part).strip()
        return (full_name or title or fallback)[:64]
    except Exception:
        return fallback[:64]


def developer_main_buttons():
    """يرتب أزرار الاتصال بأسماء الحسابات؛ Nardouv يحتفظ بملصقه المميز."""
    visible = DEVELOPERS[:3] or [{"username": "Nardouv", "display_name": "Nardouv"}]
    owner_name = developer_display_name(visible[0]) or "Nardouv"
    owner_button = Button.url(owner_name, developer_url(visible[0]), icon=OWNER_PREMIUM_EMOJI_ID)
    channel_button = Button.url("📢 قناة البوت", CHANNEL_URL)
    if len(visible) == 1:
        return [[channel_button, owner_button]]

    rows = [[owner_button, Button.url(developer_display_name(visible[1]), developer_url(visible[1]))]]
    if len(visible) >= 3:
        rows.append([Button.url(developer_display_name(visible[2]), developer_url(visible[2]))])
    rows.append([channel_button])
    return rows


# ==================== Persistence Functions ====================
def _build_data_snapshot():
    return {
        "default_tastir": default_tastir,
        "default_fardiyyat": default_fardiyyat,
        "default_reply": default_reply,
        "users_db": users_db,
        "activation_codes": activation_codes,
        "source_activation_codes": source_activation_codes,
        "all_activation_codes": all_activation_codes,
        "activation_log": activation_log[-500:],
        "admin_error_log": admin_error_log[-200:],
        "expired_code_history": expired_code_history[-500:],
        "admin_ids": ADMIN_IDS,
        "responsible_ids": RESPONSIBLE_IDS,
        "channel_url": CHANNEL_URL,
        "developers": DEVELOPERS
    }


def _write_data_snapshot():
    """كتابة ذرية سريعة: لا توقف الأمر عند تعدد تعديلات صغيرة متقاربة."""
    try:
        os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
        temp_path = DATA_FILE + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(_build_data_snapshot(), f, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp_path, DATA_FILE)
    except Exception as e:
        print(f"Error saving data: {e}")


def _flush_scheduled_save():
    global _pending_save_handle
    _pending_save_handle = None
    _write_data_snapshot()


def save_data(force=False):
    """يجمع عمليات الحفظ المتقاربة لمدة قصيرة كي لا تعطل استجابة الأوامر."""
    global _pending_save_handle
    if force:
        if _pending_save_handle:
            try:
                _pending_save_handle.cancel()
            except Exception:
                pass
            _pending_save_handle = None
        _write_data_snapshot()
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _write_data_snapshot()
        return
    if _pending_save_handle and not _pending_save_handle.cancelled():
        return
    _pending_save_handle = loop.call_later(0.20, _flush_scheduled_save)

def load_data():
    global default_tastir, default_fardiyyat, default_reply, users_db, activation_codes, source_activation_codes, all_activation_codes, activation_log, admin_error_log, expired_code_history, ADMIN_IDS, RESPONSIBLE_IDS, CHANNEL_URL, DEV_URL, DEVELOPERS
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_tastir = data.get("default_tastir", [])
                default_fardiyyat = data.get("default_fardiyyat", [])
                default_reply = data.get("default_reply", [])
                raw_users = data.get("users_db", {})
                users_db = {int(k): v for k, v in raw_users.items()}
                activation_codes = data.get("activation_codes", {})
                source_activation_codes = data.get("source_activation_codes", {})
                all_activation_codes = data.get("all_activation_codes", {})
                activation_log = data.get("activation_log", [])
                admin_error_log = data.get("admin_error_log", [])
                expired_code_history = data.get("expired_code_history", [])
                loaded_admins = data.get("admin_ids", None)
                if loaded_admins:
                    ADMIN_IDS = [int(a) for a in loaded_admins]
                RESPONSIBLE_IDS = [int(value) for value in data.get("responsible_ids", []) if str(value).lstrip("-").isdigit()]
                saved_channel = str(data.get("channel_url", "")).strip()
                if saved_channel.startswith(("https://t.me/", "http://t.me/")):
                    CHANNEL_URL = saved_channel
                saved_developers = data.get("developers", [])
                if isinstance(saved_developers, list):
                    normalized_developers = []
                    for item in saved_developers:
                        username = normalize_telegram_username(item.get("username", "") if isinstance(item, dict) else item)
                        display_name = str(item.get("display_name", "") if isinstance(item, dict) else "").strip()
                        if username and username.lower() not in [entry["username"].lower() for entry in normalized_developers]:
                            normalized_developers.append({"username": username, "display_name": (display_name or username)[:64]})
                    if normalized_developers:
                        DEVELOPERS = normalized_developers
                        DEV_URL = developer_url(DEVELOPERS[0])
        except Exception as e:
            print(f"Error loading data: {e}")

load_data()

# ==================== Helper Functions ====================
def is_subscribed(user_id):
    if is_staff(user_id):
        return True
    user_info = users_db.get(user_id)
    if not user_info:
        return False
    return time.time() < user_info.get("expires_at", 0)

def is_source_subscribed(user_id):
    if is_staff(user_id):
        return True
    user_info = users_db.get(user_id)
    if not user_info:
        return False
    return time.time() < user_info.get("source_expires_at", 0)


def has_any_subscription(user_id):
    return is_subscribed(user_id) or is_source_subscribed(user_id)


def _append_activation_log(action, user_id, admin_id=None, days=0, tastir=False, source=False, note=""):
    activation_log.append({
        "time": int(time.time()), "action": action, "user_id": int(user_id),
        "admin_id": int(admin_id) if admin_id else None, "days": int(days),
        "tastir": bool(tastir), "source": bool(source), "note": note
    })
    del activation_log[:-500]


def _pop_activation_code_details(code_store, code):
    """يدعم الأكواد القديمة التي قيمتها عدد أيام، والجديدة التي تحفظ منشئ الكود."""
    if code not in code_store:
        return None
    raw = code_store.pop(code)
    if isinstance(raw, dict):
        return int(raw.get("days", 0)), raw.get("created_by")
    return int(raw), None


async def _issuer_details_text(admin_id):
    if not admin_id:
        return "غير مسجل (كود قديم)"
    try:
        return await format_user_details(int(admin_id))
    except Exception:
        return f"• الاسم: مسؤول\n• الآيدي: `{admin_id}`\n• اليوزر: ماعنده"


async def apply_any_activation_code(user_id, code, event):
    """يحاول التسطير ثم السورس ثم جميع الصلاحيات ويعيد نوع الاشتراك."""
    success, days = await apply_activation_code(user_id, code, event)
    if success:
        return "tastir", days
    success, days = await apply_source_activation_code(user_id, code, event)
    if success:
        return "source", days
    success, days = await apply_full_activation_code(user_id, code, event)
    if success:
        return "all", days
    return None, 0


def _subscription_state(user_id):
    info = users_db.get(user_id, {})
    now = time.time()
    return now < info.get("expires_at", 0), now < info.get("source_expires_at", 0)


# ==================== Admin Backup, Sessions & Error Log ====================
def _backup_file_path(prefix="backup"):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(TEMP_DIR, f"{prefix}_{stamp}.json")


def create_settings_backup():
    """نسخة خفيفة متوافقة مع النسخ القديمة من الإعدادات فقط."""
    save_data(force=True)
    output = _backup_file_path("demon_backup")
    shutil.copy2(DATA_FILE, output)
    return output


def _archive_directory(archive, directory, prefix, excluded_paths=None):
    """يضيف ملفات مجلد إلى ZIP مع استثناء ملفات النسخ نفسها."""
    excluded_paths = {os.path.abspath(item) for item in (excluded_paths or [])}
    if not os.path.isdir(directory):
        return
    for root, _, files in os.walk(directory):
        for filename in files:
            source_path = os.path.abspath(os.path.join(root, filename))
            if source_path in excluded_paths:
                continue
            relative_path = os.path.relpath(source_path, directory)
            archive.write(source_path, os.path.join(prefix, relative_path))


def create_full_backup():
    """ينشئ ملف ZIP واحداً للبيانات والجلسات والوسائط المحلية المحفوظة."""
    save_data(force=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    output = os.path.join(BACKUP_DIR, f"demon_full_backup_{stamp}.zip")
    manifest = {
        "format": "demon_full_backup",
        "version": 1,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "includes": ["bot_data.json", "sessions", "voices", "temp_media"],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if os.path.exists(DATA_FILE):
            archive.write(DATA_FILE, "bot_data.json")
        _archive_directory(archive, SESSIONS_DIR, "sessions")
        _archive_directory(archive, VOICES_DIR, "voices")
        _archive_directory(archive, TEMP_DIR, "temp_media")
    return output


def _safe_extract_full_backup(archive_path):
    """يتحقق من ملف النسخة ثم يعيد ملفاتها إلى مجلد التخزين الدائم بأمان."""
    allowed_roots = {"bot_data.json", "backup_manifest.json", "sessions", "voices", "temp_media"}
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        if "bot_data.json" not in names:
            raise ValueError("ملف النسخة الموسعة لا يحتوي بيانات البوت.")
        try:
            imported_data = json.loads(archive.read("bot_data.json").decode("utf-8"))
        except Exception as exc:
            raise ValueError("تعذر قراءة بيانات النسخة الموسعة.") from exc
        if not isinstance(imported_data, dict) or "users_db" not in imported_data:
            raise ValueError("بيانات النسخة الموسعة غير صالحة.")

        members = []
        base = os.path.abspath(PERSISTENT_DIR)
        for info in archive.infolist():
            name = info.filename.replace("\\", "/").lstrip("/")
            if not name or name.endswith("/"):
                continue
            root = name.split("/", 1)[0]
            if root not in allowed_roots:
                raise ValueError("ملف النسخة يحتوي مساراً غير مسموح.")
            destination = os.path.abspath(os.path.join(PERSISTENT_DIR, name))
            if os.path.commonpath([base, destination]) != base:
                raise ValueError("ملف النسخة يحتوي مساراً غير آمن.")
            members.append((info, destination))

        # إزالة الملفات السابقة قبل الاستعادة حتى لا تبقى جلسات أو وسائط قديمة غير موجودة في النسخة.
        for directory in (SESSIONS_DIR, VOICES_DIR, TEMP_DIR):
            shutil.rmtree(directory, ignore_errors=True)
            os.makedirs(directory, exist_ok=True)
        if os.path.exists(DATA_FILE):
            _safe_remove(DATA_FILE)

        for info, destination in members:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with archive.open(info, "r") as source, open(destination, "wb") as target:
                shutil.copyfileobj(source, target)
    return imported_data


def _rebase_restored_media_paths():
    """تجعل مسارات الوسائط في البيانات صالحة بعد نقل النسخة إلى جهاز أو سيرفر آخر."""
    def rebase(value, base_dir):
        if not value:
            return value
        return os.path.join(base_dir, os.path.basename(str(value)))

    for info in users_db.values():
        if not isinstance(info, dict):
            continue
        if info.get("welcome_photo"):
            info["welcome_photo"] = rebase(info["welcome_photo"], TEMP_DIR)
        profile_backup = info.get("profile_backup")
        if isinstance(profile_backup, dict) and profile_backup.get("photo_path"):
            profile_backup["photo_path"] = rebase(profile_backup["photo_path"], TEMP_DIR)
        voices = info.get("voices")
        if isinstance(voices, dict):
            for number, path in list(voices.items()):
                voices[number] = rebase(path, VOICES_DIR)


async def disconnect_user_session_only(user_id, reason="فصل من لوحة الأدمن"):
    """يفصل جلسة الحساب ومهامه دون حذف اشتراك المستخدم أو بياناته."""
    stop_running_task(user_id)
    client = user_clients.pop(user_id, None)
    await stop_auto_publish_task(client, user_id, reason=reason)
    for key, task in list(broadcast_tasks.items()):
        if key == user_id and task and not task.done():
            task.cancel()
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    for suffix in (".session", ".session-journal", ".session-wal", ".session-shm"):
        _safe_remove(f"{SESSIONS_DIR}/user_{user_id}{suffix}")
    _append_activation_log("فصل_جلسة", user_id, note=reason)
    save_data()


def list_saved_session_ids():
    ids = set()
    for item in Path(SESSIONS_DIR).glob("user_*.session"):
        match = re.fullmatch(r"user_(\d+)\.session", item.name)
        if match:
            ids.add(int(match.group(1)))
    return sorted(ids)


async def report_admin_error(operation, error, user_id=None, chat_id=None):
    """يسجل ويرسل للأدمن أخطاء الدخول أو الأكواد فقط، مع بيانات المستخدم كاملة."""
    operation_text = str(operation)
    allowed_words = ("تسجيل الدخول", "تفعيل", "كود", "رمز")
    if not any(word in operation_text for word in allowed_words):
        print(f"[غير مسجل للأدمن] {operation_text}: {error}")
        return
    entry = {
        "time": int(time.time()),
        "operation": operation_text,
        "error": str(error)[:1200],
        "user_id": int(user_id) if user_id is not None else None,
        "chat_id": str(chat_id) if chat_id is not None else None,
    }
    admin_error_log.append(entry)
    del admin_error_log[:-200]
    name = "غير محدد"
    username = "ماعنده"
    if user_id is not None:
        try:
            entity = await bot.get_entity(user_id)
            name = f"{getattr(entity, 'first_name', '') or ''} {getattr(entity, 'last_name', '') or ''}".strip() or "بدون اسم"
            username = f"@{entity.username}" if getattr(entity, "username", None) else "ماعنده"
        except Exception:
            stored = users_db.get(int(user_id), {})
            name = stored.get("display_name", name)
            username = stored.get("display_username", username)
    entry["name"] = name
    entry["username"] = username
    save_data()
    details = (
        "⚠️ **سجل دخول أو تفعيل**\n\n"
        f"• العملية: `{entry['operation']}`\n"
        f"• الاسم: {name}\n"
        f"• الآيدي: `{entry['user_id'] or 'غير محدد'}`\n"
        f"• اليوزر: {username}\n"
        f"• السبب: `{entry['error']}`"
    )
    for admin_id in list(ADMIN_IDS):
        try:
            await bot.send_message(admin_id, details)
        except Exception:
            pass



def _remember_user_identity(user_id, sender):
    if user_id not in users_db:
        return
    users_db[user_id]["display_name"] = f"{getattr(sender, 'first_name', '') or ''} {getattr(sender, 'last_name', '') or ''}".strip() or "مستخدم"
    users_db[user_id]["display_username"] = f"@{sender.username}" if getattr(sender, "username", None) else "ماعنده"


def _remember_expired_code_user(user_id, info, subscription_type="جميع الاشتراكات"):
    expired_code_history.append({
        "time": int(time.time()),
        "user_id": int(user_id),
        "name": info.get("display_name", "مستخدم"),
        "username": info.get("display_username", "ماعنده"),
        "subscription_type": subscription_type,
        "tastir_expired_at": int(info.get("expires_at", 0)),
        "source_expired_at": int(info.get("source_expires_at", 0)),
    })
    del expired_code_history[:-500]


async def remove_user_completely(user_id, reason="حذف"):
    """يحذف المستخدم المنتهي/الملغى من القائمة ويفصل جلسة حسابه ومهامه."""
    if is_staff(user_id):
        return False
    stop_running_task(user_id)
    client = user_clients.pop(user_id, None)
    await stop_auto_publish_task(client, user_id, reason="تم إيقاف النشر بسبب انتهاء أو حذف الاشتراك")
    for key, task in list(broadcast_tasks.items()):
        if key == user_id and task and not task.done():
            task.cancel()
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    for suffix in (".session", ".session-journal", ".session-wal", ".session-shm"):
        _safe_remove(f"{SESSIONS_DIR}/user_{user_id}{suffix}")
    old_info = users_db.get(user_id, {})
    if "انتهاء" in reason and not old_info.get("expired_code_logged"):
        _remember_expired_code_user(user_id, old_info)
    users_db.pop(user_id, None)
    user_states.pop(user_id, None)
    _append_activation_log("حذف_مستخدم", user_id, note=reason)
    save_data()
    return True


async def subscription_maintenance_loop():
    """تنبيه قبل 24 ساعة وحذف المستخدم بعد انتهاء اشتراكيه."""
    while True:
        changed = False
        now = time.time()
        for uid, info in list(users_db.items()):
            if uid in ADMIN_IDS:
                continue
            t_exp = info.get("expires_at", 0)
            s_exp = info.get("source_expires_at", 0)
            notices = info.setdefault("expiry_notices", {})
            for kind, exp, title in (("tastir", t_exp, "اشتراك التسطير"), ("source", s_exp, "اشتراك مميزات السورس")):
                if now < exp <= now + 86400 and not notices.get(kind):
                    try:
                        await bot.send_message(uid, f"⚠️ تنبيه: {title} ينتهي خلال أقل من 24 ساعة. تواصل مع المطور للتمديد.")
                    except Exception:
                        pass
                    notices[kind] = True
                    changed = True
            # يسجل كل كود منتهٍ مرة واحدة حتى لو بقي الاشتراك الآخر فعالاً.
            expired_logged = info.setdefault("expired_code_logged", {})
            for key, exp, label in (("tastir", t_exp, "التسطير"), ("source", s_exp, "مميزات السورس")):
                if exp > 0 and now >= exp and not expired_logged.get(key):
                    _remember_expired_code_user(uid, info, label)
                    expired_logged[key] = True
                    changed = True
            if now >= t_exp and now >= s_exp:
                try:
                    await bot.send_message(uid, "⌛ انتهت اشتراكاتك وتمت إزالة بياناتك من قائمة البوت. يمكنك العودة بتفعيل كود جديد.")
                except Exception:
                    pass
                await remove_user_completely(uid, "انتهاء الاشتراكين")
                _append_activation_log("انتهاء_اشتراك", uid, note="انتهاء الاشتراكين وحذف البيانات")
                changed = True
        if changed:
            save_data()
        await asyncio.sleep(3600)

def normalize_user_command(command):
    """توحيد الأوامر: يقبل التخزين مع النقطة أو بدونها، والتنفيذ دائماً بعد إزالة النقطة."""
    return str(command or "").strip().lstrip(".").strip()


def normalize_command_list(commands, fallback):
    # نستخدم الافتراضي فقط عند أول إنشاء للحساب، أما القائمة الفارغة فهي اختيار المستخدم ولا نعيد أوامر محذوفة.
    source = fallback if commands is None else commands
    normalized = []
    for command in source:
        clean = normalize_user_command(command)
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized



def init_user_db(user_id):
    if user_id not in users_db:
        users_db[user_id] = {}
    u = users_db[user_id]
    u.setdefault("expires_at", time.time() + (100 * 365 * 86400) if is_staff(user_id) else 0)
    u.setdefault("source_expires_at", time.time() + (100 * 365 * 86400) if is_staff(user_id) else 0)
    u.setdefault("tastir", [])
    u.setdefault("fardiyyat", [])
    u.setdefault("reply", [])
    u.setdefault("nick_am", [])
    u.pop("bot_responses", None)
    u.setdefault("voices", {})
    u.setdefault("include_tastir_in_reply", True)
    u.setdefault("include_fardiyyat_in_reply", True)
    u.setdefault("include_tastir_in_nick_am", True)
    u.setdefault("include_fardiyyat_in_nick_am", True)
    u.setdefault("nick_am_enabled", False)
    u.setdefault("nick_am_reply_enabled", True)
    u.setdefault("tastir_start_cmds", ["تسطير"])
    u.setdefault("tastir_stop_cmds", ["ايقاف التسطير"])
    u.setdefault("fardiyyat_start_cmds", ["فرديات"])
    u.setdefault("fardiyyat_stop_cmds", ["ايقاف الفرديات"])
    u.setdefault("reply_start_cmds", ["ريبلاي"])
    u.setdefault("reply_stop_cmds", ["ايقاف الريبلاي"])
    # تشغيل نيك ام ثابت، بينما أوامر الإيقاف يحددها المستخدم.
    u.pop("nick_am_start_cmds", None)
    u.pop("del_nick_am_start", None)
    u.setdefault("nick_am_stop_cmds", ["ايقاف نيك ام"])
    u.setdefault("mute_cmds", ["اص"])
    u.setdefault("unmute_cmds", ["اتكلم", "إلغاء الكتم", "الغاء الكتم"])
    u.setdefault("purge_cmds", ["مسح"])
    u.setdefault("purge_all_cmds", ["مسح الكل"])
    # تقبل الأوامر القديمة والجديدة سواء حُفظت بالنقطة أم بدونها.
    u["tastir_start_cmds"] = normalize_command_list(u.get("tastir_start_cmds"), ["تسطير"])
    u["tastir_stop_cmds"] = normalize_command_list(u.get("tastir_stop_cmds"), ["ايقاف التسطير"])
    u["fardiyyat_start_cmds"] = normalize_command_list(u.get("fardiyyat_start_cmds"), ["فرديات"])
    u["fardiyyat_stop_cmds"] = normalize_command_list(u.get("fardiyyat_stop_cmds"), ["ايقاف الفرديات"])
    u["reply_start_cmds"] = normalize_command_list(u.get("reply_start_cmds"), ["ريبلاي"])
    u["reply_stop_cmds"] = normalize_command_list(u.get("reply_stop_cmds"), ["ايقاف الريبلاي"])
    u["nick_am_stop_cmds"] = normalize_command_list(u.get("nick_am_stop_cmds"), ["ايقاف نيك ام"])
    u.setdefault("del_tastir_start", True)
    u.setdefault("del_tastir_stop", True)
    u.setdefault("del_fardiyyat_start", True)
    u.setdefault("del_fardiyyat_stop", True)
    u.setdefault("del_reply_start", True)
    u.setdefault("del_reply_stop", True)
    u.setdefault("del_nick_am_stop", True)
    u.setdefault("del_mute_cmd", True)
    u.setdefault("del_unmute_cmd", True)
    u.setdefault("del_voice_cmd", True)
    u.setdefault("muted_users", [])
    u.setdefault("speed", 1.0)
    u.setdefault("storage_groups", [])
    u.setdefault("welcome_enabled", False)
    u.setdefault("welcome_text", "أهلاً بك، نورت الخاص.")
    u.setdefault("welcome_photo", None)
    u.setdefault("welcomed_private_ids", [])
    u.setdefault("smart_replies_enabled", False)
    u.setdefault("profile_backup", None)
    u.setdefault("profile_history", [])
    u.setdefault("username_history", [])
    u.setdefault("self_save_enabled", False)
    u.setdefault("self_save_chat_id", None)
    # اشتراكات القنوات/القروبات المطلوبة قبل النشر، ومهام النشر التي تستأنف بعد إعادة التشغيل.
    u.setdefault("auto_publish_jobs", [])
    save_data()

def get_next_voice_number(user_id):
    user_voices = users_db.get(user_id, {}).get("voices", {})
    existing_nums = sorted([int(k) for k in user_voices.keys() if k.isdigit()])
    expected = 1
    for num in existing_nums:
        if num == expected:
            expected += 1
        elif num > expected:
            return str(expected)
    return str(expected)

def check_cmd_exists(user_id, cmd):
    u = users_db.get(user_id, {})
    all_start_cmds = (
        u.get("tastir_start_cmds", []) +
        u.get("fardiyyat_start_cmds", []) +
        u.get("reply_start_cmds", []) +
        u.get("mute_cmds", []) +
        u.get("unmute_cmds", []) +
        u.get("purge_cmds", []) +
        u.get("purge_all_cmds", [])
    )
    return cmd in all_start_cmds

async def format_user_details(user_id):
    stored = users_db.get(int(user_id), {})
    try:
        entity = await bot.get_entity(user_id)
        first_name = entity.first_name or "بدون اسم"
        last_name = f" {entity.last_name}" if entity.last_name else ""
        full_name = f"{first_name}{last_name}".strip()
        username = f"@{entity.username}" if entity.username else "ماعنده"
    except Exception:
        full_name = stored.get("display_name", "مستخدم")
        username = stored.get("display_username", "ماعنده")

    profile_link = f"[{full_name}](tg://openmessage?user_id={user_id})"
    return f"• الاسم: {profile_link}\n• الآيدي: `{user_id}`\n• اليوزر: {username}"

async def apply_activation_code(user_id, code, event):
    details = _pop_activation_code_details(activation_codes, code)
    if not details:
        return False, 0
    days, issuer_id = details
    init_user_db(user_id)
    current_exp = max(time.time(), users_db[user_id]["expires_at"])
    users_db[user_id]["expires_at"] = current_exp + (days * 86400)
    users_db[user_id].pop("expiry_notices", None)
    sender = await event.get_sender()
    _remember_user_identity(user_id, sender)
    _append_activation_log("تفعيل_كود_تسطير", user_id, admin_id=issuer_id, days=days, tastir=True, note=f"الكود: {code}")
    save_data()
    username = f"@{sender.username}" if sender and sender.username else "ماعنده"
    first_name = sender.first_name if sender and sender.first_name else "مستخدم"
    user_link = f"[{first_name}](tg://openmessage?user_id={user_id})"
    issuer_text = await _issuer_details_text(issuer_id)
    notify_txt = (
        "📩 إشعار اشتراك جديد:\n\n"
        f"• المستخدم: {user_link}\n"
        f"• الآيدي: `{user_id}`\n"
        f"• اليوزر: {username}\n"
        f"• مدة الاشتراك: {days} يوم\n"
        f"• رمز التفعيل: `{code}`\n\n"
        f"👑 **منشئ الكود:**\n{issuer_text}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notify_txt, link_preview=False)
        except Exception:
            pass
    return True, days

async def apply_source_activation_code(user_id, code, event):
    details = _pop_activation_code_details(source_activation_codes, code)
    if not details:
        return False, 0
    days, issuer_id = details
    init_user_db(user_id)
    current_exp = max(time.time(), users_db[user_id].get("source_expires_at", 0))
    users_db[user_id]["source_expires_at"] = current_exp + (days * 86400)
    users_db[user_id].pop("expiry_notices", None)
    sender = await event.get_sender()
    _remember_user_identity(user_id, sender)
    _append_activation_log("تفعيل_كود_سورس", user_id, admin_id=issuer_id, days=days, source=True, note=f"الكود: {code}")
    save_data()
    username = f"@{sender.username}" if sender and sender.username else "ماعنده"
    first_name = sender.first_name if sender and sender.first_name else "مستخدم"
    user_link = f"[{first_name}](tg://openmessage?user_id={user_id})"
    issuer_text = await _issuer_details_text(issuer_id)
    notify_txt = (
        "📩 إشعار تفعيل مميزات السورس جديد:\n\n"
        f"• المستخدم: {user_link}\n"
        f"• الآيدي: `{user_id}`\n"
        f"• اليوزر: {username}\n"
        f"• مدة الاشتراك: {days} يوم\n"
        f"• رمز تفعيل السورس: `{code}`\n\n"
        f"👑 **منشئ الكود:**\n{issuer_text}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notify_txt, link_preview=False)
        except Exception:
            pass
    return True, days

async def apply_full_activation_code(user_id, code, event):
    details = _pop_activation_code_details(all_activation_codes, code)
    if not details:
        return False, 0
    days, issuer_id = details
    init_user_db(user_id)
    now = time.time()
    users_db[user_id]["expires_at"] = max(now, users_db[user_id].get("expires_at", 0)) + days * 86400
    users_db[user_id]["source_expires_at"] = max(now, users_db[user_id].get("source_expires_at", 0)) + days * 86400
    users_db[user_id].pop("expiry_notices", None)
    sender = await event.get_sender()
    _remember_user_identity(user_id, sender)
    _append_activation_log("تفعيل_كود_جميع_الصلاحيات", user_id, admin_id=issuer_id, days=days, tastir=True, source=True, note=f"الكود: {code}")
    save_data()
    name = users_db[user_id].get("display_name", "مستخدم")
    username = users_db[user_id].get("display_username", "ماعنده")
    issuer_text = await _issuer_details_text(issuer_id)
    notice = (
        "📩 **تفعيل جميع الصلاحيات**\n\n"
        f"• الاسم: {name}\n"
        f"• الآيدي: `{user_id}`\n"
        f"• اليوزر: {username}\n"
        f"• المدة: `{days}` يوم\n"
        f"• الكود: `{code}`\n\n"
        f"👑 **منشئ الكود:**\n{issuer_text}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notice, link_preview=False)
        except Exception:
            pass
    return True, days


async def resolve_hybrid_download_request(raw_request, default_audio=False):
    """يفهم Gemini طلب الوسائط عند توافره، ثم يعيد استعلاماً آمناً لـ yt-dlp.

    لا يتعامل Gemini مع تنزيل الملفات؛ دوره يقتصر على فهم عبارة البحث. عند انتهاء حصته
    أو حدوث أي خطأ نعود فوراً للاستعلام الأصلي، كي لا يتعطل التحميل المعتاد.
    """
    global _gemini_hybrid_unavailable_until

    request_text = " ".join(str(raw_request or "").split()).strip()
    if not request_text:
        raise ValueError("اكتب اسم المقطع أو أرسل رابطاً صحيحاً.")

    # الرابط المباشر لا يحتاج ذكاءً اصطناعياً ولا نضيف له أي زمن انتظار.
    if re.match(r"^(?:https?://|www\.)", request_text, flags=re.IGNORECASE):
        return {
            "search_query": request_text,
            "audio_only": bool(default_audio),
            "is_direct_url": True,
            "used_gemini": False,
        }

    cache_key = f"{int(bool(default_audio))}:{request_text.casefold()}"
    cached = hybrid_download_cache.get(cache_key)
    if cached and cached.get("expires_at", 0) > time.monotonic():
        return dict(cached["plan"])

    fallback = {
        "search_query": request_text[:240],
        "audio_only": bool(default_audio),
        "is_direct_url": False,
        "used_gemini": False,
    }

    # دائرة حماية: إذا أعادت الخدمة 429 لا نعلق كل طلب جديد بانتظار Gemini.
    if time.monotonic() < _gemini_hybrid_unavailable_until:
        return fallback

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return fallback

    prompt = (
        "حوّل طلب المستخدم إلى استعلام قصير ودقيق للبحث عن مقطع واحد في YouTube. "
        "أعد JSON فقط من دون Markdown بالشكل: "
        '{"query":"عنوان مناسب للبحث","audio_only":true أو false}. '
        "اجعل audio_only=true فقط إذا طلب المستخدم أغنية أو صوتاً أو mp3 أو نطقاً؛ "
        f"القيمة الافتراضية للصوت هي {str(bool(default_audio)).lower()}. "
        f"طلب المستخدم: {request_text}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.15, "maxOutputTokens": 180},
    }
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"

    def _request():
        return requests.post(url, params={"key": api_key}, json=payload, timeout=10)

    try:
        response = await asyncio.to_thread(_request)
        if response.status_code == 200:
            candidates = response.json().get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            answer = "".join(str(part.get("text", "")) for part in parts).strip()
            match = re.search(r"\{.*\}", answer, flags=re.DOTALL)
            parsed = json.loads(match.group(0) if match else answer)
            query = " ".join(str(parsed.get("query", "")).split()).strip()[:240]
            if query:
                plan = {
                    "search_query": query,
                    "audio_only": bool(parsed.get("audio_only", default_audio)),
                    "is_direct_url": False,
                    "used_gemini": True,
                }
                hybrid_download_cache[cache_key] = {
                    "plan": dict(plan),
                    "expires_at": time.monotonic() + 900,
                }
                if len(hybrid_download_cache) > 120:
                    hybrid_download_cache.pop(next(iter(hybrid_download_cache)), None)
                return plan
        elif response.status_code == 429:
            # خمس دقائق من المسار العادي تمنع بطء المستخدم عند انتهاء حصة Gemini.
            _gemini_hybrid_unavailable_until = time.monotonic() + 300
        else:
            print(f"[HYBRID GEMINI ERROR] HTTP {response.status_code}")
    except Exception as exc:
        print(f"[HYBRID GEMINI ERROR] {exc}")

    return fallback


async def hybrid_ytdlp_download(raw_request, default_audio=False):
    """Gemini للفهم والبحث، وyt-dlp للتنزيل الحقيقي للملف."""
    plan = await resolve_hybrid_download_request(raw_request, default_audio=default_audio)
    # أمر «يوت» مخصص للصوت دائماً؛ لا نسمح لمفسر الاستعلام بتحويله إلى فيديو.
    if default_audio:
        plan["audio_only"] = True
    target = plan["search_query"] if plan["is_direct_url"] else f"ytsearch1:{plan['search_query']}"
    media_path, info = await _ytdlp_download(target, audio_only=plan["audio_only"])
    return media_path, info, plan


def format_media_duration(seconds):
    """يعرض مدة الوسيط بصيغة واضحة للنتائج."""
    try:
        total = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        return "غير معروفة"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def result_channel_name(video_info):
    """يعيد أفضل اسم قناة متاح من بيانات yt-dlp."""
    return (
        video_info.get("channel")
        or video_info.get("uploader")
        or video_info.get("creator")
        or video_info.get("uploader_id")
        or "قناة يوتيوب"
    )


async def search_and_download_youtube(query):
    cache_key = " ".join(str(query or "").strip().casefold().split())

    def build_result(video_info):
        if not video_info:
            return None, None, None, None, None
        vid = video_info.get("id")
        title = (video_info.get("title") or "مقطع بدون عنوان").strip()
        duration = int(video_info.get("duration") or 0)
        channel = result_channel_name(video_info)
        file_path = os.path.join(VOICES_DIR, f"{vid}.mp3")
        if not os.path.exists(file_path):
            for filename in os.listdir(VOICES_DIR):
                if str(filename).startswith(str(vid)) and filename.lower().endswith(".mp3"):
                    file_path = os.path.join(VOICES_DIR, filename)
                    break
        thumb_path = None
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = os.path.join(VOICES_DIR, f"{vid}{ext}")
            if os.path.exists(candidate):
                thumb_path = candidate
                break
        return file_path, title, duration, channel, thumb_path

    def download():
        cached = search_cache.get(cache_key)
        if cached:
            file_path, title, duration, channel, thumb_path = build_result(cached)
            if file_path and os.path.exists(file_path):
                return file_path, title, duration, channel, thumb_path

        ydl_opts = {
            "format": "bestaudio/best",
            "default_search": "ytsearch1",
            "socket_timeout": 12,
            "retries": 2,
            "fragment_retries": 2,
            "extractor_retries": 2,
            "concurrent_fragment_downloads": 4,
            "http_chunk_size": 10 * 1024 * 1024,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "writethumbnail": True,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
            "outtmpl": os.path.join(VOICES_DIR, "%(id)s.%(ext)s"),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
            entries = info.get("entries") if isinstance(info, dict) else None
            video_info = entries[0] if entries else info
            if not video_info:
                return None, None, None, None, None
            search_cache[cache_key] = video_info
            if len(search_cache) > 120:
                search_cache.pop(next(iter(search_cache)), None)
            return build_result(video_info)

    return await asyncio.to_thread(download)

def stop_running_task(owner_id, chat_id=None, target_user_id=None, mode=None):
    keys_to_remove = []
    for key, info in list(running_tasks.items()):
        # العملية تحمل معرفاً فريداً في آخر المفتاح، لذلك تستخدم بيانات المهمة للفلترة.
        k_owner = info.get("owner_id")
        k_chat = info.get("chat_id")
        k_target = info.get("target_user_id")
        k_mode = info.get("mode")
        if k_owner == owner_id:
            chat_match = (chat_id is None) or (k_chat == chat_id)
            target_match = (target_user_id is None) or (k_target == target_user_id)
            mode_match = (mode is None) or (k_mode == mode)
            if chat_match and target_match and mode_match:
                keys_to_remove.append(key)

    for key in keys_to_remove:
        info = running_tasks.pop(key, None)
        if info and info.get("task") and not info["task"].done():
            info["task"].cancel()

TASTIR_OPERATION_MODES = {"tastir", "fardiyyat", "reply", "nick_am"}


def get_tastir_section_tasks(owner_id):
    """يعيد مهام قسم التسطير فقط، مرتبة بحسب وقت بدء التشغيل."""
    result = []
    for key, info in list(running_tasks.items()):
        if info.get("owner_id") == owner_id and info.get("mode") in TASTIR_OPERATION_MODES:
            result.append((key, info))
    return sorted(result, key=lambda item: item[1].get("started_at", 0), reverse=True)


def stop_tastir_section_tasks(owner_id):
    """يوقف التسطير والفرديات والريبلاي ونيك ام فقط، ولا يلمس أي ميزة أخرى."""
    keys = [key for key, info in list(running_tasks.items())
            if info.get("owner_id") == owner_id and info.get("mode") in TASTIR_OPERATION_MODES]
    for key in keys:
        info = running_tasks.pop(key, None)
        task = info.get("task") if info else None
        if task and not task.done():
            task.cancel()
    return len(keys)


def tastir_operation_title(mode):
    return {
        "tastir": "التسطير",
        "fardiyyat": "الفرديات",
        "reply": "الريبلاي",
        "nick_am": "نيك ام",
    }.get(mode, "عملية")


def format_tastir_elapsed(started_at):
    if not started_at:
        return "غير متاح"
    seconds = max(0, int(time.time() - started_at))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ساعة")
    if minutes or not parts:
        parts.append(f"{minutes} دقيقة")
    if seconds and not hours:
        parts.append(f"{seconds} ثانية")
    return " و ".join(parts)


async def format_tastir_operation_location(owner_id, info):
    """يعرض مكان العملية برابط قابل للفتح، ويستعمل حساب المستخدم للوصول إلى القروبات الخاصة."""
    chat_id = info.get("chat_id")
    target_user_id = info.get("target_user_id")
    client = user_clients.get(owner_id)

    if chat_id and int(chat_id) > 0:
        person_id = target_user_id or chat_id
        name = "مستخدم"
        username = None
        if client:
            try:
                entity = await client.get_entity(person_id)
                name = " ".join(part for part in [getattr(entity, "first_name", None), getattr(entity, "last_name", None)] if part) or "مستخدم"
                username = getattr(entity, "username", None)
            except Exception:
                pass
        person_link = f"tg://openmessage?user_id={person_id}"
        username_text = f"@{username}" if username else "لا يملك يوزر"
        return (
            "👤 **المكان:** محادثة خاصة\n"
            f"• الشخص: [{name}]({person_link})\n"
            f"• اليوزر: {username_text}\n"
            f"• الآيدي: `{person_id}`"
        )

    chat_name = "قروب أو قناة"
    username = None
    if client:
        try:
            entity = await client.get_entity(chat_id)
            chat_name = getattr(entity, "title", None) or "قروب أو قناة"
            username = getattr(entity, "username", None)
        except Exception:
            pass
    chat_link = f"https://t.me/{username}" if username else f"tg://openmessage?chat_id={chat_id}"
    return (
        "👥 **المكان:** قروب أو قناة\n"
        f"• القروب/القناة: [{chat_name}]({chat_link})\n"
        f"• الآيدي: `{chat_id}`"
    )


def register_tastir_operation_view(owner_id, task_key):
    """معرف قصير خاص بصاحب العملية حتى تبقى بيانات أزرار تيليجرام ضمن الحد المسموح."""
    now = time.time()
    for token, details in list(tastir_operation_views.items()):
        if details.get("expires_at", 0) < now:
            tastir_operation_views.pop(token, None)
    token = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")
    while token in tastir_operation_views:
        token = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")
    tastir_operation_views[token] = {
        "owner_id": owner_id,
        "task_key": task_key,
        "expires_at": now + 3600,
    }
    return token

def start_running_task(client, owner_id, chat_id, mode, target_msg_id=None, target_user_id=None, nick_prefix=None, nick_target_style="plain"):
    # لا نشغّل حلقة فارغة: الجمل يجب أن تكون التي أضافها المستخدم أو الجمل الأساسية التي حفظها الأدمن.
    current_info = users_db.get(owner_id, {})
    if mode == "tastir" and not (current_info.get("tastir", []) or default_tastir):
        return False
    if mode == "fardiyyat" and not (current_info.get("fardiyyat", []) or default_fardiyyat):
        return False
    if mode == "nick_am":
        nick_has_private = bool(current_info.get("nick_am", []))
        nick_has_tastir = current_info.get("include_tastir_in_nick_am", True) and (current_info.get("tastir", []) or default_tastir)
        nick_has_fardiyyat = current_info.get("include_fardiyyat_in_nick_am", True) and (current_info.get("fardiyyat", []) or default_fardiyyat)
        if not (nick_has_private or nick_has_tastir or nick_has_fardiyyat):
            return False

    # كل تشغيل يأخذ مفتاحاً مستقلاً حتى يبقى أكثر من تسطير/فرديات/نيك ام شغالاً في المكان نفسه.
    operation_id = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")
    task_key = (owner_id, chat_id, target_user_id, mode, operation_id)

    running_tasks[task_key] = {
        "task": None,
        "owner_id": owner_id,
        "chat_id": chat_id,
        "mode": mode,
        "target_msg_id": target_msg_id,
        "target_user_id": target_user_id,
        "nick_prefix": str(nick_prefix or "").strip(),
        "nick_target_style": str(nick_target_style or "plain"),
        "nick_reply_last_msg_id": None,
        "nick_reply_sent_without_message": False,
        "operation_id": operation_id,
        "started_at": time.time(),
    }

    async def loop():
        try:
            # تعتمد السرعة على بداية كل دورة وليس على وقت انتهاء طلب الإرسال،
            # لذلك لا يُضاف زمن الشبكة إلى السرعة المختارة عندما يكون الإرسال أسرع منها.
            next_send_at = time.monotonic()
            while True:
                wait_seconds = next_send_at - time.monotonic()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                task_info = running_tasks.get(task_key)
                if not task_info or task_info.get("mode") != mode:
                    break
                
                if not is_subscribed(owner_id):
                    break
                
                user_info = users_db.get(owner_id, {})
                
                if mode == "tastir":
                    phrases = user_info.get("tastir", []) + default_tastir
                elif mode == "fardiyyat":
                    phrases = user_info.get("fardiyyat", []) + default_fardiyyat
                elif mode == "nick_am":
                    phrases = list(user_info.get("nick_am", []))
                    if user_info.get("include_tastir_in_nick_am", True):
                        phrases += user_info.get("tastir", []) + default_tastir
                    if user_info.get("include_fardiyyat_in_nick_am", True):
                        phrases += user_info.get("fardiyyat", []) + default_fardiyyat
                else:
                    phrases = []

                curr_target_msg_id = task_info.get("target_msg_id")
                target_uid = task_info.get("target_user_id")
                
                # كريبلاي نيك ام يرسل مرة واحدة ثم ينتظر رسالة جديدة من الشخص نفسه.
                nick_as_reply = mode == "nick_am" and user_info.get("nick_am_reply_enabled", True)
                nick_target_style = task_info.get("nick_target_style", "plain")
                if nick_as_reply:
                    last_replied_id = task_info.get("nick_reply_last_msg_id")
                    sent_without_message = task_info.get("nick_reply_sent_without_message", False)
                    if curr_target_msg_id and curr_target_msg_id == last_replied_id:
                        next_send_at = time.monotonic() + 0.15
                        await asyncio.sleep(0.15)
                        continue
                    if not curr_target_msg_id and sent_without_message:
                        next_send_at = time.monotonic() + 0.15
                        await asyncio.sleep(0.15)
                        continue

                if phrases:
                    phrase = random.choice(phrases)
                    final_text = phrase
                    if mode == "nick_am":
                        prefix = str(task_info.get("nick_prefix") or "").strip()
                        if not prefix:
                            break
                        final_text = f"{prefix} {phrase}"
                    sent = False
                    # نيك ام يحتفظ دائماً بآخر رسالة للشخص، لكن اختيار المستخدم يحدد
                    # إن كانت الرسالة تُربط بها كريبلاي أم ترسل متتابعة من دون ربط.
                    send_as_reply = user_info.get("nick_am_reply_enabled", True)
                    # الرد الذي بدأ عليه نيك ام يبقى رداً حتى لو كان تكرار الريبلاي معطلاً.
                    should_reply = mode != "nick_am" or (nick_target_style == "reply") or (send_as_reply and bool(curr_target_msg_id))

                    if should_reply and curr_target_msg_id:
                        try:
                            await client.send_message(chat_id, final_text, reply_to=curr_target_msg_id)
                            sent = True
                        except Exception:
                            if target_uid:
                                try:
                                    async for msg in client.iter_messages(chat_id, from_user=target_uid, limit=1):
                                        task_info["target_msg_id"] = msg.id
                                        curr_target_msg_id = msg.id
                                        await client.send_message(chat_id, final_text, reply_to=curr_target_msg_id)
                                        sent = True
                                        break
                                except Exception:
                                    pass

                    if not sent:
                        # المنشن الصريح يبقى موجوداً في كلا النمطين؛ أما الرد فيستخدم سهم الرد.
                        if target_uid and chat_id != target_uid and (mode != "nick_am" or nick_target_style == "mention" or send_as_reply):
                            try:
                                user_entity = await client.get_entity(target_uid)
                                u_name = user_entity.first_name or "مستخدم"
                                mention = f"@{user_entity.username}" if user_entity.username else f"[{u_name}](tg://openmessage?user_id={target_uid})"
                                final_text = f"{final_text} {mention}"
                            except Exception:
                                pass
                        
                        try:
                            await client.send_message(chat_id, final_text)
                            sent = True
                        except Exception:
                            pass

                    if sent and mode == "nick_am" and send_as_reply:
                        if curr_target_msg_id:
                            task_info["nick_reply_last_msg_id"] = curr_target_msg_id
                        else:
                            task_info["nick_reply_sent_without_message"] = True

                try:
                    delay = max(0.1, float(user_info.get("speed", 1.0)))
                except (TypeError, ValueError):
                    delay = 1.0
                next_send_at += delay
                # عندما يستغرق إرسال تيليجرام وقتاً أطول من السرعة المختارة،
                # لا يمكن إرسال رسالة بأثر رجعي؛ تبدأ الدورة التالية فور الجاهزية.
                if next_send_at < time.monotonic():
                    next_send_at = time.monotonic()
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            current_info = running_tasks.get(task_key)
            if current_info and current_info.get("task") is asyncio.current_task():
                running_tasks.pop(task_key, None)

    print(f"[TASK STARTED] mode={mode} owner={owner_id} chat={chat_id} target={target_user_id}")
    task = asyncio.create_task(loop())
    running_tasks[task_key]["task"] = task
    return True

async def resolve_target_user(event):
    """يحدد المستخدم من الرد أو اليوزر أو الآيدي أو محادثة الخاص الحالية."""
    if event.reply_to_msg_id:
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.sender_id:
            return reply_msg.sender_id
    text_parts = (event.raw_text or "").split(maxsplit=1)
    if len(text_parts) > 1:
        arg = text_parts[1].strip()
        try:
            entity = await event.client.get_entity(arg)
            return entity.id
        except Exception:
            pass
    if event.is_private:
        try:
            peer = await event.get_chat()
            return getattr(peer, "id", event.chat_id)
        except Exception:
            return event.chat_id
    return None



async def resolve_nick_am_launch(event, nick_prefix, target_msg_id, target_user_id):
    """يفصل كلمة نيك ام عن هدف التشغيل: الرد يحتفظ بالرد، والمنشن يحتفظ بالمنشن."""
    prefix = str(nick_prefix or "").strip()
    target_style = "reply" if target_msg_id else ("reply" if event.is_private else "plain")

    # في القروب يمكن وضع اليوزر في آخر الأمر: نيك ام الرياض @username.
    if not target_msg_id and prefix:
        parts = prefix.rsplit(maxsplit=1)
        candidate = parts[-1] if parts else ""
        if candidate.startswith("@") and len(candidate) > 1:
            try:
                entity = await event.client.get_entity(candidate)
                target_user_id = entity.id
                prefix = parts[0].strip() if len(parts) > 1 else ""
                target_style = "mention"
            except Exception:
                pass

    return prefix, target_msg_id, target_user_id, target_style

async def check_user_ban_permissions(client, chat_entity, user):
    """يتحقق من صلاحية الحظر الفعلية من صلاحيات العضو، للقروب والقناة."""
    try:
        # get_permissions هي الواجهة المتوافقة مع Telethon؛ لا توجد get_participant في العميل.
        perms = await client.get_permissions(chat_entity, user)
    except Exception as exc:
        print(f"[FLUSH PERMISSION CHECK] تعذر قراءة الصلاحيات: {type(exc).__name__}: {exc}")
        return False

    if getattr(perms, 'is_creator', False) or isinstance(perms, ChannelParticipantCreator):
        return True

    rights = getattr(perms, 'admin_rights', None)
    if rights and getattr(rights, 'ban_users', False):
        return True

    # توافق مع بعض إصدارات Telethon التي تكشف الحق مباشرة على كائن الصلاحيات.
    if getattr(perms, 'ban_users', False):
        return True

    return False

async def run_flush_process(client, chat_id, user_id, status_target):
    u_info = users_db.get(user_id, {})
    speed = 0.01
    me = await client.get_me()
    
    kicked_count = 0
    failed_count = 0
    start_time = time.time()
    
    if hasattr(status_target, 'edit'):
        status_msg = await status_target.edit("⏳ جاري بدء تفليش وطرد جميع الأعضاء...")
    else:
        status_msg = await client.send_message(chat_id, "⏳ جاري بدء تفليش وطرد جميع الأعضاء...")

    try:
        chat_entity = await client.get_entity(chat_id)
        async for user in client.iter_participants(chat_entity):
            if user.id == me.id:
                continue
            try:
                await client(EditBannedRequest(chat_entity, user.id, ChatBannedRights(until_date=None, view_messages=True)))
                kicked_count += 1
                await asyncio.sleep(speed)
            except Exception:
                try:
                    await client.delete_chat_user(chat_entity, user.id)
                    kicked_count += 1
                    await asyncio.sleep(speed)
                except Exception:
                    failed_count += 1
    except Exception as e:
        print(f"Flush error: {e}")

    elapsed = round(time.time() - start_time, 2)
    report = (
        f"📊 **تقرير تفليش القروب/القناة:**\n\n"
        f"• تم طرد / حظر: `{kicked_count}` عضواً\n"
        f"• فشل طرد: `{failed_count}` عضواً\n"
        f"• السرعة المستخدمة: `{speed}` ثانية\n"
        f"• الوقت المستغرق: `{elapsed}` ثانية"
    )
    try:
        await status_msg.edit(report)
    except Exception:
        try:
            await client.send_message(user_id, report)
        except Exception:
            pass

async def start_manual_flush_task(client, owner_id, target_chat, status_chat_id, mode="ban"):
    """يشغل تفليشاً يدوياً قابلاً للإيقاف، بالحظر أو بالطرد، بعد التحقق من الصلاحية."""
    target_entity = await client.get_entity(target_chat)
    me = await client.get_me()
    if not await check_user_ban_permissions(client, target_entity, me):
        raise PermissionError("انت لست مرفوع بصلاحية حظر المستخدمين بالقروب/القناة")
    task_key = (owner_id, int(target_entity.id))
    previous = manual_flush_tasks.get(task_key)
    if previous and not previous.done():
        previous.cancel()

    async def worker():
        speed = 0.01
        action_name = "الحظر" if mode == "ban" else "الطرد"
        count = 0
        failed = 0
        status = await client.send_message(status_chat_id, f"⏳ جاري التفليش بـ{action_name}...")
        try:
            async for member in client.iter_participants(target_entity):
                if member.id == me.id or getattr(member, "bot", False):
                    continue
                try:
                    if mode == "ban":
                        await client(EditBannedRequest(target_entity, member.id, ChatBannedRights(until_date=None, view_messages=True)))
                    else:
                        await client.delete_chat_user(target_entity, member.id)
                    count += 1
                    await asyncio.sleep(speed)
                except Exception as exc:
                    raw = str(exc).upper()
                    if "FLOOD_WAIT" in raw:
                        seconds = int(re.search(r"\d+", raw).group()) if re.search(r"\d+", raw) else 5
                        await asyncio.sleep(seconds)
                    elif any(marker in raw for marker in ("CHAT_ADMIN_REQUIRED", "RIGHTS_NOT_AVAILABLE", "USER_ADMIN_INVALID")):
                        raise PermissionError("انسحبت صلاحية الحظر أو الطرد أثناء التفليش.")
                    else:
                        failed += 1
        except asyncio.CancelledError:
            await status.edit(f"⏹️ تم إيقاف التفليش.\n\n• تم التعامل مع: `{count}` عضواً\n• فشل: `{failed}`")
            raise
        except Exception as exc:
            await status.edit(f"⚠️ توقف التفليش.\n\n• السبب: {exc}\n• تم التعامل مع: `{count}` عضواً\n• فشل: `{failed}`")
        else:
            await status.edit(f"✅ انتهى التفليش بـ{action_name}.\n\n• تم التعامل مع: `{count}` عضواً\n• فشل: `{failed}`")
        finally:
            manual_flush_tasks.pop(task_key, None)

    task = asyncio.create_task(worker())
    manual_flush_tasks[task_key] = task
    return target_entity


async def stop_manual_flush_tasks(owner_id, target_chat_id=None):
    stopped = 0
    for key, task in list(manual_flush_tasks.items()):
        if key[0] != owner_id:
            continue
        if target_chat_id is not None and key[1] != int(target_chat_id):
            continue
        if not task.done():
            task.cancel()
            stopped += 1
    return stopped


# ==================== Source Features: Profile, Publishing, Media & Data ====================
def source_lock_message():
    return "⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس."


def _safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _add_profile_history(owner_id, first_name, last_name, username):
    init_user_db(owner_id)
    entry = {
        "name": f"{first_name or ''} {last_name or ''}".strip() or "بدون اسم",
        "username": f"@{username}" if username else "لا يوجد",
        "time": int(time.time())
    }
    history = users_db[owner_id].setdefault("profile_history", [])
    username_history = users_db[owner_id].setdefault("username_history", [])
    if not history or history[-1].get("name") != entry["name"]:
        history.append(entry)
        users_db[owner_id]["profile_history"] = history[-30:]
    if username and username not in username_history:
        username_history.append(username)
        users_db[owner_id]["username_history"] = username_history[-30:]




def _serialize_emoji_status(status):
    if isinstance(status, EmojiStatus):
        return {"kind": "emoji", "document_id": int(status.document_id)}
    if isinstance(status, EmojiStatusCollectible):
        return {
            "kind": "collectible",
            "collectible_id": int(status.collectible_id),
            "document_id": int(status.document_id),
            "title": status.title,
            "slug": status.slug,
            "pattern_document_id": int(status.pattern_document_id),
            "center_color": int(status.center_color),
            "edge_color": int(status.edge_color),
            "pattern_color": int(status.pattern_color),
            "text_color": int(status.text_color),
        }
    return {"kind": "empty"}


def _deserialize_emoji_status(data):
    data = data or {"kind": "empty"}
    if data.get("kind") == "emoji" and data.get("document_id"):
        return EmojiStatus(document_id=int(data["document_id"]))
    if data.get("kind") == "collectible" and data.get("document_id"):
        return EmojiStatusCollectible(
            collectible_id=int(data["collectible_id"]),
            document_id=int(data["document_id"]),
            title=data.get("title") or "",
            slug=data.get("slug") or "",
            pattern_document_id=int(data.get("pattern_document_id") or 0),
            center_color=int(data.get("center_color") or 0),
            edge_color=int(data.get("edge_color") or 0),
            pattern_color=int(data.get("pattern_color") or 0),
            text_color=int(data.get("text_color") or 0),
        )
    return EmojiStatusEmpty()


def _serialize_peer_color(color):
    if not color:
        return None
    return {
        "color": getattr(color, "color", None),
        "background_emoji_id": getattr(color, "background_emoji_id", None),
    }


def _deserialize_peer_color(data):
    if not data:
        return None
    return PeerColor(
        color=data.get("color"),
        background_emoji_id=data.get("background_emoji_id"),
    )


def _serialize_birthday(value):
    if not value:
        return None
    return {"day": int(value.day), "month": int(value.month), "year": getattr(value, "year", None)}


def _deserialize_birthday(data):
    if not data:
        return None
    return Birthday(day=int(data["day"]), month=int(data["month"]), year=data.get("year"))


def _serialize_business_location(value):
    if not value:
        return None
    point = getattr(value, "geo_point", None)
    return {
        "address": getattr(value, "address", "") or "",
        "lat": getattr(point, "lat", None) if point else None,
        "long": getattr(point, "long", None) if point else None,
        "accuracy_radius": getattr(point, "accuracy_radius", None) if point else None,
    }


def _deserialize_business_location(data):
    if not data:
        return None
    point = None
    if data.get("lat") is not None and data.get("long") is not None:
        point = InputGeoPoint(
            lat=float(data["lat"]), long=float(data["long"]),
            accuracy_radius=data.get("accuracy_radius")
        )
    return BusinessLocation(address=data.get("address") or "", geo_point=point)


def _serialize_business_work_hours(value):
    if not value:
        return None
    return {
        "timezone_id": getattr(value, "timezone_id", "UTC") or "UTC",
        "open_now": getattr(value, "open_now", None),
        "weekly_open": [
            {"start_minute": int(item.start_minute), "end_minute": int(item.end_minute)}
            for item in (getattr(value, "weekly_open", None) or [])
        ],
    }


def _deserialize_business_work_hours(data):
    if not data:
        return None
    return BusinessWorkHours(
        timezone_id=data.get("timezone_id") or "UTC",
        open_now=data.get("open_now"),
        weekly_open=[
            BusinessWeeklyOpen(start_minute=int(item["start_minute"]), end_minute=int(item["end_minute"]))
            for item in data.get("weekly_open", [])
        ],
    )


async def delete_message_after(message, seconds):
    """يحذف النتيجة المختصرة لاحقاً من دون تعطيل الأمر."""
    if not message:
        return
    try:
        await asyncio.sleep(seconds)
        await message.delete()
    except Exception:
        pass

async def apply_profile_template(client, owner_id, target):
    """يحفظ المظهر الحالي ثم يطبق الاسم والبايو والصورة القابلة للتعديل من الحساب الهدف."""
    init_user_db(owner_id)
    me = await client.get_me()
    # تحفظ الهوية الحالية لأول انتحال فقط. لا تستبدلها الانتحالات التالية.
    if not users_db[owner_id].get("profile_backup"):
        full_me = await client(GetFullUserRequest(me))
        current_full = getattr(full_me, "full_user", None)
        old_bio = getattr(current_full, "about", "") or ""
        old_photo = os.path.join(TEMP_DIR, f"profile_backup_{owner_id}.jpg")
        _safe_remove(old_photo)
        downloaded_old_photo = await client.download_profile_photo(me, file=old_photo)
        users_db[owner_id]["profile_backup"] = {
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
            "about": old_bio,
            "photo_path": downloaded_old_photo if downloaded_old_photo else None,
            "emoji_status": _serialize_emoji_status(getattr(me, "emoji_status", None)),
            "name_color": _serialize_peer_color(getattr(me, "color", None)),
            "profile_color": _serialize_peer_color(getattr(me, "profile_color", None)),
            "birthday": _serialize_birthday(getattr(current_full, "birthday", None)),
            "business_location": _serialize_business_location(getattr(current_full, "business_location", None)),
            "business_work_hours": _serialize_business_work_hours(getattr(current_full, "business_work_hours", None)),
            "saved_at": int(time.time())
        }
        _add_profile_history(owner_id, me.first_name, me.last_name, me.username)

    target_full = await client(GetFullUserRequest(target))
    target_bio = getattr(target_full.full_user, "about", "") or ""
    target_photo_path = os.path.join(TEMP_DIR, f"target_profile_{owner_id}.jpg")
    _safe_remove(target_photo_path)
    downloaded_target_photo = await client.download_profile_photo(target, file=target_photo_path)

    await client(UpdateProfileRequest(
        first_name=(target.first_name or "مستخدم")[:64],
        last_name=(target.last_name or "")[:64],
        about=target_bio[:70]
    ))

    if downloaded_target_photo:
        uploaded = await client.upload_file(downloaded_target_photo)
        await client(UploadProfilePhotoRequest(file=uploaded))
        _safe_remove(downloaded_target_photo)

    # نسخ عناصر مظهر بريم عند توفر الصلاحية على الحساب الذي ينفذ الانتحال.
    if getattr(me, "premium", False):
        try:
            target_status = getattr(target, "emoji_status", None) or EmojiStatusEmpty()
            await client(UpdateEmojiStatusRequest(emoji_status=target_status))
        except Exception as exc:
            print(f"[CLONE STYLE] تعذر نسخ الحالة المميزة: {type(exc).__name__}")
        try:
            await client(UpdateColorRequest(for_profile=False, color=getattr(target, "color", None)))
        except Exception as exc:
            print(f"[CLONE STYLE] تعذر نسخ لون الاسم: {type(exc).__name__}")
        try:
            await client(UpdateColorRequest(for_profile=True, color=getattr(target, "profile_color", None)))
        except Exception as exc:
            print(f"[CLONE STYLE] تعذر نسخ لون أو خلفية الملف: {type(exc).__name__}")

    # حقول التاريخ والموقع وأوقات العمل تعمل فقط للحسابات التي يسمح لها تيليجرام بها.
    target_full_user = getattr(target_full, "full_user", None)
    try:
        await client(UpdateBirthdayRequest(birthday=getattr(target_full_user, "birthday", None)))
    except Exception as exc:
        print(f"[CLONE BUSINESS] تعذر نسخ التاريخ: {type(exc).__name__}")
    try:
        target_location = getattr(target_full_user, "business_location", None)
        if target_location:
            target_geo = getattr(target_location, "geo_point", None)
            input_geo = None
            if target_geo and getattr(target_geo, "lat", None) is not None:
                input_geo = InputGeoPoint(lat=target_geo.lat, long=target_geo.long, accuracy_radius=getattr(target_geo, "accuracy_radius", None))
            await client(UpdateBusinessLocationRequest(geo_point=input_geo, address=getattr(target_location, "address", "") or ""))
        else:
            await client(UpdateBusinessLocationRequest(geo_point=None, address=""))
    except Exception as exc:
        print(f"[CLONE BUSINESS] تعذر نسخ الموقع: {type(exc).__name__}")
    try:
        target_hours = getattr(target_full_user, "business_work_hours", None)
        await client(UpdateBusinessWorkHoursRequest(business_work_hours=target_hours))
    except Exception as exc:
        print(f"[CLONE BUSINESS] تعذر نسخ أوقات العمل: {type(exc).__name__}")

    save_data()
    return target.first_name or "مستخدم"


async def _clear_current_profile_photo(client):
    try:
        photos = await client(GetUserPhotosRequest(user_id="me", offset=0, max_id=0, limit=1))
        if getattr(photos, "photos", None):
            await client(DeletePhotosRequest(id=photos.photos[:1]))
    except Exception:
        pass


async def restore_profile_template(client, owner_id):
    init_user_db(owner_id)
    backup = users_db[owner_id].get("profile_backup")
    if not backup:
        raise ValueError("لا توجد نسخة محفوظة من بيانات حسابك قبل التغيير.")

    await client(UpdateProfileRequest(
        first_name=(backup.get("first_name") or "مستخدم")[:64],
        last_name=(backup.get("last_name") or "")[:64],
        about=(backup.get("about") or "")[:70]
    ))
    photo_path = backup.get("photo_path")
    await _clear_current_profile_photo(client)
    if photo_path and os.path.exists(photo_path):
        uploaded = await client.upload_file(photo_path)
        await client(UploadProfilePhotoRequest(file=uploaded))

    # تعيد عناصر المظهر المحفوظة إن كانت متاحة للحساب الحالي.
    try:
        await client(UpdateEmojiStatusRequest(emoji_status=_deserialize_emoji_status(backup.get("emoji_status"))))
    except Exception:
        pass
    try:
        await client(UpdateColorRequest(for_profile=False, color=_deserialize_peer_color(backup.get("name_color"))))
    except Exception:
        pass
    try:
        await client(UpdateColorRequest(for_profile=True, color=_deserialize_peer_color(backup.get("profile_color"))))
    except Exception:
        pass
    try:
        await client(UpdateBirthdayRequest(birthday=_deserialize_birthday(backup.get("birthday"))))
    except Exception:
        pass
    try:
        location = _deserialize_business_location(backup.get("business_location"))
        if location:
            await client(UpdateBusinessLocationRequest(geo_point=location.geo_point, address=location.address))
        else:
            await client(UpdateBusinessLocationRequest(geo_point=None, address=""))
    except Exception:
        pass
    try:
        hours = _deserialize_business_work_hours(backup.get("business_work_hours"))
        await client(UpdateBusinessWorkHoursRequest(business_work_hours=hours))
    except Exception:
        pass

    me = await client.get_me()
    _add_profile_history(owner_id, me.first_name, me.last_name, me.username)
    # بعد الإعادة تحذف النسخة المؤقتة حتى يتم حفظ وضعك الجديد عند أول انتحال تالٍ.
    users_db[owner_id].pop("profile_backup", None)
    save_data()


def _publish_job_list(owner_id):
    init_user_db(owner_id)
    return users_db[owner_id].setdefault("auto_publish_jobs", [])


def _remove_persisted_publish_job(owner_id, target_chat_id, operation_id=None):
    target = int(target_chat_id)
    jobs = _publish_job_list(owner_id)
    if operation_id is None:
        users_db[owner_id]["auto_publish_jobs"] = [job for job in jobs if int(job.get("target_chat_id", 0)) != target]
    else:
        users_db[owner_id]["auto_publish_jobs"] = [
            job for job in jobs
            if not (int(job.get("target_chat_id", 0)) == target and str(job.get("operation_id", "")) == str(operation_id))
        ]
    save_data()


def _upsert_persisted_publish_job(owner_id, target_chat_id, source_message, delay, count, forward_mode, completed=0, origin_chat_id=None, operation_id=None):
    target = int(target_chat_id)
    source_chat_id = getattr(source_message, "chat_id", None)
    source_message_id = getattr(source_message, "id", None)
    if source_chat_id is None or source_message_id is None:
        raise ValueError("تعذر حفظ مصدر رسالة النشر لاستعادتها لاحقاً.")
    operation_id = str(operation_id or secrets.token_urlsafe(6).replace("-", "x").replace("_", "y"))
    job = {
        "operation_id": operation_id,
        "target_chat_id": target,
        "source_chat_id": int(source_chat_id),
        "source_message_id": int(source_message_id),
        "delay": float(delay),
        "count": int(count),
        "forward_mode": bool(forward_mode),
        "completed": int(completed),
        "origin_chat_id": int(origin_chat_id) if origin_chat_id is not None else int(source_chat_id),
        "updated_at": int(time.time()),
    }
    jobs = [item for item in _publish_job_list(owner_id)
            if str(item.get("operation_id", "")) != operation_id]
    jobs.append(job)
    users_db[owner_id]["auto_publish_jobs"] = jobs
    save_data()
    return job


def _update_publish_completed(owner_id, target_chat_id, completed, operation_id=None):
    target = int(target_chat_id)
    for job in _publish_job_list(owner_id):
        same_target = int(job.get("target_chat_id", 0)) == target
        same_operation = operation_id is None or str(job.get("operation_id", "")) == str(operation_id)
        if same_target and same_operation:
            job["completed"] = int(completed)
            job["updated_at"] = int(time.time())
            save_data()
            return


def _translate_publish_error(error):
    raw = str(error or "").strip()
    normalized = raw.upper()
    if "YOU CAN'T WRITE IN THIS CHAT" in normalized or "CHAT_WRITE_FORBIDDEN" in normalized:
        return "تم تقييدك من الكتابة في هذا القروب أو القناة."
    if "CHAT_SEND_MEDIA_FORBIDDEN" in normalized or "MEDIA_FORBIDDEN" in normalized:
        return "لا تملك صلاحية إرسال الوسائط في هذا القروب أو القناة."
    if "USER_BANNED_IN_CHANNEL" in normalized or "USER_BANNED" in normalized:
        return "تم حظر الحساب من هذا القروب أو القناة."
    if "CHAT_ADMIN_REQUIRED" in normalized or "RIGHTS_NOT_AVAILABLE" in normalized:
        return "لا تملك الصلاحية اللازمة للنشر هنا."
    if "PROTECTED CHAT" in normalized or "FORWARDS_RESTRICTED" in normalized or ("FORWARD" in normalized and "RESTRICT" in normalized):
        return "رفض تيليجرام التحويل في المحاولة النظامية؛ يظهر تفصيل الطلبين في سجل الخطأ للإدارة."
    if "MESSAGE_ID_INVALID" in normalized:
        return "تعذر الوصول إلى رسالة المصدر للتحويل؛ أعد الرد على الرسالة ثم شغّل النشر من جديد."
    if "CHANNEL_PRIVATE" in normalized or "CHAT_PRIVATE" in normalized:
        return "القروب أو القناة خاص ولا يستطيع الحساب الوصول إليه."
    if "PEER_ID_INVALID" in normalized or "USERNAME_NOT_OCCUPIED" in normalized:
        return "معرف القروب أو القناة غير صحيح أو لم يعد متاحاً."
    if "FLOOD_WAIT" in normalized:
        return "تم تقييد الحساب مؤقتاً من تيليجرام بسبب كثرة العمليات."
    if "AUTH_KEY_UNREGISTERED" in normalized or "SESSION_REVOKED" in normalized:
        return "انتهت جلسة الحساب أو تم إلغاؤها؛ يلزم تسجيل الدخول للحساب مرة أخرى."
    if "TIMEOUT" in normalized or "TIMEDOUT" in normalized:
        return "انقطع الاتصال مؤقتاً أثناء النشر؛ سيحاول البوت الاستعادة تلقائياً."
    if "TYPEERROR" in normalized or "VALUEERROR" in normalized:
        return "تعذر تجهيز رسالة النشر؛ أعد الرد على الرسالة المطلوبة ثم شغّل النشر من جديد."
    if "RPCERROR" in normalized or "BAD_REQUEST" in normalized:
        return "رفض تيليجرام عملية النشر؛ تحقق من صلاحية الحساب والقروب ومصدر الرسالة."
    return "تعذر إكمال النشر بسبب خطأ من تيليجرام؛ أعد المحاولة بعد ثوانٍ."


def _is_transient_publish_error(error):
    """يُبقي المهمة حية عند أخطاء الشبكة المؤقتة بدلاً من إيقاف كل النشر."""
    normalized = str(error or "").upper()
    transient_markers = (
        "TIMEOUT", "TIMEDOUT", "CONNECTION", "NETWORK", "SERVER_ERROR",
        "RPC_CALL_FAIL", "RESET BY PEER", "TRANSPORT",
    )
    return any(marker in normalized for marker in transient_markers)


async def _forward_original_publish_message(client, target_chat_id, source_message):
    """تحويل نظامي مباشر للرسالة الأصلية بلا فحص محتوى أو تقييد محلي."""
    if source_message is None:
        raise ValueError("تعذر العثور على الرسالة الأصلية للتحويل.")
    # هذه نفس عملية تحويل رسالة تيليجرام من المصدر إلى الوجهة، ولا توجد أي شروط محلية قبلها.
    await client.forward_messages(target_chat_id, source_message)


async def _publish_message(client, target_chat_id, source_message, forward_mode=False):
    """ينشر نسخة بلا مصدر افتراضياً، أو تحويلاً مباشراً طبيعياً عند كتابة «تحويل»."""
    if forward_mode:
        await _forward_original_publish_message(client, target_chat_id, source_message)
        return

    text = getattr(source_message, "message", None) or ""
    entities = getattr(source_message, "entities", None)
    media = getattr(source_message, "media", None)
    if media is not None and getattr(source_message, "file", None) is not None:
        await client.send_file(
            target_chat_id,
            media,
            caption=text or None,
            formatting_entities=entities,
        )
        return
    await client.send_message(
        target_chat_id,
        text or "\u2063",
        formatting_entities=entities,
        link_preview=bool(getattr(source_message, "web_preview", None)),
    )


async def _publish_target_name(client, target_chat_id):
    try:
        entity = await client.get_entity(target_chat_id)
        return getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(target_chat_id)
    except Exception:
        return str(target_chat_id)


async def _send_publish_stop_notice(owner_id, target_name, target_chat_id, reason):
    text = (
        "⚠️ **تم إيقاف النشر**\n\n"
        f"• القروب/القناة ← **{target_name}**\n"
        f"• الآيدي ← `{target_chat_id}`\n"
        f"• السبب ← {reason}"
    )
    try:
        await bot.send_message(owner_id, text)
    except Exception:
        pass


def _parse_join_target(value):
    target = str(value or "").strip()
    if not target:
        raise ValueError("الرابط أو اليوزر فارغ.")
    lower = target.lower()
    # بعض الأزرار تستخدم رابط Telegram الداخلي بدلاً من t.me.
    if lower.startswith("tg://resolve?"):
        match = re.search(r"(?:^|[?&])domain=([^&]+)", target, flags=re.I)
        if match:
            target = "@" + match.group(1).strip()
            lower = target.lower()
    if "telegram.me/" in lower:
        target = "https://t.me/" + target.split("telegram.me/", 1)[1]
        lower = target.lower()
    if "t.me/+" in lower:
        return "invite", target.split("+")[-1].split("?")[0]
    if "t.me/joinchat/" in lower:
        return "invite", target.rstrip("/").split("/")[-1].split("?")[0]
    if "t.me/" in lower:
        target = "@" + target.rstrip("/").split("/")[-1].split("?")[0]
    if target.startswith("@") or target.lstrip("-").isdigit():
        return "public", target
    raise ValueError("رابط أو يوزر اشتراك غير صالح.")


def _is_publish_write_block(error):
    text = str(error or "").upper()
    return any(marker in text for marker in (
        "YOU CAN'T WRITE IN THIS CHAT", "CHAT_WRITE_FORBIDDEN",
        "CHAT_SEND_MEDIA_FORBIDDEN", "USER_BANNED_IN_CHANNEL",
    ))


def _extract_join_targets_from_message(message):
    """يستخرج روابط الاشتراك من أزرار ورسالة بوت الاشتراك الإجباري."""
    targets = []
    seen = set()

    def add(value):
        if not value:
            return
        value = str(value).strip()
        try:
            _parse_join_target(value)
        except ValueError:
            return
        if value not in seen:
            seen.add(value)
            targets.append(value)

    for row in (getattr(message, "buttons", None) or []):
        for button in row:
            add(getattr(button, "url", None))

    raw_text = getattr(message, "raw_text", "") or ""
    for link in re.findall(r"(?:https?://)?t\.me/(?:joinchat/|\+)?[A-Za-z0-9_+\-]+", raw_text, flags=re.I):
        add(link)
    return targets


async def _join_publish_target(client, target):
    """يعيد joined عند الدخول الفوري، أو pending عند إرسال طلب يحتاج موافقة أدمن."""
    kind, value = _parse_join_target(target)
    if kind == "invite":
        invite_info = await client(CheckChatInviteRequest(value))
        if getattr(invite_info, "request_needed", False):
            await client(ImportChatInviteRequest(value))
            return "pending"
        await client(ImportChatInviteRequest(value))
        return "joined"
    entity = await client.get_entity(value)
    result = await client(JoinChannelRequest(entity))
    result_name = type(result).__name__.lower()
    if "request" in result_name or "pending" in result_name:
        return "pending"
    return "joined"


def _remember_discovered_subscription(owner_id, target):
    init_user_db(owner_id)
    items = users_db[owner_id].setdefault("publish_required_chats", [])
    if target not in items:
        items.append(target)
        save_data()


async def _press_subscription_check_buttons(client, message):
    """يضغط فقط أزرار التحقق الآمنة بعد الانضمام لكي يعترف بوت الاشتراك بالعضوية."""
    pressed = False
    check_words = ("تحقق", "تأكيد", "فحص", "check", "verify")
    try:
        peer = await client.get_input_entity(message.chat_id)
        for row in (getattr(message, "buttons", None) or []):
            for button in row:
                label = (getattr(button, "text", "") or "").lower()
                data = getattr(button, "data", None)
                if data and any(word in label for word in check_words):
                    await client(GetBotCallbackAnswerRequest(peer=peer, msg_id=message.id, data=data))
                    pressed = True
    except Exception:
        pass
    return pressed


async def resolve_forced_subscription_from_chat(client, owner_id, target_chat_id, attempted_targets=None):
    """يقرأ اشتراكات القروب من أزرار/روابط الرسائل، ينضم للجديد منها ثم يضغط تحقق.

    attempted_targets يحتفظ بما عولج في مهمة النشر الحالية، لذلك لا يدور البوت على
    الرابط نفسه إذا ظهر شرط اشتراك جديد بعده.
    """
    discovered = []
    check_messages = []
    attempted_targets = attempted_targets if attempted_targets is not None else set()
    try:
        async for message in client.iter_messages(target_chat_id, limit=100):
            if getattr(message, "out", False):
                continue
            # بعض أنظمة الاشتراك ترسل الرسالة من بوت، وبعضها من حساب أو خدمة أخرى.
            # نعتمد على وجود أزرار/روابط وكلمات الاشتراك بدلاً من نوع المرسل فقط.
            raw_text = (getattr(message, "raw_text", "") or "").lower()
            buttons = getattr(message, "buttons", None) or []
            subscription_words = ("اشتراك", "اشترك", "subscribe", "channel", "قناة", "تحقق", "تأكيد")
            if not buttons and not any(word in raw_text for word in subscription_words):
                continue
            candidates = _extract_join_targets_from_message(message)
            if candidates:
                discovered.extend(candidates)
                check_messages.append(message)

        unique_targets = []
        for target in discovered:
            if target not in unique_targets and target not in attempted_targets:
                unique_targets.append(target)
        if not unique_targets:
            return False, "لم أجد اشتراكاً إجبارياً جديداً قابلاً للانضمام؛ قد يحتاج الشرط موافقة أدمن أو رابطاً صالحاً.", []

        joined_or_known = 0
        pending_targets = []
        for target in unique_targets:
            try:
                join_state = await _join_publish_target(client, target)
                _remember_discovered_subscription(owner_id, target)
                attempted_targets.add(target)
                if join_state == "pending":
                    pending_targets.append(target)
                else:
                    joined_or_known += 1
            except Exception as e:
                error_text = str(e).upper()
                if "USER_ALREADY_PARTICIPANT" in error_text or ("ALREADY" in error_text and "PARTICIPANT" in error_text):
                    _remember_discovered_subscription(owner_id, target)
                    attempted_targets.add(target)
                    joined_or_known += 1
                    continue
                return False, f"تعذر الاشتراك في `{target}`: {_translate_publish_error(e)}", []

        for message in check_messages:
            await _press_subscription_check_buttons(client, message)
        details = []
        if joined_or_known:
            details.append(f"تمت معالجة {joined_or_known} اشتراك إجباري")
        if pending_targets:
            details.append(f"تم إرسال {len(pending_targets)} طلب انضمام بانتظار موافقة الأدمن")
        return bool(joined_or_known or pending_targets), "؛ ".join(details) + ".", pending_targets
    except Exception as e:
        return False, _translate_publish_error(e), []


async def ensure_publish_required_chats(client, owner_id):
    """ينضم الحساب تلقائياً فقط إلى القوائم التي أضافها مالك الحساب بنفسه."""
    required = list(users_db.get(owner_id, {}).get("publish_required_chats", []))
    joined = []
    for target in required:
        try:
            kind, value = _parse_join_target(target)
            if kind == "invite":
                await client(ImportChatInviteRequest(value))
            else:
                entity = await client.get_entity(value)
                await client(JoinChannelRequest(entity))
            joined.append(str(target))
        except Exception as e:
            message = str(e).upper()
            if "USER_ALREADY_PARTICIPANT" in message or "ALREADY" in message and "PARTICIPANT" in message:
                continue
            return False, _translate_publish_error(e), str(target)
    return True, "", joined


async def check_publish_permission(client, target_chat_id, owner_id=None):
    """يفحص حق الإرسال الفعلي قبل إنشاء مهمة النشر، دون إرسال رسالة اختبار للوجهة."""
    try:
        entity = await client.get_entity(target_chat_id)
        name = getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(target_chat_id)
        me = await client.get_me()
        perms = await client.get_permissions(entity, me)
        if getattr(perms, "is_banned", False) or getattr(perms, "send_messages", None) is False:
            return False, name, "لا تستطيع الإرسال هنا؛ ربما تم تقييدك أو حظرك."
        # في القنوات يلزم أن يكون الحساب مالكاً أو أدمن ويملك post_messages فعلياً.
        if getattr(entity, "broadcast", False) and not getattr(entity, "megagroup", False):
            if getattr(perms, "is_creator", False):
                return True, name, ""
            if not getattr(perms, "is_admin", False):
                return False, name, "لا تستطيع النشر في هذه القناة؛ يجب أن تكون مالكاً أو أدمن بصلاحية النشر."
            rights = getattr(perms, "admin_rights", None)
            if rights is not None and not getattr(rights, "post_messages", False):
                return False, name, "أنت أدمن في القناة لكن لا تملك صلاحية نشر الرسائل."
        return True, name, ""
    except Exception as e:
        if owner_id is not None:
            await report_admin_error("فحص صلاحيات النشر", e, owner_id, target_chat_id)
        return False, str(target_chat_id), _translate_publish_error(e)


async def start_auto_publish_task(client, owner_id, target_chat_id, source_message, delay, count, forward_mode=False, completed=0, origin_chat_id=None, restored=False, pending_approval_targets=None, operation_id=None):
    operation_id = str(operation_id or secrets.token_urlsafe(6).replace("-", "x").replace("_", "y"))
    task_key = (owner_id, int(target_chat_id), operation_id)
    job = _upsert_persisted_publish_job(owner_id, target_chat_id, source_message, delay, count, forward_mode, completed, origin_chat_id, operation_id)

    async def publish_loop():
        sent = int(job.get("completed", 0))
        target_name = await _publish_target_name(client, target_chat_id)
        transient_notice_sent = False
        # كل رابط يُعالج مرة واحدة فقط. يدعم التسلسل الطويل للاشتراكات من دون حلقة غير منتهية.
        forced_subscription_targets = set()
        max_forced_subscription_targets = 50
        active_pending_approval_targets = list(pending_approval_targets or [])
        approval_wait_notice_sent = False
        try:
            while sent < count:
                try:
                    await _publish_message(client, target_chat_id, source_message, forward_mode)
                except Exception as e:
                    if _is_publish_write_block(e):
                        # إذا كان هناك طلب انضمام أُرسل بالفعل، ننتظر قبول الأدمن ثم نعيد نفس الرسالة.
                        if active_pending_approval_targets:
                            if not approval_wait_notice_sent:
                                try:
                                    await bot.send_message(
                                        owner_id,
                                        "⏳ تم إرسال طلب انضمام للاشتراك الإجباري، لكن القروب يحتاج موافقة الأدمن. "
                                        "ستبقى مهمة النشر منتظرة وستكمل تلقائياً فور الموافقة."
                                    )
                                except Exception:
                                    pass
                                approval_wait_notice_sent = True
                            await asyncio.sleep(60)
                            continue
                        if len(forced_subscription_targets) < max_forced_subscription_targets:
                            resolved, resolve_note, new_pending_targets = await resolve_forced_subscription_from_chat(
                                client, owner_id, target_chat_id, forced_subscription_targets
                            )
                            if resolved:
                                # لا يزيد sent هنا؛ يعاد إرسال الرسالة نفسها بعد معالجة كل اشتراك جديد.
                                if new_pending_targets:
                                    active_pending_approval_targets.extend(new_pending_targets)
                                await asyncio.sleep(2)
                                continue
                    if not _is_transient_publish_error(e):
                        raise
                    # لا نوقف 14 حساباً عند انقطاع مؤقت؛ ننتظر ثم نعيد المحاولة على نفس الرسالة.
                    if not transient_notice_sent:
                        try:
                            await bot.send_message(owner_id, f"⚠️ تعذر الاتصال مؤقتاً أثناء النشر في **{target_name}**. سيحاول ديمون الاستعادة تلقائياً.")
                        except Exception:
                            pass
                        transient_notice_sent = True
                    await asyncio.sleep(15)
                    continue
                transient_notice_sent = False
                active_pending_approval_targets.clear()
                approval_wait_notice_sent = False
                sent += 1
                _update_publish_completed(owner_id, target_chat_id, sent, operation_id)
                if sent < count:
                    await asyncio.sleep(delay)
        except asyncio.CancelledError:
            reason = publish_stop_reasons.pop(task_key, "تم إيقاف النشر يدوياً")
            _remove_persisted_publish_job(owner_id, target_chat_id, operation_id)
            await _send_publish_stop_notice(owner_id, target_name, target_chat_id, reason)
            raise
        except Exception as e:
            print(f"[PUBLISH ERROR] owner={owner_id} target={target_chat_id} type={type(e).__name__} raw={e}")
            await report_admin_error("توقف النشر التلقائي", e, owner_id, target_chat_id)
            _remove_persisted_publish_job(owner_id, target_chat_id, operation_id)
            await _send_publish_stop_notice(owner_id, target_name, target_chat_id, _translate_publish_error(e))
        else:
            _remove_persisted_publish_job(owner_id, target_chat_id, operation_id)
            try:
                await bot.send_message(owner_id, f"✅ اكتمل النشر في **{target_name}** بعد إرسال {sent} رسالة.")
            except Exception:
                pass
        finally:
            auto_publish_tasks.pop(task_key, None)
            auto_publish_meta.pop(task_key, None)
            publish_stop_reasons.pop(task_key, None)

    task = asyncio.create_task(publish_loop())
    auto_publish_tasks[task_key] = task
    auto_publish_meta[task_key] = job
    if restored:
        target_name = await _publish_target_name(client, target_chat_id)
        try:
            await bot.send_message(owner_id, f"♻️ تم استئناف النشر تلقائياً في **{target_name}** من الرسالة رقم {int(completed) + 1}.")
        except Exception:
            pass
    return task_key


async def stop_auto_publish_task(client, owner_id, target_chat_id=None, reason="تم إيقاف النشر يدوياً"):
    stopped = 0
    for key, task in list(auto_publish_tasks.items()):
        task_owner, task_chat = key[0], key[1]
        if task_owner == owner_id and (target_chat_id is None or task_chat == int(target_chat_id)):
            if not task.done():
                publish_stop_reasons[key] = reason
                task.cancel()
                stopped += 1
    return stopped


async def restore_auto_publish_jobs(client, owner_id):
    """يعيد تشغيل المهام المحفوظة؛ أي منع اشتراك يعالج داخل دورة النشر نفسها."""
    jobs = list(users_db.get(owner_id, {}).get("auto_publish_jobs", []))
    for job in jobs:
        target_chat_id = int(job.get("target_chat_id", 0))
        if not target_chat_id:
            continue
        operation_id = str(job.get("operation_id") or secrets.token_urlsafe(6).replace("-", "x").replace("_", "y"))
        job["operation_id"] = operation_id
        task_key = (owner_id, target_chat_id, operation_id)
        if task_key in auto_publish_tasks and not auto_publish_tasks[task_key].done():
            continue
        try:
            source_message = await client.get_messages(int(job["source_chat_id"]), ids=int(job["source_message_id"]))
            if not source_message:
                raise RuntimeError("رسالة مصدر النشر لم تعد متاحة للحساب.")
            await start_auto_publish_task(
                client, owner_id, target_chat_id, source_message,
                float(job.get("delay", 1.0)), int(job.get("count", 1)),
                bool(job.get("forward_mode", False)), int(job.get("completed", 0)),
                job.get("origin_chat_id"), restored=True, operation_id=operation_id,
            )
        except Exception as e:
            _remove_persisted_publish_job(owner_id, target_chat_id)
            target_name = await _publish_target_name(client, target_chat_id)
            await _send_publish_stop_notice(owner_id, target_name, target_chat_id, "تعذر استئناف المهمة: " + _translate_publish_error(e))


async def convert_to_image(client, source_message, destination, reply_to=None):
    if Image is None:
        raise RuntimeError("مكتبة Pillow غير مثبتة. ثبّتها بالأمر: pip install pillow")
    if not source_message or not source_message.media:
        raise ValueError("قم بالرد على ملصق أو GIF أولاً.")
    raw_path = await client.download_media(source_message, file=TEMP_DIR)
    if not raw_path:
        raise ValueError("تعذر تحميل الوسيط.")
    output = os.path.join(TEMP_DIR, f"image_{int(time.time() * 1000)}.png")
    try:
        with Image.open(raw_path) as image:
            if getattr(image, "is_animated", False):
                image.seek(0)
            image.convert("RGBA").save(output, "PNG")
        await client.send_file(destination, output, reply_to=reply_to)
    finally:
        _safe_remove(raw_path)
        _safe_remove(output)


async def convert_to_sticker(client, source_message, destination, reply_to=None):
    if Image is None:
        raise RuntimeError("مكتبة Pillow غير مثبتة. ثبّتها بالأمر: pip install pillow")
    if not source_message or not source_message.photo:
        raise ValueError("قم بالرد على صورة أولاً.")
    raw_path = await client.download_media(source_message, file=TEMP_DIR)
    if not raw_path:
        raise ValueError("تعذر تحميل الصورة.")
    output = os.path.join(TEMP_DIR, f"sticker_{int(time.time() * 1000)}.webp")
    try:
        with Image.open(raw_path) as image:
            image = image.convert("RGBA")
            image.thumbnail((512, 512))
            image.save(output, "WEBP", quality=90, method=6)
        await client.send_file(
            destination,
            output,
            reply_to=reply_to,
            attributes=[DocumentAttributeSticker(alt="", stickerset=InputStickerSetEmpty())]
        )
    finally:
        _safe_remove(raw_path)
        _safe_remove(output)


async def extract_audio_from_video(client, source_message, destination, reply_to=None):
    if not source_message or not source_message.video:
        raise ValueError("قم بالرد على فيديو أولاً.")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("أداة ffmpeg غير مثبتة. ثبّتها في تيرمكس بالأمر: pkg install ffmpeg")
    raw_path = await client.download_media(source_message, file=TEMP_DIR)
    if not raw_path:
        raise ValueError("تعذر تحميل الفيديو.")
    output = os.path.join(TEMP_DIR, f"audio_{int(time.time() * 1000)}.mp3")
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", raw_path, "-vn", "-c:a", "libmp3lame", output,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.communicate()
        if process.returncode != 0 or not os.path.exists(output):
            raise RuntimeError("فشل استخراج الصوت من الفيديو.")
        await client.send_file(destination, output, reply_to=reply_to, voice_note=False)
    finally:
        _safe_remove(raw_path)
        _safe_remove(output)


async def convert_to_voice_note(client, source_message, destination, reply_to=None):
    if not source_message or not (source_message.audio or source_message.voice):
        raise ValueError("قم بالرد على ملف صوتي أو بصمة أولاً.")
    raw_path = await client.download_media(source_message, file=TEMP_DIR)
    if not raw_path:
        raise ValueError("تعذر تحميل الصوت.")
    try:
        await client.send_file(destination, raw_path, reply_to=reply_to, voice_note=True)
    finally:
        _safe_remove(raw_path)


async def get_my_data_report(client, owner_id):
    init_user_db(owner_id)
    me = await client.get_me()
    _add_profile_history(owner_id, me.first_name, me.last_name, me.username)
    save_data()

    created_channels = []
    created_groups = []
    async for dialog in client.iter_dialogs(limit=None):
        entity = dialog.entity
        if getattr(entity, "creator", False):
            if getattr(entity, "broadcast", False):
                created_channels.append((getattr(entity, "title", "بدون اسم"), entity.id))
            elif getattr(entity, "megagroup", False) or hasattr(entity, "participants_count"):
                created_groups.append((getattr(entity, "title", "بدون اسم"), entity.id))

    history = users_db[owner_id].get("profile_history", [])[-15:]
    usernames = users_db[owner_id].get("username_history", [])[-15:]
    text = (
        "📂 **بياناتي:**\n\n"
        f"• الاسم الحالي: `{(me.first_name or '')} {(me.last_name or '')}`\n"
        f"• اليوزر الحالي: @{me.username if me.username else 'لا يوجد'}\n"
        f"• الآيدي: `{me.id}`\n\n"
        "🧾 **الأسماء المحفوظة:**\n" +
        ("\n".join(f"• {entry.get('name', 'بدون اسم')}" for entry in history) if history else "لا يوجد سجل محفوظ بعد.") +
        "\n\n🔖 **اليوزرات المحفوظة:**\n" +
        ("\n".join(f"• @{username}" for username in usernames) if usernames else "لا يوجد سجل محفوظ بعد.") +
        "\n\n📢 **القنوات التي أنشأتها وما زال حسابك يصل إليها:**\n" +
        ("\n".join(f"• {title} — `{chat_id}`" for title, chat_id in created_channels[:30]) if created_channels else "لا توجد.") +
        "\n\n👥 **القروبات التي أنشأتها وما زال حسابك يصل إليها:**\n" +
        ("\n".join(f"• {title} — `{chat_id}`" for title, chat_id in created_groups[:30]) if created_groups else "لا توجد.")
    )
    return text


SOURCE_MENU_TITLE = "👨🏻‍💻 | **مرحباً بك عزيزي المستخدم**\n💼 | **قائمة أوامر سورس ديمون**\n⚙️ | **اختر ما تريد من الأزرار أسفل**"
TASTIR_INLINE_MENU_TITLE = "📝 | **قسم التسطير — ديمون**\n⚙️ | **اختر القسم الذي تريد إدارته من الأزرار أسفل**"
SOURCE_MENU_FALLBACK = """⚠️ تعذر إرسال قائمة الأزرار المضمّنة.

فعّل Inline Mode لبوت ديمون من @BotFather عبر الأمر `/setinline`، ثم أعد تشغيل البوت وجرب `.الاوامر` مرة أخرى."""


# رموز مؤقتة تمنع أي شخص غير صاحب الجلسة من استدعاء قائمة السورس المضمّنة.
inline_source_requests = {}


async def send_source_commands_menu(client, owner_id, chat_id):
    """يرسل القائمة فقط من جلسة الحساب المرتبط وبنفس المحادثة."""
    try:
        me = await client.get_me()
        if me.id != owner_id:
            raise RuntimeError("جلسة اليوزر بوت لا تطابق صاحب الحساب المرتبط")
        bot_me = await bot.get_me()
        if not bot_me.bot:
            raise RuntimeError("جلسة الإدارة ليست جلسة بوت")
        if not bot_me.username:
            raise RuntimeError("لا يوجد يوزر لبوت الإدارة")
        token = secrets.token_urlsafe(18)
        inline_source_requests[token] = {"owner_id": owner_id, "expires_at": time.time() + 90}
        results = await client.inline_query(bot_me.username, f"demon_source_menu:{token}")
        if not results:
            inline_source_requests.pop(token, None)
            raise RuntimeError("لم تصل نتيجة القائمة المضمّنة؛ فعّل Inline Mode للبوت من BotFather")
        await results[0].click(chat_id)
        return True
    except Exception as e:
        bot_name = getattr(bot_me, "username", "بوت الإدارة") if "bot_me" in locals() else "بوت الإدارة"
        reason = f"{type(e).__name__}: {e}"
        print(f"\n[INLINE MENU ERROR] {reason}\n")
        await client.send_message(
            chat_id,
            f"⚠️ تعذر إظهار قائمة الأزرار عبر @{bot_name}.\n• السبب ← `{reason}`\n\nتأكد من تشغيل بوت ديمون مرة واحدة فقط ومن تفعيل Inline Mode في @BotFather."
        )
        return False


async def send_tastir_commands_menu(client, owner_id, chat_id):
    """يعرض قسم التسطير كأزرار عبر بوت ديمون، للحساب المشترك فقط."""
    try:
        me = await client.get_me()
        if me.id != owner_id:
            raise RuntimeError("جلسة اليوزر بوت لا تطابق صاحب الحساب المرتبط")
        bot_me = await bot.get_me()
        if not bot_me.bot or not bot_me.username:
            raise RuntimeError("بوت الإدارة غير جاهز")
        token = secrets.token_urlsafe(18)
        inline_source_requests[token] = {
            "owner_id": owner_id,
            "expires_at": time.time() + 90,
            "menu": "tastir",
        }
        results = await client.inline_query(bot_me.username, f"demon_tastir_menu:{token}")
        if not results:
            inline_source_requests.pop(token, None)
            raise RuntimeError("لم تصل نتيجة قائمة التسطير المضمّنة")
        await results[0].click(chat_id)
        return True
    except Exception as e:
        bot_name = getattr(bot_me, "username", "بوت الإدارة") if "bot_me" in locals() else "بوت الإدارة"
        reason = f"{type(e).__name__}: {e}"
        print(f"\n[INLINE TASTIR MENU ERROR] {reason}\n")
        await client.send_message(chat_id, f"⚠️ تعذر إظهار قائمة التسطير عبر @{bot_name}.\n• السبب ← `{reason}`")
        return False


# ==================== Source Features: Self Save, Links & Statistics ====================
def get_self_save_destination(owner_id):
    """الأولوية: مجموعة ذاتية مخصصة، ثم آخر مجموعة تخزين، ثم الرسائل المحفوظة."""
    init_user_db(owner_id)
    info = users_db[owner_id]
    if info.get("self_save_chat_id"):
        return info["self_save_chat_id"]
    storage_groups = info.get("storage_groups", [])
    return storage_groups[-1] if storage_groups else "me"


def self_save_destination_text(owner_id):
    target = get_self_save_destination(owner_id)
    if target == "me":
        return "الرسائل المحفوظة"
    if users_db.get(owner_id, {}).get("self_save_chat_id") == target:
        return f"مجموعة الذاتية (`{target}`)"
    return f"مجموعة التخزين (`{target}`)"


async def save_media_to_self_destination(client, owner_id, message):
    target_chat_id = get_self_save_destination(owner_id)
    try:
        await client.forward_messages(target_chat_id, message)
        return target_chat_id
    except Exception:
        downloaded = await client.download_media(message, file=TEMP_DIR)
        if not downloaded:
            raise RuntimeError("تعذر حفظ الوسيط.")
        try:
            await client.send_file(target_chat_id, downloaded, caption=message.raw_text or "")
            return target_chat_id
        finally:
            _safe_remove(downloaded)


def estimated_creation_year(user_id):
    """تقدير تقريبي مبني على نطاقات آيديات تيليجرام، وليس تاريخاً رسمياً."""
    uid = abs(int(user_id))
    ranges = [
        (1_000_000, "2013 أو أقدم"),
        (10_000_000, "2014"),
        (50_000_000, "2015"),
        (100_000_000, "2016"),
        (200_000_000, "2017"),
        (400_000_000, "2018"),
        (700_000_000, "2019"),
        (1_000_000_000, "2020"),
        (1_500_000_000, "2021"),
        (2_500_000_000, "2022"),
        (4_000_000_000, "2023"),
    ]
    for maximum, year in ranges:
        if uid < maximum:
            return year
    return "أحدث من 2024"


async def get_user_entity_from_command(client, event, command_parts, private_peer=False):
    """يدعم الرد والمنشن والآيدي، ويستهدف الطرف الآخر تلقائياً في الخاص."""
    if event.reply_to_msg_id:
        reply = await event.get_reply_message()
        if reply and reply.sender_id:
            return await client.get_entity(reply.sender_id)
    if len(command_parts) > 1:
        return await client.get_entity(command_parts[1])
    if event.is_private or private_peer and event.is_private:
        return await event.get_chat()
    return await client.get_me()


async def build_direct_account_link(entity):
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}"
    return f"tg://openmessage?user_id={entity.id}"


async def build_account_inspection_report(client, target):
    """يجمع فقط بيانات الحساب التي يتيحها تيليجرام للحساب الطالب."""
    full = await client(GetFullUserRequest(target))
    full_user = getattr(full, "full_user", None)
    about = getattr(full_user, "about", None) or "ما عنده بايو"
    common_count = getattr(full_user, "common_chats_count", 0) or 0
    phone = getattr(full_user, "phone", None) or getattr(target, "phone", None)
    phone_text = phone if phone else "مخفي أو غير متاح"
    try:
        photos = await client(GetUserPhotosRequest(user_id=target, offset=0, max_id=0, limit=1))
        photo_count = int(getattr(photos, "count", len(getattr(photos, "photos", []) or [])))
    except Exception:
        photo_count = "غير متاح"

    # الحوار الخاص يعني أن الحساب ظاهر ضمن محادثات هذا الحساب، من دون كشف محتوى المحادثة.
    private_chat = False
    try:
        async for dialog in client.iter_dialogs(limit=None):
            if getattr(dialog.entity, "id", None) == target.id:
                private_chat = True
                break
    except Exception:
        pass

    flags = []
    if getattr(target, "verified", False):
        flags.append("موثّق")
    if getattr(target, "premium", False):
        flags.append("بريميوم")
    if getattr(target, "bot", False):
        flags.append("بوت")
    if getattr(target, "scam", False):
        flags.append("معلّم كمشبوه")
    if getattr(target, "fake", False):
        flags.append("معلّم كمزيّف")
    if getattr(target, "restricted", False):
        flags.append("مقيّد")
    if getattr(target, "deleted", False):
        flags.append("حساب محذوف")
    account_flags = "، ".join(flags) if flags else "حساب عادي"

    status_name = type(getattr(target, "status", None)).__name__
    status_map = {
        "UserStatusOnline": "متصل الآن",
        "UserStatusOffline": "غير متصل",
        "UserStatusRecently": "آخر ظهور مؤخراً",
        "UserStatusLastWeek": "آخر ظهور خلال أسبوع",
        "UserStatusLastMonth": "آخر ظهور خلال شهر",
        "UserStatusEmpty": "آخر ظهور مخفي",
    }
    status = status_map.get(status_name, "آخر ظهور غير متاح")
    name = f"{getattr(target, 'first_name', '') or ''} {getattr(target, 'last_name', '') or ''}".strip() or "بدون اسم"
    username = f"@{target.username}" if getattr(target, "username", None) else "ماعنده"
    link = await build_direct_account_link(target)
    creation = estimated_creation_year(target.id)
    return (
        "🔎 **كشف معلومات الحساب**\n\n"
        f"• الاسم: {name}\n"
        f"• الآيدي: `{target.id}`\n"
        f"• اليوزر: {username}\n"
        f"• رابط الحساب: [اضغط هنا]({link})\n"
        f"• رقم الهاتف: `{phone_text}`\n"
        f"• البايو: {about}\n"
        f"• القروبات المشتركة: `{common_count}`\n"
        f"• بينكم محادثة خاصة: {'نعم' if private_chat else 'لا'}\n"
        f"• صور الحساب: `{photo_count}`\n"
        f"• تاريخ الإنشاء التقديري: `{creation}`\n"
        f"• حالة الحساب: {account_flags}\n"
        f"• الظهور: {status}"
    )


# ذاكرة مؤقتة للقنوات والقروبات لتسريع العرض الفوري وعدم تكرار استعلامات تيليجرام البطيئة
_account_chat_lists_cache = {}

async def get_account_chat_lists(client, mode="all", force_refresh=False):
    """يعرض القنوات والسوبرقروبات والقروبات العادية بتهيئة سريعة وذاكرة مؤقتة ذكية."""
    client_id = id(client)
    cache_key = (client_id, mode)
    now = time.monotonic()
    
    if not force_refresh and cache_key in _account_chat_lists_cache:
        cached_time, cached_groups, cached_channels = _account_chat_lists_cache[cache_key]
        if now - cached_time < 300: # تخزين مؤقت لمدة 5 دقائق
            return cached_groups, cached_channels

    groups = []
    channels = []
    async for dialog in client.iter_dialogs(limit=300): # تحديد حد معقول لضمان السرعة الفورية
        entity = dialog.entity
        is_broadcast_channel = bool(getattr(entity, "broadcast", False) and not getattr(entity, "megagroup", False))
        is_group = bool(
            getattr(dialog, "is_group", False)
            or getattr(entity, "megagroup", False)
            or (not is_broadcast_channel and hasattr(entity, "participants_count"))
        )
        if not is_broadcast_channel and not is_group:
            continue

        is_owner = bool(getattr(entity, "creator", False))
        is_admin = is_owner or bool(getattr(getattr(entity, "admin_rights", None), "post_messages", False))
        if mode != "all":
            try:
                permissions = await client.get_permissions(entity, "me")
                is_owner = is_owner or bool(getattr(permissions, "is_creator", False))
                is_admin = is_admin or bool(getattr(permissions, "is_admin", False))
            except Exception:
                pass

        if mode == "owner" and not is_owner:
            continue
        if mode == "admin" and not is_admin:
            continue

        item = (getattr(entity, "title", None) or getattr(dialog, "name", None) or "بدون اسم", entity.id)
        if is_broadcast_channel:
            channels.append(item)
        else:
            groups.append(item)

    groups.sort(key=lambda item: str(item[0]).casefold())
    channels.sort(key=lambda item: str(item[0]).casefold())
    
    _account_chat_lists_cache[cache_key] = (now, groups, channels)
    return groups, channels


def format_account_chat_list(items, title, mode_label):
    if not items:
        return f"📂 **{title} {mode_label}:**\n\nلا توجد نتائج."
    visible = items[:45]
    rows = [f"**{index}.** {name} — `{chat_id}`" for index, (name, chat_id) in enumerate(visible, 1)]
    more = f"\n\n⚠️ تم عرض {len(visible)} من أصل {len(items)}." if len(items) > len(visible) else ""
    return f"📂 **{title} {mode_label}:**\n\n" + "\n".join(rows) + more


async def build_stats_report(client):
    me = await client.get_me()
    return (
        "📊 **إحصائياتي:**\n\n"
        f"• الاسم: {(me.first_name or '')} {(me.last_name or '')}\n"
        f"• الآيدي: `{me.id}`\n"
        f"• اليوزر: @{me.username if me.username else 'ماعنده'}\n"
        f"• عمليات النشر الشغالة: `{len(auto_publish_tasks)}`\n"
        f"• عمليات التسطير والريبلاي الشغالة: `{len(running_tasks)}`"
    )


CONVERSION_GUIDE = """⤾ اوامـر الصيـغ والتحويـل 💾
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .لصوره
≫ بـ بالرد على ‹ ملصـق - GIF › لتحويله الى صـورة 🖼

• .لملصق
≫ بـ بالرد على صـورة لتحويلها الى ملصـق 🎗

• .الصوت
≫ بـ بالرد على فيديو لـ استخراج الصـوت منه 🎧

• .لبصمه
≫ بـ بالرد على صوت لـ تحويله الى بصمـه 🎤"""

ID_GUIDE = """⤾ اوامـر الايـدي 💳
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .ايدي

•  الاستخـدام 💡
↞بـدون رد لعـرض معلوماتـك
↞بالـرد او بوضـع يوزر المستخدم مع الامـر لعـرض معلومـات مستخـدم"""

ACCOUNT_LINK_GUIDE = """⤾ اوامـر رابـط الحساب 🔗
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .رابط
↞ لجلب رابـط مباشـر للحسـاب

•  الاستخـدام 💡
↞ بالـرد على مستخـدم او بكتابه الايدي بعـد الامـر"""

CREATION_GUIDE = """⤾ اوامـر كشف تاريخ الانشاء 📆
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .الانشاء
↞ بالـرد على مستـخـدم او بكتابه الايـدي بعـد الامـر

↜ ملاحظـه ⚠️
↞ الحسابات ذات انشاء 2024 وأكثر سوف تظهر ك أحدث من 2024"""

AUTO_PUBLISH_GUIDE = """⤾ اوامــر النـشــر التـلـقـائـي 📍
‏⋆————‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 ›————⋆

← للنشر من داخـل المجمـوعة ↓
 • .نشر + عدد الثواني + عدد المرات + تحويل
 • .واو + عدد الثواني + عدد المرات + تحويل
 ↞ بالـرد علـى الرسالـه المـراد نشرهـا 🚀

↜ ملاحظة مهمة ⚠️
↞ إذا ما تبي رسالتك تتحول سواء كانت من قناة أو قروب أو حسابك الشخصي أو حساب شخص ما، لا تكتب كلمة تحويل في نهاية الأمر.
↞ عند كتابة تحويل في نهاية الأمر، سيحوّل النص أو الوسائط كما هي. وإذا كانت المجموعة تمنع تحويل محتوى القنوات أو رفض تيليجرام الإرسال، يتوقف النشر ويصلك السبب.

← للنشر من خارج المجمـوعة 🔥 ↓
 • .ستارت + عدد الثواني + عدد المرات + ايدي المجموعة + تحويل
 ↞ بالـرد على الرسالة المـراد نشـرها 🚀

↜ ملاحظة مهمة ⚠️
↞ كلمة تحويل اختيارية أيضاً في أمر ستارت؛ اتركها للنشر بدون تحويل، أو أضفها آخر الأمر للتحويل الطبيعي.

• ملاحظات هامـه ❕❔
1 - كـل اوامـر النشـر تدعم الملصقات المميزه ⭐ والوسائط حسب ما يسمح به تيليجرام.
2 - يمكنك الحصـول على ايدي المجموعات من هنا @is_idbot 🤖
3 - للنشـر بـدون توقـف ضـع عـدد مـرات 999

• .النشر الشغال
↞ لـ معـرفـة عمليات النشـر الشغالـه حاليا ⛄

• .بس
↞ لـ إيقـاف النشر التلقائي في مجموعه معينه 📌
↞ قـم بكتابـه الامـر داخل المجموعة

• .ايقاف النشر
↞ لـ إيقـاف جميـع عمليـات النشـر التلقـائـي المرتبطـة بـك 🎡"""

SELF_SAVE_GUIDE = """⤾ اوامــر حـفـظ الذاتـيه 🧧
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• حفظ الذاتية التلقائي يعمل دائماً للوسائط المؤقتة التي تصلك في الخاص.
↞ بدون تعيين مجموعة: تُحفظ في الرسائل المحفوظة.
↞ عند تعيين مجموعة ذاتية أو وجود مجموعة تخزين: تُحفظ في المجموعة بدلاً من المحفوظات.

• .انشاء مجموعة الذاتيه
↞ ينشئ قروباً خاصاً ويعيّنه لحفظ الذاتية.

• .تعيين مجموعة الذاتيه + آيدي أو رابط المجموعة
↞ لتعيين مجموعة موجودة كوجهة لحفظ الذاتية.

• .حذف مجموعة الذاتيه
↞ يلغي المجموعة المعيّنة؛ ثم يستخدم مجموعة التخزين إن وجدت، وإلا الرسائل المحفوظة.

• .ذاتيه
↞ بالرد على أي وسيط لحفظه فوراً في وجهة الذاتية الحالية.

• .مقيد أو .حفظ
↞ ضع رابط الرسالة لحفظ المحتوى المقيد في وجهة الذاتية الحالية."""

WELCOME_GUIDE = """⤾ اوامــر الترحيـب والـردود 🗳
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .تفعيل الترحيب
↞ لتفعـيل ترحيـب الخـاص في حسابـك 🎗

• .تعطيل الترحيب
↞ لتعطيل ترحيـب الخـاص في حسابـك 🪄

• .تعيين الترحيب
↞ لـ تعيين ترحيـب مخصص لحسابك 📩

• .تعيين صورة الترحيب
↞ لـ تعيين صورة مخصصه مـع الترحيـب 🗳

• .حذف صورة الترحيب
↞ لـ حـذف صـورة الترحيب 🗑️

• .جلب الترحيب
↞ لـ جلب الترحيـب الحالي لحسابك

• .تفعيل الردود
↞ لتفعـيل ردود موجـود فـي السـوبـرات 📮

• .تعطيل الردود
↞ لتعـطيل ردود موجـود فـي السـوبـرات 📪

↜ ملاحظـه ⚠️
↞ ردود موجـود هـي رد ذكـي يتـم إرساله عندمـا يقوم شخـص بعمل منشن لك بكلـمه موجـود او اكلك او مفعل نشر او ما يشابههم"""

STATS_GUIDE = """⤾ اوامــر عـرض قـروباتك 💬
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .قروباتي مالك
↞ لـ عـرض قائمة بجميع القروبات التي لديك صلاحية مالك فيها 🤴🏻

• .قروباتي ادمن
↞ لـ عـرض قائمة بجميع القروبات التي لديك صلاحية ادمن فيها 👮🏻‍♂

• .قروباتي الكل
↞ لـ عـرض قائمة بجميع القروبات الموجودة بحسابك 🔖

⤾ اوامــر عـرض قنواتـك 📢
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .قنواتي مالك
↞ لـ عـرض قائمة بجميع القنوات التي لديك صلاحية مالك فيها 🤴🏻

• .قنواتي ادمن
↞ لـ عـرض قائمة بجميع القنوات التي لديك صلاحية ادمن فيها 👮🏻‍♂

• .قنواتي الكل
↞ لـ عـرض قائمة بجميع القنوات الموجودة بحسابك 🔖

⤾ اوامــر عرض الاحصائيات 📊
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .احصائياتي
↞ لـ عـرض قائمة بجميع احصائيات الحساب 📈"""


# ==================== Source Sections: Download, Writing, Broadcast & Cleanup ====================
YOUTUBE_GUIDE = """⤾ اوامــر اليـوتيـوب 🎧
‏⋆ —— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › —— ⋆

• .يوت
↞ بكتابه نص البحث مع الامر
↞ لـ تنزيل الصـوت mp3 🎗

• .بحث
↞ بكتابه نص البحث مع الامر
↞ لـ البحـث داخل اليوتيوب بشكل inline

• .تحميل
↞ بـ وضع رابط فيديو مـع الامر
↞ لـ تحميل فيديو من اليوتيوب بالرابط 🎗

• .ريديت [ رابط ريديت ]
↞ لـ تحميل فيديو أو صورة من ريديت 🎗"""

TIKTOK_GUIDE = """⤾ اوامــر تحميل تيك توك 🔘
‏⋆ —— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › —— ⋆

• .تحميل
↞ بـ وضع رابـط افيديو بعد الامـر
↞ لـ تنزيل الفيديو من تيك توك 🎗"""

INSTAGRAM_GUIDE = """⤾ اوامــر تحميل انستغرام 🩸
‏⋆ —— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › —— ⋆

• .تحميل
↞ بـ وضـع رابـط الريلـز او الستـوري بعد الامـر
↞ لـ تنزيل الستوري او الريلز 🎗"""

PINTEREST_GUIDE = """⤾ اوامــر تحمـيل بنترست 🖼️
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .بنترست [ رابـط بنترست ]
↞ لـ تحميل صوره او فيديو من بنترست 📌"""

STORY_GUIDE = """⤾ اوامــر تحمـيل الستـوري 📥
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .ستوري [ رابـط الستـوري ]
↞ لـ تنزيـل ستـوري قنـاه او حسـاب 🏷"""

GITHUB_GUIDE = """⤾ اوامــر تحمـيل من قيثهوب 📥
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .مستودع [ رابـط المستـودع ]
↞ لـ تنزيـل مستودع من قيثهوب 📌"""

RESTRICTED_GUIDE = """⤾ اوامــر المحتـوى المقيد 🔑
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .مقيد أو .حفظ
↞ ضع رابط الرسالة بعد الأمر.
↞ يحفظ المحتوى في مجموعة الذاتية المعيّنة، أو مجموعة التخزين، أو الرسائل المحفوظة حسب إعدادك."""

WRITING_GUIDE = """⤾ اوامـر الخطـوط الـكتابـة ✍
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .اكتب [ النـص ]
← لكتـابة النـص على ورقه بخط اليد 📝

• .نسخ
≫ بكتابـة النص بعد الامـر بالـرد بالامر علـى الرسالـه
← لكتـابة النـص بـخط قابل للنسخ — يعمـل بالـرد او بـوضع النـص مـع الامـر

• .غامق
≫ بكتابـة النص بعد الامـر او بالـرد بالامر علـى الرسالـه
← لكتـابة النـص بـخط غـامق — يعمـل بالـرد او بـوضع النـص مـع الامـر

• .مائل
← لكتـابة النـص بـخط مائـل — يعمـل بالـرد او بـوضع النـص مـع الامـر"""

BROADCAST_GUIDE = """⤾ اوامــر الاذاعــه 🎙
‏⋆ —— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › —— ⋆

• .اذاعه
↞ بالـرد على النص المراد اذاعته
↞ يقـوم بإرسـال الرسـاله الـى كل الخـاص عنـدك 📢

↞تقدر تحدد العدد الي تريد ترسل له الاذاعه بكتابه العدد المطلوب مع الامر مثال :

• .اذاعه 30
• بالرد على الرساله الي تريد ترسلها

• .ايقاف الاذاعه
↞ يقـوم بايقـاف الاذاعـه في حال كانت تعمل 💡"""

LEAVE_CLEANUP_GUIDE = """⤾ اوامــر المغـادرة والتصفيـه 🚶🏻
‏⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .مغادرة القنوات
↞ لـ الخـروج مـن جميـع القنـوات الموجودة بحسابك 📢

• .مغادرة القروبات
↞ لـ الخـروج مـن جميع القروبات الموجودة بحسابك 💬

• .تصفية الخاص
↞ لـ مسـح جميع الدردشـات الخاصـه 👤

• .تصفية البوتات
↞ لـ تصفيـة جميع البوتات الموجودة بحسابك 🤖"""


def _safe_title(text, limit=80):
    return re.sub(r"[^\w\-]+", "_", text or "file")[:limit]


async def _ytdlp_download(url, audio_only=False):
    stamp = str(int(time.time() * 1000))
    template = os.path.join(TEMP_DIR, f"download_{stamp}.%(ext)s")
    options = {
        "outtmpl": template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 12,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
        "concurrent_fragment_downloads": 4,
        "http_chunk_size": 10 * 1024 * 1024,
        "format": "bestaudio/best" if audio_only else "best[height<=720][ext=mp4]/best[height<=720]/best",
    }
    if audio_only:
        options["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}]
    loop = asyncio.get_running_loop()

    def worker():
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info), info

    predicted, info = await loop.run_in_executor(None, worker)
    if audio_only:
        base = os.path.splitext(predicted)[0]
        expected = base + ".mp3"
        if os.path.exists(expected):
            predicted = expected
    if not os.path.exists(predicted):
        candidates = sorted(Path(TEMP_DIR).glob(f"download_{stamp}*"), key=lambda item: item.stat().st_mtime)
        if not candidates:
            raise RuntimeError("لم يتم العثور على الملف بعد التحميل.")
        predicted = str(candidates[-1])
    return predicted, info


async def download_and_send_url(client, chat_id, url, audio_only=False):
    file_path = None
    try:
        file_path, info = await _ytdlp_download(url, audio_only=audio_only)
        caption = (info.get("title") or "تم التحميل")[:900]
        await client.send_file(chat_id, file_path, caption=caption, voice_note=False)
    finally:
        _safe_remove(file_path)



async def download_github_repository(client, chat_id, url):
    parsed = urllib.parse.urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() not in ["github.com", "www.github.com"] or len(parts) < 2:
        raise ValueError("أرسل رابط مستودع GitHub صحيحاً.")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    target = os.path.join(TEMP_DIR, f"{_safe_title(owner)}_{_safe_title(repo)}.zip")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"

    def fetch():
        response = requests.get(api_url, timeout=60, headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        with open(target, "wb") as out:
            out.write(response.content)

    try:
        await asyncio.to_thread(fetch)
        await client.send_file(chat_id, target, caption=f"📦 مستودع {owner}/{repo}")
    finally:
        _safe_remove(target)


async def save_restricted_message(client, chat_id, url):
    match = re.search(r"https?://t\.me/(c/)?([^/?#]+)/([0-9]+)", url)
    if not match:
        raise ValueError("أرسل رابط رسالة تيليجرام صحيحاً.")
    is_private, peer_name, message_id = match.groups()
    peer = int(f"-100{peer_name}") if is_private else peer_name
    entity = await client.get_entity(peer)
    message = await client.get_messages(entity, ids=int(message_id))
    if not message:
        raise ValueError("لم يتم العثور على الرسالة أو لا يملك الحساب صلاحية الوصول إليها.")
    try:
        await client.forward_messages(chat_id, message)
    except Exception:
        if message.media:
            temp = await client.download_media(message, file=TEMP_DIR)
            try:
                await client.send_file(chat_id, temp, caption=message.text or "")
            finally:
                _safe_remove(temp)
        elif message.text:
            await client.send_message(chat_id, message.text)
        else:
            raise RuntimeError("تعذر حفظ محتوى الرسالة.")


async def download_telegram_story(client, chat_id, url):
    match = re.search(r"https?://t\.me/([^/?#]+)/s/([0-9]+)", url)
    if not match:
        match = re.search(r"https?://t\.me/([^/?#]+)/([0-9]+)", url)
    if not match:
        raise ValueError("أرسل رابط ستوري تيليجرام صحيحاً.")
    username, story_id = match.groups()
    from telethon.tl.functions.stories import GetStoriesByIDRequest
    entity = await client.get_entity(username)
    result = await client(GetStoriesByIDRequest(peer=entity, id=[int(story_id)]))
    stories = getattr(result, "stories", [])
    if not stories:
        raise ValueError("تعذر العثور على الستوري أو لا يملك الحساب صلاحية الوصول إليها.")
    story = stories[0]
    if not getattr(story, "media", None):
        raise ValueError("الستوري لا يحتوي على وسيط قابل للتنزيل.")
    await client.send_file(chat_id, story.media, caption=getattr(story, "caption", "") or "")


def extract_text_argument(text, command):
    value = text[len(command):].strip()
    return value


async def get_command_text(event, text, command):
    value = extract_text_argument(text, command)
    if value:
        return value
    if event.reply_to_msg_id:
        reply = await event.get_reply_message()
        if reply and reply.raw_text:
            return reply.raw_text.strip()
    return ""


TRANSLATION_COMMANDS = {
    "عربي": ("ar", "العربية"),
    "انجليزي": ("en", "الإنجليزية"),
    "روسي": ("ru", "الروسية"),
    "فرنسي": ("fr", "الفرنسية"),
    "تركي": ("tr", "التركية"),
    "هندي": ("hi", "الهندية"),
    "الماني": ("de", "الألمانية"),
    "كردي": ("ku", "الكردية"),
    "فارسي": ("fa", "الفارسية"),
}

TRANSLATION_GUIDE = """⤾ اوامــر الـترجـمـة 🏧
⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆

• .عربي
• .انجليزي
• .روسي
• .فرنسي
• .تركي
• .هندي
• .الماني
• .كردي
• .فارسي

•  الاستخـدام 💡
↞ قـم بالـرد على الرساله بالامـر أو بكتابه النـص بعد الامـر"""


def _translate_text_sync(text, target_language):
    response = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": f"autodetect|{target_language}"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    translated = (payload.get("responseData") or {}).get("translatedText")
    if not translated:
        raise RuntimeError("خدمة الترجمة لم تُرجع نصاً قابلاً للعرض.")
    return translated


async def translate_text(text, target_language):
    if not text or not text.strip():
        raise ValueError("أرسل النص بعد الأمر أو رد على رسالة نصية.")
    clean_text = text.strip()
    cache_key = (clean_text, target_language)
    now = time.monotonic()
    cached = _translation_cache.get(cache_key)
    if cached and now - cached[0] < 900:
        return cached[1]
    translated = await asyncio.to_thread(_translate_text_sync, clean_text, target_language)
    _translation_cache[cache_key] = (now, translated)
    if len(_translation_cache) > 300:
        oldest = sorted(_translation_cache.items(), key=lambda item: item[1][0])[:80]
        for key, _ in oldest:
            _translation_cache.pop(key, None)
    return translated


async def make_handwriting_image(client, chat_id, value):
    if Image is None:
        raise RuntimeError("مكتبة Pillow غير مثبّتة. نفذ: pip install pillow")
    width, height = 1200, max(400, 260 + (len(value) // 35) * 65)
    image = Image.new("RGB", (width, height), "#f8f2dd")
    draw = ImageDraw.Draw(image)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        font = ImageFont.truetype(font_path, 46)
    except Exception:
        font = ImageFont.load_default()
    draw.rectangle((30, 30, width - 30, height - 30), outline="#b18a5a", width=3)
    draw.multiline_text((80, 95), value, fill="#26201b", font=font, spacing=22, align="right")
    output = os.path.join(TEMP_DIR, f"handwriting_{int(time.time() * 1000)}.png")
    try:
        image.save(output)
        await client.send_file(chat_id, output, caption="📝 الكتابة")
    finally:
        _safe_remove(output)


async def start_broadcast_task(client, owner_id, source_message, limit):
    previous = broadcast_tasks.get(owner_id)
    if previous and not previous.done():
        previous.cancel()

    async def worker():
        delivered = 0
        failed = 0
        try:
            me = await client.get_me()
            async for dialog in client.iter_dialogs(limit=None):
                entity = dialog.entity
                if delivered >= limit:
                    break
                if not getattr(entity, "bot", False) and getattr(dialog, "is_user", False) and getattr(entity, "id", None) != me.id:
                    try:
                        await client.forward_messages(entity, source_message)
                        delivered += 1
                        await asyncio.sleep(0.8)
                    except Exception:
                        failed += 1
            total = delivered + failed
            await client.send_message(
                owner_id,
                f"✅ **انتهت إذاعة قسم الحساب.**\n\n• تم الإرسال بنجاح: `{delivered}` شخصاً\n• فشل الإرسال: `{failed}` شخصاً\n• إجمالي من تمت معالجتهم: `{total}` شخصاً"
            )
        except asyncio.CancelledError:
            try:
                total = delivered + failed
                await client.send_message(
                    owner_id,
                    f"⏹️ **تم إيقاف إذاعة قسم الحساب.**\n\n• تم الإرسال قبل الإيقاف: `{delivered}` شخصاً\n• فشل الإرسال: `{failed}` شخصاً\n• إجمالي من تمت معالجتهم: `{total}` شخصاً"
                )
            except Exception:
                pass
            raise
        finally:
            broadcast_tasks.pop(owner_id, None)

    task = asyncio.create_task(worker())
    broadcast_tasks[owner_id] = task


async def bulk_account_action(client, owner_id, action):
    count = 0
    me = await client.get_me()
    async for dialog in client.iter_dialogs(limit=None):
        entity = dialog.entity
        try:
            if action == "leave_channels" and getattr(entity, "broadcast", False):
                await client(LeaveChannelRequest(entity))
                count += 1
            elif action == "leave_groups" and getattr(entity, "megagroup", False):
                await client(LeaveChannelRequest(entity))
                count += 1
            elif action == "clear_private" and getattr(dialog, "is_user", False) and not getattr(entity, "bot", False) and entity.id != me.id:
                await client.delete_dialog(entity, revoke=True)
                count += 1
            elif action == "clear_bots" and getattr(dialog, "is_user", False) and getattr(entity, "bot", False):
                await client.delete_dialog(entity, revoke=True)
                count += 1
        except Exception:
            pass
    return count


async def get_cached_user_me(client_inst, owner_id):
    """يتجنب طلب get_me من تيليجرام مع كل أمر أو رسالة."""
    cached = _user_me_cache.get(owner_id)
    now = time.monotonic()
    if cached and now - cached[0] < 900:
        return cached[1]
    me = await client_inst.get_me()
    _user_me_cache[owner_id] = (now, me)
    return me


async def cancel_all_user_operations(client, owner_id):
    """يلغي أي حالة إدخال أو عملية مرتبطة بصاحب الحساب، ويعيد ملخصاً قصيراً."""
    pending_cancelled = user_states.pop(owner_id, None) is not None

    running_before = sum(1 for info in running_tasks.values() if info.get("owner_id") == owner_id)
    stop_running_task(owner_id)

    publish_stopped = 0
    if client:
        try:
            publish_stopped = await stop_auto_publish_task(client, owner_id, reason="تم الإلغاء بالأمر .الغاء")
        except Exception:
            pass

    try:
        flush_stopped = await stop_manual_flush_tasks(owner_id)
    except Exception:
        flush_stopped = 0

    broadcast_stopped = 0
    task = broadcast_tasks.pop(owner_id, None)
    if task and not task.done():
        task.cancel()
        broadcast_stopped = 1

    bot_flush_stopped = 0
    for key, task in list(bot_flush_tasks.items()):
        if key[0] != owner_id:
            continue
        if task and not task.done():
            task.cancel()
            bot_flush_stopped += 1
        bot_flush_tasks.pop(key, None)

    total = running_before + publish_stopped + flush_stopped + broadcast_stopped + bot_flush_stopped
    return pending_cancelled, total


async def register_userbot_events(client_inst, owner_id):
    @client_inst.on(events.NewMessage)
    async def userbot_handler(event):
        # تجاهل تام لأي رسالة صادرة من البوت أو مرسلة إليه لمنع التداخل
        if event.chat_id in manager_bot_id or event.sender_id in manager_bot_id:
            return

        chat_id = event.chat_id
        text = event.raw_text.strip() if event.raw_text else ""
        me = await get_cached_user_me(client_inst, owner_id)

        # في القناة قد يكون مرسل المنشور هو آيدي القناة، لكن event.out يثبت أن المنشور من حساب المستخدم.
        if event.out and (event.sender_id == me.id or event.is_channel):
            init_user_db(owner_id)
            user_info = users_db[owner_id]

            # نتيجة أي أمر مكتوب بالرد تعود إلى الرسالة نفسها؛ من دون رد تبقى رسالة عادية.
            command_reply_to = event.reply_to_msg_id

            async def command_reply(message, **kwargs):
                # تستخدم النتائج المهمة هذا الخيار لتبقى في المحادثة بدلاً من الحذف المؤقت.
                keep_result = bool(kwargs.pop("keep_result", False))
                temporary_seconds = kwargs.pop("temporary_seconds", None)
                if command_reply_to and "reply_to" not in kwargs:
                    kwargs["reply_to"] = command_reply_to
                outgoing_message = message
                if isinstance(message, str) and "formatting_entities" not in kwargs and not kwargs.get("buttons"):
                    outgoing_message, premium_entities = prepare_premium_command_message(message)
                    if premium_entities:
                        kwargs["formatting_entities"] = premium_entities
                        kwargs["parse_mode"] = None
                sent_message = await client_inst.send_message(chat_id, outgoing_message, **kwargs)
                # لا تحذف القوائم والأزرار أو رسائل التقدم، ولا نتائج الترجمة والتحويل النهائية.
                message_text = str(message or "")
                is_progress = message_text.startswith(("⏳", "🔍", "⚡", "📊"))
                raw_command = (event.raw_text or "").lstrip(".").strip().split()
                translation_result = bool(raw_command and raw_command[0] in TRANSLATION_COMMANDS)
                if not keep_result and not translation_result and not kwargs.get("buttons") and not is_progress:
                    action_commands = {"انتحال", "كشف", "ايدي", "رابط", "الانشاء", "تثبيت", "الغاء", "إلغاء", "كتم"}
                    wait_seconds = int(temporary_seconds) if temporary_seconds is not None else (10 if command_reply_to or (raw_command and raw_command[0] in action_commands) else 4)
                    asyncio.create_task(delete_message_after(sent_message, wait_seconds))
                return sent_message

            async def send_empty_tastir_notice_private(message):
                # هذا التنبيه لا يظهر في الشات الذي كُتب فيه الأمر حتى لا يزعج الطرف الآخر.
                # يرسل فقط إلى خاص بوت الإدارة لصاحب الحساب الذي شغّل الأمر.
                try:
                    await bot.send_message(owner_id, message)
                except Exception:
                    pass

            async def command_reply_file(file, **kwargs):
                if command_reply_to and "reply_to" not in kwargs:
                    kwargs["reply_to"] = command_reply_to
                return await client_inst.send_file(chat_id, file, **kwargs)
            
            # أمر إلغاء موحد: يوضع قبل حالات الإدخال كي لا يُحفظ كنص أو إعداد بالخطأ.
            if text in (".الغاء", ".إلغاء"):
                pending_cancelled, stopped_count = await cancel_all_user_operations(client_inst, owner_id)
                try:
                    await event.delete()
                except Exception:
                    pass
                if pending_cancelled or stopped_count:
                    await command_reply(f"✅ تم الإلغاء بنجاح.\n• تم إلغاء حالة إدخال: {'نعم' if pending_cancelled else 'لا'}\n• العمليات المتوقفة: `{stopped_count}`")
                else:
                    await command_reply("ℹ️ لا توجد عملية أو حالة إدخال نشطة لإلغائها.")
                return

            # إدخالات الأوامر اليدوية التي تبدأ في محادثة معينة تبقى فيها.
            pending_local = user_states.get(owner_id)
            if pending_local and pending_local.get("origin_chat_id") == chat_id:
                # نتجاهل رسالة الطلب التي يرسلها البوت بنفسه حتى لا تُحفظ كنص ترحيب.
                if pending_local.get("ignore_message_id") == event.id:
                    return
                pending_step = pending_local.get("step")
                if pending_step == "awaiting_welcome_text_local":
                    if not text:
                        await command_reply( "⚠️ أرسل نص الترحيب أولاً.")
                        return
                    user_info["welcome_text"] = text
                    save_data()
                    user_states.pop(owner_id, None)
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    await command_reply( "✅ تم تعيين نص الترحيب بنجاح.")
                    return

                if pending_step == "awaiting_welcome_photo_local":
                    if not event.photo:
                        await command_reply( "⚠️ أرسل **صورة** فقط لتعيينها كصورة ترحيب.")
                        return
                    old_photo = user_info.get("welcome_photo")
                    _safe_remove(old_photo)
                    photo_path = os.path.join(TEMP_DIR, f"welcome_{owner_id}.jpg")
                    await client_inst.download_media(event.message, file=photo_path)
                    user_info["welcome_photo"] = photo_path
                    save_data()
                    user_states.pop(owner_id, None)
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    await command_reply( "✅ تم تعيين صورة الترحيب بنجاح.")
                    return

            t_start = user_info.get("tastir_start_cmds", [])
            t_stop = user_info.get("tastir_stop_cmds", [])
            f_start = user_info.get("fardiyyat_start_cmds", [])
            f_stop = user_info.get("fardiyyat_stop_cmds", [])
            r_start = user_info.get("reply_start_cmds", [])
            r_stop = user_info.get("reply_stop_cmds", [])
            n_stop = user_info.get("nick_am_stop_cmds", [])
            m_cmds = user_info.get("mute_cmds", [])
            um_cmds = user_info.get("unmute_cmds", [])
            p_cmds = user_info.get("purge_cmds", [])
            p_all_cmds = user_info.get("purge_all_cmds", [])

            # ===== قائمة قسم التسطير: تعمل بالنقطة فقط وتظهر عبر بوت ديمون =====
            # يوضع هذا الشرط قبل الأوامر القديمة حتى لا يتعارض مع أي أمر تشغيل مخصص باسم «التسطير».
            if text == ".التسطير":
                if not is_subscribed(owner_id):
                    await command_reply( "⚠️ هذه القائمة خاصة بالمشتركين في التسطير. فعّل كود اشتراك التسطير أولاً.")
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                await send_tastir_commands_menu(client_inst, owner_id, chat_id)
                return

            # ===== الأوامر القديمة: تعمل بالنقطة أو بدونها =====
            # التسطير والفرديات والريبلاي والكتم من مميزات الحساب القديمة، وليست مميزات سورس.

            # ===== ميزات الذكاء الاصطناعي والأصوات الواقعية =====
            if text in (".تفعيل الذكاء الاصطناعي", "تفعيل الذكاء الاصطناعي"):
                if not is_source_subscribed(owner_id):
                    msg = await command_reply(source_lock_message())
                    asyncio.create_task(delete_message_after(msg, 6))
                    return
                user_info["ai_chat_enabled"] = True
                save_data()
                try:
                    await event.delete()
                except Exception:
                    pass
                msg = await command_reply("🤖 **تم تفعيل الذكاء الاصطناعي بنجاح.**\n\nاستخدم الآن: `.ذكاء [سؤالك]`")
                asyncio.create_task(delete_message_after(msg, 6))
                return

            if text in (".تعطيل الذكاء الاصطناعي", "تعطيل الذكاء الاصطناعي"):
                user_info["ai_chat_enabled"] = False
                save_data()
                try:
                    await event.delete()
                except Exception:
                    pass
                msg = await command_reply("🛑 **تم تعطيل الذكاء الاصطناعي.**")
                asyncio.create_task(delete_message_after(msg, 6))
                return

            if text.startswith(".ذكاء ") or text.startswith("ذكاء "):
                if not is_source_subscribed(owner_id):
                    msg = await command_reply(source_lock_message())
                    asyncio.create_task(delete_message_after(msg, 6))
                    return
                if not user_info.get("ai_chat_enabled", False):
                    msg = await command_reply("⚠️ الذكاء الاصطناعي معطل. اكتب أولاً: `.تفعيل الذكاء الاصطناعي`")
                    asyncio.create_task(delete_message_after(msg, 6))
                    return
                prompt = text.split(" ", 1)[1].strip()
                if not prompt:
                    msg = await command_reply("⚠️ اكتب سؤالك أو طلبك بعد الأمر.")
                    asyncio.create_task(delete_message_after(msg, 6))
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                wait_msg = await client_inst.send_message(chat_id, "🤖 جاري التفكير...")
                result = await ask_sarcastic_ai(prompt, owner_id)
                try:
                    await wait_msg.delete()
                except Exception:
                    pass
                if result.get("type") == "image" and result.get("url"):
                    await client_inst.send_file(chat_id, result["url"], caption=result.get("text", ""), reply_to=event.reply_to_msg_id)
                else:
                    await client_inst.send_message(chat_id, result.get("text", "⚠️ تعذر الحصول على رد الآن."), reply_to=event.reply_to_msg_id)
                return

            # ===== أصوات البنات الواقعية المتاحة =====
            voice_match = re.match(r"^\.?بنت\s*([1-7])\s*(.*)", text)
            if voice_match:
                v_num, v_text = voice_match.groups()
                voice_key = f"بنت {v_num}"
                final_text = v_text.strip()
                if not final_text and event.reply_to_msg_id:
                    rep_msg = await event.get_reply_message()
                    if rep_msg and rep_msg.text:
                        final_text = rep_msg.text
                if not final_text:
                    msg = await command_reply(f"⚠️ اكتب نصاً بعد أمر {voice_key} أو رد على رسالة.")
                    asyncio.create_task(delete_message_after(msg, 6))
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                wait_msg = await client_inst.send_message(chat_id, f"🎙️ جاري توليد فويس ({voice_key})...")
                audio_path = await generate_ai_voice_audio_v2(final_text, voice_key)
                try:
                    await wait_msg.delete()
                except Exception:
                    pass
                if audio_path:
                    from telethon.tl.types import DocumentAttributeAudio
                    duration = 5
                    try:
                        from pydub import AudioSegment
                        duration = max(1, int(len(AudioSegment.from_file(audio_path)) / 1000))
                    except Exception:
                        pass
                    await client_inst.send_file(
                        chat_id,
                        audio_path,
                        voice_note=True,
                        force_document=False,
                        mime_type="audio/ogg",
                        attributes=[DocumentAttributeAudio(duration=duration, voice=True)],
                        reply_to=event.reply_to_msg_id,
                    )
                    _safe_remove(audio_path)
                else:
                    msg = await command_reply("❌ فشل توليد الفويس. تحقق من رصيد ElevenLabs أو الاتصال.")
                    asyncio.create_task(delete_message_after(msg, 6))
                return

            legacy_text = text[1:].strip() if text.startswith(".") else text.strip()
            legacy_parts = legacy_text.split()
            legacy_first_word = legacy_parts[0] if legacy_parts else ""
            t_start = normalize_command_list(t_start, [])
            t_stop = normalize_command_list(t_stop, [])
            f_start = normalize_command_list(f_start, [])
            f_stop = normalize_command_list(f_stop, [])
            r_start = normalize_command_list(r_start, [])
            r_stop = normalize_command_list(r_stop, [])
            n_stop = normalize_command_list(n_stop, [])
            m_cmds = normalize_command_list(m_cmds, [])
            um_cmds = normalize_command_list(um_cmds, [])

            legacy_target_msg_id = event.reply_to_msg_id
            legacy_target_user_id = None
            if event.is_private:
                legacy_target_user_id = chat_id
                legacy_target_msg_id = None
            elif legacy_target_msg_id:
                legacy_reply = await event.get_reply_message()
                if legacy_reply:
                    legacy_target_user_id = legacy_reply.sender_id

            nick_am_command = "نيك ام" if (legacy_text == "نيك ام" or legacy_text.startswith("نيك ام ")) else None
            if nick_am_command:
                # عند التعطيل نتجاهل العبارة بصمت حتى لا تتداخل مع الحديث العادي.
                if not user_info.get("nick_am_enabled", False):
                    return
                nick_prefix = legacy_text[len(nick_am_command):].strip()
                nick_prefix, nick_target_msg_id, nick_target_user_id, nick_target_style = await resolve_nick_am_launch(
                    event, nick_prefix, legacy_target_msg_id, legacy_target_user_id
                )
                if not nick_prefix:
                    await command_reply("⚠️ يجب كتابة اسم بعد أمر نيك ام.")
                    return
                started = start_running_task(
                    client_inst, owner_id, chat_id, "nick_am", nick_target_msg_id,
                    nick_target_user_id, nick_prefix=nick_prefix, nick_target_style=nick_target_style,
                )
                if not started:
                    await send_empty_tastir_notice_private("⚠️ لا توجد نصوص نشطة لنيك ام. أضف نصاً أو فعّل تضمين التسطير أو الفرديات.")
                return

            if legacy_text in t_start:
                if user_info.get("del_tastir_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                started = start_running_task(client_inst, owner_id, chat_id, "tastir", legacy_target_msg_id, legacy_target_user_id)
                if not started:
                    await send_empty_tastir_notice_private("⚠️ لا توجد جمل تسطير محفوظة. أضف جملة أولاً من زر «إضافة جمل التسطير».")
                return

            if legacy_text in f_start:
                if user_info.get("del_fardiyyat_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                started = start_running_task(client_inst, owner_id, chat_id, "fardiyyat", legacy_target_msg_id, legacy_target_user_id)
                if not started:
                    await send_empty_tastir_notice_private("⚠️ لا توجد كلمات فرديات محفوظة. أضف كلمة أولاً من زر «إضافة كلمات الفرديات».")
                return

            if legacy_text in r_start:
                if user_info.get("del_reply_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                if not legacy_target_user_id or legacy_target_user_id in manager_bot_id:
                    await command_reply( "⚠️ الريبلاي يحتاج الرد على رسالة شخص داخل القروب أو الخاص، ولا يعمل في محادثة بوت الإدارة.")
                    return
                if not (user_info.get("reply", []) or default_reply or user_info.get("tastir", []) or default_tastir or user_info.get("fardiyyat", []) or default_fardiyyat):
                    await send_empty_tastir_notice_private("⚠️ لا توجد جمل ريبلاي أو تسطير أو فرديات محفوظة لإرسالها.")
                    return
                operation_id = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")
                task_key = (owner_id, chat_id, legacy_target_user_id, "reply", operation_id)
                running_tasks[task_key] = {"task": None, "owner_id": owner_id, "chat_id": chat_id, "target_user_id": legacy_target_user_id, "mode": "reply", "target_msg_id": legacy_target_msg_id, "operation_id": operation_id, "started_at": time.time()}
                return

            if legacy_text in t_stop:
                if user_info.get("del_tastir_stop", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                stop_running_task(owner_id, chat_id, target_user_id=legacy_target_user_id, mode="tastir")
                return

            if legacy_text in f_stop:
                if user_info.get("del_fardiyyat_stop", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                stop_running_task(owner_id, chat_id, target_user_id=legacy_target_user_id, mode="fardiyyat")
                return

            if legacy_text in n_stop:
                if user_info.get("del_nick_am_stop", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                stop_running_task(owner_id, chat_id, target_user_id=legacy_target_user_id, mode="nick_am")
                return

            if legacy_text in r_stop:
                if user_info.get("del_reply_stop", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                stop_running_task(owner_id, chat_id, target_user_id=legacy_target_user_id, mode="reply")
                return

            if legacy_text in m_cmds or legacy_first_word in m_cmds:
                if user_info.get("del_mute_cmd", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                target_uid = await resolve_target_user(event)
                if target_uid and target_uid != me.id and target_uid not in manager_bot_id and target_uid not in user_info["muted_users"]:
                    user_info["muted_users"].append(target_uid)
                    save_data()
                return

            if legacy_text in um_cmds or legacy_first_word in um_cmds:
                if user_info.get("del_unmute_cmd", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                target_uid = await resolve_target_user(event)
                if target_uid and target_uid in user_info["muted_users"]:
                    user_info["muted_users"].remove(target_uid)
                    save_data()
                return

            # أوامر السورس، ومن ضمنها .الاوامر، لا تعمل إلا بالنقطة.
            if not text.startswith("."):
                return
            text = legacy_text
            cmd_parts = text.split()
            cmd_first_word = cmd_parts[0] if cmd_parts else ""

            # ===== تفعيل تلقائي آمن: الكود يفعّل فقط عندما يرسله صاحب الحساب من حسابه =====
            if len(cmd_parts) == 1 and re.fullmatch(r"(?:PBL|SRC|ALL)-[A-Za-z0-9_-]+", text, flags=re.IGNORECASE):
                code = text.upper()
                kind, days = await apply_any_activation_code(owner_id, code, event)
                if kind:
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    result_text = {
                        "tastir": f"✅ تم تفعيل اشتراك التسطير تلقائياً لمدة {days} يوم.",
                        "source": f"✅ تم تفعيل مميزات السورس تلقائياً لمدة {days} يوم.",
                        "all": f"✅ تم تفعيل جميع الصلاحيات تلقائياً لمدة {days} يوم. تم تفعيل التسطير ومميزات السورس معاً.",
                    }[kind]
                    await command_reply( result_text)
                return

            # ===== أوامر مميزات السورس الجديدة =====
            if text == "الاوامر":
                # كل حساب مرتبط ومشترك يعرض قائمته بنفسه؛ لا توجد أي صلاحية خاصة بالمطور هنا.
                if not has_any_subscription(owner_id):
                    await command_reply( source_lock_message())
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                if is_source_subscribed(owner_id):
                    await send_source_commands_menu(client_inst, owner_id, chat_id)
                else:
                    # مشترك التسطير فقط يحصل على قائمة التسطير بدلاً من قائمة السورس المقفلة.
                    await send_tastir_commands_menu(client_inst, owner_id, chat_id)
                return

            if text == "انتحال" or text.startswith("انتحال "):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    target_id = await resolve_target_user(event)
                    if not target_id:
                        await command_reply( "❌ استخدم الأمر بالرد على شخص أو اكتب: `.انتحال @username`")
                        return
                    target = await client_inst.get_entity(target_id)
                    if not getattr(target, "first_name", None):
                        await command_reply( "❌ هذا الهدف ليس حساب مستخدم.")
                        return
                    await event.delete()
                    status = await command_reply( "⏳ جاري تطبيق بيانات المظهر...")
                    target_name = await apply_profile_template(client_inst, owner_id, target)
                    await status.edit("✅ **تم الانتحال بنجاح.**\n↩️ اكتب `.اعاده` لإرجاع النسخة المحفوظة.")
                    asyncio.create_task(delete_message_after(status, 10))
                except Exception as e:
                    await command_reply( f"❌ تعذر تطبيق بيانات المظهر:\n`{e}`")
                return

            if text == "اعاده":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                status = await command_reply( "⏳ جاري إعادة بيانات حسابك المحفوظة...")
                try:
                    await restore_profile_template(client_inst, owner_id)
                    await status.edit("✅ تمت إعادة بيانات حسابك المحفوظة.")
                    asyncio.create_task(delete_message_after(status, 4))
                except Exception as e:
                    await status.edit(f"❌ تعذرت الإعادة:\n`{e}`")
                return

            if text == "تفعيل الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                user_info["welcome_enabled"] = True
                save_data()
                await event.delete()
                await command_reply( "✅ تم تفعيل الترحيب الخاص.")
                return

            if text == "تعطيل الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                user_info["welcome_enabled"] = False
                save_data()
                await event.delete()
                await command_reply( "✅ تم تعطيل الترحيب الخاص.")
                return

            if text == "تعيين الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                prompt = await command_reply("📝 أرسل نص الترحيب الجديد الآن في نفس هذه المحادثة:", temporary_seconds=10)
                user_states[owner_id] = {"step": "awaiting_welcome_text_local", "origin_chat_id": chat_id, "ignore_message_id": prompt.id}
                return

            if text == "تعيين صورة الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                prompt = await command_reply("🖼️ أرسل صورة الترحيب الجديدة الآن في نفس هذه المحادثة:", temporary_seconds=10)
                user_states[owner_id] = {"step": "awaiting_welcome_photo_local", "origin_chat_id": chat_id, "ignore_message_id": prompt.id}
                return

            if text == "حذف صورة الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                _safe_remove(user_info.get("welcome_photo"))
                user_info["welcome_photo"] = None
                save_data()
                await event.delete()
                await command_reply( "✅ تم حذف صورة الترحيب.")
                return

            if text == "جلب الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                current_welcome = user_info.get("welcome_text", "أهلاً بك، نورت الخاص.")
                await command_reply( f"📋 **نص الترحيب الحالي:**\n\n{current_welcome}")
                photo_path = user_info.get("welcome_photo")
                if photo_path and os.path.exists(photo_path):
                    await command_reply_file( photo_path)
                return

            if text == "تفعيل الردود":
                if not is_source_subscribed(owner_id):
                    return
                user_info["smart_replies_enabled"] = True
                save_data()
                await event.delete()
                await command_reply( "✅ تم تفعيل ردود موجود.")
                return

            if text == "تعطيل الردود":
                if not is_source_subscribed(owner_id):
                    return
                user_info["smart_replies_enabled"] = False
                save_data()
                await event.delete()
                await command_reply( "✅ تم تعطيل ردود موجود.")
                return

            if cmd_first_word in ["نشر", "واو", "ستارت"]:
                if not is_source_subscribed(owner_id):
                    return
                if not event.reply_to_msg_id:
                    await command_reply( "❌ يجب الرد على الرسالة المراد نشرها ثم كتابة الأمر.")
                    return
                try:
                    forward_mode = cmd_parts[-1] == "تحويل"
                    clean_parts = cmd_parts[:-1] if forward_mode else cmd_parts
                    if cmd_first_word in ["نشر", "واو"]:
                        if len(clean_parts) != 3:
                            raise ValueError("الصيغة: `.نشر عدد_الثواني عدد_المرات [تحويل]`")
                        target_chat_id = chat_id
                        delay = float(clean_parts[1])
                        count = int(clean_parts[2])
                    else:
                        if len(clean_parts) != 4:
                            raise ValueError("الصيغة: `.ستارت عدد_الثواني عدد_المرات آيدي_القروب [تحويل]`")
                        delay = float(clean_parts[1])
                        count = int(clean_parts[2])
                        target_chat_id = int(clean_parts[3])
                    if delay < 0.5 or count < 1:
                        raise ValueError("أقل مدة مسموحة 0.5 ثانية والعدد يجب أن يكون أكبر من صفر.")
                    # لا نمنع البدء بفحص مبدئي قد يخلط بين اشتراك إجباري وتقييد فعلي.
                    # المهمة تجرب الإرسال أولاً، ثم تعالج الأزرار والروابط إن ظهر منع كتابة.
                    target_name = await _publish_target_name(client_inst, target_chat_id)
                    pending_targets = []
                    if count == 999:
                        count = 10**9
                    reply_message = await event.get_reply_message()
                    await event.delete()
                    await start_auto_publish_task(
                        client_inst, owner_id, target_chat_id, reply_message, delay, count, forward_mode,
                        origin_chat_id=chat_id, pending_approval_targets=pending_targets
                    )
                    mode_text = "بتحويل الرسالة" if forward_mode else "بدون تحويل المصدر"
                    if pending_targets:
                        await command_reply( "⏳ تم إرسال طلب انضمام للاشتراك الإجباري. ستنتظر المهمة موافقة الأدمن ثم تكمل النشر تلقائياً.")
                    else:
                        await command_reply( f"✅ بدأ النشر في **{target_name}** كل `{delay}` ثانية ({mode_text}).")
                except Exception as e:
                    await command_reply( f"❌ تعذر بدء النشر:\n`{e}`")
                return

            if text == "النشر الشغال":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                active_publish_keys = {(key[1], str(key[2])) for key, task in auto_publish_tasks.items() if not task.done()}
                jobs = [job for job in users_db.get(owner_id, {}).get("auto_publish_jobs", [])
                        if (int(job.get("target_chat_id", 0)), str(job.get("operation_id", ""))) in active_publish_keys]
                rows = []
                for job in jobs:
                    target_id = int(job.get("target_chat_id", 0))
                    target_name = await _publish_target_name(client_inst, target_id)
                    rows.append(f"• **{target_name}** — `{target_id}`\n  تم إرسال: `{job.get('completed', 0)}` من `{job.get('count', 0)}`")
                await command_reply( "📊 **عمليات النشر الشغالة:**\n\n" + ("\n".join(rows) if rows else "لا توجد عمليات نشر."))
                return

            if text == "بس":
                if not is_source_subscribed(owner_id):
                    return
                stopped = await stop_auto_publish_task(client_inst, owner_id, chat_id, "تم إيقاف النشر يدوياً بواسطة صاحب الحساب")
                await event.delete()
                await command_reply( f"✅ تم إيقاف {stopped} عملية نشر في هذا القروب.")
                return

            if text == "ايقاف النشر":
                if not is_source_subscribed(owner_id):
                    return
                stopped = await stop_auto_publish_task(client_inst, owner_id, reason="تم إيقاف جميع عمليات النشر يدوياً بواسطة صاحب الحساب")
                await event.delete()
                await command_reply( f"✅ تم إيقاف {stopped} عملية نشر.")
                return

            if text in ["لصوره", "لملصق", "الصوت", "لبصمه"]:
                if not is_source_subscribed(owner_id):
                    return
                if not event.reply_to_msg_id:
                    await command_reply( "❌ يجب الرد على الوسيط المطلوب تحويله أولاً.")
                    return
                try:
                    reply_message = await event.get_reply_message()
                    await event.delete()
                    if text == "لصوره":
                        await convert_to_image(client_inst, reply_message, chat_id)
                    elif text == "لملصق":
                        await convert_to_sticker(client_inst, reply_message, chat_id)
                    elif text == "الصوت":
                        await extract_audio_from_video(client_inst, reply_message, chat_id)
                    else:
                        await convert_to_voice_note(client_inst, reply_message, chat_id)
                except Exception as e:
                    await command_reply( f"❌ تعذر التحويل:\n`{e}`")
                return

            if text == "ايدي" or text.startswith("ايدي "):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    target_id = None
                    if event.reply_to_msg_id:
                        reply_message = await event.get_reply_message()
                        target_id = reply_message.sender_id if reply_message else None
                    elif len(cmd_parts) > 1:
                        target_id = (await client_inst.get_entity(cmd_parts[1])).id
                    elif event.is_private:
                        private_target = await event.get_chat()
                        await event.delete()
                        await command_reply( f"`{getattr(private_target, 'id', chat_id)}`")
                        return
                    target = await client_inst.get_entity(target_id or me.id)
                    full_name = f"{getattr(target, 'first_name', '') or ''} {getattr(target, 'last_name', '') or ''}".strip() or "بدون اسم"
                    username = f"@{target.username}" if getattr(target, "username", None) else "ماعنده"
                    await event.delete()
                    await command_reply( f"💳 **بيانات المستخدم:**\n\n• الاسم: {full_name}\n• الآيدي: `{target.id}`\n• اليوزر: {username}")
                except Exception as e:
                    await command_reply( f"❌ تعذر جلب البيانات:\n`{e}`")
                return

            if text == "بياناتي":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                    report = await get_my_data_report(client_inst, owner_id)
                    await command_reply( report)
                except Exception as e:
                    await command_reply( f"❌ تعذر جلب بياناتك:\n`{e}`")
                return

            if text == "رابط" or text.startswith("رابط "):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    target = await get_user_entity_from_command(client_inst, event, cmd_parts)
                    full_name = f"{getattr(target, 'first_name', '') or ''} {getattr(target, 'last_name', '') or ''}".strip() or "بدون اسم"
                    link = await build_direct_account_link(target)
                    await event.delete()
                    await command_reply( f"🔗 **رابط الحساب:**\n\n• الاسم: {full_name}\n• الآيدي: `{target.id}`\n• الرابط: [اضغط هنا]({link})")
                except Exception as e:
                    await command_reply( f"❌ تعذر جلب رابط الحساب:\n`{e}`")
                return

            if text == "الانشاء" or text.startswith("الانشاء "):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    target = await get_user_entity_from_command(client_inst, event, cmd_parts)
                    full_name = f"{getattr(target, 'first_name', '') or ''} {getattr(target, 'last_name', '') or ''}".strip() or "بدون اسم"
                    estimated = estimated_creation_year(target.id)
                    await event.delete()
                    await command_reply( f"📆 **تاريخ الإنشاء التقديري:**\n\n• الاسم: {full_name}\n• الآيدي: `{target.id}`\n• تقدير الإنشاء: `{estimated}`\n\n⚠️ هذا تقدير مبني على نطاق الآيدي وليس تاريخاً رسمياً من تيليجرام.")
                except Exception as e:
                    await command_reply( f"❌ تعذر كشف تاريخ الإنشاء:\n`{e}`")
                return

            if text == "كشف" or text.startswith("كشف "):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    target = await get_user_entity_from_command(client_inst, event, cmd_parts, private_peer=True)
                    report = await build_account_inspection_report(client_inst, target)
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    await command_reply( report, link_preview=False)
                except Exception as e:
                    await command_reply( f"❌ تعذر كشف معلومات الحساب:\n`{e}`")
                return

            if cmd_first_word in TRANSLATION_COMMANDS:
                if not is_source_subscribed(owner_id):
                    return
                target_language, _ = TRANSLATION_COMMANDS[cmd_first_word]
                try:
                    source_value = await get_command_text(event, text, cmd_first_word)
                    if not source_value:
                        return
                    translated_value = await translate_text(source_value, target_language)
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    # النتيجة فقط، من دون عنوان أو توجيهات أو رسائل خطأ ظاهرة للمستخدم.
                    await command_reply(translated_value, keep_result=True)
                except Exception:
                    pass
                return

            if text in ("تفعيل الذاتيه", "تعطيل الذاتيه"):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                await command_reply(f"✅ حفظ الذاتية تلقائي دائماً. الوجهة الحالية: **{self_save_destination_text(owner_id)}**.")
                return

            if text == "انشاء مجموعة الذاتيه":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                try:
                    result = await client_inst(CreateChannelRequest(
                        title="مجموعة الذاتية",
                        about="لحفظ الوسائط الذاتية تلقائياً عبر بوت ديمون.",
                        megagroup=True,
                    ))
                    target_chat = result.chats[0]
                    user_info["self_save_chat_id"] = target_chat.id
                    save_data()
                    await command_reply(f"✅ تم إنشاء وتعيين مجموعة الذاتية بنجاح.\n• الآيدي: `{target_chat.id}`\n• ستُحفظ فيها الوسائط الذاتية القادمة في الخاص.")
                except Exception as e:
                    await command_reply(f"❌ تعذر إنشاء مجموعة الذاتية:\n`{e}`")
                return

            if text.startswith("تعيين مجموعة الذاتيه"):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    arg = text.replace("تعيين مجموعة الذاتيه", "", 1).strip()
                    if not arg:
                        raise ValueError("اكتب آيدي المجموعة بعد الأمر.")
                    target_chat = await client_inst.get_entity(int(arg) if arg.lstrip("-").isdigit() else arg)
                    user_info["self_save_chat_id"] = target_chat.id
                    save_data()
                    await event.delete()
                    await command_reply(f"✅ تم تعيين مجموعة الذاتية: `{target_chat.id}`\n• ستُحفظ فيها الوسائط الذاتية القادمة في الخاص.")
                except Exception as e:
                    await command_reply(f"❌ تعذر تعيين مجموعة الذاتية:\n`{e}`")
                return

            if text == "حذف مجموعة الذاتيه":
                if not is_source_subscribed(owner_id):
                    return
                user_info["self_save_chat_id"] = None
                save_data()
                await event.delete()
                await command_reply(f"✅ تم حذف مجموعة الذاتية. الوجهة الحالية: **{self_save_destination_text(owner_id)}**.")
                return

            if text == "ذاتيه":
                if not is_source_subscribed(owner_id):
                    return
                if not event.reply_to_msg_id:
                    await command_reply( "❌ قم بالرد على الوسيط الذي تريد حفظه ثم اكتب `.ذاتيه`.")
                    return
                try:
                    reply_message = await event.get_reply_message()
                    if not reply_message or not reply_message.media:
                        raise ValueError("الرسالة التي تم الرد عليها لا تحتوي على وسيط.")
                    await event.delete()
                    target = await save_media_to_self_destination(client_inst, owner_id, reply_message)
                    await command_reply( f"✅ تم حفظ الوسيط في `{target}`.")
                except Exception as e:
                    await command_reply( f"❌ تعذر حفظ الوسيط:\n`{e}`")
                return

            if text in ["قروباتي مالك", "قروباتي ادمن", "قروباتي الكل", "قنواتي مالك", "قنواتي ادمن", "قنواتي الكل"]:
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                    parts = text.split()
                    category = parts[0]
                    mode_word = parts[1]
                    mode = {"مالك": "owner", "ادمن": "admin", "الكل": "all"}[mode_word]
                    groups, channels = await get_account_chat_lists(client_inst, mode)
                    items = groups if category == "قروباتي" else channels
                    title = "القروبات" if category == "قروباتي" else "القنوات"
                    status = {"مالك": "التي أنت مالكها", "ادمن": "التي أنت أدمن فيها", "الكل": "الموجودة بحسابك"}[mode_word]
                    output = f"📊 **{title} {status}:**\n\n"
                    output += "\n".join(f"• {name} — `{chat_id}`" for name, chat_id in items[:100]) if items else "لا توجد نتائج."
                    if len(items) > 100:
                        output += f"\n\n⚠️ تم عرض 100 من أصل {len(items)}."
                    await command_reply( output)
                except Exception as e:
                    await command_reply( f"❌ تعذر جلب القائمة:\n`{e}`")
                return

            if text == "احصائياتي":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                    await command_reply( await build_stats_report(client_inst))
                except Exception as e:
                    await command_reply( f"❌ تعذر جلب الإحصائيات:\n`{e}`")
                return

            # ===== أوامر البحث والتحميل =====
            if text in ("الحاسبه", "الحاسبة", "ح"):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                try:
                    bot_me = await bot.get_me()
                    results = await client_inst.inline_query(bot_me.username, "demon_calculator")
                    await results[0].click(chat_id)
                except Exception as e:
                    await command_reply( f"❌ تعذر عرض الآلة الحاسبة:\n`{e}`")
                return

            if text.startswith("يوت "):
                if not is_source_subscribed(owner_id):
                    return
                query = text[4:].strip()
                if not query:
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                status = await command_reply("⏳ جاري فهم طلبك والبحث وتحميل الصوت...")
                media_path = None
                try:
                    media_path, info, _plan = await hybrid_ytdlp_download(query, default_audio=True)
                    await command_reply_file(media_path, caption=(info.get("title") or query)[:900])
                    await status.delete()
                except Exception as e:
                    await status.edit(f"❌ تعذر تحميل الصوت:\n`{e}`")
                finally:
                    _safe_remove(media_path)
                return

            if text.startswith("تحميل "):
                if not is_source_subscribed(owner_id):
                    return
                url = text[6:].strip()
                if not url:
                    return
                await event.delete()
                status = await command_reply( "⏳ جاري التحميل...")
                try:
                    await download_and_send_url(client_inst, chat_id, url, audio_only=False)
                    await status.delete()
                except Exception as e:
                    await report_admin_error("تحميل رابط", e, owner_id, chat_id)
                    await status.edit(f"❌ تعذر التحميل:\n`{e}`")
                return

            if text.startswith("ريديت "):
                if not is_source_subscribed(owner_id):
                    return
                url = text[6:].strip()
                if not url:
                    return
                await event.delete()
                status = await command_reply("⏳ جاري تحميل محتوى ريديت...")
                try:
                    await download_and_send_url(client_inst, chat_id, url, audio_only=False)
                    await status.delete()
                except Exception as e:
                    await report_admin_error("تحميل ريديت", e, owner_id, chat_id)
                    await status.edit(f"❌ تعذر تحميل ريديت:\n`{e}`")
                return

            if text.startswith("بنترست "):
                if not is_source_subscribed(owner_id):
                    return
                url = text[8:].strip()
                await event.delete()
                status = await command_reply( "⏳ جاري تحميل محتوى بنترست...")
                try:
                    await download_and_send_url(client_inst, chat_id, url)
                    await status.delete()
                except Exception as e:
                    await report_admin_error("تحميل بنترست", e, owner_id, chat_id)
                    await status.edit(f"❌ تعذر تحميل بنترست:\n`{e}`")
                return

            if text.startswith("ستوري "):
                if not is_source_subscribed(owner_id):
                    return
                url = text[7:].strip()
                await event.delete()
                status = await command_reply( "⏳ جاري تحميل الستوري...")
                try:
                    await download_telegram_story(client_inst, chat_id, url)
                    await status.delete()
                except Exception as e:
                    await report_admin_error("تحميل ستوري", e, owner_id, chat_id)
                    await status.edit(f"❌ تعذر تحميل الستوري:\n`{e}`")
                return

            if text.startswith("مستودع "):
                if not is_source_subscribed(owner_id):
                    return
                url = text[8:].strip()
                await event.delete()
                status = await command_reply( "⏳ جاري تحميل المستودع...")
                try:
                    await download_github_repository(client_inst, chat_id, url)
                    await status.delete()
                except Exception as e:
                    await report_admin_error("تحميل مستودع", e, owner_id, chat_id)
                    await status.edit(f"❌ تعذر تحميل المستودع:\n`{e}`")
                return

            if text.startswith("مقيد ") or text.startswith("حفظ "):
                if not is_source_subscribed(owner_id):
                    return
                url = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
                await event.delete()
                status = await command_reply( "⏳ جاري حفظ المحتوى...")
                try:
                    await save_restricted_message(client_inst, chat_id, url)
                    await status.delete()
                except Exception as e:
                    await status.edit(f"❌ تعذر حفظ المحتوى:\n`{e}`")
                return

            # ===== الكتابة والخطوط =====
            if text.startswith("اكتب "):
                if not is_source_subscribed(owner_id):
                    return
                value = await get_command_text(event, text, "اكتب")
                if not value:
                    await command_reply( "❌ اكتب النص بعد الأمر: `.اكتب النص`")
                    return
                await event.delete()
                try:
                    await make_handwriting_image(client_inst, chat_id, value)
                except Exception as e:
                    await command_reply( f"❌ تعذر إنشاء الكتابة:\n`{e}`")
                return

            if text == "نسخ" or text.startswith("نسخ ") or text == "غامق" or text.startswith("غامق ") or text == "مائل" or text.startswith("مائل "):
                if not is_source_subscribed(owner_id):
                    return
                command = cmd_first_word
                value = await get_command_text(event, text, command)
                if not value:
                    await command_reply( "❌ اكتب النص بعد الأمر أو رد على رسالة نصية.")
                    return
                await event.delete()
                if command == "نسخ":
                    await command_reply( f"`{value}`")
                elif command == "غامق":
                    await command_reply( f"**{value}**")
                else:
                    await command_reply( f"__{value}__")
                return

            # ===== الإذاعة والتنظيف =====
            if text == "اذاعه" or text.startswith("اذاعه "):
                if not is_source_subscribed(owner_id):
                    return
                if not event.reply_to_msg_id:
                    await command_reply( "❌ قم بالرد على الرسالة المراد إذاعتها أولاً.")
                    return
                try:
                    parts = text.split()
                    limit = int(parts[1]) if len(parts) > 1 else 10**9
                    if limit < 1:
                        raise ValueError("العدد يجب أن يكون أكبر من صفر.")
                    reply_message = await event.get_reply_message()
                    await event.delete()
                    await start_broadcast_task(client_inst, owner_id, reply_message, limit)
                    await command_reply( f"✅ بدأت الإذاعة إلى حد أقصى `{limit if limit < 10**9 else 'كل الخاص'}` محادثة.")
                except Exception as e:
                    await command_reply( f"❌ تعذر بدء الإذاعة:\n`{e}`")
                return

            if text == "ايقاف الاذاعه":
                task = broadcast_tasks.get(owner_id)
                if task and not task.done():
                    task.cancel()
                    await event.delete()
                    await command_reply( "⏹️ تم طلب إيقاف الإذاعة.")
                else:
                    await command_reply( "⚠️ لا توجد إذاعة شغالة حالياً.")
                return

            if text in ["مغادرة القنوات", "مغادرة القروبات", "تصفية الخاص", "تصفية البوتات"]:
                if not is_source_subscribed(owner_id):
                    return
                action_map = {
                    "مغادرة القنوات": "leave_channels",
                    "مغادرة القروبات": "leave_groups",
                    "تصفية الخاص": "clear_private",
                    "تصفية البوتات": "clear_bots"
                }
                await event.delete()
                status = await command_reply( "⏳ جاري تنفيذ العملية...")
                try:
                    completed = await bulk_account_action(client_inst, owner_id, action_map[text])
                    await status.edit(f"✅ اكتملت العملية. تم التعامل مع `{completed}` محادثة/قناة/قروب.")
                except Exception as e:
                    await status.edit(f"❌ تعذر تنفيذ العملية:\n`{e}`")
                return

            if text == "ايقاف التفليش":
                if not is_source_subscribed(owner_id):
                    return
                target_id = chat_id
                if len(cmd_parts) > 2:
                    try:
                        target_id = int(cmd_parts[2])
                    except ValueError:
                        target_id = chat_id
                stopped = await stop_manual_flush_tasks(owner_id, target_id)
                try:
                    await event.delete()
                except Exception:
                    pass
                if not stopped:
                    await command_reply( "⚠️ لا توجد عملية تفليش يدوية شغالة لهذا القروب.")
                return

            if text == "تفليش" or text.startswith("تفليش بالطرد") or text.startswith("تفليش بالحظر"):
                if not is_source_subscribed(owner_id):
                    return
                mode = "kick" if text.startswith("تفليش بالطرد") else "ban"
                target_ref = chat_id
                parts = text.split(maxsplit=2)
                if len(parts) == 3:
                    target_ref = parts[2]
                try:
                    await event.delete()
                except Exception:
                    pass
                try:
                    await start_manual_flush_task(client_inst, owner_id, target_ref, chat_id, mode)
                except Exception as e:
                    await command_reply( f"❌ تعذر بدء التفليش: `{e}`")
                return

            if text.startswith("بحث "):
                if not is_source_subscribed(owner_id):
                    return
                query = text[3:].strip()
                if query:
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    search_msg = await command_reply(f"🔍 جاري فهم طلبك والبحث في يوتيوب عن: `{query}`...")
                    try:
                        plan = await resolve_hybrid_download_request(query, default_audio=True)
                        file_path, title, duration, uploader, thumb_path = await search_and_download_youtube(plan["search_query"])
                        if file_path and os.path.exists(file_path):
                            await search_msg.delete()
                            from telethon.tl.types import DocumentAttributeAudio
                            safe_title = (title or "مقطع بدون عنوان").strip()[:64]
                            safe_channel = (uploader or "قناة يوتيوب").strip()[:64]
                            display_caption = (
                                f"🎧 **{safe_title}**\n"
                                f"📺 القناة: **{safe_channel}**\n"
                                f"⏱️ المدة: `{format_media_duration(duration)}`"
                            )
                            await client_inst.send_file(
                                chat_id,
                                file_path,
                                thumb=thumb_path,
                                caption=display_caption,
                                parse_mode="md",
                                mime_type="audio/mpeg",
                                force_document=False,
                                attributes=[DocumentAttributeAudio(duration=int(duration or 0), title=safe_title, performer=safe_channel)],
                                voice_note=False,
                            )
                        else:
                            await search_msg.edit("❌ لم يتم العثور على نتائج مطابقة لبحثك.")
                    except Exception as e:
                        try:
                            await search_msg.edit(f"❌ حدث خطأ أثناء البحث والتحميل: `{e}`")
                        except Exception:
                            pass
                return

            voice_match = re.match(r"^(صوتيه|صوتية)\s*(\d+)$", text)
            if voice_match:
                if not is_source_subscribed(owner_id):
                    return
                voice_num = voice_match.group(2)
                voices_dict = user_info.get("voices", {})
                
                if voice_num in voices_dict:
                    file_path = voices_dict[voice_num]
                    if os.path.exists(file_path):
                        if user_info.get("del_voice_cmd", True):
                            try:
                                await event.delete()
                            except Exception:
                                pass
                        
                        target_reply = event.reply_to_msg_id
                        try:
                            await client_inst.send_file(
                                chat_id,
                                file_path,
                                voice_note=True,
                                reply_to=target_reply
                            )
                        except Exception as e:
                            print(f"Error sending voice: {e}")
                return

            if text == "تثبيت":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                if not event.reply_to_msg_id:
                    await command_reply( "❌ رد على الرسالة المطلوبة ثم اكتب `.تثبيت`.")
                    return
                try:
                    await client_inst.pin_message(chat_id, event.reply_to_msg_id, notify=True)
                except Exception as e:
                    await command_reply( f"❌ تعذر تثبيت الرسالة: `{e}`")
                return

            if text in ("الغاء التثبيت", "إلغاء التثبيت"):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                try:
                    await client_inst.unpin_message(chat_id, event.reply_to_msg_id if event.reply_to_msg_id else None, notify=True)
                except Exception as e:
                    await command_reply( f"❌ تعذر إلغاء التثبيت: `{e}`")
                return

            if text in p_all_cmds or cmd_first_word in p_all_cmds:
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                
                msg_ids = []
                async for msg in client_inst.iter_messages(chat_id, from_user=me.id):
                    msg_ids.append(msg.id)
                    if len(msg_ids) >= 100:
                        try:
                            await client_inst.delete_messages(chat_id, msg_ids)
                        except Exception:
                            pass
                        msg_ids = []
                if msg_ids:
                    try:
                        await client_inst.delete_messages(chat_id, msg_ids)
                    except Exception:
                        pass
                return

            if cmd_first_word in p_cmds:
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                
                count = 20
                if len(cmd_parts) > 1 and cmd_parts[1].isdigit():
                    count = int(cmd_parts[1])

                msg_ids = []
                async for msg in client_inst.iter_messages(chat_id, from_user=me.id, limit=count):
                    msg_ids.append(msg.id)
                
                if msg_ids:
                    try:
                        await client_inst.delete_messages(chat_id, msg_ids)
                    except Exception:
                        pass
                return

            if text in m_cmds or cmd_first_word in m_cmds:
                if not is_source_subscribed(owner_id):
                    return
                if user_info.get("del_mute_cmd", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                target_uid = await resolve_target_user(event)
                if target_uid and target_uid != me.id and target_uid not in manager_bot_id:
                    if target_uid not in user_info["muted_users"]:
                        user_info["muted_users"].append(target_uid)
                        save_data()
                return

            elif text in um_cmds or cmd_first_word in um_cmds:
                if not is_source_subscribed(owner_id):
                    return
                if user_info.get("del_unmute_cmd", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                target_uid = await resolve_target_user(event)
                if target_uid:
                    if target_uid in user_info["muted_users"]:
                        user_info["muted_users"].remove(target_uid)
                        save_data()
                return

            target_msg_id = event.reply_to_msg_id
            target_user_id = None

            if event.is_private:
                target_user_id = chat_id
                target_msg_id = None
            elif target_msg_id:
                reply_msg = await event.get_reply_message()
                if reply_msg:
                    target_user_id = reply_msg.sender_id

            # النص تمّت إزالة النقطة منه مسبقاً، لذلك نطابقه مع النسخ الموحّدة للأوامر المخزنة.
            t_start = normalize_command_list(t_start, ["تسطير"])
            t_stop = normalize_command_list(t_stop, ["ايقاف التسطير"])
            f_start = normalize_command_list(f_start, ["فرديات"])
            f_stop = normalize_command_list(f_stop, ["ايقاف الفرديات"])
            r_start = normalize_command_list(r_start, ["ريبلاي"])
            r_stop = normalize_command_list(r_stop, ["ايقاف الريبلاي"])
            n_stop = normalize_command_list(user_info.get("nick_am_stop_cmds", []), ["ايقاف نيك ام"])

            nick_am_command = "نيك ام" if (text == "نيك ام" or text.startswith("نيك ام ")) else None
            if nick_am_command:
                if not user_info.get("nick_am_enabled", False):
                    return
                nick_prefix = text[len(nick_am_command):].strip()
                nick_prefix, nick_target_msg_id, nick_target_user_id, nick_target_style = await resolve_nick_am_launch(
                    event, nick_prefix, target_msg_id, target_user_id
                )
                if not nick_prefix:
                    await command_reply("⚠️ يجب كتابة اسم بعد أمر نيك ام.")
                    return
                started = start_running_task(
                    client_inst, owner_id, chat_id, "nick_am", nick_target_msg_id,
                    nick_target_user_id, nick_prefix=nick_prefix, nick_target_style=nick_target_style,
                )
                if not started:
                    await send_empty_tastir_notice_private("⚠️ لا توجد نصوص نشطة لنيك ام. أضف نصاً أو فعّل تضمين التسطير أو الفرديات.")
                return

            if text in t_start:
                if user_info.get("del_tastir_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                started = start_running_task(client_inst, owner_id, chat_id, "tastir", target_msg_id, target_user_id)
                if not started:
                    await send_empty_tastir_notice_private("⚠️ لا توجد جمل تسطير محفوظة. أضف جملة أولاً من زر «إضافة جمل التسطير».")
                return

            elif text in f_start:
                if user_info.get("del_fardiyyat_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                started = start_running_task(client_inst, owner_id, chat_id, "fardiyyat", target_msg_id, target_user_id)
                if not started:
                    await send_empty_tastir_notice_private("⚠️ لا توجد كلمات فرديات محفوظة. أضف كلمة أولاً من زر «إضافة كلمات الفرديات».")
                return

            elif text in r_start:
                if user_info.get("del_reply_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                if not target_user_id or target_user_id in manager_bot_id:
                    await command_reply( "⚠️ الريبلاي يحتاج الرد على رسالة شخص داخل القروب أو الخاص، ولا يعمل في محادثة بوت الإدارة.")
                    return
                if not (user_info.get("reply", []) or default_reply or user_info.get("tastir", []) or default_tastir or user_info.get("fardiyyat", []) or default_fardiyyat):
                    await send_empty_tastir_notice_private("⚠️ لا توجد جمل ريبلاي أو تسطير أو فرديات محفوظة لإرسالها.")
                    return
                task_key = (owner_id, chat_id, target_user_id, "reply")
                running_tasks[task_key] = {
                    "task": None,
                    "owner_id": owner_id,
                    "chat_id": chat_id,
                    "target_user_id": target_user_id,
                    "mode": "reply",
                    "target_msg_id": target_msg_id,
                    "started_at": time.time()
                }
                return

            elif text in t_stop:
                if user_info.get("del_tastir_stop", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                stop_running_task(owner_id, chat_id, target_user_id=target_user_id, mode="tastir")
                return

            elif text in f_stop:
                if user_info.get("del_fardiyyat_stop", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                stop_running_task(owner_id, chat_id, target_user_id=target_user_id, mode="fardiyyat")
                return

            elif text in n_stop:
                if user_info.get("del_nick_am_stop", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                stop_running_task(owner_id, chat_id, target_user_id=target_user_id, mode="nick_am")
                return

            elif text in r_stop:
                if user_info.get("del_reply_stop", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                stop_running_task(owner_id, chat_id, target_user_id=target_user_id, mode="reply")
                return

            elif text in ["ايقاف", "إيقاف", "توقف", "ايقاف عام"]:
                try:
                    await event.delete()
                except Exception:
                    pass
                stop_running_task(owner_id, chat_id)
                return

        else:
            sender_id = event.sender_id
            user_info = users_db.get(owner_id, {})
            
            # --- الترحيب الخاص وردود المنشن الذكية ---
            if is_source_subscribed(owner_id):
                is_private_incoming = event.is_private and sender_id != me.id and sender_id not in manager_bot_id
                if is_private_incoming and user_info.get("welcome_enabled", False):
                    welcomed = user_info.setdefault("welcomed_private_ids", [])
                    if sender_id not in welcomed:
                        welcome_text = user_info.get("welcome_text", "أهلاً بك، نورت الخاص.")
                        welcome_photo = user_info.get("welcome_photo")
                        try:
                            if welcome_photo and os.path.exists(welcome_photo):
                                await client_inst.send_file(chat_id, welcome_photo, caption=welcome_text)
                            else:
                                await client_inst.send_message(chat_id, welcome_text)
                            welcomed.append(sender_id)
                            user_info["welcomed_private_ids"] = welcomed[-1000:]
                            save_data()
                        except Exception:
                            pass

                if (not event.is_private and event.mentioned and user_info.get("smart_replies_enabled", False)):
                    incoming_text = (text or "").lower()
                    trigger_words = ["موجود", "اكلك", "آكلك", "مفعل نشر", "مفعل النشر", "وينك", "متواجد"]
                    if any(word in incoming_text for word in trigger_words):
                        try:
                            await client_inst.send_message(chat_id, "موجود ✅", reply_to=event.id)
                        except Exception:
                            pass

            # --- حفظ الذاتية التلقائي: الوسائط المؤقتة الواردة في الخاص فقط ---
            self_destruct_private_media = False
            if is_source_subscribed(owner_id):
                try:
                    ttl_value = getattr(event.message, "ttl_period", None) or getattr(event.media, "ttl_seconds", None)
                    self_destruct_private_media = bool(event.is_private and sender_id != me.id and event.media and ttl_value)
                    if self_destruct_private_media:
                        await save_media_to_self_destination(client_inst, owner_id, event.message)
                except Exception as e:
                    print(f"Self-save error: {e}")

            # --- مجموعة التخزين: بطاقة واحدة للمصدر الحالي، ثم تحويل الرسائل حتى يصل مصدر مختلف ---
            # الوسيط الذاتي في الخاص تم حفظه للتو عبر وجهة الذاتية، فلا نكرره هنا.
            if is_source_subscribed(owner_id) and user_info.get("storage_groups") and not self_destruct_private_media:
                storage_group_id = user_info["storage_groups"][-1]
                is_private_msg = event.is_private and sender_id != me.id and sender_id not in manager_bot_id
                is_reply_to_me = False
                if not event.is_private and event.reply_to_msg_id:
                    try:
                        replied = await event.get_reply_message()
                        is_reply_to_me = bool(replied and replied.sender_id == me.id)
                    except Exception:
                        is_reply_to_me = False
                is_relevant_group_message = (not event.is_private) and (bool(event.mentioned) or is_reply_to_me)
                notice_key = (owner_id, int(chat_id), int(event.id))
                now = time.time()
                for key, expires_at in list(storage_notice_cache.items()):
                    if expires_at < now:
                        storage_notice_cache.pop(key, None)

                # لا تنشئ مفتاح التخزين إلا لرسالة واردة تخص المستخدم ولها مرسل فعلي.
                # رسائل القنوات الخارجة وبعض رسائل الخدمة لا تحمل sender_id، ويجب ألا توقف الأوامر بسبب ذلك.
                if (
                    (is_private_msg or is_relevant_group_message)
                    and sender_id is not None
                    and chat_id is not None
                    and chat_id != storage_group_id
                    and notice_key not in storage_notice_cache
                ):
                    # الخاص: المصدر هو الشخص. القروب: المصدر هو الشخص داخل القروب نفسه.
                    source_key = ("private", int(sender_id)) if is_private_msg else ("group", int(chat_id), int(sender_id))
                    previous_source = storage_active_sources.get(owner_id)
                    show_notice_card = previous_source != source_key
                    storage_notice_cache[notice_key] = now + 3600
                    try:
                        sender_entity = await event.get_sender()
                        sender_name = getattr(sender_entity, "first_name", None) or "بدون اسم"
                        if getattr(sender_entity, "last_name", None):
                            sender_name += f" {sender_entity.last_name}"
                        sender_username = f"@{sender_entity.username}" if getattr(sender_entity, "username", None) else "ماعنده"
                        has_media = bool(event.media)

                        if is_private_msg:
                            if show_notice_card:
                                private_notice = (
                                    f"- المستخــدم {sender_name} ارسـل لك رسالة جـديـدة 💬\n"
                                    f"- ايديـه ◂ `{sender_id}`\n"
                                    f"- يوزره ◂ {sender_username}"
                                )
                                await client_inst.send_message(storage_group_id, private_notice, parse_mode="md")
                                storage_active_sources[owner_id] = source_key
                            # رسالة الخاص تتحول دائماً مع الصورة أو الوسيط والنص المرافق.
                            # والوسائط المؤقتة نحاول حفظها فور وصول الحدث قبل أن تنتهي صلاحيتها.
                            try:
                                await client_inst.forward_messages(storage_group_id, event.message)
                            except Exception:
                                if has_media:
                                    stored_path = await client_inst.download_media(event.message, file=TEMP_DIR)
                                    if stored_path:
                                        try:
                                            await client_inst.send_file(storage_group_id, stored_path, caption=event.raw_text or "")
                                        finally:
                                            _safe_remove(stored_path)
                                elif event.raw_text:
                                    await client_inst.send_message(storage_group_id, event.raw_text)
                        else:
                            chat_entity = await event.get_chat()
                            chat_title = getattr(chat_entity, "title", "مجموعة")
                            chat_username = getattr(chat_entity, "username", None)
                            if chat_username:
                                msg_link = f"https://t.me/{chat_username}/{event.id}"
                            else:
                                internal_chat_id = str(chat_id).replace("-100", "")
                                msg_link = f"https://t.me/c/{internal_chat_id}/{event.id}"

                            # القروبات: بطاقة التاك عند تغير المصدر، ثم تحويل رسالة الشخص نفسها
                            # بالوسيط والنص المرافق حتى تصل مجموعة التخزين الرسالة كاملة.
                            if show_notice_card:
                                message_text = event.raw_text or ("رسالة تحتوي على وسائط" if has_media else "رسالة بدون نص")
                                group_notice = (
                                    "#تـنـبـيـه_تــاك\n\n"
                                    "◂ **المجمـوعـة :**\n"
                                    f"- الاســم : {chat_title}\n"
                                    f"- الايدي : `{chat_id}`\n\n"
                                    "◂ **المـرسـل :**\n"
                                    f"- الاســم : {sender_name}\n"
                                    f"- الايدي : `{sender_id}`\n"
                                    f"- اليـوزر : {sender_username}\n\n"
                                    f"◂ **الرسالـة :** {message_text}\n\n"
                                    f"◂ **الرابـط :** [اضغـط هـنـا]({msg_link})"
                                )
                                await client_inst.send_message(storage_group_id, group_notice, link_preview=False, parse_mode="md")
                                storage_active_sources[owner_id] = source_key
                            try:
                                # التحويل يحتفظ بالنص وبالوسيط كما أرسله صاحب التاك.
                                await client_inst.forward_messages(storage_group_id, event.message)
                            except Exception:
                                # عند تعذر التحويل، نحفظ الوسيط مباشرة مع النص إن كان متاحاً.
                                if has_media:
                                    stored_path = await client_inst.download_media(event.message, file=TEMP_DIR)
                                    if stored_path:
                                        try:
                                            await client_inst.send_file(storage_group_id, stored_path, caption=event.raw_text or "")
                                        finally:
                                            _safe_remove(stored_path)
                                elif event.raw_text:
                                    await client_inst.send_message(storage_group_id, event.raw_text)
                    except Exception as e:
                        print(f"Storage group alert error: {e}")
            # ------------------------------------------------
            
            muted_list = user_info.get("muted_users", [])
            if sender_id in muted_list:
                try:
                    await event.delete()
                except Exception:
                    pass
                return

            for key, info in list(running_tasks.items()):
                if info.get("owner_id") == owner_id and info.get("chat_id") == chat_id and info.get("target_user_id") == sender_id:
                    info["target_msg_id"] = event.id
            reply_tasks = [info for info in running_tasks.values()
                           if info.get("owner_id") == owner_id and info.get("chat_id") == chat_id
                           and info.get("target_user_id") == sender_id and info.get("mode") == "reply"]
            if reply_tasks:
                if is_subscribed(owner_id):
                    phrases = list(user_info.get("reply", []) + default_reply)
                    
                    if user_info.get("include_tastir_in_reply", True):
                        phrases += user_info.get("tastir", []) + default_tastir
                        
                    if user_info.get("include_fardiyyat_in_reply", True):
                        phrases += user_info.get("fardiyyat", []) + default_fardiyyat

                    if phrases:
                        phrase = random.choice(phrases)
                        try:
                            await client_inst.send_message(chat_id, phrase, reply_to=event.id)
                        except Exception:
                            pass

# ==================== UI Keyboards ====================
def main_menu_keyboard(user_id):
    # غير المشترك لا يرى إلا أكواد التفعيل والقناة والمطور.
    tastir_active = is_subscribed(user_id)
    source_active = is_source_subscribed(user_id)
    buttons = []
    # يبقى زر التفعيل الناقص ظاهراً حتى يفعّل المستخدم الاشتراك الآخر أيضاً.
    if not tastir_active:
        buttons.append([Button.inline("🎟️ كود تفعيل التسطير", b"enter_code_start")])
    if not source_active:
        buttons.append([Button.inline("⭐ كود تفعيل مميزات السورس", b"enter_source_code_start")])
    if not (tastir_active and source_active):
        buttons.append([Button.inline("✨ كود تفعيل جميع الصلاحيات", b"enter_all_code_start")])
    if tastir_active or source_active:
        buttons.append([Button.inline("🔑 تسجيل الدخول / ربط الحساب", b"login_start")])
        if tastir_active:
            buttons.append([Button.inline("📝 قسم التسطير", b"tastir_section")])
        if source_active:
            buttons.append([Button.inline("⭐ مميزات السورس", b"source_features_menu")])
        buttons.append([Button.inline("📊 حالة الاشتراكات", b"sub_info")])
    if is_staff(user_id):
        buttons.append([Button.inline("👑 لوحة تحكم المسؤول", b"admin_menu")])
    buttons.extend(developer_main_buttons())
    return buttons


def tastir_section_keyboard(user_id):
    return [
        [Button.inline("📝 التسطير", b"tastir_menu"), Button.inline("🎯 الفرديات", b"fardiyyat_menu")],
        [Button.inline("💬 الريبلاي", b"reply_menu"), Button.inline("🏷️ نيك ام", b"nick_am_menu")],
        [Button.inline("⚡ السرعة", b"speed_menu")],
        [Button.inline("🛑 إيقاف العمليات", b"tastir_ops_menu")],
        [Button.inline("🔙 رجوع", b"main_menu")]
    ]

def nick_am_menu_keyboard(user_id):
    u = users_db.get(user_id, {})
    enabled = bool(u.get("nick_am_enabled", False))
    status = "مفعل ✅" if enabled else "معطل ❌"
    activation_button = [Button.inline(f"🔘 تفعيل نيك ام [{status}]", b"toggle_nick_am")]
    if not enabled:
        return [
            activation_button,
            [Button.inline("🔙 رجوع إلى قسم التسطير", b"tastir_section")],
        ]

    stop_delete = "✅" if u.get("del_nick_am_stop", True) else "❌"
    tastir_include = "✅" if u.get("include_tastir_in_nick_am", True) else "❌"
    fardiyyat_include = "✅" if u.get("include_fardiyyat_in_nick_am", True) else "❌"
    reply_status = "مفعل ✅" if u.get("nick_am_reply_enabled", True) else "غير مفعل ❌"
    return [
        activation_button,
        [Button.inline(f"💬 إرسال الرسائل كريبلاي [{reply_status}]", b"toggle_nick_am_reply")],
        [Button.inline("➕ إضافة نصوص نيك ام", b"add_nick_am"), Button.inline("📋 عرض النصوص", b"show_nick_am")],
        [Button.inline(f"📝 تضمين التسطير بالنيك ام [{tastir_include}]", b"tog_nick_am_tastir")],
        [Button.inline(f"🎯 تضمين الفرديات بالنيك ام [{fardiyyat_include}]", b"tog_nick_am_fardiyyat")],
        [Button.inline("⏹️ إضافة أمر إيقاف", b"add_nick_am_stop"), Button.inline("📜 أوامر الإيقاف", b"show_nick_am_stop")],
        [Button.inline(f"🗑️ مسح أمر الإيقاف [{stop_delete}]", b"tog_nick_am_stop")],
        [Button.inline("❌ خيارات حذف نصوص نيك ام", b"del_nick_am_sub")],
        [Button.inline("❌ حذف أوامر الإيقاف", b"clear_nick_am_stop")],
        [Button.inline("🔙 رجوع إلى قسم التسطير", b"tastir_section")],
    ]


def tastir_operations_menu_keyboard():
    return [
        [Button.inline("🛑 إيقاف جميع العمليات", b"tastir_ops_stop_all")],
        [Button.inline("📋 إيقاف عملية", b"tastir_ops_list")],
        [Button.inline("🔙 رجوع إلى قسم التسطير", b"tastir_section")],
    ]

def flush_section_keyboard():
    return [
        [Button.inline("🚀 التفليش عبر البوت", b"flush_menu")],
        [Button.inline("📖 شرح التفليش اليدوي", b"manual_flush_info")],
        [Button.inline("🔙 رجوع إلى مميزات السورس", b"source_features_menu")],
    ]


def flush_menu_keyboard():
    return [
        [Button.inline("🚀 بدء التفليش", b"start_flush_flow")],
        [Button.inline("🔙 رجوع", b"flush_section")]
    ]

def flush_speed_menu_keyboard(user_id):
    u = users_db.get(user_id, {})
    spd = u.get("flush_speed", 0.5)
    return [
        [Button.inline(f"⏱️ 3 ثواني {'✅' if spd == 3.0 else ''}", b"fspd_3"), Button.inline(f"⏱️ 2 ثانية {'✅' if spd == 2.0 else ''}", b"fspd_2")],
        [Button.inline(f"⏱️ 1 ثانية {'✅' if spd == 1.0 else ''}", b"fspd_1"), Button.inline(f"⏱️ 0.5 ثانية {'✅' if spd == 0.5 else ''}", b"fspd_0.5")],
        [Button.inline("🔙 رجوع إلى قسم التفليش", b"flush_section")]
    ]

def source_features_menu_keyboard():
    return [
        [Button.inline("💥 قسم التفليش", b"flush_section"), Button.inline("📦 مجموعة التخزين", b"storage_group_menu")],
        [Button.inline("🤖 قسم الذكاء الاصطناعي", b"ai_main_menu")],
        [Button.inline("📌 فكرة التثبيت", b"feature_pin_info")],
        [Button.inline("🧹 مسح الشامل", b"info_purge_all"), Button.inline("🔢 مسح بالعدد المحدد", b"info_purge_quick")],
        [Button.inline("🔇 الكتم الشامل", b"mute_menu"), Button.inline("🎙️ الصوتيات", b"voice_menu")],
        [Button.inline("👤 الحساب", b"section_account"), Button.inline("📬 الترحيب والردود", b"section_welcome")],
        [Button.inline("🧧 حفظ الذاتية", b"section_self_save"), Button.inline("📍 النشر التلقائي", b"section_publish")],
        [Button.inline("🎧 البحث والتحميل", b"section_download"), Button.inline("🧰 الأدوات", b"section_tools")],
        [Button.inline("🔙 رجوع", b"main_menu")]
    ]
def tools_back_keyboard():
    return [[Button.inline("◀️ رجوع", b"section_tools")]]


def account_section_keyboard():
    return [
        [Button.inline("📊 الاحصائيات", b"stats_menu"), Button.inline("📂 بياناتي", b"my_data_menu")],
        [Button.inline("💬 قروباتي وقنواتي", b"chat_lists_menu"), Button.inline("🎭 الانتحال", b"clone_menu")],
        [Button.inline("🚶 المغادرة والتصفية", b"leave_cleanup_menu"), Button.inline("📆 تاريخ الإنشاء", b"creation_info")],
        [Button.inline("💳 الأيدي", b"id_menu")],
        [Button.inline("◀️ رجوع", b"source_features_menu")]
    ]


def welcome_section_keyboard():
    return [[Button.inline("📬 الترحيب والردود", b"welcome_menu")], [Button.inline("◀️ رجوع", b"source_features_menu")]]


def self_save_section_keyboard():
    return [
        [Button.inline("🧧 حفظ الذاتية", b"self_save_menu"), Button.inline("🧩 محتوى مقيد", b"restricted_menu")],
        [Button.inline("◀️ رجوع", b"source_features_menu")],
    ]


def chat_lists_keyboard(user_id=None):
    rows = [
        [Button.inline("💬 قروباتي", b"chat_list_groups_all"), Button.inline("📢 قنواتي", b"chat_list_channels_all")],
        [Button.inline("👑 قروباتي مالك", b"chat_list_groups_owner"), Button.inline("👑 قنواتي مالك", b"chat_list_channels_owner")],
        [Button.inline("🛡️ قروباتي أدمن", b"chat_list_groups_admin"), Button.inline("🛡️ قنواتي أدمن", b"chat_list_channels_admin")],
    ]
    if user_id is not None and (is_owner(user_id) or is_responsible(user_id)):
        rows.append([Button.inline("🔄 تحديث شامل", b"chat_list_refresh"), Button.inline("◀️ رجوع", b"section_account")])
    else:
        rows.append([Button.inline("◀️ رجوع", b"section_account")])
    return rows


def publish_section_keyboard():
    return [[Button.inline("📍 النشر التلقائي", b"auto_publish_menu"), Button.inline("🎙 الإذاعة", b"broadcast_menu")], [Button.inline("◀️ رجوع", b"source_features_menu")]]


def download_section_keyboard():
    return [
        [Button.inline("🔴 أوامر اليوتيوب", b"youtube_menu")],
        [Button.inline("⚪ تيك توك", b"tiktok_menu"), Button.inline("🩸 انستغرام", b"instagram_menu")],
        [Button.inline("📌 بنترست", b"pinterest_menu"), Button.inline("📥 تحميل ستوري", b"story_menu")],
        [Button.inline("📦 مستودع GitHub", b"github_menu")],
        [Button.inline("◀️ رجوع", b"source_features_menu")]
    ]


def tools_section_keyboard():
    return [
        [Button.inline("🔗 رابط الحساب", b"account_link_info"), Button.inline("✍️ الكتابة والخطوط", b"writing_menu")],
        [Button.inline("📟 الآلة الحاسبة", b"calculator_menu"), Button.inline("🏧 الترجمة", b"translation_info")],
        [Button.inline("🖼 الصيغ والتحويل", b"conversion_menu")],
        [Button.inline("◀️ رجوع", b"source_features_menu")]
    ]


def calculator_keyboard():
    return [
        [Button.inline("1", b"calc_1"), Button.inline("2", b"calc_2"), Button.inline("3", b"calc_3"), Button.inline("+", b"calc_+")],
        [Button.inline("4", b"calc_4"), Button.inline("5", b"calc_5"), Button.inline("6", b"calc_6"), Button.inline("−", b"calc_-")],
        [Button.inline("7", b"calc_7"), Button.inline("8", b"calc_8"), Button.inline("9", b"calc_9"), Button.inline("×", b"calc_*")],
        [Button.inline(".", b"calc_."), Button.inline("0", b"calc_0"), Button.inline("⌫", b"calc_back"), Button.inline("÷", b"calc_/")],
        [Button.inline("AC", b"calc_clear"), Button.inline("=", b"calc_equals")]
    ]


def _format_calculator_value(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("ناتج غير صالح")
        if value.is_integer():
            return str(int(value))
        return f"{value:.12g}"
    return str(value)


def process_calculator_action(previous, action):
    """منطق حاسبة محدود وآمن: + - × ÷ . = وAC والحذف."""
    if isinstance(previous, dict):
        expression = str(previous.get("expression", ""))
        just_evaluated = bool(previous.get("just_evaluated", False))
    else:
        expression = str(previous or "")
        just_evaluated = False

    operators = "+-*/"
    if expression == "خطأ":
        expression, just_evaluated = "", False

    if action == "clear":
        expression, just_evaluated = "", False
    elif action == "back":
        expression = expression[:-1]
        just_evaluated = False
    elif action == "equals":
        try:
            if not expression or expression[-1] in operators or not re.fullmatch(r"[0-9+\-*/(). ]+", expression):
                raise ValueError("صيغة غير صالحة")
            expression = _format_calculator_value(eval(expression, {"__builtins__": {}}, {}))
            just_evaluated = True
        except Exception:
            expression, just_evaluated = "خطأ", True
    elif action in operators:
        if expression == "":
            expression = "-" if action == "-" else ""
        elif expression[-1] in operators:
            expression = expression[:-1] + action
        else:
            expression += action
        just_evaluated = False
    elif action == ".":
        if just_evaluated:
            expression, just_evaluated = "0.", False
        else:
            current_number = re.split(r"[+\-*/]", expression)[-1]
            if "." not in current_number:
                expression += "." if current_number else "0."
    elif action.isdigit():
        if just_evaluated:
            expression = ""
        expression += action
        just_evaluated = False

    return {"expression": expression, "just_evaluated": just_evaluated}


def clone_menu_keyboard():
    return [
        [Button.inline("🎭 بدء تغيير المظهر", b"clone_start"), Button.inline("↩️ إعادة حسابي", b"clone_restore")],
        [Button.inline("📖 الشرح اليدوي", b"clone_info")],
        [Button.inline("🔙 رجوع", b"source_features_menu")]
    ]


def welcome_menu_keyboard(user_id):
    info = users_db.get(user_id, {})
    welcome_status = "✅" if info.get("welcome_enabled", False) else "❌"
    smart_status = "✅" if info.get("smart_replies_enabled", False) else "❌"
    return [
        [Button.inline(f"تفعيل/تعطيل الترحيب [{welcome_status}]", b"toggle_welcome")],
        [Button.inline("📝 تعيين الترحيب", b"set_welcome_text"), Button.inline("🖼️ تعيين صورة الترحيب", b"set_welcome_photo")],
        [Button.inline("🗑️ حذف صورة الترحيب", b"delete_welcome_photo"), Button.inline("📋 جلب الترحيب", b"get_welcome")],
        [Button.inline(f"تفعيل/تعطيل ردود موجود [{smart_status}]", b"toggle_smart_replies")],
        [Button.inline("🔙 رجوع", b"source_features_menu")]
    ]


def auto_publish_menu_keyboard():
    return [
        [Button.inline("📖 شرح الأوامر اليدوية", b"auto_publish_info")],
        [Button.inline("📊 عمليات النشر الشغالة", b"auto_publish_running")],
        [Button.inline("🛑 إيقاف كل النشر", b"auto_publish_stop_all")],
        [Button.inline("🔙 رجوع", b"source_features_menu")]
    ]


def conversion_menu_keyboard():
    return [
        [Button.inline("🖼️ ملصق/GIF إلى صورة", b"convert_image_start")],
        [Button.inline("🎗️ صورة إلى ملصق", b"convert_sticker_start")],
        [Button.inline("🎧 فيديو إلى صوت", b"convert_audio_start")],
        [Button.inline("🎤 صوت إلى بصمة", b"convert_voice_start")],
        [Button.inline("📖 الشرح اليدوي", b"conversion_info")],
        [Button.inline("🔙 رجوع", b"source_features_menu")]
    ]


def id_menu_keyboard():
    return [
        [Button.inline("💳 عرض آيدي حسابي", b"show_my_id")],
        [Button.inline("🔎 البحث بيوزر أو آيدي", b"lookup_id_start")],
        [Button.inline("📖 الشرح اليدوي", b"id_info")],
        [Button.inline("🔙 رجوع", b"source_features_menu")]
    ]

def storage_group_menu_keyboard():
    return [
        [Button.inline("➕ إنشاء مجموعة التخزين", b"create_storage_group")],
        [Button.inline("📋 مجموعات التخزين الحالية", b"list_storage_groups")],
        [Button.inline("❌ حذف مجموعة تخزين", b"del_storage_group_start")],
        [Button.inline("🔙 رجوع", b"source_features_menu")]
    ]
def voice_menu_keyboard(user_id):
    u = users_db.get(user_id, {})
    v_st = "✅" if u.get("del_voice_cmd", True) else "❌"
    return [
        [Button.inline("➕ إضافة صوتية", b"add_voice"), Button.inline("📂 عرض الصوتيات", b"show_voice")],
        [Button.inline(f"🗑️ مسح أمر الصوتية [{v_st}]", b"tog_voice_cmd")],
        [Button.inline("❌ حذف صوتية محددة", b"del_voice_item"), Button.inline("⚠️ مسح جميع الصوتيات", b"clear_voice")],
        [Button.inline("🔙 رجوع", b"source_features_menu")]
    ]

def tastir_menu_keyboard(user_id):
    u = users_db.get(user_id, {})
    t_st = "✅" if u.get("del_tastir_start", True) else "❌"
    t_sp = "✅" if u.get("del_tastir_stop", True) else "❌"
    return [
        [Button.inline("➕ إضافة جمل التسطير", b"add_tastir"), Button.inline("📋 عرض الجمل", b"show_tastir")],
        [Button.inline("▶️ إضافة أمر تشغيل", b"add_tastir_start"), Button.inline("📜 أوامر التشغيل", b"show_tastir_start")],
        [Button.inline("⏹️ إضافة أمر إيقاف", b"add_tastir_stop"), Button.inline("📜 أوامر الإيقاف", b"show_tastir_stop")],
        [Button.inline(f"🗑️ مسح أمر التشغيل [{t_st}]", b"tog_tastir_start"), Button.inline(f"🗑️ مسح أمر الإيقاف [{t_sp}]", b"tog_tastir_stop")],
        [Button.inline("❌ خيارات حذف جمل التسطير", b"del_tastir_sub")],
        [Button.inline("❌ حذف أوامر التشغيل", b"clear_tastir_start"), Button.inline("❌ حذف أوامر الإيقاف", b"clear_tastir_stop")],
        [Button.inline("🔙 رجوع", b"tastir_section")]
    ]

def fardiyyat_menu_keyboard(user_id):
    u = users_db.get(user_id, {})
    f_st = "✅" if u.get("del_fardiyyat_start", True) else "❌"
    f_sp = "✅" if u.get("del_fardiyyat_stop", True) else "❌"
    return [
        [Button.inline("➕ إضافة كلمات الفرديات", b"add_fardiyyat"), Button.inline("📋 عرض الكلمات", b"show_fardiyyat")],
        [Button.inline("▶️ إضافة أمر تشغيل", b"add_fardiyyat_start"), Button.inline("📜 أوامر التشغيل", b"show_fardiyyat_start")],
        [Button.inline("⏹️ إضافة أمر إيقاف", b"add_fardiyyat_stop"), Button.inline("📜 أوامر الإيقاف", b"show_fardiyyat_stop")],
        [Button.inline(f"🗑️ مسح أمر التشغيل [{f_st}]", b"tog_fardiyyat_start"), Button.inline(f"🗑️ مسح أمر الإيقاف [{f_sp}]", b"tog_fardiyyat_stop")],
        [Button.inline("❌ خيارات حذف الفرديات", b"del_fardiyyat_sub")],
        [Button.inline("❌ حذف أوامر التشغيل", b"clear_fardiyyat_start"), Button.inline("❌ حذف أوامر الإيقاف", b"clear_fardiyyat_stop")],
        [Button.inline("🔙 رجوع", b"tastir_section")]
    ]

def reply_menu_keyboard(user_id):
    u = users_db.get(user_id, {})
    r_st = "✅" if u.get("del_reply_start", True) else "❌"
    r_sp = "✅" if u.get("del_reply_stop", True) else "❌"
    t_rep_st = "✅" if u.get("include_tastir_in_reply", True) else "❌"
    f_rep_st = "✅" if u.get("include_fardiyyat_in_reply", True) else "❌"
    return [
        [Button.inline("➕ إضافة جمل الريبلاي", b"add_reply"), Button.inline("📋 عرض الجمل", b"show_reply")],
        [Button.inline(f"📝 تضمين التسطير بالريبلاي [{t_rep_st}]", b"tog_rep_tastir")],
        [Button.inline(f"🎯 تضمين الفرديات بالريبلاي [{f_rep_st}]", b"tog_rep_fardiyyat")],
        [Button.inline("▶️ إضافة أمر تشغيل", b"add_reply_start"), Button.inline("📜 أوامر التشغيل", b"show_reply_start")],
        [Button.inline("⏹️ إضافة أمر إيقاف", b"add_reply_stop"), Button.inline("📜 أوامر الإيقاف", b"show_reply_stop")],
        [Button.inline(f"🗑️ مسح أمر التشغيل [{r_st}]", b"tog_reply_start"), Button.inline(f"🗑️ مسح أمر الإيقاف [{r_sp}]", b"tog_reply_stop")],
        [Button.inline("❌ خيارات حذف جمل الريبلاي", b"del_reply_sub")],
        [Button.inline("❌ حذف أوامر التشغيل", b"clear_reply_start"), Button.inline("❌ حذف أوامر الإيقاف", b"clear_reply_stop")],
        [Button.inline("🔙 رجوع", b"tastir_section")]
    ]

def mute_menu_keyboard(user_id):
    u = users_db.get(user_id, {})
    m_st = "✅" if u.get("del_mute_cmd", True) else "❌"
    um_st = "✅" if u.get("del_unmute_cmd", True) else "❌"
    return [
        [Button.inline("🔇 إضافة أمر كتم", b"add_mute_cmd"), Button.inline("📜 أوامر الكتم", b"show_mute_cmds")],
        [Button.inline("🔊 إضافة أمر إلغاء كتم", b"add_unmute_cmd"), Button.inline("📜 أوامر إلغاء الكتم", b"show_unmute_cmds")],
        [Button.inline("❌ خيارات حذف أوامر الكتم", b"del_mute_cmd_sub")],
        [Button.inline("❌ خيارات حذف أوامر إلغاء الكتم", b"del_unmute_cmd_sub")],
        [Button.inline(f"🗑️ مسح أمر الكتم [{m_st}]", b"tog_mute_cmd"), Button.inline(f"🗑️ مسح أمر إلغاء الكتم [{um_st}]", b"tog_unmute_cmd")],
        [Button.inline("👥 عرض المكتومين", b"show_muted_users"), Button.inline("❌ خيارات حذف المكتومين", b"del_muted_users_sub")],
        [Button.inline("🔙 رجوع", b"source_features_menu")]
    ]

def speed_menu_keyboard():
    return [
        [Button.inline("⏱️ 0.5 ثانية", b"spd_0.5"), Button.inline("⏱️ 1 ثانية", b"spd_1")],
        [Button.inline("⏱️ 2 ثانية", b"spd_2"), Button.inline("⏱️ 3 ثانية", b"spd_3")],
        [Button.inline("⏱️ 4 ثانية", b"spd_4"), Button.inline("⏱️ 5 ثانية", b"spd_5")],
        [Button.inline("⏱️ 6 ثانية", b"spd_6"), Button.inline("⏱️ 7 ثانية", b"spd_7")],
        [Button.inline("⏱️ 8 ثانية", b"spd_8"), Button.inline("⏱️ 9 ثانية", b"spd_9")],
        [Button.inline("⏱️ 10 ثانية", b"spd_10")],
        [Button.inline("🔙 رجوع", b"tastir_section")]
    ]

def admin_menu_keyboard(user_id):
    buttons = [
        [Button.inline("👥 قسم المستخدمين", b"admin_users_menu")],
        [Button.inline("📝 إدارة الكلمات والجمل", b"admin_words_menu"), Button.inline("🎟️ أكواد التفعيل", b"admin_codes_menu")],
        [Button.inline("📢 إذاعة عامة", b"broadcast_start"), Button.inline("📊 إحصائيات النظام", b"admin_stats")],
    ]
    if is_owner(user_id) or is_responsible(user_id):
        buttons.insert(1, [Button.inline("👑 قسم المسؤولين", b"admin_admins_menu")])
        buttons.insert(3, [Button.inline("💾 إدارة بيانات البوت", b"admin_data_menu")])
    buttons.append([Button.inline("🔙 رجوع", b"main_menu")])
    return buttons


def admin_users_keyboard():
    return [
        [Button.inline("📋 قائمة المستخدمين", b"list_users")],
        [Button.inline("➕ تفعيل مستخدم بالآيدي", b"manual_activate_start"), Button.inline("📅 تمديد اشتراك", b"extend_subscription_start")],
        [Button.inline("🗑️ حذف مستخدم نهائياً", b"revoke_user_start")],
        [Button.inline("◀️ رجوع", b"admin_menu")]
    ]


def admin_admins_keyboard(user_id):
    buttons = [[Button.inline("🔎 كشف قائمة المسؤولين", b"list_responsibles")]]
    if is_owner(user_id):
        buttons.extend([
            [Button.inline("⭐ رفع مسؤول", b"add_responsible_start"), Button.inline("❌ حذف مسؤول", b"delete_responsible_start")],
            [Button.inline("👥 قائمة الإدارة", b"list_admins")],
            [Button.inline("➕ إضافة أدمن", b"add_admin_start"), Button.inline("❌ حذف أدمن", b"delete_admin_start")],
        ])
    buttons.append([Button.inline("◀️ رجوع", b"admin_menu")])
    return buttons


def admin_words_keyboard():
    return [
        [Button.inline("📝 إدارة التسطير الأساسي", b"admin_tastir_menu")],
        [Button.inline("🎯 إدارة الفرديات الأساسية", b"admin_fardiyyat_menu")],
        [Button.inline("◀️ رجوع", b"admin_menu")]
    ]


def admin_codes_keyboard():
    return [
        [Button.inline("🎟️ توليد كود التسطير", b"gen_code"), Button.inline("⭐ توليد كود السورس", b"gen_source_code")],
        [Button.inline("✨ توليد كود جميع الصلاحيات", b"gen_all_code")],
        [Button.inline("📋 سجل التفعيل", b"activation_log_menu"), Button.inline("⌛ الأكواد المنتهية", b"expired_codes_menu")],
        [Button.inline("◀️ رجوع", b"admin_menu")]
    ]


def admin_data_keyboard(user_id):
    # المسؤول يرى إدارة البيانات ويستعمل أدوات العرض والنسخ؛ تغيير ملكية البوت وصلاحياته للريس فقط.
    buttons = [
        [Button.inline("💾 إنشاء نسخة احتياطية كاملة", b"backup_export")],
        [Button.inline("📱 إدارة جلسات الحسابات", b"sessions_menu"), Button.inline("⚠️ سجل الأخطاء", b"admin_error_log_menu")],
    ]
    if is_owner(user_id):
        buttons.insert(0, [Button.inline("📢 تغيير قناة البوت", b"change_channel_start")])
        buttons.insert(1, [Button.inline("👨‍💻 المطورين", b"manage_developers_menu")])
        buttons[2].append(Button.inline("📥 استيراد نسخة احتياطية", b"backup_import_start"))
    buttons.append([Button.inline("◀️ رجوع", b"admin_menu")])
    return buttons


def manual_subscription_keyboard(state):
    t = "✅" if state.get("grant_tastir") else "❌"
    s = "✅" if state.get("grant_source") else "❌"
    mode = "تمديد" if state.get("mode") == "extend" else "تفعيل"
    return [
        [Button.inline(f"تفعيل اشتراك التسطير [{t}]", b"manual_toggle_tastir")],
        [Button.inline(f"تفعيل اشتراك مميزات السورس [{s}]", b"manual_toggle_source")],
        [Button.inline(f"✅ تأكيد {mode} الاشتراك", b"manual_confirm")],
        [Button.inline("❌ إلغاء", b"admin_menu")]
    ]

def admin_tastir_menu_keyboard():
    return [
        [Button.inline("➕ إضافة تسطير أساسي", b"add_def_tastir"), Button.inline("📋 عرض التسطير الأساسي", b"show_def_tastir")],
        [Button.inline("🗑️ حذف جملة أساسية محددة", b"del_def_tastir_item_start"), Button.inline("⚠️ حذف جميع التسطير الأساسي", b"clear_def_tastir")],
        [Button.inline("🔙 رجوع", b"admin_words_menu")]
    ]

def admin_fardiyyat_menu_keyboard():
    return [
        [Button.inline("➕ إضافة فرديات أساسية", b"add_def_fardiyyat"), Button.inline("📋 عرض الفرديات الأساسية", b"show_def_fardiyyat")],
        [Button.inline("🗑️ حذف كلمة أساسية محددة", b"del_def_fardiyyat_item_start"), Button.inline("⚠️ حذف جميع الفرديات الأساسية", b"clear_def_fardiyyat")],
        [Button.inline("🔙 رجوع", b"admin_words_menu")]
    ]

# ==================== Bot Event Handlers ====================
WELCOME_PHOTO_CAPTION_MARKER = "مرحبًا بك في بوت"


async def send_dynamic_profile_welcome(event, user_id, welcome_txt, welcome_entities):
    """يرسل صورة الحساب الحالية مع نص وأزرار /start في رسالة واحدة."""
    buttons = main_menu_keyboard(user_id)
    try:
        # نستدعي أحدث صورة للمالك مباشرة من Telegram ونرسل مرجعها، بلا تنزيل أو رفع جديد.
        owner_profile = await bot.get_entity(OWNER_ID)
        owner_input = InputUser(owner_profile.id, owner_profile.access_hash)
        photos_result = await bot(GetUserPhotosRequest(owner_input, offset=0, max_id=0, limit=1))
        welcome_photo = next((photo for photo in getattr(photos_result, "photos", []) if getattr(photo, "access_hash", None)), None)
        if welcome_photo:
            try:
                return await bot.send_file(
                    event.chat_id,
                    welcome_photo,
                    caption=welcome_txt,
                    buttons=buttons,
                    parse_mode=None,
                    formatting_entities=welcome_entities,
                )
            except Exception as emoji_error:
                # تظل الصورة موجودة حتى لو تعذر إرفاق الإيموجي المميز في caption.
                print(f"[WELCOME PHOTO EMOJI FALLBACK] {emoji_error}")
                return await bot.send_file(
                    event.chat_id,
                    welcome_photo,
                    caption=welcome_txt,
                    buttons=buttons,
                )
    except Exception as photo_error:
        print(f"[WELCOME PROFILE PHOTO FALLBACK] {photo_error}")

    # إذا لم تكن للحساب صورة حالية أو تعذر تحميلها، يظهر الترحيب النصي المعتاد.
    try:
        return await event.respond(
            welcome_txt,
            buttons=buttons,
            link_preview=False,
            parse_mode=None,
            formatting_entities=welcome_entities,
        )
    except Exception as welcome_error:
        print(f"[WELCOME EMOJI FALLBACK] {welcome_error}")
        return await event.respond(welcome_txt, buttons=buttons, link_preview=False)


async def replace_welcome_photo_with_text_menu(event):
    """يحذف ترحيب /start المصور مرة واحدة، ثم يحوّل نفس التنقل إلى رسالة نصية."""
    try:
        original = await event.get_message()
        caption = str(getattr(original, "raw_text", "") or getattr(original, "message", "") or "")
        if not original or not getattr(original, "photo", None) or WELCOME_PHOTO_CAPTION_MARKER not in caption:
            return False

        # رسالة انتقال غير مرئية تُحرر موضعاً للقائمة النصية الجديدة، فلا يظهر للمستخدم أي نص انتظار.
        replacement = await bot.send_message(event.chat_id, "\u2063", link_preview=False)
        await bot.delete_messages(event.chat_id, [original.id])
        # تجعل كل event.edit لاحق في الفرع الحالي يعدّل رسالة النص الجديدة بدل رسالة الصورة المحذوفة.
        event.query.msg_id = replacement.id
        event._message = replacement
        return True
    except Exception as exc:
        print(f"[WELCOME PHOTO REPLACE ERROR] {exc}")
        return False


@bot.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    user_id = event.sender_id
    init_user_db(user_id)
    args = event.text.split()
    if len(args) > 1:
        code = args[1].strip()
        success, days = await apply_activation_code(user_id, code, event)
        if success:
            await event.respond(f"✅ تم تفعيل اشتراك التسطير بنجاح لمدة {days} يوم.")
        else:
            success_src, days_src = await apply_source_activation_code(user_id, code, event)
            if success_src:
                await event.respond(f"✅ تم تفعيل مميزات السورس بنجاح لمدة {days_src} يوم.")
            else:
                success_all, days_all = await apply_full_activation_code(user_id, code, event)
                if success_all:
                    await event.respond(f"✅ تم تفعيل كود جميع الصلاحيات بنجاح لمدة {days_all} يوم. تم تفعيل التسطير ومميزات السورس معاً.")
                else:
                    await report_admin_error("كود تفعيل غير صالح", "محاولة كود غير صالح أو مستخدم", user_id)
                    await event.respond("❌ رمز التفعيل غير صالح أو تم استخدامه سابقاً.")
    welcome_txt, welcome_entities = build_damon_welcome_message()
    await send_dynamic_profile_welcome(event, user_id, welcome_txt, welcome_entities)


# ==================== AI Section: smooth in-place navigation ====================
async def _edit_ai_view(event, text, buttons):
    """يحدّث نفس رسالة القائمة فقط؛ لا يحذفها ولا ينشئ رسالة قائمة جديدة."""
    try:
        await event.edit(text, buttons=buttons, link_preview=False)
    except MessageNotModifiedError:
        pass
    except Exception as exc:
        print(f"[AI MENU EDIT ERROR] {exc}")
        try:
            await event.answer("⚠️ تعذر تحديث القائمة، جرّب فتح مميزات السورس مرة أخرى.", alert=True)
        except Exception:
            pass


async def send_ai_main_menu(event):
    txt = (
        "🤖 **قسم الذكاء الاصطناعي**\n"
        "⋆ ———————————————————— ⋆\n\n"
        "اختر القسم الذي تريد استخدامه أو الاطلاع على شرحه من الأزرار التالية."
    )
    buttons = [
        [Button.inline("🎙️ الأصوات 1 — البنات", b"ai_voices_help")],
        [Button.inline("🧠 الذكاء الاصطناعي", b"ai_chat_help")],
        [Button.inline("🔙 رجوع إلى مميزات السورس", b"source_features_menu")],
    ]
    await _edit_ai_view(event, txt, buttons)


async def send_ai_chat_help(event):
    txt = (
        "🧠 **شرح الذكاء الاصطناعي والبحث**\n"
        "⋆ ———————————————————— ⋆\n\n"
        "• `.تفعيل الذكاء الاصطناعي`\n"
        "↞ لتشغيل الدردشة والبحث الذكي على حسابك.\n\n"
        "• `.تعطيل الذكاء الاصطناعي`\n"
        "↞ لإيقاف الدردشة والبحث الذكي.\n\n"
        "• `.ذكاء [سؤالك أو طلبك]`\n"
        "↞ للدردشة وطرح الأسئلة والبحث الذكي.\n\n"
        "**مثال:** `.ذكاء ما هي أفضل طريقة لتنظيم الوقت؟`\n\n"
        "📌 يجب تفعيل الذكاء أولاً قبل استخدام أمر `.ذكاء`."
    )
    await _edit_ai_view(event, txt, [[Button.inline("🔙 رجوع لقسم الذكاء", b"ai_main_menu")]])


async def send_12_voices_guide_smooth(event):
    """عرض أصوات البنات المتاحة فقط عبر تعديل الرسالة نفسها."""
    txt = (
        "🎙️ **الأصوات 1 — أصوات البنات الواقعية**\n"
        "⋆ ———————————————————— ⋆\n\n"
        "• `.بنت 1 [النص]` ↞ ناعم ودلوع.\n"
        "• `.بنت 2 [النص]` ↞ حنون وهادئ.\n"
        "• `.بنت 3 [النص]` ↞ خفيف ومرح.\n"
        "• `.بنت 4 [النص]` ↞ لطيف وواضح.\n"
        "• `.بنت 5 [النص]` ↞ دافئ ومريح.\n"
        "• `.بنت 6 [النص]` ↞ ناعم وثقيل.\n"
        "• `.بنت 7 [النص]` ↞ هادئ وفخم.\n\n"
        "💡 **طريقة الاستخدام:**\n"
        "• اكتب الأمر بالنقطة مع النص، مثال: `.بنت 1 هلا والله`.\n"
        "• أو ردّ على رسالة ثم اكتب الأمر لتحويل نصها إلى فويس.\n\n"
        "📌 هذه هي جميع أصوات البنات المتاحة فعلياً للحساب الحالي عبر API."
    )
    await _edit_ai_view(event, txt, [[Button.inline("🔙 رجوع لقسم الذكاء", b"ai_main_menu")]])


@bot.on(events.CallbackQuery)
async def callback_handler(event):
    global default_tastir, default_fardiyyat, default_reply, CHANNEL_URL, DEV_URL
    user_id = event.sender_id
    data = event.data
    init_user_db(user_id)
    # إذا كان الزر من ترحيب /start المصور، نحذفه أولاً ثم يكمل الفرع الحالي على قائمة نصية.
    await replace_welcome_photo_with_text_menu(event)
    track_menu_navigation(user_id, data)

    if data in OWNER_ONLY_CALLBACKS and not is_owner(user_id):
        await event.answer("⚠️ تعذر الوصول: هذه الإدارة مخصصة للريس فقط.", alert=True)
        return

    # هذه المعالجات أولاً حتى لا تتعارض معها أي فروع قديمة.
    # توافق مع أي رسائل قائمة قديمة تحمل المعرف السابق.
    if data in (b"ai_main_menu", b"ai_section_menu"):
        await event.answer()
        await send_ai_main_menu(event)
        return
    if data == b"ai_chat_help":
        await event.answer()
        await send_ai_chat_help(event)
        return
    if data == b"ai_voices_help":
        await event.answer()
        await send_12_voices_guide_smooth(event)
        return

    fast_menu_callbacks = {
        b"main_menu", b"tastir_section", b"tastir_menu", b"fardiyyat_menu", b"reply_menu", b"nick_am_menu", b"speed_menu",
        b"source_features_menu", b"flush_section", b"flush_menu", b"mute_menu", b"voice_menu", b"clone_menu", b"welcome_menu",
        b"auto_publish_menu", b"conversion_menu", b"id_menu", b"ai_main_menu", b"ai_chat_help", b"ai_voices_help", b"section_account", b"section_publish", b"section_download", b"section_tools",
        b"youtube_menu", b"tiktok_menu", b"instagram_menu", b"pinterest_menu", b"story_menu", b"github_menu", b"writing_menu", b"ai_section_menu",
    }
    if data in fast_menu_callbacks:
        try:
            await event.answer()
        except Exception:
            pass

    if data in [b"main_menu", b"tastir_section", b"tastir_menu", b"fardiyyat_menu", b"reply_menu", b"flush_section", b"flush_menu", b"mute_menu", b"source_features_menu", b"voice_menu", b"admin_menu", b"admin_users_menu", b"admin_admins_menu", b"admin_words_menu", b"admin_codes_menu", b"admin_data_menu", b"admin_tastir_menu", b"admin_fardiyyat_menu", b"clone_menu", b"welcome_menu", b"auto_publish_menu", b"conversion_menu", b"id_menu", b"ai_main_menu", b"ai_chat_help", b"ai_voices_help"]:
        user_states.pop(user_id, None)

    if data.startswith(b"calc_"):
        key = (event.chat_id, event.message_id, user_id)
        action = data.decode()[5:]
        session = process_calculator_action(calculator_sessions.get(key, ""), action)
        calculator_sessions[key] = session
        display = session["expression"] or "0"
        try:
            await event.edit(f"📟 **الآلة الحاسبة**\n\n`{display}`", buttons=calculator_keyboard())
        except MessageNotModifiedError:
            await event.answer()
        return

    if data == b"main_menu":
        # الأزرار القديمة التي كانت تعيد للرئيسية تستعمل الآن آخر قائمة فعلية كخطوة رجوع واحدة.
        stack = navigation_history.get(int(user_id), [])
        if len(stack) > 1:
            stack.pop()
            data = stack[-1]
        else:
            navigation_history.pop(int(user_id), None)

    if data == b"main_menu":
        welcome_txt, welcome_entities = build_damon_welcome_message()
        try:
            try:
                await event.edit(
                    welcome_txt,
                    buttons=main_menu_keyboard(user_id),
                    link_preview=False,
                    parse_mode=None,
                    formatting_entities=welcome_entities,
                )
            except Exception as welcome_error:
                print(f"[WELCOME MENU EMOJI FALLBACK] {welcome_error}")
                await event.edit(welcome_txt, buttons=main_menu_keyboard(user_id), link_preview=False)
        except MessageNotModifiedError:
            await event.answer()

    elif data == b"flush_section":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit("💥 **قسم التفليش:**\n\nاختر التفليش عبر البوت أو راجع شرح الأوامر اليدوية.", buttons=flush_section_keyboard())

    elif data == b"flush_menu":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        await event.edit("⚡ **قائمة التفليش عبر البوت:**\n\nاختر ما يناسبك من الخيارات أدناه:", buttons=flush_menu_keyboard())

    elif data == b"manual_flush_info":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        txt = (
            "⤾ اوامـر التفلـيش اليدوي 🚷\n"
            "⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆\n\n"
            "• `.تفليش بالطرد`\n"
            "≫ لكتابة الأمر داخل المجموعة أو وضع الآيدي بعد الأمر.\n\n"
            "• `.تفليش بالحظر`\n"
            "≫ لكتابة الأمر داخل المجموعة أو وضع الآيدي بعد الأمر.\n\n"
            "• `.ايقاف التفليش`\n"
            "≫ لإيقاف التفليش في حال كان شغالاً."
        )
        await event.edit(
            txt,
            buttons=[
                [Button.inline("🔙 رجوع إلى قسم التفليش", b"flush_section")]
            ]
        )

    elif data == b"flush_speed_menu":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        await event.edit("⚡ **اختر سرعة التفليش:**", buttons=flush_speed_menu_keyboard(user_id))

    elif data.startswith(b"fspd_"):
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        spd_val = float(data.decode()[5:])
        users_db[user_id]["flush_speed"] = spd_val
        save_data()
        await event.answer(f"✅ تم ضبط سرعة التفليش إلى {spd_val} ثانية.", alert=True)
        await event.edit("⚡ **اختر سرعة التفليش:**", buttons=flush_speed_menu_keyboard(user_id))

    elif data == b"start_flush_flow":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        if user_id not in user_clients:
            await event.answer("⚠️ يرجى تسجيل الدخول بحسابك (اليوزر بوت) أولاً عبر زر تسجيل الدخول في الرئيسية.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_flush_target"}
        await event.edit(
            "🚀 **بدء التفليش:**\n\n"
            "يرجى إرسال **رابط القروب/القناة** أو **المعرف الرقمي (ID)** الخاص بالقروب أو القناة الآن:",
            buttons=[[Button.inline("🔙 رجوع إلى قسم التفليش", b"flush_section")]]
        )

    elif data.startswith(b"confirm_flush_action_"):
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
            
        ans = data.decode().split("_")[-1]
        st = user_states.get(user_id, {})
        chat_id = st.get("chat_id")
        
        if ans == "no":
            user_states.pop(user_id, None)
            await event.edit("❌ تم إلغاء عملية التفليش.", buttons=[[Button.inline("🔙 رجوع إلى قسم التفليش", b"flush_section")]])
            return

        client = user_clients.get(user_id)
        if not client:
            await event.answer("⚠️ جلسة الحساب غير متصلة.", alert=True)
            return
            
        user_states.pop(user_id, None)
        me = await client.get_me()
        # السرعة التي اختارها المستخدم تطبق فعلياً؛ الحد الأدنى يحمي الحلقة من قيمة سالبة أو صفرية.
        selected_speed = 0.01
        selected_speed = max(0.05, min(selected_speed, 5.0))
        status_msg = await event.edit(
            f"⏳ جاري بدء التفليش...\n\n• السرعة: `{selected_speed}` ثانية\n• اضغط إيقاف التفليش في أي وقت.",
            buttons=[[Button.inline("⏹️ إيقاف التفليش", f"stop_bot_flush_{chat_id}")]]
        )
        task_key = (user_id, int(chat_id))
        previous_task = bot_flush_tasks.get(task_key)
        if previous_task and not previous_task.done():
            previous_task.cancel()
        
        async def fast_flush():
            count = 0
            failed = 0
            start_time = time.time()
            try:
                chat_entity = await client.get_entity(chat_id)
                async for member in client.iter_participants(chat_entity):
                    if member.id == me.id:
                        continue
                    try:
                        await client(EditBannedRequest(chat_entity, member.id, ChatBannedRights(until_date=None, view_messages=True)))
                        count += 1
                        await asyncio.sleep(selected_speed)
                    except Exception as exc:
                        err_str = str(exc).upper()
                        if "FLOOD_WAIT" in err_str:
                            match = re.search(r"\d+", err_str)
                            wait_time = int(match.group()) if match else 5
                            await status_msg.edit(
                                f"⚠️ تم تقييد السرعة مؤقتاً من تيليجرام. جارٍ الانتظار `{wait_time}` ثانية...\n\n• تم التعامل مع: `{count}`",
                                buttons=[[Button.inline("⏹️ إيقاف التفليش", f"stop_bot_flush_{chat_id}")]]
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        if any(marker in err_str for marker in ("USER_ADMIN_INVALID", "CHAT_ADMIN_REQUIRED", "RIGHTS_NOT_AVAILABLE")):
                            raise PermissionError("انسحبت صلاحية الحظر أو لم تعد متاحة أثناء التفليش.")
                        # نجرب الطرد العادي للحالات التي لا تقبل الحظر المباشر.
                        try:
                            await client.delete_chat_user(chat_entity, member.id)
                            count += 1
                            await asyncio.sleep(selected_speed)
                        except Exception:
                            failed += 1
            except asyncio.CancelledError:
                elapsed = round(time.time() - start_time, 1)
                await status_msg.edit(
                    f"⏹️ **تم إيقاف التفليش.**\n\n• تم التعامل مع: `{count}` عضواً\n• فشل: `{failed}`\n• الوقت: `{elapsed}` ثانية",
                    buttons=[[Button.inline("🔙 رجوع إلى قسم التفليش", b"flush_section")]]
                )
                raise
            except Exception as exc:
                elapsed = round(time.time() - start_time, 1)
                await status_msg.edit(
                    f"⚠️ **توقف التفليش:** {exc}\n\n• تم التعامل مع: `{count}` عضواً\n• فشل: `{failed}`\n• الوقت: `{elapsed}` ثانية",
                    buttons=[[Button.inline("🔙 رجوع إلى قسم التفليش", b"flush_section")]]
                )
            else:
                elapsed = round(time.time() - start_time, 1)
                await status_msg.edit(
                    f"✅ **انتهى التفليش.**\n\n• تم التعامل مع: `{count}` عضواً\n• فشل: `{failed}`\n• السرعة: `{selected_speed}` ثانية\n• الوقت: `{elapsed}` ثانية",
                    buttons=[[Button.inline("🔙 رجوع إلى قسم التفليش", b"flush_section")]]
                )
            finally:
                bot_flush_tasks.pop(task_key, None)
                
        bot_flush_tasks[task_key] = asyncio.create_task(fast_flush())

    elif data.startswith(b"stop_bot_flush_"):
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ هذه المهمة تخص مستخدم آخر أو اشتراكك غير فعال.", alert=True)
            return
        try:
            target_chat_id = int(data.decode().rsplit("_", 1)[-1])
        except Exception:
            await event.answer("تعذر تحديد مهمة التفليش.", alert=True)
            return
        task = bot_flush_tasks.get((user_id, target_chat_id))
        if task and not task.done():
            task.cancel()
            await event.answer("⏹️ جاري إيقاف التفليش...", alert=False)
        else:
            await event.answer("لا توجد عملية تفليش شغالة حالياً.", alert=True)
        return

    elif data == b"cancel_flush":
        user_states.pop(user_id, None)
        await event.edit("💥 **قسم التفليش:**", buttons=flush_section_keyboard())

    elif data == b"tastir_section":
        if not is_subscribed(user_id):
            await event.answer("⚠️ هذا القسم يحتاج كود تفعيل التسطير.", alert=True)
            return
        await event.edit("📝 **قسم التسطير:**\n\nاختر ما تريد من الأسفل.", buttons=tastir_section_keyboard(user_id))

    elif data == b"source_features_menu":
        is_src = is_source_subscribed(user_id)
        txt = (
            "⭐ **مميزات السورس:**\n\n"
            "اختر الخاصية التي تريد الاستعلام عنها أو التحكم بها من القائمة أدناه:\n\n"
        )
        if not is_src:
            txt = (
                "⭐ **مميزات السورس:**\n\n"
                "⚠️ **تنبيه:** تواصل معى المطور لتزويدك بكود اشتراك لمميزات السورس والمستخدم م راح يقدر يستخدم مميزات السورس لين يرسل كود تفعيل مميزات السورس.\n\n"
                "يمكنك استعراض الخصائص المضافة أدناه:"
            )
            
        buttons = source_features_menu_keyboard()
        if not is_src:
            buttons.insert(0, [Button.inline("🎟️ تفعيل مميزات السورس", b"enter_source_code_start")])
            
        await event.edit(txt, buttons=buttons)

    elif data == b"clone_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(
            "🎭 **قائمة تغيير مظهر الحساب:**\n\n"
            "يمكنك تطبيق الاسم والبايو والصورة المتاحة لحساب تختاره، مع حفظ بياناتك الحالية لتستعمل زر الإعادة لاحقاً.",
            buttons=clone_menu_keyboard()
        )

    elif data == b"clone_info":
        await event.edit(
            "📖 **شرح تغيير المظهر:**\n\n"
            "• يدوياً: اكتب `.انتحال @user` أو رد على شخص واكتب `.انتحال`.\n"
            "• بالأزرار: اختر بدء تغيير المظهر ثم أرسل اليوزر أو الآيدي.\n"
            "• للإعادة إلى النسخة المحفوظة اكتب `.اعاده`.\n\n"
            "سيتم حفظ اسمك وبايوك وصورتك الحالية قبل التغيير.",
            buttons=[[Button.inline("🔙 رجوع", b"clone_menu")]]
        )

    elif data == b"clone_start":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        if user_id not in user_clients:
            await event.answer("⚠️ يرجى تسجيل الدخول بحسابك أولاً.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_clone_target"}
        await event.edit("🎭 أرسل يوزر المستخدم أو آيديه لتطبيق الاسم والبايو والصورة المتاحة لحسابه:", buttons=[[Button.inline("🔙 رجوع", b"clone_menu")]])

    elif data == b"clone_restore":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        client = user_clients.get(user_id)
        if not client:
            await event.answer("⚠️ جلسة اليوزر بوت غير متصلة.", alert=True)
            return
        await event.edit("⏳ جاري إعادة بيانات حسابك المحفوظة...")
        try:
            await restore_profile_template(client, user_id)
            await event.edit("✅ تمت إعادة الاسم والبايو والصورة المحفوظة لحسابك بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"clone_menu")]])
        except Exception as e:
            await event.edit(f"❌ تعذرت الإعادة:\n`{e}`", buttons=[[Button.inline("🔙 رجوع", b"clone_menu")]])

    elif data == b"welcome_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(WELCOME_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"toggle_welcome":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        users_db[user_id]["welcome_enabled"] = not users_db[user_id].get("welcome_enabled", False)
        save_data()
        state_txt = "تفعيل" if users_db[user_id]["welcome_enabled"] else "تعطيل"
        await event.answer(f"✅ تم {state_txt} الترحيب الخاص.", alert=True)
        await event.edit("👋 **أوامر الترحيب والردود:**", buttons=welcome_menu_keyboard(user_id))

    elif data == b"set_welcome_text":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        user_states[user_id] = {"step": "awaiting_welcome_text"}
        await event.edit("📝 أرسل نص الترحيب الجديد الآن:", buttons=[[Button.inline("🔙 رجوع", b"welcome_menu")]])
        asyncio.create_task(delete_message_after(event.message, 10))

    elif data == b"set_welcome_photo":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        user_states[user_id] = {"step": "awaiting_welcome_photo"}
        await event.edit("🖼️ أرسل صورة الترحيب الآن:", buttons=[[Button.inline("🔙 رجوع", b"welcome_menu")]])
        asyncio.create_task(delete_message_after(event.message, 10))

    elif data == b"delete_welcome_photo":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        photo_path = users_db[user_id].get("welcome_photo")
        _safe_remove(photo_path)
        users_db[user_id]["welcome_photo"] = None
        save_data()
        await event.answer("✅ تم حذف صورة الترحيب.", alert=True)
        await event.edit("👋 **أوامر الترحيب والردود:**", buttons=welcome_menu_keyboard(user_id))

    elif data == b"get_welcome":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        txt = users_db[user_id].get("welcome_text", "أهلاً بك، نورت الخاص.")
        photo_path = users_db[user_id].get("welcome_photo")
        await event.edit(f"📋 **نص الترحيب الحالي:**\n\n{txt}", buttons=[[Button.inline("🔙 رجوع", b"welcome_menu")]])
        if photo_path and os.path.exists(photo_path):
            await bot.send_file(user_id, photo_path, caption="🖼️ صورة الترحيب الحالية")

    elif data == b"toggle_smart_replies":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        users_db[user_id]["smart_replies_enabled"] = not users_db[user_id].get("smart_replies_enabled", False)
        save_data()
        state_txt = "تفعيل" if users_db[user_id]["smart_replies_enabled"] else "تعطيل"
        await event.answer(f"✅ تم {state_txt} ردود موجود.", alert=True)
        await event.edit("👋 **أوامر الترحيب والردود:**", buttons=welcome_menu_keyboard(user_id))

    elif data == b"auto_publish_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit("📍 **قائمة النشر التلقائي:**\n\nيمكنك عرض شرح الأوامر، ومتابعة عمليات النشر أو إيقافها من الأزرار.", buttons=auto_publish_menu_keyboard())

    elif data == b"publish_required_add":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        user_states[user_id] = {"step": "awaiting_publish_required_add"}
        await event.edit("➕ أرسل يوزر أو رابط القروب/القناة المطلوب اشتراك حساب النشر فيه تلقائياً قبل النشر.\n\nمثال: `@channel` أو `https://t.me/channel`", buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]])

    elif data == b"publish_required_list":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        items = users_db[user_id].get("publish_required_chats", [])
        body = "\n".join(f"• `{item}`" for item in items) if items else "لا توجد اشتراكات نشر مضافة."
        await event.edit("📋 **اشتراكات النشر الإلزامية:**\n\n" + body, buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]])

    elif data == b"publish_required_delete_start":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        items = users_db[user_id].get("publish_required_chats", [])
        if not items:
            await event.answer("لا توجد اشتراكات نشر لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_publish_required_delete"}
        await event.edit("🗑️ أرسل نفس اليوزر أو الرابط الذي تريد حذفه من اشتراكات النشر.\n\n" + "\n".join(f"• `{item}`" for item in items), buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]])

    elif data == b"auto_publish_info":
        await event.edit(
            "⤾ اوامــر النـشــر التـلـقـائـي  📍\n"
            "⋆————‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 ›————⋆  \n\n"
            "← للنشر من داخـل المجمـوعة ↓  \n"
            "• .نشر + عدد الثواني + عدد المرات + تحويل  \n"
            "• .واو + عدد الثواني + عدد المرات + تحويل  \n"
            "↞ بـالـرد علـى الرسالـه المـراد نشرهـا 🚀\n\n"
            "← للنشر من خارج المجمـوعة 🔥 ↓  \n"
            "• .ستارت + عدد الثواني + عدد المرات + ايدي المجموعة + تحويل  \n"
            "↞ بالـرد على الرسالة المـراد نشـرها 🚀\n\n"
            "• ملاحظات هامـه ❕❔\n"
            "1 - كـل اوامـر النشـر تدعم الملصقات المميزه ⭐ + تدعـم صـورة واحـدة  \n"
            "2 - يمكنك الحصـول على ايدي المجموعات من هنا @is_idbot 🤖\n"
            "3 - للنشـر بـدون توقـف ضـع عـدد مـرات 999  \n\n"
            "• .النشر الشغال  \n"
            "↞ لـ معـرفـة عمليات النشـر الشغالـه حاليا ⛄  \n\n"
            "• .بس  \n"
            "↞ لـ إيقـاف النشر التلقائي في مجموعه معينه 📌  \n"
            "↞ قـم بكتابـه الامـر داخل المجموعة  \n\n"
            "• .ايقاف النشر  \n"
            "↞ لـ إيقـاف جميـع عمليـات النشـر التلقـائـي المرتبطـة بـك 🎡  \n\n"
            "↜ ملاحظـه ❕  \n"
            "- اوامـر النشـر التلقـائي قد تكـون خطيـره علـى بعـض الحسـابـات بسبـب سياسـة تلجـرام\n\n"
            "• التحويل ↔\n"
            "- لا تكتب كلمة تحويل = ينشر البوت نسخة من النص أو الوسيط بدون إظهار مصدر الرسالة.\n"
            "- اكتب تحويل في نهاية الأمر = يرسلها كتحويل ويظهر مصدرها.\n"
            "مثال: `.نشر 3 10 تحويل`\n"
            "مثال بدون تحويل: `.نشر 3 10`",
            buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]]
        )
    elif data == b"auto_publish_running":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        active_publish_keys = {(key[1], str(key[2])) for key, task in auto_publish_tasks.items() if not task.done()}
        jobs = [job for job in users_db.get(user_id, {}).get("auto_publish_jobs", [])
                if (int(job.get("target_chat_id", 0)), str(job.get("operation_id", ""))) in active_publish_keys]
        client = user_clients.get(user_id)
        rows = []
        for job in jobs:
            target_id = int(job.get("target_chat_id", 0))
            target_name = await _publish_target_name(client, target_id) if client else str(target_id)
            rows.append(f"• **{target_name}** — `{target_id}`\n  تم إرسال: `{job.get('completed', 0)}` من `{job.get('count', 0)}`")
        text = "📊 **عمليات النشر الشغالة:**\n\n" + ("\n".join(rows) if rows else "لا توجد عمليات نشر حالياً.")
        await event.edit(text, buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]])

    elif data == b"auto_publish_stop_all":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        client = user_clients.get(user_id)
        stopped = await stop_auto_publish_task(client, user_id, reason="تم إيقاف جميع عمليات النشر من لوحة التحكم") if client else 0
        await event.answer(f"✅ تم إيقاف {stopped} عملية نشر.", alert=True)
        await event.edit("📍 **قائمة النشر التلقائي:**", buttons=auto_publish_menu_keyboard())

    elif data == b"conversion_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(CONVERSION_GUIDE, buttons=tools_back_keyboard())

    elif data in [b"convert_image_start", b"convert_sticker_start", b"convert_audio_start", b"convert_voice_start"]:
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        step_map = {
            b"convert_image_start": ("awaiting_convert_image", "أرسل ملصقاً أو GIF لتحويله إلى صورة."),
            b"convert_sticker_start": ("awaiting_convert_sticker", "أرسل صورة لتحويلها إلى ملصق."),
            b"convert_audio_start": ("awaiting_convert_audio", "أرسل فيديو لاستخراج الصوت منه."),
            b"convert_voice_start": ("awaiting_convert_voice", "أرسل ملفاً صوتياً لتحويله إلى بصمة.")
        }
        step, prompt = step_map[data]
        user_states[user_id] = {"step": step}
        await event.edit(f"💾 {prompt}", buttons=[[Button.inline("🔙 رجوع", b"conversion_menu")]])

    elif data == b"conversion_info":
        await event.edit(
            "📖 **التحويل اليدوي:**\n\n"
            "• `.لصوره` بالرد على ملصق أو GIF.\n"
            "• `.لملصق` بالرد على صورة.\n"
            "• `.الصوت` بالرد على فيديو.\n"
            "• `.لبصمه` بالرد على ملف صوتي.",
            buttons=[[Button.inline("🔙 رجوع", b"conversion_menu")]]
        )

    elif data == b"id_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(ID_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"section_account")]])

    elif data == b"show_my_id":
        client = user_clients.get(user_id)
        if not client:
            await event.answer("⚠️ يرجى تسجيل الدخول بحسابك أولاً.", alert=True)
            return
        me = await client.get_me()
        username = f"@{me.username}" if me.username else "ماعنده"
        await event.edit(f"💳 **بياناتك:**\n\n• الاسم: {me.first_name or 'بدون اسم'}\n• الآيدي: `{me.id}`\n• اليوزر: {username}", buttons=[[Button.inline("🔙 رجوع", b"id_menu")]])

    elif data == b"lookup_id_start":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        user_states[user_id] = {"step": "awaiting_id_lookup"}
        await event.edit("🔎 أرسل يوزر المستخدم أو آيديه الآن:", buttons=[[Button.inline("🔙 رجوع", b"id_menu")]])

    elif data == b"id_info":
        await event.edit("📖 **الاستخدام اليدوي:**\n\n• `.ايدي` بدون رد لعرض معلوماتك.\n• بالرد على مستخدم ثم `.ايدي` لعرض معلوماته.\n• أو اكتب `.ايدي @username`.", buttons=[[Button.inline("🔙 رجوع", b"id_menu")]])

    elif data == b"my_data_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        client = user_clients.get(user_id)
        if not client:
            await event.answer("⚠️ يرجى تسجيل الدخول بحسابك أولاً.", alert=True)
            return
        await event.edit("⏳ جاري جمع بيانات حسابك وقنواتك وقروباتك...")
        try:
            report = await get_my_data_report(client, user_id)
            await event.edit(report, buttons=[[Button.inline("🔙 رجوع", b"section_account")]])
        except Exception as e:
            await event.edit(f"❌ تعذر جلب البيانات:\n`{e}`", buttons=[[Button.inline("🔙 رجوع", b"section_account")]])

    elif data == b"account_link_info":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(ACCOUNT_LINK_GUIDE, buttons=tools_back_keyboard())

    elif data == b"creation_info":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(CREATION_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"section_account")]])

    elif data == b"translation_info":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(TRANSLATION_GUIDE, buttons=tools_back_keyboard())

    elif data == b"self_save_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(SELF_SAVE_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"section_self_save")]])

    elif data == b"stats_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(STATS_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"section_account")]])

    elif data == b"chat_lists_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit("💬 **قروباتي وقنواتي**\n\nاختر القائمة التي تريد عرضها.", buttons=chat_lists_keyboard(user_id))

    elif data == b"chat_list_refresh":
        if not is_source_subscribed(user_id) or not (is_owner(user_id) or is_responsible(user_id)):
            await event.answer("⚠️ هذا الزر مخصص للمسؤولين والريس فقط.", alert=True)
            return
        # تحديث شامل وتنشيط لكل الذاكرة المؤقتة والبيانات دون حذف أي معلومة
        client = user_clients.get(user_id)
        if client:
            client_id = id(client)
            for m in ["all", "owner", "admin"]:
                _account_chat_lists_cache.pop((client_id, m), None)
        try:
            save_data()
        except Exception:
            pass
        await event.answer("✅ تم التحديث الشامل وتنشيط كافة البيانات بنجاح دون حذف أي معلومة.", alert=True)
        await event.edit("💬 **قروباتي وقنواتي**\n\nتم التحديث الشامل بنجاح. اختر القائمة التي تريد عرضها:", buttons=chat_lists_keyboard(user_id))

    elif data.startswith(b"chat_list_"):
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        client = user_clients.get(user_id)
        if not client:
            await event.answer("⚠️ يرجى تسجيل الدخول بحسابك أولاً.", alert=True)
            return
        try:
            _, _, category, mode = data.decode().split("_", 3)
            # إرسال رسالة انتظار سريعة جداً عند الجلب الأول لتفادي تعليق واجهة تيليجرام
            await event.edit("⚡ جاري جلب القائمة فوراً...")
            groups, channels = await get_account_chat_lists(client, mode, force_refresh=False)
            is_groups = category == "groups"
            title = "قروباتي" if is_groups else "قنواتي"
            mode_label = {"all": "الكل", "owner": "مالك", "admin": "أدمن"}.get(mode, "الكل")
            await event.edit(format_account_chat_list(groups if is_groups else channels, title, mode_label), buttons=[[Button.inline("🔙 رجوع", b"chat_lists_menu")]])
        except Exception as e:
            await event.edit(f"❌ تعذر جلب القائمة:\n`{e}`", buttons=[[Button.inline("🔙 رجوع", b"chat_lists_menu")]])

    elif data in [b"section_account", b"section_welcome", b"section_self_save", b"section_publish", b"section_download", b"section_tools"]:
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        section_map = {
            b"section_account": ("👤 **قسم الحساب**\n\nاختر ما تريد من الأسفل.", account_section_keyboard()),
            b"section_welcome": ("📬 **قسم الترحيب والردود**\n\nاختر ما تريد من الأسفل.", welcome_section_keyboard()),
            b"section_self_save": ("🧧 **قسم حفظ الذاتية**\n\nاختر ما تريد من الأسفل.", self_save_section_keyboard()),
            b"section_publish": ("📍 **قسم النشر التلقائي**\n\nاختر ما تريد من الأسفل.", publish_section_keyboard()),
            b"section_download": ("🎧 **قسم البحث والتحميل**\n\nاختر ما تريد من الأسفل.", download_section_keyboard()),
            b"section_tools": ("🧰 **قسم الأدوات**\n\nاختر ما تريد من الأسفل.", tools_section_keyboard())
        }
        title, buttons = section_map[data]
        await event.edit(title, buttons=buttons)

    elif data in [b"youtube_menu", b"tiktok_menu", b"instagram_menu", b"pinterest_menu", b"story_menu", b"github_menu", b"restricted_menu", b"writing_menu", b"broadcast_menu", b"leave_cleanup_menu"]:
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        guide_map = {
            b"youtube_menu": YOUTUBE_GUIDE,
            b"tiktok_menu": TIKTOK_GUIDE,
            b"instagram_menu": INSTAGRAM_GUIDE,
            b"pinterest_menu": PINTEREST_GUIDE,
            b"story_menu": STORY_GUIDE,
            b"github_menu": GITHUB_GUIDE,
            b"restricted_menu": RESTRICTED_GUIDE,
            b"writing_menu": WRITING_GUIDE,
            b"broadcast_menu": BROADCAST_GUIDE,
            b"leave_cleanup_menu": LEAVE_CLEANUP_GUIDE
        }
        if data == b"writing_menu":
            buttons = tools_back_keyboard()
        elif data == b"restricted_menu":
            buttons = [[Button.inline("◀️ رجوع", b"section_self_save")]]
        else:
            buttons = [[Button.inline("◀️ رجوع", b"section_download")]]
        await event.edit(guide_map[data], buttons=buttons)

    elif data == b"calculator_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        client = user_clients.get(user_id)
        if not client:
            await event.answer("⚠️ يرجى تسجيل الدخول بحسابك أولاً.", alert=True)
            return
        try:
            bot_me = await bot.get_me()
            results = await client.inline_query(bot_me.username, "demon_calculator")
            await results[0].click(event.chat_id)
            await event.answer("✅ أرسلت الآلة الحاسبة في هذه المحادثة.", alert=True)
        except Exception as e:
            await event.answer(f"❌ تعذر إظهار الحاسبة: {e}", alert=True)

    elif data == b"storage_group_menu":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        txt = (
            "📦 **قائمة مجموعة التخزين:**\n\n"
            "هذه الميزة تقوم بإنشاء مجموعة خاصة بك لحفظ وتخزين أي رسالة (منشن أو خاص) تصلك، مع معلومات المرسل والرسالة.\n"
            "اختر ما تود القيام به:"
        )
        await event.edit(txt, buttons=storage_group_menu_keyboard())

    elif data == b"create_storage_group":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        client = user_clients.get(user_id)
        if not client:
            await event.answer("⚠️ يرجى تسجيل الدخول بحسابك (اليوزر بوت) أولاً.", alert=True)
            return
            
        status_msg = await event.edit("⏳ جاري إنشاء مجموعة التخزين الخاصة بك...")
        try:
            # Create a megagroup (supergroup) directly
            result = await client(CreateChannelRequest(
                title="مجموعة التخزين ™",
                about="مجموعة خاصة لتخزين الرسائل والمنشنات تلقائياً.",
                megagroup=True
            ))
            new_chat_id = int(f"-100{result.chats[0].id}")
            
            users_db[user_id].setdefault("storage_groups", []).append(new_chat_id)
            save_data()
            
            # محاولة جلب رابط الدعوة
            try:
                from telethon.tl.functions.messages import ExportChatInviteRequest
                invite = await client(ExportChatInviteRequest(peer=result.chats[0]))
                invite_link = invite.link
            except:
                invite_link = "لا يمكن توليد رابط، يمكنك إيجاد المجموعة في محادثاتك."
                
            await status_msg.edit(
                f"✅ **تم إنشاء مجموعة التخزين بنجاح!**\n\n"
                f"▪️ **اسم المجموعة:** مجموعة التخزين ™\n"
                f"▪️ **الآيدي:** `{new_chat_id}`\n"
                f"🔗 **الرابط:** {invite_link}\n\n"
                f"سيتم تحويل أي منشن أو رسالة خاصة إلى هذه المجموعة تلقائياً.",
                buttons=[[Button.inline("🔙 رجوع", b"storage_group_menu")]]
            )
        except Exception as e:
            await status_msg.edit(f"❌ حدث خطأ أثناء إنشاء المجموعة:\n`{e}`", buttons=[[Button.inline("🔙 رجوع", b"storage_group_menu")]])

    elif data == b"list_storage_groups":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        groups = users_db[user_id].get("storage_groups", [])
        if not groups:
            txt = "📋 لا يوجد لديك أي مجموعات تخزين منشأة حالياً."
        else:
            txt = "📋 **مجموعات التخزين الحالية:**\n\n"
            for idx, gid in enumerate(groups, 1):
                txt += f"**{idx}.** آيدي المجموعة: `{gid}`\n"
            txt += "\n💡 *ملاحظة:* التنبيهات يتم إرسالها لآخر مجموعة تم إنشاؤها."
            
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"storage_group_menu")]])

    elif data == b"del_storage_group_start":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        groups = users_db[user_id].get("storage_groups", [])
        if not groups:
            await event.answer("⚠️ لا توجد مجموعات تخزين لحذفها.", alert=True)
            return
            
        user_states[user_id] = {"step": "awaiting_del_storage_group"}
        txt = "❌ **حذف مجموعة تخزين:**\n\nأرسل آيدي المجموعة التي تود إزالتها من سجل البوت:\n\n"
        for gid in groups:
            txt += f"• `{gid}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"storage_group_menu")]])

    elif data == b"feature_youtube_info":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        txt = (
            "🔍 **فكرة بحث اليوتيوب:**\n\n"
            "يتيح لك السورس البحث عن أي أغنية أو مقطع صوتي في يوتيوب وتحميله وإرساله مباشرة من خلال حسابك الشخصي (اليوزر بوت) كملف صوتي يحتوي على الاسم، اسم القناة، المدة، وصورة الغلاف على اليسار.\n\n"
            "**كيف تستخدمها؟**\n"
            "• اكتب في أي محادثة أو قروب: `بحث [اسم الأغنية أو المطلب]`.\n"
            "• سيقوم الحساب بحذف رسالتك، إرسال رسالة جاري البحث، ثم جلب الملف الصوتي وإرساله فوراً وبدون أي أزرار أو معرفات."
        )
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"feature_pin_info":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        txt = (
            "⤾ اوامـر التـثـبيـت 📌\n"
            "⋆ ——— ‹ ᥙ𝗌𝖾𝗋𝖻᥆𝗍 › ——— ⋆\n\n"
            "• `.تثبيت`\n"
            "↞ بالـرد على الرسالة المراد تثبيتها.\n\n"
            "• `.الغاء التثبيت`\n"
            "↞ لإلغاء تثبيت الرسالة المثبتة، أو بالرد على رسالة مثبتة لإلغائها.\n\n"
            "• الاستخدام 💡\n"
            "↞ اكتب الأوامر بالنقطة فقط. يجب أن يكون حسابك يملك صلاحية تثبيت أو إلغاء تثبيت الرسائل في القروب."
        )
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"enter_code_start":
        user_states[user_id] = {"step": "awaiting_code_input"}
        await event.edit("🎟️ **كود تفعيل التسطير:**\n\nيرجى إرسال كود تفعيل التسطير الآن:", buttons=[[Button.inline("🔙 رجوع", b"main_menu")]])

    elif data == b"enter_all_code_start":
        user_states[user_id] = {"step": "awaiting_all_code_input"}
        await event.edit("✨ **كود تفعيل جميع الصلاحيات:**\n\nأرسل الكود الآن لتفعيل التسطير ومميزات السورس معاً:", buttons=[[Button.inline("🔙 رجوع", b"main_menu")]])

    elif data == b"enter_source_code_start":
        user_states[user_id] = {"step": "awaiting_source_code_input"}
        await event.edit("🎟️ **إدخال كود تفعيل مميزات السورس:**\n\nيرجى إرسال كود تفعيل مميزات السورس الآن:", buttons=[[Button.inline("🔙 رجوع", b"main_menu")]])

    elif data == b"sub_info":
        if is_staff(user_id):
            txt = "📝 **اشتراك التسطير:** مفعل بنمط مسؤول 👑 (غير محدود)\n⭐ **مميزات السورس:** مفعل 👑 (غير محدود)"
        else:
            exp = users_db[user_id]["expires_at"]
            src_exp = users_db[user_id].get("source_expires_at", 0)
            
            sub_txt = f"مفعل ✅ (متبقي {int((exp - time.time()) / 86400)} يوم)" if time.time() < exp else "غير مفعل ❌"
            src_txt = f"مفعل ✅ (متبقي {int((src_exp - time.time()) / 86400)} يوم)" if time.time() < src_exp else "غير مفعل ❌ (تواصل مع المطور لتزويدك بكود تفعيل مميزات السورس)"
            
            txt = f"📝 **اشتراك التسطير:** {sub_txt}\n⭐ **اشتراك مميزات السورس:** {src_txt}"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"main_menu")]])

    elif data == b"login_start":
        if not has_any_subscription(user_id):
            await event.answer("⚠️ فعّل كود التسطير أو كود مميزات السورس أولاً لتتمكن من تسجيل الدخول.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_phone"}
        await event.edit(
            "🔑 **تسجيل الدخول / ربط الحساب:**\n\n"
            "1. أرسل رقم الهاتف كاملاً مع رمز الدولة، مثال: `+966500000000`.\n"
            "2. سيرسل تليجرام رمز التحقق للحساب؛ أرسله هنا في خاص البوت لإكمال الدخول.\n"
            "3. إذا كان الحساب محمياً بالتحقق بخطوتين، سيطلب البوت كلمة المرور هنا لإكمال الدخول.\n\n"
            "🔒 الرمز وكلمة المرور يستخدمان لإتمام الدخول فقط ولا يحفظهما البوت.",
            buttons=[[Button.inline("🔙 رجوع", b"main_menu")]]
        )
    elif data in [b"admin_users_menu", b"admin_admins_menu", b"admin_words_menu", b"admin_codes_menu", b"admin_data_menu"] and is_staff(user_id):
        menu_map = {
            b"admin_users_menu": ("👥 **قسم المستخدمين**", admin_users_keyboard()),
            b"admin_admins_menu": ("👑 **قسم المسؤولين**", admin_admins_keyboard(user_id)),
            b"admin_words_menu": ("📝 **قسم إدارة الكلمات والجمل**", admin_words_keyboard()),
            b"admin_codes_menu": ("🎟️ **قسم أكواد التفعيل**", admin_codes_keyboard()),
            b"admin_data_menu": ("💾 **قسم إدارة بيانات البوت**", admin_data_keyboard(user_id)),
        }
        title, buttons = menu_map[data]
        await event.edit(title, buttons=buttons)

    elif data in [b"manual_activate_start", b"extend_subscription_start"] and is_staff(user_id):
        mode = "extend" if data == b"extend_subscription_start" else "activate"
        user_states[user_id] = {"step": f"awaiting_{mode}_user_id", "mode": mode}
        title = "تمديد" if mode == "extend" else "تفعيل"
        await event.edit(f"➕ **{title} البوت لمستخدم:**\n\nأرسل آيدي المستخدم الرقمي الآن:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data in [b"manual_toggle_tastir", b"manual_toggle_source"] and is_staff(user_id):
        state = user_states.get(user_id, {})
        if state.get("step") != "awaiting_manual_choices":
            await event.answer("⚠️ ابدأ عملية التفعيل أو التمديد أولاً.", alert=True)
            return
        key = "grant_tastir" if data == b"manual_toggle_tastir" else "grant_source"
        state[key] = not state.get(key, False)
        await event.edit("✅ **اختيار نوع الاشتراك:**\n\nحدد الاشتراكات ثم اضغط تأكيد.", buttons=manual_subscription_keyboard(state))

    elif data == b"manual_confirm" and is_staff(user_id):
        state = user_states.get(user_id, {})
        if state.get("step") != "awaiting_manual_choices":
            await event.answer("⚠️ لا توجد عملية تفعيل معلقة.", alert=True)
            return
        if not state.get("grant_tastir") and not state.get("grant_source"):
            await event.answer("⚠️ اختر اشتراكاً واحداً على الأقل.", alert=True)
            return
        target = state["target_uid"]
        days = state["days"]
        init_user_db(target)
        now = time.time()
        if state.get("grant_tastir"):
            users_db[target]["expires_at"] = max(now, users_db[target].get("expires_at", 0)) + days * 86400
        if state.get("grant_source"):
            users_db[target]["source_expires_at"] = max(now, users_db[target].get("source_expires_at", 0)) + days * 86400
        users_db[target].pop("expiry_notices", None)
        _append_activation_log("تمديد" if state.get("mode") == "extend" else "تفعيل_يدوي", target, user_id, days, state.get("grant_tastir"), state.get("grant_source"))
        save_data()
        user_states.pop(user_id, None)
        types = []
        if state.get("grant_tastir"):
            types.append("التسطير")
        if state.get("grant_source"):
            types.append("مميزات السورس")
        try:
            await bot.send_message(target, f"✅ تم تفعيل اشتراكك ({' + '.join(types)}) لمدة {days} يوم.")
        except Exception:
            pass
        await event.edit(f"✅ تم {'تمديد' if state.get('mode') == 'extend' else 'تفعيل'} اشتراك المستخدم `{target}` لمدة {days} يوم: {' + '.join(types)}.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"activation_log_menu" and is_staff(user_id):
        rows = activation_log[-30:][::-1]
        if not rows:
            txt = "📋 **سجل التفعيل:**\n\nلا يوجد سجل حتى الآن."
        else:
            blocks = []
            for idx, row in enumerate(rows, 1):
                when = time.strftime('%Y-%m-%d %H:%M', time.localtime(row.get('time', 0)))
                identity = await format_user_details(row['user_id'])
                issuer_id = row.get('admin_id')
                issuer_text = await _issuer_details_text(issuer_id)
                blocks.append(f"**{idx}.** `{when}`\n{identity}\n• العملية: {row['action']}\n• المدة: `{row.get('days', 0)}` يوم\n👑 **منشئ/منفذ الكود:**\n{issuer_text}")
            txt = "📋 **سجل التفعيل:**\n\n" + "\n\n".join(blocks)
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_data_menu")]])

    elif data in [b"expired_today_menu", b"expired_codes_menu"] and is_staff(user_id):
        cutoff = time.time() - (30 * 86400)
        rows = sorted([row for row in expired_code_history if row.get('time', 0) >= cutoff], key=lambda row: row.get('time', 0), reverse=True)
        if not rows:
            txt = "⌛ **الأكواد المنتهية — آخر 30 يوماً:**\n\nلا توجد أكواد منتهية مسجلة خلال آخر 30 يوماً."
        else:
            blocks = []
            for idx, row in enumerate(rows, 1):
                when = time.strftime('%Y-%m-%d %H:%M', time.localtime(row.get('time', 0)))
                blocks.append(f"**{idx}.** {row.get('name', 'مستخدم')}\n• الآيدي: `{row.get('user_id')}`\n• اليوزر: {row.get('username', 'ماعنده')}\n• الكود المنتهي: {row.get('subscription_type', 'اشتراك')}\n• انتهى: `{when}`")
            txt = "⌛ **الأكواد المنتهية — آخر 30 يوماً:**\n\n" + "\n\n".join(blocks)
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_data_menu")]], link_preview=False)

    elif data == b"voice_menu":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        await event.edit("🎙️ **قائمة التحكم بالصوتيات:**\n\nاختر من القائمة أدناه:", buttons=voice_menu_keyboard(user_id))

    elif data == b"tog_voice_cmd":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        users_db[user_id]["del_voice_cmd"] = not users_db[user_id].get("del_voice_cmd", True)
        save_data()
        await event.edit("🎙️ **قائمة التحكم بالصوتيات:**\n\nاختر من القائمة أدناه:", buttons=voice_menu_keyboard(user_id))

    elif data == b"add_voice":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        next_num = get_next_voice_number(user_id)
        user_states[user_id] = {"step": "awaiting_voice"}
        await event.edit(
            f"➕ **إضافة صوتية جديدة:**\n\n"
            f"الصوتية القادمة ستأخذ رقم تلقائي: `{next_num}`\n\n"
            f"الرجاء إرسال **الملف الصوتي** أو **البصمة** الآن لتخزينها:",
            buttons=[[Button.inline("🔙 رجوع", b"voice_menu")]]
        )

    elif data == b"show_voice":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        v_dict = users_db[user_id].get("voices", {})
        if not v_dict:
            txt = "📂 لا توجد صوتيات مضافة حالياً."
        else:
            txt = "🎙️ **قائمة الصوتيات المسجلة لدي:**\n\n"
            for k in sorted(v_dict.keys(), key=lambda x: int(x) if x.isdigit() else x):
                txt += f"• صوتية رقم `{k}` ⬅️ للاستخدام اكتب: `صوتيه {k}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"voice_menu")]])

    elif data == b"del_voice_item":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        v_dict = users_db[user_id].get("voices", {})
        if not v_dict:
            await event.answer("⚠️ لا توجد صوتيات لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_voice_num"}
        await event.edit("❌ أرسل **رقم الصوتية** التي تريد حذفها (مثال: `1`):", buttons=[[Button.inline("🔙 رجوع", b"voice_menu")]])

    elif data == b"clear_voice":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        v_dict = users_db[user_id].get("voices", {})
        for path in list(v_dict.values()):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        users_db[user_id]["voices"] = {}
        save_data()
        await event.answer("⚠️ تم مسح جميع الصوتيات بنجاح.", alert=True)
        await event.edit("🎙️ **قائمة التحكم بالصوتيات:**", buttons=voice_menu_keyboard(user_id))

    elif data == b"info_purge_quick":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        txt = (
            "ℹ️ **طريقة المسح بالعدد المحدد:**\n\n"
            "يتيح لك هذا الأمر مسح عدد معين من آخر رسائلك في القروب أو المحادثات الخاصة.\n\n"
            "**كيف تستخدمه؟**\n"
            "• اكتب في المحادثة: `مسح 20` وسيقوم البوت بمسح آخر 20 رسالة أرسلتها أنت فقط.\n"
            "• إذا كتبت `مسح` فقط بدون تحديد رقم، سيمسح تلقائياً آخر 20 رسالة لك."
        )
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"info_purge_all":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        txt = (
            "ℹ️ **طريقة المسح الشامل:**\n\n"
            "يتيح لك هذا الأمر مسح كافة الرسائل التي قمت بإرسالها في المجموعات أو الخاصة من بداية المحادثة.\n\n"
            "**كيف تستخدمه؟**\n"
            "• اكتب في المحادثة أو القروب: `مسح الكل` وسيبدأ البوت فوراً بمسح جميع رسائلِك بالكامل."
        )
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"nick_am_menu":
        await event.edit("🏷️ **قائمة نيك ام:**", buttons=nick_am_menu_keyboard(user_id))

    elif data == b"toggle_nick_am":
        enabled = not users_db[user_id].get("nick_am_enabled", False)
        users_db[user_id]["nick_am_enabled"] = enabled
        if not enabled:
            stop_running_task(user_id, mode="nick_am")
        save_data()
        await event.edit("🏷️ **قائمة نيك ام:**", buttons=nick_am_menu_keyboard(user_id))

    elif data == b"toggle_nick_am_reply":
        users_db[user_id]["nick_am_reply_enabled"] = not users_db[user_id].get("nick_am_reply_enabled", True)
        save_data()
        await event.edit("🏷️ **قائمة نيك ام:**", buttons=nick_am_menu_keyboard(user_id))

    elif data == b"add_nick_am":
        user_states[user_id] = {"step": "awaiting_nick_am"}
        await event.edit("➕ أرسل النص المراد إضافته إلى نيك ام:", buttons=[[Button.inline("🔙 رجوع", b"nick_am_menu")]])

    elif data == b"show_nick_am":
        private_phrases = users_db[user_id].get("nick_am", [])
        tastir_phrases = users_db[user_id].get("tastir", []) + default_tastir
        fardiyyat_phrases = users_db[user_id].get("fardiyyat", []) + default_fardiyyat
        include_tastir = users_db[user_id].get("include_tastir_in_nick_am", True)
        include_fardiyyat = users_db[user_id].get("include_fardiyyat_in_nick_am", True)

        sections = []
        if private_phrases:
            sections.append("🏷️ **نصوص نيك ام:**\n" + "\n".join([f"• `{phrase}`" for phrase in private_phrases]))
        if include_tastir and tastir_phrases:
            sections.append("📝 **التسطير المضمن بالنيك ام:**\n" + "\n".join([f"• `{phrase}`" for phrase in tastir_phrases]))
        if include_fardiyyat and fardiyyat_phrases:
            sections.append("🎯 **الفرديات المضمنة بالنيك ام:**\n" + "\n".join([f"• `{phrase}`" for phrase in fardiyyat_phrases]))

        output = "📋 **نصوص نيك ام النشطة حالياً:**\n\n" + ("\n\n".join(sections) if sections else "لا توجد نصوص نيك ام أو مصادر مضمّنة نشطة.")
        await event.edit(output, buttons=[[Button.inline("🔙 رجوع", b"nick_am_menu")]])

    elif data == b"del_nick_am_sub":
        buttons = [
            [Button.inline("🗑️ حذف نص محدد", b"del_nick_am_item_start")],
            [Button.inline("⚠️ حذف شامل (نصوص نيك ام فقط)", b"clear_nick_am")],
            [Button.inline("🔙 رجوع", b"nick_am_menu")],
        ]
        await event.edit("❌ **خيارات حذف نصوص نيك ام:**", buttons=buttons)

    elif data == b"del_nick_am_item_start":
        phrases = users_db[user_id].get("nick_am", [])
        if not phrases:
            await event.answer("⚠️ لا توجد نصوص مضافة لنيك ام لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_nick_am_item"}
        output = "📋 **أرسل النص الذي تريد حذفه من نيك ام:**\n\n" + "\n".join([f"• `{phrase}`" for phrase in phrases])
        await event.edit(output, buttons=[[Button.inline("🔙 رجوع", b"nick_am_menu")]])

    elif data == b"clear_nick_am":
        users_db[user_id]["nick_am"] = []
        save_data()
        await event.answer("⚠️ تم مسح نصوص نيك ام الخاصة فقط.", alert=True)
        await event.edit("🏷️ **قائمة نيك ام:**", buttons=nick_am_menu_keyboard(user_id))

    elif data == b"tog_nick_am_tastir":
        users_db[user_id]["include_tastir_in_nick_am"] = not users_db[user_id].get("include_tastir_in_nick_am", True)
        save_data()
        await event.edit("🏷️ **قائمة نيك ام:**", buttons=nick_am_menu_keyboard(user_id))

    elif data == b"tog_nick_am_fardiyyat":
        users_db[user_id]["include_fardiyyat_in_nick_am"] = not users_db[user_id].get("include_fardiyyat_in_nick_am", True)
        save_data()
        await event.edit("🏷️ **قائمة نيك ام:**", buttons=nick_am_menu_keyboard(user_id))

    elif data == b"tog_nick_am_stop":
        users_db[user_id]["del_nick_am_stop"] = not users_db[user_id].get("del_nick_am_stop", True)
        save_data()
        await event.edit("🏷️ **قائمة نيك ام:**", buttons=nick_am_menu_keyboard(user_id))

    elif data == b"add_nick_am_stop":
        user_states[user_id] = {"step": "awaiting_nick_am_stop"}
        await event.edit("⏹️ أرسل نص أمر إيقاف نيك ام الجديد:", buttons=[[Button.inline("🔙 رجوع", b"nick_am_menu")]])

    elif data == b"show_nick_am_stop":
        commands = users_db[user_id].get("nick_am_stop_cmds", [])
        text_out = "📜 **أوامر إيقاف نيك ام الحالية:**\n\n" + "\n".join([f"• `{command}`" for command in commands])
        await event.edit(text_out, buttons=[[Button.inline("🔙 رجوع", b"nick_am_menu")]])

    elif data == b"clear_nick_am_stop":
        users_db[user_id]["nick_am_stop_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر إيقاف نيك ام.", alert=True)
        await event.edit("🏷️ **قائمة نيك ام:**", buttons=nick_am_menu_keyboard(user_id))

    elif data == b"tastir_ops_menu":
        await event.edit(
            "🛑 **إيقاف عمليات قسم التسطير:**\n\n"
            "هذه القائمة تخص التسطير والفرديات والريبلاي ونيك ام فقط، ولا تؤثر في النشر أو بقية مميزات السورس.",
            buttons=tastir_operations_menu_keyboard(),
        )

    elif data == b"tastir_ops_stop_all":
        stopped_count = stop_tastir_section_tasks(user_id)
        if not stopped_count:
            await event.answer("ليس هناك عمليات شغالة في قسم التسطير.", alert=True)
            return
        await event.edit(
            f"✅ تم إيقاف `{stopped_count}` عملية من عمليات قسم التسطير.",
            buttons=tastir_operations_menu_keyboard(),
        )

    elif data == b"tastir_ops_list":
        operations = get_tastir_section_tasks(user_id)
        if not operations:
            await event.edit(
                "ℹ️ ليس هناك عمليات شغالة في قسم التسطير حالياً.",
                buttons=tastir_operations_menu_keyboard(),
            )
            return
        rows = []
        for index, (task_key, info) in enumerate(operations, 1):
            token = register_tastir_operation_view(user_id, task_key)
            elapsed = format_tastir_elapsed(info.get("started_at"))
            mode_title = tastir_operation_title(info.get("mode"))
            rows.append([Button.inline(f"{index}. {mode_title} — شغالة منذ {elapsed}", f"tastir_op_view_{token}")])
        rows.append([Button.inline("🔙 رجوع", b"tastir_ops_menu")])
        await event.edit("📋 **العمليات الشغالة:**\n\nاختر عملية لعرض مكانها وتفاصيلها وإيقافها:", buttons=rows)

    elif data.startswith(b"tastir_op_view_"):
        token = data.decode().replace("tastir_op_view_", "", 1)
        view = tastir_operation_views.get(token)
        if not view or view.get("owner_id") != user_id:
            await event.answer("انتهت صلاحية هذه القائمة. افتح العمليات مرة أخرى.", alert=True)
            return
        task_key = tuple(view.get("task_key", ()))
        info = running_tasks.get(task_key)
        if not info or info.get("owner_id") != user_id or info.get("mode") not in TASTIR_OPERATION_MODES:
            await event.answer("هذه العملية توقفت بالفعل.", alert=True)
            return
        mode_title = tastir_operation_title(info.get("mode"))
        started_at = info.get("started_at")
        started_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at)) if started_at else "غير متاح"
        location_text = await format_tastir_operation_location(user_id, info)
        extra = ""
        if info.get("mode") == "nick_am":
            extra = f"\n• الاسم المستخدم: `{info.get('nick_prefix', 'غير محدد')}`"
        detail = (
            f"📌 **تفاصيل عملية {mode_title}:**\n\n"
            f"• بدأت في: `{started_text}`\n"
            f"• تعمل منذ: `{format_tastir_elapsed(started_at)}`{extra}\n\n"
            f"{location_text}"
        )
        await event.edit(
            detail,
            buttons=[
                [Button.inline("🛑 إيقاف هذه العملية", f"tastir_op_stop_{token}")],
                [Button.inline("🔙 رجوع إلى العمليات", b"tastir_ops_list")],
            ],
            link_preview=False,
        )

    elif data.startswith(b"tastir_op_stop_"):
        token = data.decode().replace("tastir_op_stop_", "", 1)
        view = tastir_operation_views.get(token)
        if not view or view.get("owner_id") != user_id:
            await event.answer("انتهت صلاحية هذه القائمة. افتح العمليات مرة أخرى.", alert=True)
            return
        task_key = tuple(view.get("task_key", ()))
        info = running_tasks.get(task_key)
        if not info or info.get("owner_id") != user_id or info.get("mode") not in TASTIR_OPERATION_MODES:
            await event.answer("هذه العملية متوقفة بالفعل.", alert=True)
            return
        stop_running_task(user_id, info.get("chat_id"), info.get("target_user_id"), info.get("mode"))
        tastir_operation_views.pop(token, None)
        await event.edit(
            f"✅ تم إيقاف عملية **{tastir_operation_title(info.get('mode'))}** بنجاح.",
            buttons=tastir_operations_menu_keyboard(),
        )

    elif data == b"tastir_menu":
        await event.edit("📝 **قائمة التسطير:**\nيرجى تحديد الخيار المطلوب:", buttons=tastir_menu_keyboard(user_id))

    elif data == b"tog_tastir_start":
        users_db[user_id]["del_tastir_start"] = not users_db[user_id].get("del_tastir_start", True)
        save_data()
        await event.edit("📝 **قائمة التسطير:**", buttons=tastir_menu_keyboard(user_id))

    elif data == b"tog_tastir_stop":
        users_db[user_id]["del_tastir_stop"] = not users_db[user_id].get("del_tastir_stop", True)
        save_data()
        await event.edit("📝 **قائمة التسطير:**", buttons=tastir_menu_keyboard(user_id))

    elif data == b"add_tastir":
        user_states[user_id] = {"step": "awaiting_tastir"}
        await event.edit("➕ أرسل النص المراد إضافته إلى قائمة التسطير (يمكنك إرسال عدة جمل متتالية، وعند الانتهاء اضغط رجوع):", buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif data == b"show_tastir":
        phrases = users_db[user_id]["tastir"]
        txt = "📋 **قائمة جمل التسطير الخاص بك:**\n\n" + ("\n".join([f"• `{p}`" for p in phrases]) if phrases else "لا توجد جمل مضافة.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif data == b"del_tastir_sub":
        buttons = [
            [Button.inline("🗑️ حذف جمل محددة", b"del_tastir_item_start")],
            [Button.inline("⚠️ حذف شامل (جميع الجمل)", b"clear_tastir")],
            [Button.inline("🔙 رجوع", b"tastir_menu")]
        ]
        await event.edit("❌ **خيارات حذف جمل التسطير:**\n\nاختر طريقة الحذف المناسبة:", buttons=buttons)

    elif data == b"del_tastir_item_start":
        phrases = users_db[user_id]["tastir"]
        if not phrases:
            await event.answer("⚠️ لا توجد جمل مضافة لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_tastir_item"}
        txt = "📋 **أرسل الجملة التي تريد حذفها الآن:**\n\n"
        for p in phrases:
            txt += f"• `{p}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif data == b"clear_tastir":
        users_db[user_id]["tastir"] = []
        save_data()
        await event.answer("⚠️ تم مسح جميع جمل التسطير الخاصة بك.", alert=True)
        await event.edit("📝 **قائمة التسطير:**", buttons=tastir_menu_keyboard(user_id))

    elif data == b"add_tastir_start":
        user_states[user_id] = {"step": "awaiting_tastir_start"}
        await event.edit("▶️ أرسل نص أمر تشغيل التسطير الجديد:", buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif data == b"show_tastir_start":
        cmds = users_db[user_id]["tastir_start_cmds"]
        txt = "📜 **أوامر تشغيل التسطير الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif data == b"clear_tastir_start":
        users_db[user_id]["tastir_start_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر تشغيل التسطير.", alert=True)
        await event.edit("📝 **قائمة التسطير:**", buttons=tastir_menu_keyboard(user_id))

    elif data == b"add_tastir_stop":
        user_states[user_id] = {"step": "awaiting_tastir_stop"}
        await event.edit("⏹️ أرسل نص أمر إيقاف التسطير الجديد:", buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif data == b"show_tastir_stop":
        cmds = users_db[user_id]["tastir_stop_cmds"]
        txt = "📜 **أوامر إيقاف التسطير الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif data == b"clear_tastir_stop":
        users_db[user_id]["tastir_stop_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر إيقاف التسطير.", alert=True)
        await event.edit("📝 **قائمة التسطير:**", buttons=tastir_menu_keyboard(user_id))

    elif data == b"fardiyyat_menu":
        await event.edit("🎯 **قائمة الفرديات:**\nيرجى تحديد الخيار المطلوب:", buttons=fardiyyat_menu_keyboard(user_id))

    elif data == b"tog_fardiyyat_start":
        users_db[user_id]["del_fardiyyat_start"] = not users_db[user_id].get("del_fardiyyat_start", True)
        save_data()
        await event.edit("🎯 **قائمة الفرديات:**", buttons=fardiyyat_menu_keyboard(user_id))

    elif data == b"tog_fardiyyat_stop":
        users_db[user_id]["del_fardiyyat_stop"] = not users_db[user_id].get("del_fardiyyat_stop", True)
        save_data()
        await event.edit("🎯 **قائمة الفرديات:**", buttons=fardiyyat_menu_keyboard(user_id))

    elif data == b"add_fardiyyat":
        user_states[user_id] = {"step": "awaiting_fardiyyat"}
        await event.edit("➕ أرسل الكلمة المراد إضافتها إلى الفرديات (يمكنك إرسال عدة كلمات، وعند الانتهاء اضغط رجوع):", buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif data == b"show_fardiyyat":
        phrases = users_db[user_id]["fardiyyat"]
        txt = "📋 **قائمة كلمات الفرديات الخاصة بك:**\n\n" + ("\n".join([f"• `{p}`" for p in phrases]) if phrases else "لا توجد كلمات مضافة.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif data == b"del_fardiyyat_sub":
        buttons = [
            [Button.inline("🗑️ حذف كلمات محددة", b"del_fardiyyat_item_start")],
            [Button.inline("⚠️ حذف شامل (جميع الكلمات)", b"clear_fardiyyat")],
            [Button.inline("🔙 رجوع", b"fardiyyat_menu")]
        ]
        await event.edit("❌ **خيارات حذف كلمات الفرديات:**\n\nاختر طريقة الحذف المناسبة:", buttons=buttons)

    elif data == b"del_fardiyyat_item_start":
        phrases = users_db[user_id]["fardiyyat"]
        if not phrases:
            await event.answer("⚠️ لا توجد كلمات مضافة لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_fardiyyat_item"}
        txt = "📋 **أرسل الكلمة التي تريد حذفها الآن:**\n\n"
        for p in phrases:
            txt += f"• `{p}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif data == b"clear_fardiyyat":
        users_db[user_id]["fardiyyat"] = []
        save_data()
        await event.answer("⚠️ تم مسح جميع كلمات الفرديات الخاصة بك.", alert=True)
        await event.edit("🎯 **قائمة الفرديات:**", buttons=fardiyyat_menu_keyboard(user_id))

    elif data == b"add_fardiyyat_start":
        user_states[user_id] = {"step": "awaiting_fardiyyat_start"}
        await event.edit("▶️ أرسل نص أمر تشغيل الفرديات الجديد:", buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif data == b"show_fardiyyat_start":
        cmds = users_db[user_id]["fardiyyat_start_cmds"]
        txt = "📜 **أوامر تشغيل الفرديات الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif data == b"clear_fardiyyat_start":
        users_db[user_id]["fardiyyat_start_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر تشغيل الفرديات.", alert=True)
        await event.edit("🎯 **قائمة الفرديات:**", buttons=fardiyyat_menu_keyboard(user_id))

    elif data == b"add_fardiyyat_stop":
        user_states[user_id] = {"step": "awaiting_fardiyyat_stop"}
        await event.edit("⏹️ أرسل نص أمر إيقاف الفرديات الجديد:", buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif data == b"show_fardiyyat_stop":
        cmds = users_db[user_id]["fardiyyat_stop_cmds"]
        txt = "📜 **أوامر إيقاف الفرديات الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif data == b"clear_fardiyyat_stop":
        users_db[user_id]["fardiyyat_stop_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر إيقاف الفرديات.", alert=True)
        await event.edit("🎯 **قائمة الفرديات:**", buttons=fardiyyat_menu_keyboard(user_id))

    elif data == b"reply_menu":
        await event.edit("💬 **قائمة الريبلاي:**\nيرجى تحديد الخيار المطلوب:", buttons=reply_menu_keyboard(user_id))

    elif data == b"tog_rep_tastir":
        users_db[user_id]["include_tastir_in_reply"] = not users_db[user_id].get("include_tastir_in_reply", True)
        save_data()
        await event.edit("💬 **قائمة الريبلاي:**", buttons=reply_menu_keyboard(user_id))

    elif data == b"tog_rep_fardiyyat":
        users_db[user_id]["include_fardiyyat_in_reply"] = not users_db[user_id].get("include_fardiyyat_in_reply", True)
        save_data()
        await event.edit("💬 **قائمة الريبلاي:**", buttons=reply_menu_keyboard(user_id))

    elif data == b"tog_reply_start":
        users_db[user_id]["del_reply_start"] = not users_db[user_id].get("del_reply_start", True)
        save_data()
        await event.edit("💬 **قائمة الريبلاي:**", buttons=reply_menu_keyboard(user_id))

    elif data == b"tog_reply_stop":
        users_db[user_id]["del_reply_stop"] = not users_db[user_id].get("del_reply_stop", True)
        save_data()
        await event.edit("💬 **قائمة الريبلاي:**", buttons=reply_menu_keyboard(user_id))

    elif data == b"add_reply":
        user_states[user_id] = {"step": "awaiting_reply"}
        await event.edit("➕ أرسل النص المراد إضافته للرد به تلقائياً (تضاف للريبلاي فقط، ويمكنك إرسال عدة جمل):", buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif data == b"show_reply":
        r_phrases = users_db[user_id].get("reply", [])
        t_phrases = users_db[user_id].get("tastir", []) + default_tastir
        f_phrases = users_db[user_id].get("fardiyyat", []) + default_fardiyyat
        
        inc_t = users_db[user_id].get("include_tastir_in_reply", True)
        inc_f = users_db[user_id].get("include_fardiyyat_in_reply", True)
        
        all_phrases = list(r_phrases + default_reply)
        if inc_t:
            all_phrases += t_phrases
        if inc_f:
            all_phrases += f_phrases
            
        txt = "📋 **قائمة جمل الريبلاي (النشطة حالياً حسب خياراتك):**\n\n" + ("\n".join([f"• `{p}`" for p in all_phrases]) if all_phrases else "لا توجد جمل مضافة أو نشطة.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif data == b"del_reply_sub":
        buttons = [
            [Button.inline("🗑️ حذف جمل محددة (الخاصة بالريبلاي)", b"del_reply_item_start")],
            [Button.inline("⚠️ حذف شامل (جميع جمل الريبلاي الخاصة)", b"clear_reply")],
            [Button.inline("🔙 رجوع", b"reply_menu")]
        ]
        await event.edit("❌ **خيارات حذف جمل الريبلاي:**\n\nاختر طريقة الحذف المناسبة:", buttons=buttons)

    elif data == b"del_reply_item_start":
        phrases = users_db[user_id]["reply"]
        if not phrases:
            await event.answer("⚠️ لا توجد جمل مضافة مخصصة للريبلاي فقط لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_reply_item"}
        txt = "📋 **أرسل الجملة التي تريد حذفها من الريبلاي:**\n\n"
        for p in phrases:
            txt += f"• `{p}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif data == b"clear_reply":
        users_db[user_id]["reply"] = []
        save_data()
        await event.answer("⚠️ تم مسح جميع جمل الريبلاي المخصصة.", alert=True)
        await event.edit("💬 **قائمة الريبلاي:**", buttons=reply_menu_keyboard(user_id))

    elif data == b"add_reply_start":
        user_states[user_id] = {"step": "awaiting_reply_start"}
        await event.edit("▶️ أرسل نص أمر تشغيل الريبلاي الجديد:", buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif data == b"show_reply_start":
        cmds = users_db[user_id]["reply_start_cmds"]
        txt = "📜 **أوامر تشغيل الريبلاي الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif data == b"clear_reply_start":
        users_db[user_id]["reply_start_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر تشغيل الريبلاي.", alert=True)
        await event.edit("💬 **قائمة الريبلاي:**", buttons=reply_menu_keyboard(user_id))

    elif data == b"add_reply_stop":
        user_states[user_id] = {"step": "awaiting_reply_stop"}
        await event.edit("⏹️ أرسل نص أمر إيقاف الريبلاي الجديد:", buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif data == b"show_reply_stop":
        cmds = users_db[user_id]["reply_stop_cmds"]
        txt = "📜 **أوامر إيقاف الريبلاي الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif data == b"clear_reply_stop":
        users_db[user_id]["reply_stop_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر إيقاف الريبلاي.", alert=True)
        await event.edit("💬 **قائمة الريبلاي:**", buttons=reply_menu_keyboard(user_id))

    elif data == b"mute_menu":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        await event.edit("🔇 **قائمة الكتم الشامل:**\nيرجى تحديد الخيار المطلوب:", buttons=mute_menu_keyboard(user_id))

    elif data == b"tog_mute_cmd":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        users_db[user_id]["del_mute_cmd"] = not users_db[user_id].get("del_mute_cmd", True)
        save_data()
        await event.edit("🔇 **قائمة الكتم الشامل:**", buttons=mute_menu_keyboard(user_id))

    elif data == b"tog_unmute_cmd":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        users_db[user_id]["del_unmute_cmd"] = not users_db[user_id].get("del_unmute_cmd", True)
        save_data()
        await event.edit("🔇 **قائمة الكتم الشامل:**", buttons=mute_menu_keyboard(user_id))

    elif data == b"add_mute_cmd":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_mute_cmd"}
        await event.edit("🔇 أرسل نص أمر الكتم الجديد (يمكنك إرسال عدة أوامر، وعند الانتهاء اضغط رجوع):", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"show_mute_cmds":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        cmds = users_db[user_id]["mute_cmds"]
        txt = "📜 **أوامر الكتم الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"del_mute_cmd_sub":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        buttons = [
            [Button.inline("🗑️ حذف أمر كتم محدد", b"del_mute_cmd_item_start")],
            [Button.inline("⚠️ حذف شامل (جميع أوامر الكتم)", b"clear_mute_cmd")],
            [Button.inline("🔙 رجوع", b"mute_menu")]
        ]
        await event.edit("❌ **خيارات حذف أوامر الكتم:**", buttons=buttons)

    elif data == b"del_mute_cmd_item_start":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        cmds = users_db[user_id]["mute_cmds"]
        if not cmds:
            await event.answer("⚠️ لا توجد أوامر كتم لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_mute_cmd_item"}
        txt = "📋 **أرسل أمر الكتم الذي تريد حذفه الآن:**\n\n"
        for c in cmds:
            txt += f"• `{c}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"clear_mute_cmd":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        users_db[user_id]["mute_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر الكتم.", alert=True)
        await event.edit("🔇 **قائمة الكتم:**", buttons=mute_menu_keyboard(user_id))

    elif data == b"add_unmute_cmd":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_unmute_cmd"}
        await event.edit("🔊 أرسل نص أمر إلغاء الكتم الجديد (يمكنك إرسال عدة أوامر، وعند الانتهاء اضغط رجوع):", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"show_unmute_cmds":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        cmds = users_db[user_id]["unmute_cmds"]
        txt = "📜 **أوامر إلغاء الكتم الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"del_unmute_cmd_sub":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        buttons = [
            [Button.inline("🗑️ حذف أمر إلغاء كتم محدد", b"del_unmute_cmd_item_start")],
            [Button.inline("⚠️ حذف شامل (جميع أوامر إلغاء الكتم)", b"clear_unmute_cmd")],
            [Button.inline("🔙 رجوع", b"mute_menu")]
        ]
        await event.edit("❌ **خيارات حذف أوامر إلغاء الكتم:**", buttons=buttons)

    elif data == b"del_unmute_cmd_item_start":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        cmds = users_db[user_id]["unmute_cmds"]
        if not cmds:
            await event.answer("⚠️ لا توجد أوامر إلغاء كتم لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_unmute_cmd_item"}
        txt = "📋 **أرسل أمر إلغاء الكتم الذي تريد حذفه الآن:**\n\n"
        for c in cmds:
            txt += f"• `{c}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"clear_unmute_cmd":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        users_db[user_id]["unmute_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر إلغاء الكتم.", alert=True)
        await event.edit("🔇 **قائمة الكتم:**", buttons=mute_menu_keyboard(user_id))

    elif data == b"show_muted_users":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        m_list = users_db[user_id]["muted_users"]
        txt = "👥 **قائمة المعرفات المكتومة حالياً:**\n\n" + ("\n".join([f"• `{u}`" for u in m_list]) if m_list else "لا يوجد مستخدمون مكتومون.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"del_muted_users_sub":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        buttons = [
            [Button.inline("🗑️ إلغاء كتم مستخدم محدد", b"del_muted_user_item_start")],
            [Button.inline("⚠️ مسح جميع المكتومين", b"clear_muted_users")],
            [Button.inline("🔙 رجوع", b"mute_menu")]
        ]
        await event.edit("❌ **خيارات حذف المكتومين:**", buttons=buttons)

    elif data == b"del_muted_user_item_start":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        m_list = users_db[user_id]["muted_users"]
        if not m_list:
            await event.answer("⚠️ لا يوجد مستخدمون مكتومون.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_muted_user_item"}
        txt = "📋 **أرسل آيدي المستخدم المراد إزالة كتمه الآن:**\n\n"
        for u in m_list:
            txt += f"• `{u}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"clear_muted_users":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        users_db[user_id]["muted_users"] = []
        save_data()
        await event.answer("⚠️ تم مسح جميع المكتومين بنجاح.", alert=True)
        await event.edit("🔇 **قائمة الكتم:**", buttons=mute_menu_keyboard(user_id))

    elif data == b"speed_menu":
        cur_spd = users_db[user_id]["speed"]
        await event.edit(f"⚡ **ضبط السرعة:**\n⏱️ السرعة الحالية: `{cur_spd}` ثانية", buttons=speed_menu_keyboard())

    elif data.startswith(b"spd_"):
        spd_code = data.decode()[4:]
        if spd_code in SPEED_MAP:
            users_db[user_id]["speed"] = SPEED_MAP[spd_code]
            save_data()
            await event.answer(f"✅ تم تحديد السرعة إلى {SPEED_MAP[spd_code]} ثانية.", alert=True)
            cur_spd = users_db[user_id]["speed"]
            await event.edit(f"⚡ **ضبط السرعة:**\n⏱️ السرعة الحالية: `{cur_spd}` ثانية", buttons=speed_menu_keyboard())

    elif data == b"admin_menu":
        if not is_staff(user_id):
            await event.answer("⚠️ هذه القائمة مخصصة للمسؤولين فقط.", alert=True)
            return
        await event.edit("👑 **لوحة تحكم المسؤول:**", buttons=admin_menu_keyboard(user_id))

    elif data == b"admin_tastir_menu" and is_staff(user_id):
        await event.edit("📝 **إدارة التسطير الأساسي (العام):**", buttons=admin_tastir_menu_keyboard())

    elif data == b"add_def_tastir" and is_staff(user_id):
        user_states[user_id] = {"step": "awaiting_add_def_tastir"}
        await event.edit("➕ أرسل الجملة الأساسية للتسطير (لتنضاف تلقائياً للجميع):", buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])

    elif data == b"show_def_tastir" and is_staff(user_id):
        txt = "📋 **قائمة التسطير الأساسية الحالية:**\n\n" + ("\n".join([f"• `{p}`" for p in default_tastir]) if default_tastir else "لا توجد جمل أساسية مضافة.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])

    elif data == b"del_def_tastir_item_start" and is_staff(user_id):
        if not default_tastir:
            await event.answer("⚠️ لا توجد جمل أساسية لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_def_tastir_item"}
        txt = "📋 **أرسل الجملة الأساسية التي تريد حذفها:**\n\n"
        for p in default_tastir:
            txt += f"• `{p}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])

    elif data == b"clear_def_tastir" and is_staff(user_id):
        default_tastir = []
        save_data()
        await event.answer("⚠️ تم مسح جميع جمل التسطير الأساسية.", alert=True)
        await event.edit("📝 **إدارة التسطير الأساسي:**", buttons=admin_tastir_menu_keyboard())

    elif data == b"admin_fardiyyat_menu" and is_staff(user_id):
        await event.edit("🎯 **إدارة الفرديات الأساسية (العامة):**", buttons=admin_fardiyyat_menu_keyboard())

    elif data == b"add_def_fardiyyat" and is_staff(user_id):
        user_states[user_id] = {"step": "awaiting_add_def_fardiyyat"}
        await event.edit("➕ أرسل الكلمة الأساسية للفرديات (لتنضاف تلقائياً للجميع):", buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])

    elif data == b"show_def_fardiyyat" and is_staff(user_id):
        txt = "📋 **قائمة الفرديات الأساسية الحالية:**\n\n" + ("\n".join([f"• `{p}`" for p in default_fardiyyat]) if default_fardiyyat else "لا توجد كلمات أساسية مضافة.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])

    elif data == b"del_def_fardiyyat_item_start" and is_staff(user_id):
        if not default_fardiyyat:
            await event.answer("⚠️ لا توجد كلمات أساسية لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_def_fardiyyat_item"}
        txt = "📋 **أرسل الكلمة الأساسية التي تريد حذفها:**\n\n"
        for p in default_fardiyyat:
            txt += f"• `{p}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])

    elif data == b"clear_def_fardiyyat" and is_staff(user_id):
        default_fardiyyat = []
        save_data()
        await event.answer("⚠️ تم مسح جميع كلمات الفرديات الأساسية.", alert=True)
        await event.edit("🎯 **إدارة الفرديات الأساسية:**", buttons=admin_fardiyyat_menu_keyboard())

    elif data == b"broadcast_start" and is_staff(user_id):
        user_states[user_id] = {"step": "awaiting_broadcast_msg"}
        await event.edit("📢 **الإذاعة العامة:**\n\nأرسل الرسالة المراد إرسالها لجميع المستخدِمين الآن:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"gen_code" and is_staff(user_id):
        user_states[user_id] = {"step": "awaiting_code_days"}
        await event.edit("🎟️ **توليد رمز اشتراك جديد:**\n\nأرسل مدة الاشتراك بالأيام (مثال: `30`):", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"gen_source_code" and is_staff(user_id):
        user_states[user_id] = {"step": "awaiting_source_code_days"}
        await event.edit("🎟️ **توليد كود مميزات السورس جديد:**\n\nأرسل مدة اشتراك مميزات السورس بالأيام (مثال: `30`):", buttons=[[Button.inline("🔙 رجوع", b"admin_codes_menu")]])

    elif data == b"gen_all_code" and is_staff(user_id):
        user_states[user_id] = {"step": "awaiting_all_code_days"}
        await event.edit("✨ **توليد كود جميع الصلاحيات:**\n\nأرسل مدة الاشتراك بالأيام. هذا الكود يفعل التسطير ومميزات السورس معاً:", buttons=[[Button.inline("🔙 رجوع", b"admin_codes_menu")]])

    elif data == b"list_admins" and is_owner(user_id):
        await event.edit("جاري تحميل قائمة الإدارة...")
        sections = ["👑 **قائمة الإدارة:**\n"]
        sections.append("**الريس:**\n" + await format_user_details(OWNER_ID))
        if RESPONSIBLE_IDS:
            responsible_rows = []
            for index, responsible_id in enumerate(RESPONSIBLE_IDS, 1):
                responsible_rows.append(f"**{index}.**\n" + await format_user_details(responsible_id))
            sections.append("⭐ **المسؤولون:**\n" + "\n\n".join(responsible_rows))
        if ADMIN_IDS:
            admin_rows = []
            for index, admin_id in enumerate(ADMIN_IDS, 1):
                if admin_id == OWNER_ID or admin_id in RESPONSIBLE_IDS:
                    continue
                admin_rows.append(f"**{index}.**\n" + await format_user_details(admin_id))
            sections.append("👤 **الأدمنية:**\n" + ("\n\n".join(admin_rows) if admin_rows else "لا يوجد أدمنية مضافون."))
        await event.edit("\n\n".join(sections), buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]], link_preview=False)

    elif data == b"list_users" and is_staff(user_id):
        await event.edit("جاري تنظيف وتحميل قائمة المستخدمين...")
        now = time.time()
        for stale_uid, stale_info in list(users_db.items()):
            if stale_uid not in ADMIN_IDS and now >= stale_info.get("expires_at", 0) and now >= stale_info.get("source_expires_at", 0):
                await remove_user_completely(stale_uid, "تنظيف قائمة المستخدمين")
        if not users_db:
            await event.edit("📋 لا يوجد مستخدمين مسجلين حالياً في النظام.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return

        txt = "📋 **قائمة المستخدمين والمشتركين في النظام:**\n\n"
        all_uids = list(users_db.keys())
        display_uids = all_uids[:30]

        for idx, uid in enumerate(display_uids, 1):
            user_info_str = await format_user_details(uid)
            exp = users_db[uid].get("expires_at", 0)
            src_exp = users_db[uid].get("source_expires_at", 0)
            
            if uid in ADMIN_IDS:
                status_str = "👑 مسؤول (اشتراك مفتوح)"
                src_status_str = "👑 مسؤول (مفتوح)"
            else:
                rem_days = int((exp - time.time()) / 86400) if time.time() < exp else 0
                status_str = f"✅ مفعل (متبقي {rem_days} يوم)" if time.time() < exp else "❌ غير مفعل"
                
                src_rem_days = int((src_exp - time.time()) / 86400) if time.time() < src_exp else 0
                src_status_str = f"✅ مفعل للسورس (متبقي {src_rem_days} يوم)" if time.time() < src_exp else "❌ السورس غير مفعل"

            txt += f"**{idx}.** {user_info_str}\n  • الحالة: {status_str}\n  • السورس: {src_status_str}\n\n"

        if len(all_uids) > 30:
            txt += f"\n⚠️ يتم عرض 30 مستخدم من أصل إجمالي `{len(all_uids)}` مستخدم."

        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]], link_preview=False)

    elif data == b"revoke_user_start" and is_staff(user_id):
        user_states[user_id] = {"step": "awaiting_revoke_user_id"}
        await event.edit("🗑️ **حذف مستخدم نهائياً:**\n\nأرسل المعرف الرقمي (ID) للمستخدم المراد إلغاء اشتراكه وتصفيره:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"add_admin_start" and is_owner(user_id):
        user_states[user_id] = {"step": "awaiting_new_admin_id"}
        await event.edit("➕ **إضافة مسؤول جديد:**\n\nأرسل المعرف الرقمي (ID) لشخص المراد ترقيته:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"delete_admin_start" and is_owner(user_id):
        user_states[user_id] = {"step": "awaiting_delete_admin_id"}
        await event.edit("❌ **حذف مسؤول:**\n\nأرسل المعرف الرقمي (ID) للمسؤول المراد إزالته:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"change_channel_start":
        user_states[user_id] = {"step": "awaiting_channel_url"}
        await event.edit("📢 أرسل رابط قناة البوت الجديد أو يوزرها:", buttons=[[Button.inline("🔙 رجوع", b"admin_data_menu")]])

    elif data == b"manage_developers_menu":
        buttons = []
        rows = []
        for index, item in enumerate(DEVELOPERS[:3], 1):
            label = developer_display_name(item)
            title = "Nardouv" if index == 1 else label
            rows.append(f"• {title}: @{item.get('username', 'غير محدد')}")
            buttons.append([Button.inline(f"✏️ تغيير {title}", f"edit_developer_{index - 1}".encode())])
            if index > 1:
                buttons.append([Button.inline(f"🗑️ حذف {title}", f"delete_developer_{index - 1}".encode())])
        listing = "\n".join(rows) if rows else "لا يوجد مطورون مضافون."
        if len(DEVELOPERS) < 3:
            buttons.append([Button.inline("➕ إضافة مطور", b"add_developer_start")])
        buttons.append([Button.inline("🔙 رجوع", b"admin_data_menu")])
        await event.edit("👨‍💻 **المطورون في القائمة الرئيسية:**\n\n" + listing, buttons=buttons)

    elif data.startswith(b"edit_developer_"):
        if not is_owner(user_id):
            await event.answer("⚠️ تعذر الوصول: هذه الإدارة مخصصة للريس فقط.", alert=True)
            return
        try:
            developer_index = int(data.decode().rsplit("_", 1)[-1])
        except ValueError:
            await event.answer("⚠️ اختيار المطور غير صحيح.", alert=True)
            return
        if developer_index < 0 or developer_index >= len(DEVELOPERS):
            await event.answer("⚠️ المطور غير موجود.", alert=True)
            return
        title = "الريس" if developer_index == 0 else f"المطور {developer_index + 1}"
        user_states[user_id] = {"step": "awaiting_developer_username", "developer_index": developer_index}
        await event.edit(f"👨‍💻 أرسل يوزر {title} الجديد:", buttons=[[Button.inline("🔙 رجوع", b"manage_developers_menu")]])

    elif data.startswith(b"delete_developer_"):
        if not is_owner(user_id):
            await event.answer("⚠️ تعذر الوصول: هذه الإدارة مخصصة للريس فقط.", alert=True)
            return
        try:
            developer_index = int(data.decode().rsplit("_", 1)[-1])
        except ValueError:
            await event.answer("⚠️ اختيار المطور غير صحيح.", alert=True)
            return
        if developer_index <= 0 or developer_index >= len(DEVELOPERS):
            await event.answer("⚠️ لا يمكن حذف الريس أو المطور غير الموجود.", alert=True)
            return
        removed = DEVELOPERS.pop(developer_index)
        save_data(force=True)
        await event.answer(f"✅ تم حذف @{removed.get('username', 'المطور')} من القائمة الرئيسية.", alert=True)
        await event.edit("👨‍💻 **المطورون في القائمة الرئيسية:**", buttons=[[Button.inline("🔙 رجوع", b"manage_developers_menu")]])

    elif data == b"add_developer_start":
        if len(DEVELOPERS) >= 3:
            await event.answer("⚠️ وصلت إلى الحد الأقصى: ثلاثة مطورين.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_developer_username", "developer_index": None}
        await event.edit("👨‍💻 أرسل يوزر المطور الجديد:", buttons=[[Button.inline("🔙 رجوع", b"manage_developers_menu")]])

    elif data == b"list_responsibles":
        rows = []
        for index, responsible_id in enumerate(RESPONSIBLE_IDS, 1):
            rows.append(f"**{index}.**\n" + await format_user_details(responsible_id))
        text_out = "⭐ **قائمة المسؤولين:**\n\n" + ("\n\n".join(rows) if rows else "لا يوجد مسؤولون مرفوعون حالياً.")
        await event.edit(text_out, buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]], link_preview=False)

    elif data == b"delete_responsible_start":
        if not RESPONSIBLE_IDS:
            await event.answer("⚠️ لا يوجد مسؤولون لحذفهم.", alert=True)
            return
        rows = []
        for index, responsible_id in enumerate(RESPONSIBLE_IDS, 1):
            rows.append(f"• {index}. `{responsible_id}`")
        user_states[user_id] = {"step": "awaiting_delete_responsible_id"}
        await event.edit("❌ أرسل آيدي المسؤول الذي تريد حذفه:\n\n" + "\n".join(rows), buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]])

    elif data == b"add_responsible_start":
        user_states[user_id] = {"step": "awaiting_responsible_id"}
        await event.edit("⭐ أرسل آيدي الشخص الذي تريد رفعه مسؤولاً:", buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]])

    elif data == b"backup_export" and (is_owner(user_id) or is_responsible(user_id)):
        try:
            backup_path = create_full_backup()
            await bot.send_file(
                user_id,
                backup_path,
                caption=(
                    "💾 نسخة احتياطية كاملة لبوت ديمون.\n\n"
                    "تشمل: البيانات والاشتراكات والأكواد والإعدادات، جلسات الحسابات، "
                    "الصوتيات والوسائط المحلية المحفوظة.\n"
                    "⚠️ الملف يحتوي جلسات حساسة؛ احتفظ به لنفسك ولا ترسله لأي شخص."
                ),
            )
        except Exception as e:
            await report_admin_error("إنشاء نسخة احتياطية كاملة", e, user_id)
            await event.answer("❌ تعذر إنشاء النسخة الاحتياطية الكاملة.", alert=True)

    elif data == b"backup_import_start" and is_owner(user_id):
        user_states[user_id] = {"step": "awaiting_backup_import"}
        await event.edit(
            "📥 أرسل الآن ملف النسخة الاحتياطية الكاملة بصيغة ZIP.\n\n"
            "ستُستعاد البيانات والجلسات والصوتيات والوسائط المحلية، وسيُحفظ ملف كامل من الوضع الحالي قبل الاستيراد.\n"
            "⚠️ لا تستورد إلا نسخة موثوقة أنشأها بوتك.",
            buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]],
        )

    elif data == b"sessions_menu" and (is_owner(user_id) or is_responsible(user_id)):
        saved_ids = list_saved_session_ids()
        connected_ids = sorted(user_clients.keys())
        async def _session_rows(ids):
            if not ids:
                return "لا توجد حسابات."
            blocks = []
            for idx, uid in enumerate(ids[:40], 1):
                identity = await format_user_details(uid)
                blocks.append(f"**{idx}.**\n{identity}")
            return "\n\n".join(blocks)
        saved_text = await _session_rows(saved_ids)
        connected_text = await _session_rows(connected_ids)
        await event.edit(
            f"📱 **إدارة جلسات الحسابات**\n\n🗃️ **جلسات محفوظة:**\n{saved_text}\n\n🟢 **جلسات متصلة الآن:**\n{connected_text}",
            buttons=[[Button.inline("❌ فصل جلسة مستخدم", b"session_disconnect_start")], [Button.inline("🔙 رجوع", b"admin_data_menu")]],
            link_preview=False
        )

    elif data == b"session_disconnect_start" and is_owner(user_id):
        user_states[user_id] = {"step": "awaiting_disconnect_session_id"}
        await event.edit("❌ أرسل آيدي المستخدم الذي تريد فصل جلسته. لن يتم حذف اشتراكه أو بياناته، لكنه يحتاج لتسجيل الدخول من جديد.", buttons=[[Button.inline("🔙 رجوع", b"sessions_menu")]])

    elif data == b"admin_error_log_menu" and (is_owner(user_id) or is_responsible(user_id)):
        if not admin_error_log:
            await event.edit("✅ لا توجد أخطاء دخول أو تفعيل مسجلة حالياً.", buttons=[[Button.inline("🔙 رجوع", b"admin_data_menu")]])
        else:
            rows = []
            for idx, item in enumerate(admin_error_log[-20:][::-1], 1):
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(item.get("time", 0)))
                rows.append(f"**{idx}.** `{when}`\n• العملية: {item.get('operation')}\n• الاسم: {item.get('name', 'غير محدد')}\n• الآيدي: `{item.get('user_id') or '-'}`\n• اليوزر: {item.get('username', 'ماعنده')}\n• السبب: `{item.get('error')}`")
            await event.edit("⚠️ **سجل أخطاء الدخول والتفعيل:**\n\n" + "\n\n".join(rows), buttons=[[Button.inline("🗑️ مسح سجل الأخطاء", b"admin_error_log_clear")], [Button.inline("🔙 رجوع", b"admin_data_menu")]])

    elif data == b"admin_error_log_clear" and is_owner(user_id):
        admin_error_log.clear()
        save_data()
        await event.answer("✅ تم مسح سجل الأخطاء.", alert=True)
        await event.edit("✅ لا توجد أخطاء دخول أو تفعيل مسجلة حالياً.", buttons=[[Button.inline("🔙 رجوع", b"admin_data_menu")]])

    elif data == b"admin_stats" and is_staff(user_id):
        txt = f"📊 **إحصائيات النظام:**\n\n• إجمالي المسجلين: {len(users_db)}\n• عدد المسؤولين: {len(ADMIN_IDS)}\n• الحسابات المتصلة حالياً: {len(user_clients)}\n• المهام الشغالة حالياً: {len(running_tasks)}"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

# ==================== Inline Menus (via the Manager Bot) ====================
@bot.on(events.InlineQuery)
async def inline_source_menu_handler(event):
    query = (event.text or "").strip()
    if query.startswith("demon_source_menu:") or query.startswith("demon_tastir_menu:"):
        token = query.split(":", 1)[1]
        request = inline_source_requests.pop(token, None)
        # لا نعيد أي نتيجة إذا لم تأتِ من الحساب المرتبط الذي طلب القائمة للتو.
        if not request or request.get("expires_at", 0) < time.time() or request.get("owner_id") != event.sender_id:
            await event.answer([], cache_time=0, private=True)
            return
        if request.get("menu") == "tastir":
            result = event.builder.article(
                title="قسم التسطير — ديمون",
                text=TASTIR_INLINE_MENU_TITLE,
                buttons=tastir_section_keyboard(event.sender_id),
                link_preview=False
            )
        else:
            result = event.builder.article(
                title="مميزات السورس — بوت ديمون",
                text=SOURCE_MENU_TITLE,
                buttons=source_features_menu_keyboard(),
                link_preview=False
            )
        await event.answer([result], cache_time=0, private=True)
    elif query == "demon_calculator":
        result = event.builder.article(
            title="الآلة الحاسبة",
            text="📟 **الآلة الحاسبة**\n\n`0`",
            buttons=calculator_keyboard(),
            link_preview=False
        )
        await event.answer([result], cache_time=0, private=True)


# ==================== Text & Media Input Handlers ====================
@bot.on(events.NewMessage)
async def message_input_handler(event):
    global default_tastir, default_fardiyyat, default_reply, activation_codes, source_activation_codes, all_activation_codes, CHANNEL_URL, DEV_URL
    if not event.is_private or (event.text and event.text.startswith("/")):
        return

    user_id = event.sender_id
    text = event.raw_text.strip() if event.raw_text else ""

    # يعمل في خاص بوت الإدارة أيضاً لإلغاء طلبات النصوص أو الصور أو الأرقام المفتوحة.
    if text in (".الغاء", ".إلغاء"):
        pending_cancelled, stopped_count = await cancel_all_user_operations(user_clients.get(user_id), user_id)
        if pending_cancelled or stopped_count:
            await event.respond(f"✅ تم الإلغاء بنجاح.\n• تم إلغاء حالة إدخال: {'نعم' if pending_cancelled else 'لا'}\n• العمليات المتوقفة: `{stopped_count}`")
        else:
            await event.respond("ℹ️ لا توجد عملية أو حالة إدخال نشطة لإلغائها.")
        return

    # التفعيل الفوري في خاص البوت: لا يحتاج المستخدم للضغط على أي زر.
    # يعالج فقط صيغة أكواد ديمون كي لا يرد على الرسائل العادية.
    if text and re.fullmatch(r"(?:PBL|SRC|ALL)-[A-Za-z0-9_-]+", text, flags=re.IGNORECASE):
        code = text.upper()
        kind, days = await apply_any_activation_code(user_id, code, event)
        if kind:
            result = {
                "tastir": f"✅ تم تفعيل اشتراك التسطير بنجاح لمدة {days} يوم.",
                "source": f"✅ تم تفعيل مميزات السورس بنجاح لمدة {days} يوم.",
                "all": f"✅ تم تفعيل جميع الصلاحيات بنجاح لمدة {days} يوم. تم تفعيل التسطير ومميزات السورس معاً.",
            }[kind]
            await event.respond(result)
        else:
            was_used = any(str(row.get("note", "")).strip() == f"الكود: {code}" for row in activation_log)
            if was_used:
                await event.respond("❌ هذا الكود مستخدم مسبقاً.")
            else:
                await report_admin_error("كود تفعيل غير صالح", "محاولة كود غير صالح في خاص البوت", user_id)
                await event.respond("❌ الكود غير صحيح.")
        return

    state = user_states.get(user_id)
    if not state:
        return

    step = state.get("step")

    if step == "awaiting_channel_url":
        if not is_owner(user_id):
            user_states.pop(user_id, None)
            return
        channel_username = normalize_telegram_username(text)
        if not channel_username:
            await event.respond("⚠️ أرسل رابط قناة صحيحاً أو يوزر قناة صحيحاً.", buttons=[[Button.inline("🔙 رجوع", b"admin_data_menu")]])
            return
        CHANNEL_URL = f"https://t.me/{channel_username}"
        save_data(force=True)
        user_states.pop(user_id, None)
        await event.respond("✅ تم تغيير قناة البوت وتحديث زر القائمة الرئيسية.", buttons=main_menu_keyboard(user_id))
        return

    elif step == "awaiting_developer_username":
        if not is_owner(user_id):
            user_states.pop(user_id, None)
            return
        developer_username = normalize_telegram_username(text)
        if not developer_username:
            await event.respond("⚠️ أرسل يوزر مطور صحيحاً.", buttons=[[Button.inline("🔙 رجوع", b"manage_developers_menu")]])
            return
        developer_index = state.get("developer_index")
        if any(index != developer_index and item.get("username", "").lower() == developer_username.lower() for index, item in enumerate(DEVELOPERS)):
            await event.respond("⚠️ هذا المطور موجود بالفعل.", buttons=[[Button.inline("🔙 رجوع", b"manage_developers_menu")]])
            return
        if developer_index is None:
            if len(DEVELOPERS) >= 3:
                await event.respond("⚠️ وصلت إلى الحد الأقصى: ثلاثة مطورين.", buttons=[[Button.inline("🔙 رجوع", b"manage_developers_menu")]])
                return
            developer_name = await resolve_developer_display_name(developer_username)
            DEVELOPERS.append({"username": developer_username, "display_name": developer_name})
            success_text = f"✅ تم إضافة {developer_name} إلى القائمة الرئيسية."
        else:
            try:
                developer_index = int(developer_index)
            except (TypeError, ValueError):
                developer_index = -1
            if developer_index < 0 or developer_index >= len(DEVELOPERS):
                await event.respond("⚠️ المطور المحدد لم يعد موجوداً.", buttons=[[Button.inline("🔙 رجوع", b"manage_developers_menu")]])
                return
            developer_name = await resolve_developer_display_name(developer_username)
            DEVELOPERS[developer_index] = {"username": developer_username, "display_name": developer_name}
            if developer_index == 0:
                DEV_URL = f"https://t.me/{developer_username}"
                developer_name = "Nardouv"
                DEVELOPERS[developer_index]["display_name"] = developer_name
            success_text = f"✅ تم تغيير {developer_name} في القائمة الرئيسية."
        save_data(force=True)
        user_states.pop(user_id, None)
        await event.respond(success_text, buttons=main_menu_keyboard(user_id))
        return

    elif step == "awaiting_responsible_id":
        if not is_owner(user_id) or not text.isdigit():
            await event.respond("⚠️ أرسل آيدي رقمي صحيح.", buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]])
            return
        responsible_id = int(text)
        if responsible_id == OWNER_ID:
            await event.respond("⚠️ هذا هو الريس بالفعل.", buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]])
            return
        if responsible_id not in RESPONSIBLE_IDS:
            RESPONSIBLE_IDS.append(responsible_id)
            save_data(force=True)
        user_states.pop(user_id, None)
        await event.respond("✅ تم رفع الشخص مسؤولاً كاملاً.", buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]])
        return

    elif step == "awaiting_delete_responsible_id":
        if not is_owner(user_id) or not text.isdigit():
            await event.respond("⚠️ أرسل آيدي المسؤول الرقمي.", buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]])
            return
        responsible_id = int(text)
        if responsible_id not in RESPONSIBLE_IDS:
            await event.respond("⚠️ هذا الآيدي ليس ضمن قائمة المسؤولين.", buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]])
            return
        RESPONSIBLE_IDS.remove(responsible_id)
        save_data(force=True)
        user_states.pop(user_id, None)
        await event.respond("✅ تم حذف المسؤول بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"admin_admins_menu")]])
        return

    if step == "awaiting_backup_import":
        if not is_owner(user_id):
            user_states.pop(user_id, None)
            return
        if not event.document:
            await event.respond("⚠️ أرسل ملف ZIP للنسخة الاحتياطية الكاملة.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        imported_path = None
        restore_copy = None
        try:
            imported_path = await event.download_media(file=TEMP_DIR)
            if not str(imported_path).lower().endswith(".zip"):
                raise ValueError("أرسل ملف ZIP الذي أنشأه زر النسخة الاحتياطية الكاملة.")
            # تبقى نسخة الإدخال خارج مجلد الوسائط لأن الاستيراد يمسح الوسائط القديمة قبل استعادتها.
            restore_copy = os.path.join(BACKUP_DIR, f"restore_input_{secrets.token_urlsafe(8)}.zip")
            shutil.copy2(imported_path, restore_copy)
            current_backup = create_full_backup()
            for session_client in list(user_clients.values()):
                try:
                    await session_client.disconnect()
                except Exception:
                    pass
            user_clients.clear()
            _safe_extract_full_backup(restore_copy)
            load_data()
            _rebase_restored_media_paths()
            save_data(force=True)
            user_states.pop(user_id, None)
            await event.respond(
                "✅ تم استيراد النسخة الاحتياطية الكاملة بنجاح.\n\n"
                "تمت استعادة البيانات والجلسات والوسائط المحلية. أعد تشغيل البوت مرة واحدة لتوصيل كل الجلسات المستعادة.\n"
                f"📦 تم حفظ نسخة كاملة من الوضع السابق في: `{os.path.basename(current_backup)}`",
                buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]],
            )
        except Exception as e:
            await report_admin_error("استيراد نسخة احتياطية كاملة", e, user_id)
            await event.respond(f"❌ تعذر استيراد النسخة: `{e}`", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        finally:
            _safe_remove(imported_path)
            _safe_remove(restore_copy)
        return

    elif step == "awaiting_disconnect_session_id":
        if not is_owner(user_id) or not text.isdigit():
            await event.respond("⚠️ أرسل آيدي رقمي صحيح.", buttons=[[Button.inline("🔙 رجوع", b"sessions_menu")]])
            return
        target_id = int(text)
        await disconnect_user_session_only(target_id)
        user_states.pop(user_id, None)
        await event.respond(f"✅ تم فصل جلسة المستخدم `{target_id}` وإيقاف مهامه، مع بقاء اشتراكه وبياناته.", buttons=[[Button.inline("🔙 رجوع", b"sessions_menu")]])
        return

    elif step == "awaiting_clone_target":
        client = user_clients.get(user_id)
        if not client:
            user_states.pop(user_id, None)
            await event.respond("⚠️ جلسة اليوزر بوت غير متصلة.", buttons=[[Button.inline("🔙 رجوع", b"clone_menu")]])
            return
        try:
            target = await client.get_entity(text)
            if not getattr(target, "first_name", None):
                raise ValueError("الهدف ليس حساب مستخدم.")
            await event.respond("⏳ جاري حفظ بياناتك وتطبيق بيانات المظهر...")
            target_name = await apply_profile_template(client, user_id, target)
            user_states.pop(user_id, None)
            await event.respond(f"✅ تم تطبيق الاسم والبايو والصورة المتاحة لحساب: **{target_name}**.\n↩️ استخدم `.اعاده` لإرجاع النسخة المحفوظة.", buttons=[[Button.inline("🔙 رجوع", b"clone_menu")]])
        except Exception as e:
            await event.respond(f"❌ تعذر تطبيق بيانات المظهر:\n`{e}`", buttons=[[Button.inline("🔙 رجوع", b"clone_menu")]])
        return

    elif step == "awaiting_welcome_text":
        if not is_source_subscribed(user_id):
            return
        users_db[user_id]["welcome_text"] = text
        save_data()
        user_states.pop(user_id, None)
        await event.respond("✅ تم تعيين نص الترحيب بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"welcome_menu")]])
        return

    elif step == "awaiting_welcome_photo":
        if not is_source_subscribed(user_id):
            return
        if not event.photo:
            await event.respond("⚠️ أرسل صورة فقط لتعيينها كصورة ترحيب.", buttons=[[Button.inline("🔙 رجوع", b"welcome_menu")]])
            return
        old_photo = users_db[user_id].get("welcome_photo")
        _safe_remove(old_photo)
        photo_path = os.path.join(TEMP_DIR, f"welcome_{user_id}.jpg")
        await event.download_media(photo_path)
        users_db[user_id]["welcome_photo"] = photo_path
        save_data()
        user_states.pop(user_id, None)
        await event.respond("✅ تم تعيين صورة الترحيب بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"welcome_menu")]])
        return

    elif step == "awaiting_id_lookup":
        client = user_clients.get(user_id)
        if not client:
            user_states.pop(user_id, None)
            await event.respond("⚠️ جلسة اليوزر بوت غير متصلة.", buttons=[[Button.inline("🔙 رجوع", b"id_menu")]])
            return
        try:
            target = await client.get_entity(text)
            name = f"{getattr(target, 'first_name', '') or ''} {getattr(target, 'last_name', '') or ''}".strip() or "بدون اسم"
            username = f"@{target.username}" if getattr(target, "username", None) else "ماعنده"
            user_states.pop(user_id, None)
            await event.respond(f"💳 **بيانات المستخدم:**\n\n• الاسم: {name}\n• الآيدي: `{target.id}`\n• اليوزر: {username}", buttons=[[Button.inline("🔙 رجوع", b"id_menu")]])
        except Exception as e:
            await event.respond(f"❌ لم يتم العثور على المستخدم:\n`{e}`", buttons=[[Button.inline("🔙 رجوع", b"id_menu")]])
        return

    elif step in ["awaiting_convert_image", "awaiting_convert_sticker", "awaiting_convert_audio", "awaiting_convert_voice"]:
        client = user_clients.get(user_id)
        if not client:
            user_states.pop(user_id, None)
            await event.respond("⚠️ جلسة اليوزر بوت غير متصلة.", buttons=[[Button.inline("🔙 رجوع", b"conversion_menu")]])
            return
        try:
            if step == "awaiting_convert_image":
                await convert_to_image(bot, event.message, user_id)
            elif step == "awaiting_convert_sticker":
                await convert_to_sticker(bot, event.message, user_id)
            elif step == "awaiting_convert_audio":
                await extract_audio_from_video(bot, event.message, user_id)
            else:
                await convert_to_voice_note(bot, event.message, user_id)
            user_states.pop(user_id, None)
            await event.respond("✅ تم التحويل بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"conversion_menu")]])
        except Exception as e:
            await event.respond(f"❌ تعذر التحويل:\n`{e}`", buttons=[[Button.inline("🔙 رجوع", b"conversion_menu")]])
        return

    elif step == "awaiting_flush_target":
        client = user_clients.get(user_id)
        if not client:
            user_states.pop(user_id, None)
            await event.respond("⚠️ جلسة اليوزر بوت غير متصلة.", buttons=[[Button.inline("🔙 رجوع", b"flush_menu")]])
            return

        try:
            chat_entity = await client.get_entity(text)
            me = await client.get_me()
            has_ban = await check_user_ban_permissions(client, chat_entity, me)
            
            if not has_ban:
                user_states.pop(user_id, None)
                await event.respond("انت لست مرفوع بصلاحية حظر المستخدمين بالقروب/القناة", buttons=[[Button.inline("🔙 رجوع", b"flush_menu")]])
                return

            user_states[user_id] = {"step": "confirm_flush", "chat_id": chat_entity.id}
            await event.respond(
                "⚠️ **تأكيد التفليش:**\n\n"
                "هل تود بدأ التفليش وطرد جميع الأعضاء؟",
                buttons=[
                    [Button.inline("✅ نعم", f"confirm_flush_action_{chat_entity.id}"), Button.inline("❌ لا", b"cancel_flush")]
                ]
            )
        except Exception as e:
            await event.respond(f"❌ لم يتم العثور على القروب/القناة أو حدث خطأ:\n`{e}`\n\nتأكد من الرابط أو المعرف وأرسله مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"flush_menu")]])
        return

    elif step in ["awaiting_activate_user_id", "awaiting_extend_user_id"] and is_staff(user_id):
        if not text.isdigit():
            await event.respond("⚠️ أرسل آيدي رقمي صحيح للمستخدم:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        target_uid = int(text)
        mode = state.get("mode", "activate")
        user_states[user_id] = {"step": f"awaiting_{mode}_days", "mode": mode, "target_uid": target_uid}
        await event.respond("📅 أرسل عدد أيام الاشتراك:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        return

    elif step in ["awaiting_activate_days", "awaiting_extend_days"] and is_staff(user_id):
        if not text.isdigit() or int(text) <= 0:
            await event.respond("⚠️ أرسل عدد أيام صحيح أكبر من صفر:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        state["step"] = "awaiting_manual_choices"
        state["days"] = int(text)
        state.setdefault("grant_tastir", False)
        state.setdefault("grant_source", False)
        title = "التمديد" if state.get("mode") == "extend" else "التفعيل"
        await event.respond(f"✅ **اختيار اشتراكات {title}:**\n\nالمستخدم: `{state['target_uid']}`\nالمدة: `{state['days']}` يوم\n\nاختر الاشتراكات ثم أكد:", buttons=manual_subscription_keyboard(state))
        return

    elif step == "awaiting_code_days" and is_staff(user_id):
        if not text.isdigit():
            await event.respond("⚠️ يرجى إرسال رقم صحيح يمثل عدد الأيام:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        days = int(text)
        code = "PBL-" + secrets.token_hex(4).upper()
        activation_codes[code] = {"days": days, "created_by": user_id}
        _append_activation_log("توليد_كود_تسطير", user_id, user_id, days, tastir=True, note=f"الكود: {code}")
        save_data()
        user_states.pop(user_id, None)
        await event.respond(f"✅ **تم توليد كود التسطير بنجاح:**\n\n• الكود: `{code}`\n• المدة: `{days}` يوم", buttons=[[Button.inline("🔙 رجوع", b"admin_codes_menu")]])
        return

    elif step == "awaiting_source_code_days" and is_staff(user_id):
        if not text.isdigit() or int(text) <= 0:
            await event.respond("⚠️ يرجى إرسال رقم صحيح يمثل عدد الأيام:", buttons=[[Button.inline("🔙 رجوع", b"admin_codes_menu")]])
            return
        days = int(text)
        code = "SRC-" + secrets.token_hex(4).upper()
        source_activation_codes[code] = {"days": days, "created_by": user_id}
        _append_activation_log("توليد_كود_سورس", user_id, user_id, days, source=True, note=f"الكود: {code}")
        save_data()
        user_states.pop(user_id, None)
        await event.respond(f"✅ **تم توليد كود مميزات السورس بنجاح:**\n\n• الكود: `{code}`\n• المدة: `{days}` يوم", buttons=[[Button.inline("🔙 رجوع", b"admin_codes_menu")]])
        return

    elif step == "awaiting_all_code_days" and is_staff(user_id):
        if not text.isdigit() or int(text) <= 0:
            await event.respond("⚠️ يرجى إرسال رقم صحيح يمثل عدد الأيام:", buttons=[[Button.inline("🔙 رجوع", b"admin_codes_menu")]])
            return
        days = int(text)
        code = "ALL-" + secrets.token_hex(4).upper()
        all_activation_codes[code] = {"days": days, "created_by": user_id}
        _append_activation_log("توليد_كود_جميع_الصلاحيات", user_id, user_id, days, tastir=True, source=True, note=f"الكود: {code}")
        save_data()
        user_states.pop(user_id, None)
        await event.respond(f"✅ **تم توليد كود جميع الصلاحيات بنجاح:**\n\n• الكود: `{code}`\n• المدة: `{days}` يوم\n• التفعيل: التسطير + مميزات السورس", buttons=[[Button.inline("🔙 رجوع", b"admin_codes_menu")]])
        return

    elif step == "awaiting_add_def_tastir" and is_staff(user_id):
        default_tastir.append(text)
        save_data()
        await event.respond("✅ تم إضافة الجملة الأساسية للتسطير بنجاح وتحديثها للجميع.\n\nيمكنك إرسال جملة أخرى أو الضغط على رجوع:", buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])
        return

    elif step == "awaiting_del_def_tastir_item" and is_staff(user_id):
        if text in default_tastir:
            default_tastir.remove(text)
            save_data()
            await event.respond(f"✅ تم حذف الجملة الأساسية: `{text}` بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])
        else:
            await event.respond("❌ الجملة غير موجودة في التسطير الأساسي، تأكد منها ثم أرسلها مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])
        return

    elif step == "awaiting_add_def_fardiyyat" and is_staff(user_id):
        default_fardiyyat.append(text)
        save_data()
        await event.respond("✅ تم إضافة الكلمة الأساسية للفرديات بنجاح وتحديثها للجميع.\n\nيمكنك إرسال كلمة أخرى أو الضغط على رجوع:", buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])
        return

    elif step == "awaiting_del_def_fardiyyat_item" and is_staff(user_id):
        if text in default_fardiyyat:
            default_fardiyyat.remove(text)
            save_data()
            await event.respond(f"✅ تم حذف الكلمة الأساسية: `{text}` بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])
        else:
            await event.respond("❌ الكلمة غير موجودة في الفرديات الأساسية، تأكد منها ثم أرسلها مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])
        return
    elif step == "awaiting_code_input":
        success, days = await apply_activation_code(user_id, text, event)
        user_states.pop(user_id, None)
        if success:
            await event.respond(f"✅ تم تفعيل الاشتراك بنجاح لمدة {days} يوم.")
        else:
            await event.respond("❌ رمز التفعيل غير صالح أو تم استخدامه سابقاً.")

    elif step == "awaiting_source_code_input":
        success, days = await apply_source_activation_code(user_id, text, event)
        user_states.pop(user_id, None)
        if success:
            await event.respond(f"✅ تم تفعيل مميزات السورس بنجاح لمدة {days} يوم.")
        else:
            await report_admin_error("كود سورس غير صالح", "محاولة كود سورس غير صالح أو مستخدم", user_id)
            await event.respond("❌ كود تفعيل مميزات السورس غير صالح أو تم استخدامه سابقاً.")

    elif step == "awaiting_all_code_input":
        success, days = await apply_full_activation_code(user_id, text, event)
        user_states.pop(user_id, None)
        if success:
            await event.respond(f"✅ تم تفعيل كود جميع الصلاحيات بنجاح لمدة {days} يوم. تم تفعيل التسطير ومميزات السورس معاً.")
        else:
            await report_admin_error("كود جميع الصلاحيات غير صالح", "محاولة كود جميع الصلاحيات غير صالح أو مستخدم", user_id)
            await event.respond("❌ كود جميع الصلاحيات غير صالح أو تم استخدامه سابقاً.")

    elif step == "awaiting_broadcast_msg" and is_staff(user_id):
        user_states.pop(user_id, None)
        msg = await event.respond("⏳ جاري إرسال الإذاعة لجميع المستخدمين...")
        success_count = 0
        fail_count = 0
        for uid in users_db.keys():
            try:
                await bot.send_message(uid, f"📢 **إشعار هام من إدارة البوت:**\n\n{text}")
                success_count += 1
                await asyncio.sleep(0.1)
            except Exception:
                fail_count += 1
        total_count = success_count + fail_count
        await msg.edit(
            f"✅ **تم إكمال الإذاعة العامة:**\n\n• تم الإرسال بنجاح: `{success_count}` مستخدماً\n• فشل الإرسال: `{fail_count}` مستخدماً\n• إجمالي من تمت معالجتهم: `{total_count}` مستخدماً",
            buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]]
        )
        return

    elif step == "awaiting_revoke_user_id" and is_staff(user_id):
        user_states.pop(user_id, None)
        if not text.isdigit():
            await event.respond("⚠️ يرجى إرسال معرف رقمي (ID) صحيح:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        target_uid = int(text)
        if target_uid in users_db:
            await remove_user_completely(target_uid, "حذف يدوي من الأدمن")
            await event.respond(f"✅ تم حذف المستخدم `{target_uid}` نهائياً من قائمة المستخدمين وفصل جلسته.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        else:
            await event.respond("❌ المستخدم غير مسجل في قاعدة البيانات.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        return

    elif step == "awaiting_new_admin_id" and is_owner(user_id):
        user_states.pop(user_id, None)
        if not text.isdigit():
            await event.respond("⚠️ يرجى إرسال معرف رقمي (ID) صحيح:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        new_admin_id = int(text)
        if new_admin_id not in ADMIN_IDS:
            ADMIN_IDS.append(new_admin_id)
            init_user_db(new_admin_id)
            users_db[new_admin_id]["expires_at"] = time.time() + (100 * 365 * 86400)
            users_db[new_admin_id]["source_expires_at"] = time.time() + (100 * 365 * 86400)
            save_data()
            await event.respond(f"✅ تم إضافة المستخدم `{new_admin_id}` إلى قائمة المسؤولين بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        else:
            await event.respond("⚠️ المستخدم مسجل كمسؤول مسبقاً.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        return

    elif step == "awaiting_delete_admin_id" and is_owner(user_id):
        user_states.pop(user_id, None)
        if not text.isdigit():
            await event.respond("⚠️ يرجى إرسال معرف رقمي (ID) صحيح:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        del_admin_id = int(text)
        if del_admin_id == 520859814:
            await event.respond("⚠️ لا يمكن إزالة المطور الأساسي من قائمة المسؤولين.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        if del_admin_id in ADMIN_IDS:
            ADMIN_IDS.remove(del_admin_id)
            save_data()
            await event.respond(f"✅ تم إزالة المستخدم `{del_admin_id}` من قائمة المسؤولين بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        else:
            await event.respond("⚠️ المستخدم ليس مسؤولاً في القائمة.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        return

    elif step == "awaiting_phone":
        phone = text.replace(" ", "")
        msg = await event.respond("⏳ جاري إرسال كود التحقق...")
        try:
            client = TelegramClient(f"{SESSIONS_DIR}/user_{user_id}", API_ID, API_HASH, auto_reconnect=True, connection_retries=None, retry_delay=5)
            await client.connect()
            send_code = await client.send_code_request(phone)
            
            user_states[user_id] = {
                "step": "awaiting_code",
                "client": client,
                "phone": phone,
                "phone_code_hash": send_code.phone_code_hash
            }
            await msg.edit(
                "📩 **تم إرسال كود التحقق بنجاح!**\n\n"
                "يرجى إرسال الكود الذي وصلك من تليجرام الآن.\n"
                "💡 *ملاحظة:* إذا واجهت مشكلة، يمكنك إرسال الكود مفصولاً بمسافات (مثال: `1 2 3 4 5`)."
            )
        except Exception as e:
            user_states.pop(user_id, None)
            await report_admin_error("إرسال كود تسجيل الدخول", e, user_id)
            await msg.edit(f"❌ حدث خطأ أثناء إرسال الكود:\n`{e}`\n\nتأكد من كتابة الرقم بشكل صحيح مع رمز الدولة ثم حاول مجدداً.")

    elif step == "awaiting_code":
        code = text.replace(" ", "").replace("-", "")
        client = state.get("client")
        phone = state.get("phone")
        phone_code_hash = state.get("phone_code_hash")

        msg = await event.respond("⏳ جاري التحقق من الكود وتسجيل الدخول...")
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            user_clients[user_id] = client
            await register_userbot_events(client, user_id)
            user_states.pop(user_id, None)
            await msg.edit("✅ **تم تسجيل الدخول وربط حسابك بنجاح!**\nيمكنك الآن استخدام أوامر البوت مباشرة في القروبات والمحادثات.")
        except SessionPasswordNeededError:
            user_states[user_id] = {
                "step": "awaiting_password",
                "client": client
            }
            await msg.edit("🔐 **الحساب محمي بالتحقق بخطوتين (2FA):**\n\nيرجى إرسال كلمة المرور (الباسورد) الخاصة بحسابك الآن:")
        except Exception as e:
            await report_admin_error("تأكيد كود تسجيل الدخول", e, user_id)
            await msg.edit(f"❌ رمز التحقق غير صحيح أو منتهي الصلاحية:\n`{e}`\n\nأعد إرسال الكود الصحيح:")

    elif step == "awaiting_password":
        password = text
        client = state.get("client")
        msg = await event.respond("⏳ جاري التحقق من كلمة المرور...")
        try:
            await client.sign_in(password=password)
            user_clients[user_id] = client
            await register_userbot_events(client, user_id)
            user_states.pop(user_id, None)
            await msg.edit("✅ **تم تسجيل الدخول وربط حسابك بنجاح!**\nيمكنك الآن استخدام أوامر البوت مباشرة في القروبات والمحادثات.")
        except Exception as e:
            await report_admin_error("تأكيد كلمة مرور تسجيل الدخول", e, user_id)
            await msg.edit(f"❌ كلمة المرور غير صحيحة:\n`{e}`\n\nيرجى إرسال كلمة المرور الصحيحة مرة أخرى:")

    elif step == "awaiting_voice":
        if event.voice or event.audio:
            next_num = get_next_voice_number(user_id)
            file_path = os.path.join(VOICES_DIR, f"voice_{user_id}_{next_num}.ogg")
            await event.download_media(file_path)
            users_db[user_id]["voices"][next_num] = file_path
            save_data()
            user_states.pop(user_id, None)
            await event.respond(f"✅ تم حفظ الصوتية بنجاح برقم: `{next_num}`", buttons=[[Button.inline("🔙 رجوع", b"voice_menu")]])

    elif step == "awaiting_del_voice_num":
        if text.isdigit() and text in users_db[user_id].get("voices", {}):
            path = users_db[user_id]["voices"].pop(text)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
            save_data()
            user_states.pop(user_id, None)
            await event.respond(f"✅ تم حذف الصوتية رقم `{text}` بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"voice_menu")]])
        else:
            await event.respond("❌ رقم الصوتية غير صحيح أو غير موجود، تأكد منه ثم أرسله مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"voice_menu")]])

    elif step == "awaiting_tastir":
        users_db[user_id]["tastir"].append(text)
        save_data()
        await event.respond("✅ تم إضافة الجملة إلى التسطير بنجاح (وستتوفر تلقائياً في الريبلاي حسب تفعيلك).\n\nيمكنك إرسال جملة أخرى، أو اضغط زر الرجوع للإنهاء:", buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif step == "awaiting_tastir_start":
        if check_cmd_exists(user_id, text):
            await event.respond("⚠️ هذا الأمر مستخدم بالفعل في مكان آخر.")
        else:
            users_db[user_id]["tastir_start_cmds"].append(text)
            save_data()
            await event.respond("✅ تم إضافة أمر تشغيل التسطير بنجاح.\n\nيمكنك إرسال أمر آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif step == "awaiting_tastir_stop":
        users_db[user_id]["tastir_stop_cmds"].append(text)
        save_data()
        await event.respond("✅ تم إضافة أمر إيقاف التسطير بنجاح.\n\nيمكنك إرسال أمر آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif step == "awaiting_nick_am_stop":
        users_db[user_id]["nick_am_stop_cmds"].append(text)
        save_data()
        await event.respond("✅ تم إضافة أمر إيقاف نيك ام بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"nick_am_menu")]])

    elif step == "awaiting_nick_am":
        users_db[user_id]["nick_am"].append(text)
        save_data()
        await event.respond("✅ تم إضافة النص إلى نيك ام بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"nick_am_menu")]])

    elif step == "awaiting_fardiyyat":
        users_db[user_id]["fardiyyat"].append(text)
        save_data()
        await event.respond("✅ تم إضافة الكلمة إلى الفرديات بنجاح (وستتوفر تلقائياً في الريبلاي حسب تفعيلك).\n\nيمكنك إرسال كلمة أخرى، أو اضغط زر الرجوع للإنهاء:", buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif step == "awaiting_fardiyyat_start":
        if check_cmd_exists(user_id, text):
            await event.respond("⚠️ هذا الأمر مستخدم بالفعل في مكان آخر.")
        else:
            users_db[user_id]["fardiyyat_start_cmds"].append(text)
            save_data()
            await event.respond("✅ تم إضافة أمر تشغيل الفرديات بنجاح.\n\nيمكنك إرسال أمر آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif step == "awaiting_fardiyyat_stop":
        users_db[user_id]["fardiyyat_stop_cmds"].append(text)
        save_data()
        await event.respond("✅ تم إضافة أمر إيقاف الفرديات بنجاح.\n\nيمكنك إرسال أمر آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif step == "awaiting_reply":
        users_db[user_id]["reply"].append(text)
        save_data()
        await event.respond("✅ تم إضافة النص إلى الريبلاي بنجاح (خاص بالريبلاي فقط).\n\nيمكنك إرسال نص آخر لإضافته، أو اضغط زر الرجوع للإنهاء:", buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif step == "awaiting_reply_start":
        if check_cmd_exists(user_id, text):
            await event.respond("⚠️ هذا الأمر مستخدم بالفعل في مكان آخر.")
        else:
            users_db[user_id]["reply_start_cmds"].append(text)
            save_data()
            await event.respond("✅ تم إضافة أمر تشغيل الريبلاي بنجاح.\n\nيمكنك إرسال أمر آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif step == "awaiting_reply_stop":
        users_db[user_id]["reply_stop_cmds"].append(text)
        save_data()
        await event.respond("✅ تم إضافة أمر إيقاف الريبلاي بنجاح.\n\nيمكنك إرسال أمر آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif step == "awaiting_mute_cmd":
        users_db[user_id]["mute_cmds"].append(text)
        save_data()
        await event.respond("✅ تم إضافة أمر الكتم بنجاح.\n\nيمكنك إرسال أمر آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif step == "awaiting_unmute_cmd":
        users_db[user_id]["unmute_cmds"].append(text)
        save_data()
        await event.respond("✅ تم إضافة أمر إلغاء الكتم بنجاح.\n\nيمكنك إرسال أمر آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif step == "awaiting_del_tastir_item":
        if text in users_db[user_id]["tastir"]:
            users_db[user_id]["tastir"].remove(text)
            save_data()
            await event.respond(f"✅ تم حذف الجملة: `{text}` بنجاح.\n\nأرسل جملة أخرى لحذفها، أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])
        else:
            await event.respond("❌ الجملة غير موجودة، تأكد منها ثم أرسلها مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"tastir_menu")]])

    elif step == "awaiting_del_fardiyyat_item":
        if text in users_db[user_id]["fardiyyat"]:
            users_db[user_id]["fardiyyat"].remove(text)
            save_data()
            await event.respond(f"✅ تم حذف الكلمة: `{text}` بنجاح.\n\nأرسل كلمة أخرى لحذفها، أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])
        else:
            await event.respond("❌ الكلمة غير موجودة، تأكد منها ثم أرسلها مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"fardiyyat_menu")]])

    elif step == "awaiting_del_nick_am_item":
        if text in users_db[user_id].get("nick_am", []):
            users_db[user_id]["nick_am"].remove(text)
            save_data()
            await event.respond(f"✅ تم حذف النص: `{text}` بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"nick_am_menu")]])
        else:
            await event.respond("❌ النص غير موجود، تأكد منه ثم أرسله مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"nick_am_menu")]])

    elif step == "awaiting_del_reply_item":
        if text in users_db[user_id]["reply"]:
            users_db[user_id]["reply"].remove(text)
            save_data()
            await event.respond(f"✅ تم حذف الجملة: `{text}` بنجاح.\n\nأرسل جملة أخرى لحذفها، أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])
        else:
            await event.respond("❌ الجملة غير موجودة، تأكد منها ثم أرسلها مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"reply_menu")]])

    elif step == "awaiting_del_mute_cmd_item":
        if text in users_db[user_id]["mute_cmds"]:
            users_db[user_id]["mute_cmds"].remove(text)
            save_data()
            await event.respond(f"✅ تم حذف أمر الكتم: `{text}` بنجاح.\n\nأرسل أمراً آخر لحذفه، أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])
        else:
            await event.respond("❌ الأمر غير موجود، تأكد منه ثم أرسله مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif step == "awaiting_del_unmute_cmd_item":
        if text in users_db[user_id]["unmute_cmds"]:
            users_db[user_id]["unmute_cmds"].remove(text)
            save_data()
            await event.respond(f"✅ تم حذف أمر إلغاء الكتم: `{text}` بنجاح.\n\nأرسل أمراً آخر لحذفه، أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])
        else:
            await event.respond("❌ الأمر غير موجود، تأكد منه ثم أرسله مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif step == "awaiting_publish_required_add":
        try:
            _parse_join_target(text)
            entries = users_db[user_id].setdefault("publish_required_chats", [])
            if text not in entries:
                entries.append(text)
                save_data()
            user_states.pop(user_id, None)
            await event.respond("✅ تم حفظ اشتراك النشر. سيحاول الحساب الانضمام إليه تلقائياً قبل عمليات النشر القادمة.", buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]])
        except ValueError as e:
            await event.respond(f"⚠️ {e}", buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]])

    elif step == "awaiting_publish_required_delete":
        entries = users_db[user_id].setdefault("publish_required_chats", [])
        if text in entries:
            entries.remove(text)
            save_data()
            user_states.pop(user_id, None)
            await event.respond("✅ تم حذف اشتراك النشر من القائمة.", buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]])
        else:
            await event.respond("⚠️ لم أجد هذا الرابط أو اليوزر في القائمة. أرسله كما ظهر في القائمة.", buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]])

    elif step == "awaiting_del_storage_group":
        try:
            gid_to_del = int(text)
            if gid_to_del in users_db[user_id].get("storage_groups", []):
                users_db[user_id]["storage_groups"].remove(gid_to_del)
                save_data()
                await event.respond(f"✅ تم إزالة مجموعة التخزين `{gid_to_del}` من السجل بنجاح.\n\nأرسل آيدي آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"storage_group_menu")]])
            else:
                await event.respond("❌ الآيدي غير موجود في قائمة مجموعات التخزين الخاصة بك:", buttons=[[Button.inline("🔙 رجوع", b"storage_group_menu")]])
        except ValueError:
            await event.respond("⚠️ يرجى إرسال آيدي رقمي صحيح:", buttons=[[Button.inline("🔙 رجوع", b"storage_group_menu")]])

    elif step == "awaiting_del_muted_user_item":
        try:
            uid_to_unmute = int(text)
            if uid_to_unmute in users_db[user_id]["muted_users"]:
                users_db[user_id]["muted_users"].remove(uid_to_unmute)
                save_data()
                await event.respond(f"✅ تم إزالة كتم المستخدم `{uid_to_unmute}` بنجاح.\n\nأرسل آيدي آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])
            else:
                await event.respond("❌ المعرف غير موجود في قائمة المكتومين:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])
        except ValueError:
            await event.respond("⚠️ يرجى إرسال آيدي رقمي صحيح:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

# ==================== Main Bot Startup ====================

async def ask_sarcastic_ai(prompt, owner_id):
    """بحث ودردشة عبر Gemini مع Google Search؛ يعمل خارج حلقة الأحداث حتى لا يجمّد البوت."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"type": "text", "text": "⚠️ لم يتم ضبط مفتاح Gemini للذكاء الاصطناعي."}

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
    payload = {
        "contents": [{
            "parts": [{
                "text": (
                    "أنت مساعد عربي ذكي في بوت تيليجرام. أجب بدقة وبأسلوب لطيف ومختصر، "
                    "واستخدم بحث Google المدمج عند الحاجة للمعلومات الحديثة. "
                    f"سؤال المستخدم: {prompt}"
                )
            }]
        }],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.75, "maxOutputTokens": 1024},
    }

    def _request():
        return requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=22,
        )

    try:
        response = await asyncio.to_thread(_request)
    except requests.RequestException as exc:
        print(f"[GEMINI NETWORK ERROR] {exc}")
        return {"type": "text", "text": "⚠️ تعذر الاتصال بخدمة الذكاء حالياً. حاول مرة أخرى بعد قليل."}

    if response.status_code == 200:
        try:
            candidates = response.json().get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            answer = "".join(str(part.get("text", "")) for part in parts).strip()
            if answer:
                return {"type": "text", "text": answer}
        except Exception as exc:
            print(f"[GEMINI PARSE ERROR] {exc}")
        return {"type": "text", "text": "⚠️ لم يصل رد قابل للقراءة من خدمة الذكاء. حاول صياغة السؤال بشكل مختلف."}

    try:
        api_error = response.json().get("error", {})
        detail = api_error.get("message", "")
    except Exception:
        detail = ""
    print(f"[GEMINI API ERROR] HTTP {response.status_code}: {detail}")

    if response.status_code == 429:
        return {"type": "text", "text": "⚠️ خدمة Gemini وصلت حدّ الاستخدام حالياً. انتظر قليلاً أو راجع حصة الاستخدام والفوترة للمفتاح، ثم أعد المحاولة."}
    if response.status_code in (401, 403):
        return {"type": "text", "text": "⚠️ مفتاح Gemini غير مخول لهذه العملية أو يحتاج تفعيل الصلاحيات."}
    return {"type": "text", "text": "⚠️ تعذر تنفيذ طلب الذكاء الآن. حاول لاحقاً."}
async def send_ai_section_menu(client_inst, owner_id, chat_id):
    """واجهة متوافقة للرسائل القديمة: ترشد إلى أصوات البنات فقط."""
    txt = (
        "🤖 **قسم الذكاء الاصطناعي**\n\n"
        "🎙️ **الأصوات 1 — البنات الواقعية:**\n"
        "استخدم `.بنت 1` إلى `.بنت 7` مع النص أو بالرد على رسالة.\n\n"
        "🧠 استخدم `.تفعيل الذكاء الاصطناعي` ثم `.ذكاء [سؤالك]`."
    )
    await client_inst.send_message(
        chat_id,
        txt,
        buttons=[[Button.inline("🔙 رجوع لقسم الذكاء", b"ai_main_menu")]],
        link_preview=False,
    )

async def send_ai_guide_menu(client_inst, owner_id, chat_id):
    """دليل متوافق مع الواجهة الحالية: ذكاء وأصوات البنات فقط."""
    txt = (
        "⤾ اوامـر الـذكـاء الاصطـناعي والاصـوات 🤖🎙️\n"
        "⋆ ———————————————————— ⋆\n\n"
        "• `.تفعيل الذكاء الاصطناعي`\n↞ لتفعيل الدردشة والبحث الذكي.\n\n"
        "• `.ذكاء [سؤالك]`\n↞ للدردشة والبحث الذكي.\n\n"
        "• `.بنت 1 [النص]` إلى `.بنت 7 [النص]`\n↞ لتحويل النص أو الرسالة المردود عليها إلى فويس أنثوي واقعي."
    )
    await client_inst.send_message(chat_id, txt, buttons=[[Button.inline("🔙 رجوع", data=b"ai_main_menu")]])

# ==================== Girl Voices — Arabic Natural Delivery ====================
# أصوات نسائية متاحة للحساب الحالي؛ تستخدم النموذج متعدد اللغات الأنسب للنطق العربي الطبيعي.
AI_GIRL_VOICE_PROFILES = {
    "بنت 1": {"voice_id": "cgSgspJ2msm6clMCkdW9", "label": "خفيف ودلوع", "stability": 0.34, "similarity": 0.90, "style": 0.22},
    "بنت 2": {"voice_id": "EXAVITQu4vr4xnSDxMaL", "label": "دافئ وحنون", "stability": 0.44, "similarity": 0.88, "style": 0.18},
    "بنت 3": {"voice_id": "FGY2WhTYpPnrIDTdsKH5", "label": "مرح ولطيف", "stability": 0.38, "similarity": 0.84, "style": 0.26},
    "بنت 4": {"voice_id": "Xb7hH8MSUJpSbSDYk0k2", "label": "واضح وهادئ", "stability": 0.55, "similarity": 0.86, "style": 0.12},
    "بنت 5": {"voice_id": "XrExE9yKIg1WjnnlVkGX", "label": "أنثوي مريح", "stability": 0.42, "similarity": 0.87, "style": 0.22},
    "بنت 6": {"voice_id": "hpp4J3VqNfWAUOO0d1Us", "label": "ناعم وثقيل", "stability": 0.40, "similarity": 0.90, "style": 0.20},
    "بنت 7": {"voice_id": "pFZP5JQG7iQjIQuC4Bku", "label": "فخم وهادئ", "stability": 0.52, "similarity": 0.85, "style": 0.14},
}
AI_VOICES_CONFIG_12 = {name: profile["voice_id"] for name, profile in AI_GIRL_VOICE_PROFILES.items()}


async def generate_ai_voice_audio_v2(text, voice_name):
    """ينشئ OGG/Opus مباشراً بصوت أنثوي طبيعي عربي لرسائل Voice Note."""
    try:
        eleven_key = "sk_e62a48b7b0d68a8ad065c5935397dad3ea443634df64f4df"
        profile = AI_GIRL_VOICE_PROFILES.get(voice_name, AI_GIRL_VOICE_PROFILES["بنت 1"])
        raw_text = " ".join(str(text or "").split()).strip()
        if not raw_text:
            return None

        # نترك النص كما كتبه المستخدم؛ إزالة وسوم الأداء الإنجليزية تمنع إفساد النطق العربي.
        response = await asyncio.to_thread(
            requests.post,
            f"https://api.elevenlabs.io/v1/text-to-speech/{profile['voice_id']}",
            params={"output_format": "opus_48000_32"},
            json={
                "text": raw_text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": profile["stability"],
                    "similarity_boost": profile["similarity"],
                    "style": profile["style"],
                    "use_speaker_boost": True,
                },
            },
            headers={
                "Accept": "audio/ogg",
                "Content-Type": "application/json",
                "xi-api-key": eleven_key,
            },
            timeout=35,
        )
        if response.status_code != 200:
            print(f"[ELEVENLABS API ERROR] HTTP {response.status_code}: {response.text[:500]}")
            return None
        if not response.content.startswith(b"OggS"):
            print("[ELEVENLABS AUDIO ERROR] الرد ليس ملف OGG/Opus صالحاً.")
            return None
        output = os.path.join(TEMP_DIR, f"girl_voice_{int(time.time() * 1000)}_{random.randint(100, 999)}.ogg")
        with open(output, "wb") as audio_file:
            audio_file.write(response.content)
        return output
    except Exception as exc:
        print(f"[ELEVENLABS TTS EXCEPTION] {exc}")
        return None

async def send_12_voices_guide(client_inst, owner_id, chat_id, message_id=None):
    """توافق مع أي زر قديم: يعرض دليل أصوات البنات فقط."""
    txt = (
        "🎙️ **الأصوات 1 — أصوات البنات الواقعية**\n\n"
        "• `.بنت 1 [النص]` ↞ ناعم ودلوع.\n"
        "• `.بنت 2 [النص]` ↞ حنون وهادئ.\n"
        "• `.بنت 3 [النص]` ↞ خفيف ومرح.\n"
        "• `.بنت 4 [النص]` ↞ لطيف وواضح.\n"
        "• `.بنت 5 [النص]` ↞ دافئ ومريح.\n"
        "• `.بنت 6 [النص]` ↞ ناعم وثقيل.\n"
        "• `.بنت 7 [النص]` ↞ هادئ وفخم."
    )
    buttons = [[Button.inline("🔙 رجوع لقسم الذكاء", data=b"ai_main_menu")]]
    try:
        if message_id:
            await client_inst.edit_message(chat_id, message_id, txt, buttons=buttons, link_preview=False)
        else:
            await client_inst.send_message(chat_id, txt, buttons=buttons, link_preview=False)
    except Exception:
        await client_inst.send_message(chat_id, txt, buttons=buttons, link_preview=False)

async def main():
    print("Starting bot...")
    await bot.start(bot_token=BOT_TOKEN)
    manager_me = await bot.get_me()
    print(f"Manager Bot: @{manager_me.username or 'بدون_يوزر'} | ID: {manager_me.id}")
    print("لتعمل .الاوامر كأزرار عبر البوت: فعّل Inline Mode لهذا البوت من BotFather عبر /setinline.")
    asyncio.create_task(subscription_maintenance_loop())
    saved_user_rows = list(users_db.items())
    for uid_str, u_data in saved_user_rows:
        uid = int(uid_str)
        session_path = f"{SESSIONS_DIR}/user_{uid}"
        if os.path.exists(f"{session_path}.session"):
            try:
                client = TelegramClient(session_path, API_ID, API_HASH, auto_reconnect=True, connection_retries=None, retry_delay=5)
                await client.connect()
                if await client.is_user_authorized():
                    user_clients[uid] = client
                    await register_userbot_events(client, uid)
                    print(f"Restored userbot session for user {uid}")
                    await restore_auto_publish_jobs(client, uid)
                else:
                    print(f"Session for user {uid} is no longer authorized; login is required once.")
            except Exception as e:
                print(f"Failed to restore userbot session for {uid}: {e}")
    async def user_connection_guard():
        while True:
            for uid, client in list(user_clients.items()):
                try:
                    if not client.is_connected():
                        await client.connect()
                        if await client.is_user_authorized():
                            print(f"Reconnected userbot session for user {uid}")
                except Exception as e:
                    print(f"Reconnect attempt failed for user {uid}: {e}")
            await asyncio.sleep(30)
    asyncio.create_task(user_connection_guard())
    print("Bot is running...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
