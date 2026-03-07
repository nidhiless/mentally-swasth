from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message  # ← This is for EMAILS
from datetime import datetime, timedelta, timezone
import random
import uuid
from dotenv import load_dotenv
import os

load_dotenv()

from collections import defaultdict

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    "DATABASE_URL",
    "sqlite:///mentally_swasth.db"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ===== EMAIL CONFIGURATION =====
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
print("MAIL USER:", os.getenv("MAIL_USERNAME"))
print("MAIL PASS:", os.getenv("MAIL_PASSWORD"))
# Initialize extensions
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
mail = Mail(app)

# Database Models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_active = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Gamification stats
    level = db.Column(db.Integer, default=1)
    xp = db.Column(db.Integer, default=50)
    title = db.Column(db.String(50), default='Beginner')
    messages_sent = db.Column(db.Integer, default=0)
    streak_days = db.Column(db.Integer, default=1)
    
    # OTP fields
    is_verified = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    otp_attempts = db.Column(db.Integer, default=0)
    
    # Relationships
    moods = db.relationship('Mood', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')  # ← Renamed
    ratings = db.relationship('Rating', backref='user', lazy=True, cascade='all, delete-orphan')

class Mood(db.Model):
    __tablename__ = 'moods'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mood = db.Column(db.String(20))
    emoji = db.Column(db.String(10))
    value = db.Column(db.Integer)
    note = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# ← RENAMED from Message to ChatMessage to avoid conflict with flask_mail.Message
class ChatMessage(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Rating(db.Model):
    __tablename__ = 'ratings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating_value = db.Column(db.Integer)
    feedback = db.Column(db.Text)
    category = db.Column(db.String(50), default='chat')
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# Wellness tips
WELLNESS_TIPS = [
    "Take 5 deep breaths when you feel overwhelmed.",
    "Write down 3 things you're grateful for today.",
    "Step outside for 5 minutes of fresh air.",
    "Drink a glass of water and stretch your body.",
    "Close your eyes and focus on your breath for 1 minute.",
    "Send a kind message to someone you care about.",
    "Listen to your favorite calming song.",
    "Take a short break from screens.",
    "Practice positive affirmations in the mirror.",
    "Remember: progress, not perfection."
]

# ========== CHAT STORAGE ==========
online_users = {}  # {user_id: username}
chat_history = []  # Store last 50 messages

# Create tables
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# ========== SIGNUP ROUTE ==========
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """New user signup with email"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        
        # Validation
        if not username or not email:
            return render_template('signup.html', error="Username and email are required")
        
        # Check if username exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('signup.html', error="Username already taken")
        
        # Check if email exists
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return render_template('signup.html', error="Email already registered")
        
        # Create new user
        user = User(
            username=username,
            email=email,
            phone=phone,
            last_active=datetime.now(timezone.utc)
        )
        
        db.session.add(user)
        db.session.commit()
        
        return render_template('signup.html', success="Account created successfully! Please login.")
    
    return render_template('signup.html')

# ========== OTP HELPER FUNCTIONS ==========
def generate_otp():
    """Generate a 6-digit OTP"""
    return ''.join(random.choices('0123456789', k=6))

def send_otp_email(user_email, otp, username):
    """Send OTP via email - FIXED VERSION"""
    try:
        print(f"📧 Attempting to send email to: {user_email}")
        print(f"📧 Using account: {app.config['MAIL_USERNAME']}")
        
        # Create message - subject as first argument (positional)
        # This is flask_mail.Message, NOT your database model!
        msg = Message(
            "Your Mentally Swasth Login OTP",  # Subject as first argument
            sender=app.config['MAIL_USERNAME'],
            recipients=[user_email]
        )
        
        msg.body = f"""
Hello {username},

Your OTP for login to Mentally Swasth is: {otp}

This OTP is valid for 5 minutes.

- Mentally Swasth Team
"""
        
        msg.html = f"""
<div style="font-family: 'Poppins', sans-serif; max-width: 500px; margin: 0 auto; padding: 30px; background: linear-gradient(135deg, #6366f1, #10b981); border-radius: 20px;">
    <div style="background: white; padding: 30px; border-radius: 15px;">
        <h1 style="color: #6366f1; margin-bottom: 20px;">Mentally Swasth</h1>
        <h2 style="color: #1f2937;">Hello {username}! 👋</h2>
        <p style="color: #4b5563; font-size: 16px;">Your OTP for login is:</p>
        <div style="background: #f3f4f6; padding: 20px; border-radius: 10px; text-align: center; margin: 20px 0;">
            <span style="font-size: 36px; font-weight: bold; color: #6366f1; letter-spacing: 5px;">{otp}</span>
        </div>
        <p style="color: #6b7280; font-size: 14px;">This OTP is valid for <strong>5 minutes</strong>.</p>
    </div>
</div>
"""
        
        mail.send(msg)
        print("✅ Email sent successfully!")
        return True
    except Exception as e:
        print(f"❌ ERROR sending email: {str(e)}")
        return False

# ========== FIXED VERIFY OTP FUNCTION - NO DUPLICATES, CLEAN INDENTATION ==========
def verify_otp(user, entered_otp):
    """Verify OTP for user"""
    if not user.otp_code or not user.otp_expiry:
        return False, "No OTP found. Please request a new one."

    if user.otp_attempts >= 3:
        return False, "Too many failed attempts. Please request a new OTP."

    # Convert stored expiry to timezone-aware for comparison
    if user.otp_expiry.tzinfo is None:
        expiry = user.otp_expiry.replace(tzinfo=timezone.utc)
    else:
        expiry = user.otp_expiry

    if datetime.now(timezone.utc) > expiry:
        return False, "OTP expired. Please request a new one."

    if user.otp_code != entered_otp:
        user.otp_attempts += 1
        db.session.commit()
        remaining = 3 - user.otp_attempts
        if remaining > 0:
            return False, f"Invalid OTP. {remaining} attempts remaining."
        else:
            return False, "Invalid OTP. No attempts remaining. Please request a new OTP."

    # Success - clear OTP
    user.otp_code = None
    user.otp_expiry = None
    user.otp_attempts = 0
    user.is_verified = True
    db.session.commit()

    return True, "OTP verified successfully!"

# ========== OTP VERIFICATION ROUTES ==========
@app.route('/verify-otp', methods=['POST'])
def verify_otp_route():
    """Verify the OTP entered by user"""
    otp = request.form.get('otp', '').strip()
    username = request.form.get('username', '').strip()
    
    if not otp or len(otp) != 6:
        return render_template('verify-otp.html', 
                             error="Please enter a valid 6-digit OTP",
                             username=username,
                             email=session.get('otp_email', ''))
    
    # Get user from session
    user_id = session.get('otp_user_id')
    if not user_id:
        return redirect(url_for('login'))
    
    user = User.query.get(int(user_id))
    if not user:
        return redirect(url_for('login'))
    
    # Verify OTP
    success, message = verify_otp(user, otp)
    
    if success:
        # Clear OTP session data
        session['user_id'] = str(user.id)
        session['username'] = user.username
        session.pop('otp_user_id', None)
        session.pop('otp_username', None)
        session.pop('otp_email', None)
        
        # Update last active
        user.last_active = datetime.now(timezone.utc)
        db.session.commit()
        
        return redirect(url_for('dashboard'))
    else:
        return render_template('verify-otp.html', 
                             error=message,
                             username=username,
                             email=session.get('otp_email', ''))

@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    """Resend OTP to user's email"""
    data = request.get_json()
    username = data.get('username', '').strip()
    
    # Get user from session
    user_id = session.get('otp_user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    user = User.query.get(int(user_id))
    if not user or user.username != username:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Generate new OTP
    otp = generate_otp()
    user.otp_code = otp
    user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    user.otp_attempts = 0
    db.session.commit()
    
    # Send new OTP
    if send_otp_email(user.email, otp, user.username):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to send OTP'})

# ========== LOGIN ROUTE ==========
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle login - Step 1: Username/Email verification & OTP sending"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        
        if not username or not email:
            return render_template('login.html', error="Username and email are required")
        
        # Find user
        user = User.query.filter_by(username=username).first()
        
        # Check if user exists and email matches
        if not user:
            return render_template('login.html', error="User not found. Please sign up first.")
        
        if user.email != email:
            return render_template('login.html', error="Email does not match this username")
        
        # Generate OTP
        otp = generate_otp()
        user.otp_code = otp
        user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        user.otp_attempts = 0
        db.session.commit()
        
        # Send OTP via email
        if send_otp_email(user.email, otp, user.username):
            # Store in session that we're in OTP stage
            session['otp_user_id'] = user.id
            session['otp_username'] = user.username
            session['otp_email'] = user.email
            
            return render_template('verify-otp.html', 
                                 username=user.username,
                                 email=user.email)
        else:
            return render_template('login.html', error="Failed to send OTP. Please try again.")
    
    return render_template('login.html')

# ========== LOGOUT ROUTE ==========
@app.route('/logout')
def logout():
    """Logout user and clear all session data"""
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(int(session['user_id']))
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    # Calculate progress
    next_level_xp = user.level * 100
    progress_percent = min(100, (user.xp / next_level_xp) * 100) if next_level_xp > 0 else 0
    
    # Get daily tip
    tip_index = hash(f"{user.id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}") % len(WELLNESS_TIPS)
    
    # Get stats
    message_count = ChatMessage.query.filter_by(user_id=user.id).count()  # ← Updated
    mood_count = Mood.query.filter_by(user_id=user.id).count()
    rating_count = Rating.query.filter_by(user_id=user.id).count()
    
    # Get recent moods
    recent_moods = Mood.query.filter_by(user_id=user.id)\
        .order_by(Mood.timestamp.desc())\
        .limit(5).all()
    
    # Format created_at date
    created_at_str = user.created_at.strftime('%b %Y') if user.created_at else 'Recently'
    
    return render_template('dashboard.html',
                         username=user.username,
                         level=user.level,
                         xp=user.xp,
                         title=user.title,
                         streak=user.streak_days,
                         progress=progress_percent,
                         next_xp=next_level_xp,
                         daily_tip=WELLNESS_TIPS[tip_index],
                         total_moods=mood_count,
                         total_messages=message_count,
                         total_ratings=rating_count,
                         recent_moods=recent_moods,
                         created_at=created_at_str)

# ========== CHAT ROUTE ==========
@app.route('/chat')
def chat():
    """Simple community chat - everyone chats together"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(int(session['user_id']))
    
    return render_template('chat.html', 
                         username=user.username,
                         user_id=user.id)

# ========== MOOD ROUTE ==========
@app.route('/mood')
def mood():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(int(session['user_id']))
    
    moods = Mood.query.filter_by(user_id=user.id)\
        .order_by(Mood.timestamp.desc())\
        .all()
    
    if moods:
        avg_mood = sum(m.value for m in moods) / len(moods)
        
        # Find most common mood
        mood_counts = {}
        for m in moods:
            mood_counts[m.mood] = mood_counts.get(m.mood, 0) + 1
        most_common = max(mood_counts, key=mood_counts.get) if mood_counts else None
    else:
        avg_mood = 0
        most_common = None
    
    return render_template('mood.html', 
                         username=user.username,
                         moods=[{
                             'mood': m.mood,
                             'emoji': m.emoji,
                             'value': m.value,
                             'note': m.note,
                             'timestamp': m.timestamp.strftime('%Y-%m-%d %H:%M')
                         } for m in moods],
                         avg_mood=round(avg_mood, 1),
                         total_moods=len(moods),
                         streak=user.streak_days,
                         most_common=most_common)

# ========== LEVEL ROUTE ==========
@app.route('/level')
def level():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(int(session['user_id']))
    
    titles = ['Beginner', 'Listener', 'Supporter', 'Helper', 'Therapist', 'Guide', 'Master', 'Legend', 'Guru', 'Enlightened']
    current_title = titles[min(user.level - 1, len(titles) - 1)]
    
    current_level_xp = (user.level - 1) * 100
    xp_in_level = user.xp - current_level_xp
    progress = (xp_in_level / 100) * 100 if user.level < 10 else 100
    
    # Get total messages and moods for stats
    message_count = ChatMessage.query.filter_by(user_id=user.id).count()  # ← Updated
    mood_count = Mood.query.filter_by(user_id=user.id).count()
    
    return render_template('level.html',
                         username=user.username,
                         level=user.level,
                         xp=user.xp,
                         title=current_title,
                         progress=progress,
                         xp_in_level=xp_in_level,
                         total_messages=message_count,
                         total_moods=mood_count)

# ========== RATING ROUTE ==========
@app.route('/rating')
def rating():
    """Ratings page with real data"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(int(session['user_id']))
    
    # Get user's ratings
    ratings = Rating.query.filter_by(user_id=user.id)\
        .order_by(Rating.timestamp.desc()).all()
    
    # Calculate stats
    total_ratings = len(ratings)
    avg_rating = sum(r.rating_value for r in ratings) / total_ratings if total_ratings > 0 else 0
    total_xp = total_ratings * 5  # 5 XP per rating
    
    return render_template('rating.html',
                         username=user.username,
                         ratings=[{
                             'rating_value': r.rating_value,
                             'feedback': r.feedback,
                             'category': r.category,
                             'timestamp': r.timestamp.strftime('%Y-%m-%d %H:%M')
                         } for r in ratings],
                         avg_rating=round(avg_rating, 1),
                         total_ratings=total_ratings,
                         total_xp=total_xp,
                         streak=user.streak_days)

# ========== API ROUTES ==========
@app.route('/api/recent_moods', methods=['GET'])
def recent_moods():
    if 'user_id' not in session:
        return jsonify({'moods': []})
    
    user_id = int(session['user_id'])
    moods = Mood.query.filter_by(user_id=user_id)\
        .order_by(Mood.timestamp.desc())\
        .limit(5).all()
    
    mood_list = [{
        'mood': m.mood,
        'emoji': m.emoji,
        'value': m.value,
        'timestamp': m.timestamp.strftime('%H:%M')
    } for m in moods]
    
    return jsonify({'moods': mood_list})

@app.route('/api/online_count', methods=['GET'])
def online_count():
    return jsonify({'count': len(online_users)})

@app.route('/api/user_stats', methods=['GET'])
def user_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    user = User.query.get(int(session['user_id']))
    
    # Get most common mood
    moods = Mood.query.filter_by(user_id=user.id).all()
    if moods:
        mood_counts = {}
        for m in moods:
            mood_counts[m.mood] = mood_counts.get(m.mood, 0) + 1
        common_mood = max(mood_counts, key=mood_counts.get)
    else:
        common_mood = None
    
    return jsonify({
        'streak': user.streak_days,
        'commonMood': common_mood
    })

@app.route('/api/mood_data', methods=['GET'])
def mood_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    range_type = request.args.get('range', 'week')
    user_id = int(session['user_id'])
    
    # Get moods based on range
    if range_type == 'week':
        # Last 7 days
        since = datetime.now(timezone.utc) - timedelta(days=7)
        moods = Mood.query.filter_by(user_id=user_id)\
            .filter(Mood.timestamp >= since)\
            .order_by(Mood.timestamp).all()
        
        # Group by day
        daily_moods = defaultdict(list)
        for m in moods:
            day = m.timestamp.strftime('%a')
            daily_moods[day].append(m.value)
        
        # Calculate daily averages
        days_order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        labels = []
        values = []
        
        for day in days_order:
            if daily_moods[day]:
                avg = sum(daily_moods[day]) / len(daily_moods[day])
                values.append(round(avg, 1))
            else:
                values.append(None)
            labels.append(day)
    
    elif range_type == 'month':
        # Last 30 days grouped by week
        since = datetime.now(timezone.utc) - timedelta(days=30)
        moods = Mood.query.filter_by(user_id=user_id)\
            .filter(Mood.timestamp >= since)\
            .order_by(Mood.timestamp).all()
        
        # Group by week
        weekly_moods = [[] for _ in range(4)]
        for m in moods:
            days_ago = (datetime.now(timezone.utc) - m.timestamp).days
            week_index = min(3, days_ago // 7)
            weekly_moods[3 - week_index].append(m.value)
        
        labels = ['Week 1', 'Week 2', 'Week 3', 'Week 4']
        values = []
        for week in weekly_moods:
            if week:
                avg = sum(week) / len(week)
                values.append(round(avg, 1))
            else:
                values.append(None)
    
    else:  # 3 months
        since = datetime.now(timezone.utc) - timedelta(days=90)
        moods = Mood.query.filter_by(user_id=user_id)\
            .filter(Mood.timestamp >= since)\
            .order_by(Mood.timestamp).all()
        
        # Group by month
        monthly_moods = defaultdict(list)
        for m in moods:
            month = m.timestamp.strftime('%b')
            monthly_moods[month].append(m.value)
        
        months_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        current_month = datetime.now(timezone.utc).month
        start_idx = max(0, current_month - 4)
        labels = months_order[start_idx:current_month]
        values = []
        
        for month in labels:
            if monthly_moods[month]:
                avg = sum(monthly_moods[month]) / len(monthly_moods[month])
                values.append(round(avg, 1))
            else:
                values.append(None)
    
    return jsonify({
        'labels': labels,
        'values': values
    })

@app.route('/api/save_mood', methods=['POST'])
def save_mood():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.json
    user = User.query.get(int(session['user_id']))
    
    mood_entry = Mood(
        user_id=user.id,
        mood=data.get('mood'),
        emoji=data.get('emoji', '😐'),
        value=data.get('value', 3),
        note=data.get('note', '')
    )
    
    db.session.add(mood_entry)
    user.xp += 10
    
    # Update streak
    user.streak_days += 1
    
    leveled_up = False
    if user.xp >= user.level * 100:
        user.level += 1
        leveled_up = True
    
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'xp': 10,
        'leveled_up': leveled_up,
        'new_level': user.level if leveled_up else None
    })

@app.route('/api/save_rating', methods=['POST'])
def save_rating():
    """Save real rating to database"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.json
    user = User.query.get(int(session['user_id']))
    
    rating = Rating(
        user_id=user.id,
        rating_value=data.get('rating'),
        feedback=data.get('feedback', ''),
        category=data.get('category', 'chat')
    )
    
    db.session.add(rating)
    user.xp += 5
    db.session.commit()
    
    return jsonify({'success': True, 'xp': 5})

# ========== SIMPLE CHAT SOCKET EVENTS ==========
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        user_id = session['user_id']
        username = session['username']
        
        # Add to online users
        online_users[user_id] = username
        
        # Send welcome message
        welcome_msg = {
            'username': 'System',
            'message': f'👋 {username} joined the chat',
            'timestamp': datetime.now(timezone.utc).strftime('%H:%M'),
            'type': 'system'
        }
        chat_history.append(welcome_msg)
        if len(chat_history) > 50:
            chat_history.pop(0)
        
        # Broadcast to everyone
        emit('receive_message', welcome_msg, broadcast=True)
        emit('update_users', {
            'users': list(online_users.values()),
            'count': len(online_users)
        }, broadcast=True)
        
        # Send chat history to new user
        emit('chat_history', {'messages': chat_history})

@socketio.on('join_community')
def handle_join_community():
    """Handle user joining community chat"""
    if 'user_id' in session:
        user_id = session['user_id']
        username = session['username']
        
        # Ensure user is in online_users
        if user_id not in online_users:
            online_users[user_id] = username
            
            # Send welcome message
            welcome_msg = {
                'username': 'System',
                'message': f'👋 {username} joined the chat',
                'timestamp': datetime.now(timezone.utc).strftime('%H:%M'),
                'type': 'system'
            }
            chat_history.append(welcome_msg)
            if len(chat_history) > 50:
                chat_history.pop(0)
            
            emit('receive_message', welcome_msg, broadcast=True)
            emit('update_users', {
                'users': list(online_users.values()),
                'count': len(online_users)
            }, broadcast=True)

@socketio.on('send_message')
def handle_message(data):
    if 'user_id' not in session:
        return
    
    user_id = session['user_id']
    username = session['username']
    message = data.get('message', '').strip()
    
    if not message:
        return
    
    # Create message
    msg_obj = {
        'username': username,
        'message': message,
        'timestamp': datetime.now(timezone.utc).strftime('%H:%M'),
        'user_id': user_id
    }
    
    # Save to history
    chat_history.append(msg_obj)
    if len(chat_history) > 50:
        chat_history.pop(0)
    
    # Save to database - using ChatMessage model now
    db_message = ChatMessage(
        user_id=int(user_id),
        content=message
    )
    db.session.add(db_message)
    
    # Update user stats
    user = User.query.get(int(user_id))
    if user:
        user.messages_sent += 1
        user.xp += 2
        if user.xp >= user.level * 100:
            user.level += 1
        db.session.commit()
    
    # Broadcast to everyone
    emit('receive_message', msg_obj, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    if 'user_id' not in session:
        return
    
    emit('user_typing', {
        'username': session['username'],
        'typing': data.get('typing', False)
    }, broadcast=True, include_self=False)

@socketio.on('disconnect')
def handle_disconnect():
    if 'user_id' in session:
        user_id = session['user_id']
        username = session['username']
        
        # Remove from online users
        if user_id in online_users:
            del online_users[user_id]
        
        # Send leave message
        leave_msg = {
            'username': 'System',
            'message': f'👋 {username} left the chat',
            'timestamp': datetime.now(timezone.utc).strftime('%H:%M'),
            'type': 'system'
        }
        chat_history.append(leave_msg)
        if len(chat_history) > 50:
            chat_history.pop(0)
        
        emit('receive_message', leave_msg, broadcast=True)
        emit('update_users', {
            'users': list(online_users.values()),
            'count': len(online_users)
        }, broadcast=True)
        
        # Update last active
        user = User.query.get(int(user_id))
        if user:
            user.last_active = datetime.now(timezone.utc)
            db.session.commit()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)