import socket

def get_local_ip() -> str:
    """ Attempts to determine the local IP address of the system. """
    try:
        # Create a dummy socket to connect to an external server (no traffic is sent)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        # We don't need to reach this IP, it's just to trigger the routing logic
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
