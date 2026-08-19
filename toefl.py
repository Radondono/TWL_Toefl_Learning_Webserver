#!/usr/bin/env python3
"""
TOEFL Vocabulary Quiz Server with Admin Messaging System
- Admin can broadcast or send private messages
- Users have an inbox with unread count
"""

import os
import random
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

app = Flask(__name__)
app.secret_key = os.urandom(24)
PORT = 3000
DB_PATH = 'toefl.db'
CSV_PATH = 'toefl_words.csv'

# ─── G7 intervals ───
REVIEW_INTERVALS = [1, 2, 4, 7, 14, 30, 60]
MAX_LEVEL = len(REVIEW_INTERVALS) - 1

# ─── Database schema ───
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            banned BOOLEAN DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL,
            definition TEXT NOT NULL,
            pos TEXT,
            difficulty INTEGER,
            theme TEXT,
            synonyms TEXT,
            example_sentence TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            attempts INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0,
            mastered BOOLEAN DEFAULT 0,
            difficult BOOLEAN DEFAULT 0,
            review_level INTEGER DEFAULT 0,
            next_review TIMESTAMP,
            last_reviewed TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (word_id) REFERENCES vocabulary (id),
            UNIQUE(user_id, word_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read BOOLEAN DEFAULT 0,
            FOREIGN KEY (sender_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()
    migrate_db()

def migrate_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Users: banned
    c.execute("PRAGMA table_info(users)")
    user_cols = [col[1] for col in c.fetchall()]
    if 'banned' not in user_cols:
        c.execute("ALTER TABLE users ADD COLUMN banned BOOLEAN DEFAULT 0")
        conn.commit()
    # Progress: SRS columns
    c.execute("PRAGMA table_info(progress)")
    prog_cols = [col[1] for col in c.fetchall()]
    for col in ['review_level', 'next_review', 'last_reviewed']:
        if col not in prog_cols:
            c.execute(f"ALTER TABLE progress ADD COLUMN {col} {('INTEGER' if col=='review_level' else 'TIMESTAMP')}")
            conn.commit()
    if 'review_level' not in prog_cols:
        c.execute("UPDATE progress SET review_level = 0 WHERE review_level IS NULL")
    if 'next_review' not in prog_cols:
        c.execute("UPDATE progress SET next_review = CURRENT_TIMESTAMP WHERE next_review IS NULL")
    # Messages table is created above, no migration needed.
    conn.commit()
    conn.close()
    print("✅ Database migration complete.")

def create_admin_if_missing():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    if not c.fetchone():
        hashed = generate_password_hash('admin')
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                  ('admin', hashed, 'admin'))
        conn.commit()
    conn.close()

def load_vocabulary_from_csv():
    if not os.path.exists(CSV_PATH):
        print(f"⚠️ {CSV_PATH} not found. Run build_vocab.py first.")
        return
    df = pd.read_csv(CSV_PATH)
    required = ['word', 'definition_en']
    if not all(col in df.columns for col in required):
        print("❌ CSV missing required columns: word, definition_en")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for _, row in df.iterrows():
        word = str(row['word']).strip()
        definition = str(row['definition_en']).strip()
        pos = str(row.get('pos', '')).strip()
        difficulty = int(row.get('difficulty', 3)) if pd.notna(row.get('difficulty')) else 3
        theme = str(row.get('theme', '')).strip()
        synonyms = str(row.get('synonyms', '')).strip()
        example = str(row.get('example_sentence', '')).strip()
        if word and definition:
            try:
                c.execute('''
                    INSERT INTO vocabulary (word, definition, pos, difficulty, theme, synonyms, example_sentence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (word, definition, pos, difficulty, theme, synonyms, example))
            except sqlite3.IntegrityError:
                c.execute('''
                    UPDATE vocabulary SET definition=?, pos=?, difficulty=?, theme=?, synonyms=?, example_sentence=?
                    WHERE word=?
                ''', (definition, pos, difficulty, theme, synonyms, example, word))
    conn.commit()
    conn.close()
    print(f"✅ Loaded vocabulary from {CSV_PATH}")

# ─── Init ───
init_db()
create_admin_if_missing()
load_vocabulary_from_csv()

# ─── Helpers ───
def get_all_words():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, word, definition, pos, difficulty, theme, synonyms, example_sentence
        FROM vocabulary ORDER BY word
    ''')
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'word': r[1], 'definition': r[2], 'pos': r[3],
             'difficulty': r[4], 'theme': r[5], 'synonyms': r[6], 'example': r[7]} for r in rows]

