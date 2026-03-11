from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import random
import requests
from dotenv import load_dotenv
import os
from collections import defaultdict

load_dotenv()

app = Flask(__name__)

# Configuration — SECRET_KEY must be set before anything else
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'mentally-swasth-secret-key-2024')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # set True only if HTTPS enforced
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    "DATABASE_URL",
    "sqlite:///mentally_swasth.db"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ========== DATABASE MODELS ==========
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_active = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    level = db.Column(db.Integer, default=1)
    xp = db.Column(db.Integer, default=50)
    title = db.Column(db.String(50), default='Beginner')
    messages_sent = db.Column(db.Integer, default=0)
    streak_days = db.Column(db.Integer, default=1)

    is_verified = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    otp_attempts = db.Column(db.Integer, default=0)

    moods = db.relationship('Mood', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')
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

online_users = {}
chat_history = []

with app.app_context():
    db.create_all()


# ========== RESEND EMAIL ==========
def send_otp_email(user_email, otp, username):
    try:
        print(f"📧 Attempting to send email to: {user_email}")
        RESEND_API_KEY = os.getenv('RESEND_API_KEY')
        MAIL_FROM = os.getenv('MAIL_FROM', 'Mentally Swasth <onboarding@resend.dev>')

        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "from": MAIL_FROM,
                "to": [user_email],
                "subject": "Your Mentally Swasth Login OTP",
                "text": f"Hello {username},\n\nYour OTP for Mentally Swasth is: {otp}\n\nValid for 5 minutes.\n\n- Mentally Swasth Team",
                "html": f"""
<div style="font-family:sans-serif;max-width:500px;margin:0 auto;padding:30px;background:linear-gradient(135deg,#6366f1,#10b981);border-radius:20px;">
  <div style="background:white;padding:30px;border-radius:15px;">
    <h1 style="color:#6366f1;margin-bottom:20px;">Mentally Swasth</h1>
    <h2 style="color:#1f2937;">Hello {username}! 👋</h2>
    <p style="color:#4b5563;font-size:16px;">Your OTP for login is:</p>
    <div style="background:#f3f4f6;padding:20px;border-radius:10px;text-align:center;margin:20px 0;">
      <span style="font-size:36px;font-weight:bold;color:#6366f1;letter-spacing:5px;">{otp}</span>
    </div>
    <p style="color:#6b7280;font-size:14px;">Valid for <strong>5 minutes</strong>.</p>
  </div>
</div>"""
            }
        )

        if response.status_code in (200, 201):
            print("✅ Email sent successfully!")
            return True
        else:
            print(f"❌ Resend error {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print(f"❌ ERROR sending email: {str(e)}")
        return False


# ========== OTP HELPERS ==========
def generate_otp():
    return ''.join(random.choices('0123456789', k=6))


def verify_otp(user, entered_otp):
    if not user.otp_code or not user.otp_expiry:
        return False, "No OTP found. Please request a new one."
    if user.otp_attempts >= 3:
        return False, "Too many failed attempts. Please request a new OTP."

    expiry = user.otp_expiry.replace(tzinfo=timezone.utc) if user.otp_expiry.tzinfo is None else user.otp_expiry
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

    user.otp_code = None
    user.otp_expiry = None
    user.otp_attempts = 0
    user.is_verified = True
    db.session.commit()
    return True, "OTP verified successfully!"


# ========== ROUTES ==========
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()

        if not username or not email:
            return render_template('signup.html', error="Username and email are required")
        if User.query.filter_by(username=username).first():
            return render_template('signup.html', error="Username already taken")
        if User.query.filter_by(email=email).first():
            return render_template('signup.html', error="Email already registered")

        user = User(username=username, email=email, phone=phone,
                    last_active=datetime.now(timezone.utc))
        db.session.add(user)
        db.session.commit()
        return render_template('signup.html', success="Account created successfully! Please login.")

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()

        if not username or not email:
            return render_template('login.html', error="Username and email are required")

        user = User.query.filter_by(username=username).first()
        if not user:
            return render_template('login.html', error="User not found. Please sign up first.")
        if user.email != email:
            return render_template('login.html', error="Email does not match this username")

        otp = generate_otp()
        user.otp_code = otp
        user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        user.otp_attempts = 0
        db.session.commit()

        if send_otp_email(user.email, otp, user.username):
            # ✅ Save to session THEN redirect — this is the key fix
            session.permanent = True
            session['otp_user_id'] = user.id
            session['otp_username'] = user.username
            session['otp_email'] = user.email
            return redirect(url_for('verify_otp_page'))  # ← REDIRECT not render_template
        else:
            return render_template('login.html', error="Failed to send OTP. Please try again.")

    return render_template('login.html')


# ========== SEPARATE GET ROUTE FOR OTP PAGE ==========
@app.route('/verify-otp', methods=['GET'])
def verify_otp_page():
    """Show the OTP verification page"""
    user_id = session.get('otp_user_id')
    if not user_id:
        return redirect(url_for('login'))

    return render_template('verify-otp.html',
                           username=session.get('otp_username', ''),
                           email=session.get('otp_email', ''))


@app.route('/verify-otp', methods=['POST'])
def verify_otp_route():
    """Handle OTP form submission"""
    otp = request.form.get('otp', '').strip()
    username = request.form.get('username', '').strip()

    if not otp or len(otp) != 6:
        return render_template('verify-otp.html', error="Please enter a valid 6-digit OTP",
                               username=username, email=session.get('otp_email', ''))

    user_id = session.get('otp_user_id')
    print(f"DEBUG verify: user_id from session = {user_id}, session = {dict(session)}")

    if not user_id:
        return redirect(url_for('login'))

    user = User.query.get(int(user_id))
    if not user:
        return redirect(url_for('login'))

    success, message = verify_otp(user, otp)

    if success:
        session.permanent = True
        session['user_id'] = str(user.id)
        session['username'] = user.username
        session.pop('otp_user_id', None)
        session.pop('otp_username', None)
        session.pop('otp_email', None)
        user.last_active = datetime.now(timezone.utc)
        db.session.commit()
        print(f"DEBUG: ✅ Login success for {user.username}, session={dict(session)}")
        return redirect(url_for('dashboard'))
    else:
        return render_template('verify-otp.html', error=message,
                               username=username, email=session.get('otp_email', ''))


@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    data = request.get_json()
    username = data.get('username', '').strip()
    user_id = session.get('otp_user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Session expired'})

    user = User.query.get(int(user_id))
    if not user or user.username != username:
        return jsonify({'success': False, 'error': 'User not found'})

    otp = generate_otp()
    user.otp_code = otp
    user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    user.otp_attempts = 0
    db.session.commit()

    if send_otp_email(user.email, otp, user.username):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Failed to send OTP'})


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        print(f"DEBUG: ❌ No user_id in session at dashboard. Session={dict(session)}")
        return redirect(url_for('login'))
    user = User.query.get(int(session['user_id']))
    if not user:
        session.clear()
        return redirect(url_for('login'))

    next_level_xp = user.level * 100
    progress_percent = min(100, (user.xp / next_level_xp) * 100) if next_level_xp > 0 else 0
    tip_index = hash(f"{user.id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}") % len(WELLNESS_TIPS)
    message_count = ChatMessage.query.filter_by(user_id=user.id).count()
    mood_count = Mood.query.filter_by(user_id=user.id).count()
    rating_count = Rating.query.filter_by(user_id=user.id).count()
    recent_moods = Mood.query.filter_by(user_id=user.id).order_by(Mood.timestamp.desc()).limit(5).all()
    created_at_str = user.created_at.strftime('%b %Y') if user.created_at else 'Recently'

    return render_template('dashboard.html',
                           username=user.username, level=user.level, xp=user.xp,
                           title=user.title, streak=user.streak_days, progress=progress_percent,
                           next_xp=next_level_xp, daily_tip=WELLNESS_TIPS[tip_index],
                           total_moods=mood_count, total_messages=message_count,
                           total_ratings=rating_count, recent_moods=recent_moods,
                           created_at=created_at_str)


