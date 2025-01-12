from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask import send_from_directory
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') 

# Configuration
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'  # Local SQLite database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())


# Routes

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    videos = Video.query.filter(Video.uploaded_by != user_id).all()  # Exclude user's own videos

    # Fetch likes and comments for each video
    video_data = []
    for video in videos:
        likes_count = Like.query.filter_by(video_id=video.id).count()
        comments = Comment.query.filter_by(video_id=video.id).all()
        comments_data = [{'user': User.query.get(c.user_id).username, 'content': c.content, 'timestamp': c.timestamp}
                         for c in comments]
        video_data.append({
            'id': video.id,
            'filename': video.filename,
            'uploaded_by': video.uploaded_by,
            'likes_count': likes_count,
            'comments': comments_data
        })

    return render_template('index.html', videos=video_data)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='sha256')
        user = User(username=username, password=hashed_password)
        try:
            db.session.add(user)
            db.session.commit()
            flash('Signup successful! Please login.', 'success')
            return redirect(url_for('login'))
        except:
            flash('Username already exists!', 'danger')
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('index'))  # Changed to redirect to the index page
        else:
            flash('Invalid credentials!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    username = session['username']
    videos = Video.query.filter_by(uploaded_by=user_id).all()  # Fetch all videos by the user
    return render_template('profile.html', username=username, videos=videos)

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized. Please log in.'}), 401

    user_id = session['user_id']
    file = request.files.get('file')
    if not file:
        return jsonify({'message': 'No file provided.'}), 400

    filename = file.filename
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        # Save the file
        file.save(filepath)

        # Save file info to the database
        video = Video(filename=filename, uploaded_by=user_id)
        db.session.add(video)
        db.session.commit()

        return jsonify({'message': 'Video uploaded successfully!'})
    except Exception as e:
        return jsonify({'message': f'Error uploading video: {str(e)}'}), 500

@app.route('/like', methods=['POST'])
def like_video():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    user_id = session['user_id']
    video_id = data.get('video_id')

    if not video_id:
        return jsonify({'error': 'Missing video_id'}), 400

    existing_like = Like.query.filter_by(user_id=user_id, video_id=video_id).first()
    if existing_like:
        return jsonify({'message': 'Already liked!'})

    like = Like(user_id=user_id, video_id=video_id)
    db.session.add(like)
    db.session.commit()

    # Notify uploader
    video = Video.query.get(video_id)
    uploader = User.query.get(video.uploaded_by)
    print(f"Notification: {uploader.username}, your video received a like!")

    likes_count = Like.query.filter_by(video_id=video_id).count()
    return jsonify({'message': 'Video liked successfully!', 'likes_count': likes_count})

@app.route('/comment', methods=['POST'])
def comment_video():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    user_id = session['user_id']
    video_id = data.get('video_id')
    content = data.get('content')

    if not video_id or not content:
        return jsonify({'error': 'Missing video_id or content'}), 400

    comment = Comment(content=content, video_id=video_id, user_id=user_id)
    db.session.add(comment)
    db.session.commit()

    # Notify uploader
    video = Video.query.get(video_id)
    uploader = User.query.get(video.uploaded_by)
    print(f"Notification: {uploader.username}, your video received a new comment: '{content}'")

    # Prepare the new comment data
    comment_data = {
        'user': User.query.get(user_id).username,
        'content': content,
        'timestamp': comment.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }
    return jsonify({'message': 'Comment added successfully!', 'comment': comment_data})

@app.route('/video_details/<int:video_id>', methods=['GET'])
def video_details(video_id):
    video = Video.query.get(video_id)
    likes_count = Like.query.filter_by(video_id=video_id).count()
    comments = Comment.query.filter_by(video_id=video_id).all()
    comments_data = [{'user': User.query.get(c.user_id).username, 'content': c.content, 'timestamp': c.timestamp}
                     for c in comments]

    return jsonify({'likes': likes_count, 'comments': comments_data})

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        # Handle search via form submission
        username = request.form.get('username', '').strip()
    else:
        # Handle search via query parameter
        username = request.args.get('query', '').strip()

    if not username:
        flash('Please enter a username to search!', 'warning')
        return redirect(url_for('index'))
    
    # Case-insensitive search
    user = User.query.filter(User.username.ilike(f'%{username}%')).first()
    if not user:
        flash('No user found with that username.', 'danger')
        return redirect(url_for('index'))
    
    # Fetch videos uploaded by the searched user
    videos = Video.query.filter_by(uploaded_by=user.id).all()
    
    # Fetch likes and comments for each video
    video_data = []
    for video in videos:
        likes_count = Like.query.filter_by(video_id=video.id).count()
        comments = Comment.query.filter_by(video_id=video.id).all()
        comments_data = [{'user': User.query.get(c.user_id).username, 'content': c.content, 'timestamp': c.timestamp}
                         for c in comments]
        video_data.append({
            'id': video.id,
            'filename': video.filename,
            'uploaded_by': user.username,
            'likes_count': likes_count,
            'comments': comments_data
        })
    
    # Render results
    return render_template('search_results.html', results=video_data, search_query=username)




if __name__ == '__main__':
    db.create_all()
    app.run(debug=False)
