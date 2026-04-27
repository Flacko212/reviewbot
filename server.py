import os
import json
import urllib.parse
import httpx
from flask import Flask, request, jsonify, send_from_directory
from anthropic import Anthropic

app = Flask(__name__, static_folder='static')

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
APP_URL = os.environ.get('APP_URL', 'https://automatedreviewbot.co.uk')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
FROM_EMAIL = 'reviews@automatedreviewbot.co.uk'

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    try:
        return send_from_directory('static', path)
    except Exception:
        return send_from_directory('static', 'index.html')

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json() or {}
        prompt = data.get('prompt', '').strip()
        client_key = data.get('apiKey', '').strip()
        if not prompt:
            return jsonify({'error': 'No prompt provided'}), 400
        api_key = ANTHROPIC_API_KEY or client_key
        if not api_key:
            return jsonify({'error': 'No Anthropic API key configured. Add ANTHROPIC_API_KEY in Railway environment variables.'}), 400
        c = Anthropic(api_key=api_key)
        message = c.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=300,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return jsonify({'content': [{'type': 'text', 'text': message.content[0].text}]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/has-server-key', methods=['GET'])
def has_server_key():
    return jsonify({'has_key': bool(ANTHROPIC_API_KEY)})

@app.route('/api/google-auth-url', methods=['GET'])
def google_auth_url():
    redirect_uri = APP_URL + '/oauth/callback'
    scope = 'https://www.googleapis.com/auth/business.manage https://www.googleapis.com/auth/userinfo.email'
    url = (
        'https://accounts.google.com/o/oauth2/v2/auth'
        '?client_id=' + urllib.parse.quote(GOOGLE_CLIENT_ID) +
        '&redirect_uri=' + urllib.parse.quote(redirect_uri) +
        '&response_type=code'
        '&scope=' + urllib.parse.quote(scope) +
        '&access_type=offline'
        '&prompt=consent'
    )
    return jsonify({'url': url})

@app.route('/oauth/callback')
def oauth_callback():
    code = request.args.get('code', '')
    if not code:
        return 'No authorisation code received.', 400
    redirect_uri = APP_URL + '/oauth/callback'
    try:
        token_resp = httpx.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': code,
                'client_id': GOOGLE_CLIENT_ID,
                'client_secret': GOOGLE_CLIENT_SECRET,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code'
            },
            timeout=15
        )
        tokens = token_resp.json()
        access_token = tokens.get('access_token', '')
        refresh_token = tokens.get('refresh_token', '')
        accounts = []
        try:
            acct_resp = httpx.get(
                'https://mybusinessaccountmanagement.googleapis.com/v1/accounts',
                headers={'Authorization': 'Bearer ' + access_token},
                timeout=10
            )
            accounts = acct_resp.json().get('accounts', [])
        except Exception:
            pass
        access_enc = urllib.parse.quote(access_token)
        refresh_enc = urllib.parse.quote(refresh_token)
        accounts_enc = urllib.parse.quote(json.dumps(accounts))
        html = (
            '<!DOCTYPE html><html><head><title>Connecting...</title></head><body>'
            '<p>Connecting to Google Business, please wait...</p>'
            '<script>'
            'try {'
            "localStorage.setItem('g_access', decodeURIComponent('" + access_enc + "'));"
            "localStorage.setItem('g_refresh', decodeURIComponent('" + refresh_enc + "'));"
            "localStorage.setItem('g_accounts', decodeURIComponent('" + accounts_enc + "'));"
            "localStorage.setItem('g_just_connected', 'true');"
            "window.location.href = '/';"
            '} catch(e) {'
            "document.body.innerHTML = 'Connection error: ' + e.message;"
            '}'
            '</script></body></html>'
        )
        return html
    except Exception as e:
        return 'OAuth error: ' + str(e), 500

