"""City → state lookup and pincode → (city, state) via India Post API."""

import json
import re
from pathlib import Path

_PINCODE_CACHE_PATH = Path(__file__).parent.parent / "data" / "reference" / "pincode_cache.json"

_CITY_STATE: dict[str, str] = {
    # Karnataka
    "bengaluru": "Karnataka", "bangalore": "Karnataka",
    # Telangana
    "hyderabad": "Telangana",
    # Maharashtra
    "mumbai": "Maharashtra", "pune": "Maharashtra",
    "nagpur": "Maharashtra", "thane": "Maharashtra",
    "navi mumbai": "Maharashtra",
    # Delhi NCR
    "delhi": "Delhi", "new delhi": "Delhi",
    "gurgaon": "Haryana", "gurugram": "Haryana",
    "noida": "Uttar Pradesh", "greater noida": "Uttar Pradesh",
    "faridabad": "Haryana", "ghaziabad": "Uttar Pradesh",
    # Tamil Nadu
    "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu",
    "madurai": "Tamil Nadu",
    # West Bengal
    "kolkata": "West Bengal",
    # Rajasthan
    "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "udaipur": "Rajasthan", "sikar": "Rajasthan",
    # Gujarat
    "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat",
    # Uttar Pradesh
    "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh",
    "agra": "Uttar Pradesh", "varanasi": "Uttar Pradesh",
    # Punjab / Chandigarh
    "chandigarh": "Chandigarh",
    "ludhiana": "Punjab", "amritsar": "Punjab",
    # Madhya Pradesh
    "bhopal": "Madhya Pradesh", "indore": "Madhya Pradesh",
    # Kerala
    "kochi": "Kerala", "thiruvananthapuram": "Kerala",
    # Andhra Pradesh
    "visakhapatnam": "Andhra Pradesh", "vijayawada": "Andhra Pradesh",
    # Odisha
    "bhubaneswar": "Odisha",
    # Jharkhand
    "ranchi": "Jharkhand",
    # Bihar
    "patna": "Bihar",
    # Assam
    "guwahati": "Assam",
}


def city_to_state(city: str | None) -> str | None:
    if not city:
        return None
    return _CITY_STATE.get(city.strip().lower())


def pincode_to_city_state(pincode: str | None) -> tuple[str | None, str | None]:
    """
    Look up city (District) and state for a 6-digit Indian pincode.
    Calls api.postalpincode.in on first use; results cached locally.
    Returns (city, state) or (None, None) on lookup failure.
    """
    if not pincode or not re.match(r'^\d{6}$', str(pincode).strip()):
        return None, None

    pincode = str(pincode).strip()

    # Check local cache first
    cache: dict = {}
    try:
        if _PINCODE_CACHE_PATH.exists():
            cache = json.loads(_PINCODE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass

    if pincode in cache:
        entry = cache[pincode]
        return entry.get("city"), entry.get("state")

    # Call India Post API
    # verify=False: their SSL cert has expired but the API is live and data is non-sensitive
    try:
        import requests, warnings
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        resp = requests.get(
            f"https://api.postalpincode.in/pincode/{pincode}",
            timeout=8,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data and data[0].get("Status") == "Success":
            po = data[0]["PostOffice"][0]
            city  = po.get("District") or po.get("Name")
            state = po.get("State")
            cache[pincode] = {"city": city, "state": state}
            try:
                _PINCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                _PINCODE_CACHE_PATH.write_text(
                    json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            except Exception:
                pass
            return city, state
    except Exception:
        pass

    return None, None
