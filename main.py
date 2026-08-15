import asyncio
import os
import random
import secrets
import time
import json
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
from telethon.tl.functions.channels import EditBannedRequest, CreateChannelRequest, LeaveChannelRequest
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest, GetUserPhotosRequest
from telethon.tl.types import (
    ChatBannedRights, ChannelParticipantCreator, ChannelParticipantAdmin,
    DocumentAttributeSticker, InputStickerSetEmpty
)

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

# ملف حفظ البيانات ومجلد الصوتيات والجلسات
DATA_FILE = "bot_data.json"
VOICES_DIR = "voices"
SESSIONS_DIR = "sessions"
TEMP_DIR = "temp_media"

if not os.path.exists(VOICES_DIR):
    os.makedirs(VOICES_DIR)
if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

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
activation_log = []
admin_error_log = []
users_db = {}
user_clients = {}
user_states = {}
search_cache = {}

# القوائم الأساسية العامة (تدار عبر لوحة الأدمن وتنعكس للجميع)
default_tastir = []
default_fardiyyat = []
default_reply = []

# المهام النشطة
running_tasks = {}
auto_publish_tasks = {}
broadcast_tasks = {}
calculator_sessions = {}
publish_stop_reasons = {}

# جلسة مستقلة للبوت؛ تمنع استخدام جلسة حساب شخصي قديمة بدل بوت الإدارة.
bot = TelegramClient("manager_bot_8617294862", API_ID, API_HASH)

# ==================== Persistence Functions ====================
def save_data():
    try:
        data = {
            "default_tastir": default_tastir,
            "default_fardiyyat": default_fardiyyat,
            "default_reply": default_reply,
            "users_db": users_db,
            "activation_codes": activation_codes,
            "source_activation_codes": source_activation_codes,
            "activation_log": activation_log[-500:],
            "admin_error_log": admin_error_log[-200:],
            "admin_ids": ADMIN_IDS
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving data: {e}")

def load_data():
    global default_tastir, default_fardiyyat, default_reply, users_db, activation_codes, source_activation_codes, activation_log, admin_error_log, ADMIN_IDS
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
                activation_log = data.get("activation_log", [])
                admin_error_log = data.get("admin_error_log", [])
                loaded_admins = data.get("admin_ids", None)
                if loaded_admins:
                    ADMIN_IDS = [int(a) for a in loaded_admins]
        except Exception as e:
            print(f"Error loading data: {e}")

load_data()

# ==================== Helper Functions ====================
def is_subscribed(user_id):
    if user_id in ADMIN_IDS:
        return True
    user_info = users_db.get(user_id)
    if not user_info:
        return False
    return time.time() < user_info.get("expires_at", 0)

def is_source_subscribed(user_id):
    if user_id in ADMIN_IDS:
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


def _subscription_state(user_id):
    info = users_db.get(user_id, {})
    now = time.time()
    return now < info.get("expires_at", 0), now < info.get("source_expires_at", 0)


# ==================== Admin Backup, Sessions & Error Log ====================
def _backup_file_path(prefix="backup"):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(TEMP_DIR, f"{prefix}_{stamp}.json")


def create_settings_backup():
    """ينشئ نسخة من الإعدادات والاشتراكات والأكواد فقط، دون ملفات جلسات حساسة."""
    save_data()
    output = _backup_file_path("pablo_backup")
    shutil.copy2(DATA_FILE, output)
    return output


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
    """يسجل خطأً منظماً ويبلغ المسؤولين الذين بدأوا البوت."""
    entry = {
        "time": int(time.time()),
        "operation": str(operation),
        "error": str(error)[:1200],
        "user_id": int(user_id) if user_id is not None else None,
        "chat_id": str(chat_id) if chat_id is not None else None,
    }
    admin_error_log.append(entry)
    del admin_error_log[:-200]
    save_data()
    details = f"⚠️ **سجل خطأ جديد**\n\n• العملية: `{entry['operation']}`\n• المستخدم: `{entry['user_id'] or 'غير محدد'}`\n• المحادثة: `{entry['chat_id'] or 'غير محددة'}`\n• السبب: `{entry['error']}`"
    for admin_id in list(ADMIN_IDS):
        try:
            await bot.send_message(admin_id, details)
        except Exception:
            pass



async def remove_user_completely(user_id, reason="حذف"):
    """يحذف المستخدم المنتهي/الملغى من القائمة ويفصل جلسة حسابه ومهامه."""
    if user_id in ADMIN_IDS:
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
    u.setdefault("expires_at", time.time() + (100 * 365 * 86400) if user_id in ADMIN_IDS else 0)
    u.setdefault("source_expires_at", time.time() + (100 * 365 * 86400) if user_id in ADMIN_IDS else 0)
    u.setdefault("tastir", [])
    u.setdefault("fardiyyat", [])
    u.setdefault("reply", [])
    u.pop("bot_responses", None)
    u.setdefault("voices", {})
    u.setdefault("include_tastir_in_reply", True)
    u.setdefault("include_fardiyyat_in_reply", True)
    u.setdefault("tastir_start_cmds", ["تسطير"])
    u.setdefault("tastir_stop_cmds", ["ايقاف التسطير"])
    u.setdefault("fardiyyat_start_cmds", ["فرديات"])
    u.setdefault("fardiyyat_stop_cmds", ["ايقاف الفرديات"])
    u.setdefault("reply_start_cmds", ["ريبلاي"])
    u.setdefault("reply_stop_cmds", ["ايقاف الريبلاي"])
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
    u.setdefault("del_tastir_start", True)
    u.setdefault("del_tastir_stop", True)
    u.setdefault("del_fardiyyat_start", True)
    u.setdefault("del_fardiyyat_stop", True)
    u.setdefault("del_reply_start", True)
    u.setdefault("del_reply_stop", True)
    u.setdefault("del_mute_cmd", True)
    u.setdefault("del_unmute_cmd", True)
    u.setdefault("del_voice_cmd", True)
    u.setdefault("muted_users", [])
    u.setdefault("speed", 1.0)
    u.setdefault("flush_speed", 0.5)
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
    try:
        entity = await bot.get_entity(user_id)
        first_name = entity.first_name or "بدون اسم"
        last_name = f" {entity.last_name}" if entity.last_name else ""
        full_name = f"{first_name}{last_name}".strip()
        username = f"@{entity.username}" if entity.username else "لا يوجد اسم مستخدم"
    except Exception:
        full_name = "مستخدم"
        username = "لا يوجد اسم مستخدم"

    profile_link = f"[{full_name}](tg://openmessage?user_id={user_id})"
    return f"• الاسم: {profile_link}\n  • المعرف: `{user_id}`\n  • اسم المستخدم: {username}"

async def apply_activation_code(user_id, code, event):
    if code in activation_codes:
        days = activation_codes.pop(code)
        init_user_db(user_id)
        current_exp = max(time.time(), users_db[user_id]["expires_at"])
        users_db[user_id]["expires_at"] = current_exp + (days * 86400)
        users_db[user_id].pop("expiry_notices", None)
        _append_activation_log("تفعيل_كود_تسطير", user_id, days=days, tastir=True)
        save_data()
        
        sender = await event.get_sender()
        username = f"@{sender.username}" if sender and sender.username else "لا يوجد اسم مستخدم"
        first_name = sender.first_name if sender and sender.first_name else "مستخدم"
        user_link = f"[{first_name}](tg://openmessage?user_id={user_id})"
        
        notify_txt = (
            "📩 إشعار اشتراك جديد:\n\n"
            f"• المستخدم: {user_link}\n"
            f"• المعرف: `{user_id}`\n"
            f"• اسم المستخدم: {username}\n"
            f"• مدة الاشتراك: {days} يوم\n"
            f"• رمز التفعيل: `{code}`"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, notify_txt)
            except Exception:
                pass
                
        return True, days
    return False, 0

async def apply_source_activation_code(user_id, code, event):
    if code in source_activation_codes:
        days = source_activation_codes.pop(code)
        init_user_db(user_id)
        current_exp = max(time.time(), users_db[user_id].get("source_expires_at", 0))
        users_db[user_id]["source_expires_at"] = current_exp + (days * 86400)
        users_db[user_id].pop("expiry_notices", None)
        _append_activation_log("تفعيل_كود_سورس", user_id, days=days, source=True)
        save_data()
        
        sender = await event.get_sender()
        username = f"@{sender.username}" if sender and sender.username else "لا يوجد اسم مستخدم"
        first_name = sender.first_name if sender and sender.first_name else "مستخدم"
        user_link = f"[{first_name}](tg://openmessage?user_id={user_id})"
        
        notify_txt = (
            "📩 إشعار تفعيل مميزات السورس جديد:\n\n"
            f"• المستخدم: {user_link}\n"
            f"• المعرف: `{user_id}`\n"
            f"• اسم المستخدم: {username}\n"
            f"• مدة الاشتراك: {days} يوم\n"
            f"• رمز تفعيل السورس: `{code}`"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, notify_txt)
            except Exception:
                pass
                
        return True, days
    return False, 0

async def search_and_download_youtube(query):
    def download():
        if query in search_cache:
            video_info = search_cache[query]
            vid = video_info.get('id')
            title = video_info.get('title', 'Audio')
            duration = int(video_info.get('duration', 0))
            uploader = video_info.get('uploader', 'YouTube')
            
            file_path = os.path.join(VOICES_DIR, f"{vid}.mp3")
            if os.path.exists(file_path):
                thumb_path = None
                for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    tp = os.path.join(VOICES_DIR, f"{vid}{ext}")
                    if os.path.exists(tp):
                        thumb_path = tp
                        break
                return file_path, title, duration, uploader, thumb_path

        ydl_opts = {
            'format': 'bestaudio/best',
            'default_search': 'ytsearch1',
            'socket_timeout': 10,
            'quiet': True,
            'no_warnings': True,
            'writethumbnail': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            },
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'outtmpl': os.path.join(VOICES_DIR, '%(id)s.%(ext)s'),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
            if 'entries' in info:
                if not info['entries']:
                    return None, None, None, None, None
                video_info = info['entries'][0]
            else:
                video_info = info
            
            search_cache[query] = video_info
            
            vid = video_info.get('id')
            title = video_info.get('title', 'Audio')
            duration = int(video_info.get('duration', 0))
            uploader = video_info.get('uploader', 'YouTube')
            
            file_path = os.path.join(VOICES_DIR, f"{vid}.mp3")
            if not os.path.exists(file_path):
                for f in os.listdir(VOICES_DIR):
                    if f.startswith(vid) and f.endswith('.mp3'):
                        file_path = os.path.join(VOICES_DIR, f)
                        break
            
            thumb_path = None
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                tp = os.path.join(VOICES_DIR, f"{vid}{ext}")
                if os.path.exists(tp):
                    thumb_path = tp
                    break
                    
            return file_path, title, duration, uploader, thumb_path

    return await asyncio.to_thread(download)

def stop_running_task(owner_id, chat_id=None, target_user_id=None, mode=None):
    keys_to_remove = []
    for key, info in list(running_tasks.items()):
        k_owner, k_chat, k_target, k_mode = key
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

def start_running_task(client, owner_id, chat_id, mode, target_msg_id=None, target_user_id=None):
    # لا نشغّل حلقة فارغة: الجمل يجب أن تكون التي أضافها المستخدم أو الجمل الأساسية التي حفظها الأدمن.
    current_info = users_db.get(owner_id, {})
    if mode == "tastir" and not (current_info.get("tastir", []) or default_tastir):
        return False
    if mode == "fardiyyat" and not (current_info.get("fardiyyat", []) or default_fardiyyat):
        return False

    task_key = (owner_id, chat_id, target_user_id, mode)
    stop_running_task(owner_id, chat_id, target_user_id=target_user_id, mode=mode)

    running_tasks[task_key] = {
        "task": None,
        "owner_id": owner_id,
        "chat_id": chat_id,
        "mode": mode,
        "target_msg_id": target_msg_id,
        "target_user_id": target_user_id
    }

    async def loop():
        try:
            while True:
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
                else:
                    phrases = []

                curr_target_msg_id = task_info.get("target_msg_id")
                target_uid = task_info.get("target_user_id")
                
                if phrases:
                    phrase = random.choice(phrases)
                    sent = False
                    
                    if curr_target_msg_id:
                        try:
                            await client.send_message(chat_id, phrase, reply_to=curr_target_msg_id)
                            sent = True
                        except Exception:
                            if target_uid:
                                try:
                                    async for msg in client.iter_messages(chat_id, from_user=target_uid, limit=1):
                                        task_info["target_msg_id"] = msg.id
                                        curr_target_msg_id = msg.id
                                        await client.send_message(chat_id, phrase, reply_to=curr_target_msg_id)
                                        sent = True
                                        break
                                except Exception:
                                    pass
                    
                    if not sent:
                        final_text = phrase
                        if target_uid and chat_id != target_uid:
                            try:
                                user_entity = await client.get_entity(target_uid)
                                u_name = user_entity.first_name or "مستخدم"
                                mention = f"@{user_entity.username}" if user_entity.username else f"[{u_name}](tg://openmessage?user_id={target_uid})"
                                final_text = f"{phrase} {mention}"
                            except Exception:
                                pass
                        
                        try:
                            await client.send_message(chat_id, final_text)
                            sent = True
                        except Exception:
                            pass
                
                delay = user_info.get("speed", 1.0)
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    print(f"[TASK STARTED] mode={mode} owner={owner_id} chat={chat_id} target={target_user_id}")
    task = asyncio.create_task(loop())
    running_tasks[task_key]["task"] = task
    return True

async def resolve_target_user(event):
    if event.is_private:
        return event.chat_id
    if event.reply_to_msg_id:
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.sender_id:
            return reply_msg.sender_id
    text_parts = event.raw_text.split(maxsplit=1)
    if len(text_parts) > 1:
        arg = text_parts[1].strip()
        try:
            entity = await event.client.get_entity(arg)
            return entity.id
        except Exception:
            pass
    return None

async def check_user_ban_permissions(client, chat_entity, user):
    try:
        participant = await client.get_participant(chat_entity, user)
        if getattr(participant, 'admin_rights', None) and participant.admin_rights.ban_users:
            return True
        if getattr(participant, 'is_creator', False) or isinstance(participant, (ChannelParticipantCreator,)):
            return True
        if hasattr(participant, 'admin') and participant.admin:
            return True
        
        perms = await client.get_permissions(chat_entity, user)
        if getattr(perms, 'ban_users', False) or getattr(perms, 'is_admin', False) or getattr(perms, 'is_creator', False):
            return True
    except Exception:
        pass
    return False

async def run_flush_process(client, chat_id, user_id, status_target):
    u_info = users_db.get(user_id, {})
    speed = u_info.get("flush_speed", 0.5)
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


async def apply_profile_template(client, owner_id, target):
    """يحفظ المظهر الحالي ثم يطبق الاسم والبايو والصورة القابلة للتعديل من الحساب الهدف."""
    init_user_db(owner_id)
    me = await client.get_me()
    full_me = await client(GetFullUserRequest(me))
    old_bio = getattr(full_me.full_user, "about", "") or ""
    old_photo = os.path.join(TEMP_DIR, f"profile_backup_{owner_id}.jpg")
    _safe_remove(old_photo)
    downloaded_old_photo = await client.download_profile_photo(me, file=old_photo)

    users_db[owner_id]["profile_backup"] = {
        "first_name": me.first_name or "",
        "last_name": me.last_name or "",
        "about": old_bio,
        "photo_path": downloaded_old_photo if downloaded_old_photo else None,
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

    me = await client.get_me()
    _add_profile_history(owner_id, me.first_name, me.last_name, me.username)
    save_data()


async def _publish_message(client, target_chat_id, source_message, forward_mode=False):
    """ينشر بتحويل صريح أو بنسخ مخفي المصدر افتراضياً."""
    if forward_mode:
        await client.forward_messages(target_chat_id, source_message)
        return
    from telethon.tl.functions.messages import ForwardMessagesRequest
    target_peer = await client.get_input_entity(target_chat_id)
    await client(ForwardMessagesRequest(
        from_peer=source_message.peer_id,
        id=[source_message.id],
        to_peer=target_peer,
        drop_author=True,
        random_id=[secrets.randbits(63)]
    ))


async def _publish_target_name(client, target_chat_id):
    try:
        entity = await client.get_entity(target_chat_id)
        return getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(target_chat_id)
    except Exception:
        return str(target_chat_id)


async def _send_publish_stop_notice(owner_id, target_name, reason):
    text = f"• تم إيقاف النشر في {target_name}\n• السبب ← {reason}"
    try:
        await bot.send_message(owner_id, text)
    except Exception:
        pass


async def check_publish_permission(client, target_chat_id, owner_id=None):
    """يفحص حق الإرسال قبل إنشاء مهمة النشر، دون إرسال رسالة اختبار للوجهة."""
    try:
        entity = await client.get_entity(target_chat_id)
        name = getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(target_chat_id)
        if getattr(entity, "broadcast", False) and not getattr(entity, "megagroup", False):
            perms = await client.get_permissions(entity, "me")
            if getattr(perms, "is_banned", False) or getattr(perms, "send_messages", None) is False:
                return False, name, "لا تستطيع النشر في هذه القناة؛ أنت محظور أو لا تملك صلاحية الإرسال."
            if not (getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False)):
                return False, name, "لا تستطيع النشر في هذه القناة؛ يجب أن تكون مالكاً أو أدمن بصلاحية النشر."
        else:
            perms = await client.get_permissions(entity, "me")
            if getattr(perms, "is_banned", False) or getattr(perms, "send_messages", None) is False:
                return False, name, "لا تستطيع الإرسال في هذه المجموعة؛ ربما تم تقييدك أو حظرك."
        return True, name, ""
    except Exception as e:
        if owner_id is not None:
            await report_admin_error("فحص صلاحيات النشر", e, owner_id, target_chat_id)
        return False, str(target_chat_id), f"تعذر فحص صلاحية الإرسال: {e}"


async def start_auto_publish_task(client, owner_id, target_chat_id, source_message, delay, count, forward_mode=False):
    task_key = (owner_id, int(target_chat_id))
    old_task = auto_publish_tasks.get(task_key)
    if old_task and not old_task.done():
        await stop_auto_publish_task(client, owner_id, target_chat_id, "تم استبدال عملية النشر بعملية جديدة")

    async def publish_loop():
        completed = 0
        target_name = await _publish_target_name(client, target_chat_id)
        try:
            while completed < count:
                await _publish_message(client, target_chat_id, source_message, forward_mode)
                completed += 1
                if completed < count:
                    await asyncio.sleep(delay)
        except asyncio.CancelledError:
            reason = publish_stop_reasons.pop(task_key, "تم إيقاف النشر يدوياً")
            await _send_publish_stop_notice(owner_id, target_name, reason)
            raise
        except Exception as e:
            await report_admin_error("توقف النشر التلقائي", e, owner_id, target_chat_id)
            await _send_publish_stop_notice(owner_id, target_name, str(e))
        finally:
            auto_publish_tasks.pop(task_key, None)
            publish_stop_reasons.pop(task_key, None)

    task = asyncio.create_task(publish_loop())
    auto_publish_tasks[task_key] = task
    return task_key


async def stop_auto_publish_task(client, owner_id, target_chat_id=None, reason="تم إيقاف النشر يدوياً"):
    stopped = 0
    for key, task in list(auto_publish_tasks.items()):
        task_owner, task_chat = key
        if task_owner == owner_id and (target_chat_id is None or task_chat == int(target_chat_id)):
            if not task.done():
                publish_stop_reasons[key] = reason
                task.cancel()
                stopped += 1
    return stopped


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


SOURCE_MENU_TITLE = "👨🏻‍💻 | **مرحباً بك عزيزي المستخدم**\n💼 | **قائمة أوامر سورس بوت بابلو**\n⚙️ | **اختر ما تريد من الأزرار أسفل**\n\n♡ **source pablo** 🧸"
SOURCE_MENU_FALLBACK = """⚠️ تعذر إرسال قائمة الأزرار المضمّنة.

فعّل Inline Mode لبوت بابلو من @BotFather عبر الأمر `/setinline`، ثم أعد تشغيل البوت وجرب `.الاوامر` مرة أخرى."""


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
        results = await client.inline_query(bot_me.username, f"pablo_source_menu:{token}")
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
            f"⚠️ تعذر إظهار قائمة الأزرار عبر @{bot_name}.\n• السبب ← `{reason}`\n\nفعّل Inline Mode لهذا البوت من @BotFather عبر `/setinline` ثم أعد تشغيل البوت."
        )
        return False


