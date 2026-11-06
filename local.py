"""Local-only entry point; never imports or connects to Speakeasy."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'additional_files/evaluation'))
sys.path.insert(1, str(ROOT / 'additional_files/src/chatbot'))
from local_api import main
if __name__ == '__main__':
    main()
