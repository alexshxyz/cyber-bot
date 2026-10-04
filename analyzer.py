from dataclasses import dataclass
from decimal import Decimal

from config import DROP_THRESHOLD_PERCENT
from data import UpcomingEvent


@dataclass(frozen=True)
class MatchAlert:
    event_id: str
    message: str


# Проверяет изменение коэффициента для одной стороны от старой записи к новой.
def _get_drop_percent(old_odds: Decimal, new_odds: Decimal) -> Decimal | None:
    if old_odds <= new_odds or old_odds <= 0:
        return None

    return (old_odds - new_odds) / old_odds * 100


# Создает уведомление, если коэффициент 1X2 упал больше чем на 20 процентов.
def _analyze_1x2(event: UpcomingEvent) -> MatchAlert | None:
    if len(event.odds_1x2) < 2:
        return None

    old_odds = event.odds_1x2[-1]
    new_odds = event.odds_1x2[0]
    drops = [
        (
            "Home",
            old_odds.home_od,
            new_odds.home_od,
            _get_drop_percent(old_odds.home_od, new_odds.home_od),
        ),
        (
            "Away",
            old_odds.away_od,
            new_odds.away_od,
            _get_drop_percent(old_odds.away_od, new_odds.away_od),
        ),
    ]
    qualifying_drops = [
        item
        for item in drops
        if item[3] is not None and item[3] > DROP_THRESHOLD_PERCENT
    ]
    if not qualifying_drops:
        return None

    side, old_value, new_value, drop_percent = max(
        qualifying_drops,
        key=lambda item: item[3],
    )
    message = (
        f"league: {event.league}\n"
        f"{event.home} - {event.away}\n"
        f"Drop 1x2: {side} Win {old_value} -> {new_value}\n"
        f"{drop_percent:.2f}%"
    )
    return MatchAlert(event.event_id, message)


# Проверяет матчи и возвращает сообщения для будущего notifier.
def analyze_events(events: list[UpcomingEvent]) -> list[MatchAlert]:
    alerts: list[MatchAlert] = []
    for event in events:
        alert = _analyze_1x2(event)
        if alert is not None:
            alerts.append(alert)
    return alerts
