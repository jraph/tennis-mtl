from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tennis_booking.config import AppConfig, load_locations


ProgressCallback = Callable[[str], None]
BASE_URL = "https://loisirs.montreal.ca/IC3/#/U6510/search/"
DETAIL_BASE_URL = "https://loisirs.montreal.ca/IC3/#/U6510/view/"
API_URL = "https://loisirs.montreal.ca/IC3/api/U6510/public/search/"
TIME_ZONE_OFFSET = "-04:00"
try:
    MONTREAL_TZ = ZoneInfo("America/Toronto")
except ZoneInfoNotFoundError:
    MONTREAL_TZ = timezone(timedelta(hours=-4), "America/Toronto")


@dataclass
class CheckRequest:
    date: str
    time: str
    time_window_hours: int
    borough_ids: list[str]
    facility_type_ids: list[str]
    dates: list[str] | None = None
    allowed_times: list[str] | None = None
    site_ids: list[str] | None = None
    site_names: list[str] | None = None
    sort_column: str = "facility.name"

    @classmethod
    def from_config(cls, config: AppConfig, date_override: str | None = None) -> "CheckRequest":
        return cls(
            date=date_override or config.date,
            time=config.time,
            time_window_hours=config.time_window_hours,
            borough_ids=config.borough_ids,
            facility_type_ids=config.facility_type_ids,
            dates=[date_override or config.date],
            allowed_times=[config.time],
            site_ids=config.site_ids,
            site_names=config.site_names,
            sort_column=config.sort_column,
        )


@dataclass
class CheckResult:
    checked_at: str
    search_url: str
    status: str
    matches: list[str]
    slots: list[dict[str, Any]]
    query_date: str
    query_dates: list[str]
    query_time: str
    query_times: list[str]
    time_window_hours: int
    record_count: int = 0
    available_count: int = 0
    page_title: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_search_url(request: CheckRequest) -> str:
    end_time = search_end_time(request)
    dates = request_dates(request)
    value = {
        "startTime": f"{request.date}T{request.time}:00.000{TIME_ZONE_OFFSET}",
        "dates": [f"{date}T00:00:00.000{TIME_ZONE_OFFSET}" for date in dates],
        "facilityTypeIds": ",".join(request.facility_type_ids),
        "boroughIds": ",".join(request.borough_ids),
    }
    if end_time:
        value["endTime"] = f"{request.date}T{end_time}:00.000{TIME_ZONE_OFFSET}"

    search_param = {
        "filter": {
            "isCollapsed": False,
            "offset": 0,
            "value": value,
        },
        "sortable": {"isOrderAsc": True, "column": request.sort_column},
    }
    query = urlencode(
        {
            "searchParam": json.dumps(search_param, separators=(",", ":")),
            "hasBoroughFilter": "true",
        }
    )
    return f"{BASE_URL}?{query}"


def build_search_payload(
    request: CheckRequest,
    offset: int = 0,
    limit: int = 100,
    site_id: str | None = None,
) -> dict[str, Any]:
    end_time = search_end_time(request)
    dates = request_dates(request)
    payload = {
        "limit": limit,
        "offset": offset,
        "sortColumn": request.sort_column,
        "isSortOrderAsc": True,
        "facilityTypeIds": ",".join(request.facility_type_ids),
        "boroughIds": ",".join(request.borough_ids),
        "dates": [f"{date}T00:00:00.000{TIME_ZONE_OFFSET}" for date in dates],
        "startTime": request.time,
        "endTime": end_time,
    }
    if site_id:
        payload["siteId"] = int(site_id)
    return payload


def scan_dates(config: AppConfig) -> list[CheckResult]:
    start = datetime.strptime(config.date, "%Y-%m-%d").date()
    end = (datetime.combine(start, datetime.min.time()) + timedelta(hours=config.scan_window_hours)).date()
    results = []
    total_days = (end - start).days + 1
    for offset in range(total_days):
        target_date = (start + timedelta(days=offset)).isoformat()
        results.append(check_availability(CheckRequest.from_config(config, target_date)))
    return results


