
# OPERATION RINGALING-DDING
---
## Security Assessment Report

**Primary Attack Vector:** update2d

**Secondary Attack Vector:** netupsrv

**Target:** DDING-3000 SmartBell - International Bongo Machines

_by David Shmilowitz_

# **1**. Unpacking the U5FS Image

The assignment files came inside a disk image called `operation.u5fs`. It also came with a PDF that described a custom filesystem called `U5FS`, a fictional format designed specifically for the Femtium architecture that powers the DDING-3000's embedded system. First thing I did was research the format, but nothing useful came up. Only that Femtium is a custom computer architecture emulator used by FE. No tooling exists for this format, so the only option was to read the spec and write an extractor from scratch.
## 1.1 PDF walkthrough

The PDF described U5FS as a block-based filesystem. Reading through the documentation, there were key things I needed to understand: how the superblock is laid out, where inodes lived, how directories chained to other inodes, and how file data blocks are referenced.  
There are three fundamental structures (besides the file data and unused free blocks):

**1. The Superblock (block 0)** The very first block is special. It's called the superblock and it's the entry point to the entire filesystem. It contains:

![](assets/images/1.1%20u5fs.pdf%20-%20Section%2010%20Superblock.png)
- `magic` - The magic number (`0x55354653` which is the ASCII string "U5FS") that confirms this is actually a U5FS image.
- `version` - The version number (v1 or v2).
- `blocksize` - The block size in bytes.
- `blockcount` - The total number of blocks.
- `rootnode` - The block number of the root inode.

You always start here. Without the superblock you have no idea where anything is.

**2. The Block Allocation Bitmap (block 1)** Right after the superblock comes the bitmap. This is a long sequence of bits, one bit per block in the entire filesystem. If a bit is 1, that block is in use. If it's 0, it's free.


For reading purposes (which is all I needed for extraction), the bitmap is mostly irrelevant. I just followed the inode chain and let the inodes tell me which blocks belong to each file. The bitmap matters more when you're writing or allocating new files. For this extraction I skipped it entirely and followed the inode chain directly.

**3. Inodes** This is where it gets interesting. An inode is a metadata structure that describes a filesystem object. Every file, every directory, every symlink has exactly one inode. The inode contains:
![](assets/images/1.1%20u5fs.pdf%20-%20Section%2011%20Filesystem%20inode%20format.png)
- `reserved` - 4 unused bytes
- `Owner` (`uid` and `gid`).
- `Timestamps` (access time, modification time, change time) with whole seconds and nanoseconds.
- `perm` - Permissions (16-bit Unix permission mask).
- `links` - Number of  links.
- `size` - File size in bytes.

The **root inode** is the inode for the root directory. The superblock tells me which block number it lives in.
### Directory inodes

A directory inode starts with the common `u5fs_inode` fields described above, then contains a list of **directory entries** (`u5fs_dentry`). Each entry has the following format:

- `dnode` - A block number pointing to another inode.
- `dtype` - A type byte indicating what kind of thing that inode is (file, directory, symlink, etc.).
- `name[]` - A null-terminated UTF-8 string containing the name.

So a directory inode essentially says: "I contain these named things, and here's the block number of each one's inode." 
To list a directory, read its inode, then read the dentry list. To recurse into a subdirectory, you take its `dnode`, read that block as an inode, and repeat. This is exactly how every Unix filesystem works.
### File inodes

A file inode starts with the same common fields, then contains a list of data block numbers.
To read a file:
1. Read its inode
2. Get the list of block numbers
3. Read each block in order
4. Concatenate them
5. Trim to `size` bytes (the last block might not be fully used)

For small files, all the block numbers fit directly in the inode. For larger files, U5FS uses indirection:

- `block[n]` The first 1009 slots in the inode are direct data block pointers
- `indirect1` - If those run out, this field points to a block that contains another list of data block numbers
- `indirect2` - If even that's not enough, this field points to a block containing a list of indirect1 blocks

I thought of it like this: direct blocks are like having your friends' addresses written in your notebook. indirect1 is like "call this person, they have a list." indirect2 is like "call this person, they have a list of people who each have a list."

The spec was very explicit about the maximum size of around 4GB. Below is an image reference taken from `u5fs.pdf`:

![](assets/images/1.1%20u5fs.pdf%20-%20Maximum%20Size.png)
## 1.2 Deconstructing operation.u5fs

First thing I did was hexdump the start of the file to check the layout matched what the spec said:
![](assets/images/1.2%20hex%20dump%20of%20operation.u5fs.png)

```
00000000: 5535 4653    = "U5FS" magic (4 bytes)
00000004: 0000 0002    = Version 2
00000008: 0000 1000    = Block size (4096 = 0x1000)
0000000C: 0001 f400    = Block count (128000)
00000010: 0000 0006    = Root inode block (6)
```

The header values match the structure described in the documentation. The magic value `U5FS` identifies the filesystem, followed by the version number, block size, and block count.  
The endianness can also be confirmed to be big-endian. The `block size` field at offset `00000008` contains `00001000`. In big-endian encoding, the most significant byte comes first, so reading left to right gives `0x00001000`, which is exactly the expected block size listed in the documentation of 4096.

## 1.3 Initial Python script

I intended to write my extractor script in Python, since I have a lot of experience with it.

![](assets/images/Pasted%20image%2020260321184348.png)


I used Python's `struct` library, referring to the documentation to translate the spec fields into an unpack format string. My script reads the superblock that contains exactly 5 fields, each a 32-bit integer (4 bytes each): 5 × 4 = 20. The script unpacks the tuple directly into named variables in one line. Then I printed the results to the terminal. So:

- `magic` gets the first 4 bytes → `0x55354653` → "U5FS"
- `version` gets bytes 4-7 → `2`
- `bsize` gets bytes 8-11 → `4096`
- `bcount` gets bytes 12-15 → `128000`
- `root` gets bytes 16-19 → `6`

![](assets/images/Pasted%20image%2020260321172933.png)

### Parsing the Root Inode

The superblock just told me where everything is. With `root = 6` and `bsize = 4096`, the root inode is at byte offset `6 × 4096 = 24576`.

Looking at the documentation for `u5fs_inode`:

![](assets/images/Pasted%20image%2020260321173000.png)

Counting it would mean:

- `4 reserved`
- `4 owner_id`
- `4 owner_gid`
- `4 atime_secs`
- `4 atime_nsec`
- `4 mtime_secs`
- `4 mtime_nsec`
- `4 ctime_secs`
- `4 ctime_nsec`
- `2 perm 2 links`
- `4 size`
- total = 44 bytes
  