def get_user_by_username(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, password_hash, role, banned FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'id': row[0], 'username': row[1], 'password_hash': row[2], 'role': row[3], 'banned': bool(row[4])}
    return None

def get_user_progress(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT word_id, attempts, correct, mastered, difficult,
               review_level, next_review, last_reviewed
        FROM progress WHERE user_id = ?
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    progress = {}
    for wid, att, cor, mas, diff, rl, nr, lr in rows:
        progress[wid] = {
            'attempts': att,
            'correct': cor,
            'mastered': bool(mas),
            'difficult': bool(diff),
            'review_level': rl or 0,
            'next_review': nr,
            'last_reviewed': lr
        }
    return progress

def get_quiz_words(user_id, num_questions=10, difficulty_filter=None, theme_filter=None, mode='all'):
    all_words = get_all_words()
    if difficulty_filter:
        all_words = [w for w in all_words if w['difficulty'] in difficulty_filter]
    if theme_filter:
        all_words = [w for w in all_words if w['theme'] in theme_filter]
    if len(all_words) == 0:
        return []
    progress = get_user_progress(user_id)

    if mode == 'review':
        due_words = []
        now = datetime.now()
        for w in all_words:
            p = progress.get(w['id'], {'next_review': datetime.now()})
            next_review = p.get('next_review')
            if next_review is None:
                continue
            if isinstance(next_review, str):
                next_review = datetime.fromisoformat(next_review)
            if next_review <= now:
                due_words.append(w)
        if not due_words:
            return []
        random.shuffle(due_words)
        return due_words[:min(num_questions, len(due_words))]

    elif mode == 'mastered':
        mastered_words = []
        for w in all_words:
            p = progress.get(w['id'], {'mastered': False})
            if p['mastered']:
                mastered_words.append(w)
        if not mastered_words:
            return []
        return random.sample(mastered_words, min(num_questions, len(mastered_words)))

    elif mode == 'learning':
        learning_words = []
        for w in all_words:
            p = progress.get(w['id'], {'attempts': 0, 'mastered': False})
            if p['attempts'] > 0 and not p['mastered']:
                learning_words.append(w)
        if not learning_words:
            return []
        random.shuffle(learning_words)
        return learning_words[:min(num_questions, len(learning_words))]

    elif mode == 'difficult':
        difficult_words = []
        for w in all_words:
            p = progress.get(w['id'], {'difficult': False})
            if p['difficult']:
                difficult_words.append(w)
        if not difficult_words:
            return []
        random.shuffle(difficult_words)
        return difficult_words[:min(num_questions, len(difficult_words))]

    else:  # 'all'
        difficult_not_mastered = []
        difficult_mastered = []
        not_mastered = []
        mastered = []
        for w in all_words:
            wid = w['id']
            p = progress.get(wid, {'attempts': 0, 'correct': 0, 'mastered': False, 'difficult': False})
            if p['difficult']:
                if p['mastered']:
                    difficult_mastered.append(w)
                else:
                    difficult_not_mastered.append(w)
            else:
                if p['mastered']:
                    mastered.append(w)
                else:
                    not_mastered.append(w)
        prioritized = []
        random.shuffle(difficult_not_mastered)
        prioritized.extend(difficult_not_mastered)
        random.shuffle(difficult_mastered)
        prioritized.extend(difficult_mastered)
        random.shuffle(not_mastered)
        prioritized.extend(not_mastered)
        random.shuffle(mastered)
        prioritized.extend(mastered)
        if len(prioritized) < num_questions:
            return random.sample(all_words, min(num_questions, len(all_words)))
        return prioritized[:num_questions]

def update_progress(user_id, word, correct):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM vocabulary WHERE word = ?", (word,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    word_id = row[0]
    c.execute('''
        SELECT attempts, correct, mastered, difficult, review_level, next_review, last_reviewed
        FROM progress WHERE user_id = ? AND word_id = ?
    ''', (user_id, word_id))
    row = c.fetchone()
    now = datetime.now()
    if row:
        attempts, correct_so_far, mastered_flag, difficult, rl, next_rev, last_rev = row
        attempts += 1
        if correct:
            correct_so_far += 1
        mastered = 1 if (attempts >= 5 and correct_so_far / attempts >= 0.8) else 0
        if correct:
            new_level = min(rl + 1, MAX_LEVEL)
            interval_days = REVIEW_INTERVALS[new_level]
            next_review = now + timedelta(days=interval_days)
            last_reviewed = now
        else:
            new_level = 0
            interval_days = REVIEW_INTERVALS[0]
            next_review = now + timedelta(days=interval_days)
            last_reviewed = now
        c.execute('''
            UPDATE progress
            SET attempts = ?, correct = ?, mastered = ?,
                review_level = ?, next_review = ?, last_reviewed = ?
            WHERE user_id = ? AND word_id = ?
        ''', (attempts, correct_so_far, mastered, new_level, next_review, last_reviewed, user_id, word_id))
    else:
        attempts = 1
        correct_so_far = 1 if correct else 0
        mastered = 0
        if correct:
            new_level = 1
            interval_days = REVIEW_INTERVALS[new_level]
            next_review = now + timedelta(days=interval_days)
            last_reviewed = now
        else:
            new_level = 0
            interval_days = REVIEW_INTERVALS[0]
            next_review = now + timedelta(days=interval_days)
            last_reviewed = now
        c.execute('''
            INSERT INTO progress (user_id, word_id, attempts, correct, mastered, difficult,
                                  review_level, next_review, last_reviewed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, word_id, attempts, correct_so_far, mastered, 0,
              new_level, next_review, last_reviewed))
    conn.commit()
    conn.close()

def toggle_difficult(user_id, word):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM vocabulary WHERE word = ?", (word,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    word_id = row[0]
    c.execute("SELECT difficult FROM progress WHERE user_id = ? AND word_id = ?", (user_id, word_id))
    row = c.fetchone()
    if row:
        new_val = 0 if row[0] else 1
        c.execute("UPDATE progress SET difficult = ? WHERE user_id = ? AND word_id = ?",
                  (new_val, user_id, word_id))
    else:
        new_val = 1
        c.execute('''
            INSERT INTO progress (user_id, word_id, attempts, correct, mastered, difficult,
                                  review_level, next_review, last_reviewed)
            VALUES (?, ?, 0, 0, 0, ?, 0, CURRENT_TIMESTAMP, NULL)
        ''', (user_id, word_id, new_val))
    conn.commit()
    conn.close()
    return True

# ─── Message functions ───
def send_message(sender_id, receiver_id, subject, body):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (sender_id, receiver_id, subject, body)
        VALUES (?, ?, ?, ?)
    ''', (sender_id, receiver_id, subject, body))
    conn.commit()
    conn.close()

def get_user_messages(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, sender_id, receiver_id, subject, body, created_at, read
        FROM messages
        WHERE receiver_id = ? OR receiver_id IS NULL
        ORDER BY created_at DESC
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    messages = []
    for row in rows:
        messages.append({
            'id': row[0],
            'sender_id': row[1],
            'receiver_id': row[2],
            'subject': row[3],
            'body': row[4],
            'created_at': row[5],
            'read': bool(row[6])
        })
    return messages

def get_message(message_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, sender_id, receiver_id, subject, body, created_at, read
        FROM messages
        WHERE id = ? AND (receiver_id = ? OR receiver_id IS NULL)
    ''', (message_id, user_id))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'id': row[0],
            'sender_id': row[1],
            'receiver_id': row[2],
            'subject': row[3],
            'body': row[4],
            'created_at': row[5],
            'read': bool(row[6])
        }
    return None

def mark_message_read(message_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE messages SET read = 1
        WHERE id = ? AND (receiver_id = ? OR receiver_id IS NULL)
    ''', (message_id, user_id))
    conn.commit()
    conn.close()

def get_unread_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM messages
        WHERE (receiver_id = ? OR receiver_id IS NULL) AND read = 0
    ''', (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_all_users_except(admin_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE id != ? ORDER BY username", (admin_id,))
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'username': r[1]} for r in rows]

# ─── Routes ───
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user_by_username(username)
        if user and not user['banned'] and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        elif user and user['banned']:
            return render_template('login.html', error='Your account has been banned.')
        else:
            return render_template('login.html', error='Invalid username or password')
    return render_template('login.html', error=None)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            return render_template('register.html', error='Username and password required')
        if get_user_by_username(username):
            return render_template('register.html', error='Username already taken')
        hashed = generate_password_hash(password)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
            conn.commit()
        except sqlite3.IntegrityError:
            return render_template('register.html', error='Username already exists')
        finally:
            conn.close()
        return redirect(url_for('login'))
    return render_template('register.html', error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    unread = get_unread_count(user_id)
    words = get_all_words()
    progress = get_user_progress(user_id)
    word_list = []
    mastered_count = in_progress_count = not_started_count = difficult_count = 0
    due_count = 0
    now = datetime.now()
    for w in words:
        p = progress.get(w['id'], {'attempts': 0, 'correct': 0, 'mastered': False,
                                   'difficult': False, 'next_review': now})
        status = 'not_started'
        if p['mastered']:
            status = 'mastered'
            mastered_count += 1
        elif p['attempts'] > 0:
            status = 'learning'
            in_progress_count += 1
        else:
            not_started_count += 1
        if p['difficult']:
            difficult_count += 1
        if p['attempts'] > 0:
            next_review = p['next_review']
            if isinstance(next_review, str):
                next_review = datetime.fromisoformat(next_review)
            if next_review <= now:
                due_count += 1
        word_list.append({
            'id': w['id'],
            'word': w['word'],
            'definition': w['definition'],
            'pos': w['pos'],
            'difficulty': w['difficulty'],
            'theme': w['theme'],
            'synonyms': w['synonyms'],
            'example': w['example'],
            'status': status,
            'difficult': p['difficult'],
            'attempts': p['attempts'],
            'correct': p['correct'],
            'next_review': p['next_review']
        })
    seen_words = [w for w in word_list if w['attempts'] > 0]
    total_words = len(words)
    return render_template('dashboard.html',
                           username=session['username'],
                           role=session['role'],
                           total_words=total_words,
                           mastered_count=mastered_count,
                           in_progress_count=in_progress_count,
                           not_started_count=not_started_count,
                           difficult_count=difficult_count,
                           due_count=due_count,
                           unread=unread,
                           words=seen_words)

@app.route('/inbox')
def inbox():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    messages = get_user_messages(user_id)
    return render_template('inbox.html', messages=messages, username=session['username'])

@app.route('/inbox/<int:message_id>')
def view_message(message_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    msg = get_message(message_id, user_id)
    if not msg:
        return "Message not found or unauthorized.", 404
    if not msg['read']:
        mark_message_read(message_id, user_id)
    return render_template('message_detail.html', msg=msg, username=session['username'])

@app.route('/api/unread', methods=['GET'])
def api_unread():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    count = get_unread_count(session['user_id'])
    return jsonify({'unread': count})

@app.route('/quiz')
def quiz():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('quiz.html', username=session['username'])

@app.route('/admin')
def admin():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT u.id, u.username, u.role, u.banned,
               COUNT(p.word_id) as words_tried,
               SUM(p.attempts) as total_attempts,
               SUM(p.correct) as total_correct,
               COUNT(CASE WHEN p.mastered = 1 THEN 1 END) as mastered_count,
               COUNT(CASE WHEN p.difficult = 1 THEN 1 END) as difficult_count
        FROM users u
        LEFT JOIN progress p ON u.id = p.user_id
        GROUP BY u.id
        ORDER BY u.username
    ''')
    users = c.fetchall()
    conn.close()
    return render_template('admin.html', users=users, admin_id=session['user_id'])

@app.route('/admin/messages', methods=['GET', 'POST'])
def admin_messages():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        receiver_id = request.form.get('receiver_id')
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()
        if not subject or not body:
            return render_template('admin_messages.html', error='Subject and body required.', users=get_all_users_except(session['user_id']))
        if receiver_id == 'all':
            receiver_id = None  # broadcast
        else:
            try:
                receiver_id = int(receiver_id)
            except ValueError:
                return render_template('admin_messages.html', error='Invalid user selection.', users=get_all_users_except(session['user_id']))
        send_message(session['user_id'], receiver_id, subject, body)
        return redirect(url_for('admin_messages', sent=1))
    users = get_all_users_except(session['user_id'])
    sent = request.args.get('sent')
    return render_template('admin_messages.html', users=users, sent=sent)

@app.route('/admin/ban/<int:user_id>', methods=['POST'])
def admin_ban(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    if user_id == session['user_id']:
        return jsonify({'error': 'Cannot ban yourself'}), 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT banned FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    new_val = 0 if row[0] else 1
    c.execute("UPDATE users SET banned = ? WHERE id = ?", (new_val, user_id))
    conn.commit()
    conn.close()
    return jsonify({'message': f'User {"banned" if new_val else "unbanned"}'})

@app.route('/admin/delete_progress/<int:user_id>', methods=['POST'])
def admin_delete_progress(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    if user_id == session['user_id']:
        return jsonify({'error': 'Cannot delete your own progress'}), 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM progress WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Progress deleted'})

@app.route('/admin/change_password/<int:user_id>', methods=['POST'])
def admin_change_password(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    new_password = request.form.get('new_password')
    if not new_password or len(new_password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    hashed = generate_password_hash(new_password)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, user_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Password updated'})

@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    new_hash = generate_password_hash('password123')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Password reset to "password123"'})

@app.route('/api/themes', methods=['GET'])
def api_themes():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT theme FROM vocabulary WHERE theme IS NOT NULL AND theme != '' ORDER BY theme")
    rows = c.fetchall()
    conn.close()
    themes = [r[0] for r in rows]
    return jsonify(themes)

@app.route('/api/quiz', methods=['GET'])
def api_quiz():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    user_id = session['user_id']
    num = int(request.args.get('num', 10))
    mode = request.args.get('mode', 'all')
    diff_str = request.args.get('difficulty', '')
    difficulty_filter = None
    if diff_str:
        difficulty_filter = [int(x.strip()) for x in diff_str.split(',') if x.strip().isdigit()]
    theme_str = request.args.get('theme', '')
    theme_filter = None
    if theme_str:
        theme_filter = [x.strip() for x in theme_str.split(',') if x.strip()]
    selected = get_quiz_words(user_id, num, difficulty_filter, theme_filter, mode)
    if not selected:
        return jsonify([])
    all_words = get_all_words()
    questions = []
    for item in selected:
        word = item['word']
        correct_def = item['definition']
        pos = item.get('pos', '')
        difficulty = item.get('difficulty', 3)
        others = [w for w in all_words if w['word'] != word]
        wrong_defs = [w['definition'] for w in random.sample(others, min(3, len(others)))]
        while len(wrong_defs) < 3:
            wrong_defs.append("(definition not available)")
        options = [{'text': correct_def, 'correct': True}] + [{'text': d, 'correct': False} for d in wrong_defs[:3]]
        random.shuffle(options)
        questions.append({
            'word': word,
            'definition': correct_def,
            'pos': pos,
            'difficulty': difficulty,
            'theme': item.get('theme', ''),
            'synonyms': item.get('synonyms', ''),
            'example': item.get('example', ''),
            'options': options
        })
    return jsonify(questions)

@app.route('/api/progress', methods=['POST'])
def api_progress():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    word = data.get('word')
    correct = data.get('correct')
    if not word or correct is None:
        return jsonify({'error': 'Missing data'}), 400
    update_progress(session['user_id'], word, correct)
    return jsonify({'message': 'Progress updated'})

@app.route('/api/toggle_difficult', methods=['POST'])
def api_toggle_difficult():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    word = data.get('word')
    if not word:
        return jsonify({'error': 'Missing word'}), 400
    success = toggle_difficult(session['user_id'], word)
    if success:
        return jsonify({'message': 'Toggled difficulty'})
    else:
        return jsonify({'error': 'Word not found'}), 404

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=True)