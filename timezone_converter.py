"""Convert a time from one time zone to another using Python's standard library."""

from datetime import datetime
from zoneinfo import ZoneInfo


def convert_timezone(time_to_convert: datetime, from_tz: str, to_tz: str) -> datetime:
    """
    Convert a time from one time zone to another.

    Parameters
    ----------
    time_to_convert : datetime
        The time to convert. If it is "naive" (has no tzinfo), it is
        interpreted as being in `from_tz`. If it already carries a tzinfo,
        it is first re-expressed in `from_tz` so the input is unambiguous.
    from_tz : str
        IANA time zone name of the source, e.g. "Europe/Amsterdam".
    to_tz : str
        IANA time zone name of the target, e.g. "Africa/Addis_Ababa".

    Returns
    -------
    datetime
        A timezone-aware datetime representing the same instant in `to_tz`.
    """
    source = ZoneInfo(from_tz)  # raises ZoneInfoNotFoundError for bad names
    target = ZoneInfo(to_tz)

    if time_to_convert.tzinfo is None:
        localized = time_to_convert.replace(tzinfo=source)
    else:
        localized = time_to_convert.astimezone(source)

    return localized.astimezone(target)


if __name__ == "__main__":
    # Example 1: a fixed meeting time in Amsterdam -> New York and Tokyo
    meeting = datetime(2026, 11, 2, 14, 57)
    for zone in ["America/New_York", "Asia/Tokyo", "Africa/Addis_Ababa"]:
        converted = convert_timezone(meeting, "Europe/Amsterdam", zone)
        print(f"Amsterdam {meeting:%Y-%m-%d %H:%M} -> {zone}: "
              f"{converted:%Y-%m-%d %H:%M %Z (UTC%z)}")

    # Example 2: the current time in Amsterdam -> UTC
    now_ams = datetime.now(ZoneInfo("Europe/Amsterdam"))
    now_utc = convert_timezone(now_ams, "Europe/Amsterdam", "UTC")
    print(f"\nNow (Amsterdam): {now_ams:%Y-%m-%d %H:%M %Z}")
    print(f"Now (UTC):       {now_utc:%Y-%m-%d %H:%M %Z}")

    # Example 3: daylight-saving edge case — same clock time, different offsets
    summer = convert_timezone(datetime(2026, 7, 1, 12, 0), "Europe/Amsterdam", "UTC")
    winter = convert_timezone(datetime(2026, 12, 1, 12, 0), "Europe/Amsterdam", "UTC")
    print(f"\n12:00 Amsterdam in July     -> {summer:%H:%M} UTC (CEST, +2)")
    print(f"12:00 Amsterdam in December -> {winter:%H:%M} UTC (CET, +1)")
