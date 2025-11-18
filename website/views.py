from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from website.models import User, Event, School, Round, Score
from website import db
from werkzeug.security import generate_password_hash

views = Blueprint('views', __name__)

def set_active_event(event_id):
    # Deactivate all other events
    Event.query.update({Event.is_active: False})
    
    # Activate the selected event
    event = Event.query.get(event_id)
    if event:
        event.is_active = True
        db.session.commit()
        return True
    return False

#=============================GENERAL ROUTES======================================
@views.route('/')
def home():
    return render_template("home.html")

@views.route('/leaderboard')
def leaderboard():
    current_event = Event.query.filter_by(is_active=True).first()

    if not current_event:
        return render_template('viewer/leaderboard.html', event=None, schools=[])

    schools = School.query.filter_by(event_id=current_event.id).all()

    # Aggregate scores per school
    school_totals = []
    for school in schools:
        total_points = sum(
            score.round.points   # points defined by admin in Round
            for score in school.scores if score.is_correct
        )
        school_totals.append((school, total_points))

    # Sort by total points descending
    school_totals.sort(key=lambda x: x[1], reverse=True)

    return render_template('viewer/leaderboard.html', event=current_event, school_totals=school_totals)




#=============================ADMIN ROUTES======================================
@views.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return "Unauthorized", 403
    return render_template('admin/admin_dashboard.html')


@views.route('/admin/register-user', methods=['GET', 'POST'])
@login_required
def register_user():
    if current_user.role != 'admin':
        return "Unauthorized", 403

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        from werkzeug.security import generate_password_hash
        new_user = User(username=username,
                        password=generate_password_hash(password),
                        role=role)

        db.session.add(new_user)
        db.session.commit()
        flash('User created successfully!', category='success')
        return redirect(url_for('views.admin_dashboard'))

    return render_template('admin/register_user.html')


@views.route('/admin/event-registration', methods=['GET', 'POST'])
@login_required
def event_registration():
    if current_user.role != 'admin':
        return "Unauthorized", 403
    
    # 1. Handle POST request for creating a new event
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_event':
            name = request.form.get('name')
            is_active = request.form.get('is_active') == 'on'
            scoring_type = request.form.get('scoring_type') # <--- Capture input
            
            if not name:
                flash('Event name is required.', category='error')
                return redirect(url_for('views.event_registration'))

            new_event = Event(name=name, is_active=is_active, scoring_type=scoring_type)
            db.session.add(new_event)
            db.session.commit()

            if is_active:
                set_active_event(new_event.id)
                
            flash(f'Event "{name}" created successfully.', category='success')

            return redirect(url_for('views.round_setup', event_id=new_event.id))
            
        elif action == 'set_active':
            event_id = request.form.get('event_id')
            if set_active_event(event_id):
                flash('Active event updated.', category='success')
            else:
                flash('Error setting active event.', category='error')
        
        return redirect(url_for('views.event_registration'))

    # 2. Handle GET request for displaying the dashboard
    events = Event.query.order_by(Event.id.desc()).all()
    active_event = Event.query.filter_by(is_active=True).first()
    
    # You might want to pre-load rounds/schools for the active event here later
    
    return render_template('admin/event_registration.html', 
                           events=events,
                           active_event=active_event)

@views.route('/admin/event/delete/<int:event_id>', methods=['POST'])
@login_required
def delete_event(event_id):
    if current_user.role != 'admin':
        return "Unauthorized", 403
        
    event = Event.query.get_or_404(event_id)
    
    # Optional: Prevent deleting active event to avoid crashing live scoring
    if event.is_active:
        flash('Cannot delete the currently active event. Deactivate it first.', category='error')
    else:
        db.session.delete(event)
        db.session.commit()
        flash(f'Event "{event.name}" has been deleted.', category='success')
        
    return redirect(url_for('views.event_registration'))

