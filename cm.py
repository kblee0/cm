import ctypes
import logging
import threading
import time
import traceback

import pystray
import win32api
import win32clipboard
import win32con
import win32gui
from PIL import Image

# Store the supported formats
SUPPORTED_CF = [
    win32clipboard.RegisterClipboardFormat("Rich Text Format"),
    win32clipboard.CF_TEXT,  # 1: Text
    win32clipboard.CF_OEMTEXT,
    win32clipboard.CF_LOCALE,
    # win32clipboard.CF_BITMAP,
    # win32clipboard.CF_DIB,
    win32clipboard.CF_DIBV5,  # 17: Images
    # win32clipboard.CF_ENHMETAFILE
    win32clipboard.CF_UNICODETEXT,  # 13: Unicode Text
    win32clipboard.RegisterClipboardFormat("HTML Format"),
    win32clipboard.RegisterClipboardFormat("image/svg+xml"),
    win32clipboard.RegisterClipboardFormat("PNG"),
    # win32clipboard.RegisterClipboardFormat("XML Spreadsheet"),
]


class Clipboard:
    def __init__(self, trigger_at_start: bool = False):
        self._trigger_at_start = trigger_at_start
        self._clip_data = {}
        self._last_clip_seq = 0
        self._thread_id = 0
        self._hwnd = self._create_window()

    def _create_window(self) -> int:
        """
        Create a window for listening to messages
        :return: window hwnd
        """
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._process_message
        wc.lpszClassName = self.__class__.__name__
        wc.hInstance = win32api.GetModuleHandle(None)
        class_atom = win32gui.RegisterClass(wc)
        return win32gui.CreateWindow(class_atom, self.__class__.__name__, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)

    @staticmethod
    def _format_name(fmt):
        if not hasattr(Clipboard._format_name, "formats"):
            Clipboard._format_name.formats = {val: name for name, val in vars(win32clipboard).items() if
                                              name.startswith('CF_')}

        if fmt in Clipboard._format_name.formats:
            return Clipboard._format_name.formats[fmt]
        try:
            Clipboard._format_name.formats[fmt] = win32clipboard.GetClipboardFormatName(fmt)
            return Clipboard._format_name.formats[fmt]
        except:
            return "unknown"

    def _process_message(self, hwnd: int, msg: int, wparam: int, lparam: int):
        WM_CLIPBOARDUPDATE = 0x031D

        if msg == WM_CLIPBOARDUPDATE:
            self._process_clip()

        return 0

    def _process_clip(self):
        clip_seq = win32clipboard.GetClipboardSequenceNumber()

        logging.debug("++++++++++ Start sequence = %d, last sequence = %d ++++++++++", clip_seq, self._last_clip_seq)
        if self._last_clip_seq >= clip_seq:
            logging.debug("Ignore processed sequences. seq = %d", clip_seq)
            return
        time.sleep(0.1)
        for i in range(1, 5):
            try:
                time.sleep(0.1 * i)
                win32clipboard.OpenClipboard()
                logging.debug("OpenClipboard() success.")
                break
            except:
                logging.error("OpenClipboard error. %s", traceback.format_exc())

        try:
            format = win32clipboard.EnumClipboardFormats(0)
            logging.debug("First clipboard format :: %s(%d)", Clipboard._format_name(format), format)

            if format != 0:
                self._backup_clipboard()
            else:
                self._restore_clipboard()
                pass
        finally:
            win32clipboard.CloseClipboard()
            logging.debug("CloseClipboard")
            self._last_clip_seq = win32clipboard.GetClipboardSequenceNumber()

    def _backup_clipboard(self):
        logging.debug("Starts clipboard backup.")

        format = win32clipboard.EnumClipboardFormats(0)

        data = {}
        while format != 0:
            format_name = Clipboard._format_name(format)
            if format in SUPPORTED_CF:
                try:
                    data[format] = win32clipboard.GetClipboardData(format)
                    logging.debug("+ Backup  :: format = %s(%d), size = %d", format_name, format, len(data[format]))
                except:
                    logging.error("GetClipboardData(%s(%d)) error. %s", format_name, format, traceback.format_exc())
            else:
                logging.debug("- Backup  :: format = %s(%d)", format_name, format)
            format = win32clipboard.EnumClipboardFormats(format)

        self._clip_data = data
        logging.info("Clipboard has been backed up. :: format count = %d", len(data))

    def _restore_clipboard(self):
        if self._clip_data == {}:
            logging.debug("There is no clipboard data to restore. :: last_seq = %d", self._last_clip_seq)
            return

        logging.debug("Starts clipboard restoration.")
        win32clipboard.EmptyClipboard()

        for format in self._clip_data:
            format_name = Clipboard._format_name(format)
            try:
                win32clipboard.SetClipboardData(format, self._clip_data[format])
                logging.debug("* Restore :: format = %s(%d), size = %d", format_name, format,
                              len(self._clip_data[format]))
            except:
                logging.error("SetClipboardData() error. :: format = %s(%d), size = %d, %s", format_name, format,
                              len(self._clip_data[format]), traceback.format_exc())
                return
        logging.info("Clipboard has been restored. :: format count = %d", len(self._clip_data))

    def listen(self):
        if self._thread_id > 0:
            logging.info("Clipboard listener is already running.")
            return

        if self._trigger_at_start:
            self._process_clip()

        def runner():
            logging.info("Clipboard listener started.")

            self._thread_id = win32api.GetCurrentThreadId()
            ctypes.windll.user32.AddClipboardFormatListener(self._hwnd)
            win32gui.PumpMessages()
            ctypes.windll.user32.RemoveClipboardFormatListener(self._hwnd)
            logging.info("Clipboard listener stopped.")
            self._thread_id = 0

        th = threading.Thread(target=runner, daemon=True)

        th.start()

        while th.is_alive():
            th.join(1)

    def stop(self):
        if self._thread_id > 0:
            win32api.PostThreadMessage(self._thread_id, win32con.WM_QUIT, 0, 0)


class TrayIcon:
    def __init__(self):
        self._icon = None
        self._clipboard = None

    def run(self):
        image = Image.open("cm.png")

        menu = pystray.Menu(
            pystray.MenuItem('Debug mode', lambda: self._set_loglevel(logging.DEBUG)),
            pystray.MenuItem('Info mode', lambda: self._set_loglevel(logging.INFO)),
            pystray.MenuItem('Start CM', lambda: self._run_clipboard_manager(self._icon)),
            pystray.MenuItem('Stop CM', lambda: self._clipboard.stop()),
            pystray.MenuItem('Quit', lambda: self.stop()))

        self._icon = pystray.Icon("CM", image, "Clipboard Manager", menu=menu)

        self._clipboard = Clipboard(trigger_at_start=False)
        self._icon.run(self._run_clipboard_manager)

    def _run_clipboard_manager(self, icon):
        self._icon.visible = True

        def clipboard_runner():
            self._clipboard.listen()

        th = threading.Thread(target=clipboard_runner, daemon=True)
        th.start()

    def _stop_clipboard_manager(self):
        self._clipboard.stop()

    def _set_loglevel(self, level):
        logging.getLogger().setLevel(level)

    def stop(self):
        self._icon.visible = False
        self._clipboard.stop()
        self._icon.stop()


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s [%(levelname)s]: %(message)s', level=logging.DEBUG)
    trayIcon = TrayIcon()
    trayIcon.run()