def scan_time_grid(config: AppConfig, progress: ProgressCallback | None = None) -> list[CheckResult]:
    start = datetime.strptime(config.date, "%Y-%m-%d").date()
    dates = config.check_dates or [
        (start + timedelta(days=day_offset)).isoformat()
        for day_offset in range(config.check_days)
    ]
    start_time = min(config.check_times)
    end_time = max(config.check_times)
    query_window_hours = hours_between(start_time, end_time) + config.time_window_hours

    request = CheckRequest(
        date=dates[0],
        time=start_time,
        time_window_hours=query_window_hours,
        borough_ids=config.borough_ids,
        facility_type_ids=config.facility_type_ids,
        dates=dates,
        allowed_times=config.check_times,
        site_ids=config.site_ids,
        site_names=config.site_names,
        sort_column=config.sort_column,
    )
    return [check_availability(request, progress=progress)]


def check_availability(request: CheckRequest, progress: ProgressCallback | None = None) -> CheckResult:
    url = build_search_url(request)
    checked_at = datetime.now().isoformat(timespec="seconds")

    emit_progress(
        progress,
        (
            f"Querying Loisirs for {format_query_dates(request)} at "
            f"{format_query_times(request)} across {len(request.borough_ids)} boroughs "
            f"and {len(request.facility_type_ids)} facility type(s)."
        )
    )
    if request.site_ids:
        emit_progress(progress, f"Filtering selected siteIds after API response: {', '.join(request.site_ids)}.")

    try:
        payload = fetch_all_slots(request, progress=progress)
    except Exception as error:
        emit_progress(progress, f"API check failed: {error}")
        return CheckResult(
            checked_at=checked_at,
            search_url=url,
            status="error",
            matches=[],
            slots=[],
            query_date=request.date,
            query_dates=request_dates(request),
            query_time=request.time,
            query_times=request.allowed_times or [request.time],
            time_window_hours=request.time_window_hours,
            error=str(error),
        )

    slots = payload["results"]
    emit_progress(progress, f"Filtering {len(slots)} API record(s) to selected times and sites.")
    relevant_slots = filter_slots_to_time_window(slots, request)
    slot_summaries = summarize_slots(relevant_slots, request)
    matches = [slot["summary"] for slot in slot_summaries[:12]]
    available_count = count_available(relevant_slots)
    record_count = int(payload["recordCount"])
    status = "available" if available_count else "unavailable"

    emit_progress(progress, f"Finished: {available_count} reservable slot(s) from {record_count} API record(s).")

    return CheckResult(
        checked_at=checked_at,
        search_url=url,
        status=status,
        matches=matches,
        slots=slot_summaries,
        query_date=request.date,
        query_dates=request_dates(request),
        query_time=request.time,
        query_times=request.allowed_times or [request.time],
        time_window_hours=request.time_window_hours,
        record_count=record_count,
        available_count=available_count,
        page_title="API",
    )


def fetch_all_slots(request: CheckRequest, progress: ProgressCallback | None = None) -> dict[str, Any]:
    if request.site_ids:
        return fetch_selected_site_slots(request, progress=progress)
    if len(request.borough_ids) > 1:
        return fetch_all_slots_by_borough(request, progress=progress)
    return fetch_all_slots_for_request(request, progress=progress)


def fetch_selected_site_slots(request: CheckRequest, progress: ProgressCallback | None = None) -> dict[str, Any]:
    selected_site_ids = {str(site_id) for site_id in (request.site_ids or [])}
    known_borough_ids, direct_site_ids = selected_site_query_plan(request.site_ids or [])
    results: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    found_site_ids: set[str] = set()
    record_count = 0

    for index, borough_id in enumerate(known_borough_ids, start=1):
        emit_progress(progress, f"Querying selected-site borough {borough_id} ({index}/{len(known_borough_ids)}).")
        borough_payload = fetch_all_slots_for_request(
            request_with_borough(request, borough_id),
            progress=progress,
        )
        record_count += int(borough_payload["recordCount"])
        for slot in borough_payload["results"]:
            site_id = str(((slot.get("facility") or {}).get("site") or {}).get("id") or "")
            if site_id in selected_site_ids:
                found_site_ids.add(site_id)
            key = slot_identity(slot)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.append(slot)

    fallback_site_ids = list(direct_site_ids) + [
        site_id for site_id in selected_site_ids - found_site_ids - set(direct_site_ids)
    ]

    for index, site_id in enumerate(fallback_site_ids, start=1):
        emit_progress(progress, f"Querying selected siteId {site_id} ({index}/{len(fallback_site_ids)}).")
        site_payload = fetch_all_slots_for_request(
            request_with_borough(request, ""),
            progress=progress,
            site_id=site_id,
        )
        record_count += int(site_payload["recordCount"])
        for slot in site_payload["results"]:
            key = slot_identity(slot)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.append(slot)

    return {"recordCount": record_count, "results": results}