@views.route('/admin/event/edit/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    if current_user.role != 'admin':
        return "Unauthorized", 403
        
    event = Event.query.get_or_404(event_id)
    
    if request.method == 'POST':
        event.name = request.form.get('name')
        db.session.commit()
        flash('Event updated successfully.', category='success')
        return redirect(url_for('views.event_registration'))
        
    return render_template('admin/event_edit.html', event=event)


# NEW (Fixed)
@views.route('/admin/round-setup/<int:event_id>', methods=['GET', 'POST'])
@login_required
def round_setup(event_id):  # <--- Renamed function
    if current_user.role != 'admin':
        return "Unauthorized", 403
        
    event = Event.query.get_or_404(event_id)

    if request.method == 'POST':
        # ... (keep your existing logic for adding rounds) ...
        difficulty = request.form.get('difficulty')
        points = request.form.get('points')
        total_questions = request.form.get('total_questions')
        round_number = request.form.get('round_number')
        qualifying_count = request.form.get('qualifying_count')
        is_final = request.form.get('is_final') == 'on' # Checkbox returns 'on' if checked

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
        flash(f'{difficulty} Round added successfully!', category='success')
        # Update redirect to point to the new name
        return redirect(url_for('views.round_setup', event_id=event.id))

    # ... (keep existing logic) ...
    rounds = Round.query.filter_by(event_id=event.id).order_by(Round.number.asc()).all()

    # Update template render to point to a renamed template (see Step 2)
    return render_template('admin/round_setup.html', event=event, rounds=rounds)


@views.route('/admin/round/delete/<int:round_id>', methods=['POST'])
@login_required
def delete_round(round_id):
    if current_user.role != 'admin':
        return "Unauthorized", 403
        
    round_obj = Round.query.get_or_404(round_id)
    event_id = round_obj.event_id # Remember this so we can go back
    
    db.session.delete(round_obj)
    db.session.commit()
    
    flash('Round deleted.', category='success')
    return redirect(url_for('views.round_setup', event_id=event_id))


@views.route('/admin/round-control')
@login_required
def round_control():
    if current_user.role != 'admin': return "Unauthorized", 403
    
    active_event = Event.query.filter_by(is_active=True).first()
    if not active_event:
        return redirect(url_for('views.event_registration'))

    rounds = Round.query.filter_by(event_id=active_event.id).order_by(Round.number.asc()).all()
    active_round = Round.query.filter_by(event_id=active_event.id, is_active=True).first()
    
    live_scores = []
    round_fully_completed = False 
    
    if active_round:
        # --- NEW FILTER LOGIC ---
        all_schools = School.query.filter_by(event_id=active_event.id).all()
        participating_schools = []

        # Check if the round has a restriction (like a Tie Breaker)
        if active_round.participating_school_ids:
            allowed_ids = active_round.participating_school_ids.split(',')
            # Only keep schools that are in the allowed list
            participating_schools = [s for s in all_schools if str(s.id) in allowed_ids]
        else:
            # Normal round: Everyone plays
            participating_schools = all_schools
        
        # Flags for checking completion
        all_schools_finished = True 
        
        # Iterate ONLY through participating schools
        for school in participating_schools:
            scores_in_this_round = Score.query.filter_by(school_id=school.id, round_id=active_round.id).all()
            
            current_points = 0
            answered_count = 0
            
            for s in scores_in_this_round:
                answered_count += 1
                if s.is_correct:
                    current_points += active_round.points
            
            # Check completion for this specific school
            if answered_count < active_round.total_questions:
                all_schools_finished = False

            live_scores.append({
                'school_id': school.id,
                'school': school.name,
                'score': current_points,
                'answered': answered_count,
                'total': active_round.total_questions
            })
            
        live_scores.sort(key=lambda x: x['score'], reverse=True)
        
        # If we have schools AND everyone finished
        if participating_schools and all_schools_finished:
            round_fully_completed = True

    return render_template('admin/round_control.html', 
                           event=active_event, 
                           rounds=rounds, 
                           active_round=active_round, 
                           live_scores=live_scores,
                           round_fully_completed=round_fully_completed)

@views.route('/admin/round/activate/<int:round_id>', methods=['POST'])
@login_required
def activate_round(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    target_round = Round.query.get_or_404(round_id)
    
    # Deactivate ALL rounds in this event first (ensure only 1 is active)
    all_rounds = Round.query.filter_by(event_id=target_round.event_id).all()
    for r in all_rounds:
        r.is_active = False
        
    # Activate target
    target_round.is_active = True
    db.session.commit()
    
    flash(f'{target_round.difficulty} Round is now LIVE.', category='success')
    return redirect(url_for('views.round_control'))

@views.route('/admin/round/stop/<int:round_id>', methods=['POST'])
@login_required
def stop_round(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    round_obj = Round.query.get_or_404(round_id)
    round_obj.is_active = False
    db.session.commit()
    
    flash('Round stopped. Scoring is closed.', category='warning')
    return redirect(url_for('views.round_control'))

@views.route('/admin/round/evaluate/<int:round_id>', methods=['POST'])
@login_required
def evaluate_round(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    current_round = Round.query.get_or_404(round_id)
    event = Event.query.get(current_round.event_id) # <--- Need Event object for rules
    event_id = current_round.event_id
    cutoff = current_round.qualifying_count
    
    if cutoff == 0:
        flash('No qualifying limit set. Proceed manually.', category='info')
        return redirect(url_for('views.round_control'))

    # --- 1. CALCULATE STANDINGS FOR THIS ROUND ---
    all_schools = School.query.filter_by(event_id=event_id).all()
    standings = []
    
    # Filter participants (Crucial for Tie Breakers)
    participating_schools = []
    if current_round.participating_school_ids:
        allowed_ids = current_round.participating_school_ids.split(',')
        participating_schools = [s for s in all_schools if str(s.id) in allowed_ids]
    else:
        participating_schools = all_schools

    for school in participating_schools:
        # === LOGIC FOR CALCULATING SCORE ===
        score_val = 0
        
        if event.scoring_type == 'cumulative':
            # LOGIC: Sum scores from ALL rounds up to current, excluding Tie Breakers
            for s in school.scores:
                # Check 1: Must be this event
                # Check 2: Must be this round OR a previous round (number <= current)
                # Check 3: Must NOT be a Tie Breaker (usually they don't count for accumulation)
                if (s.round.event_id == event.id and 
                    s.round.number <= current_round.number and 
                    'Tie Breaker' not in s.round.difficulty and 
                    s.is_correct):
                    
                    score_val += s.round.points
                    
        else:
            # LOGIC: Per Round (Back to Zero)
            # Only count scores strictly from THIS round ID
            score_val = sum(s.round.points for s in school.scores 
                            if s.round_id == current_round.id and s.is_correct)
        
        # ===================================

        standings.append({'school': school, 'score': score_val})
    
    # Sort High to Low
    standings.sort(key=lambda x: x['score'], reverse=True)

    # --- 2. TIE DETECTION ---
    
    # Check if we even have enough players to worry about a cutoff
    if len(standings) <= cutoff:
        # Everyone qualifies (or wins if it's a Tie Breaker)
        qualified_schools = [s['school'] for s in standings]
    
    else:
        boundary_score = standings[cutoff - 1]['score']
        next_score = standings[cutoff]['score']
        
        # IF TIE AT THE CUTOFF
        if boundary_score == next_score:
            
            # [CONSTRAINT 2] Block evaluation if Tie Breaker is STILL tied
            if 'Tie Breaker' in current_round.difficulty:
                flash("⚠️ CANNOT ADVANCE! There is still a tie for the final spot. Please click '+1 Q' to add another question and break the tie.", category='error')
                return redirect(url_for('views.round_control'))
            
            # ELSE: Normal Round Tie -> Create Tie Breaker
            tied_schools = [s['school'] for s in standings if s['score'] == boundary_score]
            tied_ids = [str(s.id) for s in tied_schools]
            ids_string = ",".join(tied_ids)

            # Calculate how many clean winners there were
            clean_winners = [s for s in standings if s['score'] > boundary_score]
            clean_count = len(clean_winners)
            slots_for_tiebreaker = cutoff - clean_count
            
            tb_round = Round(
                event_id=event_id,
                number=current_round.number, 
                difficulty=f"Tie Breaker ({current_round.difficulty})",
                points=1,
                total_questions=1, 
                participating_school_ids=ids_string,
                qualifying_count=slots_for_tiebreaker,
                is_active=False
            )
            db.session.add(tb_round)
            db.session.commit()
            
            flash(f"⚠️ TIE! {len(tied_schools)} schools are fighting for {slots_for_tiebreaker} spot(s). Tie Breaker created.", category='warning')
            return redirect(url_for('views.round_control'))

        # NO TIE: Determine qualifiers normally
        qualified_schools = [s['school'] for s in standings[:cutoff]]


    # --- 3. MERGE & ADVANCE (Handle "Reunification") ---
    
    # List of schools moving to the next stage
    final_advancing_schools = qualified_schools

    # [CONSTRAINT 1] If this was a Tie Breaker, we must fetch the "Clean Winners"
    # who were waiting in the Parent Round.
    if 'Tie Breaker' in current_round.difficulty:
        # Find Parent Round (Same number, but NOT a Tie Breaker)
        parent_round = Round.query.filter(
            Round.event_id == event_id,
            Round.number == current_round.number,
            Round.difficulty.notlike('%Tie Breaker%')
        ).first()

        if parent_round:
            # Re-calculate Parent Standings to find the Clean Winners
            # Clean Winners = Top (Total_Qualifiers - TieBreaker_Qualifiers)
            clean_spots = parent_round.qualifying_count - current_round.qualifying_count
            
            # Logic to fetch parent standings (simplified for brevity)
            # We fetch ALL schools again to rank them on the PARENT round scores
            p_schools = School.query.filter_by(event_id=event_id).all()
            p_standings = []
            for s in p_schools:
                # Ensure school was allowed in parent
                if parent_round.participating_school_ids:
                    if str(s.id) not in parent_round.participating_school_ids.split(','): continue
                
                sc = sum(score.round.points for score in s.scores if score.round_id == parent_round.id and score.is_correct)
                p_standings.append({'school': s, 'score': sc})
            
            p_standings.sort(key=lambda x: x['score'], reverse=True)
            
            # Get the clean winners
            clean_winners = [x['school'] for x in p_standings[:clean_spots]]
            
            # MERGE: Clean Winners + Tie Breaker Winners
            final_advancing_schools = clean_winners + qualified_schools
            
            flash(f"Tie Breaker Complete! Merged {len(qualified_schools)} survivors with {len(clean_winners)} waiting qualifiers.", category='success')


    # --- 4. PUSH TO NEXT ROUND (OR FINALIZE) ---
    
    final_ids = [str(s.id) for s in final_advancing_schools]
    final_ids_str = ",".join(final_ids)
    
    # Check if Parent (or current) was marked Final
    # If current is Tie Breaker, inherit 'is_final' from parent logic implicitly
    is_event_over = current_round.is_final or ('Tie Breaker' in current_round.difficulty and 'Final' in current_round.difficulty)

    if is_event_over:
        winner_names = ", ".join([s.name for s in final_advancing_schools])
        flash(f"🏆 EVENT COMPLETE! Official Winners: {winner_names}", category='success')
    else:
        # Find Next Round
        next_round = Round.query.filter(
            Round.event_id == event_id, 
            Round.number > current_round.number
        ).order_by(Round.number.asc()).first()
        
        if next_round:
            next_round.participating_school_ids = final_ids_str
            db.session.commit()
            flash(f"Advanced {len(final_advancing_schools)} schools to {next_round.difficulty} Round.", category='success')
        else:
            flash(f"Evaluation Complete. {len(final_advancing_schools)} schools qualified, but no Next Round found.", category='warning')

    return redirect(url_for('views.round_control'))


@views.route('/admin/round/create-tiebreaker', methods=['POST'])
@login_required
def create_tiebreaker():
    if current_user.role != 'admin': return "Unauthorized", 403
    
    active_event = Event.query.filter_by(is_active=True).first()
    if not active_event: return "No active event", 400
    
    # 1. Get the selected school IDs from the form
    # The HTML form will send checkboxes named 'school_ids'
    selected_school_ids = request.form.getlist('school_ids')
    
    if not selected_school_ids:
        flash('You must select at least 2 schools for a tie breaker.', category='error')
        return redirect(url_for('views.round_control'))

    # Convert list ['1', '4'] to string "1,4"
    ids_string = ",".join(selected_school_ids)

    # 2. Determine next round number
    last_round = Round.query.filter_by(event_id=active_event.id).order_by(Round.number.desc()).first()
    next_num = (last_round.number + 1) if last_round else 1
    
    # 3. Create the Tie Breaker Round
    # We give it 5 questions by default. If they tie again, you just score Q2, then Q3...
    tb_round = Round(
        event_id=active_event.id,
        number=next_num,
        difficulty="Tie Breaker",
        points=1, 
        total_questions=5, 
        participating_school_ids=ids_string  # <--- THIS IS KEY
    )
    db.session.add(tb_round)
    db.session.commit()
    
    flash(f'Tie Breaker created for {len(selected_school_ids)} schools!', category='success')
    return redirect(url_for('views.round_control'))

@views.route('/admin/round/add-question/<int:round_id>', methods=['POST'])
@login_required
def add_question(round_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    current_round = Round.query.get_or_404(round_id)
    
    # Increment question count
    current_round.total_questions += 1
    db.session.commit()
    
    flash(f'Question added! Total is now {current_round.total_questions}. Tabulators should refresh.', category='success')
    return redirect(url_for('views.round_control'))

@views.route('/admin/tie-breaker')
@login_required
def tie_breaker():
    if current_user.role != 'admin':
        return "Unauthorized", 403
    return render_template('admin/tie_breaker.html')


@views.route('/admin/school-registration/<int:event_id>', methods=['GET', 'POST'])
@login_required
def school_registration(event_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    event = Event.query.get_or_404(event_id)

    if request.method == 'POST':
        school_name = request.form.get('school_name')
        tabulator_id = request.form.get('tabulator_id') 

        # 1. Validation Checks
        school_exists = School.query.filter_by(name=school_name, event_id=event.id).first()
        
        # NEW CHECK: Is this tabulator already busy IN THIS EVENT?
        existing_assignment = School.query.filter_by(event_id=event.id, user_id=tabulator_id).first()

        if school_exists:
            flash(f'School "{school_name}" is already registered.', category='error')
        elif existing_assignment:
            flash(f'This Tabulator is already assigned to "{existing_assignment.name}" for this event.', category='error')
        else:
            # 2. Create School
            new_school = School(
                name=school_name,
                event_id=event.id,
                user_id=tabulator_id # Assign tabulator directly here
            )
            db.session.add(new_school)
            db.session.commit()
            flash(f'School "{school_name}" added successfully!', category='success')
            return redirect(url_for('views.school_registration', event_id=event.id))

    # GET: Show list
    schools = School.query.filter_by(event_id=event.id).all()
    
    # Dropdown: Show ALL tabulators. 
    # (Optional: You could filter out ones already taken in this event, but showing all is fine too)
    all_tabulators = User.query.filter_by(role='tabulator').all()

    return render_template('admin/school_registration.html', 
                           event=event, schools=schools, all_tabulators=all_tabulators)


@views.route('/admin/school/delete/<int:school_id>', methods=['POST'])
@login_required
def delete_school(school_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    school = School.query.get_or_404(school_id)
    event_id = school.event_id
    
    # Optional: Also delete the associated Tabulator User to keep DB clean
    if school.tabulator:
        db.session.delete(school.tabulator)
        
    db.session.delete(school)
    db.session.commit()
    
    flash('School and Tabulator removed successfully.', category='success')
    return redirect(url_for('views.school_registration', event_id=event_id))


@views.route('/admin/final-results')
@login_required
def final_results():
    if current_user.role != 'admin':
        return "Unauthorized", 403
    return render_template('admin/final_results.html')



#=============================TABULATOR ROUTES======================================
@views.route('/tabulator/dashboard')
@login_required
def tabulator_dashboard():
    if current_user.role != 'tabulator': return "Unauthorized", 403
    
    # 1. Find Active Event
    active_event = Event.query.filter_by(is_active=True).first()
    
    school = None
    rounds = []
    
    if active_event:
        # 2. Find the school assigned to THIS user for THIS event
        school = School.query.filter_by(event_id=active_event.id, user_id=current_user.id).first()
        rounds = active_event.rounds

    return render_template('tabulator/tabulator_dashboard.html', 
                           school=school, 
                           active_event=active_event,
                           rounds=rounds)

@views.route('/tabulator/scoring/<int:round_id>', methods=['GET', 'POST'])
@login_required
def scoring(round_id):
    # 1. Security Check: Role
    if current_user.role != 'tabulator':
        return "Unauthorized", 403

    current_round = Round.query.get_or_404(round_id)
    
    # 2. Check if Round is Active
    if not current_round.is_active:
        flash(f'The {current_round.difficulty} Round is currently closed.', category='error')
        return redirect(url_for('views.tabulator_dashboard'))

    # 3. Find the School assigned to THIS user for THIS round's event
    # (Crucial because one tabulator might work multiple events)
    school = School.query.filter_by(
        event_id=current_round.event_id, 
        user_id=current_user.id
    ).first()

    if not school:
        flash("You are not assigned to any school for this specific event.", category='error')
        return redirect(url_for('views.tabulator_dashboard'))

    # 4. Check Eligibility (Tie Breaker Filter)
    # This ensures tabulators don't accidentally score a Tie Breaker they aren't part of
    if not current_round.is_school_allowed(school.id):
        flash("Your school is not participating in this specific round.", category='warning')
        return redirect(url_for('views.tabulator_dashboard'))

    # 5. Handle Score Submission (POST)
    if request.method == 'POST':
        # Loop through all questions defined for this round
        for q_num in range(1, current_round.total_questions + 1):
            # Get value from radio button ('correct', 'wrong', or None)
            answer_status = request.form.get(f'question_{q_num}')

            if answer_status:
                is_correct_val = (answer_status == 'correct')

                # Check if a score already exists for this question
                existing_score = Score.query.filter_by(
                    school_id=school.id,
                    round_id=current_round.id,
                    question_number=q_num
                ).first()

                if existing_score:
                    existing_score.is_correct = is_correct_val
                else:
                    new_score = Score(
                        school_id=school.id,
                        round_id=current_round.id,
                        question_number=q_num,
                        is_correct=is_correct_val
                    )
                    db.session.add(new_score)

        db.session.commit()
        flash('Scores saved successfully!', category='success')
        return redirect(url_for('views.scoring', round_id=current_round.id))

    # 6. Load Page Data (GET)
    # Fetch existing scores to pre-fill the buttons
    existing_scores = Score.query.filter_by(school_id=school.id, round_id=current_round.id).all()
    
    # Create a dictionary for easy lookup in HTML: {1: True, 2: False}
    score_map = {s.question_number: s.is_correct for s in existing_scores}

    return render_template('tabulator/scoring.html', 
                           school=school, 
                           round=current_round, 
                           total_questions=current_round.total_questions,
                           score_map=score_map)
