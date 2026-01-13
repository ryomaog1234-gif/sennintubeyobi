from functools import lru_cache, wraps
from threading import Lock
import time


def cache(seconds: int, max_size: int = 128, typed: bool = False):
    def wrapper(f):
        # 1関数につき1つのLockを共有
        lock = Lock()

        # lru_cacheを適用
        func = lru_cache(maxsize=max_size, typed=typed)(f)

        # TTL（秒）
        func.ttl = seconds
        # 単調増加クロックで期限を管理
        func.expire = time.monotonic() + func.ttl

        @wraps(f)
        def inner(*args, **kwargs):
            now = time.monotonic()

            # TTL判定とクリアを排他制御
            with lock:
                if now > func.expire:
                    func.cache_clear()
                    func.expire = now + func.ttl

            # キャッシュされた関数を呼び出す
            return func(*args, **kwargs)

        # 外部から操作できるよう公開
        inner.clear_cache = func.cache_clear
        inner.cache_info = func.cache_info

        return inner

    return wrapper
