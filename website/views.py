from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, make_response, current_app
from flask_login import login_required, current_user
from .models import User, Event, School, Round, Score
from . import db
from sqlalchemy import func
from werkzeug.security import generate_password_hash
from fpdf import FPDF
from itertools import groupby 
import os
import socket
import qrcode
import io
from flask import send_file

views = Blueprint('views', __name__)

def to_ordinal(n):
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"

def set_active_event(event_id):
    Event.query.update({Event.is_active: False})
    event = Event.query.get(event_id)
    if event:
        event.is_active = True
        db.session.commit()
        return True
    return False

def get_network_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

@views.route('/')
def home():
    return render_template("home.html")

@views.route('/about')
def about():
    return render_template("about.html")

# --- VIEWER LEADERBOARD (FIXED SORTING) ---
@views.route('/leaderboard')
def leaderboard():
    active_event = Event.query.filter_by(is_active=True).first()
    if not active_event: return render_template('viewer/leaderboard.html', event=None)

    active_round = Round.query.filter_by(event_id=active_event.id, is_active=True).first()
    
    # --- 1. IDENTIFY PHASE AND COLUMNS ---
    display_rounds = []
    clincher_rounds = []
    final_round = Round.query.filter_by(event_id=active_event.id, is_final=True).first()
    
    # Fetch ALL rounds for calculation history (Even if not displayed)
    all_rounds_ordered = Round.query.filter_by(event_id=active_event.id).order_by(Round.number.asc()).all()
    cumulative_history_rounds = [r for r in all_rounds_ordered if not r.is_final and 'Clincher' not in r.difficulty and 'Tie Breaker' not in r.difficulty]

    # Check Phase
    is_hybrid_final = False
    if active_event.scoring_type == 'hybrid':
        if active_round and (active_round.is_final or (final_round and active_round.number == final_round.number)):
            is_hybrid_final = True
        elif final_round and not active_round: 
            if Score.query.filter_by(round_id=final_round.id).first():
                is_hybrid_final = True

    if is_hybrid_final and final_round:
        display_rounds.append(final_round)
        clincher_rounds = Round.query.filter(
            Round.event_id == active_event.id,
            Round.number == final_round.number,
            Round.difficulty.like('%Clincher%')
        ).order_by(Round.id.asc()).all()
        display_rounds.extend(clincher_rounds)
    else:
        display_rounds = cumulative_history_rounds

    # --- 2. CALCULATE SCORES ---
    schools = School.query.filter_by(event_id=active_event.id).all()
    rankings = []
    
    for school in schools:
        round_scores = {}
        
        # A. Scores for Displayed Columns
        for r in display_rounds:
            r_score = sum(s.round.points for s in school.scores if s.round_id == r.id and s.is_correct)
            round_scores[r.difficulty] = r_score
        
        # B. Calculate Historical Total (For sorting fallback)
        history_total = 0
        for r in cumulative_history_rounds:
            history_total += sum(s.round.points for s in school.scores if s.round_id == r.id and s.is_correct)

        # C. Build Sort Key
        sort_key = []
        is_competing = False
        
        if is_hybrid_final:
            # Priority 1: Is Qualified for Final? (1=Yes, 0=No)
            # This ensures finalists stay above disqualified schools even if scores are 0
            is_qualified = 0
            if final_round and final_round.is_school_allowed(school.id):
                is_qualified = 1
            sort_key.append(is_qualified)
            
            # Priority 2: Scores in Final/Clincher Rounds
            for r in display_rounds:
                sort_key.append(round_scores[r.difficulty])
            
            # Priority 3: Historical Cumulative Total
            # This sorts the disqualified schools (and breaks ties for finalists)
            sort_key.append(history_total)

            # Competing Status
            if active_round and active_round.is_school_allowed(school.id):
                is_competing = True
                
        else:
            # Normal Phase: Sort by Total History
            sort_key = [history_total]
            if active_round and active_round.is_school_allowed(school.id):
                is_competing = True

        # D. Determine Total Display
        if is_hybrid_final and final_round:
             display_total = round_scores.get(final_round.difficulty, 0)
        else:
             display_total = history_total

        rankings.append({
            'id': school.id,
            'name': school.name,
            'total': display_total,
            'breakdown': round_scores,
            'sort_key': tuple(sort_key),
            'is_competing': is_competing
        })

    rankings.sort(key=lambda x: x['sort_key'], reverse=True)

    return render_template('viewer/leaderboard.html', 
                           event=active_event, 
                           rankings=rankings, 
                           rounds=display_rounds,
                           active_round=active_round,
                           is_hybrid_final=is_hybrid_final)

