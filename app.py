import socket
import threading
import logging
import time
import os

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
        
        # Создаем сокет
        self.create_socket()
        
    def create_socket(self):
        """Создаем и настраиваем сокет"""
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
        """Обработка healthcheck запросов от Render.com"""
        try:
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
                response = (
                    b'HTTP/1.1 404 Not Found\r\n'
                    b'Connection: close\r\n\r\n'
                )
                client_socket.sendall(response)
        except Exception as e:
            logger.error(f"Ошибка healthcheck: {e}")
        finally:
            client_socket.close()

    def handle_socks5(self, client_socket):
        """Реализация простого SOCKS5 прокси"""
        try:
            # Этап 1: Аутентификация
            client_socket.recv(256)  # Читаем приветствие
            client_socket.sendall(b'\x05\x00')  # NO AUTH
            
            # Этап 2: Запрос на подключение
            data = client_socket.recv(4)
            if len(data) < 4:
                raise ValueError("Неверный запрос")
                
            version, cmd, _, addr_type = data
            if version != 5 or cmd != 1:  # Только CONNECT
                raise ValueError("Неподдерживаемая команда")
            
            # Чтение адреса назначения
            if addr_type == 1:  # IPv4
                addr = socket.inet_ntoa(client_socket.recv(4))
            elif addr_type == 3:  # Доменное имя
                domain_length = client_socket.recv(1)[0]
                addr = client_socket.recv(domain_length).decode()
            else:
                raise ValueError("Неподдерживаемый тип адреса")
                
            # Чтение порта назначения
            port = int.from_bytes(client_socket.recv(2), 'big')
            
            logger.info(f"Запрос на подключение к {addr}:{port}")
            
            # Устанавливаем соединение с целевым сервером
            remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_socket.connect((addr, port))
            
            # Отправляем успешный ответ
            bind_addr = socket.inet_aton('0.0.0.0')
            bind_port = 0
            response = b'\x05\x00\x00\x01' + bind_addr + bind_port.to_bytes(2, 'big')
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
        """Передача данных между клиентом и удаленным сервером"""
        try:
            while self.running:
                # Проверяем данные от клиента
                if client in socket.select([client], [], [], 1)[0]:
                    data = client.recv(4096)
                    if not data: 
                        break
                    remote.sendall(data)
                
                # Проверяем данные от сервера
                if remote in socket.select([remote], [], [], 1)[0]:
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

    def handle_client(self, client_socket, client_address):
        """Определяем тип подключения и обрабатываем"""
        try:
            # Проверяем первый байт для определения типа подключения
            first_byte = client_socket.recv(1, socket.MSG_PEEK)
            
            if first_byte == b'\x05':  # SOCKS5
                logger.info(f"Обнаружено SOCKS5 подключение от {client_address}")
                self.handle_socks5(client_socket)
            else:  # Предполагаем HTTP (для healthcheck)
                logger.info(f"Обнаружено HTTP подключение от {client_address}")
                self.handle_healthcheck(client_socket)
                
        except Exception as e:
            logger.error(f"Ошибка обработки клиента: {e}")
            try:
                client_socket.close()
            except:
                pass

    def start(self):
        """Основной цикл сервера"""
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                logger.info(f"Принято подключение от {client_address}")
                
                # Обработка клиента в отдельном потоке
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
        """Остановка сервера"""
        self.running = False
        try:
            if self.server_socket:
                self.server_socket.close()
        except:
            pass
        logger.info("Сервер остановлен")

if __name__ == "__main__":
    # Получаем порт из переменных окружения Render.com
    PORT = int(os.environ.get('PORT', 443))
    
    # Ждем 10 секунд перед запуском (для инициализации сети)
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