@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(int(session['user_id']))
    return render_template('chat.html', username=user.username, user_id=user.id)


@app.route('/mood')
def mood():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(int(session['user_id']))
    moods = Mood.query.filter_by(user_id=user.id).order_by(Mood.timestamp.desc()).all()

    avg_mood = sum(m.value for m in moods) / len(moods) if moods else 0
    mood_counts = {}
    for m in moods:
        mood_counts[m.mood] = mood_counts.get(m.mood, 0) + 1
    most_common = max(mood_counts, key=mood_counts.get) if mood_counts else None

    return render_template('mood.html', username=user.username,
                           moods=[{'mood': m.mood, 'emoji': m.emoji, 'value': m.value,
                                   'note': m.note, 'timestamp': m.timestamp.strftime('%Y-%m-%d %H:%M')} for m in moods],
                           avg_mood=round(avg_mood, 1), total_moods=len(moods),
                           streak=user.streak_days, most_common=most_common)


@app.route('/level')
def level():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(int(session['user_id']))
    titles = ['Beginner', 'Listener', 'Supporter', 'Helper', 'Therapist',
              'Guide', 'Master', 'Legend', 'Guru', 'Enlightened']
    current_title = titles[min(user.level - 1, len(titles) - 1)]
    xp_in_level = user.xp - (user.level - 1) * 100
    progress = (xp_in_level / 100) * 100 if user.level < 10 else 100

    return render_template('level.html', username=user.username, level=user.level,
                           xp=user.xp, title=current_title, progress=progress,
                           xp_in_level=xp_in_level,
                           total_messages=ChatMessage.query.filter_by(user_id=user.id).count(),
                           total_moods=Mood.query.filter_by(user_id=user.id).count())