# ... (Keep Admin Routes: dashboard, register_user, edit_user, event_registration, delete_event, edit_event, school routes, round setup routes, round control, activate/stop/add question routes UNCHANGED) ...

@views.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin': return "Unauthorized", 403
    
    server_ip = get_network_ip()
    server_url = f"http://{server_ip}:5000"
    
    return render_template('admin/admin_dashboard.html', server_url=server_url)

# --- QR CODE ROUTE ---
@views.route('/admin/generate-qr')
@login_required
def generate_qr():
    if current_user.role != 'admin': return "Unauthorized", 403
    
    # 1. Determine the URL
    ip = get_network_ip()
    port = 5000 # Default Flask port
    url = f"http://{ip}:{port}"
    
    # 2. Generate QR Image
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 3. Save to Byte Stream (in-memory, no file saved)
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

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
        final_round = Round.query.filter_by(event_id=active_event.id, is_final=True).first()
        
        # --- 1. DETERMINE SCORING MODE & COLUMNS ---
        if active_event.scoring_type == 'hybrid':
            if active_round.is_final or (final_round and active_round.number == final_round.number):
                show_cumulative = False
                # For Hybrid Final Clinchers, we might show the Final Round context
                if 'Tie Breaker' in active_round.difficulty or 'Clincher' in active_round.difficulty:
                    if final_round: previous_rounds = [final_round]
                else:
                    previous_rounds = []
            else:
                # Normal Hybrid Phase
                # Check if Tie Breaker -> Force Non-Cumulative
                if 'Tie Breaker' in active_round.difficulty:
                    show_cumulative = False
                    previous_rounds = []
                else:
                    show_cumulative = True
                    previous_rounds = Round.query.filter(
                         Round.event_id == active_event.id,
                         Round.number < active_round.number,
                         Round.difficulty.notlike('%Tie Breaker%')
                     ).order_by(Round.number.asc()).all()
                 
        elif active_event.scoring_type == 'cumulative':
            # === FIX: FORCE NON-CUMULATIVE FOR TIE BREAKERS ===
            if 'Tie Breaker' in active_round.difficulty:
                show_cumulative = False
                previous_rounds = []
            else:
                show_cumulative = True
                previous_rounds = Round.query.filter(
                     Round.event_id == active_event.id,
                     Round.number < active_round.number,
                     Round.difficulty.notlike('%Tie Breaker%')
                 ).order_by(Round.number.asc()).all()
             
        all_schools = School.query.filter_by(event_id=active_event.id).all()
        participating_schools = []

        if active_round.participating_school_ids:
            allowed_ids = active_round.participating_school_ids.split(',')
            participating_schools = [s for s in all_schools if str(s.id) in allowed_ids]
        else:
            participating_schools = all_schools
        
        all_schools_finished = True 
        
        for school in participating_schools:
            scores_in_this_round = Score.query.filter_by(school_id=school.id, round_id=active_round.id).all()
            current_round_points = 0
            answered_count = 0
            
            for s in scores_in_this_round:
                answered_count += 1
                if s.is_correct: current_round_points += active_round.points
            
            if answered_count < active_round.total_questions:
                all_schools_finished = False

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
                # Hybrid Final Phase Sorting Logic
                is_clincher = ('Tie Breaker' in active_round.difficulty or 'Clincher' in active_round.difficulty)
                if is_clincher and final_round:
                     final_score = sum(s.round.points for s in school.scores 
                                       if s.round_id == final_round.id and s.is_correct)
                     breakdown[final_round.id] = final_score
                     main_score_for_sorting = (final_score, current_round_points)
                else:
                     main_score_for_sorting = (current_round_points, 0)
            
            else:
                # Standard Per Round / Tie Breaker Sorting
                main_score_for_sorting = current_round_points

            display_score = 0
            if show_cumulative:
                display_score = main_score_for_sorting
            else:
                display_score = current_round_points

            live_scores.append({
                'school_id': school.id,
                'school': school.name,
                'current_score': current_round_points,
                'total_score': main_score_for_sorting, 
                'display_score': display_score,
                'breakdown': breakdown,
                'answered': answered_count,
                'total_q': active_round.total_questions
            })
            
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