@app.route('/api/reviews', methods=['POST'])
def fetch_reviews():
    try:
        data = request.get_json() or {}
        access_token = data.get('access_token', '')
        location_name = data.get('location_name', '')
        if not access_token or not location_name:
            return jsonify({'error': 'Missing access_token or location_name'}), 400
        resp = httpx.get(
            'https://mybusiness.googleapis.com/v4/' + location_name + '/reviews',
            headers={'Authorization': 'Bearer ' + access_token},
            timeout=15
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/post-reply', methods=['POST'])
def post_reply():
    try:
        data = request.get_json() or {}
        access_token = data.get('access_token', '')
        location_name = data.get('location_name', '')
        review_id = data.get('review_id', '')
        reply_text = data.get('reply_text', '')
        if not all([access_token, location_name, review_id, reply_text]):
            return jsonify({'error': 'Missing required fields'}), 400
        resp = httpx.put(
            'https://mybusiness.googleapis.com/v4/' + location_name + '/reviews/' + review_id + '/reply',
            headers={
                'Authorization': 'Bearer ' + access_token,
                'Content-Type': 'application/json'
            },
            json={'comment': reply_text},
            timeout=15
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/send-review-email', methods=['POST'])
def send_review_email():
    try:
        data = request.get_json() or {}
        customer_name = data.get('customer_name', '').strip()
        customer_email = data.get('customer_email', '').strip()
        business_name = data.get('business_name', '').strip()
        review_link = data.get('review_link', '').strip()
        business_id = str(data.get('business_id', ''))
        if not customer_email or not business_name:
            return jsonify({'error': 'Missing required fields'}), 400
        if not RESEND_API_KEY:
            return jsonify({'error': 'RESEND_API_KEY not set in Railway environment variables'}), 500
        if not review_link:
            review_link = 'https://www.google.com/search?q=' + urllib.parse.quote(business_name + ' google reviews')
        first_name = customer_name.split()[0] if customer_name else 'there'
        unsubscribe_url = APP_URL + '/unsubscribe?email=' + urllib.parse.quote(customer_email)
        html_body = (
            '<!DOCTYPE html><html><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
            '<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif">'
            '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 20px">'
            '<tr><td align="center">'
            '<table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">'
            '<tr><td style="background:linear-gradient(135deg,#16a34a,#15803d);padding:36px 40px;text-align:center">'
            '<div style="font-size:26px;font-weight:800;color:white">' + business_name + '</div>'
            '<div style="font-size:14px;color:rgba(255,255,255,0.85);margin-top:6px">Thank you for choosing us</div>'
            '</td></tr>'
            '<tr><td style="padding:40px">'
            '<p style="font-size:16px;font-weight:600;color:#0f172a;margin:0 0 12px">Hi ' + first_name + '! &#128075;</p>'
            '<p style="font-size:14px;color:#475569;line-height:1.7;margin:0 0 16px">'
            'We really hope you enjoyed your experience with <strong>' + business_name + '</strong>. '
            'We work hard to provide the best possible service and hearing from customers like you means the world to us.</p>'
            '<p style="font-size:14px;color:#475569;line-height:1.7;margin:0 0 32px">'
            'Would you mind taking 60 seconds to leave us a Google review? '
            'It helps other local people find us and makes a huge difference.</p>'
            '<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">'
            '<a href="' + review_link + '" style="display:inline-block;background:linear-gradient(135deg,#16a34a,#15803d);'
            'color:white;text-decoration:none;font-size:15px;font-weight:700;padding:18px 44px;border-radius:10px">'
            '&#11088; Leave a Google Review</a>'
            '</td></tr></table>'
            '<p style="font-size:12px;color:#94a3b8;text-align:center;margin:20px 0 0">Takes less than a minute &bull; No account needed</p>'
            '</td></tr>'
            '<tr><td style="padding:20px 40px;border-top:1px solid #e2e8f0;background:#f8fafc">'
            '<p style="font-size:11px;color:#94a3b8;text-align:center;margin:0;line-height:1.8">'
            'You received this because you recently used ' + business_name + '.<br>'
            '<a href="' + unsubscribe_url + '" style="color:#94a3b8">Unsubscribe</a>'
            '</p></td></tr>'
            '</table></td></tr></table></body></html>'
        )
        resp = httpx.post(
            'https://api.resend.com/emails',
            headers={
                'Authorization': 'Bearer ' + RESEND_API_KEY,
                'Content-Type': 'application/json'
            },
            json={
                'from': business_name + ' Reviews <' + FROM_EMAIL + '>',
                'to': [customer_email],
                'subject': 'How was your experience with ' + business_name + '?',
                'html': html_body
            },
            timeout=20
        )
        result = resp.json()
        if resp.status_code in [200, 201]:
            return jsonify({'success': True, 'id': result.get('id', '')})
        else:
            return jsonify({'error': result}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/unsubscribe')
def unsubscribe():
    email = request.args.get('email', '')
    return (
        '<html><head><title>Unsubscribed</title>'
        '<style>body{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;'
        'min-height:100vh;margin:0;background:#f1f5f9}'
        '.card{background:white;padding:48px;border-radius:16px;text-align:center;max-width:400px;'
        'box-shadow:0 4px 24px rgba(0,0,0,0.08)}'
        'h2{color:#0f172a;margin:0 0 12px}p{color:#475569;line-height:1.6}</style></head>'
        '<body><div class="card">'
        '<div style="font-size:48px;margin-bottom:16px">&#10003;</div>'
        '<h2>Unsubscribed</h2>'
        '<p>' + (email or 'You') + ' will no longer receive review request emails.</p>'
        '</div></body></html>'
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