With the blueprint for `u5fs_inode` I extended my Python script with the translated root inode header structure. `fields` takes the 44 raw bytes and splits them according to the format string:
- `>` = big-endian
- `IIIIIIIII` = nine unsigned 32-bit integers (reserved, uid, gid, and the three timestamp pairs)
- `HH` = two unsigned 16-bit integers (perm and links)
- `i` = one signed 32-bit integer (size)

![](assets/images/Pasted%20image%2020260321184533.png)

`fields` becomes a 12 value tuple that I print out to the terminal:

![](assets/images/Pasted%20image%2020260321173057.png)

Comparing the additional information from output to what I expected:
- `reserved: 0` correct, documentation says this field is unused for historical reasons.
- `uid: 0` **and** `gid: 0` root owned, as expected for a filesystem root directory.
- `atime_sec: 1773102411` last access time as Unix timestamp (2026).
- `mtime_sec: 1773046100` last modified time as Unix timestamps (2026).
- `ctime_sec: 1773102367` last metadata change time as Unix timestamps (2026).
- `perm: 0o755` means `rwxr-xr-x` which is standard Unix root directory permissions.
- `links: 1` one hard link to this inode.
- `size: 98` bytes.

All of this confirms my byte offsets are completely correct. The size being 98 bytes is important. It means there are 98 bytes of directory entries immediately following this 44-byte header in the block. That's what I'll read next.
### Examining the root directory’s entries

Now that I know the root directory has 98 bytes of directory entries. The documentation also lists that `u5fs_dentry`’s `dnode` is 4 bytes and `dtype` is 1 byte:


With this information I knew that I had to loop through all 98 bytes and every time I found a directory, I needed to add 5 bytes to my offset counter:

![](assets/images/Pasted%20image%2020260321191603.png)

Checking that `offset` was working I printed the values into terminal:

![](assets/images/Pasted%20image%2020260321173227.png)

`offset` counter is working correctly for each iteration, but `dtype` doesn’t look correct. The documentation lists the following dtypes:

![](assets/images/Pasted%20image%2020260321173237.png)

Going back to the documentation, I realized I was missing the name reading part.

![](assets/images/Pasted%20image%2020260321192809.png)

The loop was only reading `dnode` and `dtype`, moving forward exactly 5 bytes each iteration and leaving the `name[]` bytes unread. This meant the next iteration started in the middle of a name string, which explained the garbage `dtype` values like 65, 82, and 178.

The fix is straightforward. Unlike `dnode` and `dtype` which are fixed sizes, `name[]` has no static byte length. The documentation defines it as a zero-terminated string. So instead of reading a fixed number of bytes, I walk forward one byte at a time until I hit a null byte. I also changed the print outs to get a better understanding of what was going on:

![](assets/images/Pasted%20image%2020260321193318.png)

This way each iteration consumes the complete entry. 4 bytes for `dnode`, 1 byte for `dtype`, n bytes for the `name[]`, and 1 byte for the null-terminator, before moving on to the next one.
Below is the output result:

![](assets/images/Pasted%20image%2020260321173311.png)

Great, now the files inside the .`u5fs` file are readable and makes sense. I planned to start extracting the `README.md` file first. For that I first needed to extract the size of the file:

![](assets/images/Pasted%20image%2020260321193812.png)

Output:
![](assets/images/Pasted%20image%2020260321173327.png)

The `README.md` file being 455 bytes means that it would only need one data block, since 455 < 4096. But I still had to read the full block. The next step was to extract the content of the `README.md` file.

![](assets/images/Pasted%20image%2020260321210247.png)

![](assets/images/Pasted%20image%2020260321173339.png)
*Output*
To showcase the read chain so far in a graphical way:
- superblock (block 0)
	- root inode (block 6)
		- directory entries (98 bytes)
			- README.md inode (block 126717)
				- data block pointer (block 15148)
					- file contents (455 bytes)

The next step is to do the same thing for `BURNAFTERREADING.md`, its `dnode` is at `1383`. Exactly same recipe, just using `dnode` 1383 instead of 126717.

![](assets/images/Pasted%20image%2020260321211224.png)

Running above script resulted in some issues, because unlike `README.md`, `BURNAFTERREADING.md` is 15148 bytes. Too large to fit in a single 4096-byte block. 15148 / 4096 = 3.6982… meaning the file spans 4 blocks. Therefore I needed to follow the block pointers.

![](assets/images/Pasted%20image%2020260321211411.png)


The updated script includes the following additions:

- Line 106 - After the 44-byte header, the rest of the 4096-byte block is packed with 32-bit block pointers. `(4096 - 44) / 4 = 1013` total pointer slots. This accounts for the 1009 direct block pointers + `indirect1` + `indirect2` + `reserved0` + `reserved1`, which are the four additional fields defined in the documentation.

- Line 107 - I read all of them at once using a dynamic format string. `f">{num_ptrs}I"` expands to `">1013I"` which reads 1013 unsigned 32-bit integers starting at offset 44.

- Line 110+111 - Most of those 1013 slots are empty. Only the first few contain real block numbers. A zero value means unallocated per the documentation. This list collects only the non-zero pointers, giving me just the blocks that actually contain file data. The blocks without a zero value get printed:

![](assets/images/Pasted%20image%2020260321221123.png)	

- Line 114 to 117 - Loop through each block number and append to `buf`. After the loop `buf` contains all the raw file data stitched together. But it will be slightly too long since the last block is only partially used.

- Line 120 – Trims to actual size of file and decode from raw bytes to a readable string and prints it.

The updated script successfully printed the entire `BURNAFTERREADING.md` file:

![](assets/images/Pasted%20image%2020260321221023.png)

### Directory Inode Structure

Directory inodes follow a different layout. The documentation defines `u5fs_dir_inode` as:

![](assets/images/Pasted%20image%2020260321220949.png)
  
Unlike file inodes, directory inodes have no block pointers after the header. Instead, the directory entries are stored directly in the same block, immediately following the 44-byte header. This means there's no indirection, everything is self-contained in one block.

The `size` field tells me exactly how many bytes of entries follow the header. For the root directory, `size` returned 98, so bytes 44 through 141 of block 6 are directory entries. I already knew this from earlier in the script. I just needed to slice those bytes out and parse them.

This makes sense given that a directory is essentially just a list of names and pointers, small enough to fit in a single block. A file can be any size, so it needs to point to as many data blocks as it requires.

I could reuse some of the same logic used for the root directory, but the parts explained above need to be accounted for.

![](assets/images/Pasted%20image%2020260321220918.png)

For file inodes I read block pointers at offset 44 and followed them to external data blocks. For directory inodes the data is right here in the same block, so I just slice it out directly.

The output can be seen in the image below:

