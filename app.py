import socket
import threading
import socketserver

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass

class SocksProxy(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            print(f"Connection from: {self.client_address}")
            # SOCKS5 handshake
            self.request.recv(4096)
            self.request.sendall(b"\x05\x00")
            
            # Request details
            data = self.request.recv(4096)
            version, cmd, _, addr_type = data[:4]
            
            if addr_type == 1:  # IPv4
                addr = socket.inet_ntoa(data[4:8])
                port = int.from_bytes(data[8:10], 'big')
            else:
                self.request.close()
                return
                
            # Connect to target
            remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote.connect((addr, port))
            
            # Send success response
            self.request.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + b"\x00\x00")
            
            # Start tunneling
            self.tunnel(self.request, remote)
            
        except Exception as e:
            print(f"Error: {e}")

    def tunnel(self, client, remote):
        while True:
            try:
                data = client.recv(4096)
                if not data: break
                remote.sendall(data)
                
                reply = remote.recv(4096)
                if not reply: break
                client.sendall(reply)
                
            except:
                break
        client.close()
        remote.close()

if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 443
    server = ThreadedTCPServer((HOST, PORT), SocksProxy)
    server.serve_forever()
