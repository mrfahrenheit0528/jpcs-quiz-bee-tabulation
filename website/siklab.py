"""Projection standings, calculated directly from committed answers."""
from .models import Event, Round, School
from .scoring import EventTotals


def standings():
    event = Event.query.filter_by(is_active=True).first()
    if not event:
        return dict(event=None, rankings=[], stage=None, active_round=None)

    rounds = Round.query.filter_by(event_id=event.id).order_by(Round.number, Round.id).all()
    totals = EventTotals(event.id)
    active = next((r for r in rounds if r.is_active), None)
    scored_ids = {rid for (_, rid) in totals.values}
    stage = active or next((r for r in reversed(rounds) if r.id in scored_ids), None)
    schools = School.query.filter_by(event_id=event.id).order_by(School.name, School.id).all()

    def is_extra(r):
        return 'Clincher' in r.difficulty or 'Tie Breaker' in r.difficulty

    # Extra rounds resolve a tie in their parent stage; they do not reset its scores.
    base = stage
    if stage and is_extra(stage):
        base = next((r for r in rounds if r.number == stage.number and not is_extra(r)), stage)
    history = [r for r in rounds if not is_extra(r) and base and r.number <= base.number]
    clean_slate = event.scoring_type == 'per_round' or (
        event.scoring_type == 'hybrid' and base and base.is_final)
    extras = [r for r in rounds if stage and base and is_extra(r)
              and r.number == base.number and r.id <= stage.id
              and (r.id in scored_ids or r.id == stage.id)]
    # Inactive rounds with saved results remain visible, including elimination
    # rounds during a clean-slate final. Unplayed rounds have no score rows.
    display_rounds = [r for r in rounds if r.is_active or r.id in scored_ids]
    rankings = []
    for school in schools:
        eligible = bool(base and base.is_school_allowed(school.id))
        points = (totals.points(school.id, base.id) if clean_slate and base else
                  sum(totals.points(school.id, r.id) for r in history))
        tie_scores = tuple(totals.points(school.id, r.id) if r.is_school_allowed(school.id)
                           else -1 for r in extras)
        rankings.append(dict(
            id=school.id, name=school.name, points=points, eligible=eligible,
            round_points=totals.points(school.id, stage.id) if stage else 0,
            in_stage=bool(stage and stage.is_school_allowed(school.id)),
            breakdown={r.id: totals.points(school.id, r.id) for r in display_rounds},
            sort_key=(eligible, points, tie_scores),
        ))
    rankings.sort(key=lambda row: row['sort_key'], reverse=True)
    previous = None
    for index, row in enumerate(rankings, 1):
        if row['sort_key'] != previous:
            rank = index
        row['rank'] = rank
        previous = row['sort_key']
    return dict(event=event, rankings=rankings, stage=stage, active_round=active,
                rounds=display_rounds,
                score_label='ROUND SCORE' if clean_slate else 'TOTAL POINTS')