![](assets/images/Pasted%20image%2020260321221411.png)

### Refactoring and scaling for repeated actions

Inside `update2d` directory, I saw 2 files and 3 directories. My Python script now has the logic to extract both files and directories. The logic is the same just using different `dnode` number each time.

I needed to create a function that can be called multiple times and used to iterate over the root directory and subdirectories. Wrapping the directory extraction logic into a function does the trick. It also needs to write the extracted files to disk rather than just printing them.

![](assets/images/Pasted%20image%2020260321222221.png)

  ![](assets/images/Pasted%20image%2020260321222059.png)
  
Inside my function I needed to use `dtype` to determine what I am hitting. There are 2 types of dtypes that dictates the following reaction. The rest are not important for this extraction:

- `dir` - dtype 1
  When I hit a directory entry I call `extract` again with that entry's `dnode`, which runs the entire function again for the subdirectory, which may find more subdirectories, which calls `extract` again, and so on until there are no more directories left. Basically a recursive walkthrough.
- `file` - dtype 2
  Same logic as `BURNAFTERREADING.md`: read the inode, get the size, read all block pointers, stitch the blocks together, trim to actual size.

![](assets/images/Pasted%20image%2020260321223508.png)

Running the script extracted the entire filesystem:

  
But shortly after I realized that I got too excited too soon. Some files were exactly the same size and no file exceeded 3.9MB. Meaning that the larger files were cut off at 3.9MB.
This is when I realized that I forgot to add logic for indirect1 and indirect2. Basically cutting any file short if it was larger than the maximum:

1009 blocks × 4096 bytes = 4132864 bytes ≈ 3.9 MB.

  
### Adding Indirect Block Support

The documentation says the last 4 slots are `indirect1`, `indirect2`, `reserved`, `reserved`. So `n-4` is `indirect1` and `n-3` is `indirect2`. Everything before those is a direct data block pointer:

![](assets/images/Pasted%20image%2020260321232916.png)  
  
If `indirect1` is non-zero it means the file is large enough to need an extra block of pointers. I jump to that block and read it. I read it as a list of 32-bit block numbers, stop at the first zero, and append each non-zero block number to my list. Same pattern as reading direct blocks, just one level of indirection added:

![](assets/images/Pasted%20image%2020260322172515.png)

`indirect2` adds another layer. The `indirect2` block does not contain data block numbers directly. It contains a list of `indirect1` block numbers. So I needed to read the `indirect2` block, skip the first 4 bytes, which the documentation says are reserved, then loop through its entries.  
Each non-zero entry is itself an `indirect1` block, so I jumped to it and read its list of data block numbers exactly the same way as above. `indirect2` gives `indirect1` blocks, each `indirect1` block gives data blocks.

It’s a nested loop.

![](assets/images/Pasted%20image%2020260321233943.png)

## 1.4 Future Improvements

The script works for the purpose it was written for, extracting the contents of a known image under controlled conditions. Because of the scope of this assignment I won’t spend time polishing the script, but If I were to create a reusable script I would look into the following improvements:

- General cleanup
    - Removing steps that were used in early development that serves no purpose other than testing and investigating.
    - Replacing hardcoded values with variables to add flexibility.
- QoL improvements
    - Improve print-outs
    - Progress bar
    - Fail-checks
    - Better naming for variables
    - Better descriptive comments.
- Write a readme.md for the script that explains how to use it.
- Add handling for directories that spans more than one block.
- Add protection against corrupted images. Bad block pointers would crash the script.

# 2. Three Possible Paths

The extracted filesystem contained three different tasks, which I could pick from:

### Netupsrv

No source code was provided, meaning the protocol would have to be reconstructed entirely from packet captures and binary analysis. Binary exploitation without source can be time consuming and the risk of spending significant time without producing a working made this my 2nd pick.

### Update2d

The source code was provided, which removes the need for blind reverse engineering.  
My brief brainstorming made me assume that the skills required would be: file format analysis, Python scripting, and basic cryptography. Which matched what I was already doing in the U5FS extraction work. The path from reading the code to producing an exploit felt best suited for me.

### Firmware

Femtium is a fictional architecture with no existing tools, no community resources, and no prior art to reference. Even basic tasks like disassembly would require building or extending tools from scratch. Beyond that, writing shellcode or exploits for an unknown ISA requires deep embedded systems knowledge and assembly fluency that I didn't feel confident enough in to produce meaningful results within the scope of this assessment.

This made it the least attractive choice for demonstrating my current skillset.

### My decision

Based on the assessment above I chose update2d as my primary attack vector. It offered the best balance between the skills I already have and the complexity of the task. The other two vectors presented too much uncertainty around tooling and prior knowledge to be a productive use of the available time.

# 3. update2d

The `README.md` file contained information about the setup and the assignment at hand. A summary of the key points:

Setup
- Full source code.
- A working dummy private key for signing crafted images.
- 6 real sample images showing all feature combinations.
- The exact command line used on target.

Objectives
- Primary objective: Find a way to make update2d execute unintended commands.
- Make the solution work regardless of which feature combination the target uses.
- Produce a proof of concept .u2d file that runs a command of my choosing.
- Decrypt the intercepted images if possible.
- Bonus: find a way to escalate from the unprivileged uid=1001 to root, given that the service itself runs as root.

## 3.1 Getting an overview

My first thought was to thoroughly get a grasp of all the information for the assignment. Inside of the `src` directory there’s another `README` file.


The files were named meaningfully and therefore with a bit of research, the structure was fairly obvious.

- The folder `images` contained the 6 real sample images and the private key as described in the parent `README.md` file.
- `Src` folder contained a `README` resembling documentation for update2d.
- `ARC4`, `HMAC-SHA256` and `SHA-256` were the crypto components.
- Files with the `xfrm_` prefix were handling compression, encryption and encoding.
- `update2d.c` and `main.c` were the core logic files.
- `tcp_server` and `watchdir` files handled the different modes the service can run in.
- Rest was misc. Like logging, ring buffer utility and debug helpers.

I started with `update2d.h` since header files usually give the clearest picture of the structure of the codebase. For the sake of explanation and using the ”divide and conquer” technique, I decided to split the header file into sections.

## 3.2 Update2d.h

I split the header file into seven logical sections, each revealing a different layer of how the service works.

**Section 1**  declared that it only processes `.u2d` files and that the expected version number in every image header is `VER_2`:

  
**Section 2** creates the global struct `G` that lists everything the service needs at runtime. As the `src/README` describes, the keyfile is used for both authentication and decryption: "Master key used for authentication and decryption." This means the same key field controls both the `HMAC` signature verification and the `ARC4` decryption of any encrypted image:

  
Unsigned
- **mode:** which mode the service runs in (stdin, file, listen or watch).
- **port**: network port when running in listen mode.
- **uid / gid**: the user and group to drop privileges to before running EXEC commands.
- **timeout**: how long before an unfinished update is aborted.

