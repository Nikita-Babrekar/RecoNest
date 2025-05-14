from flask import Flask, render_template, request, redirect, url_for, session, jsonify
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

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)
app.secret_key = os.urandom(24)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Firebase
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate('serviceAccountKey.json')
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    logging.error(f"Firebase initialization failed: {str(e)}")

def load_media_data():
    try:
        with open('data/media_data.json') as f:
            data = json.load(f)
        
        # Add IDs if not present
        for media_type in ['movie', 'book']:
            for item in data[media_type]:
                if 'id' not in item:
                    item['id'] = str(uuid.uuid4())
        return data
    except Exception as e:
        logging.error(f"Failed to load media data: {str(e)}")
        return {'movie': [], 'book': []}

media_data = load_media_data()

class RecommendationEngine:
    def __init__(self, data):
        self.data = data
        self.tfidf = TfidfVectorizer(stop_words='english')
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
        return random.sample(self.data.get(media_type, []), min(limit, len(self.data.get(media_type, [])))
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
    return render_template('home.html')

@app.route('/choose')
@firebase_auth_required
def choose():
    return render_template('choose.html')

@app.route('/saved')
@firebase_auth_required
def saved():
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
        return jsonify({'success': True, 'user': session['user']})
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
    app.run(host='0.0.0.0', port=5000, debug=True)