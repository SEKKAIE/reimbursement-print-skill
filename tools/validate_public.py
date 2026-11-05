"""Validate public skill structure, links and generic-data boundaries."""
from pathlib import Path
from zipfile import ZipFile
import json
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".mjs", ".txt"}
EXPECTED_BINARY = Path("assets/package/forms/reimbursement-forms.xlsx")
EXCLUDED_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
PATTERNS = {
    "absolute local drive path": re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/](?!/)"),
    "home directory path": re.compile(r"/(?:Users|home)/[^/\s<>]+/"),
    "access token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|sk-[A-Za-z0-9_-]{24,})\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "email address": re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}
errors = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        errors.append(message)


def scan_text(label, text):
    for name, pattern in PATTERNS.items():
        matches = pattern.findall(text)
        if name == "email address":
            matches = [value for value in matches if not value.endswith("@users.noreply.github.com")]
        check(not matches, f"{label}: possible {name}")


required = ["SKILL.md", "README.md", "CONTRIBUTING.md", "LICENSE", "agents/openai.yaml",
            "references/setup.md", "references/job-contract.md", "references/print-layouts.md",
            "assets/package/forms/reimbursement-forms.xlsx", "assets/package/forms/field-map.json",
            "assets/package/forms/fill_forms.mjs", "assets/package/forms/preserve_print_layout.py",
            "assets/package/scripts/prepare_receipts.py", "assets/package/scripts/pack_by_layout.py",
            "assets/package/schema/job.schema.json", "assets/package/schema/job.example.json"]
for name in required:
    check((ROOT / name).is_file(), f"Missing {name}")

for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts):
        continue
    relative = path.relative_to(ROOT)
    check(path.suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".ofd", ".zip", ".db", ".sqlite"}, f"Unexpected data/binary file: {relative}")
    check(path.suffix != ".xlsx" or relative == EXPECTED_BINARY, f"Unexpected workbook: {relative}")
    if path.suffix in TEXT_SUFFIXES or path.name in {"LICENSE", ".gitignore"}:
        text = path.read_text(encoding="utf-8-sig")
        scan_text(str(relative), text)
        if path.suffix == ".json":
            json.loads(text)
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("#"):
                    continue
                file_target = target.split("#", 1)[0]
                if file_target:
                    check((path.parent / file_target).is_file(), f"Broken link {relative}: {target}")

skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
check(skill.startswith("---\n"), "SKILL.md frontmatter missing")
check("name: reimbursement-print\n" in skill, "Unexpected skill name")
check("description:" in skill.split("---", 2)[1], "Skill description missing")

example = json.loads((ROOT / "assets/package/schema/job.example.json").read_text(encoding="utf-8-sig"))
check(not example["expenses"] and not example["evidence"], "Example must not contain real transactions")
check(all(not value for value in example["profile"].values()), "Example profile defaults must be blank")

with ZipFile(ROOT / EXPECTED_BINARY) as archive:
    check(archive.testzip() is None, "Workbook CRC failure")
    content_types = archive.read("[Content_Types].xml").decode("utf-8")
    check(bool(re.search(r"<Types\s", content_types)) and 'xmlns="http://schemas.openxmlformats.org/package/2006/content-types"' in content_types,
          "Workbook content types require the conventional default namespace for the XLSX import runtime")
    for name in archive.namelist():
        check(not any(part in name.lower() for part in ["externallinks/", "embeddings/", "comments", "persons/", "media/", "customxml/"]), f"Unexpected workbook member: {name}")
        if name.endswith((".xml", ".rels")):
            text = archive.read(name).decode("utf-8")
            scan_text("workbook:" + name, text)
            check('TargetMode="External"' not in text, f"External workbook relationship: {name}")
            ET.fromstring(text)
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    guide = ET.fromstring(archive.read("xl/worksheets/sheet4.xml"))
    for cell in ["B4", "B5", "B6", "B7", "B8", "B9"]:
        node = guide.find(f".//m:c[@r='{cell}']", namespace)
        value = node.find("m:v", namespace) if node is not None else None
        inline = node.find("m:is", namespace) if node is not None else None
        check(value is None or not value.text, f"Nonblank profile cell {cell}")
        check(inline is None or not "".join(inline.itertext()), f"Nonblank profile cell {cell}")

if errors:
    print(json.dumps({"status": "failed", "checks": checks, "errors": errors}, indent=2))
    sys.exit(1)
print(json.dumps({"status": "passed", "checks": checks, "errors": []}))
