# generate_session.py
# Ishlatish: API_ID va API_HASH muhit o'zgaruvchilarini o'rnatgach:
# python3 generate_session.py
# Skript sizni Pyrogram orqali Telegramga ulanganda sessiya stringini chiqaradi.
import os
from pyrogram import Client

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")

if not API_ID or not API_HASH:
    print("Iltimos, API_ID va API_HASH muhit o'zgaruvchilarini to'ldiring.")
    print("Misol (bash): export API_ID=21279015; export API_HASH='4c25a868bfd3be62a606bb7e0e82870b'")
    exit(1)

print("Pyrogram orqali sessiya yaratilmoqda. Telefon raqamingiz yoki Telegram orqali kelgan kodni kiriting...")
with Client("temp_session", api_id=API_ID, api_hash=API_HASH) as app:
    session = app.export_session_string()
    print("\n--- SAQLANG: STRING_SESSION quyida ---\n")
    print(session)
    print("\n--- END ---\n")
    print("STRING_SESSION ni PythonAnywhere muhit o'zgaruvchilariga (env) qo'ying.")