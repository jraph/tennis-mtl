import argparse
from datetime import date, timedelta

from tennis_booking.config import load_config
from tennis_booking.loisirs import scan_time_grid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single Loisirs availability check.")
    when = parser.add_mutually_exclusive_group()
    when.add_argument("--date", help="Target date in YYYY-MM-DD (overrides --in-days).")
    when.add_argument(
        "--in-days",
        type=int,
        default=2,
        dest="in_days",
        help="How many days ahead to check: 0=today, 1=tomorrow, 2=day after tomorrow (default).",
    )
    parser.add_argument("--time", help="Start hour as HH:MM (e.g. 18:00). Defaults to the current hour.")
    parser.add_argument("--borough", help="Comma-separated borough IDs (e.g. 7,5). Overrides config defaults.")
    parser.add_argument("--site", help="Comma-separated site IDs to restrict the search.")
    parser.add_argument("--site-name", help="Comma-separated site names (partial, case-insensitive).")
    return parser.parse_args()


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    args = parse_args()
    config = load_config()
    config.date = args.date or (date.today() + timedelta(days=args.in_days)).isoformat()
    config.check_dates = []
    if args.time:
        config.check_times = [args.time]
    if args.borough is not None:
        config.borough_ids = split_csv(args.borough)
    if args.site is not None:
        config.site_ids = split_csv(args.site)
    if args.site_name is not None:
        config.site_names = split_csv(args.site_name)

    for result in scan_time_grid(config):
        print(
            f"{result.checked_at} | {result.query_date} {result.query_time} | {result.status.upper()} | "
            f"{result.available_count}/{result.record_count} relevant/returned slots | {result.search_url}"
        )
        if result.error:
            print(f"  ERROR | {result.error}")
        current_hour = None
        for slot in result.slots:
            if slot["hour"] != current_hour:
                current_hour = slot["hour"]
                print(f"  {slot['hour_label']}")
            print(f"  {slot['summary']}")
            print(f"    Reserve: {slot['reservation_url']}")


if __name__ == "__main__":
    main()
