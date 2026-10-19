# python fix_ph.py {덱}.pptx — pptxgenjs가 쓴 개체 틀 번호를 본 덱 `내용_단쪽`과 같게 맞춤(pptx-guide 6-14)
# 빈 폴더 항목(이름이 /로 끝나는 zip 항목)도 함께 뺌 — 일부 도구가 손상 파일로 오인하는 것을 막기 위함
import re, shutil, sys, zipfile
src = sys.argv[1]
tmp = src + ".tmp"
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        if item.filename.endswith("/"):
            continue
        data = zin.read(item.filename)
        if re.match(r"ppt/(slides|slideLayouts)/slide(Layout)?\d+\.xml$", item.filename):
            x = data.decode("utf8")
            x = re.sub(r'<p:ph\s+idx="\d+"\s+type="title"[^>]*/>', '<p:ph type="title"/>', x)
            x = re.sub(r'<p:ph type="sldNum" sz="quarter" idx="\d+"/>', '<p:ph type="sldNum" idx="4"/>', x)
            data = x.encode("utf8")
        zout.writestr(item, data)
shutil.move(tmp, src)
print("개체 틀 번호 정리 완료:", src)
