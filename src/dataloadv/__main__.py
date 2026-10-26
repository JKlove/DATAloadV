"""``python -m dataloadv`` 入口（等价于 console script ``dataloadv``）."""

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