@app.route('/rating')
def rating():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(int(session['user_id']))
    ratings = Rating.query.filter_by(user_id=user.id).order_by(Rating.timestamp.desc()).all()
    total_ratings = len(ratings)
    avg_rating = sum(r.rating_value for r in ratings) / total_ratings if total_ratings > 0 else 0

    return render_template('rating.html', username=user.username,
                           ratings=[{'rating_value': r.rating_value, 'feedback': r.feedback,
                                     'category': r.category,
                                     'timestamp': r.timestamp.strftime('%Y-%m-%d %H:%M')} for r in ratings],
                           avg_rating=round(avg_rating, 1), total_ratings=total_ratings,
                           total_xp=total_ratings * 5, streak=user.streak_days)


# ========== API ROUTES ==========
@app.route('/api/recent_moods')
def recent_moods():
    if 'user_id' not in session:
        return jsonify({'moods': []})
    moods = Mood.query.filter_by(user_id=int(session['user_id'])).order_by(Mood.timestamp.desc()).limit(5).all()
    return jsonify({'moods': [{'mood': m.mood, 'emoji': m.emoji, 'value': m.value,
                                'timestamp': m.timestamp.strftime('%H:%M')} for m in moods]})


@app.route('/api/online_count')
def online_count():
    return jsonify({'count': len(online_users)})


@app.route('/api/user_stats')
def user_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    user = User.query.get(int(session['user_id']))
    moods = Mood.query.filter_by(user_id=user.id).all()
    mood_counts = {}
    for m in moods:
        mood_counts[m.mood] = mood_counts.get(m.mood, 0) + 1
    common_mood = max(mood_counts, key=mood_counts.get) if mood_counts else None
    return jsonify({'streak': user.streak_days, 'commonMood': common_mood})


