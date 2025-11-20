from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, make_response
from flask_login import login_required, current_user
from .models import User, Event, School, Round, Score
from . import db
from sqlalchemy import func
from werkzeug.security import generate_password_hash
from fpdf import FPDF

views = Blueprint('views', __name__)

# --- HELPER ---
def set_active_event(event_id):
    Event.query.update({Event.is_active: False})
    event = Event.query.get(event_id)
    if event:
        event.is_active = True
        db.session.commit()
        return True
    return False

# --- GENERAL ROUTES ---
@views.route('/')
def home():
    return render_template("home.html")

# --- VIEWER LEADERBOARD ---
@views.route('/leaderboard')
def leaderboard():
    active_event = Event.query.filter_by(is_active=True).first()
    if not active_event: return render_template('viewer/leaderboard.html', event=None)

    active_round = Round.query.filter_by(event_id=active_event.id, is_active=True).first()
    
    # --- 1. DETERMINE COLUMNS TO SHOW ---
    display_rounds = []
    final_round = Round.query.filter_by(event_id=active_event.id, is_final=True).first()
    is_hybrid_final = False

    if active_event.scoring_type == 'hybrid':
        # Check if we are in the Final Phase
        # (Active round is Final, or Active is a Tie Breaker for Final, or Final is done)
        if active_round and (active_round.is_final or (final_round and active_round.number == final_round.number)):
            is_hybrid_final = True
            
            # Column 1: The Final Round
            if final_round: display_rounds.append(final_round)
            
            # Column 2: The Tie Breaker (if active)
            if 'Tie Breaker' in active_round.difficulty:
                display_rounds.append(active_round)
        else:
            # Normal Phase: Show all Cumulative Rounds (Exclude Final, Exclude Tie Breakers)
            all_rounds = Round.query.filter_by(event_id=active_event.id).order_by(Round.number.asc()).all()
            display_rounds = [r for r in all_rounds if not r.is_final and 'Tie Breaker' not in r.difficulty]
            
    else:
        # Standard Cumulative/Per Round Behavior
        all_rounds = Round.query.filter_by(event_id=active_event.id).order_by(Round.number.asc()).all()
        display_rounds = [r for r in all_rounds if 'Tie Breaker' not in r.difficulty]


    # --- 2. CALCULATE SCORES ---
    schools = School.query.filter_by(event_id=active_event.id).all()
    rankings = []
    
    for school in schools:
        round_scores = {}
        primary_score = 0   # Used for Total/Final Column
        secondary_score = 0 # Used for Tie Breakers
        
        if is_hybrid_final:
            # Hybrid Final Mode: 
            # Score = Final Round Score (+ Tie Breaker Score for sorting only)
            
            # A. Final Round Score
            if final_round:
                f_points = sum(s.round.points for s in school.scores 
                               if s.round_id == final_round.id and s.is_correct)
                round_scores[final_round.difficulty] = f_points
                primary_score = f_points
            
            # B. Tie Breaker Score (if active)
            if active_round and 'Tie Breaker' in active_round.difficulty:
                tb_points = sum(s.round.points for s in school.scores 
                                if s.round_id == active_round.id and s.is_correct)
                round_scores[active_round.difficulty] = tb_points
                secondary_score = tb_points

        else:
            # Cumulative Mode
            for r in display_rounds:
                r_points = sum(s.round.points for s in school.scores 
                               if s.round_id == r.id and s.is_correct)
                round_scores[r.difficulty] = r_points
                
                # Accumulate if allowed
                if active_event.scoring_type == 'cumulative' or (active_event.scoring_type == 'hybrid' and not is_hybrid_final):
                    primary_score += r_points
                elif active_event.scoring_type == 'per_round':
                    # Only count if it's the active round
                    if active_round and r.id == active_round.id:
                        primary_score = r_points

        rankings.append({
            'name': school.name,
            'total': primary_score,         # Displayed in Gold Column
            'sort_key': (primary_score, secondary_score), # Tuple for sorting
            'breakdown': round_scores
        })

    # Sort by Primary then Secondary
    rankings.sort(key=lambda x: x['sort_key'], reverse=True)

    return render_template('viewer/leaderboard.html', 
                           event=active_event, 
                           rankings=rankings, 
                           rounds=display_rounds,
                           active_round=active_round,
                           is_hybrid_final=is_hybrid_final)

# --- ADMIN ROUTES ---

@views.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin': return "Unauthorized", 403
    return render_template('admin/admin_dashboard.html')

