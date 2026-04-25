"""Cloud Function HTTPS — filtra alertas Canarytokens e encaminha p/ Telegram.

Repos públicos GitHub recebem dezenas de scanners automatizados que detectam
padrões `AKIA...` e tentam autenticar para validar a chave. Cada validação
dispara o Canarytoken — gerando ruído alto sem valor de detecção real
(esses não são humanos).

Esta função:
1. Recebe POST do Canarytokens.org com payload JSON do trigger
2. Aplica heurísticas para detectar **scanner automatizado**:
   - User-Agent regex (python-requests, Go-http-client, libwww, etc)
   - IP em ranges conhecidos de cloud providers (Azure, AWS, GCP US/EU)
3. Se detectado scanner → loga e responde 200 (sem notificar)
4. Se passou filtro → considera trigger humano REAL e envia
   notificação via Telegram para o owner

O canarytoken email original CONTINUA ativo como backup; este filtro é
adicional. Resultado: usuário só recebe notificação via Telegram quando
filtro determina humano provável.

Princípios canônicos:
- Token compartilhado (X-Canary-Filter-Token) para evitar webhook público
- TELEGRAM_BOT_TOKEN + chat_id via env vars (nunca em log)
- Mensagem ao Telegram escapada MarkdownV2 antes do envio
- Falha do Telegram NÃO derruba a função (200 sempre que possível,
  para evitar Canarytokens.org retentando)
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from typing import Any

import functions_framework
import httpx
from flask import Request, Response

logger = logging.getLogger("canary_filter")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# User-Agents tipicamente usados por scanners automatizados de credenciais
_SCANNER_UA_RE = re.compile(
    r"(python-requests|Go-http-client|Java/|curl/|libwww-perl|aiohttp|okhttp|"
    r"nodejs|node-fetch|axios|httpx|httplib|wget/|libcurl|"
    r"PostmanRuntime|insomnia|trufflehog|gitleaks|secretscan|"
    r"github-secret|amazon-internal|aws-sdk-go|botocore)",
    re.IGNORECASE,
)

# Ranges de IP de cloud providers que indicam scanner automatizado
# (CIDR list — ranges públicos publicados pela Microsoft/Amazon/Google)
_SCANNER_IP_RANGES = [
    # Azure US (GitHub Actions runners)
    "52.160.0.0/12",  # Azure US-West
    "52.224.0.0/11",  # Azure US-East
    "20.0.0.0/8",  # Azure (broadly)
    "13.64.0.0/11",  # Azure US
    # AWS US (general scanners)
    "52.0.0.0/11",  # AWS US
    "54.144.0.0/12",  # AWS US
    # GCP US
    "34.64.0.0/10",  # GCP US
    "35.184.0.0/13",  # GCP US
]


def _is_scanner_ip(ip_str: str) -> bool:
    """True se IP cai em range conhecido de cloud provider."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for cidr in _SCANNER_IP_RANGES:
        try:
            if ip in ipaddress.ip_network(cidr):
                return True
        except ValueError:  # pragma: no cover - configuration error
            continue
    return False


def _is_scanner_ua(user_agent: str) -> bool:
    """True se User-Agent indica scanner automatizado."""
    if not user_agent:
        return False
    return bool(_SCANNER_UA_RE.search(user_agent))


def _extract_trigger_info(payload: dict[str, Any]) -> dict[str, str]:
    """Extrai campos relevantes do payload Canarytokens.org.

    Formato varia ligeiramente; tentamos múltiplos paths.
    """
    info = payload.get("additional_info") or {}
    if isinstance(info, dict):
        ua = info.get("useragent") or info.get("user_agent") or info.get("User-Agent") or ""
        ip = info.get("src_ip") or info.get("source_ip") or info.get("ip") or ""
    else:
        ua = ""
        ip = ""

    return {
        "user_agent": str(ua),
        "source_ip": str(ip),
        "memo": str(payload.get("memo", "")),
        "channel": str(payload.get("channel", "")),
        "time": str(payload.get("time", "")),
        "token": str(payload.get("token", ""))[:16],  # truncar
    }


def _escape_md(text: str) -> str:
    """Escapa MarkdownV2 do Telegram."""
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", text)


def _send_telegram(message: str) -> bool:
    """Envia mensagem ao chat do dono. Retorna True se enviou ok."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if not bot_token or not chat_id:
        logger.warning("telegram credentials missing")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
            r = client.post(
                url,
                json={
                    "chat_id": int(chat_id),
                    "text": message,
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": True,
                },
            )
            r.raise_for_status()
            return True
    except (httpx.HTTPError, ValueError) as e:
        logger.exception("telegram send failed: %s", type(e).__name__)
        return False


@functions_framework.http
def canary_filter(request: Request) -> Response:
    """Entry point HTTPS."""
    expected_token = os.environ.get("FILTER_TOKEN")
    if expected_token:
        # Token via query param OU header (Canarytokens.org limited)
        received = request.args.get("token") or request.headers.get("X-Canary-Filter-Token", "")
        if received != expected_token:
            logger.warning("auth failed from %s", request.remote_addr)
            return Response("unauthorized", status=401)

    if request.method != "POST":
        return Response("method not allowed", status=405)

    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        payload = {}

    info = _extract_trigger_info(payload)

    # Decidir se filtra ou notifica
    is_scanner_ua = _is_scanner_ua(info["user_agent"])
    is_scanner_ip = _is_scanner_ip(info["source_ip"])
    is_scanner = is_scanner_ua or is_scanner_ip

    logger.info(
        "trigger memo=%s ip=%s ua=%s scanner=%s (ua=%s ip=%s)",
        info["memo"][:80],
        info["source_ip"],
        info["user_agent"][:80],
        is_scanner,
        is_scanner_ua,
        is_scanner_ip,
    )

    if is_scanner:
        return Response("filtered (scanner)", status=200)

    # Trigger considerado humano — envia ao Telegram
    msg = (
        "🚨 *CANARYTOKEN ACIONADO* 🚨\n\n"
        f"*Memo:* {_escape_md(info['memo'])}\n"
        f"*Canal:* {_escape_md(info['channel'])}\n"
        f"*IP origem:* `{_escape_md(info['source_ip'])}`\n"
        f"*User\\-Agent:* {_escape_md(info['user_agent'][:100])}\n"
        f"*Hora:* {_escape_md(info['time'])}\n\n"
        "_Este alerta passou pelo filtro automático \\(não é scanner conhecido\\)\\._\n"
        "_Verifique em canarytokens\\.org se o uso é legítimo\\._"
    )
    sent = _send_telegram(msg)
    return Response(
        f"forwarded telegram={sent}",
        status=200,
    )
