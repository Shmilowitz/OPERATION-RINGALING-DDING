c1 = open("imgC1.u2d", "rb").read()
c2 = open("imgC2.u2d", "rb").read()

print(f"imgC1: {len(c1)} bytes")
print(f"imgC2: {len(c2)} bytes")

#payload starts after header at byte 8
print(f"imgC1 payload: {len(c1) - 8} bytes")
print(f"imgC2 payload: {len(c2) - 8} bytes")

key = open("key.priv", "rb").read()
print(f"key: {len(key)} bytes")

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

#payload starts after header at byte 8
c2_payload = c2[8:]
decrypted_c2 = rc4(key, c2_payload)
print(f"decrypted imgC2: {decrypted_c2.hex()}")

#cut the first 32 bytes which are the HMAC tag
objects = decrypted_c2[32:]

#ascii parse
print (objects)

#keystream = ciphertext XOR plaintext
keystream = bytes(a ^ b for a, b in zip(c2_payload, decrypted_c2))
print(f"recovered keystream: {keystream.hex()}")
print(f"keystream length: {len(keystream)}")

c1_payload = c1[8:]

#XOR imgC1 ciphertext with recovered keystream
decrypted_c1_partial = bytes(a ^ b for a, b in zip(c1_payload, keystream))
print(f"partial imgC1 decrypted: {len(decrypted_c1_partial)} bytes")
print(f"hex: {decrypted_c1_partial.hex()}")
print(f"ascii: {decrypted_c1_partial}")

