import win32clipboard
import pyperclip
from enum import Enum

if __name__ == '__main__':
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.CloseClipboard()