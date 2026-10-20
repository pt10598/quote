import os
os.environ["SKIP_DB_INIT"]="1"
from app import init
init()
print("Database initialized; existing records retained.")
