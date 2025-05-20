import telebot
from telebot import types
import json
from datetime import datetime, timedelta
import os
import threading

# Bot token and owner ID (replace OWNER_ID with your Telegram user ID)
TOKEN = "7939685234:AAEQkhe191nzbeqRSlVvHj0rxXV7B9lMgGo"
OWNER_ID = 6473717870  # replace with your Telegram ID

# Database file path
DB_FILE = 'db.txt'
db_lock = threading.Lock()

def load_data():
    """Load data from the database file (create default structure if missing)."""
    with db_lock:
        if not os.path.exists(DB_FILE):
            data = {"users": [], "keys": [], "gateways": []}
            with open(DB_FILE, 'w') as f:
                json.dump(data, f)
            return data
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            # Initialize if file is empty or corrupt
            data = {"users": [], "keys": [], "gateways": []}
    # Check expiry after loading (outside lock to avoid deadlocks)
    check_expiry(data)
    return data

def save_data(data):
    """Save the in-memory data back to the file."""
    with db_lock:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4, default=str)

def find_user(data, user_id):
    """Return the user dict for the given user_id, or None if not found."""
    for user in data["users"]:
        if user["user_id"] == user_id:
            return user
    return None

def register_user(data, user_id):
    """Add a new user with default settings if not already present."""
    if find_user(data, user_id) is None:
        user = {
            "user_id": user_id,
            "role": "free",
            "credits": 0,
            "expiry": None  # no expiry by default
        }
        data["users"].append(user)
        save_data(data)
        return True
    return False

def set_user_role(data, user_id, role, expiry_days=None):
    """Set a user's role, optionally with an expiry from now."""
    user = find_user(data, user_id)
    if user:
        user["role"] = role
        if expiry_days:
            expiry_date = datetime.now() + timedelta(days=expiry_days)
            user["expiry"] = expiry_date.strftime("%Y-%m-%d")
        else:
            user["expiry"] = None
        save_data(data)
        return True
    return False

def add_credits(data, user_id, amount):
    """Add credits to a user."""
    user = find_user(data, user_id)
    if user:
        user["credits"] += amount
        save_data(data)
        return True
    return False

def subtract_credits(data, user_id, amount):
    """Subtract credits from a user (if they have enough)."""
    user = find_user(data, user_id)
    if user and user["credits"] >= amount:
        user["credits"] -= amount
        save_data(data)
        return True
    return False

def generate_key_pair():
    """Generate a random SK/PK key pair (16-character alphanumeric)."""
    import random, string
    sk = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
    pk = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
    return sk, pk

def add_key(data, sk, pk, expiry_days=None):
    """Add a new key entry with SK and PK. Optionally set expiry days."""
    key = {
        "sk": sk,
        "pk": pk,
        "claimed_by": None,
        "status": "active",
        "expiry": None
    }
    if expiry_days:
        expiry_date = datetime.now() + timedelta(days=expiry_days)
        key["expiry"] = expiry_date.strftime("%Y-%m-%d")
    data["keys"].append(key)
    save_data(data)
    return key

def find_key_by_pk(data, pk):
    """Find a key dict by its public key (pk)."""
    for key in data["keys"]:
        if key["pk"] == pk:
            return key
    return None

def claim_key(data, user_id, pk):
    """Claim a key (by public key) for a user."""
    key = find_key_by_pk(data, pk)
    user = find_user(data, user_id)
    if key and user:
        if key["status"] != "active":
            return False, "Key is not active."
        if key["claimed_by"] is not None:
            return False, "Key has already been claimed."
        key["claimed_by"] = user_id
        key["status"] = "claimed"
        save_data(data)
        return True, f"Key {pk} has been claimed by user {user_id}."
    return False, "Key not found or user invalid."

def add_gateway(data, name, category):
    """Add a new gateway entry. Gateways have an auto-incremented ID."""
    gateway_id = len(data["gateways"]) + 1
    gateway = {
        "id": gateway_id,
        "name": name,
        "category": category,
        "status": "active"
    }
    data["gateways"].append(gateway)
    save_data(data)
    return gateway

def find_gateway(data, gateway_id):
    """Return the gateway dict with the given ID."""
    for gw in data["gateways"]:
        if gw["id"] == gateway_id:
            return gw
    return None

def set_gateway_status(data, gateway_id, status):
    """Set a gateway's status (e.g., active/inactive)."""
    gw = find_gateway(data, gateway_id)
    if gw:
        gw["status"] = status
        save_data(data)
        return True
    return False

def list_gateways(data, category=None):
    """List all gateways, or only those in a given category."""
    if category:
        return [gw for gw in data["gateways"] if gw["category"].lower() == category.lower()]
    return data["gateways"]

def check_expiry(data):
    """Check for expired users or keys and update their status."""
    now = datetime.now()
    changed = False
    # Demote expired authorized users to free
    for user in data["users"]:
        if user["role"] == "authorized" and user["expiry"]:
            expiry_date = datetime.fromisoformat(user["expiry"])
            if now > expiry_date:
                user["role"] = "free"
                user["expiry"] = None
                changed = True
    # Expire active keys past their expiry date
    for key in data["keys"]:
        if key["status"] == "active" and key["expiry"]:
            expiry_date = datetime.fromisoformat(key["expiry"])
            if now > expiry_date:
                key["status"] = "expired"
                changed = True
    if changed:
        save_data(data)

# Initialize the bot (threaded=False ensures handlers run sequentially)
bot = telebot.TeleBot(TOKEN, threaded=False)

