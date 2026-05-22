import os
from dotenv import load_dotenv

load_dotenv()

print("HF_HUB_OFFLINE=" , os.getenv("HF_HUB_OFFLINE"))
print("GLINER_MODEL_PATH=", os.getenv("GLINER_MODEL_PATH"))
print("HF_HOME=" , os.getenv("HF_HOME"))