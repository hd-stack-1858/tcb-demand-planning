"""City → state lookup for Indian cities. Used to auto-populate orders.state."""

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
    "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "udaipur": "Rajasthan",
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
