"""Pure-Python extractor for Android A/B OTA payloads (payload.bin).

Supports full OTAs (REPLACE, REPLACE_XZ, REPLACE_BZ, ZSTD, ZERO, DISCARD).
Incremental (delta) OTAs need the source images and are rejected with a clear error.
The payload may be given directly or inside an OTA .zip (stored or deflated).
"""
from __future__ import annotations

import bz2
import hashlib
import lzma
import struct
import zipfile
from dataclasses import dataclass, field
from typing import BinaryIO, Callable

MAGIC = b"CrAU"

OP_REPLACE, OP_REPLACE_BZ, OP_ZERO, OP_DISCARD, OP_REPLACE_XZ, OP_ZSTD = 0, 1, 6, 7, 8, 14
OP_NAMES = {2: "MOVE", 3: "BSDIFF", 4: "SOURCE_COPY", 5: "SOURCE_BSDIFF", 9: "PUFFDIFF",
            10: "BROTLI_BSDIFF", 11: "ZUCCHINI", 12: "LZ4DIFF_BSDIFF", 13: "LZ4DIFF_PUFFDIFF"}


class PayloadError(Exception):
    pass


# ----------------------------------------------------------- tiny protobuf
def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def pb_decode(buf: bytes) -> dict[int, list]:
    fields: dict[int, list] = {}
    pos, n = 0, len(buf)
    while pos < n:
        key, pos = _varint(buf, pos)
        num, wt = key >> 3, key & 7
        if wt == 0:
            val, pos = _varint(buf, pos)
        elif wt == 1:
            val = int.from_bytes(buf[pos:pos + 8], "little")
            pos += 8
        elif wt == 2:
            ln, pos = _varint(buf, pos)
            val = buf[pos:pos + ln]
            pos += ln
        elif wt == 5:
            val = int.from_bytes(buf[pos:pos + 4], "little")
            pos += 4
        else:
            raise PayloadError(f"Неподдерживаемый тип поля protobuf: {wt}")
        fields.setdefault(num, []).append(val)
    return fields


def _first(d: dict, key: int, default=0):
    v = d.get(key)
    return v[0] if v else default


# ----------------------------------------------------------------- model
@dataclass
class Operation:
    type: int
    data_offset: int
    data_length: int
    dst_extents: list[tuple[int, int]]
    data_sha256: bytes = b""


@dataclass
class Partition:
    name: str
    size: int
    operations: list[Operation] = field(default_factory=list)
    sha256: bytes = b""

    @property
    def is_delta(self) -> bool:
        return any(op.type in OP_NAMES for op in self.operations)


def _zstd_decompress(data: bytes) -> bytes:
    try:
        from compression import zstd  # Python 3.14+
        return zstd.decompress(data)
    except ImportError:
        pass
    try:
        import zstandard
        return zstandard.ZstdDecompressor().decompressobj().decompress(data)
    except ImportError as exc:
        raise PayloadError("Образ сжат zstd — установите модуль: pip install zstandard") from exc


