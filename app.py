from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
import uuid

# ========== ИНИЦИАЛИЗАЦИЯ ==========
app = Flask(__name__)
app.config['SECRET_KEY'] = 'maxikold-secret-key-2026-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///maxikold.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Создаем папки
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'stories'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'voice'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'groups'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'channels'), exist_ok=True)

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ========== МОДЕЛИ БАЗЫ ДАННЫХ ==========

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), default='avatars/default.png')
    bio = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    likes = db.relationship('Like', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy=True, cascade='all, delete-orphan')
    
    def likes_count(self):
        return len(self.likes)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_like'),)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room = db.Column(db.String(50), default='global')
    user = db.relationship('User', backref='messages')

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    media_type = db.Column(db.String(10), default='photo')
    media_url = db.Column(db.String(200))
    caption = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=24))
    user = db.relationship('User', backref='stories')

# ========== НОВЫЕ МОДЕЛИ (личные сообщения, группы, каналы) ==========

class PrivateChat(db.Model):
    """Личный чат между двумя пользователями"""
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_message = db.Column(db.Text)
    last_message_time = db.Column(db.DateTime, default=datetime.utcnow)
    
    user1 = db.relationship('User', foreign_keys=[user1_id])
    user2 = db.relationship('User', foreign_keys=[user2_id])
    messages = db.relationship('PrivateMessage', backref='chat', lazy=True, cascade='all, delete-orphan')
    
    def get_other_user(self, current_user_id):
        return self.user1 if self.user2_id == current_user_id else self.user2

class PrivateMessage(db.Model):
    """Сообщение в личном чате"""
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('private_chat.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    media_type = db.Column(db.String(20), default='text')
    media_url = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', backref='private_messages')

class GroupChat(db.Model):
    """Групповой чат"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.String(200), default='groups/default.png')
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    creator = db.relationship('User', foreign_keys=[created_by])
    members = db.relationship('GroupMember', backref='group', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('GroupMessage', backref='group', lazy=True, cascade='all, delete-orphan')

class GroupMember(db.Model):
    """Участник группы"""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group_chat.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    role = db.Column(db.String(20), default='member')
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='group_memberships')

class GroupMessage(db.Model):
    """Сообщение в группе"""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group_chat.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)
    media_type = db.Column(db.String(20), default='text')
    media_url = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='group_messages')

class Channel(db.Model):
    """Канал"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), unique=True)
    avatar = db.Column(db.String(200), default='channels/default.png')
    description = db.Column(db.Text)
    is_private = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    creator = db.relationship('User', foreign_keys=[created_by])
    subscribers = db.relationship('ChannelSubscriber', backref='channel', lazy=True, cascade='all, delete-orphan')
    posts = db.relationship('ChannelPost', backref='channel', lazy=True, cascade='all, delete-orphan')

class ChannelSubscriber(db.Model):
    """Подписчик канала"""
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    role = db.Column(db.String(20), default='subscriber')
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='channel_subscriptions')

class ChannelPost(db.Model):
    """Пост в канале"""
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)
    media_url = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='channel_posts')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# ========== МАРШРУТЫ ==========

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('feed'))
    return render_template('landing.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'danger')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Войдите в аккаунт', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('feed'))
        
        flash('Неверное имя пользователя или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/feed')
@login_required
def feed():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('index.html', posts=posts)

@app.route('/create_post', methods=['POST'])
@login_required
def create_post():
    content = request.form.get('content', '')
    image = request.files.get('image')
    
    if not content and not image:
        flash('Пост не может быть пустым', 'danger')
        return redirect(url_for('feed'))
    
    post = Post(content=content, user_id=current_user.id)
    
    if image and allowed_file(image.filename):
        filename = secure_filename(f"{uuid.uuid4().hex}_{image.filename}")
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        post.image = filename
    
    db.session.add(post)
    db.session.commit()
    
    flash('Пост опубликован!', 'success')
    return redirect(url_for('feed'))