@app.route('/api/mood_data')
def mood_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    range_type = request.args.get('range', 'week')
    user_id = int(session['user_id'])

    if range_type == 'week':
        since = datetime.now(timezone.utc) - timedelta(days=7)
        moods = Mood.query.filter_by(user_id=user_id).filter(Mood.timestamp >= since).order_by(Mood.timestamp).all()
        daily_moods = defaultdict(list)
        for m in moods:
            daily_moods[m.timestamp.strftime('%a')].append(m.value)
        days_order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        labels = days_order
        values = [round(sum(daily_moods[d]) / len(daily_moods[d]), 1) if daily_moods[d] else None for d in days_order]

    elif range_type == 'month':
        since = datetime.now(timezone.utc) - timedelta(days=30)
        moods = Mood.query.filter_by(user_id=user_id).filter(Mood.timestamp >= since).order_by(Mood.timestamp).all()
        weekly_moods = [[] for _ in range(4)]
        for m in moods:
            days_ago = (datetime.now(timezone.utc) - m.timestamp).days
            weekly_moods[min(3, days_ago // 7)].append(m.value)
        weekly_moods = weekly_moods[::-1]
        labels = ['Week 1', 'Week 2', 'Week 3', 'Week 4']
        values = [round(sum(w) / len(w), 1) if w else None for w in weekly_moods]

    else:
        since = datetime.now(timezone.utc) - timedelta(days=90)
        moods = Mood.query.filter_by(user_id=user_id).filter(Mood.timestamp >= since).order_by(Mood.timestamp).all()
        monthly_moods = defaultdict(list)
        for m in moods:
            monthly_moods[m.timestamp.strftime('%b')].append(m.value)
        months_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        current_month = datetime.now(timezone.utc).month
        labels = months_order[max(0, current_month - 4):current_month]
        values = [round(sum(monthly_moods[m]) / len(monthly_moods[m]), 1) if monthly_moods[m] else None for m in labels]

    return jsonify({'labels': labels, 'values': values})


@app.route('/api/save_mood', methods=['POST'])
def save_mood():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    data = request.json
    user = User.query.get(int(session['user_id']))
    db.session.add(Mood(user_id=user.id, mood=data.get('mood'), emoji=data.get('emoji', '😐'),
                        value=data.get('value', 3), note=data.get('note', '')))
    user.xp += 10
    user.streak_days += 1
    leveled_up = False
    if user.xp >= user.level * 100:
        user.level += 1
        leveled_up = True
    db.session.commit()
    return jsonify({'success': True, 'xp': 10, 'leveled_up': leveled_up,
                    'new_level': user.level if leveled_up else None})


@app.route('/api/save_rating', methods=['POST'])
def save_rating():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    data = request.json
    user = User.query.get(int(session['user_id']))
    db.session.add(Rating(user_id=user.id, rating_value=data.get('rating'),
                          feedback=data.get('feedback', ''), category=data.get('category', 'chat')))
    user.xp += 5
    db.session.commit()
    return jsonify({'success': True, 'xp': 5})


# ========== SOCKET EVENTS ==========
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        user_id = session['user_id']
        username = session['username']
        online_users[user_id] = username

        welcome_msg = {'username': 'System', 'message': f'👋 {username} joined the chat',
                       'timestamp': datetime.now(timezone.utc).strftime('%H:%M'), 'type': 'system'}
        chat_history.append(welcome_msg)
        if len(chat_history) > 50:
            chat_history.pop(0)

        emit('receive_message', welcome_msg, broadcast=True)
        emit('update_users', {'users': list(online_users.values()), 'count': len(online_users)}, broadcast=True)
        emit('chat_history', {'messages': chat_history})


@socketio.on('join_community')
def handle_join_community():
    if 'user_id' in session:
        user_id = session['user_id']
        username = session['username']
        if user_id not in online_users:
            online_users[user_id] = username
            welcome_msg = {'username': 'System', 'message': f'👋 {username} joined the chat',
                           'timestamp': datetime.now(timezone.utc).strftime('%H:%M'), 'type': 'system'}
            chat_history.append(welcome_msg)
            if len(chat_history) > 50:
                chat_history.pop(0)
            emit('receive_message', welcome_msg, broadcast=True)
            emit('update_users', {'users': list(online_users.values()), 'count': len(online_users)}, broadcast=True)


@socketio.on('send_message')
def handle_message(data):
    if 'user_id' not in session:
        return
    user_id = session['user_id']
    username = session['username']
    message = data.get('message', '').strip()
    if not message:
        return

    msg_obj = {'username': username, 'message': message,
               'timestamp': datetime.now(timezone.utc).strftime('%H:%M'), 'user_id': user_id}
    chat_history.append(msg_obj)
    if len(chat_history) > 50:
        chat_history.pop(0)

    db.session.add(ChatMessage(user_id=int(user_id), content=message))
    user = User.query.get(int(user_id))
    if user:
        user.messages_sent += 1
        user.xp += 2
        if user.xp >= user.level * 100:
            user.level += 1
        db.session.commit()
    emit('receive_message', msg_obj, broadcast=True)


@socketio.on('typing')
def handle_typing(data):
    if 'user_id' not in session:
        return
    emit('user_typing', {'username': session['username'], 'typing': data.get('typing', False)},
         broadcast=True, include_self=False)


@socketio.on('disconnect')
def handle_disconnect():
    if 'user_id' in session:
        user_id = session['user_id']
        username = session['username']
        if user_id in online_users:
            del online_users[user_id]

        leave_msg = {'username': 'System', 'message': f'👋 {username} left the chat',
                     'timestamp': datetime.now(timezone.utc).strftime('%H:%M'), 'type': 'system'}
        chat_history.append(leave_msg)
        if len(chat_history) > 50:
            chat_history.pop(0)

        emit('receive_message', leave_msg, broadcast=True)
        emit('update_users', {'users': list(online_users.values()), 'count': len(online_users)}, broadcast=True)

        user = User.query.get(int(user_id))
        if user:
            user.last_active = datetime.now(timezone.utc)
            db.session.commit()


if __name__ == '__main__':
    socketio.run(app)