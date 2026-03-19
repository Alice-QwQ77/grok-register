from __future__ import annotations

import random
import re
import string
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config_loader import get_config_value, load_config

_conf: Dict[str, Any] = load_config()

EMAIL_PROVIDER = str(get_config_value(_conf, "email_provider", "duckmail")).strip().lower() or "duckmail"

DUCKMAIL_API_BASE = str(get_config_value(_conf, "duckmail_api_base", "https://api.duckmail.sbs")).strip()
DUCKMAIL_BEARER = str(get_config_value(_conf, "duckmail_bearer", "")).strip()

TEMP_MAIL_API_BASE = str(get_config_value(_conf, "temp_mail_api_base", "https://temp-mail-api.deno.dev")).strip()
TEMP_MAIL_API_KEY = str(get_config_value(_conf, "temp_mail_api_key", "")).strip()
TEMP_MAIL_PROVIDER = str(get_config_value(_conf, "temp_mail_provider", "")).strip()
TEMP_MAIL_DOMAIN = str(get_config_value(_conf, "temp_mail_domain", "")).strip()
TEMP_MAIL_PREFIX = str(get_config_value(_conf, "temp_mail_prefix", "")).strip()

PROXY = str(get_config_value(_conf, "proxy", "")).strip()


_temp_email_cache: Dict[str, str] = {}


def get_email_and_token() -> Tuple[Optional[str], Optional[str]]:
    """
    创建临时邮箱并返回 (email, dev_token)。
    对 DuckMail，dev_token 是 mail token。
    对 temp-mail-api，dev_token 直接复用 email，后续轮询按 email 查询。
    """
    email, _password, dev_token = create_temp_email()
    if email and dev_token:
        _temp_email_cache[email] = dev_token
        return email, dev_token
    return None, None


def get_oai_code(dev_token: str, email: str, timeout: int = 90) -> Optional[str]:
    """
    轮询临时邮箱获取 OTP 验证码。
    """
    code = wait_for_verification_code(dev_token=dev_token, email=email, timeout=timeout)
    if code:
        code = code.replace("-", "")
    return code


def _create_http_session(use_tls_impersonation: bool = False):
    if use_tls_impersonation and curl_requests:
        session = curl_requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        if PROXY:
            session.proxies = {"http": PROXY, "https": PROXY}
        return session, True

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    if PROXY:
        session.proxies = {"http": PROXY, "https": PROXY}
    return session, False


def _do_request(session, use_cffi: bool, method: str, url: str, **kwargs):
    if use_cffi:
        kwargs.setdefault("impersonate", "chrome131")
    return getattr(session, method.lower())(url, **kwargs)


def _generate_password(length: int = 14) -> str:
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%"
    pwd = [random.choice(lower), random.choice(upper), random.choice(digits), random.choice(special)]
    all_chars = lower + upper + digits + special
    pwd += [random.choice(all_chars) for _ in range(length - 4)]
    random.shuffle(pwd)
    return "".join(pwd)


def _build_url(base: str, path: str, params: Optional[Dict[str, Any]] = None) -> str:
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if params:
        clean_params = {k: v for k, v in params.items() if v not in (None, "")}
        if clean_params:
            url = f"{url}?{urlencode(clean_params)}"
    return url


def _create_duckmail_session():
    return _create_http_session(use_tls_impersonation=True)


def _create_temp_mail_session():
    return _create_http_session(use_tls_impersonation=False)


def _temp_mail_headers() -> Dict[str, str]:
    if not TEMP_MAIL_API_KEY:
        raise Exception("temp_mail_api_key 未设置，无法调用 temp-mail-api")
    return {"Authorization": f"Bearer {TEMP_MAIL_API_KEY}"}


def _temp_mail_payload() -> Dict[str, str]:
    payload: Dict[str, str] = {}
    if TEMP_MAIL_PREFIX:
        payload["prefix"] = TEMP_MAIL_PREFIX
    if TEMP_MAIL_DOMAIN:
        payload["domain"] = TEMP_MAIL_DOMAIN
    if TEMP_MAIL_PROVIDER:
        payload["provider"] = TEMP_MAIL_PROVIDER
    return payload


def create_temp_email() -> Tuple[str, str, str]:
    if EMAIL_PROVIDER == "temp-mail-api":
        return create_temp_email_via_temp_mail_api()
    return create_temp_email_via_duckmail()


