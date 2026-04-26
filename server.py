from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests

app = Flask(__name__, static_folder='static')
CORS(app)

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

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

if __name__ == '__main__':
    print("")
    print("  ReviewBot is running!")
    print("  Open your browser and go to: http://localhost:5000")
    print("")
    app.run(debug=False, port=5000)
