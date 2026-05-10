from __future__ import annotations

from tennis_booking.config import AppConfig
from tennis_booking.loisirs import (
    CheckRequest,
    build_search_payload,
    check_availability,
    scan_time_grid,
)


def make_slot(
    *,
    site_id: int,
    site_name: str,
    borough_id: int,
    borough_name: str,
    start_hour: int = 8,
    can_reserve: bool = True,
) -> dict:
    utc_hour = start_hour + 4
    return {
        "facility": {
            "site": {
                "id": site_id,
                "name": site_name,
                "boroughs": [{"id": borough_id, "name": borough_name}],
                "latitude": 45.5,
                "longitude": -73.6,
            },
            "name": f"Terrain de tennis #1, {site_name}",
            "id": site_id + 10_000,
            "facilityType": {
                "id": 175,
                "name": "Terrain tennis ext",
                "description": "Terrain de tennis extérieur",
            },
        },
        "startDateTime": f"2026-05-13T{utc_hour:02d}:00:00.000Z",
        "endDateTime": f"2026-05-13T{utc_hour + 1:02d}:00:00.000Z",
        "facilityScheduleId": site_id + 20_000,
        "totalPrice": 0.0,
        "canReserve": {"value": can_reserve},
        "facilityPricingId": site_id + 30_000,
    }


def test_build_search_payload_queries_all_selected_boroughs_without_site_filter():
    request = CheckRequest(
        date="2026-05-13",
        time="08:00",
        time_window_hours=2,
        borough_ids=["7", "5", "3"],
        facility_type_ids=["175", "115"],
        dates=["2026-05-13", "2026-05-14"],
        allowed_times=["08:00", "09:00"],
        site_ids=["1734", "1520", "866"],
    )

    payload = build_search_payload(request, offset=500, limit=500)

    assert payload["boroughIds"] == "7,5,3"
    assert payload["facilityTypeIds"] == "175,115"
    assert payload["dates"] == [
        "2026-05-13T00:00:00.000-04:00",
        "2026-05-14T00:00:00.000-04:00",
    ]
    assert payload["startTime"] == "08:00"
    assert payload["endTime"] == "10:00"
    assert "siteId" not in payload


def test_check_availability_queries_each_borough_and_filters_multiple_sites(monkeypatch):
    captured_payloads = []
    slots_by_borough = {
        "7": [
            make_slot(
                site_id=1734,
                site_name="Parc La Fontaine, terrains sportifs",
                borough_id=7,
                borough_name="Le Plateau-Mont-Royal",
            ),
            make_slot(
                site_id=1726,
                site_name="Parc Jeanne-Mance, terrains sportifs",
                borough_id=7,
                borough_name="Le Plateau-Mont-Royal",
            ),
        ],
        "5": [
            make_slot(
                site_id=1520,
                site_name="Parc Beaubien, terrain de sport",
                borough_id=5,
                borough_name="Rosemont - La Petite-Patrie",
            ),
        ],
        "3": [
            make_slot(
                site_id=866,
                site_name="Terrains extérieurs Claude-Robillard",
                borough_id=3,
                borough_name="Ahuntsic - Cartierville",
            ),
        ],
    }

    def fake_post_search(payload):
        captured_payloads.append(payload)
        api_slots = slots_by_borough[payload["boroughIds"]]
        return {"recordCount": len(api_slots), "results": api_slots}

    monkeypatch.setattr("tennis_booking.loisirs.post_search", fake_post_search)

    result = check_availability(
        CheckRequest(
            date="2026-05-13",
            time="08:00",
            time_window_hours=1,
            borough_ids=["7", "5", "3"],
            facility_type_ids=["175"],
            dates=["2026-05-13"],
            allowed_times=["08:00"],
            site_ids=["1734", "1520", "866"],
        )
    )

    assert [payload["boroughIds"] for payload in captured_payloads] == ["7", "5", "3"]
    assert result.record_count == 4
    assert result.available_count == 3
    assert {str(slot["site_id"]) for slot in result.slots} == {"1734", "1520", "866"}


def test_scan_time_grid_sends_union_of_selected_boroughs_and_site_ids(monkeypatch):
    captured_requests = []

    def fake_check_availability(request, progress=None):
        captured_requests.append(request)
        return "result"

    monkeypatch.setattr("tennis_booking.loisirs.check_availability", fake_check_availability)

    config = AppConfig.from_dict(
        {
            "date": "2026-05-13",
            "check_dates": ["2026-05-13"],
            "check_times": ["08:00", "09:00"],
            "borough_ids": ["7", "5", "3"],
            "facility_type_ids": ["175"],
            "site_ids": ["1734", "1520", "866"],
        }
    )

    assert scan_time_grid(config) == ["result"]
    request = captured_requests[0]
    assert request.borough_ids == ["7", "5", "3"]
    assert request.site_ids == ["1734", "1520", "866"]
    assert request.allowed_times == ["08:00", "09:00"]
    assert request.time == "08:00"
    assert request.time_window_hours == 2


def test_selected_unmapped_sites_are_queried_by_site_id(monkeypatch):
    captured_payloads = []

    monkeypatch.setattr(
        "tennis_booking.loisirs.load_locations",
        lambda: {
            "boroughs": [],
            "sites": [
                {"site_id": "1734", "borough_id": "7"},
                {"site_id": "999", "borough_id": ""},
            ],
        },
    )

    def fake_post_search(payload):
        captured_payloads.append(payload)
        if payload.get("siteId") == 999:
            slots = [
                make_slot(
                    site_id=999,
                    site_name="Unmapped Tennis Site",
                    borough_id=8,
                    borough_name="Ville-Marie",
                )
            ]
        else:
            slots = [
                make_slot(
                    site_id=1734,
                    site_name="Parc La Fontaine, terrains sportifs",
                    borough_id=7,
                    borough_name="Le Plateau-Mont-Royal",
                )
            ]
        return {"recordCount": len(slots), "results": slots}

    monkeypatch.setattr("tennis_booking.loisirs.post_search", fake_post_search)

    result = check_availability(
        CheckRequest(
            date="2026-05-13",
            time="08:00",
            time_window_hours=1,
            borough_ids=["7"],
            facility_type_ids=["175"],
            dates=["2026-05-13"],
            allowed_times=["08:00"],
            site_ids=["1734", "999"],
        )
    )

    assert captured_payloads[0]["boroughIds"] == "7"
    assert "siteId" not in captured_payloads[0]
    assert captured_payloads[1]["boroughIds"] == ""
    assert captured_payloads[1]["siteId"] == 999
    assert result.available_count == 2
    assert {str(slot["site_id"]) for slot in result.slots} == {"1734", "999"}
