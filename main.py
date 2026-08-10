import asyncio
import os
import random
import secrets
import time
import json
import re
import yt_dlp
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError

# ==================== Configuration ====================
API_ID = 39686732
API_HASH = "4ccd261405e1fe78120b5e0a0efe48a7"
BOT_TOKEN = "8949542441:AAGYvRu0ASHzRJX2lczGB2XeArrgYVKEMc0"

# آيدي بوت الإدارة لمنع التداخل (تم وضعه هنا)
manager_bot_id = 8949542441

# قائمة المسؤولين (المطور الأساسي)
ADMIN_IDS = [520859814]

# رابط المطور وقناة البوت
DEV_URL = "https://t.me/Nardouv"
CHANNEL_URL = "https://t.me/PabloBot666"

# ملف حفظ البيانات ومجلد الصوتيات والجلسات
DATA_FILE = "bot_data.json"
VOICES_DIR = "voices"
SESSIONS_DIR = "sessions"

if not os.path.exists(VOICES_DIR):
    os.makedirs(VOICES_DIR)
if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)

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

bot = TelegramClient("manager_bot_session", API_ID, API_HASH)

# ==================== Persistence Functions ====================
def save_data():
    try:
        data = {
            "default_tastir": default_tastir,
            "default_fardiyyat": default_fardiyyat,
            "default_reply": default_reply,
            "users_db": users_db,
            "activation_codes": activation_codes,
            "admin_ids": ADMIN_IDS
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving data: {e}")

def load_data():
    global default_tastir, default_fardiyyat, default_reply, users_db, activation_codes, ADMIN_IDS
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

def init_user_db(user_id):
    if user_id not in users_db:
        users_db[user_id] = {}
    u = users_db[user_id]
    u.setdefault("expires_at", time.time() + (100 * 365 * 86400) if user_id in ADMIN_IDS else 0)
    u.setdefault("tastir", [])
    u.setdefault("fardiyyat", [])
    u.setdefault("reply", [])
    u.setdefault("bot_responses", [])
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

    task = asyncio.create_task(loop())
    running_tasks[task_key]["task"] = task

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

async def register_userbot_events(client_inst, owner_id):
    @client_inst.on(events.NewMessage)
    async def userbot_handler(event):
        # تجاهل تام لأي رسالة صادرة من البوت أو مرسلة إليه لمنع التداخل
        if manager_bot_id and (event.chat_id == manager_bot_id or event.sender_id == manager_bot_id):
            return

        chat_id = event.chat_id
        text = event.raw_text.strip() if event.raw_text else ""
        me = await client_inst.get_me()

        if event.sender_id == me.id:
            init_user_db(owner_id)
            user_info = users_db[owner_id]
            
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

            cmd_parts = text.split()
            cmd_first_word = cmd_parts[0] if cmd_parts else ""

            if text.startswith("بحث "):
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
                if user_info.get("del_mute_cmd", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                target_uid = await resolve_target_user(event)
                if target_uid and target_uid != me.id and target_uid != manager_bot_id:
                    if target_uid not in user_info["muted_users"]:
                        user_info["muted_users"].append(target_uid)
                        save_data()
                return

            elif text in um_cmds or cmd_first_word in um_cmds:
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

            if text in t_start:
                if user_info.get("del_tastir_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                start_running_task(client_inst, owner_id, chat_id, "tastir", target_msg_id, target_user_id)
                return

            elif text in f_start:
                if user_info.get("del_fardiyyat_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                start_running_task(client_inst, owner_id, chat_id, "fardiyyat", target_msg_id, target_user_id)
                return

            elif text in r_start:
                if user_info.get("del_reply_start", True):
                    try:
                        await event.delete()
                    except Exception:
                        pass
                if not target_user_id or target_user_id == manager_bot_id:
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

            is_target_active_user = False
            for key, info in list(running_tasks.items()):
                if info.get("owner_id") == owner_id and info.get("chat_id") == chat_id and info.get("target_user_id") == sender_id:
                    is_target_active_user = True
                    break

            if is_target_active_user and is_subscribed(owner_id):
                bot_responses = user_info.get("bot_responses", [])
                if bot_responses and text:
                    matched_response = None
                    cleaned_msg_text = text.lower()
                    
                    for item in bot_responses:
                        if item.lower() in cleaned_msg_text:
                            matched_response = item
                            break
                    
                    if matched_response:
                        phrase = random.choice(bot_responses)
                        try:
                            await client_inst.send_message(chat_id, phrase, reply_to=event.id)
                            return
                        except Exception:
                            pass

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
    buttons = [
        [Button.inline("🔑 تسجيل الدخول / ربط الحساب", b"login_start")]
    ]
    
    if not is_subscribed(user_id):
        buttons.append([Button.inline("🎟️ تفعيل كود الاشتراك", b"enter_code_start")])
        
    buttons.append([Button.inline("📝 التسطير", b"tastir_menu"), Button.inline("🎯 الفرديات", b"fardiyyat_menu")])
    buttons.append([Button.inline("💬 الريبلاي", b"reply_menu")])
    buttons.append([Button.inline("⭐ مميزات السورس", b"source_features_menu")])
    buttons.append([Button.inline("⚡ السرعة", b"speed_menu"), Button.inline("📊 حالة الاشتراك", b"sub_info")])
    
    if user_id in ADMIN_IDS:
        buttons.append([Button.inline("👑 لوحة تحكم المسؤول", b"admin_menu")])

    buttons.append([
        Button.url("📢 قناة البوت", CHANNEL_URL),
        Button.url("👨‍💻 المطور", DEV_URL)
    ])
    return buttons

def source_features_menu_keyboard():
    return [
        [Button.inline("🔍 فكرة بحث اليوتيوب", b"feature_youtube_info")],
        [Button.inline("📌 فكرة التثبيت", b"feature_pin_info")],
        [Button.inline("🧹 مسح الشامل", b"info_purge_all"), Button.inline("🔢 مسح بالعدد المحدد", b"info_purge_quick")],
        [Button.inline("🔇 الكتم الشامل", b"mute_menu"), Button.inline("🎙️ الصوتيات", b"voice_menu")],
        [Button.inline("🔙 رجوع", b"main_menu")]
    ]

def bot_responses_menu_keyboard():
    return [
        [Button.inline("➕ إضافة كلمات وكلمات ردود", b"add_bot_response"), Button.inline("📋 عرض ردود البوت", b"show_bot_responses")],
        [Button.inline("❌ حذف رد محدد", b"del_bot_response_item_start"), Button.inline("⚠️ حذف جميع ردود البوت", b"clear_bot_responses")],
        [Button.inline("🔙 رجوع للوحة الأدمن", b"admin_menu")]
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
        [Button.inline("🎟️ توليد كود اشتراك", b"gen_code"), Button.inline("📢 إذاعة عامة", b"broadcast_start")],
        [Button.inline("📝 إدارة التسطير الأساسي", b"admin_tastir_menu"), Button.inline("🎯 إدارة الفرديات الأساسية", b"admin_fardiyyat_menu")],
        [Button.inline("🤖 ردود البوت", b"bot_responses_menu")],
        [Button.inline("👥 قائمة المسؤولين", b"list_admins"), Button.inline("📋 قائمة المستخدمين", b"list_users")],
        [Button.inline("➕ إضافة مسؤول", b"add_admin_start"), Button.inline("❌ حذف مسؤول", b"delete_admin_start")],
        [Button.inline("❌ إلغاء اشتراك مستخدم", b"revoke_user_start")],
        [Button.inline("📊 إحصائيات النظام", b"admin_stats")],
        [Button.inline("🔙 رجوع", b"main_menu")]
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

    if data in [b"main_menu", b"tastir_menu", b"fardiyyat_menu", b"reply_menu", b"bot_responses_menu", b"mute_menu", b"source_features_menu", b"voice_menu", b"admin_menu", b"admin_tastir_menu", b"admin_fardiyyat_menu"]:
        user_states.pop(user_id, None)

    if data == b"main_menu":
        me = await bot.get_me()
        bot_username = me.username or "bot"
        welcome_txt = (
            f"مرحباً بك في بوت [Pablo](https://t.me/{bot_username})\n\n"
            "أزرار التحكم بالأسفل 👇:"
        )
        await event.edit(welcome_txt, buttons=main_menu_keyboard(user_id), link_preview=False)

    elif data == b"source_features_menu":
        await event.edit("⭐ **مميزات السورس:**\n\nاختر الخاصية التي تريد الاستعلام عنها أو التحكم بها من القائمة أدناه:", buttons=source_features_menu_keyboard())

    elif data == b"feature_youtube_info":
        txt = (
            "🔍 **فكرة بحث اليوتيوب:**\n\n"
            "يتيح لك السورس البحث عن أي أغنية أو مقطع صوتي في يوتيوب وتحميله وإرساله مباشرة من خلال حسابك الشخصي (اليوزر بوت) كملف صوتي يحتوي على الاسم، اسم القناة، المدة، وصورة الغلاف على اليسار.\n\n"
            "**كيف تستخدمها؟**\n"
            "• اكتب في أي محادثة أو قروب: `بحث [اسم الأغنية أو المطلب]`.\n"
            "• سيقوم الحساب بحذف رسالتك، إرسال رسالة جاري البحث، ثم جلب الملف الصوتي وإرساله فوراً وبدون أي أزرار أو معرفات."
        )
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"feature_pin_info":
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
        await event.edit("🎟️ **إدخال رمز التفعيل:**\n\nيرجى إرسال رمز التفعيل الخاص بك الآن:", buttons=[[Button.inline("🔙 رجوع", b"main_menu")]])

    elif data == b"sub_info":
        if user_id in ADMIN_IDS:
            txt = "📊 **حالة الاشتراك:** فعال بنمط مسؤول 👑 (غير محدود)"
        else:
            exp = users_db[user_id]["expires_at"]
            if time.time() < exp:
                rem_days = int((exp - time.time()) / 86400)
                txt = f"📊 **حالة الاشتراك:** مفعل ✅\n⏱️ **المتبقي:** {rem_days} يوم"
            else:
                txt = "📊 **حالة الاشتراك:** غير مفعل ❌\nيرجى تفعيل الاشتراك عبر الزر المخصص في الرئيسية."
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"main_menu")]])

    elif data == b"login_start":
        if not is_subscribed(user_id):
            await event.answer("⚠️ يرجى تفعيل الاشتراك أولاً لتتمكن من تسجيل الدخول.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_phone"}
        await event.edit(
            "🔑 **تسجيل الدخول / ربط الحساب:**\n\n"
            "يرجى إرسال رقم الهاتف كاملاً مع رمز الدولة (مثال: `+966500000000`):",
            buttons=[[Button.inline("🔙 رجوع", b"main_menu")]]
        )

    elif data == b"bot_responses_menu":
        if user_id not in ADMIN_IDS:
            await event.answer("⚠️ هذه القائمة مخصصة للمسؤولين فقط.", alert=True)
            return
        await event.edit("🤖 **قائمة ردود البوت المخصصة:**\n\nتتيح لك هذه القائمة إضافة كلمات وردود خاصة بها:", buttons=bot_responses_menu_keyboard())

    elif data == b"add_bot_response":
        if user_id not in ADMIN_IDS:
            await event.answer("⚠️ هذه القائمة مخصصة للمسؤولين فقط.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_bot_response"}
        await event.edit("➕ أرسل الكلمة أو العبارة والرد الخاص بها لتضاف إلى ردود البوت المخصصة:\n\n(يمكنك إرسال عدة كلمات متتالية، وعند الانتهاء اضغط رجوع):", buttons=[[Button.inline("🔙 رجوع", b"bot_responses_menu")]])

    elif data == b"show_bot_responses":
        if user_id not in ADMIN_IDS:
            await event.answer("⚠️ هذه القائمة مخصصة للمسؤولين فقط.", alert=True)
            return
        phrases = users_db[user_id].get("bot_responses", [])
        txt = "📋 **قائمة ردود البوت الخاصة بك:**\n\n" + ("\n".join([f"• `{p}`" for p in phrases]) if phrases else "لا توجد كلمات أو ردود مضافة.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"bot_responses_menu")]])

    elif data == b"del_bot_response_item_start":
        if user_id not in ADMIN_IDS:
            await event.answer("⚠️ هذه القائمة مخصصة للمسؤولين فقط.", alert=True)
            return
        phrases = users_db[user_id].get("bot_responses", [])
        if not phrases:
            await event.answer("⚠️ لا توجد كلمات مضافة لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_bot_response_item"}
        txt = "📋 **أرسل الكلمة أو الرد الذي تريد حذفه الآن:**\n\n"
        for p in phrases:
            txt += f"• `{p}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"bot_responses_menu")]])

    elif data == b"clear_bot_responses":
        if user_id not in ADMIN_IDS:
            await event.answer("⚠️ هذه القائمة مخصصة للمسؤولين فقط.", alert=True)
            return
        users_db[user_id]["bot_responses"] = []
        save_data()
        await event.answer("⚠️ تم مسح جميع ردود البوت المخصصة بنجاح.", alert=True)
        await event.edit("🤖 **قائمة ردود البوت المخصصة:**", buttons=bot_responses_menu_keyboard())

    elif data == b"voice_menu":
        await event.edit("🎙️ **قائمة التحكم بالصوتيات:**\n\nاختر من القائمة أدناه:", buttons=voice_menu_keyboard(user_id))

    elif data == b"tog_voice_cmd":
        users_db[user_id]["del_voice_cmd"] = not users_db[user_id].get("del_voice_cmd", True)
        save_data()
        await event.edit("🎙️ **قائمة التحكم بالصوتيات:**\n\nاختر من القائمة أدناه:", buttons=voice_menu_keyboard(user_id))

    elif data == b"add_voice":
        next_num = get_next_voice_number(user_id)
        user_states[user_id] = {"step": "awaiting_voice"}
        await event.edit(
            f"➕ **إضافة صوتية جديدة:**\n\n"
            f"الصوتية القادمة ستأخذ رقم تلقائي: `{next_num}`\n\n"
            f"الرجاء إرسال **الملف الصوتي** أو **البصمة** الآن لتخزينها:",
            buttons=[[Button.inline("🔙 رجوع", b"voice_menu")]]
        )

    elif data == b"show_voice":
        v_dict = users_db[user_id].get("voices", {})
        if not v_dict:
            txt = "📂 لا توجد صوتيات مضافة حالياً."
        else:
            txt = "🎙️ **قائمة الصوتيات المسجلة لدي:**\n\n"
            for k in sorted(v_dict.keys(), key=lambda x: int(x) if x.isdigit() else x):
                txt += f"• صوتية رقم `{k}` ⬅️ للاستخدام اكتب: `صوتيه {k}`\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"voice_menu")]])

    elif data == b"del_voice_item":
        v_dict = users_db[user_id].get("voices", {})
        if not v_dict:
            await event.answer("⚠️ لا توجد صوتيات لحذفها.", alert=True)
            return
        user_states[user_id] = {"step": "awaiting_del_voice_num"}
        await event.edit("❌ أرسل **رقم الصوتية** التي تريد حذفها (مثال: `1`):", buttons=[[Button.inline("🔙 رجوع", b"voice_menu")]])

    elif data == b"clear_voice":
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
        txt = (
            "ℹ️ **طريقة المسح بالعدد المحدد:**\n\n"
            "يتيح لك هذا الأمر مسح عدد معين من آخر رسائلك في القروب أو المحادثات الخاصة.\n\n"
            "**كيف تستخدمه؟**\n"
            "• اكتب في المحادثة: `مسح 20` وسيقوم البوت بمسح آخر 20 رسالة أرسلتها أنت فقط.\n"
            "• إذا كتبت `مسح` فقط بدون تحديد رقم، سيمسح تلقائياً آخر 20 رسالة لك."
        )
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"source_features_menu")]])

    elif data == b"info_purge_all":
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
        await event.edit("🔇 **قائمة الكتم الشامل:**\nيرجى تحديد الخيار المطلوب:", buttons=mute_menu_keyboard(user_id))

    elif data == b"tog_mute_cmd":
        users_db[user_id]["del_mute_cmd"] = not users_db[user_id].get("del_mute_cmd", True)
        save_data()
        await event.edit("🔇 **قائمة الكتم الشامل:**", buttons=mute_menu_keyboard(user_id))

    elif data == b"tog_unmute_cmd":
        users_db[user_id]["del_unmute_cmd"] = not users_db[user_id].get("del_unmute_cmd", True)
        save_data()
        await event.edit("🔇 **قائمة الكتم الشامل:**", buttons=mute_menu_keyboard(user_id))

    elif data == b"add_mute_cmd":
        user_states[user_id] = {"step": "awaiting_mute_cmd"}
        await event.edit("🔇 أرسل نص أمر الكتم الجديد (يمكنك إرسال عدة أوامر، وعند الانتهاء اضغط رجوع):", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"show_mute_cmds":
        cmds = users_db[user_id]["mute_cmds"]
        txt = "📜 **أوامر الكتم الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"del_mute_cmd_sub":
        buttons = [
            [Button.inline("🗑️ حذف أمر كتم محدد", b"del_mute_cmd_item_start")],
            [Button.inline("⚠️ حذف شامل (جميع أوامر الكتم)", b"clear_mute_cmd")],
            [Button.inline("🔙 رجوع", b"mute_menu")]
        ]
        await event.edit("❌ **خيارات حذف أوامر الكتم:**", buttons=buttons)

    elif data == b"del_mute_cmd_item_start":
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
        users_db[user_id]["mute_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر الكتم.", alert=True)
        await event.edit("🔇 **قائمة الكتم:**", buttons=mute_menu_keyboard(user_id))

    elif data == b"add_unmute_cmd":
        user_states[user_id] = {"step": "awaiting_unmute_cmd"}
        await event.edit("🔊 أرسل نص أمر إلغاء الكتم الجديد (يمكنك إرسال عدة أوامر، وعند الانتهاء اضغط رجوع):", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"show_unmute_cmds":
        cmds = users_db[user_id]["unmute_cmds"]
        txt = "📜 **أوامر إلغاء الكتم الحالية:**\n\n" + "\n".join([f"• `{c}`" for c in cmds])
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"del_unmute_cmd_sub":
        buttons = [
            [Button.inline("🗑️ حذف أمر إلغاء كتم محدد", b"del_unmute_cmd_item_start")],
            [Button.inline("⚠️ حذف شامل (جميع أوامر إلغاء الكتم)", b"clear_unmute_cmd")],
            [Button.inline("🔙 رجوع", b"mute_menu")]
        ]
        await event.edit("❌ **خيارات حذف أوامر إلغاء الكتم:**", buttons=buttons)

    elif data == b"del_unmute_cmd_item_start":
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
        users_db[user_id]["unmute_cmds"] = []
        save_data()
        await event.answer("❌ تم حذف جميع أوامر إلغاء الكتم.", alert=True)
        await event.edit("🔇 **قائمة الكتم:**", buttons=mute_menu_keyboard(user_id))

    elif data == b"show_muted_users":
        m_list = users_db[user_id]["muted_users"]
        txt = "👥 **قائمة المعرفات المكتومة حالياً:**\n\n" + ("\n".join([f"• `{u}`" for u in m_list]) if m_list else "لا يوجد مستخدمون مكتومون.")
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif data == b"del_muted_users_sub":
        buttons = [
            [Button.inline("🗑️ إلغاء كتم مستخدم محدد", b"del_muted_user_item_start")],
            [Button.inline("⚠️ مسح جميع المكتومين", b"clear_muted_users")],
            [Button.inline("🔙 رجوع", b"mute_menu")]
        ]
        await event.edit("❌ **خيارات حذف المكتومين:**", buttons=buttons)

    elif data == b"del_muted_user_item_start":
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

    elif data == b"list_admins" and user_id in ADMIN_IDS:
        await event.edit("جاري تحميل قائمة المسؤولين...")
        txt = "👥 **قائمة المسؤولين في النظام:**\n\n"
        for idx, aid in enumerate(ADMIN_IDS, 1):
            user_info_str = await format_user_details(aid)
            txt += f"**{idx}.**\n{user_info_str}\n\n"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]], link_preview=False)

    elif data == b"list_users" and user_id in ADMIN_IDS:
        await event.edit("جاري تحميل قائمة المستخدمين...")
        if not users_db:
            await event.edit("📋 لا يوجد مستخدمين مسجلين حالياً في النظام.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            return

        txt = "📋 **قائمة المستخدمين والمشتركين في النظام:**\n\n"
        all_uids = list(users_db.keys())
        display_uids = all_uids[:30]

        for idx, uid in enumerate(display_uids, 1):
            user_info_str = await format_user_details(uid)
            exp = users_db[uid].get("expires_at", 0)
            
            if uid in ADMIN_IDS:
                status_str = "👑 مسؤول (اشتراك مفتوح)"
            elif time.time() < exp:
                rem_days = int((exp - time.time()) / 86400)
                status_str = f"✅ مفعل (متبقي {rem_days} يوم)"
            else:
                status_str = "❌ غير مفعل / منتهي"

            txt += f"**{idx}.** {user_info_str}\n  • الحالة: {status_str}\n\n"

        if len(all_uids) > 30:
            txt += f"\n⚠️ يتم عرض 30 مستخدم من أصل إجمالي `{len(all_uids)}` مستخدم."

        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]], link_preview=False)

    elif data == b"revoke_user_start" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_revoke_user_id"}
        await event.edit("❌ **إلغاء اشتراك / حذف مستخدم:**\n\nأرسل المعرف الرقمي (ID) للمستخدم المراد إلغاء اشتراكه وتصفيره:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"add_admin_start" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_new_admin_id"}
        await event.edit("➕ **إضافة مسؤول جديد:**\n\nأرسل المعرف الرقمي (ID) لشخص المراد ترقيته:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"delete_admin_start" and user_id in ADMIN_IDS:
        user_states[user_id] = {"step": "awaiting_delete_admin_id"}
        await event.edit("❌ **حذف مسؤول:**\n\nأرسل المعرف الرقمي (ID) للمسؤول المراد إزالته:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif data == b"admin_stats" and user_id in ADMIN_IDS:
        txt = f"📊 **إحصائيات النظام:**\n\n• إجمالي المسجلين: {len(users_db)}\n• عدد المسؤولين: {len(ADMIN_IDS)}\n• الحسابات المتصلة حالياً: {len(user_clients)}\n• المهام الشغالة حالياً: {len(running_tasks)}"
        await event.edit(txt, buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

# ==================== Text & Media Input Handlers ====================
@bot.on(events.NewMessage)
async def message_input_handler(event):
    global default_tastir, default_fardiyyat, default_reply
    if not event.is_private or (event.text and event.text.startswith("/")):
        return

    user_id = event.sender_id
    state = user_states.get(user_id)
    if not state:
        return

    step = state.get("step")
    text = event.raw_text.strip() if event.raw_text else ""

    if step == "awaiting_add_def_tastir" and user_id in ADMIN_IDS:
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

    elif step == "awaiting_bot_response":
        if user_id not in ADMIN_IDS:
            return
        users_db[user_id]["bot_responses"].append(text)
        save_data()
        await event.respond("✅ تم إضافة الكلمة والرد الخاص بها إلى قائمة (ردود البوت) بنجاح.\n\nيمكنك إرسال كلمة أخرى، أو اضغط زر الرجوع للإنهاء:", buttons=[[Button.inline("🔙 رجوع", b"bot_responses_menu")]])
        return

    elif step == "awaiting_del_bot_response_item":
        if user_id not in ADMIN_IDS:
            return
        if text in users_db[user_id]["bot_responses"]:
            users_db[user_id]["bot_responses"].remove(text)
            save_data()
            await event.respond(f"✅ تم حذف الكلمة/الرد: `{text}` بنجاح.\n\nأرسل كلمة أخرى لحذفها، أو اضغط زر الرجوع للإنهاء:", buttons=[[Button.inline("🔙 رجوع", b"bot_responses_menu")]])
        else:
            await event.respond("❌ الكلمة غير موجودة بالقائمة، تأكد منها ثم أرسلها مجدداً أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"bot_responses_menu")]])
        return

    elif step == "awaiting_code_input":
        success, days = await apply_activation_code(user_id, text, event)
        user_states.pop(user_id, None)
        if success:
            await event.respond(f"✅ تم تفعيل الاشتراك بنجاح لمدة {days} يوم.")
        else:
            await event.respond("❌ رمز التفعيل غير صالح أو تم استخدامه سابقاً.")

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

    elif step == "awaiting_del_muted_user_item":
        try:
            uid_to_unmute = int(text)
            if uid_to_unmute in users_db[user_id]["muted_users"]:
                users_db[user_id]["muted_users"].remove(uid_to_unmute)
                save_data()
                await event.respond(f"✅ تم إزالة كتم المستخدم `{uid_to_unmute}` بنجاح.\n\nأرسل آيدي آخر أو اضغط رجوع:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])
            else:
                await event.respond("❌ الآيدي غير موجود في قائمة المكتومين:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])
        except ValueError:
            await event.respond("❌ يرجى إرسال آيدي رقمي صحيح:", buttons=[[Button.inline("🔙 رجوع", b"mute_menu")]])

    elif step == "awaiting_broadcast_msg":
        if user_id not in ADMIN_IDS:
            return
        user_states.pop(user_id, None)
        msg_to_send = event.raw_text
        sent_count = 0
        fail_count = 0
        
        status_msg = await event.respond("⏳ جاري بدء الإذاعة لجميع المستخدمين...")
        for uid in list(users_db.keys()):
            try:
                await bot.send_message(uid, f"📢 **إشعار هام من الإدارة:**\n\n{msg_to_send}")
                sent_count += 1
                await asyncio.sleep(0.1)
            except Exception:
                fail_count += 1
                
        await status_msg.edit(f"✅ **تمت الإذاعة بنجاح!**\n\n• تم الإرسال إلى: `{sent_count}` مستخدم\n• فشل الإرسال إلى: `{fail_count}` مستخدم", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif step == "awaiting_code_days":
        if user_id not in ADMIN_IDS:
            return
        try:
            days = int(text)
            code = secrets.token_hex(4)
            activation_codes[code] = days
            save_data()
            user_states.pop(user_id, None)
            await event.respond(
                f"✅ **تم توليد كود الاشتراك بنجاح!**\n\n"
                f"• الكود: `{code}`\n"
                f"• المدة: `{days}` يوم\n\n"
                f"رابط التفعيل المباشر:\n`https://t.me/{(await bot.get_me()).username}?start={code}`",
                buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]]
            )
        except ValueError:
            await event.respond("❌ يرجى إرسال رقم صحيح يمثل عدد الأيام:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif step == "awaiting_revoke_user_id":
        if user_id not in ADMIN_IDS:
            return
        user_states.pop(user_id, None)
        try:
            target_uid = int(text)
            if target_uid in users_db:
                users_db[target_uid]["expires_at"] = 0
                save_data()
                await event.respond(f"✅ تم إلغاء اشتراك المستخدم `{target_uid}` وتصفير مدته بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            else:
                await event.respond("❌ المستخدم غير مسجل في قاعدة البيانات.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        except ValueError:
            await event.respond("❌ يرجى إرسال آيدي رقمي صحيح:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif step == "awaiting_new_admin_id":
        if user_id not in ADMIN_IDS:
            return
        user_states.pop(user_id, None)
        try:
            new_admin = int(text)
            if new_admin not in ADMIN_IDS:
                ADMIN_IDS.append(new_admin)
                init_user_db(new_admin)
                users_db[new_admin]["expires_at"] = time.time() + (100 * 365 * 86400)
                save_data()
                await event.respond(f"✅ تم ترقية المستخدم `{new_admin}` إلى مسؤول بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            else:
                await event.respond("⚠️ المستخدم مسؤول بالفعل.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        except ValueError:
            await event.respond("❌ يرجى إرسال آيدي رقمي صحيح:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

    elif step == "awaiting_delete_admin_id":
        if user_id not in ADMIN_IDS:
            return
        user_states.pop(user_id, None)
        try:
            del_admin = int(text)
            if del_admin in ADMIN_IDS:
                if len(ADMIN_IDS) <= 1:
                    await event.respond("⚠️ لا يمكنك حذف المسؤول الوحيد للنظام.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
                    return
                ADMIN_IDS.remove(del_admin)
                save_data()
                await event.respond(f"✅ تم إزالة المستخدم `{del_admin}` من قائمة المسؤولين بنجاح.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
            else:
                await event.respond("⚠️ المستخدم ليس مسؤولاً.", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])
        except ValueError:
            await event.respond("❌ يرجى إرسال آيدي رقمي صحيح:", buttons=[[Button.inline("🔙 رجوع", b"admin_menu")]])

# ==================== Initialization & Run ====================
async def main():
    print("Starting bot...")
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot is running...")
    
    for uid, uinfo in list(users_db.items()):
        session_path = f"{SESSIONS_DIR}/user_{uid}"
        if os.path.exists(f"{session_path}.session"):
            try:
                client = TelegramClient(session_path, API_ID, API_HASH)
                await client.connect()
                if await client.is_user_authorized():
                    user_clients[uid] = client
                    await register_userbot_events(client, uid)
                    print(f"Restored session for user {uid}")
            except Exception as e:
                print(f"Failed to restore session for {uid}: {e}")

    await bot.disconnected

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
