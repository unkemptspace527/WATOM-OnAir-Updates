#!/usr/bin/env python3
"""W.A.T.O.M. public short-form feed: reject private/third-party audio and missing editorial QA."""
from pathlib import Path
from datetime import datetime, timezone
from hashlib import sha256
from mutagen.mp3 import MP3
import json, re

ROOT=Path(__file__).resolve().parent.parent
MANIFEST=ROOT/"weekly-releases/current.json"
m=json.loads(MANIFEST.read_text("utf-8"))
def fail(reason): raise SystemExit("W.A.T.O.M. public feed rejected: "+reason)
def when(value):
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        if dt.tzinfo is None:fail("Timestamps require explicit UTC offsets")
        return dt.astimezone(timezone.utc)
    except (ValueError,TypeError,AttributeError): fail("Malformed news/weather timestamp")
if m.get("schema_version")!=1 or m.get("station")!="W.A.T.O.M. 1240 AM":
    fail("Wrong schema or station")
day=m.get("release_id","")
rev=m.get("revision")
if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",day) or not isinstance(rev,int) or rev<1:
    fail("Invalid release date/revision")
if m.get("approved_by")!="WATOM programming director" or not m.get("approved_at"):
    fail("Missing editorial signoff")
when(m["approved_at"])
pack=day+"-r"+str(rev)
for kind in ("music_rotation","jazz_rotation","ad_rotation"):
    rotation=m.get(kind,[])
    if not isinstance(rotation,list) or len(rotation)>150 or len(rotation)!=len(set(rotation)):
        fail("Invalid rotation metadata")
    # References are opaque names for tracks ALREADY on the user's private device;
    # no music or drama bytes may be hosted in this public feed.
    if not all(isinstance(x,str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,55}\.mp3",x) for x in rotation):
        fail("Bad opaque bundled-audio filename")
tracks=m.get("tracks",[])
if not isinstance(tracks,list) or len(tracks)>70: fail("Too many public clips")
seen=set()
total=0
for clip in tracks:
    filename=clip.get("file","")
    if not isinstance(filename,str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,55}\.mp3",filename) or filename in seen:
        fail("Invalid or repeated filename")
    seen.add(filename)
    cat=clip.get("category")
    if cat not in ("bulletin","weather","civil_defense","ad","host","night_host","station_id","jingle"):
        fail("Public feed is for original short-form audio only, NOT music or theater")
    if clip.get("broadcast_approved") is not True or clip.get("approved_by")!="WATOM programming director":
        fail("Unapproved audio")
    if clip.get("rights_cleared") is not True or clip.get("origin_type")!="original":
        fail("No independently verified original distribution rights")
    if cat in ("weather","bulletin"):
        start,end=when(clip.get("valid_from","")),when(clip.get("valid_until",""))
        allowed=36 if cat=="weather" else 72
        if start>=end or (end-start).total_seconds()>allowed*3600:
            fail("Weather/news validity expired or implausibly long")
    audio=ROOT/"weekly-releases/audio"/pack/filename
    if not audio.is_file() or not 4096<=audio.stat().st_size<=900000:fail("Missing/oversized audio")
    total+=audio.stat().st_size
    if total>24*1024*1024:fail("Weekly media exceeds 24 MiB cap")
    if clip.get("size")!=audio.stat().st_size:fail("Audio byte length mismatch")
    actual_hash=sha256(audio.read_bytes()).hexdigest()
    if clip.get("sha256")!=actual_hash:fail("Audio hash mismatch")
    try:duration=MP3(audio).info.length
    except Exception:fail("Not a valid decodable MP3")
    if abs(duration-float(clip.get("durationSeconds",0)))>1.5:fail("Inaccurate clip duration")
    audit=clip.get("approval_record","")
    if not isinstance(audit,str) or not re.fullmatch(r"[a-z0-9_-]{10,70}\.json",audit):
        fail("Missing QA report name")
    record=ROOT/"weekly-releases/audits"/pack/audit
    if not record.is_file():fail("Missing QA report")
    qa=json.loads(record.read_text("utf-8"))
    if qa.get("audio_sha256")!=actual_hash or qa.get("editorial_approved") is not True:
        fail("QA not tied to exact audio")
    if qa.get("voice_checked") is not True or qa.get("content_checked") is not True:
        fail("Voice/script review incomplete")
    if qa.get("original_content_verified") is not True or qa.get("public_distribution_cleared") is not True:
        fail("Public release rights not proven")
allowed_audio={ROOT/"weekly-releases/audio"/pack/name for name in seen}
hosted={f for f in ROOT.rglob("*.mp3") if ".git" not in f.parts}
if hosted-allowed_audio:fail("Unapproved audio file exists in public repository")
print("PASS: public original-only W.A.T.O.M. release",pack,"clips:",len(tracks),"rotation slots:",sum(len(m.get(k,[])) for k in ("music_rotation","jazz_rotation","ad_rotation")))
