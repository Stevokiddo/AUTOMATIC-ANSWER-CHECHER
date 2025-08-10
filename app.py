from flask import Flask, render_template, request, session, redirect, url_for, flash
from forms import LoginForm, RegistrationForm
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, current_user
from flask_cors import CORS
from dotenv import load_dotenv
from models import db, User
import json
import time
import os

app = Flask(__name__)
CORS(app)

load_dotenv()  # Load environment variables from .env file

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'  #
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

#app.secret_key = os.urandom(24)  # Secret key for session management

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # redirects if not logged in

# Function to load questions from the JSON file
def load_questions(category=None):
    try:
        with open("questions.json", "r") as f:
            data = json.load(f)
            if not category:
                return data["categories"]
            return data["categories"].get(category, [])

    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading questions: {e}")
        return None

# Function to get sequential questions
def get_questions(questions, num_questions):
    if num_questions > len(questions):
        num_questions = len(questions)
    return questions[:num_questions]

# --- User Loader Callback ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))  # Reloads user from DB by ID

@app.route('/')
def home():
    form = LoginForm()
    return render_template('home/index.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    msg = ""
    
    if form.validate_on_submit():
        email = form.username.data.strip()
        password = form.password.data.strip()
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)  # Log in the user
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            msg = "Invalid email or password"
    return render_template('home/index.html', form=form, msg=msg)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    msg = ""
    
    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            msg = "Email already exists. Please use a different email."
        else:
            new_user = User(
                email=form.email.data.strip(),
                username=form.username.data.strip(),
                password= generate_password_hash(form.password.data.strip(), method='scrypt')
            )
            db.session.add(new_user)
            db.session.commit()
            msg = "You have successful registered."
            return redirect(url_for('login'))
    return render_template('home/register.html', form=form, msg=msg)



@app.route('/logout')
@login_required
def logout():
    session.clear()  # Clear session data
    return redirect(url_for('home'))


@app.route('/home')
@login_required
def index():
    categories = load_questions()
    if not categories:
        return render_template('index.html', error="Failed to load questions. Please check the questions file.")
    
    # Count questions per category
    categories_count = {cat: len(questions) for cat, questions in categories.items()}
    
    # Calculate the maximum questions available in any category
    max_questions = max(len(questions) for questions in categories.values())
    
    return render_template('index.html', categories=categories_count, max_questions=max_questions, user=current_user)

# category route
@app.route('/category/<string:category>')
@login_required
def category_questions(category):
    questions = load_questions(category)
    if not questions:
        flash(f"No questions found for {category.capitalize()}!", 'error')
        return redirect(url_for('index'))
    
    
    return render_template('category.html', 
                         category=category.capitalize(),
                         questions_count=len(questions),
                         user=current_user)

@app.route('/start', methods=['POST'])
#@login_required
@login_required
def start_quiz():
    category = request.form.get('category')
    total_questions = int(request.form.get('total_questions'))
    
    questions = load_questions(category)
    if not questions or total_questions <= 0:
        flash("Invalid quiz parameters!", 'error')
        return redirect(url_for('category_questions', category=category))
    
    # Initialize session variables
    session['category'] = category
    session['total_questions'] = min(total_questions, len(questions))
    session['questions'] = get_questions(questions, session['total_questions'])
    session['current_index'] = 0
    session['answers'] = []
    session['start_time'] = time.time()
    
    return redirect(url_for('show_question'))

@app.route('/quiz')
#@login_required
def show_question():
    # Check if quiz has started
    if 'current_index' not in session:
        return redirect(url_for('index'))
    
    current_index = session['current_index']
    total_questions = session['total_questions']
    
    # Check if quiz is completed
    if current_index >= total_questions:
        return redirect(url_for('show_results'))
    
    # Get current question
    question = session['questions'][current_index]
    question_number = current_index + 1
    
    return render_template('quiz.html', 
                          question=question, 
                          question_number=question_number,
                          total_questions=total_questions)

@app.route('/submit', methods=['POST'])
#@login_required
def submit_answer():
    current_index = session['current_index']
    question = session['questions'][current_index]
    
    # Get user's answer
    user_answer = request.form.get('answer')
    
    # Check if answer is valid
    if user_answer not in ("A", "B", "C", "D"):
        is_correct = False
    else:
        is_correct = (user_answer == question['answer'])
    
    # Store answer
    session['answers'].append({
        'question': question['question'],
        'user_answer': user_answer,
        'correct_answer': question['answer'],
        'is_correct': is_correct,
        'options': question['options']
    })
    
    # Move to next question
    session['current_index'] = current_index + 1
    session.modified = True  # Ensure session is saved
    
    return redirect(url_for('show_question'))

@app.route('/results')
@login_required
def show_results():
    if 'answers' not in session:
        return redirect(url_for('index'))
    
    total_questions = session['total_questions']
    correct = sum(1 for answer in session['answers'] if answer['is_correct'])
    score = round((correct / total_questions) * 100, 2)
    time_taken_seconds = round(time.time() - session['start_time'], 2)
    minutes = int(time_taken_seconds // 60)
    seconds = int(time_taken_seconds % 60)
    time_taken_formatted = f"{minutes}m {seconds}s"
    #time_taken_minutes = round(time_taken_seconds / 60, 2)  # Convert to minutes
    
    return render_template('results.html', 
                         category=session['category'].capitalize(),
                         total_questions=total_questions,
                         correct=correct,
                         score=score,
                         time_taken=time_taken_formatted,
                         answers=session['answers'])
    
with app.app_context():
    db.create_all()  # Create database tables if they don't exist

if __name__ == '__main__':
    app.run(debug=True)