@views.route('/admin/register-user', methods=['GET', 'POST'])
@login_required
def register_user():
    if current_user.role != 'admin': return "Unauthorized", 403

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        first_name = request.form.get('first_name')

        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists.', category='error')
        else:
            new_user = User(
                username=username,
                password=generate_password_hash(password),
                role=role,
                first_name=first_name
            )
            db.session.add(new_user)
            db.session.commit()
            flash('User created successfully!', category='success')
            return redirect(url_for('views.register_user'))

    all_users = User.query.all()
    return render_template('admin/register_user.html', users=all_users)

@views.route('/admin/user/edit/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    user = User.query.get_or_404(user_id)
    
    new_username = request.form.get('username')
    new_name = request.form.get('first_name')
    new_pass = request.form.get('password')
    
    if new_username: user.username = new_username
    if new_name: user.first_name = new_name
    if new_pass: 
        user.password = generate_password_hash(new_pass)
        
    db.session.commit()
    flash('User account updated.', 'success')
    return redirect(url_for('views.register_user'))

# --- EVENT MANAGEMENT ---

@views.route('/admin/event-registration', methods=['GET', 'POST'])
@login_required
def event_registration():
    if current_user.role != 'admin': return "Unauthorized", 403
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_event':
            name = request.form.get('name')
            is_active = request.form.get('is_active') == 'on'
            scoring_type = request.form.get('scoring_type')
            
            if not name:
                flash('Event name is required.', category='error')
            else:
                new_event = Event(name=name, is_active=is_active, scoring_type=scoring_type)
                db.session.add(new_event)
                db.session.commit()
                if is_active: set_active_event(new_event.id)
                flash(f'Event "{name}" created successfully.', category='success')
                return redirect(url_for('views.round_setup', event_id=new_event.id))
            
        elif action == 'set_active':
            event_id = request.form.get('event_id')
            if set_active_event(event_id): flash('Active event updated.', category='success')
            else: flash('Error setting active event.', category='error')
            
        elif action == 'deactivate':
            event_id = request.form.get('event_id')
            event = Event.query.get(event_id)
            if event:
                event.is_active = False
                db.session.commit()
                flash(f'Event "{event.name}" deactivated.', category='info')
    
    events = Event.query.order_by(Event.id.desc()).all()
    active_event = Event.query.filter_by(is_active=True).first()
    return render_template('admin/event_registration.html', events=events, active_event=active_event)

@views.route('/admin/event/delete/<int:event_id>', methods=['POST'])
@login_required
def delete_event(event_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    event = Event.query.get_or_404(event_id)
    if event.is_active:
        flash('Cannot delete active event.', category='error')
    else:
        db.session.delete(event)
        db.session.commit()
        flash('Event deleted.', category='success')
    return redirect(url_for('views.event_registration'))

@views.route('/admin/event/edit/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    event = Event.query.get_or_404(event_id)
    if request.method == 'POST':
        event.name = request.form.get('name')
        db.session.commit()
        flash('Event updated.', category='success')
        return redirect(url_for('views.event_registration'))
    return render_template('admin/event_edit.html', event=event)

# --- SCHOOLS ---

@views.route('/admin/school-registration/<int:event_id>', methods=['GET', 'POST'])
@login_required
def school_registration(event_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    event = Event.query.get_or_404(event_id)

    if request.method == 'POST':
        school_name = request.form.get('school_name')
        tabulator_id = request.form.get('tabulator_id') 

        school_exists = School.query.filter_by(name=school_name, event_id=event.id).first()
        existing_assignment = School.query.filter_by(event_id=event.id, user_id=tabulator_id).first()

        if school_exists:
            flash(f'School "{school_name}" is already registered.', category='error')
        elif existing_assignment:
            flash(f'Tabulator already assigned to "{existing_assignment.name}" in this event.', category='error')
        else:
            new_school = School(name=school_name, event_id=event.id, user_id=tabulator_id)
            db.session.add(new_school)
            db.session.commit()
            flash(f'School "{school_name}" added.', category='success')
            return redirect(url_for('views.school_registration', event_id=event.id))

    schools = School.query.filter_by(event_id=event.id).all()
    all_tabulators = User.query.filter_by(role='tabulator').all()
    return render_template('admin/school_registration.html', event=event, schools=schools, all_tabulators=all_tabulators)

@views.route('/admin/school/edit/<int:school_id>', methods=['POST'])
@login_required
def edit_school(school_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    school = School.query.get_or_404(school_id)
    new_name = request.form.get('school_name')
    new_tab_id = request.form.get('tabulator_id')
    
    if new_name: school.name = new_name
    if new_tab_id: school.user_id = new_tab_id
    db.session.commit()
    flash('School details updated.', 'success')
    return redirect(url_for('views.school_registration', event_id=school.event_id))

@views.route('/admin/school/delete/<int:school_id>', methods=['POST'])
@login_required
def delete_school(school_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    school = School.query.get_or_404(school_id)
    event_id = school.event_id
    db.session.delete(school)
    db.session.commit()
    flash('School removed.', category='success')
    return redirect(url_for('views.school_registration', event_id=event_id))

# --- ROUNDS CONFIGURATION ---

@views.route('/admin/round-setup/<int:event_id>', methods=['GET', 'POST'])
@login_required
def round_setup(event_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    event = Event.query.get_or_404(event_id)

    if request.method == 'POST':
        difficulty = request.form.get('difficulty')
        points = request.form.get('points')
        total_questions = request.form.get('total_questions')
        round_number = request.form.get('round_number')
        qualifying_count = request.form.get('qualifying_count')
        is_final = request.form.get('is_final') == 'on'

        new_round = Round(
            event_id=event.id,
            number=round_number,
            difficulty=difficulty,
            points=points,
            total_questions=total_questions,
            qualifying_count=int(qualifying_count) if qualifying_count else 0,
            is_final=is_final
        )
        db.session.add(new_round)
        db.session.commit()
        flash('Round added.', category='success')
        return redirect(url_for('views.round_setup', event_id=event.id))

    rounds = Round.query.filter_by(event_id=event.id).order_by(Round.number.asc()).all()
    return render_template('admin/round_setup.html', event=event, rounds=rounds)

@views.route('/admin/round/edit/<int:round_id>', methods=['POST'])
@login_required
def edit_round(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    round_obj = Round.query.get_or_404(round_id)
    
    round_obj.number = request.form.get('round_number')
    round_obj.difficulty = request.form.get('difficulty')
    round_obj.points = request.form.get('points')
    round_obj.total_questions = request.form.get('total_questions')
    q_count = request.form.get('qualifying_count')
    round_obj.qualifying_count = int(q_count) if q_count else 0
    round_obj.is_final = request.form.get('is_final') == 'on'
    
    db.session.commit()
    flash('Round details updated.', category='success')
    return redirect(url_for('views.round_setup', event_id=round_obj.event_id))

@views.route('/admin/round/delete/<int:round_id>', methods=['POST'])
@login_required
def delete_round(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    round_obj = Round.query.get_or_404(round_id)
    event_id = round_obj.event_id
    db.session.delete(round_obj)
    db.session.commit()
    flash('Round deleted.', category='success')
    return redirect(url_for('views.round_setup', event_id=event_id))


# --- LIVE ROUND CONTROL ---

@views.route('/admin/round-control')
@login_required
def round_control():
    if current_user.role != 'admin': return "Unauthorized", 403
    active_event = Event.query.filter_by(is_active=True).first()
    if not active_event: return redirect(url_for('views.event_registration'))

    rounds = Round.query.filter_by(event_id=active_event.id).order_by(Round.number.asc()).all()
    active_round = Round.query.filter_by(event_id=active_event.id, is_active=True).first()
    
    live_scores = []
    round_fully_completed = False 
    previous_rounds = []
    show_cumulative = False
    
    if active_round:
        # --- 1. DETERMINE SCORING MODE & COLUMNS ---
        
        final_round = Round.query.filter_by(event_id=active_event.id, is_final=True).first()
        
        if active_event.scoring_type == 'hybrid':
            # Check if in Final Phase
            if active_round.is_final or (final_round and active_round.number == final_round.number):
                # HYBRID FINAL: No history, just Final Round (+ Active Tie Breaker)
                show_cumulative = False
                if 'Tie Breaker' in active_round.difficulty:
                    previous_rounds = [final_round] # Show Final Round as context
                else:
                    previous_rounds = [] # Just show active (Final)
            else:
                # HYBRID NORMAL: Show cumulative history
                show_cumulative = True
                previous_rounds = Round.query.filter(
                     Round.event_id == active_event.id,
                     Round.number < active_round.number,
                     Round.difficulty.notlike('%Tie Breaker%')
                 ).order_by(Round.number.asc()).all()
                 
        elif active_event.scoring_type == 'cumulative':
            show_cumulative = True
            previous_rounds = Round.query.filter(
                 Round.event_id == active_event.id,
                 Round.number < active_round.number,
                 Round.difficulty.notlike('%Tie Breaker%')
             ).order_by(Round.number.asc()).all()
             
        # --- 2. FETCH PARTICIPANTS ---
        all_schools = School.query.filter_by(event_id=active_event.id).all()
        participating_schools = []

        if active_round.participating_school_ids:
            allowed_ids = active_round.participating_school_ids.split(',')
            participating_schools = [s for s in all_schools if str(s.id) in allowed_ids]
        else:
            participating_schools = all_schools
        
        all_schools_finished = True 
        
        for school in participating_schools:
            # A. Active Round Score
            scores_in_this_round = Score.query.filter_by(school_id=school.id, round_id=active_round.id).all()
            current_round_points = 0
            answered_count = 0
            
            for s in scores_in_this_round:
                answered_count += 1
                if s.is_correct: current_round_points += active_round.points
            
            if answered_count < active_round.total_questions:
                all_schools_finished = False

            # B. Breakdown & Total
            breakdown = {}
            main_score_for_sorting = 0
            
            if show_cumulative:
                for r in previous_rounds:
                    r_score = sum(s.round.points for s in school.scores 
                                  if s.round_id == r.id and s.is_correct)
                    breakdown[r.id] = r_score
                    main_score_for_sorting += r_score
                main_score_for_sorting += current_round_points
                
            elif active_event.scoring_type == 'hybrid' and not show_cumulative:
                # Hybrid Final Phase Logic
                # If Tie Breaker is active: Previous(Final) + Current(TB) displayed
                # Sort by Final Score (Primary) -> Tie Breaker Score (Secondary)
                
                if 'Tie Breaker' in active_round.difficulty and final_round:
                     final_score = sum(s.round.points for s in school.scores 
                                       if s.round_id == final_round.id and s.is_correct)
                     breakdown[final_round.id] = final_score
                     
                     # Tuple Sort: (Final Score, Tie Breaker Score)
                     # We pack this into main_score_for_sorting as a tuple? No, Python sort key.
                     # Let's use a separate sort key.
                     main_score_for_sorting = (final_score, current_round_points)
                else:
                     # Just Final Round
                     main_score_for_sorting = (current_round_points, 0)
            
            else:
                # Per Round
                main_score_for_sorting = current_round_points

            live_scores.append({
                'school_id': school.id,
                'school': school.name,
                'current_score': current_round_points,
                'total_score': main_score_for_sorting, # Can be int or tuple
                'breakdown': breakdown,
                'answered': answered_count,
                'total_q': active_round.total_questions
            })
            
        # SORTING
        # Handle tuple vs int sorting
        if isinstance(live_scores[0]['total_score'], tuple) if live_scores else False:
             live_scores.sort(key=lambda x: x['total_score'], reverse=True)
        else:
             live_scores.sort(key=lambda x: x['total_score'], reverse=True)
        
        if participating_schools and all_schools_finished:
            round_fully_completed = True

    return render_template('admin/round_control.html', 
                           event=active_event, 
                           rounds=rounds, 
                           active_round=active_round, 
                           live_scores=live_scores,
                           previous_rounds=previous_rounds,
                           show_cumulative=show_cumulative,
                           round_fully_completed=round_fully_completed)

@views.route('/admin/round/activate/<int:round_id>', methods=['POST'])
@login_required
def activate_round(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    target_round = Round.query.get_or_404(round_id)
    all_rounds = Round.query.filter_by(event_id=target_round.event_id).all()
    for r in all_rounds: r.is_active = False
    target_round.is_active = True
    db.session.commit()
    flash(f'{target_round.difficulty} Round is LIVE.', category='success')
    return redirect(url_for('views.round_control'))

@views.route('/admin/round/stop/<int:round_id>', methods=['POST'])
@login_required
def stop_round(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    round_obj = Round.query.get_or_404(round_id)
    round_obj.is_active = False
    db.session.commit()
    flash('Round stopped.', category='warning')
    return redirect(url_for('views.round_control'))

@views.route('/admin/round/add-question/<int:round_id>', methods=['POST'])
@login_required
def add_question(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    current_round = Round.query.get_or_404(round_id)
    current_round.total_questions += 1
    db.session.commit()
    flash(f'Question added! Total: {current_round.total_questions}.', category='success')
    return redirect(url_for('views.round_control'))

# --- EVALUATION & ADVANCEMENT (UPDATED HYBRID LOGIC) ---

@views.route('/admin/round/evaluate/<int:round_id>', methods=['POST'])
@login_required
def evaluate_round(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    current_round = Round.query.get_or_404(round_id)
    event_id = current_round.event_id
    cutoff = current_round.qualifying_count
    event = Event.query.get(event_id)
    
    if cutoff == 0:
        flash('No qualifying limit set. Proceed manually.', category='info')
        return redirect(url_for('views.round_control'))

    # 1. CALCULATE SCORES
    all_schools = School.query.filter_by(event_id=event_id).all()
    standings = []
    
    participating_schools = []
    if current_round.participating_school_ids:
        allowed_ids = current_round.participating_school_ids.split(',')
        participating_schools = [s for s in all_schools if str(s.id) in allowed_ids]
    else:
        participating_schools = all_schools

    for school in participating_schools:
        score_val = 0
        
        if 'Tie Breaker' in current_round.difficulty:
            # Sudden Death: Only this round matters
            score_val = sum(s.round.points for s in school.scores 
                            if s.round_id == current_round.id and s.is_correct)
        
        elif event.scoring_type == 'hybrid':
            if current_round.is_final:
                # Hybrid Final: Back to Zero
                score_val = sum(s.round.points for s in school.scores 
                                if s.round_id == current_round.id and s.is_correct)
            else:
                # Hybrid Normal: Cumulative
                for s in school.scores:
                    if (s.round.event_id == event.id and 
                        s.round.number <= current_round.number and 
                        'Tie Breaker' not in s.round.difficulty and 
                        s.is_correct):
                        score_val += s.round.points

        elif event.scoring_type == 'cumulative':
            for s in school.scores:
                if (s.round.event_id == event.id and 
                    s.round.number <= current_round.number and 
                    'Tie Breaker' not in s.round.difficulty and 
                    s.is_correct):
                    score_val += s.round.points
        else:
            score_val = sum(s.round.points for s in school.scores 
                            if s.round_id == current_round.id and s.is_correct)
        
        standings.append({'school': school, 'score': score_val})
    
    standings.sort(key=lambda x: x['score'], reverse=True)

    # 2. STRICT RANKING (HYBRID FINAL)
    if event.scoring_type == 'hybrid' and current_round.is_final and 'Tie Breaker' not in current_round.difficulty:
        # Check for ANY ties
        for i in range(len(standings) - 1):
            if standings[i]['score'] == standings[i+1]['score']:
                rank_num = i + 1
                tied_score = standings[i]['score']
                tied_group = [s['school'] for s in standings if s['score'] == tied_score]
                ids_string = ",".join([str(s.id) for s in tied_group])
                
                tb_round = Round(
                    event_id=event.id, number=current_round.number, 
                    difficulty=f"Tie Breaker (For Rank {rank_num})",
                    points=1, total_questions=1, participating_school_ids=ids_string,
                    qualifying_count=1, is_active=False, is_final=True
                )
                db.session.add(tb_round)
                db.session.commit()
                flash(f"⚠️ STRICT RANKING: Tie detected for Rank {rank_num}. Tie Breaker created.", category='warning')
                return redirect(url_for('views.round_control'))
        
        # If no ties, declare winners
        qualified_schools = [s['school'] for s in standings[:cutoff]] if cutoff > 0 else [s['school'] for s in standings]
        winner_names = ", ".join([s.name for s in qualified_schools])
        flash(f"🏆 FINAL RESULTS OFFICIAL: {winner_names}", category='success')
        return redirect(url_for('views.final_results', event_id=event.id))

    # 3. STANDARD TIE DETECTION (AT CUTOFF)
    if len(standings) > cutoff and cutoff > 0:
        boundary_score = standings[cutoff - 1]['score']
        next_score = standings[cutoff]['score']
        
        if boundary_score == next_score:
             if 'Tie Breaker' in current_round.difficulty:
                 flash("⚠️ CANNOT ADVANCE! Tie for final spot. Add +1 Question.", category='error')
                 return redirect(url_for('views.round_control'))
             
             tied_schools = [s['school'] for s in standings if s['score'] == boundary_score]
             ids_string = ",".join([str(s.id) for s in tied_schools])
             clean_winners = [s for s in standings if s['score'] > boundary_score]
             slots = cutoff - len(clean_winners)
             
             tb_round = Round(
                 event_id=event.id, number=current_round.number, 
                 difficulty=f"Tie Breaker ({current_round.difficulty})",
                 points=1, total_questions=1, participating_school_ids=ids_string,
                 qualifying_count=slots, is_active=False, is_final=current_round.is_final
             )
             db.session.add(tb_round)
             db.session.commit()
             flash(f"Tie detected at cutoff. Tie breaker created for {slots} spots.", category='warning')
             return redirect(url_for('views.round_control'))
             
        qualified_schools = [s['school'] for s in standings[:cutoff]]
    else:
        qualified_schools = [s['school'] for s in standings]
    
    # 4. MERGE & PUSH
    final_advancing_schools = qualified_schools
    
    if 'Tie Breaker' in current_round.difficulty:
        parent_round = Round.query.filter(
            Round.event_id == event_id,
            Round.number == current_round.number,
            Round.difficulty.notlike('%Tie Breaker%')
        ).first()

        if parent_round:
            # Recalculate Parent Standings (needed to find Clean Winners)
            clean_spots = parent_round.qualifying_count - current_round.qualifying_count
            p_schools = School.query.filter_by(event_id=event_id).all()
            p_standings = []
            for s in p_schools:
                if parent_round.participating_school_ids and str(s.id) not in parent_round.participating_school_ids.split(','): continue
                
                sc = 0
                # Use parent's scoring context logic
                is_parent_final = parent_round.is_final
                if event.scoring_type == 'hybrid' and is_parent_final:
                     sc = sum(score.round.points for s in s.scores if Score.round_id == parent_round.id and score.is_correct)
                elif event.scoring_type == 'cumulative' or (event.scoring_type == 'hybrid' and not is_parent_final):
                    for score in s.scores:
                         if (score.round.event_id == event.id and score.round.number <= parent_round.number and 'Tie Breaker' not in score.round.difficulty and score.is_correct):
                             sc += score.round.points
                else:
                    sc = sum(score.round.points for s in s.scores if score.round_id == parent_round.id and score.is_correct)
                
                p_standings.append({'school': s, 'score': sc})
            
            p_standings.sort(key=lambda x: x['score'], reverse=True)
            clean_winners = [x['school'] for x in p_standings[:clean_spots]]
            final_advancing_schools = clean_winners + qualified_schools

    # Finalize
    is_event_over = current_round.is_final or ('Tie Breaker' in current_round.difficulty and 'Final' in current_round.difficulty)
    
    if is_event_over:
        return redirect(url_for('views.final_results', event_id=event.id))
    else:
        next_round = Round.query.filter(Round.event_id == event.id, Round.number > current_round.number).order_by(Round.number.asc()).first()
        if next_round:
            ids = ",".join([str(s.id) for s in final_advancing_schools])
            next_round.participating_school_ids = ids
            db.session.commit()
            flash('Advanced to next round.', 'success')
        else:
            flash('Evaluation complete. No next round found.', 'warning')

    return redirect(url_for('views.round_control'))


# --- RESULTS & PDF ---

@views.route('/admin/final-results/<int:event_id>')
@login_required
def final_results(event_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    event = Event.query.get_or_404(event_id)
    
    schools = School.query.filter_by(event_id=event.id).all()
    rankings = []
    for school in schools:
        total_points = 0
        if event.scoring_type == 'hybrid':
             final_round = Round.query.filter_by(event_id=event.id, is_final=True).first()
             if final_round:
                 total_points = sum(s.round.points for s in school.scores 
                                   if s.round_id == final_round.id and s.is_correct)
        elif event.scoring_type == 'cumulative':
            for s in school.scores:
                if (s.round.event_id == event.id and 'Tie Breaker' not in s.round.difficulty and s.is_correct):
                    total_points += s.round.points
        else:
             final_round = Round.query.filter_by(event_id=event.id, is_final=True).first()
             if final_round:
                total_points = sum(s.round.points for s in school.scores if s.round_id == final_round.id and s.is_correct)
        
        rankings.append({'name': school.name, 'score': total_points})

    rankings.sort(key=lambda x: x['score'], reverse=True)

    tabulators = db.session.query(User).join(School).filter(School.event_id == event.id).all()
    unique_tabulators = list({t.id: t for t in tabulators}.values())

    return render_template('admin/final_results.html', event=event, rankings=rankings, tabulators=unique_tabulators, admin=current_user)

@views.route('/admin/final-results/pdf/<int:event_id>')
@login_required
def download_results_pdf(event_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    event = Event.query.get_or_404(event_id)
    
    # --- 1. PREPARE ROUND COLUMNS ---
    # Fetch all rounds to create dynamic table headers
    all_rounds = Round.query.filter_by(event_id=event.id).order_by(Round.number.asc()).all()
    # We usually exclude Tie Breakers from the main columns to keep the table clean
    round_columns = [r for r in all_rounds if 'Tie Breaker' not in r.difficulty]

    # --- 2. CALCULATE RANKINGS & BREAKDOWN ---
    schools = School.query.filter_by(event_id=event.id).all()
    rankings = []
    
    for school in schools:
        total_points = 0
        round_breakdown = {} # Store scores per round ID
        
        # A. Calculate Score for EACH Round Column
        for r in round_columns:
            r_score = sum(s.round.points for s in school.scores 
                          if s.round_id == r.id and s.is_correct)
            round_breakdown[r.id] = r_score

        # B. Calculate Final Ranking Score (Total) based on Event Type
        if event.scoring_type == 'hybrid':
             final_round = Round.query.filter_by(event_id=event.id, is_final=True).first()
             if final_round:
                 total_points = sum(s.round.points for s in school.scores 
                                   if s.round_id == final_round.id and s.is_correct)
             else:
                 # Fallback
                 total_points = sum(s.round.points for s in school.scores 
                                   if s.round.event_id == event.id and 'Tie Breaker' not in s.round.difficulty and s.is_correct)
        elif event.scoring_type == 'cumulative':
            for s in school.scores:
                if (s.round.event_id == event.id and 'Tie Breaker' not in s.round.difficulty and s.is_correct):
                    total_points += s.round.points
        else: # Per Round
             final_round = Round.query.filter_by(event_id=event.id, is_final=True).first()
             if final_round:
                total_points = sum(s.round.points for s in school.scores if s.round_id == final_round.id and s.is_correct)
        
        rankings.append({
            'name': school.name, 
            'score': total_points, 
            'breakdown': round_breakdown
        })

    rankings.sort(key=lambda x: x['score'], reverse=True)

    # --- 3. SIGNATORIES ---
    tabulators = db.session.query(User).join(School).filter(School.event_id == event.id).all()
    unique_tabulators = list({t.id: t for t in tabulators}.values())
    admin_signatories = User.query.filter(User.role == 'admin', User.username != 'admin1').all()

    # --- 4. FPDF GENERATION (LANDSCAPE) ---
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, event.name, 0, 1, 'C')
            self.set_font('Arial', 'I', 10)
            self.cell(0, 10, 'Official Final Results', 0, 1, 'C')
            self.ln(5)
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    # Initialize PDF in Landscape ('L') to fit more columns
    pdf = PDF(orientation='L', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- DYNAMIC WIDTH CALCULATION ---
    # A4 Landscape width = 297mm. Margins default ~10mm each side.
    # Effective width approx 277mm.
    effective_page_width = pdf.w - 2 * pdf.l_margin
    
    w_rank = 15
    w_total = 30
    w_round = 25 # Width per round column
    
    # Calculate remaining space for School Name
    # If too many rounds, w_school might get too small, but Landscape helps.
    w_school = effective_page_width - w_rank - w_total - (len(round_columns) * w_round)
    
    # Safety check: Ensure school name has at least 60mm
    if w_school < 60:
        w_round = (effective_page_width - w_rank - w_total - 60) / len(round_columns)
        w_school = 60

    # --- TABLE HEADER ---
    pdf.set_font("Arial", 'B', 11)
    pdf.set_fill_color(230, 230, 230)
    
    pdf.cell(w_rank, 10, "Rank", 1, 0, 'C', True)
    pdf.cell(w_school, 10, "School / Candidate", 1, 0, 'C', True)
    
    # Dynamic Round Headers
    for r in round_columns:
        # Truncate name if too long for the column
        col_name = r.difficulty[:10] 
        pdf.cell(w_round, 10, col_name, 1, 0, 'C', True)
        
    pdf.cell(w_total, 10, "Final Score", 1, 1, 'C', True)

    # --- TABLE BODY ---
    pdf.set_font("Arial", '', 11)
    
    for i, rank in enumerate(rankings):
        rank_str = f"{i+1}"
        if i == 0: rank_str = "1st"
        elif i == 1: rank_str = "2nd"
        elif i == 2: rank_str = "3rd"
        
        pdf.cell(w_rank, 10, rank_str, 1, 0, 'C')
        pdf.cell(w_school, 10, rank['name'], 1, 0, 'L')
        
        # Dynamic Round Scores
        for r in round_columns:
            score_val = str(rank['breakdown'].get(r.id, 0))
            pdf.cell(w_round, 10, score_val, 1, 0, 'C')
            
        pdf.cell(w_total, 10, str(rank['score']), 1, 1, 'C')
    
    pdf.ln(20)

    # --- SIGNATORIES (Grid Layout) ---
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 10, "Certified Correct & Verified By:", 0, 1, 'C')
    pdf.ln(10)

    col_count_max = 3
    col_width = effective_page_width / col_count_max
    row_height = 35
    current_y = pdf.get_y()

    def draw_signature_grid(signatories_list, title):
        nonlocal current_y
        chunks = [signatories_list[i:i + col_count_max] for i in range(0, len(signatories_list), col_count_max)]
        for chunk in chunks:
            if current_y + row_height > 190: # Lower limit for Landscape height (~210mm)
                pdf.add_page()
                current_y = pdf.get_y()
            
            num_in_row = len(chunk)
            row_content_width = num_in_row * col_width
            empty_space = effective_page_width - row_content_width
            start_x = pdf.l_margin + (empty_space / 2)

            for i, person in enumerate(chunk):
                display_name = (person.first_name if person.first_name else person.username).upper()
                x_pos = start_x + (i * col_width)
                line_width = col_width * 0.6 # Smaller lines for Landscape balance
                line_start_x = x_pos + (col_width - line_width) / 2
                
                pdf.line(line_start_x, current_y + 15, line_start_x + line_width, current_y + 15)
                pdf.set_xy(x_pos, current_y + 16)
                pdf.set_font("Arial", 'B', 9)
                pdf.cell(col_width, 5, display_name, 0, 2, 'C')
                pdf.set_font("Arial", 'I', 7)
                pdf.cell(col_width, 4, title, 0, 0, 'C')
            current_y += row_height

    pdf.set_font("Arial", '', 10)
    draw_signature_grid(unique_tabulators, "Official Tabulator")
    current_y += 10
    
    if admin_signatories:
        draw_signature_grid(admin_signatories, "Administrator")
    else:
        # Fallback for single admin
        if current_y + row_height > 190: pdf.add_page(); current_y = pdf.get_y()
        admin_line_width = 80
        admin_line_start = (pdf.w - admin_line_width) / 2
        pdf.line(admin_line_start, current_y + 15, admin_line_start + admin_line_width, current_y + 15)
        pdf.set_xy(0, current_y + 16)
        pdf.set_font("Arial", 'B', 10)
        name = (current_user.first_name if current_user.first_name else current_user.username).upper()
        pdf.cell(0, 5, name, 0, 1, 'C')
        pdf.set_font("Arial", 'I', 7)
        pdf.cell(0, 4, "Head Administrator", 0, 1, 'C')

    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Results_{event.id}.pdf'
    return response


# --- TABULATOR ---

@views.route('/tabulator/dashboard')
@login_required
def tabulator_dashboard():
    if current_user.role != 'tabulator': return "Unauthorized", 403
    active_event = Event.query.filter_by(is_active=True).first()
    school = None
    rounds = []
    if active_event:
        school = School.query.filter_by(event_id=active_event.id, user_id=current_user.id).first()
        rounds = active_event.rounds
    return render_template('tabulator/tabulator_dashboard.html', school=school, active_event=active_event, rounds=rounds)

@views.route('/tabulator/scoring/<int:round_id>', methods=['GET', 'POST'])
@login_required
def scoring(round_id):
    if current_user.role != 'tabulator': return "Unauthorized", 403
    current_round = Round.query.get_or_404(round_id)
    
    if not current_round.is_active:
        flash(f'The {current_round.difficulty} Round is currently closed.', category='error')
        return redirect(url_for('views.tabulator_dashboard'))

    school = School.query.filter_by(event_id=current_round.event_id, user_id=current_user.id).first()
    if not school:
        flash("You are not assigned to any school for this specific event.", category='error')
        return redirect(url_for('views.tabulator_dashboard'))

    if not current_round.is_school_allowed(school.id):
        flash("Your school is not participating in this specific round.", category='warning')
        return redirect(url_for('views.tabulator_dashboard'))

    if request.method == 'POST':
        for q_num in range(1, current_round.total_questions + 1):
            answer_status = request.form.get(f'question_{q_num}')
            if answer_status:
                is_correct_val = (answer_status == 'correct')
                existing_score = Score.query.filter_by(
                    school_id=school.id, round_id=current_round.id, question_number=q_num).first()
                if existing_score: existing_score.is_correct = is_correct_val
                else:
                    new_score = Score(school_id=school.id, round_id=current_round.id, 
                                      question_number=q_num, is_correct=is_correct_val)
                    db.session.add(new_score)
        db.session.commit()
        flash('Scores saved successfully!', category='success')
        return redirect(url_for('views.scoring', round_id=current_round.id))

    existing_scores = Score.query.filter_by(school_id=school.id, round_id=current_round.id).all()
    score_map = {s.question_number: s.is_correct for s in existing_scores}
    return render_template('tabulator/scoring.html', school=school, round=current_round, 
                           total_questions=current_round.total_questions, score_map=score_map)