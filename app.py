import os
import socket
import threading
import logging
from socketserver import ThreadingMixIn, TCPServer

logging.basicConfig(level=logging.INFO)

class ThreadedTCPServer(ThreadingMixIn, TCPServer):
    pass

class SocksProxy:
    def __init__(self, source_socket):
        self.source = source_socket
        self.target = None

    def handle(self):
        try:
            data = self.source.recv(4096)
            if data:
                # Здесь можно добавить логику обработки SOCKS
                # Упрощённая версия: перенаправляем трафик
                target_host = "example.com"  # Замените на ваш целевой хост
                target_port = 80
                
                self.target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.target.connect((target_host, target_port))
                self.target.sendall(data)
                
                threading.Thread(target=self.forward, args=(self.source, self.target)).start()
                threading.Thread(target=self.forward, args=(self.target, self.source)).start()
        except Exception as e:
            logging.error(f"Error: {e}")

    def forward(self, src, dst):
        while True:
            try:
                data = src.recv(4096)
                if not data: break
                dst.sendall(data)
            except:
                break

def main():
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", 10000))
    
    server = ThreadedTCPServer((HOST, PORT), lambda *args: None)
    server.request_queue_size = 20
    
    logging.info(f"Server started on port {PORT}")
    
    while True:
        client_socket, addr = server.get_request()
        logging.info(f"New connection: {addr}")
        proxy = SocksProxy(client_socket)
        threading.Thread(target=proxy.handle).start()

if __name__ == "__main__":
    main()