Char
- **file**: path to a specific `.u2d` file when running in file mode.
- **watch**: directory to monitor when running in watch mode.
- **logfile**: where to write log output.
- **keyfile**: path to the signing and encryption key file.

Boolean
- **listen**: true if listening for TCP connections.
- **onlysigned**: true if unsigned images should be rejected.
  The `src/README` recommends this flag for devices connected to the Internet: "Accept only signed U2D images. Recommended for devices connected to the Internet."
- **onlycrypto**: true if unencrypted images should be rejected.
- **verbose**: true if log output should also go to stdout.
- **filelog**: true if a separate log file should be written.

Other
- **logfp**: internal file handle for the log file.
- **key**: the actual key bytes read from the keyfile.
- **key_len**: length of the key in bytes.

**Section 3** The magic bytes confirm the format, `UP` for a normal image, `UU` for a UU-encoded image. The flags are a bitmask, that describes which transformations have been applied to the image. This tells exactly how to interpret the image before reading any further.  
These map directly to the features described in `src/README`: `LZ4` and `zlib` compression, `HMAC-SHA256` signing, `ARC4` encryption, and UU-encoding:

  
**Section 4** Every single `.u2d` file starts with exactly 8 bytes in the header `struct`. It consists of 2 bytes for magic, 1 byte for version, 1 byte for flags and 4 bytes for size.  
The struct uses `__attribute__((packed))`, which tells the compiler not to insert any padding between fields:

  
**Section 5** holds the four instructions a `.u2d` image can give the device. My initial thought was that `OBJ_EXEC` looked promising, since a dedicated object type whose entire purpose is to run a command on the device seemed like an obvious attack path. The question at this point is just how that command gets passed to the shell.

The `update2d`'s `README` says: "In a real DDING-3000, update2d runs as SUID root, to allow it to change UID and GID." This means file writes happen with root privileges before any privilege drop occurs, making `OBJ_FILE` a potential path to writing to sensitive system locations.

  
**Section 6** `FLG_CRC32` is an object level flag that enables checksum verification for individual objects. When set, a 4 byte CRC32 checksum is appended after the object payload. As the `src/README` describes: "To protect against data corruption during transfer to the remote device, U2D images can be augmented with a checksum of each contained object." Unlike the HMAC signature which covers the entire image and is a security mechanism, CRC32 is per object and only protects against accidental data corruption during transfer, not intentional tampering.


**Section 7** The last section handles error codes.

## 3.3 Update2d.c

After analyzing the header, the next logical step was `update2d.c`. I will describe the functions in this writeup in order of appearance. Same approach: `cat` first for an overview, then into specifics.

`update2d.c` is significantly larger than `update2d.h`, so I decided to briefly go over the less important functions and more precisely dissect the functions that play an important role going forward.

**Function 1 -** `u2d_apply_image_from_stdin()`

It takes the image from `stdin`, writes it to a temporary file via `tmpfile()`, then checks the flags. If `--onlysigned` is set the image must have `FLG_HMAC_SHA256`, and if `--onlycrypto` is set it must have `FLG_ARC4`. Either way the service exits if the check fails. If `FLG_HMAC_SHA256` is set, it calls `u2d_verify_image()` before handing off to `u2d_process_image()`

  
### Authentication happens too late

The flag checks happen after `u2d_receive_image()` has already fully received and decoded the image into `tmpfile`. The image is completely decoded before the signature is even looked at. That means if the `zlib` decompressor, `LZ4` decompressor, or `UU` decoder had any bugs in them, you could trigger them with a malformed image and no valid signature needed. I didn't go down this path, but it's worth flagging.

**Function 2 -** `u2d_receive_image()`

This function handles reading and decoding the incoming image from `stdin` into a temporary file. The function builds a chain of transforms depending on which flags are set in the header. `UU` decoding happens first since it is detected from the magic bytes before the rest of the header is read, then `zlib`, then `ARC4`, then `LZ4` based on the if statements:

`stdin -> uudecode -> zlib -> ARC4 -> LZ4 -> tmpfile`

This transform order was directly useful when writing the decryption tool later, since getting the order wrong produces garbage output rather than a helpful error. The function itself has no security logic, it just decodes whatever it receives. The decision of when to verify the signature is made by the caller.

**Function 3 -** `u2d_verify_image()`

This function handles the `HMAC-SHA256` signature verification. It reads the 32-byte signature tag from the start of the payload, then computes its own `HMAC` over the remaining bytes using the key from `G.key`, and compares the two with `memcmp()`.

In the lab I had the dummy `key.priv` which meant I could sign any image I crafted and it would pass verification. On the real target the key is unknown, which means this function is the primary barrier against sending forged images.

**Function 4 –** `u2d_process_image()`

Processing of the image is a straightforward dispatch loop. It reads 5-byte object headers one at a time and routes each one to the appropriate handler based on the type. The loop runs indefinitely until it hits `EOF` on the `tmpfile`, at which point it closes the file and returns. Any unknown object type causes the service to exit with `BADOBJ_UNKWN_TYPE`. The function itself has no security logic, it just reads and routes. The interesting behavior is entirely inside the handlers it calls, particularly `u2d_process_exec()` which is next.

**Function 5 –** `u2d_process_exec()`

This is the most important function in the entire codebase from an attacker point of view. For that reason, I split the review into sections:

**Section 1 -** Reading the command string

 
`u2d_process_exec` reads the command string one byte at a time into `cmd` until it hits a null byte.  
This function has two major security flaws. Firstly, `cmd` is only 4096 bytes (`0x1000`) but there is no bounds check on `i`. If the command string is longer than 4095 bytes the loop keeps writing past the end of the buffer. Secondly, nothing validates or sanitizes what gets read into `cmd`. Any string the attacker puts in the payload lands here.

**Section 2 -** Optional CRC32 check

If the `CRC32` flag is set on the object, it reads 4 bytes and verifies the checksum. As discussed earlier this only protects against accidental corruption, not intentional tampering. An attacker can always compute a valid `CRC32` for any payload they want.


**Section 3 -** Fork and privilege drop

The function forks a child process, drops privileges to `G.uid` and `G.gid` (1001 on the real target), then calls `system(cmd)`.

The privilege drop happens in the child only. The parent process retains its original root privileges. This distinction matters because `u2d_process_file()` runs in the parent process, not a child.

