from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from backend.database import get_db_connection

def authenticate_user(username, password):
    """Verify user credentials and return user dict if valid, else None."""
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    if user and check_password_hash(user['password_hash'], password):
        return {
            "id": user['id'],
            "username": user['username'],
            "role": user['role'],
            "full_name": user['full_name']
        }
    return None

def login_user_session(user_dict):
    session.clear()
    session['user_id'] = user_dict['id']
    session['username'] = user_dict['username']
    session['role'] = user_dict['role']
    session['full_name'] = user_dict['full_name']
    session.permanent = True

def logout_user_session():
    session.clear()

def get_current_user():
    if 'user_id' in session:
        return {
            "id": session.get('user_id'),
            "username": session.get('username'),
            "role": session.get('role'),
            "full_name": session.get('full_name')
        }
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized", "message": "Login required"}), 401
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized", "message": "Login required"}), 401
            return redirect(url_for('login_page', next=request.url))
        if session.get('role') != 'admin':
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"error": "Forbidden", "message": "Admin privileges required"}), 403
            return redirect(url_for('dashboard_page'))
        return f(*args, **kwargs)
    return decorated_function