# ==================== Source Features: Self Save, Links & Statistics ====================
async def save_media_to_self_destination(client, owner_id, message):
    init_user_db(owner_id)
    target_chat_id = users_db[owner_id].get("self_save_chat_id") or "me"
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


async def get_user_entity_from_command(client, event, command_parts):
    if event.reply_to_msg_id:
        reply = await event.get_reply_message()
        if reply and reply.sender_id:
            return await client.get_entity(reply.sender_id)
    if len(command_parts) > 1:
        return await client.get_entity(command_parts[1])
    return await client.get_me()


async def build_direct_account_link(entity):
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}"
    return f"tg://openmessage?user_id={entity.id}"


async def get_account_chat_lists(client, mode="all"):
    groups = []
    channels = []
    async for dialog in client.iter_dialogs(limit=None):
        entity = dialog.entity
        if not (getattr(entity, "megagroup", False) or getattr(entity, "broadcast", False)):
            continue

        is_owner = bool(getattr(entity, "creator", False))
        is_admin = is_owner
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

        item = (getattr(entity, "title", "بدون اسم"), entity.id)
        if getattr(entity, "broadcast", False):
            channels.append(item)
        else:
            groups.append(item)
    return groups, channels


async def build_stats_report(client):
    me = await client.get_me()
    groups, channels = await get_account_chat_lists(client, "all")
    return (
        "📊 **إحصائياتي:**\n\n"
        f"• الاسم: {(me.first_name or '')} {(me.last_name or '')}\n"
        f"• الآيدي: `{me.id}`\n"
        f"• اليوزر: @{me.username if me.username else 'ماعنده'}\n"
        f"• عدد القروبات: `{len(groups)}`\n"
        f"• عدد القنوات: `{len(channels)}`\n"
        f"• عمليات النشر الشغالة: `{len(auto_publish_tasks)}`"
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

• .تفعيل الذاتيه
↞ لـ تفعيـل حفـظ الذاتيـه التلقـائي 🏷

• .تعطيل الذاتيه
↞ لـ تعطيـل حفـظ الذاتيـه التلقـائي 🏷

• .تعيين مجموعة الذاتيه
↞ بـ وضـع ايـدي المجموعـة بعد الامـر

• .حذف مجموعة الذاتيه
↞ لـ حـذف مجموعـة الذاتيـة

• .ذاتيه
↞ بالـرد علـى الوسـائـط لحفظـها فـي حـال كانـت غيـر مفعلـه تلقـائيـاً 🧧

↜ ملاحظـه ❤️
• عند تعيين مجموعـة الذاتيـة فانه سـوف يتـم حفـظ الذاتيـة فيها بدلا مـن الرسائل المحفوظه"""

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
↞ لـ تحميل فيديو من اليوتيوب بالرابط 🎗"""

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

• .مقيد او .حفظ
↞ بـ وضـع رابـط الرسالـه مع الامـر
↞ لـ حفظ المحتوى المقيد للقنوات والمجموعات الخاصه🛡"""

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
        "noplaylist": True,
        "format": "bestaudio/best" if audio_only else "best[ext=mp4]/best",
    }
    if audio_only:
        options["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
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
                        pass
            await client.send_message(owner_id, f"✅ انتهت الإذاعة. تم الإرسال إلى `{delivered}` محادثة خاصة.")
        except asyncio.CancelledError:
            try:
                await client.send_message(owner_id, f"⏹️ تم إيقاف الإذاعة بعد الإرسال إلى `{delivered}` محادثة.")
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


async def register_userbot_events(client_inst, owner_id):
    @client_inst.on(events.NewMessage)
    async def userbot_handler(event):
        # تجاهل تام لأي رسالة صادرة من البوت أو مرسلة إليه لمنع التداخل
        if event.chat_id in manager_bot_id or event.sender_id in manager_bot_id:
            return

        chat_id = event.chat_id
        text = event.raw_text.strip() if event.raw_text else ""
        me = await client_inst.get_me()

        if event.sender_id == me.id:
            init_user_db(owner_id)
            user_info = users_db[owner_id]
            
            # إدخالات الأوامر اليدوية التي تبدأ في محادثة معينة تبقى فيها.
            pending_local = user_states.get(owner_id)
            if pending_local and pending_local.get("origin_chat_id") == chat_id:
                pending_step = pending_local.get("step")
                if pending_step == "awaiting_welcome_text_local":
                    if not text:
                        await client_inst.send_message(chat_id, "⚠️ أرسل نص الترحيب أولاً.")
                        return
                    user_info["welcome_text"] = text
                    save_data()
                    user_states.pop(owner_id, None)
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    await client_inst.send_message(chat_id, "✅ تم تعيين نص الترحيب بنجاح.")
                    return

                if pending_step == "awaiting_welcome_photo_local":
                    if not event.photo:
                        await client_inst.send_message(chat_id, "⚠️ أرسل **صورة** فقط لتعيينها كصورة ترحيب.")
                        return
                    old_photo = user_info.get("welcome_photo")
                    _safe_remove(old_photo)
                    photo_path = os.path.join(VOICES_DIR, f"welcome_{owner_id}.jpg")
                    await client_inst.download_media(event.message, file=photo_path)
                    user_info["welcome_photo"] = photo_path
                    save_data()
                    user_states.pop(owner_id, None)
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    await client_inst.send_message(chat_id, "✅ تم تعيين صورة الترحيب بنجاح.")
                    return

            t_start = user_info.get("tastir_start_cmds", [])
            t_stop = user_info.get("tastir_stop_cmds", [])
            f_start = user_info.get("fardiyyat_start_cmds", [])
            f_stop = user_info.get("fardiyyat_stop_cmds", [])
            r_start = user_info.get("reply_start_cmds", [])
            r_stop = user_info.get("reply_stop_cmds", [])
            m_cmds = user_info.get("mute_cmds", [])
            um_cmds = user_info.get("unmute_cmds", [])
            p_cmds = user_info.get("purge_cmds", [])
            p_all_cmds = user_info.get("purge_all_cmds", [])

            # ===== الأوامر القديمة: تعمل بالنقطة أو بدونها =====
            # التسطير والفرديات والريبلاي والكتم من مميزات الحساب القديمة، وليست مميزات سورس.
            legacy_text = text[1:].strip() if text.startswith(".") else text.strip()
            legacy_parts = legacy_text.split()
            legacy_first_word = legacy_parts[0] if legacy_parts else ""
            t_start = normalize_command_list(t_start, [])
            t_stop = normalize_command_list(t_stop, [])
            f_start = normalize_command_list(f_start, [])
            f_stop = normalize_command_list(f_stop, [])
            r_start = normalize_command_list(r_start, [])
            r_stop = normalize_command_list(r_stop, [])
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

            if legacy_text in t_start:
                if user_info.get("del_tastir_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                started = start_running_task(client_inst, owner_id, chat_id, "tastir", legacy_target_msg_id, legacy_target_user_id)
                if not started:
                    await client_inst.send_message(chat_id, "⚠️ لا توجد جمل تسطير محفوظة. أضف جملة أولاً من زر «إضافة جمل التسطير».")
                return

            if legacy_text in f_start:
                if user_info.get("del_fardiyyat_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                started = start_running_task(client_inst, owner_id, chat_id, "fardiyyat", legacy_target_msg_id, legacy_target_user_id)
                if not started:
                    await client_inst.send_message(chat_id, "⚠️ لا توجد كلمات فرديات محفوظة. أضف كلمة أولاً من زر «إضافة كلمات الفرديات».")
                return

            if legacy_text in r_start:
                if user_info.get("del_reply_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                if not legacy_target_user_id or legacy_target_user_id in manager_bot_id:
                    await client_inst.send_message(chat_id, "⚠️ الريبلاي يحتاج الرد على رسالة شخص داخل القروب أو الخاص، ولا يعمل في محادثة بوت الإدارة.")
                    return
                if not (user_info.get("reply", []) or default_reply or user_info.get("tastir", []) or default_tastir or user_info.get("fardiyyat", []) or default_fardiyyat):
                    await client_inst.send_message(chat_id, "⚠️ لا توجد جمل ريبلاي أو تسطير أو فرديات محفوظة لإرسالها.")
                    return
                task_key = (owner_id, chat_id, legacy_target_user_id, "reply")
                running_tasks[task_key] = {"task": None, "owner_id": owner_id, "chat_id": chat_id, "target_user_id": legacy_target_user_id, "mode": "reply", "target_msg_id": legacy_target_msg_id}
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

            # ===== أوامر مميزات السورس الجديدة =====
            if text == "الاوامر":
                if not is_source_subscribed(owner_id):
                    await client_inst.send_message(chat_id, source_lock_message())
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                await send_source_commands_menu(client_inst, owner_id, chat_id)
                return

            if text == "انتحال" or text.startswith("انتحال "):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    target_id = await resolve_target_user(event)
                    if not target_id:
                        await client_inst.send_message(chat_id, "❌ استخدم الأمر بالرد على شخص أو اكتب: `.انتحال @username`")
                        return
                    target = await client_inst.get_entity(target_id)
                    if not getattr(target, "first_name", None):
                        await client_inst.send_message(chat_id, "❌ هذا الهدف ليس حساب مستخدم.")
                        return
                    await event.delete()
                    status = await client_inst.send_message(chat_id, "⏳ جاري تطبيق بيانات المظهر...")
                    target_name = await apply_profile_template(client_inst, owner_id, target)
                    await status.edit(f"✅ تم تطبيق الاسم والبايو والصورة المتاحة لحساب: **{target_name}**\n↩️ اكتب `.اعاده` لإرجاع النسخة المحفوظة.")
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر تطبيق بيانات المظهر:\n`{e}`")
                return

            if text == "اعاده":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                status = await client_inst.send_message(chat_id, "⏳ جاري إعادة بيانات حسابك المحفوظة...")
                try:
                    await restore_profile_template(client_inst, owner_id)
                    await status.edit("✅ تمت إعادة الاسم والبايو والصورة المحفوظة لحسابك.")
                except Exception as e:
                    await status.edit(f"❌ تعذرت الإعادة:\n`{e}`")
                return

            if text == "تفعيل الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                user_info["welcome_enabled"] = True
                save_data()
                await event.delete()
                await client_inst.send_message(chat_id, "✅ تم تفعيل الترحيب الخاص.")
                return

            if text == "تعطيل الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                user_info["welcome_enabled"] = False
                save_data()
                await event.delete()
                await client_inst.send_message(chat_id, "✅ تم تعطيل الترحيب الخاص.")
                return

            if text == "تعيين الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                user_states[owner_id] = {"step": "awaiting_welcome_text_local", "origin_chat_id": chat_id}
                await client_inst.send_message(chat_id, "📝 أرسل نص الترحيب الجديد الآن في **نفس هذه المحادثة**:")
                return

            if text == "تعيين صورة الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                user_states[owner_id] = {"step": "awaiting_welcome_photo_local", "origin_chat_id": chat_id}
                await client_inst.send_message(chat_id, "🖼️ أرسل صورة الترحيب الجديدة الآن في **نفس هذه المحادثة**:")
                return

            if text == "حذف صورة الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                _safe_remove(user_info.get("welcome_photo"))
                user_info["welcome_photo"] = None
                save_data()
                await event.delete()
                await client_inst.send_message(chat_id, "✅ تم حذف صورة الترحيب.")
                return

            if text == "جلب الترحيب":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                current_welcome = user_info.get("welcome_text", "أهلاً بك، نورت الخاص.")
                await client_inst.send_message(chat_id, f"📋 **نص الترحيب الحالي:**\n\n{current_welcome}")
                photo_path = user_info.get("welcome_photo")
                if photo_path and os.path.exists(photo_path):
                    await client_inst.send_file(chat_id, photo_path)
                return

            if text == "تفعيل الردود":
                if not is_source_subscribed(owner_id):
                    return
                user_info["smart_replies_enabled"] = True
                save_data()
                await event.delete()
                await client_inst.send_message(chat_id, "✅ تم تفعيل ردود موجود.")
                return

            if text == "تعطيل الردود":
                if not is_source_subscribed(owner_id):
                    return
                user_info["smart_replies_enabled"] = False
                save_data()
                await event.delete()
                await client_inst.send_message(chat_id, "✅ تم تعطيل ردود موجود.")
                return

            if cmd_first_word in ["نشر", "واو", "ستارت"]:
                if not is_source_subscribed(owner_id):
                    return
                if not event.reply_to_msg_id:
                    await client_inst.send_message(chat_id, "❌ يجب الرد على الرسالة المراد نشرها ثم كتابة الأمر.")
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
                    allowed, target_name, permission_reason = await check_publish_permission(client_inst, target_chat_id, owner_id)
                    if not allowed:
                        await client_inst.send_message(chat_id, f"❌ لم يبدأ النشر في {target_name}.\n• السبب ← {permission_reason}")
                        return
                    if count == 999:
                        count = 10**9
                    reply_message = await event.get_reply_message()
                    await event.delete()
                    await start_auto_publish_task(client_inst, owner_id, target_chat_id, reply_message, delay, count, forward_mode)
                    mode_text = "بتحويل الرسالة" if forward_mode else "بدون تحويل المصدر"
                    await client_inst.send_message(chat_id, f"✅ بدأ النشر في `{target_chat_id}` كل `{delay}` ثانية ({mode_text}).")
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر بدء النشر:\n`{e}`")
                return

            if text == "النشر الشغال":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                jobs = [key for key, task in auto_publish_tasks.items() if key[0] == owner_id and not task.done()]
                await client_inst.send_message(chat_id, "📊 **عمليات النشر الشغالة:**\n\n" + ("\n".join(f"• `{key[1]}`" for key in jobs) if jobs else "لا توجد عمليات نشر."))
                return

            if text == "بس":
                if not is_source_subscribed(owner_id):
                    return
                stopped = await stop_auto_publish_task(client_inst, owner_id, chat_id, "تم إيقاف النشر يدوياً بواسطة صاحب الحساب")
                await event.delete()
                await client_inst.send_message(chat_id, f"✅ تم إيقاف {stopped} عملية نشر في هذا القروب.")
                return

            if text == "ايقاف النشر":
                if not is_source_subscribed(owner_id):
                    return
                stopped = await stop_auto_publish_task(client_inst, owner_id, reason="تم إيقاف جميع عمليات النشر يدوياً بواسطة صاحب الحساب")
                await event.delete()
                await client_inst.send_message(chat_id, f"✅ تم إيقاف {stopped} عملية نشر.")
                return

            if text in ["لصوره", "لملصق", "الصوت", "لبصمه"]:
                if not is_source_subscribed(owner_id):
                    return
                if not event.reply_to_msg_id:
                    await client_inst.send_message(chat_id, "❌ يجب الرد على الوسيط المطلوب تحويله أولاً.")
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
                    await client_inst.send_message(chat_id, f"❌ تعذر التحويل:\n`{e}`")
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
                    target = await client_inst.get_entity(target_id or me.id)
                    full_name = f"{getattr(target, 'first_name', '') or ''} {getattr(target, 'last_name', '') or ''}".strip() or "بدون اسم"
                    username = f"@{target.username}" if getattr(target, "username", None) else "ماعنده"
                    await event.delete()
                    await client_inst.send_message(chat_id, f"💳 **بيانات المستخدم:**\n\n• الاسم: {full_name}\n• الآيدي: `{target.id}`\n• اليوزر: {username}")
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر جلب البيانات:\n`{e}`")
                return

            if text == "بياناتي":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                    report = await get_my_data_report(client_inst, owner_id)
                    await client_inst.send_message(chat_id, report)
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر جلب بياناتك:\n`{e}`")
                return

            if text == "رابط" or text.startswith("رابط "):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    target = await get_user_entity_from_command(client_inst, event, cmd_parts)
                    full_name = f"{getattr(target, 'first_name', '') or ''} {getattr(target, 'last_name', '') or ''}".strip() or "بدون اسم"
                    link = await build_direct_account_link(target)
                    await event.delete()
                    await client_inst.send_message(chat_id, f"🔗 **رابط الحساب:**\n\n• الاسم: {full_name}\n• الآيدي: `{target.id}`\n• الرابط: [اضغط هنا]({link})")
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر جلب رابط الحساب:\n`{e}`")
                return

            if text == "الانشاء" or text.startswith("الانشاء "):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    target = await get_user_entity_from_command(client_inst, event, cmd_parts)
                    full_name = f"{getattr(target, 'first_name', '') or ''} {getattr(target, 'last_name', '') or ''}".strip() or "بدون اسم"
                    estimated = estimated_creation_year(target.id)
                    await event.delete()
                    await client_inst.send_message(chat_id, f"📆 **تاريخ الإنشاء التقديري:**\n\n• الاسم: {full_name}\n• الآيدي: `{target.id}`\n• تقدير الإنشاء: `{estimated}`\n\n⚠️ هذا تقدير مبني على نطاق الآيدي وليس تاريخاً رسمياً من تيليجرام.")
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر كشف تاريخ الإنشاء:\n`{e}`")
                return

            if text == "تفعيل الذاتيه":
                if not is_source_subscribed(owner_id):
                    return
                user_info["self_save_enabled"] = True
                save_data()
                await event.delete()
                await client_inst.send_message(chat_id, "✅ تم تفعيل حفظ الذاتية التلقائي.")
                return

            if text == "تعطيل الذاتيه":
                if not is_source_subscribed(owner_id):
                    return
                user_info["self_save_enabled"] = False
                save_data()
                await event.delete()
                await client_inst.send_message(chat_id, "✅ تم تعطيل حفظ الذاتية التلقائي.")
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
                    await client_inst.send_message(chat_id, f"✅ تم تعيين مجموعة الذاتية: `{target_chat.id}`")
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر تعيين مجموعة الذاتية:\n`{e}`")
                return

            if text == "حذف مجموعة الذاتيه":
                if not is_source_subscribed(owner_id):
                    return
                user_info["self_save_chat_id"] = None
                save_data()
                await event.delete()
                await client_inst.send_message(chat_id, "✅ تم حذف مجموعة الذاتية، وسيتم الحفظ في الرسائل المحفوظة.")
                return

            if text == "ذاتيه":
                if not is_source_subscribed(owner_id):
                    return
                if not event.reply_to_msg_id:
                    await client_inst.send_message(chat_id, "❌ قم بالرد على الوسيط الذي تريد حفظه ثم اكتب `.ذاتيه`.")
                    return
                try:
                    reply_message = await event.get_reply_message()
                    if not reply_message or not reply_message.media:
                        raise ValueError("الرسالة التي تم الرد عليها لا تحتوي على وسيط.")
                    await event.delete()
                    target = await save_media_to_self_destination(client_inst, owner_id, reply_message)
                    await client_inst.send_message(chat_id, f"✅ تم حفظ الوسيط في `{target}`.")
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر حفظ الوسيط:\n`{e}`")
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
                    await client_inst.send_message(chat_id, output)
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر جلب القائمة:\n`{e}`")
                return

            if text == "احصائياتي":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                    await client_inst.send_message(chat_id, await build_stats_report(client_inst))
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر جلب الإحصائيات:\n`{e}`")
                return

            # ===== أوامر البحث والتحميل =====
            if text == "ح":
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                try:
                    bot_me = await bot.get_me()
                    results = await client_inst.inline_query(bot_me.username, "pablo_calculator")
                    await results[0].click(chat_id)
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر عرض الآلة الحاسبة:\n`{e}`")
                return

            if text.startswith("يوت "):
                if not is_source_subscribed(owner_id):
                    return
                query = text[4:].strip()
                if not query:
                    return
                await event.delete()
                status = await client_inst.send_message(chat_id, "⏳ جاري البحث وتحميل الصوت...")
                try:
                    search_url = f"ytsearch1:{query}"
                    media_path, info = await _ytdlp_download(search_url, audio_only=True)
                    try:
                        await client_inst.send_file(chat_id, media_path, caption=(info.get("title") or query)[:900])
                    finally:
                        _safe_remove(media_path)
                    await status.delete()
                except Exception as e:
                    await status.edit(f"❌ تعذر تحميل الصوت:\n`{e}`")
                return

            if text.startswith("تحميل "):
                if not is_source_subscribed(owner_id):
                    return
                url = text[6:].strip()
                if not url:
                    return
                await event.delete()
                status = await client_inst.send_message(chat_id, "⏳ جاري التحميل...")
                try:
                    await download_and_send_url(client_inst, chat_id, url, audio_only=False)
                    await status.delete()
                except Exception as e:
                    await report_admin_error("تحميل رابط", e, owner_id, chat_id)
                    await status.edit(f"❌ تعذر التحميل:\n`{e}`")
                return

            if text.startswith("بنترست "):
                if not is_source_subscribed(owner_id):
                    return
                url = text[8:].strip()
                await event.delete()
                status = await client_inst.send_message(chat_id, "⏳ جاري تحميل محتوى بنترست...")
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
                status = await client_inst.send_message(chat_id, "⏳ جاري تحميل الستوري...")
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
                status = await client_inst.send_message(chat_id, "⏳ جاري تحميل المستودع...")
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
                status = await client_inst.send_message(chat_id, "⏳ جاري حفظ المحتوى...")
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
                    await client_inst.send_message(chat_id, "❌ اكتب النص بعد الأمر: `.اكتب النص`")
                    return
                await event.delete()
                try:
                    await make_handwriting_image(client_inst, chat_id, value)
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر إنشاء الكتابة:\n`{e}`")
                return

            if text == "نسخ" or text.startswith("نسخ ") or text == "غامق" or text.startswith("غامق ") or text == "مائل" or text.startswith("مائل "):
                if not is_source_subscribed(owner_id):
                    return
                command = cmd_first_word
                value = await get_command_text(event, text, command)
                if not value:
                    await client_inst.send_message(chat_id, "❌ اكتب النص بعد الأمر أو رد على رسالة نصية.")
                    return
                await event.delete()
                if command == "نسخ":
                    await client_inst.send_message(chat_id, f"`{value}`")
                elif command == "غامق":
                    await client_inst.send_message(chat_id, f"**{value}**")
                else:
                    await client_inst.send_message(chat_id, f"__{value}__")
                return

            # ===== الإذاعة والتنظيف =====
            if text == "اذاعه" or text.startswith("اذاعه "):
                if not is_source_subscribed(owner_id):
                    return
                if not event.reply_to_msg_id:
                    await client_inst.send_message(chat_id, "❌ قم بالرد على الرسالة المراد إذاعتها أولاً.")
                    return
                try:
                    parts = text.split()
                    limit = int(parts[1]) if len(parts) > 1 else 10**9
                    if limit < 1:
                        raise ValueError("العدد يجب أن يكون أكبر من صفر.")
                    reply_message = await event.get_reply_message()
                    await event.delete()
                    await start_broadcast_task(client_inst, owner_id, reply_message, limit)
                    await client_inst.send_message(chat_id, f"✅ بدأت الإذاعة إلى حد أقصى `{limit if limit < 10**9 else 'كل الخاص'}` محادثة.")
                except Exception as e:
                    await client_inst.send_message(chat_id, f"❌ تعذر بدء الإذاعة:\n`{e}`")
                return

            if text == "ايقاف الاذاعه":
                task = broadcast_tasks.get(owner_id)
                if task and not task.done():
                    task.cancel()
                    await event.delete()
                    await client_inst.send_message(chat_id, "⏹️ تم طلب إيقاف الإذاعة.")
                else:
                    await client_inst.send_message(chat_id, "⚠️ لا توجد إذاعة شغالة حالياً.")
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
                status = await client_inst.send_message(chat_id, "⏳ جاري تنفيذ العملية...")
                try:
                    completed = await bulk_account_action(client_inst, owner_id, action_map[text])
                    await status.edit(f"✅ اكتملت العملية. تم التعامل مع `{completed}` محادثة/قناة/قروب.")
                except Exception as e:
                    await status.edit(f"❌ تعذر تنفيذ العملية:\n`{e}`")
                return

            if text == "تفليش" or text.startswith("تفليش "):
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                
                has_ban = await check_user_ban_permissions(client_inst, chat_id, me)
                if not has_ban:
                    try:
                        await client_inst.send_message(chat_id, "❌ انت لست مرفوع بصلاحية حظر المستخدمين بالقروب/القناه")
                    except Exception:
                        pass
                    return
                
                # Fast flush process inline
                status_msg = await client_inst.send_message(chat_id, "⏳ جاري بدء تفليش وطرد جميع الأعضاء من القناة/المجموعة...")
                count = 0
                error_occurred = False
                err_msg = ""
                try:
                    chat_entity = await client_inst.get_entity(chat_id)
                    async for member in client_inst.iter_participants(chat_entity):
                        user = member
                        if user.id == me.id:
                            continue
                        try:
                            await client_inst(EditBannedRequest(chat_entity, user.id, ChatBannedRights(until_date=None, view_messages=True)))
                            count += 1
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            err_str = str(e)
                            if "FLOOD_WAIT" in err_str:
                                match = re.search(r"\d+", err_str)
                                wait_time = int(match.group()) if match else 5
                                await status_msg.edit(f"⚠️ تم اكتشاف حظر مؤقت من تيليجرام. جارٍ الانتظار لمدة {wait_time} ثانية...")
                                await asyncio.sleep(wait_time)
                                continue
                            elif "USER_ADMIN_INVALID" in err_str or "CHAT_ADMIN_REQUIRED" in err_str or "RIGHTS_NOT_AVAILABLE" in err_str:
                                error_occurred = True
                                err_msg = "انسحبت صلاحية الحظر أو حدث خطأ في الصلاحيات."
                                break
                            else:
                                pass

                    if error_occurred:
                        await status_msg.edit(f"⚠️ **توقف التفليش:** {err_msg}\n📊 **الإحصائيات النهائية:** تم طرد {count} عضواً قبل توقف الصلاحية.")
                    else:
                        await status_msg.edit(f"✅ تمت التصفية بنجاح!\n📊 **إحصائيات التفليش:** تم طرد {count} عضواً من القناة/المجموعة.")
                except Exception as e:
                    await status_msg.edit(f"❌ حدث خطأ أثناء التفليش: {e}\n📊 **الاحصائيات:** تم طرد {count} عضواً.")
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
                    
                    search_msg = await client_inst.send_message(chat_id, f"🔍 جاري البحث في يوتيوب عن: `{query}`...")
                    try:
                        file_path, title, duration, uploader, thumb_path = await search_and_download_youtube(query)
                        if file_path and os.path.exists(file_path):
                            await search_msg.delete()
                            await client_inst.send_file(
                                chat_id,
                                file_path,
                                thumb=thumb_path,
                                duration=duration,
                                title=title,
                                performer=uploader,
                                voice_note=False
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

            if text in ["تثبيت", "تثبيت الرسالة"]:
                if not is_source_subscribed(owner_id):
                    return
                try:
                    await event.delete()
                except Exception:
                    pass
                if event.reply_to_msg_id:
                    try:
                        await client_inst.pin_message(chat_id, event.reply_to_msg_id, notify=True)
                    except Exception:
                        pass
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

            if text in t_start:
                if user_info.get("del_tastir_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                started = start_running_task(client_inst, owner_id, chat_id, "tastir", target_msg_id, target_user_id)
                if not started:
                    await client_inst.send_message(chat_id, "⚠️ لا توجد جمل تسطير محفوظة. أضف جملة أولاً من زر «إضافة جمل التسطير».")
                return

            elif text in f_start:
                if user_info.get("del_fardiyyat_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                started = start_running_task(client_inst, owner_id, chat_id, "fardiyyat", target_msg_id, target_user_id)
                if not started:
                    await client_inst.send_message(chat_id, "⚠️ لا توجد كلمات فرديات محفوظة. أضف كلمة أولاً من زر «إضافة كلمات الفرديات».")
                return

            elif text in r_start:
                if user_info.get("del_reply_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                if not target_user_id or target_user_id in manager_bot_id:
                    await client_inst.send_message(chat_id, "⚠️ الريبلاي يحتاج الرد على رسالة شخص داخل القروب أو الخاص، ولا يعمل في محادثة بوت الإدارة.")
                    return
                if not (user_info.get("reply", []) or default_reply or user_info.get("tastir", []) or default_tastir or user_info.get("fardiyyat", []) or default_fardiyyat):
                    await client_inst.send_message(chat_id, "⚠️ لا توجد جمل ريبلاي أو تسطير أو فرديات محفوظة لإرسالها.")
                    return
                task_key = (owner_id, chat_id, target_user_id, "reply")
                running_tasks[task_key] = {
                    "task": None,
                    "owner_id": owner_id,
                    "chat_id": chat_id,
                    "target_user_id": target_user_id,
                    "mode": "reply",
                    "target_msg_id": target_msg_id
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

            # --- حفظ الذاتية التلقائي للوسائط ذاتية التدمير ---
            if is_source_subscribed(owner_id) and user_info.get("self_save_enabled", False):
                try:
                    ttl_value = getattr(event.message, "ttl_period", None) or getattr(event.media, "ttl_seconds", None)
                    if event.media and ttl_value:
                        await save_media_to_self_destination(client_inst, owner_id, event.message)
                except Exception as e:
                    print(f"Self-save error: {e}")

            # --- ميزة مجموعة التخزين: تنبيهات المنشن والرسائل الخاصة ---
            if is_source_subscribed(owner_id) and user_info.get("storage_groups"):
                storage_group_id = user_info["storage_groups"][-1]
                is_mention = bool(event.mentioned)
                is_private_msg = event.is_private and sender_id != me.id and sender_id not in manager_bot_id

                # لا يعيد تحويل أي رسالة تصل داخل مجموعة التخزين نفسها.
                if (is_mention or is_private_msg) and chat_id != storage_group_id:
                    try:
                        sender_entity = await event.get_sender()
                        sender_name = sender_entity.first_name or "بدون اسم"
                        if getattr(sender_entity, "last_name", None):
                            sender_name += f" {sender_entity.last_name}"
                        sender_username = f"@{sender_entity.username}" if getattr(sender_entity, "username", None) else "ماعنده"

                        # يحوّل الرسالة الأصلية أولاً، للنصوص والوسائط معاً.
                        await client_inst.forward_messages(storage_group_id, event.message)

                        if event.is_private:
                            # لا يوجد رابط HTTP مباشر لرسالة خاصة؛ هذا الرابط يفتح نفس المحادثة عند المرسل.
                            msg_link = f"tg://openmessage?user_id={sender_id}&message_id={event.id}"
                            alert_text = (
                                "🔔 **#تنبيه_جديد**\n\n"
                                "▪️ **المكان :** محادثة خاصة\n"
                                "▪️ **الايدي :** خاص\n\n"
                                "👤 **المرسل :**\n"
                                f"- الاسم : {sender_name}\n"
                                f"- الايدي : `{sender_id}`\n"
                                f"- اليوزر : {sender_username}\n\n"
                                f"🔗 **الرابط :** [اضغط هنا للذهاب للرسالة]({msg_link})"
                            )
                        else:
                            chat_entity = await event.get_chat()
                            chat_title = getattr(chat_entity, "title", "مجموعة")
                            chat_id_str = str(chat_id)
                            chat_username = getattr(chat_entity, "username", None)

                            if chat_username:
                                msg_link = f"https://t.me/{chat_username}/{event.id}"
                            else:
                                internal_chat_id = str(chat_id).replace("-100", "")
                                msg_link = f"https://t.me/c/{internal_chat_id}/{event.id}"

                            alert_text = (
                                "🔔 **#تنبيه_تاك**\n\n"
                                "▪️ **المجموعة :**\n"
                                f"- الاسم : {chat_title}\n"
                                f"- الايدي : `{chat_id_str}`\n\n"
                                "👤 **المرسل :**\n"
                                f"- الاسم : {sender_name}\n"
                                f"- الايدي : `{sender_id}`\n"
                                f"- اليوزر : {sender_username}\n\n"
                                f"🔗 **الرابط :** [اضغط هنا للذهاب للرسالة]({msg_link})"
                            )

                        await client_inst.send_message(
                            storage_group_id,
                            alert_text,
                            link_preview=False,
                            parse_mode="md"
                        )
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
            reply_key = (owner_id, chat_id, sender_id, "reply")
            if reply_key in running_tasks:
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
    if tastir_active or source_active:
        buttons.append([Button.inline("🔑 تسجيل الدخول / ربط الحساب", b"login_start")])
        if tastir_active:
            buttons.append([Button.inline("📝 قسم التسطير", b"tastir_section")])
        if source_active:
            buttons.append([Button.inline("⭐ مميزات السورس", b"source_features_menu")])
        buttons.append([Button.inline("📊 حالة الاشتراكات", b"sub_info")])

    if user_id in ADMIN_IDS:
        buttons.append([Button.inline("👑 لوحة تحكم المسؤول", b"admin_menu")])
    buttons.append([Button.url("📢 قناة البوت", CHANNEL_URL), Button.url("👨‍💻 المطور", DEV_URL)])
    return buttons


def tastir_section_keyboard(user_id):
    return [
        [Button.inline("📝 التسطير", b"tastir_menu"), Button.inline("🎯 الفرديات", b"fardiyyat_menu")],
        [Button.inline("💬 الريبلاي", b"reply_menu"), Button.inline("⚡ السرعة", b"speed_menu")],
        [Button.inline("🔙 رجوع", b"main_menu")]
    ]

def flush_menu_keyboard():
    return [
        [Button.inline("🚀 بدء التفليش", b"start_flush_flow")],
        [Button.inline("📖 شرح كيف تفلش يدويا", b"manual_flush_info")],
        [Button.inline("⚡ سرعة التفليش", b"flush_speed_menu")],
        [Button.inline("🔙 رجوع", b"source_features_menu")]
    ]

def flush_speed_menu_keyboard(user_id):
    u = users_db.get(user_id, {})
    spd = u.get("flush_speed", 0.5)
    return [
        [Button.inline(f"⏱️ 3 ثواني {'✅' if spd == 3.0 else ''}", b"fspd_3"), Button.inline(f"⏱️ 2 ثانية {'✅' if spd == 2.0 else ''}", b"fspd_2")],
        [Button.inline(f"⏱️ 1 ثانية {'✅' if spd == 1.0 else ''}", b"fspd_1"), Button.inline(f"⏱️ 0.5 ثانية {'✅' if spd == 0.5 else ''}", b"fspd_0.5")],
        [Button.inline("🔙 رجوع", b"flush_menu")]
    ]

def source_features_menu_keyboard():
    # مميزات المستخدم القديمة تبقى أولاً في مواقعها، ثم تأتي الأقسام الجديدة أسفلها.
    return [
        [Button.inline("💥 بدأ التفليش", b"start_flush_flow"), Button.inline("📖 شرح التفليش", b"manual_flush_info")],
        [Button.inline("📦 مجموعة التخزين", b"storage_group_menu")],
        [Button.inline("🔍 فكرة بحث اليوتيوب", b"feature_youtube_info"), Button.inline("📌 فكرة التثبيت", b"feature_pin_info")],
        [Button.inline("🧹 مسح الشامل", b"info_purge_all"), Button.inline("🔢 مسح بالعدد المحدد", b"info_purge_quick")],
        [Button.inline("🔇 الكتم الشامل", b"mute_menu"), Button.inline("🎙️ الصوتيات", b"voice_menu")],
        # الأقسام الجديدة التي تمت إضافتها لاحقاً.
        [Button.inline("👤 الحساب", b"section_account"), Button.inline("📬 الترحيب والردود", b"section_welcome")],
        [Button.inline("🧧 حفظ الذاتية", b"section_self_save"), Button.inline("📍 النشر التلقائي", b"section_publish")],
        [Button.inline("🎧 البحث والتحميل", b"section_download"), Button.inline("🧰 الأدوات", b"section_tools")],
        [Button.inline("🔙 رجوع", b"main_menu")]
    ]


def section_back_keyboard():
    return [[Button.inline("◀️ رجوع", b"source_features_menu")]]


def tools_back_keyboard():
    return [[Button.inline("◀️ رجوع", b"section_tools")]]


def account_section_keyboard():
    return [
        [Button.inline("📊 الاحصائيات", b"stats_menu"), Button.inline("📂 بياناتي", b"my_data_menu")],
        [Button.inline("💬 قروباتي وقنواتي", b"stats_menu"), Button.inline("🎭 الانتحال", b"clone_menu")],
        [Button.inline("🚶 المغادرة والتصفية", b"leave_cleanup_menu"), Button.inline("📆 تاريخ الإنشاء", b"creation_info")],
        [Button.inline("💳 الأيدي", b"id_menu")],
        [Button.inline("◀️ رجوع", b"source_features_menu")]
    ]


def welcome_section_keyboard():
    return [[Button.inline("📬 الترحيب والردود", b"welcome_menu")], [Button.inline("◀️ رجوع", b"source_features_menu")]]


def self_save_section_keyboard():
    return [[Button.inline("🧧 حفظ الذاتية", b"self_save_menu")], [Button.inline("◀️ رجوع", b"source_features_menu")]]


def publish_section_keyboard():
    return [[Button.inline("📍 النشر التلقائي", b"auto_publish_menu"), Button.inline("🎙 الإذاعة", b"broadcast_menu")], [Button.inline("◀️ رجوع", b"source_features_menu")]]


def download_section_keyboard():
    return [
        [Button.inline("🔴 أوامر اليوتيوب", b"youtube_menu")],
        [Button.inline("⚪ تيك توك", b"tiktok_menu"), Button.inline("🩸 انستغرام", b"instagram_menu")],
        [Button.inline("📌 بنترست", b"pinterest_menu"), Button.inline("📥 تحميل ستوري", b"story_menu")],
        [Button.inline("🧩 محتوى مقيد", b"restricted_menu"), Button.inline("📦 مستودع GitHub", b"github_menu")],
        [Button.inline("◀️ رجوع", b"source_features_menu")]
    ]


def tools_section_keyboard():
    return [
        [Button.inline("🔗 رابط الحساب", b"account_link_info"), Button.inline("✍️ الكتابة والخطوط", b"writing_menu")],
        [Button.inline("📟 الآلة الحاسبة", b"calculator_menu"), Button.inline("🖼 الصيغ والتحويل", b"conversion_menu")],
        [Button.inline("◀️ رجوع", b"source_features_menu")]
    ]


def calculator_keyboard():
    return [
        [Button.inline("1", b"calc_1"), Button.inline("2", b"calc_2"), Button.inline("3", b"calc_3"), Button.inline("+", b"calc_+")],
        [Button.inline("4", b"calc_4"), Button.inline("5", b"calc_5"), Button.inline("6", b"calc_6"), Button.inline("-", b"calc_-")],
        [Button.inline("7", b"calc_7"), Button.inline("8", b"calc_8"), Button.inline("9", b"calc_9"), Button.inline("×", b"calc_*")],
        [Button.inline(".", b"calc_."), Button.inline("0", b"calc_0"), Button.inline("⌫", b"calc_back"), Button.inline("÷", b"calc_/")],
        [Button.inline("AC", b"calc_clear"), Button.inline("=", b"calc_equals")]
    ]


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
        [Button.inline("🔙 رجوع", b"main_menu")]
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
        [Button.inline("🔙 رجوع", b"main_menu")]
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
        [Button.inline("🔙 رجوع", b"main_menu")]
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
        [Button.inline("🔙 رجوع", b"main_menu")]
    ]

def admin_menu_keyboard():
    return [
        [Button.inline("🎟️ توليد كود التسطير", b"gen_code"), Button.inline("⭐ توليد كود السورس", b"gen_source_code")],
        [Button.inline("➕ تفعيل البوت لمستخدم بالايدي", b"manual_activate_start")],
        [Button.inline("📅 تمديد اشتراك مستخدم", b"extend_subscription_start")],
        [Button.inline("📋 سجل التفعيل", b"activation_log_menu"), Button.inline("⌛ المنتهية اليوم", b"expired_today_menu")],
        [Button.inline("💾 إنشاء نسخة احتياطية", b"backup_export"), Button.inline("📥 استيراد نسخة احتياطية", b"backup_import_start")],
        [Button.inline("📱 إدارة جلسات الحسابات", b"sessions_menu"), Button.inline("⚠️ سجل الأخطاء", b"admin_error_log_menu")],
        [Button.inline("📢 إذاعة عامة", b"broadcast_start")],
        [Button.inline("📝 إدارة التسطير الأساسي", b"admin_tastir_menu"), Button.inline("🎯 إدارة الفرديات الأساسية", b"admin_fardiyyat_menu")],
        [Button.inline("👥 قائمة المسؤولين", b"list_admins"), Button.inline("📋 قائمة المستخدمين", b"list_users")],
        [Button.inline("➕ إضافة مسؤول", b"add_admin_start"), Button.inline("❌ حذف مسؤول", b"delete_admin_start")],
        [Button.inline("🗑️ حذف مستخدم نهائياً", b"revoke_user_start")],
        [Button.inline("📊 إحصائيات النظام", b"admin_stats")],
        [Button.inline("🔙 رجوع", b"main_menu")]
    ]


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
        [Button.inline("🔙 رجوع للوحة الأدمن", b"admin_menu")]
    ]

def admin_fardiyyat_menu_keyboard():
    return [
        [Button.inline("➕ إضافة فرديات أساسية", b"add_def_fardiyyat"), Button.inline("📋 عرض الفرديات الأساسية", b"show_def_fardiyyat")],
        [Button.inline("🗑️ حذف كلمة أساسية محددة", b"del_def_fardiyyat_item_start"), Button.inline("⚠️ حذف جميع الفرديات الأساسية", b"clear_def_fardiyyat")],
        [Button.inline("🔙 رجوع للوحة الأدمن", b"admin_menu")]
    ]

# ==================== Bot Event Handlers ====================
@bot.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    user_id = event.sender_id
    init_user_db(user_id)
    
    args = event.text.split()
    if len(args) > 1:
        code = args[1].strip()
        success, days = await apply_activation_code(user_id, code, event)
        if success:
            await event.respond(f"✅ تم تفعيل الاشتراك بنجاح لمدة {days} يوم.")
        else:
            success_src, days_src = await apply_source_activation_code(user_id, code, event)
            if success_src:
                await event.respond(f"✅ تم تفعيل مميزات السورس بنجاح لمدة {days_src} يوم.")
            else:
                await event.respond("❌ رمز التفعيل غير صالح أو تم استخدامه سابقاً.")

    me = await bot.get_me()
    bot_username = me.username or "bot"

    welcome_txt = (
        f"مرحباً بك في بوت [Pablo](https://t.me/{bot_username})\n\n"
        "أزرار التحكم بالأسفل 👇:"
    )
    await event.respond(welcome_txt, buttons=main_menu_keyboard(user_id), link_preview=False)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    global default_tastir, default_fardiyyat, default_reply
    user_id = event.sender_id
    data = event.data
    init_user_db(user_id)

    if data in [b"main_menu", b"tastir_section", b"tastir_menu", b"fardiyyat_menu", b"reply_menu", b"flush_menu", b"mute_menu", b"source_features_menu", b"voice_menu", b"admin_menu", b"admin_tastir_menu", b"admin_fardiyyat_menu", b"clone_menu", b"welcome_menu", b"auto_publish_menu", b"conversion_menu", b"id_menu"]:
        user_states.pop(user_id, None)

    if data.startswith(b"calc_"):
        key = (event.chat_id, event.message.id, user_id)
        expression = calculator_sessions.get(key, "")
        action = data.decode()[5:]
        if action == "clear":
            expression = ""
        elif action == "back":
            expression = expression[:-1]
        elif action == "equals":
            try:
                if not expression or not re.fullmatch(r"[0-9+\-*/(). ]+", expression):
                    raise ValueError("صيغة غير صالحة")
                value = eval(expression, {"__builtins__": {}}, {})
                expression = str(value)
            except Exception:
                expression = "خطأ"
        else:
            expression = "" if expression == "خطأ" else expression
            expression += action
        calculator_sessions[key] = expression
        display = expression or "0"
        await event.edit(f"📟 **الآلة الحاسبة**\n\n`{display}`", buttons=calculator_keyboard())
        return

    if data == b"main_menu":
        me = await bot.get_me()
        bot_username = me.username or "bot"
        welcome_txt = (
            f"مرحباً بك في بوت [Pablo](https://t.me/{bot_username})\n\n"
            "أزرار التحكم بالأسفل 👇:"
        )
        try:
            await event.edit(welcome_txt, buttons=main_menu_keyboard(user_id), link_preview=False)
        except MessageNotModifiedError:
            await event.answer()

    elif data == b"flush_menu":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        await event.edit("⚡ **قائمة التفليش:**\n\nاختر ما يناسبك من الخيارات أدناه:", buttons=flush_menu_keyboard())

    elif data == b"manual_flush_info":
        if not is_source_subscribed(user_id):
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        txt = (
            "📖 **شرح كيف تفلش يدويا:**\n\n"
            "• يمكنك استخدام أمر التفليش السريع عبر كتابة `.تفليش` في أي مجموعة أو قناة يمتلك حسابك (اليوزر بوت) صلاحية حظر المستخدمين فيها.\n"
            "• سيقوم الحساب بحذف أمرك تلقائياً وبدء تفليش وطرد جميع الأعضاء بسرعة 0.5 ثانية لكل عضو.\n"
            "• سيقوم البوت بإرسال إشعارات جاري التفليش والإحصائيات النهائية أو تفاصيل ما حدث عند اكتمال العملية أو سحب الصلاحية."
        )
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"flush_menu")]])

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
            buttons=[[Button.inline("🔙 رجوع", b"flush_menu")]]
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
            await event.edit("❌ تم إلغاء عملية التفليش.", buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])
            return

        client = user_clients.get(user_id)
        if not client:
            await event.answer("⚠️ جلسة الحساب غير متصلة.", alert=True)
            return
            
        user_states.pop(user_id, None)
        me = await client.get_me()
        status_msg = await event.edit("⏳ جاري بدء التفليش وطرد جميع الأعضاء...")
        
        async def fast_flush():
            count = 0
            error_occurred = False
            err_msg = ""
            try:
                chat_entity = await client.get_entity(chat_id)
                async for member in client.iter_participants(chat_entity):
                    user = member
                    if user.id == me.id:
                        continue
                    try:
                        await client(EditBannedRequest(chat_entity, user.id, ChatBannedRights(until_date=None, view_messages=True)))
                        count += 1
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        err_str = str(e)
                        if "FLOOD_WAIT" in err_str:
                            match = re.search(r"\d+", err_str)
                            wait_time = int(match.group()) if match else 5
                            await status_msg.edit(f"⚠️ تم اكتشاف حظر مؤقت من تيليجرام. جارٍ الانتظار لمدة {wait_time} ثانية...")
                            await asyncio.sleep(wait_time)
                            continue
                        elif "USER_ADMIN_INVALID" in err_str or "CHAT_ADMIN_REQUIRED" in err_str or "RIGHTS_NOT_AVAILABLE" in err_str:
                            error_occurred = True
                            err_msg = "انسحبت صلاحية الحظر أو حدث خطأ في الصلاحيات."
                            break
                        else:
                            pass

                if error_occurred:
                    await status_msg.edit(f"⚠️ **توقف التفليش:** {err_msg}\n📊 **الإحصائيات النهائية:** تم طرد {count} عضواً قبل توقف الصلاحية.", buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])
                else:
                    await status_msg.edit(f"✅ تمت التصفية بنجاح!\n📊 **إحصائيات التفليش:** تم طرد {count} عضواً من القناة/المجموعة.", buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])
            except Exception as e:
                await status_msg.edit(f"❌ حدث خطأ أثناء التفليش: {e}\n📊 **الاحصائيات:** تم طرد {count} عضواً.", buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])
                
        asyncio.create_task(fast_flush())

    elif data == b"cancel_flush":
        user_states.pop(user_id, None)
        await event.edit("⚡ **قائمة التفليش:**", buttons=flush_menu_keyboard())

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

    elif data == b"set_welcome_photo":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        user_states[user_id] = {"step": "awaiting_welcome_photo"}
        await event.edit("🖼️ أرسل صورة الترحيب الآن:", buttons=[[Button.inline("🔙 رجوع", b"welcome_menu")]])

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
        await event.edit(AUTO_PUBLISH_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"auto_publish_info":
        await event.edit(
            "📖 **أوامر النشر التلقائي:**\n\n"
            "• داخل المجموعة: `.نشر المدة العدد تحويل` أو `.واو المدة العدد تحويل` بالرد على الرسالة.\n"
            "• خارج المجموعة: `.ستارت المدة العدد آيدي_القروب تحويل` بالرد على الرسالة.\n\n"
            "⚠️ كلمة `تحويل` اختيارية: لا تكتبها للنشر بدون تحويل المصدر، واكتبها في نهاية الأمر للتحويل العادي للنص أو الوسائط.\n"
            "إذا منعت الوجهة تحويل محتوى القناة أو حدث أي خطأ، يتوقف النشر ويصلك السبب.\n\n"
            "• `.النشر الشغال` لعرض العمليات.\n• `.بس` لإيقاف نشر القروب الحالي.\n• `.ايقاف النشر` لإيقاف كل عملياتك.\n\n"
            "ضع `999` كعدد للتشغيل الطويل.",
            buttons=[[Button.inline("🔙 رجوع", b"auto_publish_menu")]]
        )

    elif data == b"auto_publish_running":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        keys = [key for key, task in auto_publish_tasks.items() if key[0] == user_id and not task.done()]
        text = "📊 **عمليات النشر الشغالة:**\n\n" + ("\n".join(f"• القروب: `{key[1]}`" for key in keys) if keys else "لا توجد عمليات نشر حالياً.")
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
        await event.edit(CONVERSION_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

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
        await event.edit(ID_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

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
            await event.edit(report, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])
        except Exception as e:
            await event.edit(f"❌ تعذر جلب البيانات:\n`{e}`", buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"account_link_info":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(ACCOUNT_LINK_GUIDE, buttons=tools_back_keyboard())

    elif data == b"creation_info":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(CREATION_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"self_save_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(SELF_SAVE_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"stats_menu":
        if not is_source_subscribed(user_id):
            await event.answer(source_lock_message(), alert=True)
            return
        await event.edit(STATS_GUIDE, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

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
        buttons = tools_back_keyboard() if data == b"writing_menu" else section_back_keyboard()
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
            results = await client.inline_query(bot_me.username, "pablo_calculator")
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
            await event.answer("⚠️ لا يمكنك استخدام أي ميزة بالسورس إلا بكود تفعيل. الرجاء التواصل مع المطور وإرسال كود تفعيل مميزات السورس.", alert=True)
            return
        txt = (
            "📌 **فكرة التثبيت:**\n\n"
            "يتيح لك السورس ميزة تثبيت الرسائل المهمة بسهولة تامة وبأمر سريع عبر حسابك الشخصي (اليوزر بوت).\n\n"
            "**كيف تستخدمها؟**\n"
            "• قم بالرد على أي رسالة تريد تثبيتها واكتب: `تثبيت` أو `تثبيت الرسالة`.\n"
            "• سيقوم الحساب تلقائياً بحذف أمرك وتثبيت الرسالة المطلوبة في المحادثة أو القروب مع إرسال إشعار."
        )
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"enter_code_start":
        user_states[user_id] = {"step": "awaiting_code_input"}
        await event.edit("🎟️ **كود تفعيل التسطير:**\n\nيرجى إرسال كود تفعيل التسطير الآن:", buttons=[[Button.inline("🔙 رجوع", b"main_menu")]])

    elif data == b"enter_source_code_start":
        user_states[user_id] = {"step": "awaiting_source_code_input"}
        await event.edit("🎟️ **إدخال كود تفعيل مميزات السورس:**\n\nيرجى إرسال كود تفعيل مميزات السورس الآن:", buttons=[[Button.inline("🔙 رجوع", b"main_menu")]])

    elif data == b"sub_info":
        if user_id in ADMIN_IDS:
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
            "يرجى إرسال رقم الهاتف كاملاً مع رمز الدولة (مثال: `+966500000000`):",
            buttons=[[Button.inline("🔙 رجوع", b"main_menu")]]
        )
    elif data in [b"manual_activate_start", b"extend_subscription_start"] and user_id in ADMIN_IDS:
        mode = "extend" if data == b"extend_subscription_start" else "activate"
        user_states[user_id] = {"step": f"awaiting_{mode}_user_id", "mode": mode}
        title = "تمديد" if mode == "extend" else "تفعيل"
        await event.edit(f"➕ **{title} البوت لمستخدم:**\n\nأرسل آيدي المستخدم الرقمي الآن:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data in [b"manual_toggle_tastir", b"manual_toggle_source"] and user_id in ADMIN_IDS:
        state = user_states.get(user_id, {})
        if state.get("step") != "awaiting_manual_choices":
            await event.answer("⚠️ ابدأ عملية التفعيل أو التمديد أولاً.", alert=True)
            return
        key = "grant_tastir" if data == b"manual_toggle_tastir" else "grant_source"
        state[key] = not state.get(key, False)
        await event.edit("✅ **اختيار نوع الاشتراك:**\n\nحدد الاشتراكات ثم اضغط تأكيد.", buttons=manual_subscription_keyboard(state))

    elif data == b"manual_confirm" and user_id in ADMIN_IDS:
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

    elif data == b"activation_log_menu" and user_id in ADMIN_IDS:
        rows = activation_log[-20:][::-1]
        txt = "📋 **آخر سجل تفعيل:**\n\n" + ("\n".join(f"• {time.strftime('%Y-%m-%d %H:%M', time.localtime(r['time']))} | `{r['user_id']}` | {r['action']} | {r.get('days', 0)} يوم" for r in rows) if rows else "لا يوجد سجل حتى الآن.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"expired_today_menu" and user_id in ADMIN_IDS:
        today = time.strftime('%Y-%m-%d')
        rows = [r for r in activation_log if r.get('action') == 'انتهاء_اشتراك' and time.strftime('%Y-%m-%d', time.localtime(r['time'])) == today]
        txt = "⌛ **اشتراكات انتهت اليوم:**\n\n" + ("\n".join(f"• المستخدم: `{r['user_id']}`" for r in rows) if rows else "لا توجد اشتراكات منتهية مسجلة اليوم.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

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
        if user_id not in ADMIN_IDS:
            await event.answer("⚠️ هذه القائمة مخصصة للمسؤولين فقط.", alert=True)
            return
        await event.edit("👑 **لوحة تحكم المسؤول:**", buttons=admin_menu_keyboard())

    elif data == b"admin_tastir_menu" and user_id in ADMIN_IDS:
        await event.edit("📝 **إدارة التسطير الأساسي (العام):**", buttons=admin_tastir_menu_keyboard())

    elif data == b"add_def_tastir" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_add_def_tastir"}
        await event.edit("➕ أرسل الجملة الأساسية للتسطير (لتنضاف تلقائياً للجميع):", buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])

    elif data == b"show_def_tastir" and user_id in ADMIN_IDS:
        txt = "📋 **قائمة التسطير الأساسية الحالية:**\n\n" + ("\n".join([f"• `{p}`" for p in default_tastir]) if default_tastir else "لا توجد جمل أساسية مضافة.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])

    elif data == b"del_def_tastir_item_start" and user_id in ADMIN_IDS:
        if not default_tastir:
            await event.answer("⚠️ لا توجد جمل أساسية لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_def_tastir_item"}
        txt = "📋 **أرسل الجملة الأساسية التي تريد حذفها:**\n\n"
        for p in default_tastir:
            txt += f"• `{p}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])

    elif data == b"clear_def_tastir" and user_id in ADMIN_IDS:
        default_tastir = []
        save_data()
        await event.answer("⚠️ تم مسح جميع جمل التسطير الأساسية.", alert=True)
        await event.edit("📝 **إدارة التسطير الأساسي:**", buttons=admin_tastir_menu_keyboard())

    elif data == b"admin_fardiyyat_menu" and user_id in ADMIN_IDS:
        await event.edit("🎯 **إدارة الفرديات الأساسية (العامة):**", buttons=admin_fardiyyat_menu_keyboard())

    elif data == b"add_def_fardiyyat" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_add_def_fardiyyat"}
        await event.edit("➕ أرسل الكلمة الأساسية للفرديات (لتنضاف تلقائياً للجميع):", buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])

    elif data == b"show_def_fardiyyat" and user_id in ADMIN_IDS:
        txt = "📋 **قائمة الفرديات الأساسية الحالية:**\n\n" + ("\n".join([f"• `{p}`" for p in default_fardiyyat]) if default_fardiyyat else "لا توجد كلمات أساسية مضافة.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])

    elif data == b"del_def_fardiyyat_item_start" and user_id in ADMIN_IDS:
        if not default_fardiyyat:
            await event.answer("⚠️ لا توجد كلمات أساسية لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_def_fardiyyat_item"}
        txt = "📋 **أرسل الكلمة الأساسية التي تريد حذفها:**\n\n"
        for p in default_fardiyyat:
            txt += f"• `{p}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])

    elif data == b"clear_def_fardiyyat" and user_id in ADMIN_IDS:
        default_fardiyyat = []
        save_data()
        await event.answer("⚠️ تم مسح جميع كلمات الفرديات الأساسية.", alert=True)
        await event.edit("🎯 **إدارة الفرديات الأساسية:**", buttons=admin_fardiyyat_menu_keyboard())

    elif data == b"broadcast_start" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_broadcast_msg"}
        await event.edit("📢 **الإذاعة العامة:**\n\nأرسل الرسالة المراد إرسالها لجميع المستخدِمين الآن:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"gen_code" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_code_days"}
        await event.edit("🎟️ **توليد رمز اشتراك جديد:**\n\nأرسل مدة الاشتراك بالأيام (مثال: `30`):", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"gen_source_code" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_source_code_days"}
        await event.edit("🎟️ **توليد كود مميزات السورس جديد:**\n\nأرسل مدة اشتراك مميزات السورس بالأيام (مثال: `30`):", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"list_admins" and user_id in ADMIN_IDS:
        await event.edit("جاري تحميل قائمة المسؤولين...")
        txt = "👥 **قائمة المسؤولين في النظام:**\n\n"
        for idx, aid in enumerate(ADMIN_IDS, 1):
            user_info_str = await format_user_details(aid)
            txt += f"**{idx}.**\n{user_info_str}\n\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]], link_preview=False)

    elif data == b"list_users" and user_id in ADMIN_IDS:
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

    elif data == b"revoke_user_start" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_revoke_user_id"}
        await event.edit("🗑️ **حذف مستخدم نهائياً:**\n\nأرسل المعرف الرقمي (ID) للمستخدم المراد إلغاء اشتراكه وتصفيره:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"add_admin_start" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_new_admin_id"}
        await event.edit("➕ **إضافة مسؤول جديد:**\n\nأرسل المعرف الرقمي (ID) لشخص المراد ترقيته:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"delete_admin_start" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_delete_admin_id"}
        await event.edit("❌ **حذف مسؤول:**\n\nأرسل المعرف الرقمي (ID) للمسؤول المراد إزالته:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"backup_export" and user_id in ADMIN_IDS:
        try:
            backup_path = create_settings_backup()
            await bot.send_file(user_id, backup_path, caption="💾 نسخة احتياطية للإعدادات والاشتراكات والأكواد. لا تتضمن ملفات الجلسات الحساسة.")
        except Exception as e:
            await report_admin_error("إنشاء نسخة احتياطية", e, user_id)
            await event.answer("❌ تعذر إنشاء النسخة الاحتياطية.", alert=True)

    elif data == b"backup_import_start" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_backup_import"}
        await event.edit("📥 أرسل الآن ملف النسخة الاحتياطية بصيغة JSON. سيتم حفظ نسخة تلقائية من البيانات الحالية قبل الاستيراد.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"sessions_menu" and user_id in ADMIN_IDS:
        saved_ids = list_saved_session_ids()
        connected_ids = sorted(user_clients.keys())
        saved_text = "\n".join(f"• `{uid}`" for uid in saved_ids[:40]) or "لا توجد جلسات محفوظة."
        connected_text = "\n".join(f"• `{uid}`" for uid in connected_ids[:40]) or "لا توجد جلسات متصلة حالياً."
        await event.edit(
            f"📱 **إدارة جلسات الحسابات**\n\n🗃️ جلسات محفوظة:\n{saved_text}\n\n🟢 جلسات متصلة الآن:\n{connected_text}",
            buttons=[[Button.inline("❌ فصل جلسة مستخدم", b"session_disconnect_start")], [Button.inline("🔙 رجوع", b"admin_menu")]]
        )

    elif data == b"session_disconnect_start" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_disconnect_session_id"}
        await event.edit("❌ أرسل آيدي المستخدم الذي تريد فصل جلسته. لن يتم حذف اشتراكه أو بياناته، لكنه يحتاج لتسجيل الدخول من جديد.", buttons=[[Button.inline("🔙 رجوع", b"sessions_menu")]])

    elif data == b"admin_error_log_menu" and user_id in ADMIN_IDS:
        if not admin_error_log:
            await event.edit("✅ لا يوجد أخطاء مسجلة حالياً.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        else:
            rows = []
            for item in admin_error_log[-15:][::-1]:
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(item.get("time", 0)))
                rows.append(f"• `{when}` | {item.get('operation')} | مستخدم: `{item.get('user_id') or '- '}`\n  السبب: `{item.get('error')}`")
            await event.edit("⚠️ **آخر أخطاء النظام:**\n\n" + "\n\n".join(rows), buttons=[[Button.inline("🗑️ مسح سجل الأخطاء", b"admin_error_log_clear")], [Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"admin_error_log_clear" and user_id in ADMIN_IDS:
        admin_error_log.clear()
        save_data()
        await event.answer("✅ تم مسح سجل الأخطاء.", alert=True)
        await event.edit("✅ لا يوجد أخطاء مسجلة حالياً.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"admin_stats" and user_id in ADMIN_IDS:
        txt = f"📊 **إحصائيات النظام:**\n\n• إجمالي المسجلين: {len(users_db)}\n• عدد المسؤولين: {len(ADMIN_IDS)}\n• الحسابات المتصلة حالياً: {len(user_clients)}\n• المهام الشغالة حالياً: {len(running_tasks)}"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

# ==================== Inline Menus (via the Manager Bot) ====================
@bot.on(events.InlineQuery)
async def inline_source_menu_handler(event):
    query = (event.text or "").strip()
    if query.startswith("pablo_source_menu:"):
        token = query.split(":", 1)[1]
        request = inline_source_requests.pop(token, None)
        # لا نعيد أي نتيجة إذا لم تأتِ من الحساب المرتبط الذي طلب القائمة للتو.
        if not request or request.get("expires_at", 0) < time.time() or request.get("owner_id") != event.sender_id:
            await event.answer([], cache_time=0, is_personal=True)
            return
        result = event.builder.article(
            title="مميزات السورس — بوت بابلو",
            text=SOURCE_MENU_TITLE,
            buttons=source_features_menu_keyboard(),
            link_preview=False
        )
        await event.answer([result], cache_time=0, is_personal=True)
    elif query == "pablo_calculator":
        result = event.builder.article(
            title="الآلة الحاسبة",
            text="📟 **الآلة الحاسبة**\n\n`0`",
            buttons=calculator_keyboard(),
            link_preview=False
        )
        await event.answer([result], cache_time=0, is_personal=True)


# ==================== Text & Media Input Handlers ====================
@bot.on(events.NewMessage)
async def message_input_handler(event):
    global default_tastir, default_fardiyyat, default_reply, activation_codes, source_activation_codes
    if not event.is_private or (event.text and event.text.startswith("/")):
        return

    user_id = event.sender_id
    state = user_states.get(user_id)
    if not state:
        return

    step = state.get("step")
    text = event.raw_text.strip() if event.raw_text else ""

    if step == "awaiting_backup_import":
        if user_id not in ADMIN_IDS:
            user_states.pop(user_id, None)
            return
        if not event.document:
            await event.respond("⚠️ أرسل ملف JSON للنسخة الاحتياطية.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        imported_path = None
        try:
            imported_path = await event.download_media(file=TEMP_DIR)
            with open(imported_path, "r", encoding="utf-8") as handle:
                imported = json.load(handle)
            if not isinstance(imported, dict) or "users_db" not in imported:
                raise ValueError("ملف النسخة الاحتياطية غير صالح.")
            current_backup = create_settings_backup()
            with open(DATA_FILE, "w", encoding="utf-8") as handle:
                json.dump(imported, handle, ensure_ascii=False, indent=4)
            for session_client in list(user_clients.values()):
                try:
                    await session_client.disconnect()
                except Exception:
                    pass
            user_clients.clear()
            load_data()
            user_states.pop(user_id, None)
            await event.respond(f"✅ تم استيراد النسخة الاحتياطية بنجاح. تم حفظ نسخة من البيانات السابقة في: `{os.path.basename(current_backup)}`", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        except Exception as e:
            await report_admin_error("استيراد نسخة احتياطية", e, user_id)
            await event.respond(f"❌ تعذر استيراد النسخة: `{e}`", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        finally:
            _safe_remove(imported_path)
        return

    elif step == "awaiting_disconnect_session_id":
        if user_id not in ADMIN_IDS or not text.isdigit():
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
        photo_path = os.path.join(VOICES_DIR, f"welcome_{user_id}.jpg")
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

    elif step in ["awaiting_activate_user_id", "awaiting_extend_user_id"] and user_id in ADMIN_IDS:
        if not text.isdigit():
            await event.respond("⚠️ أرسل آيدي رقمي صحيح للمستخدم:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        target_uid = int(text)
        mode = state.get("mode", "activate")
        user_states[user_id] = {"step": f"awaiting_{mode}_days", "mode": mode, "target_uid": target_uid}
        await event.respond("📅 أرسل عدد أيام الاشتراك:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        return

    elif step in ["awaiting_activate_days", "awaiting_extend_days"] and user_id in ADMIN_IDS:
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

    elif step == "awaiting_code_days" and user_id in ADMIN_IDS:
        if not text.isdigit():
            await event.respond("⚠️ يرجى إرسال رقم صحيح يمثل عدد الأيام:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        days = int(text)
        code = "PBL-" + secrets.token_hex(4).upper()
        activation_codes[code] = days
        _append_activation_log("توليد_كود_تسطير", user_id, user_id, days, tastir=True)
        save_data()
        user_states.pop(user_id, None)
        await event.respond(f"✅ **تم توليد كود التسطير بنجاح:**\n\n• الكود: `{code}`\n• المدة: `{days}` يوم", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        return

    elif step == "awaiting_source_code_days" and user_id in ADMIN_IDS:
        if not text.isdigit():
            await event.respond("⚠️ يرجى إرسال رقم صحيح يمثل عدد الأيام:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return
        days = int(text)
        code = "SRC-" + secrets.token_hex(4).upper()
        source_activation_codes[code] = days
        _append_activation_log("توليد_كود_سورس", user_id, user_id, days, source=True)
        save_data()
        user_states.pop(user_id, None)
        await event.respond(f"✅ **تم توليد كود مميزات السورس بنجاح:**\n\n• الكود: `{code}`\n• المدة: `{days}` يوم", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        return

    elif step == "awaiting_add_def_tastir" and user_id in ADMIN_IDS:
        default_tastir.append(text)
        save_data()
        await event.respond("✅ تم إضافة الجملة الأساسية للتسطير بنجاح وتحديثها للجميع.\n\nيمكنك إرسال جملة أخرى أو الضغط على رجوع:", buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])
        return

    elif step == "awaiting_del_def_tastir_item" and user_id in ADMIN_IDS:
        if text in default_tastir:
            default_tastir.remove(text)
            save_data()
            await event.respond(f"✅ تم حذف الجملة الأساسية: `{text}` بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])
        else:
            await event.respond("❌ الجملة غير موجودة في التسطير الأساسي، تأكد منها ثم أرسلها مجدداً:", buttons=[[Button.inline("🔙 رجوع", b"admin_tastir_menu")]])
        return

    elif step == "awaiting_add_def_fardiyyat" and user_id in ADMIN_IDS:
        default_fardiyyat.append(text)
        save_data()
        await event.respond("✅ تم إضافة الكلمة الأساسية للفرديات بنجاح وتحديثها للجميع.\n\nيمكنك إرسال كلمة أخرى أو الضغط على رجوع:", buttons=[[Button.inline("🔙 رجوع", b"admin_fardiyyat_menu")]])
        return

    elif step == "awaiting_del_def_fardiyyat_item" and user_id in ADMIN_IDS:
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
            await event.respond("❌ كود تفعيل مميزات السورس غير صالح أو تم استخدامه سابقاً.")

    elif step == "awaiting_broadcast_msg" and user_id in ADMIN_IDS:
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
        await msg.edit(f"✅ **تم إكمال الإذاعة بنجاح:**\n\n• تم الإرسال إلى: `{success_count}` مستخدماً\n• فشل الإرسال إلى: `{fail_count}` مستخدماً", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        return

    elif step == "awaiting_revoke_user_id" and user_id in ADMIN_IDS:
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

    elif step == "awaiting_new_admin_id" and user_id in ADMIN_IDS:
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

    elif step == "awaiting_delete_admin_id" and user_id in ADMIN_IDS:
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
            client = TelegramClient(f"{SESSIONS_DIR}/user_{user_id}", API_ID, API_HASH)
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
async def main():
    print("Starting bot...")
    await bot.start(bot_token=BOT_TOKEN)
    manager_me = await bot.get_me()
    if not manager_me.bot:
        raise RuntimeError("جلسة الإدارة ليست بوتاً. احذف جلسة manager_bot_inline_session وأعد التشغيل.")
    print(f"Manager Bot: @{manager_me.username or 'بدون_يوزر'} | ID: {manager_me.id}")
    print("لتعمل .الاوامر كأزرار عبر البوت: فعّل Inline Mode لهذا البوت من BotFather عبر /setinline.")
    
    asyncio.create_task(subscription_maintenance_loop())

    # استرجاع الجلسات المسجلة مسبقاً للمستخدمين وتشغيلها
    for uid_str, u_data in users_db.items():
        uid = int(uid_str)
        session_path = f"{SESSIONS_DIR}/user_{uid}"
        if os.path.exists(f"{session_path}.session"):
            try:
                client = TelegramClient(session_path, API_ID, API_HASH)
                await client.connect()
                if await client.is_user_authorized():
                    user_clients[uid] = client
                    await register_userbot_events(client, uid)
                    print(f"Restored userbot session for user {uid}")
            except Exception as e:
                print(f"Failed to restore session for {uid}: {e}")

    print("Bot is running...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())

