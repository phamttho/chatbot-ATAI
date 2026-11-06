import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CHATBOT_DIR = BASE_DIR / "additional_files" / "src" / "chatbot"

MODEL_ROOT = BASE_DIR / "additional_files" / "models"

if MODEL_ROOT.exists():
    for config_file in MODEL_ROOT.rglob("config.json"):
        model_dir = config_file.parent
        tokenizer = model_dir / "tokenizer.json"
        weights = (
            list(model_dir.glob("*.safetensors"))
            + list(model_dir.glob("*.bin"))
        )

        if tokenizer.exists() and weights:
            os.environ.setdefault("QWEN_MODEL_PATH", str(model_dir))
            break
sys.path.insert(0, str(CHATBOT_DIR))

os.environ["SPEAKEASY_USERNAME"] = 'TitaniumTwinklingSnake'
os.environ["SPEAKEASY_PASSWORD"] = 'DipInJKw'

from main import main

if __name__ == "__main__":
    main()
