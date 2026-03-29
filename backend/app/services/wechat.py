import httpx

from app.config import settings
from app.exceptions import BadRequestException

WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WeChatAPIClient:
    @staticmethod
    async def code2session(code: str) -> dict:
        """Exchange wx.login code for openid and session_key."""
        params = {
            "appid": settings.wechat_app_id,
            "secret": settings.wechat_app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(WECHAT_CODE2SESSION_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        if "errcode" in data and data["errcode"] != 0:
            raise BadRequestException(
                f"WeChat login failed: {data.get('errmsg', 'unknown error')}"
            )

        return {
            "openid": data["openid"],
            "session_key": data["session_key"],
            "unionid": data.get("unionid"),
        }