# ---------------- Command Handlers ----------------

@bot.message_handler(commands=['start'])
def cmd_start(message):
    data = load_data()
    user_id = message.from_user.id
    # Register the user if not already present
    if register_user(data, user_id):
        bot.reply_to(message, "Welcome! You have been registered as a free user.")
    else:
        bot.reply_to(message, "Welcome back!")

@bot.message_handler(commands=['profile'])
def cmd_profile(message):
    data = load_data()
    user_id = message.from_user.id
    user = find_user(data, user_id)
    if user:
        text = f"User ID: {user['user_id']}\nRole: {user['role']}\nCredits: {user['credits']}"
        if user['expiry']:
            text += f"\nExpiry Date: {user['expiry']}"
        bot.reply_to(message, text)
    else:
        bot.reply_to(message, "You are not registered. Send /start to register.")

@bot.message_handler(commands=['setrole'])
def cmd_setrole(message):
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /setrole <user_id> <role> [days]")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, "Invalid user ID.")
        return
    role = parts[2]
    days = int(parts[3]) if len(parts) > 3 else None
    data = load_data()
    # Only the owner can set roles
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "You are not authorized to perform this action.")
        return
    if set_user_role(data, target_id, role, days):
        bot.reply_to(message, f"User {target_id} role set to {role}.")
    else:
        bot.reply_to(message, f"User {target_id} not found.")

@bot.message_handler(commands=['addcredit'])
def cmd_addcredit(message):
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "Usage: /addcredit <user_id> <amount>")
        return
    try:
        target_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        bot.reply_to(message, "Invalid user ID or amount.")
        return
    data = load_data()
    # Only owner can add credits
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "You are not authorized to add credits.")
        return
    if add_credits(data, target_id, amount):
        bot.reply_to(message, f"Added {amount} credits to user {target_id}.")
    else:
        bot.reply_to(message, f"User {target_id} not found.")

@bot.message_handler(commands=['generatekey'])
def cmd_generate_key(message):
    data = load_data()
    user_id = message.from_user.id
    user = find_user(data, user_id)
    # Only owner or authorized users can generate keys
    if user_id != OWNER_ID and (not user or user["role"] != "authorized"):
        bot.reply_to(message, "You do not have permission to generate keys.")
        return
    sk, pk = generate_key_pair()
    # (Optional: parse an expiry days parameter from message if needed)
    expiry_days = None
    key = add_key(data, sk, pk, expiry_days)
    bot.reply_to(message, f"New key generated:\nSK: {sk}\nPK: {pk}")

@bot.message_handler(commands=['keys'])
def cmd_keys(message):
    data = load_data()
    user_id = message.from_user.id
    user = find_user(data, user_id)
    if not user:
        bot.reply_to(message, "You are not registered. Use /start.")
        return
    parts = message.text.split()
    if len(parts) == 1 or parts[1].lower() == 'all':
        # Only owner or authorized can view all keys
        if user_id != OWNER_ID and user['role'] != 'authorized':
            bot.reply_to(message, "You don't have permission to view all keys.")
            return
        text = "All keys:\n"
        for key in data["keys"]:
            text += f"PK: {key['pk']} (Status: {key['status']})\n"
        bot.reply_to(message, text)
    elif parts[1].lower() == 'mine':
        text = "Your keys:\n"
        for key in data["keys"]:
            if key["claimed_by"] == user_id:
                text += f"PK: {key['pk']} (Status: {key['status']})\n"
        bot.reply_to(message, text)
    else:
        bot.reply_to(message, "Usage: /keys [all|mine]")

@bot.message_handler(commands=['claim'])
def cmd_claim(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /claim <public_key>")
        return
    pk = parts[1]
    data = load_data()
    success, msg = claim_key(data, message.from_user.id, pk)
    bot.reply_to(message, msg)

@bot.message_handler(commands=['addgateway'])
def cmd_add_gateway(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /addgateway <name> <category>")
        return
    name = parts[1]
    category = parts[2]
    data = load_data()
    user_id = message.from_user.id
    user = find_user(data, user_id)
    # Only owner or authorized can add a gateway
    if user_id != OWNER_ID and (not user or user["role"] != "authorized"):
        bot.reply_to(message, "You do not have permission to add gateways.")
        return
    gateway = add_gateway(data, name, category)
    bot.reply_to(message, f"Gateway added with ID {gateway['id']}.")

@bot.message_handler(commands=['gateways'])
def cmd_list_gateways(message):
    parts = message.text.split()
    category = parts[1] if len(parts) > 1 else None
    data = load_data()
    gateways = list_gateways(data, category)
    if not gateways:
        bot.reply_to(message, "No gateways found.")
        return
    text = "Gateways:\n"
    for gw in gateways:
        text += f"ID: {gw['id']} Name: {gw['name']} Category: {gw['category']} Status: {gw['status']}\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=['setgatewaystatus'])
def cmd_set_gateway_status(message):
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "Usage: /setgatewaystatus <id> <status>")
        return
    try:
        gateway_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, "Invalid gateway ID.")
        return
    status = parts[2]
    data = load_data()
    # Only owner can change gateway status
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "You are not authorized to perform this action.")
        return
    if set_gateway_status(data, gateway_id, status):
        bot.reply_to(message, f"Gateway {gateway_id} status updated to {status}.")
    else:
        bot.reply_to(message, f"Gateway {gateway_id} not found.")

print("Bot is polling...")
bot.infinity_polling()
