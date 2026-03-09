import sys
import os

INTERP = os.path.expanduser("~/virtualenv/public_html/blacklist/3.11/bin/python")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

sys.path.append(os.getcwd())
from app import app as application