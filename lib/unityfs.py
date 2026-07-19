"""Minimal, byte-faithful UnityFS bundle reader/writer.

Goal: unpack -> patch a serialized file -> repack, changing nothing except
what we intend. Everything we do not touch is copied verbatim.
"""
import struct
import lz4.block


class R:
    def __init__(self, data, pos=0, be=True):
        self.d, self.p, self.be = data, pos, be

    def _f(self, f):
        return (">" if self.be else "<") + f

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def u16(self):
        v = struct.unpack_from(self._f("H"), self.d, self.p)[0]; self.p += 2; return v

    def i32(self):
        v = struct.unpack_from(self._f("i"), self.d, self.p)[0]; self.p += 4; return v

    def u32(self):
        v = struct.unpack_from(self._f("I"), self.d, self.p)[0]; self.p += 4; return v

    def i64(self):
        v = struct.unpack_from(self._f("q"), self.d, self.p)[0]; self.p += 8; return v

    def cstr(self):
        e = self.d.index(b"\0", self.p)
        v = self.d[self.p:e].decode("utf-8", "replace"); self.p = e + 1
        return v

    def align(self, n=4):
        r = self.p % n
        if r:
            self.p += n - r


def decompress(data, flags, usize):
    ctype = flags & 0x3F
    if ctype == 0:
        return data
    if ctype in (2, 3):
        return lz4.block.decompress(data, uncompressed_size=usize)
    if ctype == 1:
        import lzma
        props, dict_size = data[0], struct.unpack("<I", data[1:5])[0]
        lc = props % 9; props //= 9
        pb, lp = props // 5, props % 5
        filt = [{"id": lzma.FILTER_LZMA1, "dict_size": dict_size, "lc": lc, "lp": lp, "pb": pb}]
        return lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=filt).decompress(data[5:])
    raise ValueError(f"unknown compression {ctype}")


class Bundle:
    def __init__(self, path):
        self.raw = open(path, "rb").read()
        r = R(self.raw)
        self.signature = r.cstr()
        self.version = r.u32()
        self.unity_version = r.cstr()
        self.unity_revision = r.cstr()
        self.size = r.i64()
        self.cbis = r.u32()          # compressed blocks-info size
        self.ubis = r.u32()          # uncompressed blocks-info size
        self.flags = r.u32()
        self.header_end = r.p

        if self.version >= 7:
            r.align(16)
        self.blocksinfo_start = r.p
        bi_raw = self.raw[r.p:r.p + self.cbis]
        self.blocksinfo_end = r.p + self.cbis
        bi = decompress(bi_raw, self.flags, self.ubis)

        b = R(bi)
        self.data_hash = b.d[b.p:b.p + 16]; b.p += 16
        self.blocks = [(b.u32(), b.u32(), b.u16()) for _ in range(b.i32())]  # usize, csize, flags
        self.nodes = [(b.i64(), b.i64(), b.u32(), b.cstr()) for _ in range(b.i32())]  # off, size, flags, path

        # 0x200 = block data must start on a 16-byte boundary after blocks info
        self.pad_blocks = bool(self.flags & 0x200)
        pos = self.blocksinfo_end
        if self.pad_blocks and pos % 16:
            pos += 16 - pos % 16
        self.data_start = pos

        # decompress the block stream
        chunks = []
        for usize, csize, bflags in self.blocks:
            chunks.append(decompress(self.raw[pos:pos + csize], bflags, usize))
            pos += csize
        self.data = b"".join(chunks)

    def node_bytes(self, i):
        off, size, _, _ = self.nodes[i]
        return self.data[off:off + size]

    def describe(self):
        return (f"UnityFS v{self.version} {self.unity_version}/{self.unity_revision}\n"
                f"  flags=0x{self.flags:x} cbis={self.cbis} ubis={self.ubis} size={self.size}\n"
                f"  blocks={len(self.blocks)} (first: {self.blocks[0] if self.blocks else None})\n"
                f"  nodes={[(n[0], n[1], n[2], n[3]) for n in self.nodes]}\n"
                f"  data={len(self.data)} bytes")


class SerializedFile:
    """Parses only what we need: header + type list + object table offsets."""

    def __init__(self, data):
        self.raw = data
        r = R(data)
        self.metadata_size = r.u32()
        self.file_size = r.u32()
        self.version = r.u32()
        self.data_offset = r.u32()
        self.endian = r.u8()
        r.p += 3                                   # reserved
        if self.version >= 22:
            self.metadata_size = r.u32()
            self.file_size = r.i64()
            self.data_offset = r.i64()
            r.i64()                                # unknown
        r.be = self.endian != 0
        self.unity_version = r.cstr()
        self.target_platform = r.i32()
        self.has_type_tree = bool(r.u8())
        self.type_count = r.i32()
        self.types_start = r.p
        self.types = []
        for _ in range(self.type_count):
            self.types.append(self._read_type(r))
        self.types_end = r.p
        self.object_count = r.i32()
        self.objtable_start = r.p
        self.objects = []
        for _ in range(self.object_count):
            r.align(4)
            pos = r.p
            path_id = r.i64()
            byte_start = r.i64() if self.version >= 22 else r.u32()
            byte_size = r.u32()
            type_id = r.i32()
            self.objects.append({"entry_off": pos, "path_id": path_id,
                                 "byte_start": byte_start, "byte_size": byte_size,
                                 "type_id": type_id, "size_off": pos + 8 + (8 if self.version >= 22 else 4),
                                 "start_off": pos + 8})
        self.objtable_end = r.p

    def _read_type(self, r, is_ref_type=False):
        class_id = r.i32()
        r.u8()                                     # is_stripped
        r.u16()                                    # script_type_index
        if class_id == 114:
            r.p += 16                              # script id
        r.p += 16                                  # old type hash
        if self.has_type_tree:
            node_count = r.i32()
            strbuf_size = r.i32()
            node_size = 32 if self.version >= 19 else 24
            r.p += node_count * node_size + strbuf_size
            if self.version >= 21:
                if is_ref_type:
                    r.cstr(); r.cstr(); r.cstr()   # class, namespace, assembly
                else:
                    dep_count = r.i32()
                    r.p += dep_count * 4
        return class_id

    def describe(self):
        return (f"SerializedFile v{self.version} endian={self.endian} "
                f"meta={self.metadata_size} size={self.file_size} data_off={self.data_offset}\n"
                f"  unity={self.unity_version} typetree={self.has_type_tree} "
                f"types={self.type_count} objects={self.object_count}\n"
                f"  objtable {self.objtable_start}..{self.objtable_end}")


if __name__ == "__main__":
    import sys
    b = Bundle(sys.argv[1])
    print(b.describe())
    for i, n in enumerate(b.nodes):
        print(f"--- node {i}: {n[3]}")
        try:
            sf = SerializedFile(b.node_bytes(i))
            print("   " + sf.describe().replace("\n", "\n   "))
            print("   first objects:", [(o["path_id"], o["byte_start"], o["byte_size"]) for o in sf.objects[:4]])
            print("   last  object :", (sf.objects[-1]["path_id"], sf.objects[-1]["byte_start"], sf.objects[-1]["byte_size"]))
        except Exception as e:
            print("   parse failed:", type(e).__name__, e)
