#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NÉN DỮ LIỆU HÓA ĐƠN  -  Galaxy Studio
=====================================
Gộp hàng nghìn file hóa đơn (.zip / .xml) thành các gói nhỏ theo NGÀY LẬP hóa đơn,
đồng thời chỉ giữ MỘT bản cho các file mẫu giống hệt nhau (ảnh nền, details.js, ...).

  - Không sửa, không xóa file nguồn.
  - Mỗi gói là 1 file .zip bình thường, web đọc được ngay (không cần sửa cách tải dữ liệu).
  - Chạy lại nhiều lần được: chỉ thêm hóa đơn mới vào gói, bỏ qua hóa đơn đã có.
  - Sau khi ghi xong, tự mở lại từng gói và so sánh từng file với bản gốc (kiểm tra toàn vẹn).

Cách dùng:
    python nen_du_lieu.py  THU_MUC_NGUON  THU_MUC_DICH
Ví dụ:
    python nen_du_lieu.py NGUON DATA
Chỉ cần Python 3.8+ (không cần cài thêm thư viện).
"""
import argparse
import collections
import hashlib
import os
import re
import sys
import tempfile
import zipfile

NLAP = re.compile(rb"<NLap>\s*(\d{4}-\d{2}-\d{2})")
NO_DATE = "khong-ro-ngay"
XML_DIR = "_xml/"          # hóa đơn gốc dạng .xml đơn lẻ nằm trong thư mục này của gói
STORE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".zip")


def md5(b):
    return hashlib.md5(b).hexdigest()


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f} {u}" if u != "B" else f"{n} B"
        n /= 1024


def scan(src):
    for root, _, names in os.walk(src):
        for n in sorted(names):
            if n.lower().endswith((".zip", ".xml")):
                yield os.path.join(root, n)


def uid_of(path, src):
    base = os.path.splitext(os.path.relpath(path, src))[0]
    return base.replace(os.sep, "__")


def read_item(path):
    """Đọc 1 file nguồn -> (kind, {tên_trong_gói_gốc: bytes}). kind = 'zip' | 'xml'."""
    if path.lower().endswith(".xml"):
        with open(path, "rb") as f:
            return "xml", {os.path.basename(path): f.read()}
    files = {}
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            if not i.filename.endswith("/"):
                files[i.filename] = z.read(i.filename)
    return "zip", files


def peek_date(path):
    """Chỉ đọc phần XML để lấy ngày lập (nhanh hơn đọc cả file zip)."""
    if path.lower().endswith(".xml"):
        with open(path, "rb") as f:
            m = NLAP.search(f.read())
        return m.group(1).decode() if m else NO_DATE
    with zipfile.ZipFile(path) as z:
        for i in sorted(z.infolist(), key=lambda x: x.filename):
            if i.filename.lower().endswith(".xml"):
                m = NLAP.search(z.read(i.filename))
                if m:
                    return m.group(1).decode()
    return NO_DATE


def date_of(files):
    for name in sorted(files):
        if name.lower().endswith(".xml"):
            m = NLAP.search(files[name])
            if m:
                return m.group(1).decode()
    return NO_DATE


def write_zip(path, entries):
    """entries: dict tên -> bytes. Ghi ra file tạm rồi thay thế (an toàn nếu bị ngắt giữa chừng)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=os.path.dirname(path) or ".")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w") as z:
            # file dùng chung (không có "/") ghi trước, sau đó đến từng hóa đơn
            for name in sorted(entries, key=lambda n: ("/" in n, n)):
                low = name.lower()
                comp = zipfile.ZIP_STORED if low.endswith(STORE_EXT) else zipfile.ZIP_DEFLATED
                zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                zi.compress_type = comp
                z.writestr(zi, entries[name], compress_type=comp,
                           compresslevel=9 if comp == zipfile.ZIP_DEFLATED else None)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def build_bundle(dest, items):
    """items: list (uid, kind, files). Trả về (số hóa đơn thêm mới, số bị bỏ qua vì đã có, danh sách lỗi)."""
    existing = {}
    if os.path.exists(dest):
        with zipfile.ZipFile(dest) as z:
            for i in z.infolist():
                if not i.filename.endswith("/"):
                    existing[i.filename] = z.read(i.filename)

    # đặt tên trong gói + bỏ qua hóa đơn đã có
    fresh, skipped = [], 0
    for uid, kind, files in items:
        if kind == "xml":
            named = {XML_DIR + n: b for n, b in files.items()}
        else:
            named = {f"{uid}/{n}": b for n, b in files.items()}
        xml_names = [n for n in named if n.lower().endswith(".xml")] or list(named)
        if all(n in existing for n in xml_names):
            skipped += 1
            continue
        fresh.append((uid, kind, files, named))

    # chọn bản dùng chung (ở gốc gói) cho từng file mẫu: bản phổ biến nhất trong lô mới
    root = {n: b for n, b in existing.items() if "/" not in n}
    votes = collections.defaultdict(collections.Counter)
    sample = {}
    for uid, kind, files, _ in fresh:
        if kind != "zip":
            continue
        for n, b in files.items():
            if "/" not in n and not n.lower().endswith(".xml") and n not in root:
                h = md5(b)
                votes[n][h] += 1
                sample[(n, h)] = b
    for n, c in votes.items():
        root[n] = sample[(n, c.most_common(1)[0][0])]

    out = dict(existing)
    out.update({n: b for n, b in root.items()})
    for uid, kind, files, named in fresh:
        for n, b in files.items():
            full = (XML_DIR + n) if kind == "xml" else f"{uid}/{n}"
            shared = (kind == "zip" and "/" not in n and not n.lower().endswith(".xml")
                      and n in root and md5(root[n]) == md5(b))
            if not shared:
                out[full] = b
    write_zip(dest, out)

    # kiểm tra toàn vẹn: mở lại gói, mỗi file gốc phải khớp từng byte
    problems = []
    with zipfile.ZipFile(dest) as z:
        names = set(z.namelist())
        for uid, kind, files, named in fresh:
            for n, b in files.items():
                if kind == "xml":
                    full, fallback = XML_DIR + n, None
                else:
                    full, fallback = f"{uid}/{n}", (n if "/" not in n else None)
                got = z.read(full) if full in names else (z.read(fallback) if fallback in names else None)
                if got is None or md5(got) != md5(b):
                    problems.append(f"{uid}: file '{n}' không khớp bản gốc")
    return len(fresh), skipped, problems


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Nén dữ liệu hóa đơn thành gói theo ngày")
    ap.add_argument("nguon", help="Thư mục chứa file .zip/.xml gốc")
    ap.add_argument("dich", help="Thư mục xuất các gói (ví dụ DATA)")
    a = ap.parse_args()
    src, dst = os.path.abspath(a.nguon), os.path.abspath(a.dich)
    if not os.path.isdir(src):
        sys.exit(f"Không thấy thư mục nguồn: {src}")
    if src == dst or dst.startswith(src + os.sep):
        sys.exit("Thư mục đích phải khác và không nằm trong thư mục nguồn.")

    paths = list(scan(src))
    print(f"Tìm thấy {len(paths)} file nguồn trong {src}")
    if not paths:
        return

    # lượt 1: chỉ đọc ngày lập để chia nhóm
    groups, errors, in_bytes = collections.defaultdict(list), [], 0
    for k, p in enumerate(paths, 1):
        try:
            in_bytes += os.path.getsize(p)
            groups[peek_date(p)].append(p)
        except Exception as e:
            errors.append(f"{os.path.relpath(p, src)}: {e}")
        if k % 500 == 0:
            print(f"  đã đọc ngày lập {k}/{len(paths)}...")

    # lượt 2: dựng từng gói theo ngày
    added = skipped = 0
    problems = []
    for day in sorted(groups):
        items = []
        for p in groups[day]:
            try:
                kind, files = read_item(p)
                items.append((uid_of(p, src), kind, files))
            except Exception as e:
                errors.append(f"{os.path.relpath(p, src)}: {e}")
        n_new, n_skip, prob = build_bundle(os.path.join(dst, day + ".zip"), items)
        added += n_new
        skipped += n_skip
        problems += prob
        print(f"  {day}.zip  +{n_new} hóa đơn mới" + (f", bỏ qua {n_skip} đã có" if n_skip else ""))

    out_bytes = sum(os.path.getsize(os.path.join(dst, f)) for f in os.listdir(dst) if f.endswith(".zip"))
    print("\n=========== KẾT QUẢ ===========")
    print(f"Đã thêm: {added} hóa đơn · bỏ qua (đã có): {skipped} · gói theo ngày: {len(groups)}")
    print(f"Dung lượng nguồn: {human(in_bytes)}  →  thư mục đích: {human(out_bytes)}")
    if errors:
        print(f"\n⚠ {len(errors)} file nguồn đọc lỗi (không bị đưa vào gói):")
        for e in errors[:30]:
            print("   -", e)
    if problems:
        print(f"\n❌ {len(problems)} file KHÔNG khớp bản gốc, ĐỪNG dùng kết quả này:")
        for e in problems[:30]:
            print("   -", e)
        sys.exit(1)
    print("\n✔ Kiểm tra toàn vẹn: mọi file trong gói đều khớp từng byte với bản gốc.")


if __name__ == "__main__":
    main()