@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if like:
        db.session.delete(like)
        liked = False
    else:
        like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(like)
        liked = True
    
    db.session.commit()
    return jsonify({'liked': liked, 'count': post.likes_count()})

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    content = request.form.get('content')
    if content:
        comment = Comment(content=content, user_id=current_user.id, post_id=post_id)
        db.session.add(comment)
        db.session.commit()
        flash('Комментарий добавлен!', 'success')
    
    return redirect(url_for('feed'))

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()
    return render_template('profile.html', profile_user=user, posts=posts)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio', '')
        avatar = request.files.get('avatar')
        
        if avatar and allowed_file(avatar.filename):
            filename = secure_filename(f"avatars/{current_user.id}_{uuid.uuid4().hex}_{avatar.filename}")
            avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.avatar = filename
        
        db.session.commit()
        flash('Профиль обновлен!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    
    return render_template('edit_profile.html')

@app.route('/chat')
@login_required
def chat():
    messages = Message.query.filter_by(room='global').order_by(Message.timestamp).all()
    return render_template('chat.html', messages=messages)

@app.route('/users')
@login_required
def users():
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('users.html', users=users)

@app.route('/api/stories')
@login_required
def get_stories():
    stories = Story.query.filter(
        Story.expires_at > datetime.utcnow()
    ).order_by(Story.created_at.desc()).all()
    
    result = []
    for story in stories:
        result.append({
            'id': story.id,
            'user_id': story.user_id,
            'username': story.user.username,
            'avatar': story.user.avatar,
            'media_url': url_for('static', filename=story.media_url),
            'caption': story.caption,
            'created_at': story.created_at.strftime('%H:%M')
        })
    
    return jsonify(result)

@app.route('/api/create_story', methods=['POST'])
@login_required
def create_story():
    if 'story' not in request.files:
        return jsonify({'success': False, 'error': 'No file'}), 400
    
    file = request.files['story']
    caption = request.form.get('caption', '')
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"stories/{current_user.id}_{uuid.uuid4().hex}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        story = Story(
            user_id=current_user.id,
            media_url=filename,
            caption=caption
        )
        db.session.add(story)
        db.session.commit()
        
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Invalid file'}), 400

# ========== ЛИЧНЫЕ СООБЩЕНИЯ ==========

@app.route('/messages')
@login_required
def messages():
    chats = PrivateChat.query.filter(
        (PrivateChat.user1_id == current_user.id) | 
        (PrivateChat.user2_id == current_user.id)
    ).order_by(PrivateChat.last_message_time.desc()).all()
    
    return render_template('private_chats.html', chats=chats)

@app.route('/messages/<int:user_id>')
@login_required
def private_chat(user_id):
    other_user = User.query.get_or_404(user_id)
    
    chat = PrivateChat.query.filter(
        ((PrivateChat.user1_id == current_user.id) & (PrivateChat.user2_id == user_id)) |
        ((PrivateChat.user1_id == user_id) & (PrivateChat.user2_id == current_user.id))
    ).first()
    
    if not chat:
        chat = PrivateChat(user1_id=current_user.id, user2_id=user_id)
        db.session.add(chat)
        db.session.commit()
    
    messages_list = PrivateMessage.query.filter_by(chat_id=chat.id).order_by(PrivateMessage.created_at).all()
    
    return render_template('private_chat.html', chat=chat, other_user=other_user, messages=messages_list)

@app.route('/api/send_private', methods=['POST'])
@login_required
def send_private_message():
    data = request.json
    chat_id = data.get('chat_id')
    content = data.get('content')
    
    message = PrivateMessage(
        chat_id=chat_id,
        user_id=current_user.id,
        content=content
    )
    db.session.add(message)
    
    chat = PrivateChat.query.get(chat_id)
    chat.last_message = content[:100]
    chat.last_message_time = datetime.utcnow()
    
    db.session.commit()
    
    socketio.emit('new_private_message', {
        'id': message.id,
        'chat_id': chat_id,
        'content': content,
        'user_id': current_user.id,
        'username': current_user.username,
        'avatar': current_user.avatar,
        'timestamp': message.created_at.strftime('%H:%M')
    }, room=f'private_{chat_id}')
    
    return jsonify({'success': True, 'message': {
        'id': message.id,
        'content': content,
        'timestamp': message.created_at.strftime('%H:%M')
    }})

