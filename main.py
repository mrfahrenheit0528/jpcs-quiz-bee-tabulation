from website import create_app
import socket

app = create_app()

def get_local_ip():
    try:
        # Connect to a public DNS to find the correct outgoing IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == '__main__':
    # Get the local IP address
    host_ip = get_local_ip()
    port = 5000
    
    print(f" \n --- SERVER STARTED ---")
    print(f" * Local:    http://127.0.0.1:{port}")
    print(f" * Network:  http://{host_ip}:{port}")
    print(f" ----------------------\n")

    # host='0.0.0.0' makes it accessible to other devices
    app.run(debug=True, host='0.0.0.0', port=port)