
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
FORUM_CHANNEL_ID = int(os.getenv("FORUM_CHANNEL_ID"))
SERVER_ID = int(os.getenv("SERVER_ID"))
QUEUE_STATUS_CHANNEL_ID = 1424870061931237406

RULES_MESSAGE_LINKS = {
    "land": "https://discord.com/channels/1338951477934162064/1388566604480118864/1388577715380158627",
    "conquest": "https://discord.com/channels/1338951477934162064/1388566604480118864/1388577787249561620",
    "domination": "https://discord.com/channels/1338951477934162064/1388566604480118864/1388577916094382152",
    "luckydice": "https://discord.com/channels/1338951477934162064/1405069937592111165/1405070003937480716",
}
