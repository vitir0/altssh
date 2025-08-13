import socket
import threading
import logging
import time
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class SimpleHTTPProxy(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Health check для Render.com
            if self.path == '/health':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'OK')
                return
                
            # Проксируем HTTP-запрос
            host = 'www.google.com'  # Можно заменить на любой сайт
            port = 80
            
            # Создаем соединение с целевым сервером
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as remote_socket:
                remote_socket.connect((host, port))
                request = f"GET {self.path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
                remote_socket.sendall(request.encode())
                
                # Пересылаем ответ клиенту
                self.send_response(200)
                self.end_headers()
                while True:
                    data = remote_socket.recv(4096)
                    if not data:
                        break
                    self.wfile.write(data)
                    
            logger.info(f"Успешно проксирован запрос: {self.path}")
            
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Proxy error: {str(e)}".encode())

def run_server(port):
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, SimpleHTTPProxy)
    logger.info(f"HTTP-прокси запущен на порту {port}")
    httpd.serve_forever()

if __name__ == "__main__":
    PORT = int(os.environ.get('PORT', 443))
    
    # Ждем 10 секунд для инициализации Render
    logger.info("Ожидание 10 секунд для инициализации...")
    time.sleep(10)
    
    run_server(PORT)
