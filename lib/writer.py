"""Byte-faithful UnityFS writer: rebuild a bundle changing only chosen objects.

Everything outside the patched objects — header, type trees, script types,
externals, every untouched object — is copied verbatim. Only the object data
region is re-laid-out, and only the affected byte_start/byte_size/file_size
fields are rewritten.
"""
import struct
import lz4.block


def align8(n):
    return (n + 7) & ~7


def rebuild_serialized(sf, new_objects):
    """new_objects: {path_id: bytes}. Returns new serialized-file bytes."""
    raw = bytearray(sf.raw)

    # lay out the object data region in the original object order
    ordered = sorted(sf.objects, key=lambda o: o["byte_start"])
    region = bytearray()
    placement = {}
    for o in ordered:
        data = new_objects.get(o["path_id"])
        if data is None:
            data = sf.raw[sf.data_offset + o["byte_start"]: sf.data_offset + o["byte_start"] + o["byte_size"]]
        start = len(region)
        region += data
        placement[o["path_id"]] = (start, len(data))
        pad = align8(len(region)) - len(region)
        region += b"\0" * pad

    # trailing padding is not part of the last object; trim to the last object end
    last = max(placement.values(), key=lambda v: v[0])
    region = region[:last[0] + last[1]]

    # patch the object table entries in place.
    # Header fields are always big-endian, but the metadata follows the file's
    # own endianness flag — this table is little-endian here.
    e = ">" if sf.endian else "<"
    for o in sf.objects:
        start, size = placement[o["path_id"]]
        struct.pack_into(e + "q", raw, o["start_off"], start)
        struct.pack_into(e + "I", raw, o["size_off"], size)

    out = bytes(raw[:sf.data_offset]) + bytes(region)

    # file_size lives twice for v22: legacy u32 at 4, real i64 at 24
    out = bytearray(out)
    if sf.version >= 22:
        struct.pack_into(">q", out, 24, len(out))
    else:
        struct.pack_into(">I", out, 4, len(out))
    return bytes(out)


def rebuild_bundle(bundle, node_index, new_node_data, out_path, compress=True):
    """Write the bundle back with one node replaced.

    Blocks are LZ4HC-compressed like Unity's own, so the file stays close to its
    original size; pass compress=False for a plain, easier-to-debug bundle.
    """
    data = bytearray()
    for i, (off, size, flags, path) in enumerate(bundle.nodes):
        payload = new_node_data if i == node_index else bundle.data[off:off + size]
        data += payload
    data = bytes(data)

    # 128 KB chunks, mirroring Unity's own chunking
    CHUNK = 131072
    blocks = []
    payload = bytearray()
    pos = 0
    while pos < len(data):
        chunk = data[pos:pos + CHUNK]
        if compress:
            packed = lz4.block.compress(chunk, mode="high_compression",
                                        store_size=False)
            # only keep the compressed form if it actually helps
            if len(packed) < len(chunk):
                blocks.append((len(chunk), len(packed), 3))   # 3 = LZ4HC
                payload += packed
            else:
                blocks.append((len(chunk), len(chunk), 0))
                payload += chunk
        else:
            blocks.append((len(chunk), len(chunk), 0))
            payload += chunk
        pos += len(chunk)
    data = bytes(payload)

    nodes = []
    off = 0
    for i, (o, size, flags, path) in enumerate(bundle.nodes):
        sz = len(new_node_data) if i == node_index else size
        nodes.append((off, sz, flags, path))
        off += sz

    bi = bytearray()
    bi += bundle.data_hash
    bi += struct.pack(">i", len(blocks))
    for usize, csize, bflags in blocks:
        bi += struct.pack(">IIH", usize, csize, bflags)
    bi += struct.pack(">i", len(nodes))
    for o, sz, flags, path in nodes:
        bi += struct.pack(">qqI", o, sz, flags) + path.encode() + b"\0"
    bi = bytes(bi)

    head = bytearray()
    head += bundle.signature.encode() + b"\0"
    head += struct.pack(">I", bundle.version)
    head += bundle.unity_version.encode() + b"\0"
    head += bundle.unity_revision.encode() + b"\0"
    size_off = len(head)
    head += struct.pack(">q", 0)                      # total size, filled in below
    head += struct.pack(">I", len(bi))                # compressed blocks-info size
    head += struct.pack(">I", len(bi))                # uncompressed blocks-info size
    head += struct.pack(">I", (bundle.flags & ~0x3F)) # same flags, compression = none
    while len(head) % 16:
        head += b"\0"

    tail = bi
    if bundle.flags & 0x200:                          # pad block data to 16 bytes
        pad = (16 - (len(head) + len(bi)) % 16) % 16
        tail += b"\0" * pad

    out = bytes(head) + tail + data
    out = bytearray(out)
    struct.pack_into(">q", out, size_off, len(out))
    open(out_path, "wb").write(bytes(out))
    return len(out)