The `system(cmd)` reads a `cmd` string from the payload into a 4096 byte buffer and passes it directly to `system()`. `system()` passes its argument to `/bin/sh -c` which means the full shell is available. There is no sanitization, no validation, and no allow list of permitted commands. This is an instance of OS command injection.

There is also a secondary vulnerability here. The read loop has no bounds check on the index variable `i`.


**Function 6 -** `u2d_process_file()`

**Section 1 -** Reading the destination path

  

Same pattern as `u2d_process_exec()`. Reads a null-terminated string one byte at a time into a fixed buffer. Same two problems:

`dst` is only 256 bytes (`0x100`) with no bounds check on `i`. A destination path longer than 255 bytes overflows the stack buffer. Also, there is no path validation whatsoever. The destination can be any path on the filesystem.

**Section 2 -** Reading the file mode

Reads 4 bytes as the file permissions. The attacker controls this too. Any permission mask can be set on the created file.


**Section 3 -** Opening and writing the file.

  
This is the critical part. `open()` runs in the main process, not a forked child. On the real target the main process runs as `root` throughout, so this `open()` calls runs as root.

`fchown()` then changes ownership to `G.uid` and `G.gid,` but this happens after the file is already created and written. So the file gets created by `root` in a root-owned directory, content written by root, and only then handed off to `uid=1001`.

`u2d_process_exec()` forks a child and drops privileges before doing anything sensitive. `u2d_process_file()` never forks. Everything runs in the main process. This is the fundamental difference between the two handlers and the reason FILE objects are more dangerous than EXE.

This makes FILE objects the most powerful path for an attacker. Combined with unrestricted path selection, an attacker can write to any sensitive system location. For example:

- `/etc/cron.d/` for persistent scheduled execution.
- `/root/.ssh/authorized_keys` for permanent passwordless SSH access.
- `/etc/sudoers.d/` for privilege escalation on demand.


## 3.4 Source Code Analysis Summary

Reading through the source, two functions stood out immediately.

`u2d_process_exec()` passes the command string from the payload directly to `system()` with no sanitization. Any shell command an attacker can get into an `OBJ_EXEC` payload will execute on the device. The only barrier is the signature check in `u2d_apply_image_from_stdin()`. If `--onlysigned` is set, the image needs a valid `HMAC-SHA256` signature. In the lab I have `key.priv` which removes that barrier entirely.

`u2d_process_file()` is the more dangerous one. It writes files to arbitrary paths on the filesystem without any path validation, and does so in the main process which retains root privileges on the real SUID target. This makes it the most useful path for persistence.

The header file already gave me the structure. The next step was building the tool to produce valid signed `.u2d` images containing my own payloads.

## Creating u2d_forge.py - VULN-1

I know the format from the header file and I know that I need to produce a `.u2d` file containing an `OBJ_EXEC` object with my command. My starting point was a simple question: What does a minimal valid `.u2d` file look like in bytes?

`update2d.h` says that the file header is 8 bytes:

Every single `.u2d` file starts with exactly 8 bytes in the header `struct`. It consist of 2 bytes for magic, 1 byte for version, 1 byte for flags and 4 bytes for size.

Immediately followed by 32 bytes of `HMAC-SHA256` tag and then the object with 1 byte typeflgs, 4 bytes size and n bytes command. Important to note that the size doesn’t include header or `HMAC` tag, it is entirely the size of the object.

_Minimal .u2d_

_Minimal .u2d output_

**Header:** 
- `5550` = "UP" `magic`
- `02` = `version` 2
- `02` = `FLG_HMAC_SHA256`
- `08000000` = `size` is 8 bytes

**Object:**
- `00` = `typeflgs` = `0x00` = `OBJ_EXEC`, no flags
- `03000000` = `size` = 3 in little endian
- `696400` = `"id\x00"` in `ASCII`

Total bytes before `HMAC` is 16(8 header + 8 object).

Next step would be to add the `HMAC` signature. I need to read the dummy key from `key.priv` and compute `HMAC-SHA256` over the `object` payload, then insert the 32 byte tag between the header and the objects:

_Add HMAC signature_

_Add HMAC signature output_

`Key` is 32 bytes, `HMAC` tag is 32 bytes. Both correct. Let’s put it all together:


_Output_

The terminal output confirmed the bytes were structured correctly. The real test was running the image against `update2d` using the same flags as the real target to verify the command actually executes.

The screenshot above proves that my minimal custom .`u2d` file can run with `update2d` and executes the commands as expected.

That completes two objectives: *”Primary objective: Find a way to make update2d execute unintended commands”* and *”Produce a proof of concept .u2d file that runs a command of our choosing.”*.

## 3.5 Examining key.priv and the images

Technically, `OBJ_EXEC` is designed to run commands. The catch is it's meant to run only the manufacturer's commands, protected by the signing key. But ARC4 is a stream cipher, if the same key encrypts multiple images, the keystream gets reused. XORing two intercepted ciphertexts cancels the keystream, and knowing one plaintext recovers it entirely. Once the keystream is recovered, the signing barrier falls apart and what was supposed to be a controlled update mechanism becomes arbitrary code execution for anyone who can intercept two encrypted images.

I have six intercepted images(`ImgA.u2d`, `ImgB1.u2d`, `ImgB2.u2d`, `ImgC1.u2d`, `ImgC2.u2d`, `ImgD1.u2d`). Based on how ARC4 works as a stream cipher, if any two were encrypted with the same key, I can attempt recovery.  

I pointed out earlier that  the `src/README` describes that the keyfile is used for both authentication and decryption: "Master key used for authentication and decryption." This means the same key field controls both the `HMAC` signature verification and the ARC4 decryption of any encrypted image.


Checking the flags byte at offset 3 of each image header revealed the following:
- imgA.u2d: flags = `0x02` = `FLG_HMAC_SHA256` only (signed, not encrypted)
- imgB1.u2d: flags = `0x0a` = `FLG_HMAC_SHA256` + `FLG_ZLIB` (signed + `ZLIB`)
- imgB2.u2d: flags = `0x03` = `FLG_HMAC_SHA256` + `FLG_LZ4` (signed + `LZ4`)
- imgC1.u2d: flags = `0x06` = `FLG_HMAC_SHA256` + `FLG_ARC4` (signed + encrypted)
- imgC2.u2d: flags = `0x06` = `FLG_HMAC_SHA256` + `FLG_ARC4` (signed + encrypted)
- imgD.u2d: magic = `0x5555` = `UU` encoded wrapper, inner flags unknown