def selected_site_query_plan(site_ids: list[str]) -> tuple[list[str], list[str]]:
    locations = load_locations()
    site_boroughs = {
        str(site.get("site_id")): str(site.get("borough_id"))
        for site in locations["sites"]
        if site.get("site_id")
    }
    known_borough_ids = []
    direct_site_ids = []

    for site_id in site_ids:
        borough_id = site_boroughs.get(str(site_id))
        if borough_id:
            if borough_id not in known_borough_ids:
                known_borough_ids.append(borough_id)
        else:
            direct_site_ids.append(str(site_id))

    return known_borough_ids, direct_site_ids


def request_with_borough(request: CheckRequest, borough_id: str) -> CheckRequest:
    return CheckRequest(
        date=request.date,
        time=request.time,
        time_window_hours=request.time_window_hours,
        borough_ids=[borough_id] if borough_id else [],
        facility_type_ids=request.facility_type_ids,
        dates=request.dates,
        allowed_times=request.allowed_times,
        site_ids=request.site_ids,
        site_names=request.site_names,
        sort_column=request.sort_column,
    )


def fetch_all_slots_by_borough(request: CheckRequest, progress: ProgressCallback | None = None) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    record_count = 0
    borough_ids = request.borough_ids or [""]

    for index, borough_id in enumerate(borough_ids, start=1):
        emit_progress(progress, f"Querying borough {borough_id or 'all'} ({index}/{len(borough_ids)}).")
        borough_payload = fetch_all_slots_for_request(
            request_with_borough(request, borough_id),
            progress=progress,
        )
        record_count += int(borough_payload["recordCount"])
        for slot in borough_payload["results"]:
            key = slot_identity(slot)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.append(slot)

    return {"recordCount": record_count, "results": results}


def fetch_all_slots_for_request(
    request: CheckRequest,
    progress: ProgressCallback | None = None,
    site_id: str | None = None,
) -> dict[str, Any]:
    limit = 500
    offset = 0
    record_count = 0
    results: list[dict[str, Any]] = []

    while True:
        search_payload = build_search_payload(request, offset=offset, limit=limit, site_id=site_id)
        emit_progress(progress, f"POST search {format_api_payload(search_payload)}.")
        payload = post_search(search_payload)
        record_count = int(payload.get("recordCount") or 0)
        page_results = payload.get("results") or []
        results.extend(page_results)
        received_count = len(results)
        emit_progress(progress, f"Received {received_count} of {record_count} API record(s).")

        offset += len(page_results)
        if not page_results or offset >= record_count:
            break

    return {"recordCount": record_count, "results": results}


def slot_identity(slot: dict[str, Any]) -> str:
    facility = slot.get("facility") or {}
    return "|".join(
        str(part or "")
        for part in (
            facility.get("id"),
            slot.get("facilityScheduleId"),
            slot.get("startDateTime"),
            slot.get("endDateTime"),
        )
    )


def emit_progress(progress: ProgressCallback | None, message: str) -> None:
    if progress:
        progress(message)


def format_query_dates(request: CheckRequest) -> str:
    dates = request_dates(request)
    if len(dates) == 1:
        return dates[0]
    return f"{dates[0]} to {dates[-1]}"


def format_query_times(request: CheckRequest) -> str:
    times = request.allowed_times or [request.time]
    return ", ".join(times)


