#!/usr/bin/env python3
"""MounRiver Studio と MRS ツールチェーンの最新版 → catalog/toolchains.csv

ArduinoCore-CH32 を建てるのに要る上流のツール（IDE・RISC-V ツールチェーン・ベンダの
チップ対応パック）は WCH/MounRiver 側の都合で更新される。どの版が最新かは
<https://www.mounriver.com/download> にしか出ないが、あのページは Vue の SPA で、
中身は公開 JSON API から来ている（ページ HTML の `window._CONFIG['domianURL']`）:

    api/version/fetchRecent           swType(1=MRS1, 2=MRS2) × osType ごとの最新 IDE
    api/version/fetchRecent2          Linux MRS2 の全ファイル（.deb と .tar.xz）。swType は無視される
    api/version/fetchRecentOpenOcd    MRS_Toolchain（Linux/macOS）の最新
    api/version/fetchRecentCommunity  Community 版
    api/version/fetchRecentComponents ベンダのチップ対応パック（WCH ほか）
    api/version/{getDownloadUrl, fetchRecentOpenOcdUrl, fetchRecentComponentsUrl}
                                      resourceId → ダウンロードURL

ダウンロードURLは**署名つきで、要求した側のIPに紐付く**（`?sign=…&from=<IP>`）ので
表には入れられない。代わりに URL を返す API を `download_api` に持つ——それ自体は
腐らないし、叩けばその場で有効なURLが返る。

`docs/worklist.ja.md` の「載せないもの」（ツールチェーンの**チップ別対応状況**）とは
別物で、こちらは上流が公開している**版の一覧**そのもの。人手で書き写す表ではなく
毎週 CI が取り直すので、上流が動けば差分として出るし、APIが変われば赤くなる。

確度（`confidence`）:

    confirmed  掲載されたファイルが実際に配信されている（署名URLを解決して HEAD 200。
               API がサイズを言う行はサイズも一致した）
    reference  API の掲載のみ（`--no-verify`。配信側は確かめていない）
    conflict   配信されているサイズが掲載と食い違う

実行:
    uv run tools/build_toolchains.py              # 差分を表示するだけ
    uv run tools/build_toolchains.py --write      # catalog/toolchains.csv を書く
    uv run tools/build_toolchains.py --history    # IDE の旧版一覧（表には入れない）
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths  # noqa: E402

API = "https://api.mounriver.com/mountriver/api/version/"
TIMEOUT = 60
# API の綴り（大文字）→ 表の綴り。表側は語彙を正規化する（目録の役目）。
OS_NAME = {"WINDOWS": "windows", "LINUX": "linux", "MAC": "macos"}
ARCH_NAME = {"X64": "x64", "X86": "x86", "X32": "x86", "ARM64": "arm64"}
# API が bits を言わない行（Windows/macOS の IDE）は、配布ファイル名の語で補う。
ARCH_IN_NAME = re.compile(r"[_-](X64|X86|X32|ARM64)[._-]", re.IGNORECASE)
# 使う側の順（ツールチェーンが先、対応パックが最後）。行の並びはこれで決まる。
KIND_ORDER = ("toolchain", "ide", "ide-community", "components")

COLUMNS = ["kind", "edition", "os", "arch", "version", "file", "size_bytes",
           "released", "download_api", "#", "confidence", "basis"]


class ToolchainError(RuntimeError):
    """API が期待した形で答えなかった。

    黙って空の表を書くより落ちる方がよい（sync_catalog.py と同じ考え）。
    上流のAPIが変わったときに赤い run が出るのが、気付くための唯一の手段。
    """


def note(message: str) -> None:
    """GitHub Actions の run ページに出る警告注釈。"""
    print(f"::warning::{message}" if os.environ.get("GITHUB_ACTIONS") else f"warning: {message}",
          file=sys.stderr)


def fetch(endpoint: str, **params) -> object:
    url = API + endpoint + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - 原因は握りつぶさず載せて投げ直す
        raise ToolchainError(f"{url} を取得できませんでした: {exc}") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ToolchainError(f"{url} の応答がJSONではありません: {body[:120]!r}") from exc
    if not isinstance(payload, dict) or not payload.get("success"):
        raise ToolchainError(f"{url} が失敗を返しました: {str(payload)[:160]}")
    return payload.get("result")


def head_size(url: str) -> int | None:
    """配信側が返す Content-Length。届かなければ落とす（掲載を信じて上書きしない）。"""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            length = resp.headers.get("Content-Length")
    except Exception as exc:  # noqa: BLE001
        raise ToolchainError(f"{url.split('?')[0]} を配信側で確認できませんでした: {exc}") from exc
    return int(length) if length and length.isdigit() else None


def arch_of(bits: str | None, file: str) -> str:
    if bits and bits.upper() in ARCH_NAME:
        return ARCH_NAME[bits.upper()]
    m = ARCH_IN_NAME.search(file)
    return ARCH_NAME[m.group(1).upper()] if m else ""


def make_row(kind: str, edition: str, os_type: str, version: str, file: str, *,
             bits: str | None = None, size: object = None, released: str | None = None,
             resource_id: str = "", endpoint: str = "getDownloadUrl", basis: str = "") -> dict:
    if os_type not in OS_NAME:
        raise ToolchainError(f"{file}: 知らない osType {os_type!r}")
    return {
        "kind": kind,
        "edition": edition,
        "os": OS_NAME[os_type],
        "arch": arch_of(bits, file),
        "version": str(version or ""),
        "file": file,
        "size_bytes": str(size) if size else "",
        "released": (released or "").split(" ")[0],
        "download_api": f"{API}{endpoint}?resourceId={resource_id}",
        "confidence": "reference",
        "basis": basis,
    }


def collect() -> list[dict]:
    """上流が「いま最新」と言っている配布物を、全部で1行ずつ。"""
    rows: list[dict] = []

    for it in fetch("fetchRecentOpenOcd", lang="en") or []:
        rows.append(make_row("toolchain", "", it["osType"], it["version"], it["fileName"],
                             bits=it.get("systemBits"), size=it.get("fileSize"),
                             released=it.get("createTime"), resource_id=it["id"],
                             endpoint="fetchRecentOpenOcdUrl", basis="api(fetchRecentOpenOcd)"))

    for os_type in OS_NAME:
        for sw, edition in ((1, "mrs1"), (2, "mrs2")):
            it = fetch("fetchRecent", swType=sw, osType=os_type, lang="en")
            if it and it.get("softFileName"):
                rows.append(make_row("ide", edition, os_type, it["version"], it["softFileName"],
                                     released=it.get("crtTime"), resource_id=it["softId"],
                                     basis=f"api(fetchRecent:swType={sw},osType={os_type})"))
        # 同じ版の別形式（Linux の .deb と .tar.xz）はこちらにしか出ない。
        for it in fetch("fetchRecent2", osType=os_type, lang="en") or []:
            for rel in it.get("upgradeRelationBoList") or []:
                rows.append(make_row("ide", "mrs2", rel.get("osType") or os_type, it["version"],
                                     rel["softFileName"], bits=rel.get("bits"),
                                     released=it.get("crtTime"), resource_id=rel["softReId"],
                                     basis=f"api(fetchRecent2:osType={os_type})"))
        for it in fetch("fetchRecentCommunity", osType=os_type, lang="en") or []:
            for rel in it.get("relationList") or []:
                rows.append(make_row("ide-community", "community", rel.get("osType") or os_type,
                                     it["version"], rel["softFileName"], bits=rel.get("bits"),
                                     released=it.get("crtTime"), resource_id=rel["softReId"],
                                     basis=f"api(fetchRecentCommunity:osType={os_type})"))

    # チップ対応パック。版番号は連番（verIndex）で、実体の日付はファイル名が持つ。
    for it in fetch("fetchRecentComponents", lang="en") or []:
        rows.append(make_row("components", (it.get("vendorName") or "").lower(), it["osType"],
                             it.get("verIndex", ""), it["fileName"], size=it.get("fileSize"),
                             released=it.get("createTime"), resource_id=it["id"],
                             endpoint="fetchRecentComponentsUrl", basis="api(fetchRecentComponents)"))

    unique: dict[str, dict] = {}
    for r in rows:  # 同じファイルが2つの endpoint に出る（Linux MRS2 の .deb）。先勝ち
        unique.setdefault(r["file"], r)
    out = sorted(unique.values(),
                 key=lambda r: (KIND_ORDER.index(r["kind"]), r["edition"], r["os"], r["arch"], r["file"]))

    tally = collections.Counter(r["kind"] for r in out)
    # 上流の仕様変更は「エラー」ではなく「急に減った結果」として現れる。書き込む前に落とす。
    if tally["toolchain"] < 1 or tally["ide"] < 3:
        raise ToolchainError(f"取得できた件数が少なすぎます: {dict(tally)}")
    return out


def verify(rows: list[dict]) -> None:
    """掲載されたファイルが実際に配信されているかを、配信側のIPから見て確かめる。

    署名は要求元IPに紐付くので、URLを取る側と HEAD する側は同じホストである必要がある。
    """
    for r in rows:
        endpoint, _, query = r["download_api"][len(API):].partition("?")
        resource_id = urllib.parse.parse_qs(query)["resourceId"][0]
        url = fetch(endpoint, resourceId=resource_id)
        if not isinstance(url, str) or not url.startswith("http"):
            raise ToolchainError(f"{r['file']}: {endpoint} がURLを返しませんでした: {str(url)[:80]!r}")
        if r["file"] not in url:
            raise ToolchainError(f"{r['file']}: 解決されたURLが別のファイルです: {url.split('?')[0]}")
        size = head_size(url)
        if size is None:
            note(f"{r['file']}: 配信側がサイズを言いません")
            r["confidence"] = "confirmed"
            r["basis"] += "+head(no size)"
            continue
        if r["size_bytes"] and int(r["size_bytes"]) != size:
            r["confidence"] = "conflict"
            r["basis"] += f"+!head(size={size})"
            continue
        r["confidence"] = "confirmed"
        r["basis"] += f"+head(size={size})"
        r["size_bytes"] = str(size)  # APIが言わない行（IDE）はここで埋まる


def history() -> list[dict]:
    """IDE の旧版（querySoftVList）。表には入れず、聞かれたときに出すだけ。"""
    out = []
    for os_type in OS_NAME:
        for sw, edition in ((1, "mrs1"), (2, "mrs2")):
            result = fetch("querySoftVList", pageNo=1, pageSize=9999, swType=sw,
                           osType=os_type, lang="en") or {}
            for it in result.get("records") or []:
                out.append({"edition": edition, "os": OS_NAME[os_type], "version": it["version"],
                            "file": it.get("softFileName", ""),
                            "released": (it.get("crtTime") or "").split(" ")[0],
                            "download_api": f"{API}getDownloadUrl?resourceId={it['softId']}"})
    return sorted(out, key=lambda r: (r["edition"], r["os"], r["version"]), reverse=True)


def committed(dest: Path) -> list[dict]:
    if not dest.exists():
        return []
    with dest.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def differences(old: list[dict], new: list[dict]) -> list[str]:
    """行を file で突き合わせ、増減と変化した列を並べる。"""
    before = {r["file"]: r for r in old}
    after = {r["file"]: r for r in new}
    lines = []
    for file in sorted(set(before) - set(after)):
        lines.append(f"- 消えた: {file} ({before[file]['kind']} {before[file]['version']})")
    for file in sorted(set(after) - set(before)):
        lines.append(f"- 増えた: {file} ({after[file]['kind']} {after[file]['version']})")
    for file in sorted(set(before) & set(after)):
        changed = [f"{c}: {before[file].get(c, '')!r} → {after[file][c]!r}"
                   for c in COLUMNS if c != "#" and before[file].get(c, "") != after[file][c]]
        if changed:
            lines.append(f"- 変わった: {file} — " + " / ".join(changed))
    return lines


def summary(lines: list[str], rows: list[dict]) -> None:
    """GitHub が run の上に出す要約。"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    tally = collections.Counter(r["kind"] for r in rows)
    with open(path, "a", encoding="utf-8") as out:
        out.write(f"## 上流ツールの最新版\n\n{len(rows)} 件 {dict(tally)}\n\n")
        out.write("\n".join(lines) + "\n" if lines else "差分なし\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="catalog/toolchains.csv を書く")
    ap.add_argument("--no-verify", action="store_true",
                    help="配信側の確認を省く（confidence は reference どまり。commit しないこと）")
    ap.add_argument("--history", action="store_true", help="IDE の旧版一覧を出して終わる")
    ap.add_argument("--out", type=Path, default=None, help="出力ディレクトリの上書き（試験用）")
    args = ap.parse_args()

    try:
        if args.history:
            for r in history():
                print(f"{r['edition']:5s} {r['os']:8s} {r['version']:7s} {r['released']}  "
                      f"{r['file']}\n      {r['download_api']}")
            return 0
        rows = collect()
        if not args.no_verify:
            verify(rows)
    except ToolchainError as exc:
        print(f"::error::{exc}" if os.environ.get("GITHUB_ACTIONS") else f"error: {exc}",
              file=sys.stderr)
        return 1

    dest = paths.table("toolchains", args.out)
    lines = differences(committed(dest), rows)
    tally = collections.Counter(r["confidence"] for r in rows)
    print(f"{len(rows)} 件 {dict(tally)}", file=sys.stderr)
    for line in lines or ["差分なし"]:
        print(f"  {line}", file=sys.stderr)
    summary(lines, rows)
    if any(r["confidence"] == "conflict" for r in rows):
        note("掲載と配信でサイズが食い違う行があります（conflict）")
    if args.write:
        paths.write(dest, rows, COLUMNS)
        print(f"{dest} を更新しました", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