# ========== ГРУППОВЫЕ ЧАТЫ ==========

@app.route('/groups')
@login_required
def groups():
    my_groups = GroupMember.query.filter_by(user_id=current_user.id).all()
    groups_list = [gm.group for gm in my_groups]
    return render_template('groups.html', groups=groups_list)

@app.route('/groups/create', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        group = GroupChat(
            name=name,
            description=description,
            created_by=current_user.id
        )
        db.session.add(group)
        db.session.commit()
        
        member = GroupMember(group_id=group.id, user_id=current_user.id, role='admin')
        db.session.add(member)
        db.session.commit()
        
        flash('Группа создана!', 'success')
        return redirect(url_for('group_chat', group_id=group.id))
    
    return render_template('create_group.html')

@app.route('/groups/<int:group_id>')
@login_required
def group_chat(group_id):
    group = GroupChat.query.get_or_404(group_id)
    
    member = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    if not member:
        flash('Вы не состоите в этой группе', 'danger')
        return redirect(url_for('groups'))
    
    messages_list = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at).all()
    members_list = GroupMember.query.filter_by(group_id=group_id).all()
    
    return render_template('group_chat.html', group=group, messages=messages_list, members=members_list)

@app.route('/api/send_group', methods=['POST'])
@login_required
def send_group_message():
    data = request.json
    group_id = data.get('group_id')
    content = data.get('content')
    
    message = GroupMessage(
        group_id=group_id,
        user_id=current_user.id,
        content=content
    )
    db.session.add(message)
    db.session.commit()
    
    socketio.emit('new_group_message', {
        'id': message.id,
        'group_id': group_id,
        'content': content,
        'user_id': current_user.id,
        'username': current_user.username,
        'avatar': current_user.avatar,
        'timestamp': message.created_at.strftime('%H:%M')
    }, room=f'group_{group_id}')
    
    return jsonify({'success': True})

@app.route('/groups/<int:group_id>/invite', methods=['POST'])
@login_required
def invite_to_group(group_id):
    group = GroupChat.query.get_or_404(group_id)
    username = request.form.get('username')
    
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('group_chat', group_id=group_id))
    
    existing = GroupMember.query.filter_by(group_id=group_id, user_id=user.id).first()
    if existing:
        flash('Пользователь уже в группе', 'warning')
        return redirect(url_for('group_chat', group_id=group_id))
    
    member = GroupMember(group_id=group_id, user_id=user.id)
    db.session.add(member)
    db.session.commit()
    
    flash(f'{user.username} добавлен в группу!', 'success')
    return redirect(url_for('group_chat', group_id=group_id))

# ========== КАНАЛЫ ==========

@app.route('/channels')
@login_required
def channels():
    my_channels = Channel.query.filter_by(created_by=current_user.id).all()
    subscribed = ChannelSubscriber.query.filter_by(user_id=current_user.id).all()
    subscribed_channels = [sub.channel for sub in subscribed]
    
    recommended = Channel.query.filter(
        Channel.id.notin_([c.id for c in my_channels + subscribed_channels]),
        Channel.is_private == False
    ).limit(10).all()
    
    return render_template('channels.html', 
                         my_channels=my_channels, 
                         subscribed_channels=subscribed_channels,
                         recommended=recommended)

@app.route('/channels/create', methods=['GET', 'POST'])
@login_required
def create_channel():
    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        description = request.form.get('description')
        is_private = request.form.get('is_private') == 'on'
        
        if Channel.query.filter_by(username=username).first():
            flash('Такой @username уже занят', 'danger')
            return redirect(url_for('create_channel'))
        
        channel = Channel(
            name=name,
            username=username,
            description=description,
            is_private=is_private,
            created_by=current_user.id
        )
        db.session.add(channel)
        db.session.commit()
        
        subscriber = ChannelSubscriber(channel_id=channel.id, user_id=current_user.id, role='admin')
        db.session.add(subscriber)
        db.session.commit()
        
        flash('Канал создан!', 'success')
        return redirect(url_for('channel_view', channel_id=channel.id))
    
    return render_template('create_channel.html')