class Payload:
    def __init__(self, path: str):
        self.path = path
        self._zip: zipfile.ZipFile | None = None
        self._fh: BinaryIO
        self._base = 0  # offset of payload.bin inside the opened file
        self._open()
        self._parse()

    # ------------------------------------------------------------ opening
    def _open(self) -> None:
        if zipfile.is_zipfile(self.path):
            self._zip = zipfile.ZipFile(self.path)
            try:
                info = self._zip.getinfo("payload.bin")
            except KeyError:
                raise PayloadError("В архиве нет payload.bin — это не A/B OTA прошивка") from None
            if info.compress_type == zipfile.ZIP_STORED:
                # read straight from the zip file: fast random access
                fh = open(self.path, "rb")
                fh.seek(info.header_offset)
                local = fh.read(30)
                if local[:4] != b"PK\x03\x04":
                    raise PayloadError("Повреждённый ZIP")
                name_len, extra_len = struct.unpack("<HH", local[26:30])
                self._base = info.header_offset + 30 + name_len + extra_len
                self._fh = fh
            else:
                self._fh = self._zip.open(info)  # seekable but slower
        else:
            self._fh = open(self.path, "rb")

    def _read_at(self, offset: int, length: int) -> bytes:
        self._fh.seek(self._base + offset)
        data = self._fh.read(length)
        if len(data) != length:
            raise PayloadError("Неожиданный конец файла payload")
        return data

    def close(self) -> None:
        try:
            self._fh.close()
        finally:
            if self._zip:
                self._zip.close()

    # ------------------------------------------------------------ parsing
    def _parse(self) -> None:
        head = self._read_at(0, 24)
        if head[:4] != MAGIC:
            raise PayloadError("Это не payload.bin (нет сигнатуры CrAU)")
        version, manifest_size = struct.unpack(">QQ", head[4:20])
        if version not in (1, 2):
            raise PayloadError(f"Неизвестная версия payload: {version}")
        header_size = 20
        sig_size = 0
        if version == 2:
            sig_size = struct.unpack(">I", head[20:24])[0]
            header_size = 24
        manifest = pb_decode(self._read_at(header_size, manifest_size))
        self.data_start = header_size + manifest_size + sig_size
        self.block_size = _first(manifest, 3, 4096)
        self.version = version
        self.partitions: list[Partition] = []
        for raw in manifest.get(13, []):
            p = pb_decode(raw)
            info = pb_decode(_first(p, 7, b""))
            part = Partition(name=bytes(_first(p, 1, b"")).decode(errors="replace"),
                             size=_first(info, 1, 0), sha256=bytes(_first(info, 2, b"")))
            for raw_op in p.get(8, []):
                o = pb_decode(raw_op)
                exts = []
                for raw_e in o.get(6, []):
                    e = pb_decode(raw_e)
                    exts.append((_first(e, 1, 0), _first(e, 2, 0)))
                part.operations.append(Operation(_first(o, 1, 0), _first(o, 2, 0), _first(o, 3, 0),
                                                 exts, bytes(_first(o, 8, b""))))
            if not part.size and part.operations:
                part.size = max(s + n for op in part.operations for s, n in op.dst_extents) * self.block_size
            self.partitions.append(part)

    @property
    def is_delta(self) -> bool:
        return any(p.is_delta for p in self.partitions)

    # --------------------------------------------------------- extraction
    def extract(self, part: Partition, out_path: str,
                progress: Callable[[int, int], None] | None = None,
                cancelled: Callable[[], bool] | None = None, verify: bool = True) -> bool:
        """Write the partition image. Returns False if the hash did not match."""
        if part.is_delta:
            bad = sorted({OP_NAMES[o.type] for o in part.operations if o.type in OP_NAMES})
            raise PayloadError(f"{part.name}: инкрементальная OTA ({', '.join(bad)}). Нужна полная прошивка.")
        bs = self.block_size
        total = len(part.operations)
        with open(out_path, "wb") as out:
            for i, op in enumerate(part.operations):
                if cancelled and cancelled():
                    raise PayloadError("Отменено")
                if op.type in (OP_ZERO, OP_DISCARD):
                    data = None
                else:
                    raw = self._read_at(self.data_start + op.data_offset, op.data_length)
                    if verify and op.data_sha256 and hashlib.sha256(raw).digest() != op.data_sha256:
                        raise PayloadError(f"{part.name}: повреждённый блок данных #{i}")
                    if op.type == OP_REPLACE:
                        data = raw
                    elif op.type == OP_REPLACE_XZ:
                        data = lzma.decompress(raw)
                    elif op.type == OP_REPLACE_BZ:
                        data = bz2.decompress(raw)
                    elif op.type == OP_ZSTD:
                        data = _zstd_decompress(raw)
                    else:
                        raise PayloadError(f"{part.name}: неизвестная операция {op.type}")
                pos = 0
                for start, num in op.dst_extents:
                    length = num * bs
                    out.seek(start * bs)
                    if data is None:
                        out.write(b"\0" * length)
                    else:
                        out.write(data[pos:pos + length])
                        pos += length
                if progress:
                    progress(i + 1, total)
            out.truncate(part.size)
        if verify and part.sha256:
            h = hashlib.sha256()
            with open(out_path, "rb") as fh:
                for chunk in iter(lambda: fh.read(4 << 20), b""):
                    h.update(chunk)
            return h.digest() == part.sha256
        return True
