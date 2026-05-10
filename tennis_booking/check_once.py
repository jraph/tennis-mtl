from tennis_booking.config import load_config
from tennis_booking.loisirs import scan_time_grid


def main() -> None:
    for result in scan_time_grid(load_config()):
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
