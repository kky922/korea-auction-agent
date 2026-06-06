"""
등기정보광장 Open API 연동 (Phase 3)
https://data.iros.go.kr/rp/oa/openOapiIntro.do
API 키: .env 파일의 IROS_API_KEY (일 1,000건 무료)
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

import requests

_BASE_URL = "https://data.iros.go.kr"


def _load_api_key() -> Optional[str]:
    key = os.getenv("IROS_API_KEY")
    if key:
        return key
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("IROS_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def get_registry_summary(address: str) -> Optional[Dict[str, Any]]:
    """
    등기 현황 요약 조회.

    API 키 없으면 None 반환.
    실제 엔드포인트는 등기정보광장 명세서 확인 필요:
    https://data.iros.go.kr/rp/oa/openOapiIntro.do
    """
    api_key = _load_api_key()
    if not api_key:
        return None

    try:
        params = {
            "authKey": api_key,
            "addr": address,
            "type": "json",
        }
        resp = requests.get(
            f"{_BASE_URL}/api/registry/summary",
            params=params,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "owner": data.get("owner", "확인필요"),
                "mortgage_count": data.get("mortgage_count", 0),
                "seizure": data.get("seizure", False),
                "registry_date": data.get("registry_date", ""),
                "raw": data,
            }
    except Exception:
        pass
    return None