def create_temp_email_via_duckmail() -> Tuple[str, str, str]:
    """创建 DuckMail 临时邮箱，返回 (email, password, mail_token)"""
    if not DUCKMAIL_BEARER:
        raise Exception("duckmail_bearer 未设置，无法创建临时邮箱")

    chars = string.ascii_lowercase + string.digits
    length = random.randint(8, 13)
    email_local = "".join(random.choice(chars) for _ in range(length))
    email = f"{email_local}@duckmail.sbs"
    password = _generate_password()

    api_base = DUCKMAIL_API_BASE.rstrip("/")
    bearer_headers = {"Authorization": f"Bearer {DUCKMAIL_BEARER}"}
    session, use_cffi = _create_duckmail_session()

    try:
        res = _do_request(
            session,
            use_cffi,
            "post",
            f"{api_base}/accounts",
            json={"address": email, "password": password},
            headers=bearer_headers,
            timeout=15,
        )
        if res.status_code not in (200, 201):
            raise Exception(f"创建邮箱失败: {res.status_code} - {res.text[:200]}")

        time.sleep(0.5)
        token_res = _do_request(
            session,
            use_cffi,
            "post",
            f"{api_base}/token",
            json={"address": email, "password": password},
            timeout=15,
        )
        if token_res.status_code == 200:
            mail_token = token_res.json().get("token")
            if mail_token:
                print(f"[*] DuckMail 临时邮箱创建成功: {email}")
                return email, password, mail_token

        raise Exception(f"获取邮件 Token 失败: {token_res.status_code}")
    except Exception as e:
        raise Exception(f"DuckMail 创建邮箱失败: {e}")


def create_temp_email_via_temp_mail_api() -> Tuple[str, str, str]:
    """
    调用 temp-mail-api 创建临时邮箱。
    返回 (email, password, dev_token)，其中 password 固定为空字符串，dev_token 复用 email。
    """
    session, use_cffi = _create_temp_mail_session()
    api_base = TEMP_MAIL_API_BASE.rstrip("/")
    headers = _temp_mail_headers()
    payload = _temp_mail_payload()

    try:
        method = "post" if payload else "get"
        kwargs: Dict[str, Any] = {"headers": headers, "timeout": 15}
        if payload:
            kwargs["json"] = payload
        res = _do_request(
            session,
            use_cffi,
            method,
            _build_url(api_base, "/api/generate-email"),
            **kwargs,
        )
        if res.status_code != 200:
            raise Exception(f"创建邮箱失败: {res.status_code} - {res.text[:200]}")

        body = res.json()
        if not body.get("success"):
            raise Exception(body.get("error") or "接口返回失败")

        data = body.get("data") or {}
        email = str(data.get("email", "")).strip()
        if not email or "@" not in email:
            raise Exception("接口未返回有效邮箱地址")

        print(f"[*] temp-mail-api 临时邮箱创建成功: {email}")
        return email, "", email
    except Exception as e:
        raise Exception(f"temp-mail-api 创建邮箱失败: {e}")


def fetch_emails(dev_token: str, email: Optional[str] = None) -> List[Dict[str, Any]]:
    if EMAIL_PROVIDER == "temp-mail-api":
        return fetch_emails_via_temp_mail_api(dev_token=dev_token, email=email)
    return fetch_emails_via_duckmail(mail_token=dev_token)


def fetch_emails_via_duckmail(mail_token: str) -> List[Dict[str, Any]]:
    """获取 DuckMail 邮件列表"""
    try:
        api_base = DUCKMAIL_API_BASE.rstrip("/")
        headers = {"Authorization": f"Bearer {mail_token}"}
        session, use_cffi = _create_duckmail_session()
        res = _do_request(
            session,
            use_cffi,
            "get",
            f"{api_base}/messages",
            headers=headers,
            timeout=15,
        )
        if res.status_code == 200:
            data = res.json()
            return data.get("hydra:member") or data.get("member") or data.get("data") or []
    except Exception:
        pass
    return []