def format_api_payload(payload: dict[str, Any]) -> str:
    site_part = f", siteId={payload['siteId']}" if payload.get("siteId") else ""
    return (
        f"offset={payload['offset']}, limit={payload['limit']}, "
        f"boroughIds={payload['boroughIds'] or 'all'}, "
        f"facilityTypeIds={payload['facilityTypeIds'] or 'all'}, "
        f"dates={len(payload['dates'])}, "
        f"startTime={payload['startTime'] or 'none'}, endTime={payload['endTime'] or 'none'}"
        f"{site_part}"
    )


def post_search(payload: dict[str, Any]) -> dict[str, Any]:
    query = urlencode({"_": str(int(time.time() * 1000))})
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = UrlRequest(
        f"{API_URL}?{query}",
        data=body,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://loisirs.montreal.ca",
            "Referer": BASE_URL,
            "User-Agent": "Mozilla/5.0 tennis-booking-checker",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8-sig"))
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API returned HTTP {error.code}: {details[:500]}") from error
    except URLError as error:
        raise RuntimeError(f"API request failed: {error}") from error


def count_available(slots: list[dict[str, Any]]) -> int:
    return sum(1 for slot in slots if slot.get("canReserve", {}).get("value") is True)


def filter_slots_to_time_window(slots: list[dict[str, Any]], request: CheckRequest) -> list[dict[str, Any]]:
    ranges = []
    for date in request_dates(request):
        start = datetime.fromisoformat(f"{date}T{request.time}:00{TIME_ZONE_OFFSET}")
        ranges.append((start, start + timedelta(hours=request.time_window_hours)))
    allowed_times = set(request.allowed_times or [])
    allowed_site_ids = set(request.site_ids or [])
    allowed_site_names = {normalize_site_name(name) for name in request.site_names or []}

    return [
        slot
        for slot in slots
        if any(start <= parse_api_datetime(slot.get("startDateTime")) < end for start, end in ranges)
        and (
            not allowed_times
            or parse_api_datetime(slot.get("startDateTime")).strftime("%H:%M") in allowed_times
        )
        and slot_matches_site(slot, allowed_site_ids, allowed_site_names)
    ]


def slot_matches_site(
    slot: dict[str, Any],
    allowed_site_ids: set[str],
    allowed_site_names: set[str],
) -> bool:
    if not allowed_site_ids and not allowed_site_names:
        return True
    facility = slot.get("facility") or {}
    site = facility.get("site") or {}
    site_id = str(site.get("id") or "")
    site_name = normalize_site_name(site.get("name") or "")
    return site_id in allowed_site_ids or site_name in allowed_site_names


def normalize_site_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def request_dates(request: CheckRequest) -> list[str]:
    return request.dates or [request.date]


def hours_between(start_time: str, end_time: str) -> int:
    start_hour, start_minute = [int(part) for part in start_time.split(":", 1)]
    end_hour, end_minute = [int(part) for part in end_time.split(":", 1)]
    start = start_hour + (start_minute / 60)
    end = end_hour + (end_minute / 60)
    return int(end - start)


def search_end_time(request: CheckRequest) -> str | None:
    start = datetime.fromisoformat(f"{request.date}T{request.time}:00{TIME_ZONE_OFFSET}")
    end = start + timedelta(hours=request.time_window_hours)
    if end.date() != start.date():
        return None
    return end.strftime("%H:%M")


def summarize_slots(slots: list[dict[str, Any]], request: CheckRequest) -> list[dict[str, Any]]:
    available = [slot for slot in slots if slot.get("canReserve", {}).get("value") is True]
    chosen = available or slots
    summaries = [format_slot(slot, request) for slot in chosen]
    return sorted(
        summaries,
        key=lambda slot: (
            slot["start"],
            slot["court_number"] if slot["court_number"] is not None else 10_000,
            slot["facility"],
        ),
    )


def format_slot(slot: dict[str, Any], request: CheckRequest) -> dict[str, Any]:
    facility = slot.get("facility") or {}
    site = facility.get("site") or {}
    boroughs = site.get("boroughs") or []
    borough = boroughs[0].get("name") if boroughs else "Unknown borough"
    price = slot.get("totalPrice")
    can_reserve = slot.get("canReserve", {}).get("value") is True
    price_text = "free" if price in (None, 0) else f"${price:.2f}"
    start = parse_api_datetime(slot.get("startDateTime"))
    end = parse_api_datetime(slot.get("endDateTime"))
    search_url = build_slot_search_url(request, start)
    detail_url = build_slot_detail_url(slot, start, end) or search_url
    facility_name = facility.get("name", "Unknown court")
    coordinates = extract_coordinates(slot)
    summary = (
        f"{start.strftime('%Y-%m-%d %H:%M')}-{end.strftime('%Y-%m-%d %H:%M')} | "
        f"{facility_name} | {site.get('name', 'Unknown site')} | "
        f"{borough} | {price_text} | {'reservable' if can_reserve else 'not reservable'} | "
        f"schedule {slot.get('facilityScheduleId')}"
    )
    return {
        "summary": summary,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "hour": start.isoformat(),
        "hour_label": start.strftime("%Y-%m-%d %H:%M"),
        "facility": facility_name,
        "court_number": extract_court_number(facility_name),
        "site_id": site.get("id"),
        "site": site.get("name", "Unknown site"),
        "borough": borough,
        "borough_id": boroughs[0].get("id") if boroughs else None,
        "price": price,
        "can_reserve": can_reserve,
        "facility_id": facility.get("id"),
        "facility_pricing_id": slot.get("facilityPricingId"),
        "facility_schedule_id": slot.get("facilityScheduleId"),
        "latitude": coordinates[0] if coordinates else None,
        "longitude": coordinates[1] if coordinates else None,
        "map_url": build_map_url(coordinates, facility_name, site.get("name")),
        "search_url": search_url,
        "detail_url": detail_url,
        "reservation_url": detail_url,
    }


def extract_court_number(facility_name: str) -> int | None:
    match = re.search(r"(?:#|tennis\s+)(\d+)\b", facility_name, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def build_slot_search_url(request: CheckRequest, start: datetime) -> str:
    return build_search_url(
        CheckRequest(
            date=start.date().isoformat(),
            time=start.strftime("%H:%M"),
            time_window_hours=1,
            borough_ids=request.borough_ids,
            facility_type_ids=request.facility_type_ids,
            dates=[start.date().isoformat()],
            allowed_times=[start.strftime("%H:%M")],
            site_ids=request.site_ids,
            site_names=request.site_names,
            sort_column=request.sort_column,
        )
    )


def build_slot_detail_url(slot: dict[str, Any], start: datetime, end: datetime) -> str | None:
    facility = slot.get("facility") or {}
    facility_id = facility.get("id")
    schedule_id = slot.get("facilityScheduleId")
    if not facility_id or not schedule_id:
        return None

    start_route = start.strftime("%Y-%m-%dT%H:%M:%S")
    end_route = end.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{DETAIL_BASE_URL}{facility_id}/{start_route}/{end_route}/{schedule_id}"


def extract_coordinates(value: Any) -> tuple[float, float] | None:
    if isinstance(value, dict):
        for lat_key, lon_key in (
            ("latitude", "longitude"),
            ("lat", "lng"),
            ("lat", "lon"),
            ("y", "x"),
        ):
            if lat_key in value and lon_key in value:
                coordinates = normalize_coordinates(value.get(lat_key), value.get(lon_key))
                if coordinates:
                    return coordinates
        for child in value.values():
            coordinates = extract_coordinates(child)
            if coordinates:
                return coordinates
    elif isinstance(value, list):
        for child in value:
            coordinates = extract_coordinates(child)
            if coordinates:
                return coordinates
    return None


def normalize_coordinates(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if 45 <= lat <= 46 and -74.5 <= lon <= -73:
        return lat, lon
    return None


def build_map_url(
    coordinates: tuple[float, float] | None,
    facility_name: str,
    site_name: str | None,
) -> str:
    if coordinates:
        lat, lon = coordinates
        return f"https://www.google.com/maps?q={lat},{lon}&t=k"
    query = quote_plus(f"{facility_name} {site_name or ''} Montreal")
    return f"https://www.openstreetmap.org/search?query={query}"


def format_api_time(value: str | None) -> str:
    if not value:
        return "?"
    return parse_api_datetime(value).strftime("%Y-%m-%d %H:%M")


def parse_api_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=MONTREAL_TZ)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(MONTREAL_TZ)
