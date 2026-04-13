# src/

This folder contains all scripts written for this assessment.

---

## u5fs_extractor.py
Recursively extracts the contents of a `U5FS` disk image to disk. Reads the superblock, traverses the inode tree, and handles direct and indirect block pointers. Run with `operation.u5fs` in the same directory. Outputs to `assignment/`.

## u2d_forger.py
Builds a valid signed `.u2d` image containing either an `OBJ_EXEC` or `OBJ_FILE` payload. Supports all five feature flags: `HMAC-SHA256`, `ARC4`, `LZ4`, `ZLIB`, and `UU` encoding. Toggle features at the top of the file. Requires `images/key.priv` and the `lz4` Python package.

## keystreampwn.py
Decrypts `imgC2` using the lab key, then recovers the keystream and uses it to partially decrypt `imgC1` without the key. Demonstrates a known plaintext attack against ARC4 keystream reuse. Requires `imgC1.u2d`, `imgC2.u2d`, and `key.priv` in the same directory.

## NetsrvTest.py
Work in progress. Implements the `netupsrv` handshake and upload command, reverse engineered from `capture.pcap`. Successfully completes the handshake and receives upload acknowledgement from the server. Ran out of time before confirming the transfer worked end to end.

## old_u5fs_extractor.py
The development version of the extractor. Kept to show the iterative process. It includes the step-by-step debugging code used to verify superblock parsing, directory entry reading, and multi-block file extraction before the logic was cleaned up into the final version.