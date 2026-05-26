from __future__ import annotations

from typing import Any, Optional, Tuple

from backend.app.config import settings
from backend.app.sources.base import SourceUnavailable


def create_tushare_pro(
    token: Optional[str] = None,
    http_url: Optional[str] = None,
) -> Tuple[Any, Any]:
    """Initialize Tushare with the optional relay endpoint.

    Keep this tiny file as the single initialization path so the relay-specific
    private URL hook is not copied around the codebase.
    """

    resolved_token = token if token is not None else settings.tushare_token
    resolved_http_url = http_url if http_url is not None else settings.tushare_http_url
    if not resolved_token:
        raise SourceUnavailable("未配置 Tushare token，跳过实时日线。")
    try:
        import tushare as ts  # type: ignore
    except ImportError as exc:
        raise SourceUnavailable("未安装 tushare，请先安装 requirements.txt。") from exc

    pro = ts.pro_api(resolved_token)
    if resolved_http_url:
        # Required by the relay service:
        # pro._DataApi__http_url = "http://..."
        pro._DataApi__http_url = resolved_http_url
    return ts, pro
