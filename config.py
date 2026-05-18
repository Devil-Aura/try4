"""
Configuration — PDF Tools Bot
"""

API_ID   = 22768311
API_HASH = "702d8884f48b42e865425391432b3794"
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"   # ← Replace with your @BotFather token

# Temp directory for file operations
TEMP_DIR = "temp"

# Max PDF size accepted (MB)
MAX_FILE_SIZE_MB = 50

# DPI for rendering pages when combining.
# 150 = good print quality, safe RAM usage (~3 MB per page)
# 200 = high quality but uses ~2x RAM — only raise if VPS has 2 GB+ free
RENDER_DPI = 150

# Max concurrent heavy jobs (combine). Prevents RAM exhaustion when
# multiple users hit the bot at the same time.
MAX_CONCURRENT_JOBS = 2
