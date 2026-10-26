"""C9：集成桥 stale 判定双轨独立——fdeops 轨单独断连也要报警。

openfde 与 fdeops 是两条独立采集链；只看 openfde_synced_at 时，fdeops 文件
探针停摆（目录移走、.registry 锁死）不会黄标，投影悄然过期还显示「正常」。
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from fde_api.bridge.sync import STALE_AFTER_MINUTES, apply_snapshot, engagement_view


def _payload(slug: str) -> dict:
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "openfde": {
            "engagements": [
                {"slug": slug, "ok": True, "status": {"entities": 1}, "source_uri": "cli://openfde/x"}
            ]
        },
        "fdeops": {
            "registry_sha256": "a" * 64,
            "source_uri": "file://fdeops",
            "dirs": [{"slug": slug, "exists": True, "fde_initialized": True}],
        },
    }


def _age_fdeops_track(app, slug: str, hours: float) -> None:
    """把 fdeops 轨的 synced_at 拨回过去（模拟该轨探针停摆）。"""
    from fde_api.extensions import db

    with app.app_context():
        session = db.session()
        try:
            session.execute(
                text(
                    "UPDATE bridge_engagements SET fdeops_synced_at = :ts "
                    "WHERE slug = :slug"
                ),
                {
                    "ts": datetime.now(UTC) - timedelta(hours=hours),
                    "slug": slug,
                },
            )
            session.commit()
        finally:
            session.close()


def test_fdeops_track_disconnection_flags_stale(db_session, app, settings):
    slug = "c9-stale-check"
    apply_snapshot(_payload(slug), trigger="poller")
    _age_fdeops_track(app, slug, hours=STALE_AFTER_MINUTES + 2)

    view = engagement_view()
    row = next(item for item in view["engagements"] if item["slug"] == slug)
    assert "stale" in row["flags"], row["flags"]


def test_both_tracks_fresh_has_no_stale_flag(db_session, app, settings):
    slug = "c9-fresh-check"
    apply_snapshot(_payload(slug), trigger="poller")

    view = engagement_view()
    row = next(item for item in view["engagements"] if item["slug"] == slug)
    assert "stale" not in row["flags"], row["flags"]


def test_openfde_only_staleness_still_flags(db_session, app, settings):
    """原行为回归：openfde 轨断连照旧报警（C9 不许把旧语义修没）。"""
    slug = "c9-openfde-stale"
    apply_snapshot(_payload(slug), trigger="poller")
    from fde_api.extensions import db

    with app.app_context():
        session = db.session()
        try:
            session.execute(
                text(
                    "UPDATE bridge_engagements SET openfde_synced_at = :ts "
                    "WHERE slug = :slug"
                ),
                {
                    "ts": datetime.now(UTC) - timedelta(minutes=STALE_AFTER_MINUTES + 2),
                    "slug": slug,
                },
            )
            session.commit()
        finally:
            session.close()

    view = engagement_view()
    row = next(item for item in view["engagements"] if item["slug"] == slug)
    assert "stale" in row["flags"], row["flags"]
