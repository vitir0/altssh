import os
from flask import Flask, request, redirect

app = Flask(__name__)

# Health check для Render
@app.route('/health')
def health():
    return "OK", 200

# Простейший прокси
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def proxy(path):
    # Редирект на Google через прокси
    return redirect("https://www.google.com", code=302)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 443))
    app.run(host='0.0.0.0', port=port, ssl_context='adhoc')
