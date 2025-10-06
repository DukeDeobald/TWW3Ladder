
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
FORUM_CHANNEL_ID = int(os.getenv("FORUM_CHANNEL_ID"))
SERVER_ID = int(os.getenv("SERVER_ID"))
QUEUE_STATUS_CHANNEL_ID = 1424870061931237406

RULES_MESSAGE_LINKS = {
    "land": "https://discord.com/channels/YOUR_SERVER_ID/YOUR_CHANNEL_ID/YOUR_MESSAGE_ID",
    "conquest": "https://discordapp.com/channels/1402324586984378388/1402324588112904286/1403849596786049036",
    "domination": "https://discord.com/channels/YOUR_SERVER_ID/YOUR_CHANNEL_ID/YOUR_MESSAGE_ID",
    "luckydice": "https://discord.com/channels/YOUR_SERVER_ID/YOUR_CHANNEL_ID/YOUR_MESSAGE_ID",
}
