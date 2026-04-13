import struct
import os

f = open("operation.u5fs", "rb")

#read and parse the superblock
magic, version, bsize, bcount, root = struct.unpack(">IIIII", f.read(20))

print(f"magic:       {bytes.fromhex(f'{magic:08x}')}")
print(f"version:     {version}")
print(f"block_size:  {bsize}")
print(f"block_count: {bcount}")
print(f"root_block:  {root}")

#root inode
f.seek(root * bsize)
raw = f.read(44)

fields = struct.unpack(">IIIIIIIIIHHi", raw)
reserved, uid, gid, atime_s, atime_ns, mtime_s, mtime_ns, ctime_s, ctime_ns, perm, links, size = fields

print(f"reserved:   {reserved}")
print(f"uid:        {uid}")
print(f"gid:        {gid}")
print(f"atime_sec:  {atime_s}")
print(f"atime_nsec: {atime_ns}")
print(f"mtime_sec:  {mtime_s}")
print(f"mtime_nsec: {mtime_ns}")
print(f"ctime_sec:  {ctime_s}")
print(f"ctime_nsec: {ctime_ns}")
print(f"perm:       {oct(perm)}")
print(f"links:      {links}")
print(f"size:       {size}")


#Directory entry looping
entries_raw = f.read(98)
offset = 0
while offset < len(entries_raw):
    dnode, dtype = struct.unpack_from(">IB", entries_raw, offset)
    offset += 5

    #read null-terminated name
    name_start = offset
    while entries_raw[offset] != 0:
        offset += 1
    name = entries_raw[name_start:offset].decode("utf-8")
    offset += 1

    dtype_name = {
        1: "dir",
        2: "file",
        3: "cdev",
        4: "bdev",
        5: "symlink",
        6: "pipe",
        7: "socket"
    }.get(dtype, f"unknown({dtype})")

    print(f"  dnode={dnode}  dtype={dtype_name}  name={name}")

#jump to README.md inode - dnode 126717
f.seek(126717 * bsize)
raw2 = f.read(bsize)

#parse the first 44 bytes as the inode header
header = struct.unpack(">IIIIIIIIIHHi", raw2[:44])

#index 11 is the size field
size2 = header[11]
print(f"README.md size: {size2} bytes")

#verify full block
print(f"raw2 length: {len(raw2)}")

#first block pointer is at offset 44
block_ptr = struct.unpack_from(">I", raw2, 44)[0]
print(f"data block: {block_ptr}")

#read the actual file contents
f.seek(block_ptr * bsize)
print(f.read(size2).decode("utf-8"))

#jump to BURNAFTERREADING.md inode - dnode 1383
f.seek(1383 * bsize)
raw3 = f.read(bsize)

#same header parse as before, grab size
header3 = struct.unpack(">IIIIIIIIIHHi", raw3[:44])
size3 = header3[11]
print(f"size: {size3} bytes")

#file is bigger than one block so need to read all block pointers
#they sit right after the 44 byte header, each 4 bytes wide
num_ptrs = (bsize - 44) // 4
ptrs = struct.unpack_from(f">{num_ptrs}I", raw3, 44)

#skip the zero entries - those are unallocated
blocks = [p for p in ptrs if p != 0]
print(f"blocks: {blocks[:10]}")

#read each block and stitch them together
buf = bytearray()
for blk in blocks:
    f.seek(blk * bsize)
    buf.extend(f.read(bsize))

#trim to actual size and print
print(bytes(buf[:size3]).decode("utf-8"))

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