# --- EVALUATION LOGIC (AUTOMATIC STOP ADDED) ---
@views.route('/admin/round/evaluate/<int:round_id>', methods=['POST'])
@login_required
def evaluate_round(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    current_round = Round.query.get_or_404(round_id)
    event_id = current_round.event_id
    cutoff = current_round.qualifying_count
    event = Event.query.get(event_id)
    
    if cutoff == 0 and 'Clincher' not in current_round.difficulty:
        flash('No qualifying limit set. Proceed manually.', category='info')
        return redirect(url_for('views.round_control'))

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
        if 'Tie Breaker' in current_round.difficulty or 'Clincher' in current_round.difficulty:
            score_val = sum(s.round.points for s in school.scores 
                            if s.round_id == current_round.id and s.is_correct)
        elif event.scoring_type == 'hybrid':
            if current_round.is_final:
                score_val = sum(s.round.points for s in school.scores 
                                if s.round_id == current_round.id and s.is_correct)
            else:
                for s in school.scores:
                    if (s.round.event_id == event.id and 
                        s.round.number <= current_round.number and 
                        'Tie Breaker' not in s.round.difficulty and 
                        s.is_correct):
                        score_val += s.round.points
        elif event.scoring_type == 'cumulative':
            for s in school.scores:
                if (s.round.event_id == event.id and s.round.number <= current_round.number and 'Tie Breaker' not in s.round.difficulty and s.is_correct):
                    score_val += s.round.points
        else:
            score_val = sum(s.round.points for s in school.scores if s.round_id == current_round.id and s.is_correct)
        
        standings.append({'school': school, 'score': score_val})
    
    standings.sort(key=lambda x: x['score'], reverse=True)

    # === SPECIAL LOGIC: ITERATIVE CLINCHER EVALUATION ===
    if 'Clincher' in current_round.difficulty:
        ties_created = 0
        
        for score, group in groupby(standings, key=lambda x: x['score']):
            tied_group = list(group)
            
            if len(tied_group) > 1:
                tied_ids = [str(item['school'].id) for item in tied_group]
                ids_string = ",".join(tied_ids)
                
                if current_round.participating_school_ids:
                    current_participants = current_round.participating_school_ids.split(',')
                    if set(tied_ids) == set(current_participants) and len(standings) == len(tied_group):
                         flash("⚠️ TIE NOT BROKEN! All contestants scored the same. Please add a question (+1 Q) to break the tie.", category='error')
                         return redirect(url_for('views.round_control'))

                import re
                match = re.search(r'Clincher (\d+)', current_round.difficulty)
                current_num = int(match.group(1)) if match else 1
                next_num = current_num + 1
                
                tb_round = Round(
                    event_id=event_id,
                    number=current_round.number, 
                    difficulty=f"Clincher {next_num}",
                    points=1,
                    total_questions=1,
                    participating_school_ids=ids_string,
                    qualifying_count=0, 
                    is_active=False,
                    is_final=False 
                )
                db.session.add(tb_round)
                ties_created += 1

        db.session.commit()
        
        if ties_created > 0:
            flash(f"Evaluation Complete. Created {ties_created} new Clincher round(s) for remaining ties.", "warning")
            return redirect(url_for('views.round_control'))
        else:
            # === FIX START: Stop the round automatically ===
            current_round.is_active = False
            db.session.commit()
            # === FIX END ===
            
            flash("Evaluation Complete. All ties broken! Final Ranking is set.", "success")
            return redirect(url_for('views.final_results', event_id=event_id))

    # === HYBRID FINAL - First Trigger ===
    if event.scoring_type == 'hybrid' and current_round.is_final and not 'Clincher' in current_round.difficulty:
        for i in range(len(standings) - 1):
            if standings[i]['score'] == standings[i+1]['score']:
                tied_score = standings[i]['score']
                tied_group = [s['school'] for s in standings if s['score'] == tied_score]
                ids_string = ",".join([str(s.id) for s in tied_group])
                
                tb_round = Round(
                    event_id=event.id, number=current_round.number, 
                    difficulty="Clincher 1",
                    points=1, total_questions=1, participating_school_ids=ids_string,
                    qualifying_count=0, is_active=False, is_final=False
                )
                db.session.add(tb_round)
                db.session.commit()
                flash(f"⚠️ Tie detected in Final Round. 'Clincher 1' created.", category='warning')
                return redirect(url_for('views.round_control'))
        
        # === FIX START: Stop the round automatically if no ties ===
        current_round.is_active = False
        db.session.commit()
        # === FIX END ===

        winner_names = ", ".join([s['school'].name for s in standings[:cutoff]]) if cutoff > 0 else "Top Rankers"
        flash(f"🏆 FINAL RESULTS OFFICIAL.", category='success')
        return redirect(url_for('views.final_results', event_id=event.id))

    # === STANDARD LOGIC ===
    if len(standings) > cutoff and cutoff > 0:
        boundary_score = standings[cutoff - 1]['score']
        next_score = standings[cutoff]['score']
        
        if boundary_score == next_score:
             if 'Tie Breaker' in current_round.difficulty:
                 flash("Tie still exists. Add question.", category='error')
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
             flash(f"Tie detected at cutoff. Tie breaker created.", category='warning')
             return redirect(url_for('views.round_control'))
             
        qualified_schools = [s['school'] for s in standings[:cutoff]]
    else:
        qualified_schools = [s['school'] for s in standings]
    
    final_advancing_schools = qualified_schools
    
    if 'Tie Breaker' in current_round.difficulty:
        parent_round = Round.query.filter(Round.event_id == event_id, Round.number == current_round.number, Round.difficulty.notlike('%Tie Breaker%')).first()
        if parent_round:
            clean_spots = parent_round.qualifying_count - current_round.qualifying_count
            p_schools = School.query.filter_by(event_id=event_id).all()
            p_standings = []
            for s in p_schools:
                if parent_round.participating_school_ids and str(s.id) not in parent_round.participating_school_ids.split(','): continue
                sc = 0
                is_parent_final = parent_round.is_final
                if event.scoring_type == 'hybrid' and is_parent_final:
                     sc = sum(score.round.points for s in s.scores if score.round_id == parent_round.id and score.is_correct)
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

@views.route('/admin/final-results/<int:event_id>')
@login_required
def final_results(event_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    event = Event.query.get_or_404(event_id)
    
    # Calculate Rankings (Same logic as PDF)
    all_rounds = Round.query.filter_by(event_id=event.id).order_by(Round.number.asc()).all()
    
    # A. Cumulative Rounds (Non-Final, Non-TieBreaker)
    cumulative_rounds = [r for r in all_rounds if not r.is_final and 'Tie Breaker' not in r.difficulty and 'Clincher' not in r.difficulty]
    
    # B. Final Round
    final_round = Round.query.filter_by(event_id=event.id, is_final=True).first()
    
    # C. Final Phase Clinchers
    final_clinchers = []
    if final_round:
        final_clinchers = Round.query.filter(
            Round.event_id == event.id,
            Round.number == final_round.number,
            Round.difficulty.like('%Clincher%')
        ).order_by(Round.id.asc()).all()
    
    schools = School.query.filter_by(event_id=event.id).all()
    rankings = []
    
    for school in schools:
        data = {'name': school.name, 'cum_total': 0, 'final_score': 0, 'clincher_scores': [], 'has_final': False}
        
        # 1. Cumulative
        for r in cumulative_rounds:
            data['cum_total'] += sum(s.round.points for s in school.scores if s.round_id == r.id and s.is_correct)
            
        # 2. Final
        if final_round and final_round.is_school_allowed(school.id):
            data['has_final'] = True
            data['final_score'] = sum(s.round.points for s in school.scores if s.round_id == final_round.id and s.is_correct)
        
        # 3. Clinchers
        c_scores_list = []
        for r in final_clinchers:
             if r.is_school_allowed(school.id):
                 c_scores_list.append(sum(s.round.points for s in school.scores if s.round_id == r.id and s.is_correct))
             else:
                 c_scores_list.append(-1)
        
        data['sort_key'] = (data['has_final'], data['final_score'], tuple(c_scores_list), data['cum_total'])
        rankings.append(data)

    rankings.sort(key=lambda x: x['sort_key'], reverse=True)

    # Get Signatories for List
    tabulators = db.session.query(User).join(School).filter(School.event_id == event.id).all()
    unique_tabulators = list({t.id: t for t in tabulators}.values())
    admin_signatories = User.query.filter(User.role == 'admin', User.username != 'admin1').all()

    return render_template('admin/final_results.html', event=event, rankings=rankings, 
                           tabulators=unique_tabulators, admins=admin_signatories, admin=current_user)

@views.route('/admin/final-results/pdf/<int:event_id>')
@login_required
def download_results_pdf(event_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    event = Event.query.get_or_404(event_id)
    
    # --- 1. IDENTIFY ROUNDS & COLUMNS ---
    all_rounds = Round.query.filter_by(event_id=event.id).order_by(Round.number.asc()).all()
    cumulative_rounds = [r for r in all_rounds if not r.is_final and 'Tie Breaker' not in r.difficulty and 'Clincher' not in r.difficulty]
    final_round = Round.query.filter_by(event_id=event.id, is_final=True).first()
    
    final_clinchers = []
    if final_round:
        final_clinchers = Round.query.filter(
            Round.event_id == event.id,
            Round.number == final_round.number,
            Round.difficulty.like('%Clincher%')
        ).order_by(Round.id.asc()).all()

    # --- 2. CALCULATE SCORES ---
    schools = School.query.filter_by(event_id=event.id).all()
    rankings = []
    
    for school in schools:
        data = {
            'name': school.name,
            'cum_breakdown': {},
            'cum_total': 0,
            'final_score': 0,
            'clincher_scores': [],
            'has_final': False
        }
        
        for r in cumulative_rounds:
            score = sum(s.round.points for s in school.scores if s.round_id == r.id and s.is_correct)
            data['cum_breakdown'][r.id] = score
            data['cum_total'] += score
            
        if final_round:
            if final_round.is_school_allowed(school.id):
                data['has_final'] = True
                data['final_score'] = sum(s.round.points for s in school.scores 
                                          if s.round_id == final_round.id and s.is_correct)
        
        c_scores_list = []
        for r in final_clinchers:
             if r.is_school_allowed(school.id):
                 s_val = sum(s.round.points for s in school.scores if s.round_id == r.id and s.is_correct)
                 c_scores_list.append(s_val)
             else:
                 c_scores_list.append(-1) 
        
        data['clincher_scores'] = c_scores_list
        data['sort_key'] = (
            data['has_final'], 
            data['final_score'], 
            tuple(c_scores_list), 
            data['cum_total']
        )
        rankings.append(data)

    rankings.sort(key=lambda x: x['sort_key'], reverse=True)

    # --- 3. SIGNATORIES ---
    tabulators = db.session.query(User).join(School).filter(School.event_id == event.id).all()
    unique_tabulators = list({t.id: t for t in tabulators}.values())
    admin_signatories = User.query.filter(User.role == 'admin', User.username != 'admin1').all()

    # --- 4. PDF GENERATION (LANDSCAPE) ---
    class PDF(FPDF):
        def header(self):
            # --- CUSTOM HEADER DESIGN ---
            
            # 1. Background Image (header.png)
            header_bg = os.path.join(current_app.root_path, 'static', 'header.png')
            
            if os.path.exists(header_bg):
                # Use the PNG as background (Full width 297mm)
                self.image(header_bg, x=0, y=0, w=297, h=38)
            else:
                # Fallback to Orange Color if image missing
                self.set_fill_color(227, 82, 5)
                self.rect(0, 0, 297, 35, 'F')

            # 2. Logo (JPTABS.png)
            logo_path = os.path.join(current_app.root_path, 'static', 'JPCS.png')
            if os.path.exists(logo_path):
                self.image(logo_path, x=12, y=4, w=25)

            # 3. Header Text (White, Times New Roman, Smaller & Higher)
            self.set_text_color(255, 255, 255)
            
            # College Name
            self.set_xy(40, 4) # Higher Y
            self.set_font('Times', '', 10) 
            self.cell(0, 10, "Camarines Sur Polytechnic Colleges", 0, 2, 'L')
            
            # Department Name
            self.set_xy(40, 8) 
            self.cell(0, 10, "College of Computer Studies", 0, 2, 'L')
            
            # Org Name (Bold & Larger)
            self.set_xy(40, 13) 
            self.set_font('Times', 'B', 13) 
            self.cell(0, 10, "Junior Philippine Computer Society", 0, 2, 'L')
            
            # Chapter Name
            self.set_xy(40, 18) 
            self.set_font('Times', 'B', 10) 
            self.cell(0, 10, "CSPC Chapter", 0, 2, 'L')

            # --- DOCUMENT TITLE (Below the orange bar) ---
            self.set_y(30) # Ensure enough space below header image
            self.set_text_color(0, 0, 0) # Reset to Black
            self.set_font('Times', 'B', 16) # Changed to Times
            self.cell(0, 10, event.name, 0, 1, 'C')
            
            self.set_font('Times', 'I', 11) # Changed to Times Italic
            self.cell(0, 5, 'Official Final Results', 0, 1, 'C')
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    pdf = PDF(orientation='L', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- TABLE CONFIGURATION ---
    eff_width = pdf.w - 2 * pdf.l_margin
    
    w_rank = 15
    w_school_min = 60 
    
    cols = []
    for r in cumulative_rounds:
        cols.append({'name': r.difficulty[:10], 'type': 'cum_round', 'id': r.id})
    cols.append({'name': 'CUMULATIVE', 'type': 'cum_total', 'bg': True})
    if final_round:
        cols.append({'name': 'FINAL', 'type': 'final', 'bg': True})
    for idx, r in enumerate(final_clinchers):
        cols.append({'name': f'C{idx+1}', 'type': 'clincher', 'idx': idx})

    num_score_cols = len(cols)
    available_for_scores = eff_width - w_rank - w_school_min
    w_col = available_for_scores / num_score_cols
    if w_col > 25: w_col = 25
    w_school = eff_width - w_rank - (num_score_cols * w_col)

    # --- DRAW TABLE HEADER ---
    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(230, 230, 230)
    
    pdf.cell(w_rank, 10, "Rank", 1, 0, 'C', True)
    pdf.cell(w_school, 10, "School / Candidate", 1, 0, 'C', True)
    
    for col in cols:
        pdf.cell(w_col, 10, col['name'], 1, 0, 'C', True)
    pdf.ln()

    # --- DRAW TABLE ROWS ---
    pdf.set_font("Arial", '', 10)
    
    previous_sort_key = None
    display_rank = 0

    for i, rank in enumerate(rankings):
        current_sort_key = rank['sort_key']
        if i == 0: display_rank = 1
        elif current_sort_key != previous_sort_key: display_rank = i + 1
        previous_sort_key = current_sort_key
        rank_str = to_ordinal(display_rank)
        
        fill = False
        if display_rank <= 3: 
            pdf.set_fill_color(255, 248, 220) 
            fill = True
        
        pdf.cell(w_rank, 10, rank_str, 1, 0, 'C', fill)
        pdf.cell(w_school, 10, rank['name'], 1, 0, 'L', fill)
        
        for col in cols:
            val = "-"
            if col['type'] == 'cum_round':
                val = str(rank['cum_breakdown'].get(col['id'], 0))
            elif col['type'] == 'cum_total':
                val = str(rank['cum_total'])
                pdf.set_font("Arial", 'B', 10)
            elif col['type'] == 'final':
                if rank['has_final']:
                    val = str(rank['final_score'])
                    pdf.set_font("Arial", 'B', 10)
                else:
                    val = "-" 
            elif col['type'] == 'clincher':
                score_list = rank['clincher_scores']
                idx = col['idx']
                if idx < len(score_list):
                    s = score_list[idx]
                    val = str(s) if s != -1 else "-"
            
            pdf.cell(w_col, 10, val, 1, 0, 'C', fill)
            pdf.set_font("Arial", '', 10)
            
        pdf.ln()

    # --- SIGNATORIES (FORCE NEW PAGE) ---
    pdf.add_page() 
    
    # Header image repeats automatically via header(), so set Y below it
    pdf.set_y(47) 
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Certified Correct & Verified By:", 0, 1, 'C')
    pdf.ln(15)

    # --- GRID SETTINGS UPDATED FOR 4 COLUMNS & TIGHTER SPACING ---
    col_count_max = 4 # Changed from 3 to 4
    col_width = eff_width / col_count_max
    row_height = 30 # Reduced height from 35 to 30 (Tighter vertical spacing)
    current_y = pdf.get_y()

    def draw_signature_grid(signatories_list, title):
        nonlocal current_y
        chunks = [signatories_list[i:i + col_count_max] for i in range(0, len(signatories_list), col_count_max)]
        for chunk in chunks:
            if current_y + row_height > 190: 
                pdf.add_page()
                current_y = pdf.get_y() + 10
            
            num_in_row = len(chunk)
            row_content_width = num_in_row * col_width
            empty_space = eff_width - row_content_width
            start_x = pdf.l_margin + (empty_space / 2)

            for i, person in enumerate(chunk):
                display_name = (person.first_name if person.first_name else person.username).upper()
                x_pos = start_x + (i * col_width)
                line_width = col_width * 0.85 # Increased width slightly for better balance in 4 cols
                line_start_x = x_pos + (col_width - line_width) / 2
                
                pdf.line(line_start_x, current_y + 15, line_start_x + line_width, current_y + 15)
                pdf.set_xy(x_pos, current_y + 16)
                pdf.set_font("Arial", 'B', 9) # Font size kept readable
                pdf.cell(col_width, 5, display_name, 0, 2, 'C')
                pdf.set_font("Arial", 'I', 7)
                pdf.cell(col_width, 4, title, 0, 0, 'C')
            
            current_y += row_height

    pdf.set_font("Arial", '', 10)
    draw_signature_grid(unique_tabulators, "Official Tabulator")
    current_y += 10 # Reduced spacing between sections
    
    if admin_signatories:
        draw_signature_grid(admin_signatories, "Administrator")
    else:
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


# --- TABULATOR ROUTES ---

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