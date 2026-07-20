import logging
from logging.handlers import RotatingFileHandler
import os
import sys

from WritingToolApp import WritingToolApp

# Keep a small local diagnostic log. Windowed packaged builds have no console,
# so without this file global-hotkey and speech failures are otherwise silent.
log_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.dirname(sys.argv[0])), 'Writing Tools')
os.makedirs(log_dir, exist_ok=True)
log_handlers = [
    RotatingFileHandler(
        os.path.join(log_dir, 'writing-tools.log'),
        maxBytes=512 * 1024,
        backupCount=2,
        encoding='utf-8',
    )
]
if sys.stderr is not None:
    log_handlers.append(logging.StreamHandler())
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=log_handlers,
)


def main():
    """
    The main entry point of the application.
    """
    app = WritingToolApp(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
