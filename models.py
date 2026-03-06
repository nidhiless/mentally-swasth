# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True)  # Nullable for OTP users
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_active = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # OTP Fields (NEW)
    is_verified = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    otp_attempts = db.Column(db.Integer, default=0)
    
    # Gamification stats
    level = db.Column(db.Integer, default=1)
    xp = db.Column(db.Integer, default=50)  # Start with 50 XP
    title = db.Column(db.String(50), default='Beginner')
    streak_days = db.Column(db.Integer, default=1)  # Start with 1
    total_messages = db.Column(db.Integer, default=0)
    total_sessions = db.Column(db.Integer, default=0)
    total_moods = db.Column(db.Integer, default=0)  # NEW: Track total moods
    total_ratings = db.Column(db.Integer, default=0)  # NEW: Track total ratings
    
    # Relationships
    moods = db.relationship('Mood', backref='user', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')  # Fixed: ChatMessage
    ratings = db.relationship('Rating', backref='user', lazy=True, cascade='all, delete-orphan')
    achievements = db.relationship('UserAchievement', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_sessions = db.relationship('ChatSession', backref='user', lazy=True, cascade='all, delete-orphan')  # NEW
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        if not self.password_hash:
            return False  # OTP users don't have password
        return check_password_hash(self.password_hash, password)
    
    def add_xp(self, amount):
        self.xp += amount
        # Level up logic (every 100 XP = 1 level)
        new_level = (self.xp // 100) + 1
        if new_level > self.level:
            self.level = new_level
            self.update_title()
            return True  # Leveled up
        return False
    
    def update_title(self):
        titles = {
            1: 'Beginner',
            2: 'Listener',
            3: 'Supporter',
            4: 'Helper',
            5: 'Therapist Apprentice',
            6: 'Therapist',
            7: 'Guide',
            8: 'Mentor',
            9: 'Healer',
            10: 'Mental Wellness Master'
        }
        self.title = titles.get(self.level, 'Legend')
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'level': self.level,
            'xp': self.xp,
            'title': self.title,
            'streak_days': self.streak_days,
            'total_messages': self.total_messages,
            'total_moods': self.total_moods,
            'total_ratings': self.total_ratings,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_active': self.last_active.isoformat() if self.last_active else None
        }

class Mood(db.Model):
    __tablename__ = 'moods'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mood = db.Column(db.String(20))  # happy, sad, anxious, etc.
    emoji = db.Column(db.String(10))  # 😊, 😢, etc.
    value = db.Column(db.Integer)  # 1-5 scale
    note = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'mood': self.mood,
            'emoji': self.emoji,
            'value': self.value,
            'note': self.note,
            'timestamp': self.timestamp.isoformat()
        }

# FIXED: Renamed to ChatMessage to avoid conflict with flask_mail.Message
class ChatMessage(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_bot = db.Column(db.Boolean, default=False)  # For future bot support
    bot_name = db.Column(db.String(50), nullable=True)
    room_id = db.Column(db.String(100), default='community-chat')  # For multiple rooms
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'is_bot': self.is_bot,
            'bot_name': self.bot_name,
            'room_id': self.room_id,
            'timestamp': self.timestamp.isoformat(),
            'username': self.user.username if self.user else None
        }

class Rating(db.Model):
    __tablename__ = 'ratings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating_value = db.Column(db.Integer)  # 1-5 stars
    feedback = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), default='chat')  # 'chat', 'mood', 'general'
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'rating': self.rating_value,
            'feedback': self.feedback,
            'category': self.category,
            'timestamp': self.timestamp.isoformat()
        }

class Achievement(db.Model):
    __tablename__ = 'achievements'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(50))  # Font Awesome icon name
    xp_reward = db.Column(db.Integer, default=50)
    condition_type = db.Column(db.String(50))  # 'mood_count', 'chat_count', 'streak', etc.
    condition_value = db.Column(db.Integer)  # e.g., 10 for 10 moods tracked
    
    users = db.relationship('UserAchievement', backref='achievement', lazy=True)

class UserAchievement(db.Model):
    __tablename__ = 'user_achievements'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievements.id'), nullable=False)
    earned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (db.UniqueConstraint('user_id', 'achievement_id', name='unique_user_achievement'),)

class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'
    
    id = db.Column(db.String(100), primary_key=True)  # UUID
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = db.Column(db.DateTime, nullable=True)
    message_count = db.Column(db.Integer, default=0)
    feedback = db.Column(db.Text, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'started_at': self.started_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'message_count': self.message_count
        }

# Initialize default achievements
def init_achievements():
    achievements = [
        {
            'name': 'First Steps',
            'description': 'Track your first mood',
            'icon': 'fa-smile',
            'xp_reward': 50,
            'condition_type': 'mood_count',
            'condition_value': 1
        },
        {
            'name': 'Mood Tracker',
            'description': 'Track 10 moods',
            'icon': 'fa-chart-line',
            'xp_reward': 100,
            'condition_type': 'mood_count',
            'condition_value': 10
        },
        {
            'name': 'Mood Master',
            'description': 'Track 50 moods',
            'icon': 'fa-crown',
            'xp_reward': 250,
            'condition_type': 'mood_count',
            'condition_value': 50
        },
        {
            'name': 'First Chat',
            'description': 'Send your first message',
            'icon': 'fa-comment',
            'xp_reward': 50,
            'condition_type': 'message_count',
            'condition_value': 1
        },
        {
            'name': 'Support Seeker',
            'description': 'Send 50 messages',
            'icon': 'fa-comments',
            'xp_reward': 150,
            'condition_type': 'message_count',
            'condition_value': 50
        },
        {
            'name': 'Chat Enthusiast',
            'description': 'Send 200 messages',
            'icon': 'fa-rocket',
            'xp_reward': 400,
            'condition_type': 'message_count',
            'condition_value': 200
        },
        {
            'name': '7-Day Streak',
            'description': 'Use the app for 7 days in a row',
            'icon': 'fa-fire',
            'xp_reward': 200,
            'condition_type': 'streak',
            'condition_value': 7
        },
        {
            'name': '30-Day Streak',
            'description': 'Use the app for 30 days in a row',
            'icon': 'fa-calendar-check',
            'xp_reward': 500,
            'condition_type': 'streak',
            'condition_value': 30
        },
        {
            'name': 'Level 5 Achieved',
            'description': 'Reach level 5',
            'icon': 'fa-star',
            'xp_reward': 200,
            'condition_type': 'level',
            'condition_value': 5
        },
        {
            'name': 'Level 10 Achieved',
            'description': 'Reach level 10',
            'icon': 'fa-gem',
            'xp_reward': 500,
            'condition_type': 'level',
            'condition_value': 10
        },
        {
            'name': 'Rated & Reviewed',
            'description': 'Leave your first rating',
            'icon': 'fa-star-half-alt',
            'xp_reward': 30,
            'condition_type': 'rating_count',
            'condition_value': 1
        },
        {
            'name': 'Helpful Reviewer',
            'description': 'Leave 10 ratings',
            'icon': 'fa-pen',
            'xp_reward': 150,
            'condition_type': 'rating_count',
            'condition_value': 10
        }
    ]
    
    for ach_data in achievements:
        existing = Achievement.query.filter_by(name=ach_data['name']).first()
        if not existing:
            ach = Achievement(**ach_data)
            db.session.add(ach)
    
    db.session.commit()