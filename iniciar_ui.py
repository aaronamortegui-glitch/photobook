"""The page and the API only, on port 7871, without the worker: to try the interface
while the main instance (iniciar.py, 7870) is generating."""
import os, sys
os.environ.setdefault("PHOTOBOOK_PORT", "7871")
os.environ["PHOTOBOOK_SOLO_WEB"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from photobook.servidor import main
main()
