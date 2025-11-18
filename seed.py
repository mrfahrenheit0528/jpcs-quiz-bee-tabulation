from website import create_app, db
from website.models import User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    db.drop_all()
    db.create_all()  # ensure tables exist

    # Only create if not already present
    if not User.query.filter_by(username="admin1").first():
        admin = User(
            username="admin1",
            password=generate_password_hash("adminpass"),
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin account created successfully!")
    else:
        print("Admin account already exists.")

'''
from website import create_app, db
# Import all models needed for seeding
from website.models import User, Event, School, Round, Score
from werkzeug.security import generate_password_hash

# --- DATA DEFINITIONS ---

# 1. Users (Tabulators have a password and the school_id they are assigned to)
USER_DATA = [
    # ID, Username, Role, School ID (FK on User)
    (1, "admin1", "admin", None),
    (2, "nami", "tabulator", 2),
    (3, "kye", "tabulator", 1),
    (4, "tab1", "tabulator", 3),
    (5, "tab2", "tabulator", 4),
    (6, "tab3", "tabulator", 5),
    (7, "tab4", "tabulator", 6),
    (8, "tab5", "tabulator", 7),
    (9, "tab6", "tabulator", 8),
    (10, "tab7", "tabulator", 9),
    (11, "tab8", "tabulator", 10),
    (12, "tab9", "tabulator", 11),
    (13, "tab10", "tabulator", 12),
]

# 2. Event
EVENT_DATA = [
    # ID, Name, is_active (1=True)
    (1, "JFINIX InterSchool Competition", True),
]

# 3. Schools
SCHOOL_DATA = [
    # ID, Name, Event ID
    (1, "usant", 1),
    (2, "nnhs", 1),
    (3, "school1", 1),
    (4, "school2", 1),
    (5, "school3", 1),
    (6, "school4", 1),
    (7, "school5", 1),
    (8, "school6", 1),
    (9, "school7", 1),
    (10, "school8", 1),
    (11, "school9", 1),
    (12, "school10", 1),
]

# 4. Rounds (We need Round IDs 1 and 4 for the score data)
# Round: ID, number, difficulty, points, total_questions, event_id, qualifying_count, is_final
ROUND_DATA = [
    (1, 1, "Easy", 1, 10, 1, 10, False), # All scores provided are for this round (10 questions)
    (2, 2, "Average", 3, 10, 1, 5, False),
    (3, 3, "Difficult", 5, 10, 1, 0, False),
]

# 5. Score Data (school_id, round_id, question_number, is_correct)
SCORE_DATA = [
    (1, 1, 1, 1), (1, 1, 2, 1), (1, 1, 3, 1), (1, 1, 4, 1), (1, 1, 5, 1), (1, 1, 6, 1), (1, 1, 7, 1), (1, 1, 8, 1), (1, 1, 9, 1), (1, 1, 10, 1),
    (2, 1, 1, 1), (2, 1, 2, 1), (2, 1, 3, 1), (2, 1, 4, 1), (2, 1, 5, 1), (2, 1, 6, 1), (2, 1, 7, 1), (2, 1, 8, 1), (2, 1, 9, 1), (2, 1, 10, 1),
    (3, 1, 1, 1), (3, 1, 2, 0), (3, 1, 3, 1), (3, 1, 4, 1), (3, 1, 5, 1), (3, 1, 6, 1), (3, 1, 7, 1), (3, 1, 8, 1), (3, 1, 9, 0), (3, 1, 10, 1),
    (4, 1, 1, 1), (4, 1, 2, 0), (4, 1, 3, 1), (4, 1, 4, 1), (4, 1, 5, 1), (4, 1, 6, 1), (4, 1, 7, 0), (4, 1, 8, 1), (4, 1, 9, 1), (4, 1, 10, 0),
    (5, 1, 1, 1), (5, 1, 2, 1), (5, 1, 4, 1), (5, 1, 5, 1), (5, 1, 7, 1), (5, 1, 8, 1), (5, 1, 10, 1), (5, 1, 3, 0), (5, 1, 6, 0), (5, 1, 9, 0), # Corrected for 10 entries
    (6, 1, 1, 1), (6, 1, 2, 1), (6, 1, 3, 1), (6, 1, 4, 1), (6, 1, 5, 1), (6, 1, 6, 0), (6, 1, 7, 1), (6, 1, 8, 1), (6, 1, 9, 0), (6, 1, 10, 1),
    (7, 1, 1, 1), (7, 1, 2, 1), (7, 1, 3, 0), (7, 1, 4, 1), (7, 1, 5, 1), (7, 1, 6, 0), (7, 1, 7, 1), (7, 1, 8, 1), (7, 1, 9, 0), (7, 1, 10, 1),
    (8, 1, 1, 1), (8, 1, 2, 0), (8, 1, 3, 0), (8, 1, 4, 1), (8, 1, 5, 1), (8, 1, 6, 0), (8, 1, 7, 1), (8, 1, 8, 1), (8, 1, 9, 0), (8, 1, 10, 1),
    (9, 1, 1, 1), (9, 1, 2, 1), (9, 1, 3, 0), (9, 1, 4, 1), (9, 1, 5, 1), (9, 1, 6, 0), (9, 1, 7, 1), (9, 1, 8, 0), (9, 1, 9, 0), (9, 1, 10, 1),
    (10, 1, 1, 1), (10, 1, 2, 1), (10, 1, 3, 0), (10, 1, 4, 1), (10, 1, 5, 0), (10, 1, 6, 0), (10, 1, 7, 1), (10, 1, 8, 0), (10, 1, 9, 0), (10, 1, 10, 1),
    (11, 1, 1, 1), (11, 1, 2, 1), (11, 1, 3, 0), (11, 1, 4, 1), (11, 1, 5, 0), (11, 1, 6, 0), (11, 1, 7, 1), (11, 1, 8, 0), (11, 1, 9, 0), (11, 1, 10, 1),
    (12, 1, 1, 1), (12, 1, 2, 1), (12, 1, 3, 0), (12, 1, 4, 1), (12, 1, 5, 0), (12, 1, 6, 0), (12, 1, 7, 1), (12, 1, 8, 0), (12, 1, 9, 0), (12, 1, 10, 1),
    (10, 4, 1, 1), # Extra score for testing Round 4 (Final)
]


# --- SEEDING FUNCTION ---

app = create_app()

with app.app_context():
    # 1. Clear and Recreate Tables (Important for model updates)
    db.drop_all()
    db.create_all() 
    print("Database tables recreated.")

    try:
        # 2. Add Event
        event_objects = {}
        for id, name, is_active in EVENT_DATA:
            event = Event(id=id, name=name, is_active=is_active)
            db.session.add(event)
            event_objects[id] = event

        # 3. Add Schools
        school_objects = {}
        for id, name, event_id in SCHOOL_DATA:
            school = School(id=id, name=name, event_id=event_id)
            db.session.add(school)
            school_objects[id] = school

        # 4. Add Users (including Admin and Tabulators)
        user_objects = {}
        for id, username, role, school_id in USER_DATA:
            user = User(
                id=id,
                username=username,
                password=generate_password_hash("pass" if role == "admin" else "pass"), # Using 'pass' for all
                role=role,
                school_id=school_id # Link to the school
            )
            db.session.add(user)
            user_objects[id] = user
        
        # 5. Add Rounds
        round_objects = {}
        for id, num, diff, points, q_count, event_id, qual_count, is_final in ROUND_DATA:
            round_obj = Round(
                id=id, 
                number=num, 
                difficulty=diff, 
                points=points, 
                total_questions=q_count, 
                event_id=event_id, 
                qualifying_count=qual_count,
                is_final=is_final
            )
            db.session.add(round_obj)
            round_objects[id] = round_obj
            
        # Set Easy Round (ID 1) to active for immediate testing
        round_objects[1].is_active = True


        # 6. Add Scores
        for school_id, round_id, q_num, is_correct in SCORE_DATA:
            score = Score(
                school_id=school_id,
                round_id=round_id,
                question_number=q_num,
                is_correct=bool(is_correct)
            )
            db.session.add(score)
        
        db.session.commit()
        print("\n--- Seeding Complete ---")
        print(f"Total Users: {len(USER_DATA)}")
        print(f"Total Schools: {len(SCHOOL_DATA)}")
        print(f"Total Scores: {len(SCORE_DATA)}")
        print("\nTest Credentials:")
        print("Admin: username=admin1, password=pass")
        print("Tabulator: username=kye, password=pass (Assigned to usant)")
        print("------------------------\n")

    except Exception as e:
        db.session.rollback()
        print(f"An error occurred during seeding: {e}")
'''