`imgC1` and `imgC2` are the only two images sharing identical flags. Both are signed and `ARC4` encrypted with no compression, making them the most promising candidates for a known plaintext attack. XORing the two ciphertexts cancels the keystream entirely, leaving `P1 XOR P2`. The fixed structure of the `U2D` format means I already know what parts of the plaintext look like: the `HMAC` tag is always 32 bytes, the `object header` is always 5 bytes, and for a simple image the first object is likely an `OBJ_EXEC` with a predictable structure. That known plaintext is enough to start recovering the keystream and from there potentially the key itself.

## 3.6 Analyzing `arc4.c`

`src/arc.c` has two functions that map directly to the two phases of ARC4. `rc4_init` is the Key Scheduling Algorithm (KSA) . `rc4_next` is one step of the Pseudo Random Generation Algorithm (PRGA), it produces one keystream byte at a time.`

As Check Point Research (https://research.checkpoint.com/2022/attacking-very-weak-rc4-like-ciphers-the-hard-way/) describes: *"A Key Scheduling Algorithm (KSA) takes your key and generates a 256-byte array, and then a Pseudo-Random Generation Algorithm (PRGA) uses that byte array to output an endless stream of bytes (the key stream), which look like random noise unless you know what the original byte array was."*

Looking at `arc4.c` confirmed that the ARC4 implementation has no nonce. The keystream is derived purely from the key. This means the same key always produces the same keystream, which is the fundamental weakness I want to exploit. The theory gets explained as each step of the script builds on it. It is a textbook implementation where the `C code` maps directly to the standard 
ARC4 algorithm. For that reason, I am not going to walkthrough the code first.`

## 3.7 Building keystreampwn.py
#### Read size of ImgC1 and ImgC2

For the XOR attack payload of the two encrypted need to overlap. The keystream cancellation only works up to the length of the shorter ciphertext. The shorter payload length is the maximum number of keystream bytes I can recover in one shot.

  
_Output_

The size difference is dramatic. `ImgC1` is 32MB while `ImgC2` is 159 bytes. This means the known plaintext attack can only recover 151 bytes of keystream from this pair, which is enough to decrypt imgC2 completely but only covers the very start of imgC1.



#### Decrypting the intercepted images

The next step was to actually decrypt them. In the lab this is straightforward since I have `key.priv`. The decryption process is simply the reverse of what `u2d_receive_image()` does, read the payload after the 8 byte header, run `ARC4` with the key, extract the 32 byte `HMAC` tag from the start of the decrypted data, then parse the objects that follow.

The ARC4 algorithm has two phases:

**Phase 1 - Key Scheduling Algorithm (KSA):**


The `ARC4` implementation follows two phases directly matching `arc4.c`. The `KSA` initializes a 256 element array and scrambles it using the key. No nonce, no randomness, purely key-derived.

**Phase 2 - Pseudo Random Generation Algorithm (PRGA)**

  
The `PRGA` then uses that scrambled array to generate a keystream, one byte at a time, XORed with the input to produce the output. Since decryption is identical to encryption in a stream cipher, the same function handles both. The important thing here is that the `KSA` only takes the key as input, so the same key always produces the same keystream from byte zero, no matter what is being encrypted.

Lastly I print the output without the header:


_Output_

Now I need to remove the 32 bytes of `HMAC` tag and try and print the objects as `ASCII`, to see if it makes sense:


_Output_

The decrypted output was immediately readable. The null bytes and non-printable bytes at the start are the binary object headers. The 5 byte `typeflgs` and `size` fields defined in `update2d.h`. Everything after that is plaintext:

| Object                 | Type               |
| ---------------------- | ------------------ |
| `# Extended .u2d demo` | `EXEC`             |
| `hello`                | `FILE destination` |
| `Hello, world!\n`      | `FILE contents`    |
| `hello -> there`       | `LINK`             |
| `cat hello there`      | `EXEC`             |
| `hello`                | `ULNK`             |
| `there`                | `ULNK`             |

The image is a demo containing all four object types in sequence: EXEC, FILE, LINK and ULNK. The decryption is confirmed correct. The Python ARC4 implementation produces the same output as the C implementation in `arc4.c.`

More importantly, I now have both the ciphertext and the plaintext of `imgC2`. That gives me everything needed for the known plaintext attack, I can recover the keystream directly without needing to guess anything.

Keystream = ciphertext XOR plaintext

Since ARC4 uses no nonce or randomness, the keystream is the same one used to encrypt `ImgC1`.Whatever I recover here can be used to decrypt the start of imgC1 without the key.

  
Output:


The recovered keystream length being 151 bytes looks correct since it should be the length of `ImgC2` without the header. Now I can attempt to decrypt `ImgC1` without using the key.

Output:


The known plaintext attack worked. Without touching the key, the first 151 bytes of C1 decrypted cleanly. The first 32 bytes are unreadable binary as expected since it is the `HMAC` tag. After that the objects start and are readable:

```
- echo 'Factory resetting data partition..'
- /data/dding3000/data.u5fs.gz
- U5FS
```

They are the start of a the real intercepted firmware update. The device factory resets its data partition and then receives a `U5FS` filesystem image written to `/data/dding3000/data.u5fs.gz`-

The `U5FS` string is a nice callback. It is the same filesystem format used to deliver this entire assignment. So the real device actually boots from a `U5FS` image, the same format I unpacked earlier.

The attack only recovered 151 bytes of `ImgC1` because that is the length of `imgC2`, which is the shorter of the two ciphertexts. On the real target, intercepting a second encrypted image of similar size or larger than `imgC1` would give full decryption of both. Combined with the fact that the same key controls both encryption and signing, a successful key recovery would also produce a valid signing key for forging update packages. Anyone who can intercept two images could go from eavesdropping to forging update packages.

Having decrypted `imgC2` with the lab key and partially decrypted `imgC1` without it wraps up the decryption objective.

### Objectives Recap

The primary objective of making `update2d` execute unintended commands was satisfied by exploiting the unsanitized `system()` call in `u2d_process_exec()`. A forged signed image containing an `OBJ_EXEC` payload with shell commands was accepted and executed by the service.

The proof of concept objective was satisfied by the same demonstration.`Testevil.u2d` is the concrete deliverable, a minimal valid signed `.u2d` file that potentially can run any command of my choosing.

The decryption objective was satisfied in two ways. First by decrypting `imgC2` directly using the lab key, confirming the `ARC4` implementation was correct. Then by recovering the keystream through known plaintext attack and using it to partially decrypt `imgC1` without the key, revealing the start of a real intercepted firmware update.
In hindsight, I could have spend more time writing a script that could decrypt all of the image files for the analysts. 

Two objectives remain and the bonus objective of escalating from `uid=1001` to `root`. The solution currently only works with signed unencrypted images. The real target at the Hilbert Hotel may use any combination of compression, encryption and encoding. The forger needs to be extended to handle all feature combinations. This is the next objective I want to focus on.

