# main.py
# Pyrogram userbot: profil bio countdown + shablonlar + inline keyboard orqali shablon tanlash
import os
import asyncio
import logging
import sqlite3
from datetime import datetime
from dateutil import parser
from tzlocal import get_localzone

from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- Konfiguratsiya (env dan o'qiladi) ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
STRING_SESSION = os.environ.get("STRING_SESSION", "")
APP_NAME = os.environ.get("APP_NAME", "profile_countdown_userbot")
UPDATE_INTERVAL = float(os.environ.get("UPDATE_INTERVAL", "1"))  # soniya; default 1
DB_PATH = os.environ.get("DB_PATH", "data.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# --- DB init ---
def init_db(path=DB_PATH):
    conn = sqlite3.connect(path, check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS templates (command TEXT PRIMARY KEY, content TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn

def parse_datetime(text: str):
    dt = parser.parse(text)
    if dt.tzinfo is None:
        local_tz = get_localzone()
        dt = dt.replace(tzinfo=local_tz)
    return dt

def seconds_to_dhms(sec: int):
    if sec < 0:
        sec = 0
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return days, hours, minutes, seconds

class ProfileCountdownUserbot:
    def __init__(self):
        if not API_ID or not API_HASH or not STRING_SESSION:
            log.error("API_ID, API_HASH yoki STRING_SESSION muhit o'zgaruvchilari to'ldirilmagan.")
            raise SystemExit("Iltimos muhit o'zgaruvchilarini to'ldiring.")
        self.app = Client(APP_NAME, api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)
        self.db = init_db()
        self._countdown_task = None
        self.me = None

    # DB yordamchi
    def set_setting(self, key, value):
        c = self.db.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        self.db.commit()

    def get_setting(self, key):
        c = self.db.cursor()
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        r = c.fetchone()
        return r[0] if r else None

    def del_setting(self, key):
        c = self.db.cursor()
        c.execute("DELETE FROM settings WHERE key = ?", (key,))
        self.db.commit()

    def save_template(self, command, content):
        c = self.db.cursor()
        c.execute("INSERT OR REPLACE INTO templates(command, content) VALUES (?, ?)", (command, content))
        self.db.commit()

    def delete_template(self, command):
        c = self.db.cursor()
        c.execute("DELETE FROM templates WHERE command = ?", (command,))
        self.db.commit()

    def list_templates(self):
        c = self.db.cursor()
        c.execute("SELECT command, content FROM templates ORDER BY command")
        return c.fetchall()

    def get_template(self, command):
        c = self.db.cursor()
        c.execute("SELECT content FROM templates WHERE command = ?", (command,))
        r = c.fetchone()
        return r[0] if r else None

    # Profil bio yangilash loop
    async def profile_countdown_loop(self):
        log.info("Profile countdown task started. INTERVAL=%s", UPDATE_INTERVAL)
        client = self.app
        while True:
            target_iso = self.get_setting("countdown_target")
            bio_prefix = self.get_setting("bio_prefix") or ""
            if target_iso:
                try:
                    target_dt = parser.isoparse(target_iso)
                except Exception:
                    try:
                        target_dt = parse_datetime(target_iso)
                    except Exception:
                        log.exception("Saqlangan countdown_targetni pars qilib bo'lmadi, o'chirildi.")
                        self.del_setting("countdown_target")
                        target_dt = None

                if target_dt:
                    now = datetime.now(target_dt.tzinfo) if target_dt.tzinfo else datetime.now()
                    diff = target_dt - now
                    total_seconds = int(diff.total_seconds())
                    if total_seconds <= 0:
                        bio_text = f"{bio_prefix} Tadbir yakunlandi ({target_dt.strftime('%Y-%m-%d %H:%M:%S')})."
                    else:
                        d, h, m, s = seconds_to_dhms(total_seconds)
                        bio_text = f"{bio_prefix} {d} kun {h} soat {m} minut {s} soniya qoldi. ({target_dt.strftime('%Y-%m-%d %H:%M:%S %Z')})"

                    try:
                        await client.update_profile(bio=bio_text)
                    except FloodWait as e:
                        log.warning("FloodWait: kutilyapti %s soniya", e.x)
                        await asyncio.sleep(e.x + 1)
                    except RPCError:
                        log.exception("RPCError profil yangilashda; qisqa kutish bilan davom etiladi.")
                        await asyncio.sleep(max(1.0, UPDATE_INTERVAL))
                    except Exception:
                        log.exception("Profil update xatosi:")
                        await asyncio.sleep(max(1.0, UPDATE_INTERVAL))
                else:
                    await asyncio.sleep(max(1.0, UPDATE_INTERVAL))
            else:
                await asyncio.sleep(max(1.0, UPDATE_INTERVAL))
            await asyncio.sleep(UPDATE_INTERVAL)

    # Handlerlarni ro'yxatga olish (self.me olingach chaqiriladi)
    def register_handlers(self):
        app = self.app

        @app.on_message(filters.me & filters.text)
        async def on_own_message(client, message):
            text = (message.text or "").strip()
            # .sozlash (interaktiv): .sozlash yozsangiz, keyin .komanda va matnni ketma-ket yuborasiz
            if text.startswith(".sozlash"):
                sent = await message.reply("Shablon buyruqini kiriting (masalan .salom). 60 soniya ichida yuboring:")
                try:
                    async for m in client.listen(message.chat.id, timeout=60):
                        if m.from_user and m.from_user.is_self and (m.text or ""):
                            trigger = (m.text or "").strip()
                            if not trigger.startswith("."):
                                await m.reply("Buyruq nuqtadan boshlanishi kerak (masalan .salom). Boshidan .sozlash qiling.")
                                break
                            await m.reply("Shablon matnini yuboring (masalan: Salom, bugun {date}):")
                            try:
                                async for m2 in client.listen(message.chat.id, timeout=180):
                                    if m2.from_user and m2.from_user.is_self and (m2.text or ""):
                                        template_text = m2.text
                                        self.save_template(trigger, template_text)
                                        await m2.reply(f"Shablon saqlandi: `{trigger}` → {template_text}")
                                        break
                                else:
                                    await message.reply("Vaqt tugadi: shablon matni kelmadi.")
                            except Exception:
                                await message.reply("Shablon matnini olishda xato yuz berdi.")
                            break
                    else:
                        await sent.reply_text("Vaqt tugadi: shablon buyruq kelmadi.")
                except Exception:
                    await sent.reply_text("Interaktiv jarayonda xatolik yuz berdi.")
                return

            # inline keyboard bilan shablonlar ro'yxati
            if text.startswith(".matn") or text.startswith(".templates"):
                rows = self.list_templates()
                if not rows:
                    await message.reply("Hozircha shablonlar mavjud emas. .sozlash bilan qo'shing.")
                    return
                # quramiz: har qator 1 ta tugma
                buttons = []
                for cmd, _ in rows:
                    # callback_data cheklovi: 64 bytes; biz oddiy "tmpl:<cmd>"
                    cb = f"tmpl:{cmd}"
                    buttons.append([InlineKeyboardButton(cmd, callback_data=cb)])
                # Qo'sh: bekor qilish
                buttons.append([InlineKeyboardButton("Bekor qilish ❌", callback_data="tmpl:__cancel__")])
                markup = InlineKeyboardMarkup(buttons)
                await message.reply("Shablonlardan birini tanlang:", reply_markup=markup)
                return

            # setcountdown
            if text.startswith(".setcountdown") or text.startswith(".countdown"):
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    await message.reply("Foydalanish: .setcountdown YYYY-MM-DD HH:MM[:SS][ ±TZ]\nMasalan: .setcountdown 2025-12-19 00:00")
                    return
                payload = parts[1].strip()
                try:
                    dt = parse_datetime(payload)
                    self.set_setting("countdown_target", dt.isoformat())
                    await message.reply(f"Countdown belgilandi: {dt.isoformat()}\nProfil bio yangilanadi.")
                except Exception:
                    await message.reply("Sana/vaqt pars qilinmadi. Iltimos `2025-12-19 00:00` formatida yoki timezone bilan yuboring.")
                return

            if text.startswith(".clearcountdown"):
                self.del_setting("countdown_target")
                await message.reply("Countdown o'chirildi. Profil bio o'zgarmaydi.")
                return

            if text.startswith(".setbioprefix"):
                parts = text.split(maxsplit=1)
                pref = parts[1].strip() if len(parts) > 1 else ""
                self.set_setting("bio_prefix", pref)
                await message.reply(f"Bio prefix saqlandi: {pref}")
                return

            if text.startswith(".deltemplate"):
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    await message.reply("Foydalanish: .deltemplate .salom")
                    return
                cmd = parts[1].strip()
                self.delete_template(cmd)
                await message.reply(f"Shablon o'chirildi: {cmd}")
                return

            # oddiy buyruqlar
            if text.startswith(".ping"):
                await message.reply("Pong")
                return

            if text.startswith(".uptime"):
                await message.reply("Userbot ishlayapti.")
                return

            # Agar yozilgan xabar shablon triggeriga to'liq teng bo'lsa, uni o'chirib o'rniga shablonni yuborish
            tmpl = self.get_template(text)
            if tmpl:
                try:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await client.send_message(chat_id=message.chat.id, text=tmpl)
                except Exception:
                    log.exception("Shablonni yuborishda xato")
                return

        # Callback query handler (inline keyboard uchun)
        @app.on_callback_query()
        async def on_callback(client, callback_query):
            data = callback_query.data or ""
            from_user = callback_query.from_user
            # faqat siz (o'zingiz) tugmalarni bosishi mumkin
            if from_user and self.me and from_user.id != self.me.id:
                await callback_query.answer("Bu tugma siz uchun emas.", show_alert=True)
                return
            if not data.startswith("tmpl:"):
                await callback_query.answer()
                return
            key = data.split("tmpl:", 1)[1]
            if key == "__cancel__":
                try:
                    await callback_query.message.edit_text("Bekor qilindi ❌")
                except Exception:
                    pass
                await callback_query.answer("Bekor qilindi.")
                return
            # key shu holatda .salom (nuqtali buyruq)
            content = self.get_template(key)
            if not content:
                await callback_query.answer("Shablon topilmadi.", show_alert=True)
                try:
                    await callback_query.message.edit_text("Shablon topilmadi yoki o'chirilgan.")
                except Exception:
                    pass
                return
            # yuborish: callback qaysi chatda edi — shunday chatga yuboraman
            target_chat_id = callback_query.message.chat.id
            try:
                # optional: o'sha inline msgni o'zgartirib tanlangan shablon nomini ko'rsatish
                try:
                    await callback_query.message.edit_text(f"Tanlandi: {key}")
                except Exception:
                    pass
                await client.send_message(chat_id=target_chat_id, text=content)
                await callback_query.answer("Shablon yuborildi.")
            except Exception:
                log.exception("Callback orqali shablon yuborishda xato")
                await callback_query.answer("Yuborishda xato yuz berdi.", show_alert=True)

    async def start(self):
        await self.app.start()
        self.me = await self.app.get_me()
        log.info("Kirish: %s (%s)", getattr(self.me, "first_name", ""), getattr(self.me, "id", ""))
        self.register_handlers()
        if not self._countdown_task:
            self._countdown_task = asyncio.create_task(self.profile_countdown_loop())
        await idle()

    async def stop(self):
        if self._countdown_task:
            self._countdown_task.cancel()
            try:
                await self._countdown_task
            except asyncio.CancelledError:
                pass
        await self.app.stop()

def main():
    bot = ProfileCountdownUserbot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        log.info("To'xtatilyapti...")
        try:
            asyncio.run(bot.stop())
        except:
            pass

if __name__ == "__main__":
    main()