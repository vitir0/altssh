import os
from flask import Flask, redirect, request

app = Flask(__name__)

# Health check для Render.com
@app.route('/health')
def health():
    return "OK", 200

# Главная страница - поиск Google
@app.route('/')
def home():
    return redirect("https://www.google.com", code=302)

# Прокси-поиск
@app.route('/search')
def search():
    # Получаем поисковый запрос из URL
    query = request.args.get('q', '')
    
    # Перенаправляем в Google с поисковым запросом
    return redirect(f"https://www.google.com/search?q={query}", code=302)

# Прокси для всех других запросов
@app.route('/<path:path>')
def proxy(path):
    # Перенаправляем напрямую в Google
    return redirect(f"https://www.google.com/{path}", code=302)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 443))
    app.run(host='0.0.0.0', port=port, ssl_context='adhoc')
