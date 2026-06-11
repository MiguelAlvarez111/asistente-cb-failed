from functools import lru_cache

import requests


def _clean(value: object) -> str:
    return str(value or "").strip()


@lru_cache(maxsize=4096)
def get_npi_data(npi_number: str | None) -> dict[str, str] | None:
    if not npi_number or not str(npi_number).strip().isdigit():
        return None
    npi = str(npi_number).strip()
    try:
        response = requests.get(f"https://npiregistry.cms.hhs.gov/api/?version=2.1&number={npi}", timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return None
    if data.get("result_count", 0) <= 0:
        return None
    basic = data["results"][0].get("basic", {})
    first_name = _clean(basic.get("first_name"))
    middle_name = _clean(basic.get("middle_name"))
    last_name = _clean(basic.get("last_name"))
    name_suffix = _clean(basic.get("name_suffix"))
    credential = _clean(basic.get("credential"))
    first = " ".join(part for part in [first_name, middle_name] if part)
    display_last = " ".join(part for part in [last_name, name_suffix] if part)
    suffix = f" {credential}" if credential else ""
    full_name = f"{display_last}, {first}{suffix}".strip() if display_last else f"{first}{suffix}".strip()
    return {
        "last_name": last_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "name_suffix": name_suffix,
        "credential": credential,
        "full_name": full_name,
        "npi": npi,
    }
