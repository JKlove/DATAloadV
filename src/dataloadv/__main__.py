"""``python -m dataloadv`` 入口（等价于 console script ``dataloadv``）.

ensure_utf8_mode()（坑 #65）在 import .app 之前执行：源码跑在中文
Windows 上同样需要 UTF-8 模式自举（与打包版行为一致）。
"""

from ._utf8 import ensure_utf8_mode

ensure_utf8_mode()

from .app import main  # noqa: E402（须在 UTF-8 自举之后）

if __name__ == "__main__":
    raise SystemExit(main())
