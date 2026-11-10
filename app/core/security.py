"""Segurança, hashing de senhas, sessões, CSRF, XSS, Rate Limiting, Mascaramento de Segredos e Anti-Bot (Seção 4)."""

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import hmac
import html
from pathlib import Path
import re
import secrets
import time
from typing import Any, Dict, List, Optional
import bcrypt
from app.config import settings


def hash_password(password: str) -> str:
    """Gera hash seguro bcrypt para senha."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica senha contra hash bcrypt."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def generate_secure_token(length: int = 32) -> str:
    """Gera token criptograficamente seguro."""
    return secrets.token_urlsafe(length)


def sign_payload(payload: str) -> str:
    """Assina payload com HMAC-SHA256 usando SECRET_KEY."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_session_token(username: str, is_admin: bool = True, ttl_seconds: int = 86400) -> str:
    """Cria token de sessão assinado com expiração e papel de administrador."""
    expires_at = int(time.time()) + max(60, ttl_seconds)
    role = "ADMIN" if is_admin else "VIEWER"
    nonce = secrets.token_hex(8)
    raw = f"{username}|{role}|{expires_at}|{nonce}"
    sig = sign_payload(raw)
    return f"{raw}|{sig}"


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Valida assinatura HMAC e expiração de um token de sessão."""
    if not token or token.count("|") != 4:
        return None
    username, role, expires_str, nonce, sig = token.split("|")
    raw = f"{username}|{role}|{expires_str}|{nonce}"
    expected_sig = sign_payload(raw)
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        expires_at = int(expires_str)
    except ValueError:
        return None
    if int(time.time()) > expires_at:
        return None
    return {
        "username": username,
        "role": role,
        "is_admin": role == "ADMIN",
        "expires_at": expires_at,
    }


def generate_csrf_token(session_id: str = "union_default_session") -> str:
    """Gera token CSRF vinculado à sessão com assinatura HMAC-SHA256."""
    nonce = secrets.token_hex(12)
    payload = f"csrf:{session_id}:{nonce}"
    sig = sign_payload(payload)
    return f"{nonce}.{sig}"


def verify_csrf_token(csrf_token: str, session_id: str = "union_default_session") -> bool:
    """Verifica autenticidade do token CSRF."""
    if not csrf_token or "." not in csrf_token:
        return False
    nonce, sig = csrf_token.split(".", 1)
    payload = f"csrf:{session_id}:{nonce}"
    expected = sign_payload(payload)
    return hmac.compare_digest(sig, expected)


def sanitize_input(text: Optional[str], max_length: int = 5000) -> str:
    """Sanitiza entradas de texto contra XSS e payloads maliciosos."""
    if not text:
        return ""
    cleaned = str(text)[:max_length]
    # Remove tags script/iframe/object explícitas antes do escape HTML
    cleaned = re.sub(r"(?is)<(script|iframe|object|embed).*?>.*?</\1>", "", cleaned)
    cleaned = re.sub(r"(?i)javascript\s*:", "", cleaned)
    cleaned = re.sub(r"(?i)on\w+\s*=", "", cleaned)
    return html.escape(cleaned, quote=True).strip()


def detect_sql_injection_pattern(value: Optional[str]) -> bool:
    """Detecta tentativas clássicas de SQL Injection em parâmetros brutos."""
    if not value:
        return False
    patterns = (
        r"(?i)\bunion\s+select\b",
        r"(?i)\bdrop\s+table\b",
        r"(?i)\bor\s+1\s*=\s*1\b",
        r"(?i);\s*delete\s+from\b",
        r"(?i)--\s*$",
    )
    return any(re.search(pat, str(value)) for pat in patterns)


def mask_secret(secret_value: Optional[str]) -> str:
    """Mascara credenciais ou tokens para exibição segura em logs e diagnósticos."""
    if not secret_value:
        return "<NOT_CONFIGURED>"
    val = str(secret_value).strip()
    if len(val) <= 6:
        return "***"
    return f"{val[:3]}***{val[-2:]}"


def scan_codebase_for_hardcoded_secrets(root_dir: Path) -> Dict[str, Any]:
    """Audita arquivos Python em busca de chaves privadas ou tokens reais hardcoded."""
    suspicious_patterns = [
        re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key
        re.compile(r"APP_USR-[0-9]{10,}-[0-9]{4,}-[a-zA-Z0-9]{16,}"),  # Mercado Livre real token
        re.compile(r"sk-[a-zA-Z0-9]{32,}"),  # OpenAI real secret key
        re.compile(r"-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----"),
    ]
    findings: List[Dict[str, Any]] = []
    scanned_files = 0

    for py_file in root_dir.rglob("*.py"):
        if "tests" in py_file.parts:
            continue
        scanned_files += 1
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in suspicious_patterns:
            match = pat.search(content)
            if match:
                findings.append(
                    {
                        "file": str(py_file.relative_to(root_dir)),
                        "pattern": pat.pattern,
                    }
                )

    return {
        "scanned_files": scanned_files,
        "hardcoded_secrets_found": len(findings),
        "findings": findings,
        "status": "CLEAN" if len(findings) == 0 else "ALERT",
    }


class EndpointRateLimiter:
    """Rate limiter em memória por IP/chave para proteção de endpoints sensíveis."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, List[float]] = defaultdict(list)

    def check_allowed(self, client_key: str) -> Dict[str, Any]:
        now = time.time()
        cutoff = now - self.window_seconds
        recent = [ts for ts in self._hits[client_key] if ts > cutoff]
        self._hits[client_key] = recent
        if len(recent) >= self.max_requests:
            return {
                "allowed": False,
                "remaining": 0,
                "retry_after_seconds": int(self.window_seconds - (now - recent[0])) + 1,
            }
        self._hits[client_key].append(now)
        return {
            "allowed": True,
            "remaining": self.max_requests - len(self._hits[client_key]),
            "retry_after_seconds": 0,
        }

    def reset(self) -> None:
        self._hits.clear()


sensitive_rate_limiter = EndpointRateLimiter(max_requests=30, window_seconds=60)


def fingerprint_visitor(ip_address: Optional[str], user_agent: Optional[str]) -> str:
    """Cria hash anonimizado de visitante (LGPD-friendly) para deduplicação anti-fraude."""
    raw = f"{ip_address or 'unknown'}|{user_agent or 'unknown'}|{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def is_suspected_bot(user_agent: Optional[str]) -> bool:
    """Detecta agentes de bot/crawler conhecidos para não contabilizar cliques artificiais."""
    if not user_agent:
        return True
    ua_lower = user_agent.lower()
    bot_signatures = (
        "bot",
        "crawler",
        "spider",
        "headless",
        "selenium",
        "puppeteer",
        "playwright",
        "curl/",
        "wget/",
        "python-requests",
        "scrapy",
    )
    return any(sig in ua_lower for sig in bot_signatures)
