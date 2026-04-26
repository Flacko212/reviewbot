from flask import Flask, request, jsonify, send_from_directory, redirect, session
from flask_cors import CORS
import requests
import os
import json
import urllib.parse

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'reviewbot-secret-key-2024')
CORS(app, supports_credentials=True)

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
APP_URL = os.environ.get('APP_URL', 'https://automatedreviewbot.co.uk')
REDIRECT_URI = f"{APP_URL}/oauth/callback"

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/oauth/callback')
def oauth_callback():
    code = request.args.get('code')
    if not code:
        return redirect('/?error=no_code')
    token_response = requests.post('https://oauth2.googleapis.com/token', data={
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    })
    tokens = token_response.json()
    if 'error' in tokens:
        return redirect(f'/?error={tokens["error"]}')
    access_token = tokens.get('access_token')
    refresh_token = tokens.get('refresh_token', '')
    accounts_response = requests.get(
        'https://mybusinessaccountmanagement.googleapis.com/v1/accounts',
        headers={'Authorization': f'Bearer {access_token}'}
    )
    accounts = accounts_response.json().get('accounts', [])
    session['g_access'] = access_token
    session['g_refresh'] = refresh_token
    session['g_accounts'] = json.dumps(accounts)
    return redirect('/google-success')

@app.route('/google-success')
def google_success():
    access_token = session.get('g_access', '')
    refresh_token = session.get('g_refresh', '')
    accounts = session.get('g_accounts', '[]')
    html = f"""<!DOCTYPE html>
<html><head><title>Connected</title></head><body>
<script>
  localStorage.setItem('g_access', {json.dumps(access_token)});
  localStorage.setItem('g_refresh', {json.dumps(refresh_token)});
  localStorage.setItem('g_accounts', {json.dumps(accounts)});
  localStorage.setItem('g_just_connected', 'true');
  window.location.href = '/';
</script>
<p>Connecting... please wait.</p>
</body></html>"""
    return html

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    api_key = data.get('apiKey', '').strip()
    prompt = data.get('prompt', '').strip()
    if not api_key:
        return jsonify({'error': 'Missing API key'}), 400
    if not prompt:
        return jsonify({'error': 'Missing prompt'}), 400
    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json'
        },
        json={
            'model': 'claude-opus-4-5',
            'max_tokens': 1000,
            'messages': [{'role': 'user', 'content': prompt}]
        }
    )
    return jsonify(response.json()), response.status_code

@app.route('/api/reviews', methods=['POST'])
def fetch_reviews():
    data = request.json
    access_token = data.get('access_token')
    location_name = data.get('location_name')
    if not access_token or not location_name:
        return jsonify({'error': 'Missing params'}), 400
    response = requests.get(
        f'https://mybusiness.googleapis.com/v4/{location_name}/reviews',
        headers={'Authorization': f'Bearer {access_token}'}
    )
    return jsonify(response.json()), response.status_code

@app.route('/api/post-reply', methods=['POST'])
def post_reply():
    data = request.json
    access_token = data.get('access_token')
    location_name = data.get('location_name')
    review_id = data.get('review_id')
    reply_text = data.get('reply_text')
    if not all([access_token, location_name, review_id, reply_text]):
        return jsonify({'error': 'Missing params'}), 400
    response = requests.put(
        f'https://mybusiness.googleapis.com/v4/{location_name}/reviews/{review_id}/reply',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        },
        json={'comment': reply_text}
    )
    return jsonify(response.json()), response.status_code

@app.route('/api/refresh-token', methods=['POST'])
def refresh_token():
    data = request.json
    refresh_tok = data.get('refresh_token')
    if not refresh_tok:
        return jsonify({'error': 'Missing refresh_token'}), 400
    response = requests.post('https://oauth2.googleapis.com/token', data={
        'refresh_token': refresh_tok,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'grant_type': 'refresh_token'
    })
    return jsonify(response.json()), response.status_code

@app.route('/api/google-auth-url', methods=['GET'])
def google_auth_url():
    state = request.args.get('state', '')
    url = (
        'https://accounts.google.com/o/oauth2/v2/auth'
        f'?client_id={GOOGLE_CLIENT_ID}'
        f'&redirect_uri={REDIRECT_URI}'
        '&response_type=code'
        '&scope=https://www.googleapis.com/auth/business.manage'
        '&access_type=offline'
        '&prompt=consent'
        f'&state={state}'
    )
    return jsonify({'url': url})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  ReviewBot running on port {port}\n")
    app.run(debug=False, host='0.0.0.0', port=port)
