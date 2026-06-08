import requests


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
    first = " ".join(part for part in [basic.get("first_name", ""), basic.get("middle_name", "")] if part)
    full_name = f"{basic.get('last_name', '')}, {first} {basic.get('credential', '')}".strip()
    return {"full_name": full_name, "npi": npi}