## 3.8 Extending forger for any feature combination

Looking at the six intercepted images I saw every combination:

1. Signed only (`imgA`)
2. Signed + ZLIB (`imgB1`)
3. Signed + LZ4 (`imgB2`)
4. Signed + ARC4 (`imgC1`, `imgC2`)
5. UU encoded + ARC4 + ZLIB (`imgD`)

The forger currently only produces the simplest possible valid image, that are signed but not encrypted. The image set bit 1 with `flags=0x02` meaning `FLG_HMAC_SHA256`. This could cause issues if on the real target the service might be configured with `--onlycrypto` which would reject any encrypted image according to `update2d.h`.

The transform pipeline order from `u2d_receive_image()` tells me the encoding order. On disk data is encoded outermost first:

**`objects -> lz4 -> arc4 -> zlib -> uuencode`**

### ARC4

So I apply transforms to the object bytes before building the header. I started with ARC4 since I already have the RC4 code from `keystreampwn.py`:


Adding a simple toggle makes it easy to switch on or off. The `OR` operation `FLAGS |= 0x04` adds the `ARC4` bit to whatever flags are already set without touching the others. So a signed encrypted image turns `0x02` (signed only) into `0x06` (signed and encrypted) by combining the two bit patterns together. OR is a bitwise operation that compares two bits and returns 1 if either of them is 1. 

A visual representation looks like:

| Binary     | Hex    | Meaning                          |
|------------|--------|----------------------------------|
| `0000 0010` | `0x02` | `FLG_HMAC_SHA256` (bit 1 set)   |
| `0000 0100` | `0x04` | `FLG_ARC4` (bit 2 set)          |
| `0000 0110` | `0x06` | Both flags set (OR of the above) |

Running the updated forger against update2d with the same command as before should produce identical output, the service decrypts the payload, verifies the signature, and executes the command. The only difference is the image is now encrypted in transit.

The object bytes are encrypted before the HMAC is computed and the header is built. Printing the object both before and after encryption shows clearly what RC4 does to the payload:


The first attempt at producing an encrypted signed image returned error 2000 `U2DERR_BADSIG`. My initial assumption was that the HMAC should be computed over the plaintext objects and the encrypted objects written separately. That was wrong. Tracing through `u2d_verify_image()` and `u2d_receive_image()` more carefully revealed that `update2d` decrypts the entire payload after the header as one block before doing anything else. Meaning the HMAC tag and objects are encrypted together. Encrypting only the objects and leaving the tag in plaintext causes the signature check to fail because `update2d` decrypts the entire payload as one block before reading the tag. I updated my script with:


Output:

### Refactoring of code
Before adding the remaining transforms, the script was cleaned up. The toggle feature was moved to the top to make it easy to switch combinations on and off, the `FLAGS` byte is now built dynamically based on which toggles are active, and the transform pipeline is clearly separated from the object construction. This makes it straightforward to add `LZ4`, `ZLIB` and `UU` encoding in the same pattern.


### LZ4 and ZLIB

The next step was adding `LZ4` and `ZLIB`. I place `if` statements in the same order as the order of transform from `u2d_receive_image()`:

**`objects -> lz4 -> arc4 -> zlib -> uuencode`**


I only showcased `LZ4` here, not `ZLIB`. All I have to do was flip my `ENCRYPT` to `False` and `LZ4` to `True` in the toggles. 


Output:

Checking the output confirmed that the compression working. `flags=0x3` is exactly what I expected with `FLG_LZ4` set on bit 0 and `FLG_HMAC_SHA256` set on bit 1.
One funny side effect: the file actually got bigger from 66 bytes to 89 bytes. `LZ4` compression overhead outweighs any savings on a payload this small.

Next I wanted to make sure the feature combinations worked correctly together. Running with `FLG_LZ4` on bit 0, `FLG_HMAC_SHA256` on bit 1, and `FLG_ARC4` on bit 2 gives `flags=0x7`, which is what the output shows:


### UU-encoding

The last remaining transform is `UU` encoding. That's the outermost layer, wrapping everything else. 
UU encoding is slightly more involved than the others. Looking at `xfrm_uudecode.c` from the source, the format expects:

`begin 644 image.u2d\n`  
`[encoded lines]`  
`\n`  
`end\n`

And the outer magic bytes change from `UP` to `UU`.

I wanted to check `xfrm_uudecode.c` to see exactly what format the decoder expects:

From xfrm_uudecode.c - The begin header check:


From xfrm_uudecode.c - The backtick check:

I needed to write a `UU` encoder that matches the format expected by `xfrm_uudecode.c`. The format required is:

- A `begin 644 image.u2d` header line
- The data encoded in 45-byte chunks, each chunk prefixed with a length byte
- A backtick line signaling end of data
- An `end` footer

Python's `uu` module was deprecated in 3.11 and removed in 3.13, superseded by `base64` encoding. Searching online I found the library called `binascii` that I can use to `UU` encode the image. `b2a_uu()` takes 45 bytes, which is the `UU` standard chunk size, and returns an encoded line including the length byte at the start. 45 raw bytes encodes to 60 `ASCII` characters per line, which is why I chunk the data in pieces of 45 bytes.

Getting the encoding right took a few attempts. Reading `u2d_receive_image()` more carefully revealed that the magic bytes are read from the raw stream before the `UU` decoder is starts. This means the 2 byte `UU` magic sits entirely outside the `UU` encoded content. The decoder then handles the rest of the header (`version`, `flags`, `size`) through the decoding layer.

My first attempt encoded the entire image including the `UP` magic bytes. That meant the version field was being read through the decoder rather than raw, producing garbage value and error 1003 (`BADHDR_VERSION`). The fix was to skip the first two bytes when encoding.


  
Output:



#### Verifying all feature combinations

`flags=0x12` confirms that the function `uu_encoding` works and the commands executes as expected. Flipping all the toggles on gives `flags=0x1f`, confirming every feature combination works together.

  
### Bonus objective: root access to target

The bonus objective asks for a way to escalate from the unprivileged `uid=1001` that `EXEC` commands run as, to `root`. The path to this was already identified during the source code analysis of `u2d_process_file(),` `FILE` objects are processed in the main process which retains `root` privileges on the real SUID binary, and there is no path validation on the destination. Combined with the ability to forge valid signed images, this means I can write any file to any location on the filesystem as `root`.

**Choosing the persistence mechanism**

Two approaches stood out to me: 
1. `PAM module injection` would be the stealthier option. A malicious module loaded into the authentication stack accepts a hardcoded password through the normal login flow, producing logs that look completely legitimate. The problem is `PAM modules` need to be compiled for the target architecture, and a misconfigured PAM config locks out all authentication with no recovery without physical access. 
   I only have access to writing a new file, not appending the existing `PAM module`. I would need to read the existing config and include it in the write action. In a perfect scenario with access to the existing config, PAM module changing would be optimal but too much risk for a lab proof of concept.