def fetch_emails_via_temp_mail_api(dev_token: str, email: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    获取 temp-mail-api 邮件列表。
    dev_token 对该 provider 等同于 email。
    """
    inbox_email = (email or dev_token or "").strip()
    if not inbox_email:
        return []

    try:
        api_base = TEMP_MAIL_API_BASE.rstrip("/")
        headers = _temp_mail_headers()
        params: Dict[str, Any] = {"email": inbox_email}
        if TEMP_MAIL_PROVIDER:
            params["provider"] = TEMP_MAIL_PROVIDER

        session, use_cffi = _create_temp_mail_session()
        res = _do_request(
            session,
            use_cffi,
            "get",
            _build_url(api_base, "/api/emails", params=params),
            headers=headers,
            timeout=15,
        )
        if res.status_code != 200:
            return []

        body = res.json()
        if not body.get("success"):
            return []

        data = body.get("data") or {}
        emails = data.get("emails")
        if isinstance(emails, list):
            return emails
    except Exception:
        pass
    return []


def fetch_email_detail(dev_token: str, msg_id: str, email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if EMAIL_PROVIDER == "temp-mail-api":
        return fetch_email_detail_via_temp_mail_api(dev_token=dev_token, msg_id=msg_id, email=email)
    return fetch_email_detail_via_duckmail(mail_token=dev_token, msg_id=msg_id)


def fetch_email_detail_via_duckmail(mail_token: str, msg_id: str) -> Optional[Dict[str, Any]]:
    """获取 DuckMail 单封邮件详情"""
    try:
        api_base = DUCKMAIL_API_BASE.rstrip("/")
        headers = {"Authorization": f"Bearer {mail_token}"}
        session, use_cffi = _create_duckmail_session()

        if isinstance(msg_id, str) and msg_id.startswith("/messages/"):
            msg_id = msg_id.split("/")[-1]

        res = _do_request(
            session,
            use_cffi,
            "get",
            f"{api_base}/messages/{msg_id}",
            headers=headers,
            timeout=15,
        )
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None


def fetch_email_detail_via_temp_mail_api(
    dev_token: str,
    msg_id: str,
    email: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    inbox_email = (email or dev_token or "").strip()
    if not inbox_email or not msg_id:
        return None

    try:
        api_base = TEMP_MAIL_API_BASE.rstrip("/")
        headers = _temp_mail_headers()
        params: Dict[str, Any] = {"email": inbox_email}
        if TEMP_MAIL_PROVIDER:
            params["provider"] = TEMP_MAIL_PROVIDER

        session, use_cffi = _create_temp_mail_session()
        res = _do_request(
            session,
            use_cffi,
            "get",
            _build_url(api_base, f"/api/email/{msg_id}", params=params),
            headers=headers,
            timeout=15,
        )
        if res.status_code != 200:
            return None

        body = res.json()
        if body.get("success"):
            data = body.get("data")
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return None


def wait_for_verification_code(
    dev_token: str,
    email: Optional[str] = None,
    timeout: int = 120,
) -> Optional[str]:
    """轮询临时邮箱等待验证码邮件"""
    start = time.time()
    seen_ids = set()

    while time.time() - start < timeout:
        messages = fetch_emails(dev_token=dev_token, email=email)
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            msg_id = msg.get("id") or msg.get("@id")
            if not msg_id or msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)

            detail = fetch_email_detail(dev_token=dev_token, msg_id=str(msg_id), email=email)
            payload = detail or msg
            if payload:
                content = (
                    payload.get("text")
                    or payload.get("content")
                    or payload.get("html")
                    or payload.get("html_content")
                    or ""
                )
                code = extract_verification_code(str(content))
                if code:
                    print(f"[*] 从 {EMAIL_PROVIDER} 提取到验证码: {code}")
                    return code
        time.sleep(3)
    return None


def extract_verification_code(content: str) -> Optional[str]:
    """
    从邮件内容提取验证码。
    Grok/x.ai 常见格式：MM0-SF3 或 6 位数字。
    """
    if not content:
        return None

    m = re.search(r"(?<![A-Z0-9-])([A-Z0-9]{3}-[A-Z0-9]{3})(?![A-Z0-9-])", content)
    if m:
        return m.group(1)

    m = re.search(
        r"(?:verification code|验证码|your code)[:\s]*[<>\s]*([A-Z0-9]{3}-[A-Z0-9]{3})\b",
        content,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)

    m = re.search(r"background-color:\s*#F3F3F3[^>]*>[\s\S]*?([A-Z0-9]{3}-[A-Z0-9]{3})[\s\S]*?</p>", content)
    if m:
        return m.group(1)

    m = re.search(r"Subject:.*?(\d{6})", content)
    if m and m.group(1) != "177010":
        return m.group(1)

    for code in re.findall(r">\s*(\d{6})\s*<", content):
        if code != "177010":
            return code

    for code in re.findall(r"(?<![&#\d])(\d{6})(?![&#\d])", content):
        if code != "177010":
            return code

    return None
