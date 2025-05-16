from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, auth, firestore
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import json
import random
import os
from functools import wraps
from datetime import datetime, timedelta
import uuid
import logging

# Initialize Flask app with correct paths
app = Flask(__name__,
            template_folder='templates',  # Relative to current directory
            static_folder='static')      # Relative to current directory

CORS(app)
app.secret_key = os.urandom(24)

# Debugging endpoints
@app.route('/debug')
def debug():
    return f"""
    Current directory: {os.getcwd()}<br>
    Templates folder: {app.template_folder} (exists: {os.path.exists(app.template_folder)})<br>
    Static folder: {app.static_folder} (exists: {os.path.exists(app.static_folder)})<br>
    Static files:<br>
    - CSS: {os.path.join(app.static_folder, 'css/login.css')} (exists: {os.path.exists(os.path.join(app.static_folder, 'css/login.css'))})<br>
    - Image: {os.path.join(app.static_folder, 'images/circles-1743740021542.png')} (exists: {os.path.exists(os.path.join(app.static_folder, 'images/circles-1743740021542.png'))})
    """

# Serve static files explicitly
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

# Initialize Firebase
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate('reconest-42f2a-firebase-adminsdk-fbsvc-8418e65522.json')
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    logging.error(f"Firebase initialization failed: {str(e)}")

def load_media_data():
    try:
        with open('media_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Validate data structure
            if not isinstance(data, dict) or 'movie' not in data or 'book' not in data:
                raise ValueError("Invalid data structure")
            return data
    except Exception as e:
        logging.error(f"Failed to load media data: {str(e)}")
        return {'movie': [], 'book': []}

media_data = load_media_data()

class RecommendationEngine:
    def __init__(self, data):
        self.data = data
        self.tfidf = TfidfVectorizer(
            stop_words='english',
            min_df=1,
            max_features=1000,
            ngram_range=(1, 2),
            token_pattern=r'(?u)\b\w+\b'
        )
        self.prepare_model()
    
    def prepare_model(self):
        try:
            for media_type in ['movie', 'book']:
                for item in self.data[media_type]:
                    item['combined_features'] = ' '.join(
                        item['genre'] + 
                        item['moods'] + 
                        item['tags'] + 
                        [item['language']] +
                        [str(item.get('rating', 3)) + ' star']
                    )
            
            all_items = self.data['movie'] + self.data['book']
            self.tfidf_matrix = self.tfidf.fit_transform(
                [item['combined_features'] for item in all_items]
            )
            self.item_indices = {item['id']: idx for idx, item in enumerate(all_items)}
        except Exception as e:
            logging.error(f"Model preparation failed: {str(e)}")

    def recommend(self, media_type, liked_ids=[], mood=None, tags=[], limit=10):
        try:
            items = self.data.get(media_type, [])
            filtered_items = [
                item for item in items
                if (not mood or mood.lower() in [m.lower() for m in item['moods']]) and 
                (not tags or any(tag.lower() in [t.lower() for t in item['tags']] for tag in tags))
            ]
            
            if not liked_ids:
                return filtered_items if filtered_items else random.sample(items, min(limit, len(items)))
            
            liked_indices = [self.item_indices[id] for id in liked_ids if id in self.item_indices]
            if not liked_indices:
                return filtered_items[:limit] if filtered_items else random.sample(items, min(limit, len(items)))
            
            avg_vector = np.mean(self.tfidf_matrix[liked_indices].toarray(), axis=0)
            similarities = cosine_similarity([avg_vector], self.tfidf_matrix).flatten()
            
            recommendations = []
            for idx in similarities.argsort()[::-1]:
                item = (self.data['movie'] + self.data['book'])[idx]
                if item['id'] not in liked_ids and item in filtered_items:
                    recommendations.append(item)
                    if len(recommendations) >= limit:
                        break
            
            return recommendations if recommendations else random.sample(items, min(limit, len(items)))
        except Exception as e:
            logging.error(f"Recommendation failed: {str(e)}")
            return random.sample(self.data.get(media_type, []), min(limit, len(self.data.get(media_type, []))))

recommendation_engine = RecommendationEngine(media_data)

def firebase_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            auth.get_user(session['user']['uid'])
            return f(*args, **kwargs)
        except Exception as e:
            logging.error(f"Authentication failed: {str(e)}")
            return jsonify({'error': 'Invalid session'}), 401
    return decorated_function

@app.route('/')
def index():
    try:
        return render_template('login.html')
    except Exception as e:
        logging.error(f"Failed to render login: {str(e)}")
        return "Error loading page", 500

@app.route('/home')
@firebase_auth_required
def home():
    if not session.get('user', {}).get('preferences_set', False):
        return redirect(url_for('choose'))  # Force to choose first
    return render_template('home.html')

@app.route('/choose')
@firebase_auth_required
def choose():
    if session.get('user', {}).get('preferences_set', True):
        return redirect(url_for('home'))  # Skip if already set preferences
    return render_template('choose.html')

@app.route('/saved')
@firebase_auth_required
def saved():
    if not session.get('user', {}).get('preferences_set', False):
        return redirect(url_for('choose'))
    return render_template('saved.html')

@app.route('/api/auth/google', methods=['POST'])
def google_auth():
    try:
        id_token = request.json.get('id_token')
        decoded_token = auth.verify_id_token(id_token)
        session['user'] = {
            'uid': decoded_token['uid'],
            'email': decoded_token['email'],
            'name': decoded_token.get('name', ''),
            'picture': decoded_token.get('picture', '')
         
        }
        return jsonify({
            'success': True, 
            'user': session['user'],
            'next_page': '/choose'  # Always go to choose page first
        })
    except Exception as e:
        logging.error(f"Google auth failed: {str(e)}")
        return jsonify({'error': str(e)}), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/api/recommendations/<media_type>')
@firebase_auth_required
def get_recommendations(media_type):
    try:
        user_id = session['user']['uid']
        preferences = get_user_preferences(user_id)
        mood = request.args.get('mood')
        tags = request.args.getlist('tags[]')
        limit = int(request.args.get('limit', 10))
        liked_ids = preferences.get(f'liked_{media_type}s', [])
        
        recommendations = recommendation_engine.recommend(
            media_type, liked_ids, mood, tags, limit
        )
        
        return jsonify({
            'recommendations': recommendations,
            'popular_tags': get_popular_tags(media_type)
        })
    except Exception as e:
        logging.error(f"Recommendation API failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

def get_user_preferences(user_id):
    try:
        doc_ref = db.collection('user_preferences').document(user_id)
        doc = doc_ref.get()
        return doc.to_dict() or {'liked_movies': [], 'liked_books': []}
    except Exception as e:
        logging.error(f"Failed to get user preferences: {str(e)}")
        return {'liked_movies': [], 'liked_books': []}

def get_popular_tags(media_type):
    try:
        tags = {}
        for item in media_data[media_type]:
            for tag in item['tags']:
                tags[tag] = tags.get(tag, 0) + 1
        return sorted(tags.keys(), key=lambda x: tags[x], reverse=True)[:15]
    except Exception as e:
        logging.error(f"Failed to get popular tags: {str(e)}")
        return []

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)