@app.route('/channels/<int:channel_id>')
@login_required
def channel_view(channel_id):
    channel = Channel.query.get_or_404(channel_id)
    
    is_subscribed = ChannelSubscriber.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()
    is_owner = channel.created_by == current_user.id
    
    if channel.is_private and not is_subscribed and not is_owner:
        flash('Это приватный канал', 'danger')
        return redirect(url_for('channels'))
    
    posts = ChannelPost.query.filter_by(channel_id=channel_id).order_by(ChannelPost.created_at.desc()).all()
    subscribers_count = ChannelSubscriber.query.filter_by(channel_id=channel_id).count()
    
    return render_template('channel_view.html', 
                         channel=channel, 
                         posts=posts, 
                         subscribers=subscribers_count,
                         is_subscribed=bool(is_subscribed),
                         is_owner=is_owner)

@app.route('/channels/<int:channel_id>/subscribe', methods=['POST'])
@login_required
def subscribe_channel(channel_id):
    channel = Channel.query.get_or_404(channel_id)
    
    existing = ChannelSubscriber.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        flash('Вы отписались от канала', 'info')
    else:
        subscriber = ChannelSubscriber(channel_id=channel_id, user_id=current_user.id)
        db.session.add(subscriber)
        flash('Вы подписались на канал!', 'success')
    
    db.session.commit()
    return redirect(url_for('channel_view', channel_id=channel_id))

@app.route('/channels/<int:channel_id>/post', methods=['POST'])
@login_required
def create_channel_post(channel_id):
    channel = Channel.query.get_or_404(channel_id)
    
    subscriber = ChannelSubscriber.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()
    if not subscriber or subscriber.role not in ['admin', 'moderator']:
        flash('У вас нет прав для публикации', 'danger')
        return redirect(url_for('channel_view', channel_id=channel_id))
    
    content = request.form.get('content')
    if not content:
        flash('Пост не может быть пустым', 'danger')
        return redirect(url_for('channel_view', channel_id=channel_id))
    
    post = ChannelPost(
        channel_id=channel_id,
        user_id=current_user.id,
        content=content
    )
    
    media = request.files.get('media')
    if media and allowed_file(media.filename):
        filename = secure_filename(f"channels/{channel_id}_{uuid.uuid4().hex}_{media.filename}")
        media.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        post.media_url = filename
    
    db.session.add(post)
    db.session.commit()
    
    flash('Пост опубликован!', 'success')
    return redirect(url_for('channel_view', channel_id=channel_id))

# ========== WEBSOCKET СОБЫТИЯ ==========

@socketio.on('send_message')
def handle_message(data):
    message = Message(
        content=data['message'],
        user_id=current_user.id,
        room=data.get('room', 'global')
    )
    db.session.add(message)
    db.session.commit()
    
    emit('new_message', {
        'id': message.id,
        'message': message.content,
        'username': current_user.username,
        'avatar': current_user.avatar,
        'timestamp': message.timestamp.strftime('%H:%M'),
        'user_id': current_user.id
    }, room=data.get('room', 'global'))

@socketio.on('join')
def handle_join(data):
    join_room(data['room'])
    emit('user_joined', {
        'username': current_user.username,
        'message': f'{current_user.username} присоединился к чату'
    }, room=data['room'])

@socketio.on('join_private')
def handle_join_private(data):
    join_room(f'private_{data["chat_id"]}')

@socketio.on('join_group')
def handle_join_group(data):
    join_room(f'group_{data["group_id"]}')

# ========== ЗАПУСК ==========

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Создаем дефолтную аватарку
        default_avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars/default.png')
        if not os.path.exists(default_avatar_path):
            os.makedirs(os.path.dirname(default_avatar_path), exist_ok=True)
            try:
                from PIL import Image, ImageDraw
                img = Image.new('RGB', (200, 200), color='#00A3FF')
                draw = ImageDraw.Draw(img)
                draw.text((100, 100), '🍵', fill='white', anchor='mm', font=None)
                img.save(default_avatar_path)
            except:
                pass
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)