import os
import socket
import select
import threading
import logging
import time  # Добавлен недостающий импорт
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class ThreadedHTTPServer(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self, daemon=True)
        self.server = HTTPServer((host, port), ProxyHandler)
        self.host = host
        self.port = port
        
    def run(self):
        logger.info(f"HTTP-прокси запущен на {self.host}:{self.port}")
        self.server.serve_forever()
        
    def stop(self):
        self.server.shutdown()

class ProxyHandler(BaseHTTPRequestHandler):
    timeout = 30  # Таймаут операций
    
    def _connect_to_target(self, host, port):
        """Создает соединение с целевым сервером"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((host, port))
            return sock
        except Exception as e:
            logger.error(f"Ошибка подключения к {host}:{port}: {e}")
            return None
    
    def do_GET(self):
        try:
            # Health check для Render.com
            if self.path == '/health':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'OK')
                logger.info("Health check выполнен")
                return
                
            # Парсим URL запроса
            url = urlparse(self.path)
            target_host = url.hostname if url.hostname else 'www.google.com'
            target_port = url.port if url.port else 80
            
            # Создаем соединение с целевым сервером
            target_sock = self._connect_to_target(target_host, target_port)
            if not target_sock:
                self.send_error(502, "Bad Gateway")
                return
                
            # Формируем HTTP-запрос
            request = f"GET {self.path} HTTP/1.1\r\n"
            request += f"Host: {target_host}\r\n"
            request += "Connection: close\r\n"
            request += "\r\n"
            
            # Отправляем запрос целевому серверу
            target_sock.sendall(request.encode())
            
            # Получаем ответ и перенаправляем клиенту
            self.send_response(200)
            self.end_headers()
            
            while True:
                ready = select.select([target_sock], [], [], self.timeout)
                if ready[0]:
                    data = target_sock.recv(4096)
                    if not data:
                        break
                    self.wfile.write(data)
                else:
                    logger.warning("Таймаут при чтении данных")
                    break
                    
            logger.info(f"Успешно проксирован запрос: {self.path}")
            
        except Exception as e:
            logger.error(f"Ошибка обработки запроса: {e}")
            self.send_error(500, "Internal Server Error")
        finally:
            if target_sock:
                target_sock.close()
    
    def do_CONNECT(self):
        """Обработка HTTPS-соединений"""
        try:
            # Парсим хост и порт
            parts = self.path.split(':')
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 443
            
            # Создаем соединение с целевым сервером
            target_sock = self._connect_to_target(host, port)
            if not target_sock:
                self.send_error(502, "Bad Gateway")
                return
                
            # Отправляем клиенту подтверждение
            self.send_response(200, 'Connection Established')
            self.end_headers()
            
            # Перенаправляем трафик между клиентом и сервером
            sockets = [self.connection, target_sock]
            while True:
                readable, _, _ = select.select(sockets, [], [], self.timeout)
                if not readable:
                    break
                    
                for sock in readable:
                    data = sock.recv(4096)
                    if not data:
                        sockets.remove(sock)
                        sock.close()
                        if len(sockets) < 2:
                            return
                        continue
                        
                    if sock is self.connection:
                        target_sock.sendall(data)
                    else:
                        self.connection.sendall(data)
                        
        except Exception as e:
            logger.error(f"Ошибка HTTPS-туннеля: {e}")
        finally:
            if hasattr(self, 'target_sock') and self.target_sock:
                self.target_sock.close()

def main():
    port = int(os.environ.get('PORT', 443))
    logger.info(f"Старт сервера на порту {port}")
    
    # Запускаем HTTP-сервер в отдельном потоке
    http_server = ThreadedHTTPServer('0.0.0.0', port)
    http_server.start()
    
    try:
        # Бесконечное ожидание (с возможностью прерывания)
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info("Остановка сервера...")
        http_server.stop()

if __name__ == '__main__':
    logger.info("Инициализация прокси-сервера...")
    main()
