import struct
import os

f = open("operation.u5fs", "rb")

#read and parse the superblock
magic, version, bsize, bcount, root = struct.unpack(">IIIII", f.read(20))

def extract(dnode, out_path):
    #create the output directory
    os.makedirs(out_path, exist_ok=True)

    #read the directory inode
    f.seek(dnode * bsize)
    raw = f.read(bsize)

    #parse header to get size of directory entries
    header = struct.unpack(">IIIIIIIIIHHi", raw[:44])
    size = header[11]

    #slice out the directory entries
    entries_raw = raw[44:44+size]

    #parse entries
    offset = 0
    while offset < len(entries_raw):
        dnode, dtype = struct.unpack_from(">IB", entries_raw, offset)
        offset += 5
        name_start = offset
        while entries_raw[offset] != 0:
            offset += 1
        name = entries_raw[name_start:offset].decode("utf-8")
        offset += 1

        dst = os.path.join(out_path, name)

        if dtype == 1:
            extract(dnode, dst)

        elif dtype == 2:
            f.seek(dnode * bsize)
            raw_file = f.read(bsize)
            file_size = struct.unpack(">IIIIIIIIIHHi", raw_file[:44])[11]

            #direct block pointers - first 1009 slots
            n = (bsize - 44) // 4
            all_ptrs = struct.unpack_from(f">{n}I", raw_file, 44)
            direct = all_ptrs[:n - 4]
            indirect1 = all_ptrs[n - 4]
            indirect2 = all_ptrs[n - 3]
            blocks = [b for b in direct if b]

            #indirect1 - one extra block full of data block pointers
            if indirect1:
                f.seek(indirect1 * bsize)
                ind1_data = f.read(bsize)
                for i in range(0, bsize, 4):
                    b, = struct.unpack_from(">I", ind1_data, i)
                    if not b: break
                    blocks.append(b)

            #indirect2 - block of indirect1 blocks
            if indirect2:
                f.seek(indirect2 * bsize)
                ind2_data = f.read(bsize)
                i = 4 #skip reserved field
                while i + 4 <= bsize:
                    b, = struct.unpack_from(">I", ind2_data, i)
                    i += 4
                    if not b: break
                    f.seek(b * bsize)
                    sub = f.read(bsize)
                    for j in range(0, bsize, 4):
                        m, = struct.unpack_from(">I", sub, j)
                        if not m: break
                        blocks.append(m)

            buf = bytearray()
            for blk in blocks:
                f.seek(blk * bsize)
                buf.extend(f.read(bsize))
            open(dst, "wb").write(bytes(buf[:file_size]))

extract(root, "assignment")