import socket
import threading
import logging
import time
import os
import select

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class HybridServer:
    def __init__(self, port):
        self.port = port
        self.server_socket = None
        self.running = True
        self.create_socket()
        
    def create_socket(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(10)
            logger.info(f"Сервер запущен на порту {self.port}")
        except Exception as e:
            logger.error(f"Ошибка создания сокета: {e}")
            self.running = False

    def handle_healthcheck(self, client_socket):
        try:
            client_socket.settimeout(5)  # Таймаут 5 секунд
            request = client_socket.recv(1024)
            if b'GET /health' in request:
                response = (
                    b'HTTP/1.1 200 OK\r\n'
                    b'Content-Type: text/plain\r\n'
                    b'Connection: close\r\n\r\n'
                    b'OK'
                )
                client_socket.sendall(response)
                logger.info("Отправлен ответ на healthcheck")
            else:
                response = b'HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n'
                client_socket.sendall(response)
        except Exception as e:
            logger.error(f"Ошибка healthcheck: {e}")
        finally:
            client_socket.close()

    def handle_socks5(self, client_socket):
        try:
            client_socket.settimeout(10)  # Таймаут 10 секунд
            
            # Этап 1: Аутентификация
            data = client_socket.recv(2)  # Версия + количество методов
            if len(data) < 2 or data[0] != 0x05:
                return
                
            nmethods = data[1]
            methods = client_socket.recv(nmethods)
            client_socket.sendall(b'\x05\x00')  # NO AUTH REQUIRED

            # Этап 2: Запрос на подключение
            request = client_socket.recv(4)
            if len(request) < 4 or request[1] != 0x01:  # Только CONNECT
                return

            # Чтение адреса назначения
            addr_type = request[3]
            if addr_type == 0x01:  # IPv4
                addr = socket.inet_ntoa(client_socket.recv(4))
                port = int.from_bytes(client_socket.recv(2), 'big')
            elif addr_type == 0x03:  # Доменное имя
                domain_length = client_socket.recv(1)[0]
                addr = client_socket.recv(domain_length).decode()
                port = int.from_bytes(client_socket.recv(2), 'big')
            else:
                return

            logger.info(f"Запрос на подключение к {addr}:{port}")
            
            # Устанавливаем соединение с целевым сервером
            remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_socket.settimeout(10)
            remote_socket.connect((addr, port))
            
            # Отправляем успешный ответ
            response = b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00'
            client_socket.sendall(response)
            
            # Начинаем передачу данных
            self.relay_traffic(client_socket, remote_socket)
            
        except Exception as e:
            logger.error(f"Ошибка SOCKS5: {e}")
            try:
                client_socket.sendall(b'\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00')  # General failure
            except:
                pass
        finally:
            try:
                client_socket.close()
            except:
                pass

    def relay_traffic(self, client, remote):
        try:
            while True:
                # Ожидаем активности с любой стороны
                r, w, e = select.select([client, remote], [], [], 60)
                
                if client in r:
                    data = client.recv(4096)
                    if not data: 
                        break
                    remote.sendall(data)
                
                if remote in r:
                    data = remote.recv(4096)
                    if not data: 
                        break
                    client.sendall(data)
                    
        except Exception as e:
            logger.error(f"Ошибка ретрансляции: {e}")
        finally:
            try:
                remote.close()
            except:
                pass
            try:
                client.close()
            except:
                pass

    def handle_client(self, client_socket, client_address):
        try:
            logger.info(f"Ожидание данных от {client_address}")
            
            # Ждем данные до 5 секунд
            ready = select.select([client_socket], [], [], 5)
            if not ready[0]:
                logger.warning(f"Таймаут ожидания данных от {client_address}")
                client_socket.close()
                return
                
            # Получаем первые 3 байта без извлечения из буфера
            header = client_socket.recv(3, socket.MSG_PEEK)
            if not header:
                logger.info(f"Соединение закрыто клиентом {client_address}")
                client_socket.close()
                return
                
            logger.info(f"Получено от {client_address}: {header.hex()}")

            # SOCKS5: версия 5
            if header[0] == 0x05:
                logger.info(f"Обнаружено SOCKS5 подключение от {client_address}")
                self.handle_socks5(client_socket)
                
            # HTTP
            elif header.startswith(b'GET') or header.startswith(b'POS') or header.startswith(b'HEA'):
                logger.info(f"Обнаружено HTTP подключение от {client_address}")
                self.handle_healthcheck(client_socket)
                
            else:
                logger.warning(f"Неизвестный протокол от {client_address}: {header}")
                client_socket.close()
                
        except Exception as e:
            logger.error(f"Ошибка обработки клиента: {e}")
            try:
                client_socket.close()
            except:
                pass

    def start(self):
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                logger.info(f"Принято подключение от {client_address}")
                
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self.running:
                    logger.error(f"Ошибка accept: {e}")
                break

    def stop(self):
        self.running = False
        try:
            if self.server_socket:
                self.server_socket.close()
        except:
            pass
        logger.info("Сервер остановлен")

if __name__ == "__main__":
    PORT = int(os.environ.get('PORT', 443))
    logger.info("Ожидание 10 секунд для инициализации...")
    time.sleep(10)
    
    server = HybridServer(PORT)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        server.stop()
