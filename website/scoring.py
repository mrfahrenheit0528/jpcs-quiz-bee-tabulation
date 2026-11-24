"""One grouped query per event, preserving each screen's existing scoring rules."""
from sqlalchemy import func, case
from . import db
from .models import Score, Round


def final_sort_key(mode, qualified, final_score, history_total, clincher_scores):
    """Clinchers break ties in the event's ranking score; they add no base points."""
    if mode == 'cumulative':
        return (qualified, history_total + final_score, tuple(clincher_scores))
    return (qualified, final_score, tuple(clincher_scores), history_total)

class EventTotals:
    def __init__(self, event_id):
        rows = db.session.query(Score.school_id, Score.round_id, func.count(Score.id),
            func.sum(case((Score.is_correct.is_(True), Round.points), else_=0))).join(Round).filter(
            Round.event_id == event_id).group_by(Score.school_id, Score.round_id).all()
        self.values = {(sid, rid): (count, points) for sid, rid, count, points in rows}

    def points(self, school_id, round_id):
        return self.values.get((school_id, round_id), (0, 0))[1]

    def answered(self, school_id, round_id):
        return self.values.get((school_id, round_id), (0, 0))[0]