2. `SSH key injection` is simpler. No compilation, no architecture specific code, and the test is immediate and unambiguous. Either the SSH login works or it doesn't. For that reason SSH key injection was the starting point, with `PAM module injection` documented as a follow-up worth pursuing with more time.

Writing an attacker controlled public key to `/root/.ssh/authorized_keys` gives permanent passwordless root shell access that survives reboots and credential rotation. There are no unusual processes, no outbound connections until I choose to connect, and SSH logins with an injected key look identical to legitimate administrator activity in logs.

### SSH key injection

First, I generated a throwaway keypair that has an empty passphrase using `-N ””`:


Next, I needed to add `OBJ_FILE` support to my `u2d_forger.py` python script. The file object payload structure from `u2d_process_file()` looks like:

- 1 byte `typeflgs` (`0x01` = `OBJ_FILE`, no flags)
- 4 bytes `size` (total bytes: path + null + mode + data)
- n bytes `dst` path (null terminated)
- 4 bytes `mode` (file permissions as u32)
- n bytes `file data` (the actual content)

I added a section that uses the `OBJ_FILE` and feeds the throwaway SSH keypair. I also added another toggle for payloads to make the script more clear.

  

  

To verify the key was written correctly, I checked `authorized_keys` with `cat`: 

Then SSH'd into my own machine locally:

The SSH login succeeded immediately with no password prompt, confirming persistent access through the injected key. The bonus objective is complete.

### Update2d wrap up

All five objectives have been completed.

The primary objective and the proof of concept objective are effectively the same thing. Finding the vulnerability and building the exploit are two sides of the same coin. Both were satisfied by exploiting the unsanitized `system()` call in `u2d_process_exec()`. `Testevil.u2d` is the concrete deliverable.

Feature combinations were handled by extending `u2d_forger.py` to support the full transform pipeline, tested individually and all five simultaneously.

Decryption was satisfied two ways: `imgC2` directly with the lab key, and `imgC1` partially via known plaintext attack, recovering 151 bytes and revealing the start of a real firmware update.

The bonus objective was met through `SSH key injection` via `u2d_process_file()`. It confirmed passwordless root login.
# 4 Netupsrv

From the original briefing, `netupsrv` is the file uploader. It's the service that receives `.u2d` images over the network and passes them to `update2d`. Everything I built in the update2d section assumes `netupsrv` is already working as a delivery mechanism. Now I flipped the assumption and attacked `netupsrv` itself.

What I have to work with:

- `netup` - the server binary to test against
- `dog.jpg` - a real file extracted from a deployed device spool directory
- `capture.pcap` - a packet capture of a client transferring a file
- `update2d-wrapper` - shell script that calls update2d

The objectives in order:

1. Reverse engineer the protocol from the PCAP
2. Implement a client
3. Send a file and confirm it works
4. Trigger update2d through it
5. Read files from the spool directory
6. Gain arbitrary command execution
7. Read and write files anywhere on the filesystem

I think the `PCAP` is the golden ticket. A real client-server exchange is captured. This is where I want to start.
## 4.1 Focusing in on the PCAP

Examining the PCAP in wireshark showed me that there are two machines communicating strictly on TCP:

- 127.11.4.52:42027
- 127.202.3.1:6666

  
The first 3 packets showed a classic TCP handshake with SYN / SYN-ACK / ACK. No protocol data.

#### Exchange 1 – Handshake ping/pong

Packets 4 and 6 show a custom handshake. The client sends `hI` and `p`, the server responds with `hI` and `P`, both 10 bytes long. The `hI` bytes appear in both directions, likely a session identifier or magic value.

  
  
#### Exchange 2 – Upload command

Packet 8 and 9 appeared to be the upload command. ASCII clearly shows: `a5 ...uploaded.jpg..K`

  
The command byte looked like `a` for upload followed by 5 byte(possibly a sub-type or flag), then the null-terminated filename `uploaded.jpg`, then `K,` which is likely a checksum or length field.

The server responded with an uppercase A. This packet is 14 bytes total.

#### Assumptions based on the two exchanges

These two exchanges give me a starting point about the protocol at hand:

- Packet format: `[length byte] [command byte] [payload]`
- Client commands: lowercase (`p` = ping, `a` = upload)
- Server responses: uppercase (`P`, `A`)
- Magic/session: `hI` bytes present in both directions
- Filename: null-terminated string in upload command

## 4.2 Netupsrv binary

I took a peek at the `netupsrv` binary. First I tried to extract information with `strings netup | less`, but that looked like gibberish.

Next I tried grepping for error messages and prompt strings.

  

All those `os.(*File).Read`, `os.NewFile` symbols are Go's standard library. That's why `strings` gives mostly noise. Go binaries have their own symbol table, I could target the `main` package directly, where the protocol logic lives.:

  
The list of functions is small. There are no seperate handlers per command. `Main.handleConnection` seems to handle the entire protocol.

Since the pattern looked like `[length][lowercase letter][payload]`, the plan was to poke all 26 letters and see what error responses came back. Before that I needed a working handshake. From the PCAP I suspected `'p'` from the client and `'P'` from the server. Lowercase for client, uppercase for server response.

  

  
I wrote a script trying to get a proper handshake setup, looking for 50 at the command byte as a response:


Output:
  
It worked. The response matched `capture.pcap` exactly. The response changed byte 1 from `70` (`'p'`) to `50` (`'P'`). The next step was to add the upload command that I saw in the PCAP.

  
I copied the upload command directly from the PCAP:


Output:


  
The server responded with `0x41` = `'A'`, the uppercase ack for the `'a'` upload command.
______________________________________________________________
At this point I ran out of time. The handshake and upload command were both working and matching the PCAP. This would be a solid foundation to continue building on.




# 5 Conclusion

This assessment covered three distinct areas.

The U5FS extractor in section 1 went from a custom filesystem spec with no existing tooling to a working Python script that recursively unpacks the entire filesystem, including indirect block support.

Section 3 turned source code analysis into a working exploit chain. Arbitrary command execution via a forged `.u2d` image, partial decryption of intercepted firmware updates without the key, and persistent root access through SSH key injection.

Section 4 made a start on `netupsrv`. The handshake and upload command were both reversed and implemented from the PCAP alone before time ran out.

The update2d chain is the most complete result. Given more time, `netupsrv` would be the natural next target. The groundwork is done. The protocol format is understood, the client works, and the binary is identified as Go.