from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from typing import Literal
from urllib.parse import quote

from config import DROP_THRESHOLD_PERCENT, MAX_SIGNAL_ODDS
from data import HandicapOdds, MatchOdds, UpcomingEvent


Market = Literal["1x2_odds", "ah_odds"]


@dataclass(frozen=True)
class MatchAlert:
    event_id: str
    market: Market
    message: str
    telegram_message: str


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
    drops = _get_side_drops(old_odds, new_odds)
    qualifying_drops = [
        item
        for item in drops
        if (
            item[3] is not None
            and item[3] > DROP_THRESHOLD_PERCENT
            and item[2] <= MAX_SIGNAL_ODDS
        )
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
    telegram_message = (
        f"{_format_telegram_match_header(event)}\n\n"
        f"Победа {'1' if side == 'Home' else '2'}\n"
        f"{_format_odds(new_value)}"
    )
    return MatchAlert(event.event_id, "1x2_odds", message, telegram_message)


# Создает уведомление о падении коэффициента AH с учетом стороны и форы.
def _analyze_ah(event: UpcomingEvent) -> MatchAlert | None:
    if len(event.ah_odds) < 2:
        return None

    old_odds = event.ah_odds[-1]
    new_odds = event.ah_odds[0]
    if old_odds.handicap != new_odds.handicap:
        return None

    drops = _get_side_drops(old_odds, new_odds)
    qualifying_drops = [
        item
        for item in drops
        if (
            item[3] is not None
            and item[3] > DROP_THRESHOLD_PERCENT
            and item[2] <= MAX_SIGNAL_ODDS
        )
    ]
    if not qualifying_drops:
        return None

    side, old_value, new_value, drop_percent = max(
        qualifying_drops,
        key=lambda item: item[3],
    )
    handicap = new_odds.handicap if side == "Home" else -new_odds.handicap
    message = (
        f"league: {event.league}\n"
        f"{event.home} - {event.away}\n"
        f"Drop AH: {side} {handicap:+} Win {old_value} -> {new_value}\n"
        f"{drop_percent:.2f}%"
    )
    telegram_message = (
        f"{_format_telegram_match_header(event)}\n\n"
        f"Фора {'1' if side == 'Home' else '2'} {handicap:+}\n"
        f"{_format_odds(new_value)}"
    )
    return MatchAlert(event.event_id, "ah_odds", message, telegram_message)


# Формирует экранированный заголовок матча для Telegram с выделенной лигой.
def _format_telegram_match_header(event: UpcomingEvent) -> str:
    home_slug = "-".join(event.home.lower().split())
    away_slug = "-".join(event.away.lower().split())
    match_url = (
        "https://betsapi.com/esports/rs/bet365/"
        f"{quote(event.event_id, safe='')}/{quote(home_slug, safe='-')}"
        f"-vs-{quote(away_slug, safe='-')}"
    )
    return (
        f"🎮 <b>{escape(event.league)}</b>\n"
        f'<a href="{match_url}">{escape(event.home)} — {escape(event.away)}</a>'
    )


# Округляет коэффициент до двух знаков после десятичной точки.
def _format_odds(odds: Decimal) -> str:
    return str(odds.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# Сравнивает старые и новые коэффициенты отдельно для каждой стороны.
def _get_side_drops(
    old_odds: MatchOdds | HandicapOdds,
    new_odds: MatchOdds | HandicapOdds,
) -> list[tuple[str, Decimal, Decimal, Decimal | None]]:
    return [
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


# Проверяет матчи и возвращает сообщения для будущего notifier.
def analyze_events(events: list[UpcomingEvent]) -> list[MatchAlert]:
    alerts: list[MatchAlert] = []
    for event in events:
        for analyze_market in (_analyze_1x2, _analyze_ah):
            alert = analyze_market(event)
            if alert is not None:
                alerts.append(alert)
    return alerts
