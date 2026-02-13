#!/usr/bin/env python3
"""
Bulk create suppliers and upload price lists via API.

Steps per file in ./import_data/pricelists/:
1. Register supplier via /api/auth/register/supplier
2. Log in and obtain access token
3. Upload the corresponding price list via /api/price-lists/upload

The script is idempotent — if a supplier already exists it will re-use the account.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import requests
from requests import RequestException

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PRICE_LISTS_DIR = WORKSPACE_ROOT / "import_data" / "pricelists"

DEFAULT_API_BASE = os.environ.get("BESTPRICE_API_BASE", "http://127.0.0.1:8000/api")
DEFAULT_PASSWORD = os.environ.get("BESTPRICE_SUPPLIER_PASSWORD", "Test12345")
MAX_RESPONSE_SNIPPET = 2000
ALLOWED_LOCAL_RE = re.compile(r"[^a-z0-9._-]+")
MULTI_DOTS_RE = re.compile(r"\.+")

CYRILLIC_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


class ApiRequestError(RuntimeError):
    """Structured error for API calls."""

    def __init__(
        self,
        *,
        endpoint: str,
        status: Optional[int],
        message: str,
        response_text: str | None = None,
        error_id: Optional[str] = None,
        response_json: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status = status
        self.response_text = (response_text or "")[:MAX_RESPONSE_SNIPPET]
        self.error_id = error_id
        self.response_json = response_json or {}


def create_session() -> requests.Session:
    return requests.Session()


def parse_error_response(response: requests.Response) -> tuple[Optional[str], Optional[str], Optional[dict]]:
    payload: Optional[dict] = None
    error_id: Optional[str] = None
    message: Optional[str] = None
    try:
        payload_candidate = response.json()
        if isinstance(payload_candidate, dict):
            payload = payload_candidate
    except ValueError:
        return None, None, None

    if not payload:
        return None, None, None

    detail = payload.get("detail")
    if isinstance(detail, dict):
        error_id = detail.get("error_id") or detail.get("correlation_id")
        message = detail.get("message") or detail.get("error")
        if not message:
            # Try nested detail/message
            for key in ("reason", "detail"):
                val = detail.get(key)
                if isinstance(val, str):
                    message = val
                    break
    elif isinstance(detail, list):
        str_items = [str(item) for item in detail if item is not None]
        if str_items:
            message = "; ".join(str_items)
    elif isinstance(detail, str):
        message = detail

    error_id = error_id or payload.get("error_id") or payload.get("correlation_id")
    if not message:
        for key in ("message", "error", "reason"):
            value = payload.get(key)
            if isinstance(value, str):
                message = value
                break

    return error_id, message, payload


def derive_docs_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    return f"{base}/docs"


def ensure_backend_available(session: requests.Session, api_base: str) -> None:
    docs_url = derive_docs_url(api_base)
    try:
        response = session.get(docs_url, timeout=20)
    except RequestException as exc:
        print(f"❌ Backend not running: GET {docs_url} failed ({exc}).")
        sys.exit(1)

    if response.status_code != 200:
        print(
            f"❌ Backend not running: GET {docs_url} returned status "
            f"{response.status_code}."
        )
        sys.exit(1)


def record_failure(
    file_path: Path,
    error: ApiRequestError,
    stats: dict,
    category: str,
    supplier_name: str,
    supplier_email: str,
) -> None:
    status_text = error.status if error.status is not None else "no response"
    error_id = getattr(error, "error_id", None)
    print(
        f"❌ [{category}] file={file_path.name} supplier={supplier_name} "
        f"email={supplier_email} url={error.endpoint} status={status_text}: {error}"
    )
    if error_id:
        print(f"   error_id: {error_id}")
    if error.response_text:
        print(f"   Response excerpt: {error.response_text}")

    stats.setdefault(category, []).append(
        {
            "file": file_path.name,
            "supplier": supplier_name,
            "email": supplier_email,
            "endpoint": error.endpoint,
            "status": error.status,
            "message": str(error),
            "response": error.response_text,
            "error_id": error_id,
        }
    )


@dataclass
class SupplierPayload:
    email: str
    password: str
    company_name: str
    inn: str
    ogrn: str
    phone: str
    company_email: str
    contact_phone: str
    contact_name: str
    contact_position: str
    legal_address: str
    actual_address: str

    def to_registration_json(self) -> dict:
        return {
            "email": self.email,
            "password": self.password,
            "inn": self.inn,
            "companyName": self.company_name,
            "legalAddress": self.legal_address,
            "ogrn": self.ogrn,
            "actualAddress": self.actual_address,
            "phone": self.phone,
            "companyEmail": self.company_email,
            "contactPersonName": self.contact_name,
            "contactPersonPosition": self.contact_position,
            "contactPersonPhone": self.contact_phone,
            "dataProcessingConsent": True,
        }


def iter_pricelist_files(directory: Path) -> Iterable[Path]:
    if not directory.exists():
        raise FileNotFoundError(
            f"Directory with price lists not found: {directory}. Create it and add .xlsx files."
        )
    yield from sorted(directory.glob("*.xlsx"))


def sanitize_email_local(stem: str, index: int) -> str:
    """
    Convert filename stem to a safe ASCII email local part.
    Ensures characters limited to [a-z0-9._-] and appends -{index:05d}.
    """

    def transliterate(text: str) -> str:
        result = []
        for ch in text:
            if ch in CYRILLIC_TRANSLIT:
                result.append(CYRILLIC_TRANSLIT[ch])
                continue

            if ch.isascii():
                result.append(ch)
                continue

            normalized = unicodedata.normalize("NFKD", ch)
            ascii_equiv = normalized.encode("ascii", "ignore").decode("ascii")
            result.append(ascii_equiv)
        return "".join(result)

    base = stem.lower()
    base = transliterate(base)
    base = base.replace("@", ".")
    base = re.sub(r"[()\[\]{}]+", ".", base)
    base = re.sub(r"\s+", ".", base)

    sanitized = ALLOWED_LOCAL_RE.sub(".", base)
    sanitized = MULTI_DOTS_RE.sub(".", sanitized)
    sanitized = sanitized.strip("._-")

    if not sanitized or not sanitized.isascii():
        sanitized = f"supplier{index:05d}"

    local = f"{sanitized}-{index:05d}"
    local = ALLOWED_LOCAL_RE.sub(".", local)
    local = MULTI_DOTS_RE.sub(".", local)
    local = local.strip(".")

    if not local:
        local = f"supplier{index:05d}-{index:05d}"

    if not local.isascii():
        local = f"supplier{index:05d}-{index:05d}"

    return local


def clean_company_name(stem: str) -> str:
    cleaned = re.sub(r"\(\s*1\s*\)$", "", stem).strip()
    return cleaned or stem


def make_supplier_payload(stem: str, password: str, index: int) -> SupplierPayload:
    email_local = sanitize_email_local(stem, index)
    email = f"{email_local}@example.com"
    company_name = clean_company_name(stem)
    inn = f"770000{index:05d}"
    ogrn = f"1027700{index:07d}"
    phone = f"+7999{index:07d}"
    contact_phone = f"+7998{index:07d}"
    # Ensure company_email stays on its own line (see registration payload expectations)
    company_email = f"{email_local}@company.com"

    if not (email_local.isascii() and email.isascii() and company_email.isascii()):
        fallback_local = f"supplier{index:05d}-{index:05d}"
        email = f"{fallback_local}@example.com"
        company_email = f"{fallback_local}@company.com"
        email_local = fallback_local

    assert email.isascii(), "Email must be ASCII"
    assert company_email.isascii(), "Company email must be ASCII"
    contact_name = f"Auto Supplier {index}"
    contact_position = "Sales Manager"
    legal_address = f"{company_name}, Legal address"
    actual_address = f"{company_name}, Warehouse"

    return SupplierPayload(
        email=email,
        password=password,
        company_name=company_name,
        inn=inn,
        ogrn=ogrn,
        phone=phone,
        company_email=company_email,
        contact_phone=contact_phone,
        contact_name=contact_name,
        contact_position=contact_position,
        legal_address=legal_address,
        actual_address=actual_address,
    )


def register_supplier(session: requests.Session, api_base: str, payload: SupplierPayload) -> bool:
    endpoint = f"{api_base}/auth/register/supplier"
    try:
        response = session.post(
            endpoint,
            json=payload.to_registration_json(),
            timeout=20,
        )
    except RequestException as exc:
        raise ApiRequestError(
            endpoint=endpoint,
            status=None,
            message=f"Network error while registering supplier: {exc}",
        ) from exc

    if response.status_code == 200:
        print(f"✅ Registered supplier {payload.company_name} ({payload.email})")
        return True

    error_id, error_message, payload_json = parse_error_response(response)
    if response.status_code == 400:
        detail_message = error_message or response.reason or response.text
        info_msg = f"ℹ️ Supplier {payload.email} already exists or invalid: {detail_message}"
        if error_id:
            info_msg += f" (error_id: {error_id})"
        print(info_msg)
        return False

    raise ApiRequestError(
        endpoint=endpoint,
        status=response.status_code,
        message=error_message or f"Failed to register supplier {payload.email}",
        response_text=response.text,
        error_id=error_id,
        response_json=payload_json,
    )


def login_supplier(session: requests.Session, api_base: str, email: str, password: str) -> str:
    endpoint = f"{api_base}/auth/login"
    try:
        response = session.post(
            endpoint,
            json={"email": email, "password": password},
            timeout=20,
        )
    except RequestException as exc:
        raise ApiRequestError(
            endpoint=endpoint,
            status=None,
            message=f"Network error during login for {email}: {exc}",
        ) from exc

    error_id, error_message, payload_json = parse_error_response(response)

    if response.status_code != 200:
        raise ApiRequestError(
            endpoint=endpoint,
            status=response.status_code,
            message=error_message or f"Login failed for {email}",
            response_text=response.text,
            error_id=error_id,
            response_json=payload_json,
        )
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise ApiRequestError(
            endpoint=endpoint,
            status=response.status_code,
            message=f"No access token returned for {email}",
            response_text=json.dumps(data),
            error_id=error_id,
            response_json=data if isinstance(data, dict) else None,
        )
    return token


def upload_pricelist(
    session: requests.Session,
    api_base: str,
    token: str,
    file_path: Path,
    supplier_name: str,
    supplier_email: str,
) -> dict:
    endpoint = f"{api_base}/price-lists/upload"
    headers = {"Authorization": f"Bearer {token}"}
    mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    max_attempts = 5
    backoff = 1
    last_error: Optional[ApiRequestError] = None

    for attempt in range(1, max_attempts + 1):
        with file_path.open("rb") as fp:
            files = {"file": (file_path.name, fp, mime_type)}
            try:
                response = session.post(
                    endpoint,
                    files=files,
                    headers=headers,
                    timeout=(10, 120),
                )
            except RequestException as exc:
                error = ApiRequestError(
                    endpoint=endpoint,
                    status=None,
                    message=(
                        f"Upload network error (attempt {attempt}) for {file_path.name}: {exc}"
                    ),
                )
                print(
                    f"⚠️ Upload attempt {attempt} network error: file={file_path.name} "
                    f"supplier={supplier_name} email={supplier_email} url={endpoint} "
                    f"reason={exc}"
                )
                last_error = error
            else:
                status = response.status_code
                if status < 400:
                    return response.json()

                error_id, error_message, payload_json = parse_error_response(response)
                snippet = (response.text or "")[:MAX_RESPONSE_SNIPPET]
                print(
                    f"⚠️ Upload attempt {attempt} failed: status={status} "
                    f"file={file_path.name} supplier={supplier_name} "
                    f"email={supplier_email} url={endpoint}"
                )
                if snippet:
                    print(f"   Response snippet: {snippet}")
                if error_id:
                    print(f"   Backend error_id: {error_id}")
                if error_message:
                    print(f"   Backend reason: {error_message}")

                if status >= 500:
                    last_error = ApiRequestError(
                        endpoint=endpoint,
                        status=status,
                        message=error_message
                        or (
                            f"Upload received server error (attempt {attempt}) "
                            f"for {file_path.name}"
                        ),
                        response_text=response.text,
                        error_id=error_id,
                        response_json=payload_json,
                    )
                else:
                    raise ApiRequestError(
                        endpoint=endpoint,
                        status=status,
                        message=error_message
                        or (
                            f"Price list upload failed for {file_path.name} "
                            f"(supplier={supplier_name}, email={supplier_email})"
                        ),
                        response_text=response.text,
                        error_id=error_id,
                        response_json=payload_json,
                    )

        if attempt >= max_attempts or last_error is None:
            break

        if last_error.status is None or (last_error.status >= 500):
            sleep_duration = backoff
            backoff *= 2
            print(f"   Retrying in {sleep_duration}s...")
            time.sleep(sleep_duration)
        else:
            break

    if last_error is not None:
        raise ApiRequestError(
            endpoint=endpoint,
            status=last_error.status,
            message=str(last_error)
            if str(last_error)
            else (
                f"Upload failed after {max_attempts} attempts for {file_path.name} "
                f"(supplier={supplier_name}, email={supplier_email})"
            ),
            response_text=last_error.response_text,
            error_id=getattr(last_error, "error_id", None),
            response_json=getattr(last_error, "response_json", None),
        )

    raise ApiRequestError(
        endpoint=endpoint,
        status=None,
        message=f"Upload failed for {file_path.name} without response.",
    )


def process_file(
    session: requests.Session,
    api_base: str,
    file_path: Path,
    index: int,
    password: str,
    stats: dict,
) -> None:
    stem = file_path.stem
    payload = make_supplier_payload(stem, password, index)

    print(f"\n=== Processing [{index}] {file_path.name} ===")
    try:
        created = register_supplier(session, api_base, payload)
    except ApiRequestError as exc:
        record_failure(
            file_path,
            exc,
            stats,
            "FAILED_REGISTER",
            payload.company_name,
            payload.email,
        )
        return

    try:
        token = login_supplier(session, api_base, payload.email, payload.password)
        print(f"🔐 Logged in as {payload.email}")
    except ApiRequestError as exc:
        record_failure(
            file_path,
            exc,
            stats,
            "FAILED_LOGIN",
            payload.company_name,
            payload.email,
        )
        return

    try:
        upload_result = upload_pricelist(
            session,
            api_base,
            token,
            file_path,
            payload.company_name,
            payload.email,
        )
        preview_rows = upload_result.get("total_rows", "unknown")
        columns = upload_result.get("columns", [])
        print(f"📤 Uploaded {file_path.name} — rows: {preview_rows}, columns: {columns}")
    except ApiRequestError as exc:
        record_failure(
            file_path,
            exc,
            stats,
            "FAILED_UPLOAD",
            payload.company_name,
            payload.email,
        )
        return

    if created:
        stats["created"] += 1
        print(f"✅ Supplier {payload.company_name} ready with uploaded price list.")
    else:
        stats["reused"] += 1
        print(f"↺ Re-used existing supplier {payload.company_name} and updated price list preview.")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk register suppliers and upload price lists via BestPrice API."
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="Base URL for the API (default: %(default)s)",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="Password to assign to created suppliers (default: %(default)s)",
    )
    parser.add_argument(
        "--pricelists-dir",
        default=str(PRICE_LISTS_DIR),
        help="Directory with .xlsx price lists (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = parse_args(argv)
    directory = Path(args.pricelists_dir)

    try:
        files = list(iter_pricelist_files(directory))
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    if not files:
        print(f"⚠️ No .xlsx files found in {directory}. Nothing to do.")
        return

    api_base = args.api_base.rstrip("/")
    session = create_session()
    ensure_backend_available(session, api_base)

    print(f"🚀 Starting bulk supplier creation for {len(files)} files")
    stats = {
        "created": 0,
        "reused": 0,
        "FAILED_REGISTER": [],
        "FAILED_LOGIN": [],
        "FAILED_UPLOAD": [],
    }
    for index, file_path in enumerate(files, start=1):
        process_file(session, api_base, file_path, index, args.password, stats)

    failed_register = stats["FAILED_REGISTER"]
    failed_login = stats["FAILED_LOGIN"]
    failed_upload = stats["FAILED_UPLOAD"]
    all_failures = failed_register + failed_login + failed_upload
    failed_count = len(all_failures)
    ok_count = stats["created"] + stats["reused"]

    print("\n=== Summary ===")
    print(f"OK files: {ok_count} (created: {stats['created']}, reused: {stats['reused']})")
    print(f"FAILED_REGISTER: {len(failed_register)}")
    print(f"FAILED_LOGIN: {len(failed_login)}")
    print(f"FAILED_UPLOAD: {len(failed_upload)}")

    if failed_count:
        print("Problematic files:")
        for failure in all_failures:
            status_text = failure["status"] if failure["status"] is not None else "no response"
            print(
                f" - {failure['file']} ({failure['endpoint']} -> {status_text}): "
                f"{failure['message']}"
            )
            if failure.get("error_id"):
                print(f"   error_id: {failure['error_id']}")
            if failure.get("response"):
                print(
                    f"   response_snippet: "
                    f"{(failure['response'] or '')[:MAX_RESPONSE_SNIPPET]}"
                )

    if failed_count == 0:
        print("✅ Completed processing all price lists.")
    else:
        print("⚠️ Completed with failures.")


if __name__ == "__main__":
    main()
