"""Start the photobook server from any working directory."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from photobook.servidor import main
main()
