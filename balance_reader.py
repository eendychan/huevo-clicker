import asyncio
import json
from urllib.request import urlopen
from cdpify import Client

async def get_balance_from_tabs(debug_port=9222, target_url_part="huevo.su/clicker"):
    """
    Подключается к Chrome через CDP, находит все вкладки с нужным URL,
    читает #ck-balance в каждой и возвращает МАКСИМАЛЬНОЕ значение.
    """
    try:
        # Получаем список всех вкладок
        with urlopen(f"http://localhost:{debug_port}/json", timeout=3) as response:
            tabs = json.load(response)
    except Exception:
        return None  # Chrome не запущен с нужным флагом

    max_balance = None

    for tab in tabs:
        if tab.get("type") != "page" or target_url_part not in tab.get("url", ""):
            continue

        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            continue

        try:
            async with Client(ws_url) as client:
                result = await client.runtime.evaluate(
                    expression="""
                        (() => {
                            const el = document.getElementById('ck-balance');
                            if (!el) return null;
                            const match = el.textContent.match(/(\\d+)/);
                            return match ? parseInt(match[1]) : null;
                        })()
                    """,
                    return_by_value=True,
                )
                value = result.result.value
                if value is not None:
                    if max_balance is None or value > max_balance:
                        max_balance = value
        except Exception:
            continue  # вкладка могла закрыться или быть неактивной

    return max_balance


def fetch_balance_sync(debug_port=9222):
    """Синхронная обёртка для вызова из потока кликера."""
    try:
        return asyncio.run(get_balance_from_tabs(debug_port))
    except Exception:
        return None
