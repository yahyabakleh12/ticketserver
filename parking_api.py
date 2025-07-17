import os
import json
import time
import requests
from typing import List, Any, Dict

PARKONIC_BASE_URL = "https://api.parkonic.com/api/street-parking/v2"



def send_request_with_retry(url: str, payload: Dict[str, Any], retries: int = 3, delay: float = 1.0) -> Dict[str, Any] | str:
    """Send POST request with retries."""
    for attempt in range(retries):
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # broad catch to mirror simple behaviour
            last_exc = exc
            time.sleep(delay)
    # if all retries failed, return error message
    return str(last_exc)


def park_in_request(
    token: str,
    parkin_time: str,
    plate_code: str,
    plate_number: str,
    emirates: str,
    conf: str,
    spot_number: int,
    pole_id: int,
    images: List[str],
) -> Dict[str, Any]:
    """Call the /park-in endpoint."""
    url = f"{PARKONIC_BASE_URL}/park-in"
    payload = {
        "token": token,
        "parkin_time": str(parkin_time),
        "plate_code": plate_code,
        "plate_number": plate_number,
        "emirates": emirates,
        "conf": conf,
        "spot_number": spot_number,
        "pole_id": pole_id,
        "images": images,
    }
    resp = send_request_with_retry(url, payload)
    if isinstance(resp, str):
        try:
            resp = json.loads(resp)
        except Exception:
            resp = {}
    return resp


def park_out_request(token: str, parkout_time: str, spot_number: int, pole_id: int, trip_id: int) -> Dict[str, Any]:
    """Call the /park-out endpoint."""
    url = f"{PARKONIC_BASE_URL}/park-out"
    payload = {
        "token": token,
        "parkout_time": str(parkout_time),
        "spot_number": str(spot_number),
        "pole_id": pole_id,
        "trip_id": str(trip_id),
    }
    resp = send_request_with_retry(url, payload)
    if isinstance(resp, str):
        try:
            resp = json.loads(resp)
        except Exception:
            resp = {}
    return resp
