import socket, time

HOST = '127.0.0.1'
PORT = 6666
HANDSHAKE = bytes([0x0a, 0x70, 0x01, 0xb6, 0x00, 0x96, 0x14, 0x66, 0x15, 0x06])
UPLOAD_CMD = bytes([
    0x17, 0x61, 0x35, 0x20, 0x06, 0x10, 0x0c,
    0x75, 0x70, 0x6c, 0x6f, 0x61, 0x64, 0x65,
    0x64, 0x2e, 0x6a, 0x70, 0x67, 0x00,
    0x00, 0x4b, 0xfb
])

def recv_all(s, timeout=1):
    s.settimeout(timeout)
    data = b''
    while True:
        try:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        except socket.timeout:
            break
    return data

#Work in progress
def make_data_packet(chunk, seq):
    header = bytes([0x77, 0x63, 0x6c, 0x34, 0x54,  # 'w' + 'cl4T'
                    0x00, 0x00, 0x00, 0x00, 0x00,   # 5 zeros
                    seq & 0xff])                     # sequence byte
    total = 1 + len(header) + len(chunk)
    return bytes([total]) + header + chunk

with open('dog.jpg', 'rb') as f:
    filedata = f.read()
print(f"Sending {len(filedata)} bytes")

s = socket.socket()
s.connect((HOST, PORT))

s.send(HANDSHAKE)
time.sleep(0.1)
s.send(UPLOAD_CMD)

resp = recv_all(s)
print(f"Acks ({len(resp)} bytes): {resp.hex()}")

if b'\x41' in resp:
    print("Upload accepted! Sending data...")
    CHUNK = 211
    seq = 0xc8
    for i in range(0, len(filedata), CHUNK):
        chunk = filedata[i:i+CHUNK]
        pkt = make_data_packet(chunk, seq)
        s.send(pkt)
        seq = (seq + 1) & 0xff
        time.sleep(0.05)  # small delay between chunks
        r = recv_all(s, timeout=0.5)
        if r:
            print(f"@ offset {i}: {r.hex()}")

    print("Transfer complete!")

s.close()